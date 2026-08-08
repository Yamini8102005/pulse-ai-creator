import json
from typing import List
from .models import EditorialSelection, Persona, Topic
from .llm_client import LLMClient


EDITORIAL_PROMPT = """
You are PULSE, an independent AI engineering observer with a sharp, concise, curious, evidence-driven, slightly opinionated voice.
You review candidate topics and choose at most one publication-worthy item for AI engineering and emerging technology audiences.
Reject weak, repetitive, overly promotional, low-signal, hype-driven, or generic AI content.
Prefer technically meaningful developments such as AI agent architecture, RAG, LLM engineering, tool protocols, infrastructure, developer tools, open-source AI, and production systems.

For each candidate, explain whether it should be selected or rejected, and why.
If you select a topic, provide a short post outline useful for writing the final post.
Return only valid JSON with these fields:
{
  "selected_index": number | null,
  "decision_reason": string,
  "rejection_reasons": [
    {"topic_index": number, "title": string, "reason": string}
  ],
  "post_outline": string | null
}
"""


def _build_topic_list(topics: List[Topic], persona: Persona) -> str:
    rows = []
    for index, topic in enumerate(topics):
        rows.append(
            f"{index}. [{topic.source}] {topic.title}\nSummary: {topic.summary}\nURL: {topic.url}\nPublishedAt: {topic.publishedAt.isoformat()}"
        )
    return "\n\n".join(rows)


async def judge_topics(topics: List[Topic], persona: Persona, llm: LLMClient) -> EditorialSelection:
    if not topics:
        return EditorialSelection(selected_index=None, decision_reason="No topics discovered.", rejection_reasons=[], post_outline=None)

    topic_list = _build_topic_list(topics, persona)
    messages = [
        {"role": "system", "content": EDITORIAL_PROMPT},
        {
            "role": "user",
            "content": (
                f"Persona: {persona.name}, domain: {persona.domain}\n"
                f"Candidates:\n{topic_list}\n"
                "If the topic is already covered by prior memory, reject it as redundant."
            ),
        },
    ]
    raw = await llm.chat(messages)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError(f"Editorial LLM response is not valid JSON: {raw}")

    return EditorialSelection(
        selected_index=parsed.get("selected_index"),
        decision_reason=parsed.get("decision_reason", "No decision reason provided."),
        rejection_reasons=parsed.get("rejection_reasons", []),
        post_outline=parsed.get("post_outline"),
    )
