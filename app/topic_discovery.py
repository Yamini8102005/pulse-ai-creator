from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, List
import json

from .llm_client import LLMClient
from .models import Topic

TOPIC_DISCOVERY_PROMPT = """
You are PULSE, an AI engineering observer. Generate a list of up to 5 timely, production-relevant topics in AI engineering and emerging technology.
For each topic, include:
- title
- summary
- url
- publishedAt (UTC ISO 8601)
- source
Return only valid JSON as an array of objects with those exact keys.
"""


def _parse_topic(item: Any) -> Topic:
    published_at = item.get("publishedAt")
    if not published_at:
        raise ValueError("Topic item missing publishedAt")
    return Topic(
        title=item["title"],
        summary=item["summary"],
        url=item["url"],
        publishedAt=datetime.fromisoformat(published_at.replace("Z", "+00:00")),
        source=item["source"],
    )


async def discover_topics() -> List[Topic]:
    llm = LLMClient()
    messages = [
        {"role": "system", "content": TOPIC_DISCOVERY_PROMPT},
        {"role": "user", "content": "Generate topics relevant to AI Engineering & Emerging Technology."},
    ]
    raw = await llm.chat(messages)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Topic discovery LLM response is not valid JSON: {raw}") from exc
    if not isinstance(parsed, list):
        raise ValueError("Topic discovery response must be a JSON list of topics")
    topics: List[Topic] = []
    for item in parsed:
        if not isinstance(item, dict):
            raise ValueError("Each discovered topic must be a JSON object")
        topics.append(_parse_topic(item))
    return topics
