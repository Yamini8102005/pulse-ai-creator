import json
from datetime import datetime, timedelta, timezone
from typing import List
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import insert

from .breeth_client import BreethClient
from .config import settings
from .db import agents, posts, rejection_records
from .editorial import judge_topics
from .llm_client import LLMClient
from .models import PostDraft, Topic, Persona
from .topic_discovery import discover_topics


POST_PROMPT = """
You are PULSE, an independent AI engineering observer. Write a concise, technically sharp, evidence-driven post with a slightly opinionated voice. Use the topic information to explain the technical development, why the topic was selected, and why it matters now.
Return JSON with fields:
{
  "text": string,
  "rationale": string,
  "why_now": string,
  "sources": [string]
}
"""


def _normalize_sources(topic: Topic) -> List[str]:
    return [str(topic.url)]


async def _render_post(topic: Topic, persona: Persona, llm: LLMClient) -> PostDraft:
    messages = [
        {"role": "system", "content": POST_PROMPT},
        {
            "role": "user",
            "content": (
                f"Persona: {persona.name} ({persona.domain})\n"
                f"Topic title: {topic.title}\n"
                f"Summary: {topic.summary}\n"
                f"URL: {topic.url}\n"
                f"PublishedAt: {topic.publishedAt.isoformat()}\n"
                "Write the post without clickbait, with technical clarity and evidence-driven judgment."
            ),
        },
    ]
    raw = await llm.chat(messages)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError(f"Post generation LLM response is not valid JSON: {raw}")

    return PostDraft(
        text=parsed["text"],
        rationale=parsed["rationale"],
        why_now=parsed["why_now"],
        sources=[str(s) for s in parsed.get("sources", _normalize_sources(topic))],
    )


async def _record_breeth_episode(agent_id: str, post_text: str, breeth: BreethClient) -> None:
    content = f"[{agent_id}] {post_text}"
    await breeth.record_episode(group_id=agent_id, content=content)


async def _has_seen_topic(agent_id: str, topic: Topic, session: AsyncSession, breeth: BreethClient | None = None) -> bool:
    stmt = select(posts).where(posts.c.topic_url == str(topic.url))
    result = await session.execute(stmt)
    if result.first():
        return True
    if breeth is not None:
        try:
            resp = await breeth.search_topic(group_id=agent_id, query=topic.title, limit=5)
            if resp and resp.get("edges"):
                return True
        except Exception:
            pass
    return False


async def publish_cycle(agent_id: str, session: AsyncSession, llm: LLMClient, breeth: BreethClient | None = None) -> None:
    result = await session.execute(select(agents).where(agents.c.id == agent_id))
    agent = result.mappings().first()
    if not agent:
        return
    persona = Persona(name=agent["persona_name"], domain=agent["persona_domain"])

    topics = await discover_topics()
    filtered: List[Topic] = []
    for topic in topics:
        if await _has_seen_topic(agent_id, topic, session, breeth):
            continue
        filtered.append(topic)

    selection = await judge_topics(filtered, persona, llm)
    now = datetime.now(timezone.utc)
    next_publish_at = now + timedelta(minutes=settings.publish_interval_minutes)

    if selection.selected_index is None or selection.selected_index >= len(filtered):
        for idx, topic in enumerate(filtered):
            reason = next(
                (r["reason"] for r in selection.rejection_reasons if r.get("topic_index") == idx),
                "Not selected by editorial judgment.",
            )
            record = {
                "id": str(uuid4()),
                "agent_id": agent_id,
                "recorded_at": now,
                "topic_title": topic.title,
                "topic_url": str(topic.url),
                "topic_source": topic.source,
                "reason": reason,
            }
            await session.execute(insert(rejection_records).values(record))
        await session.execute(
            update(agents)
            .where(agents.c.id == agent_id)
            .values(next_publish_at=next_publish_at, last_cycle_started_at=None)
        )
        await session.commit()
        return

    topic = filtered[selection.selected_index]
    draft = await _render_post(topic, persona, llm)
    full_rationale = f"{draft.rationale}\nRelevance now: {draft.why_now}"
    stored = {
        "id": str(uuid4()),
        "agent_id": agent_id,
        "created_at": now,
        "text": draft.text,
        "rationale": draft.rationale,
        "why_now": draft.why_now,
        "sources": [str(s) for s in draft.sources],
        "topic_title": topic.title,
        "topic_url": str(topic.url),
        "topic_source": topic.source,
        "topic_published_at": topic.publishedAt,
    }
    await session.execute(insert(posts).values(stored))
    await session.execute(
        update(agents)
        .where(agents.c.id == agent_id)
        .values(
            next_publish_at=next_publish_at,
            last_published_at=now,
            published_count=agents.c.published_count + 1,
            last_cycle_started_at=None,
        )
    )
    await session.commit()
    if breeth is not None:
        try:
            await _record_breeth_episode(agent_id, draft.text, breeth)
        except Exception:
            pass
