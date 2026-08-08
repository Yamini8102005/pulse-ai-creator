import asyncio
import httpx
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import List
from .models import Topic


HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"
ARXIV_API_URL = "http://export.arxiv.org/api/query"


def _parse_iso8601(timestamp: str) -> datetime:
    if timestamp.endswith("Z"):
        timestamp = timestamp[:-1] + "+00:00"
    return datetime.fromisoformat(timestamp).astimezone(timezone.utc)


async def fetch_hacker_news_topics() -> List[Topic]:
    query = "AI OR artificial intelligence OR machine learning OR llm OR rag OR open-source"
    params = {
        "query": query,
        "tags": "story",
        "hitsPerPage": 20,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(HN_SEARCH_URL, params=params)
        response.raise_for_status()
        payload = response.json()

    topics: List[Topic] = []
    for hit in payload.get("hits", []):
        title = hit.get("title") or hit.get("story_title")
        url = hit.get("url") or hit.get("story_url")
        created_at = hit.get("created_at")
        if not title or not url or not created_at:
            continue
        try:
            topic = Topic(
                title=title.strip(),
                summary=hit.get("comment_text", "").strip() or title.strip(),
                url=url,
                publishedAt=_parse_iso8601(created_at),
                source="Hacker News",
            )
            topics.append(topic)
        except Exception:
            continue

    return topics


async def fetch_arxiv_topics() -> List[Topic]:
    query = "all:AI+OR+all:LLM+OR+all:\"machine+learning\"+OR+all:\"retrieval+augmented\""
    params = {
        "search_query": query,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": 10,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(ARXIV_API_URL, params=params)
        response.raise_for_status()
        document = ET.fromstring(response.text)

    topics: List[Topic] = []
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in document.findall("atom:entry", ns):
        title = entry.findtext("atom:title", default="", namespaces=ns).strip()
        summary = entry.findtext("atom:summary", default="", namespaces=ns).strip()
        url = entry.findtext("atom:id", default="", namespaces=ns)
        published = entry.findtext("atom:published", default="", namespaces=ns)
        if not title or not url or not published:
            continue
        topics.append(
            Topic(
                title=title,
                summary=summary or title,
                url=url,
                publishedAt=_parse_iso8601(published),
                source="arXiv",
            )
        )
    return topics


async def discover_topics() -> List[Topic]:
    tasks = [fetch_hacker_news_topics(), fetch_arxiv_topics()]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    topics: List[Topic] = []
    for result in results:
        if isinstance(result, Exception):
            continue
        topics.extend(result)
    topics.sort(key=lambda item: item.publishedAt, reverse=True)
    return topics
