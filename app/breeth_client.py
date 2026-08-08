import httpx
from typing import Any
from .config import settings


class BreethClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or settings.breeth_api_key
        self.base_url = base_url or settings.breeth_base_url.rstrip("/")
        self.available = bool(self.api_key)

    async def _request(self, method: str, path: str, json: Any | None = None) -> Any:
        if not self.available:
            raise RuntimeError("BREETH_API_KEY is not configured")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
            response = await client.request(method, url, json=json)
            response.raise_for_status()
            return response.json()

    async def record_episode(self, group_id: str, content: str, source_description: str = "pulse-ai-creator") -> dict:
        if not self.available:
            return {}
        body = {
            "group_id": group_id,
            "content": content,
            "source_description": source_description,
            "extract_intent": False,
        }
        return await self._request("POST", "/v1/episodes", json=body)

    async def search_topic(self, group_id: str, query: str, limit: int = 10) -> dict:
        if not self.available:
            return {"edges": []}
        body = {
            "group_id": group_id,
            "query": query,
            "limit": limit,
        }
        return await self._request("POST", "/v1/search", json=body)
