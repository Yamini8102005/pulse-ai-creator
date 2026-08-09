import httpx
import os
from typing import Any
from .config import settings


class LLMClientError(RuntimeError):
    def __init__(self, message: str, category: str | None = None, status_code: int | None = None, response: Any | None = None):
        super().__init__(message)
        self.category = category
        self.status_code = status_code
        self.response = response


class LLMClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        provider: str | None = None,
    ):
        self.provider = (provider or os.getenv("LLM_PROVIDER") or settings.llm_provider or "gemini").lower().strip()
        if self.provider == "gemini":
            self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("LLM_API_KEY") or settings.gemini_api_key or settings.llm_api_key
            self.base_url = (
                base_url
                or os.getenv("GEMINI_API_BASE")
                or os.getenv("LLM_API_BASE")
                or settings.gemini_api_base
                or settings.llm_api_base
            ).rstrip("/")
            self.model = model or os.getenv("GEMINI_MODEL") or os.getenv("LLM_MODEL") or settings.gemini_model or settings.llm_model
        elif self.provider == "openai":
            self.api_key = api_key or os.getenv("LLM_API_KEY") or settings.llm_api_key or settings.openai_api_key
            self.base_url = (
                base_url
                or os.getenv("LLM_API_BASE")
                or settings.llm_api_base
                or settings.openai_api_base
            ).rstrip("/")
            self.model = model or os.getenv("LLM_MODEL") or settings.llm_model or settings.openai_model
        elif self.provider == "ollama":
            self.api_key = api_key or os.getenv("LLM_API_KEY") or settings.llm_api_key
            self.base_url = (base_url or os.getenv("LLM_API_BASE") or settings.llm_api_base).rstrip("/")
            self.model = model or os.getenv("LLM_MODEL") or settings.llm_model
        else:
            raise RuntimeError(f"Unsupported LLM_PROVIDER: {self.provider}")

        if not self.base_url:
            raise RuntimeError("LLM_API_BASE is not configured for the selected provider")

    def _ensure_api_key(self) -> None:
        if self.provider in ("openai", "gemini") and not self.api_key:
            raise LLMClientError(
                "LLM_API_KEY or GEMINI_API_KEY is required for openai/gemini providers",
                category="configuration_error",
            )

    @staticmethod
    def _extract_text(content: Any) -> str:
        def _raw(val: Any) -> str:
            if isinstance(val, str):
                return val

            if isinstance(val, dict):
                # Support Gemini response structure (parts list)
                if "parts" in val and isinstance(val["parts"], list):
                    texts = []
                    for part in val["parts"]:
                        if isinstance(part, dict):
                            if "text" in part:
                                texts.append(str(part["text"]))
                            elif "content" in part:
                                try:
                                    texts.append(_raw(part["content"]))
                                except LLMClientError:
                                    pass
                        elif isinstance(part, str):
                            texts.append(part)
                    if texts:
                        return "".join(texts)

                # Support direct text field
                if "text" in val:
                    return str(val["text"])

                # Support nested content field
                if "content" in val:
                    return _raw(val["content"])

            if isinstance(val, list):
                return "".join(_raw(item) for item in val)

            raise LLMClientError(
                "Unable to extract text from Gemini content",
                category="api_error",
                response=val,
            )

        res = _raw(content)
        # Clean markdown code blocks if the final string is wrapped in them
        res_stripped = res.strip()
        if res_stripped.startswith("```"):
            lines = res_stripped.splitlines()
            if lines and lines[0].strip().startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            res = "\n".join(lines).strip()
        return res

    def _categorize_error(self, status_code: int, body: Any) -> str:
        error_code = None
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict):
                error_code = error.get("code")
            else:
                error_code = body.get("code")

        if status_code == 429:
            if error_code in ("credit_balance_exhausted", "insufficient_quota"):
                return "quota_exhausted"
            return "rate_limited"
        if status_code in (402, 403):
            if error_code in ("credit_balance_exhausted", "insufficient_quota"):
                return "quota_exhausted"
            return "permission_denied"
        if status_code >= 500:
            return "temporary_server_error"
        return "api_error"

    async def chat(self, messages: list[dict[str, str]], temperature: float = 0.2) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 4096,
        }

        headers = {
            "Content-Type": "application/json",
        }
        # For Gemini/Generative Language API we send the API key as a query param (key=...) rather than a Bearer token
        use_key_param = self.provider == "gemini" and bool(self.api_key)

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                if self.provider == "openai":
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                elif self.provider == "gemini":
                    # Generative Language API uses a models:generateContent endpoint.
                    gemini_payload = {
                        "model": f"models/{self.model}",
                        "contents": [
                            {
                                "role": "model" if msg.get("role", "user").lower() == "assistant" else msg.get("role", "user"),
                                "parts": [{"text": msg["content"]}],
                            }
                            for msg in messages
                        ],
                        "generationConfig": {
                            "temperature": temperature,
                            "maxOutputTokens": 4096,
                            "thinkingConfig": {
                                "thinkingBudget": 0
                            }
                        },
                    }
                    url = f"{self.base_url}/models/{self.model}:generateContent"
                    if use_key_param:
                        response = await client.post(url, headers=headers, params={"key": self.api_key}, json=gemini_payload)
                    else:
                        auth_headers = {**headers}
                        if self.api_key:
                            auth_headers["Authorization"] = f"Bearer {self.api_key}"
                        response = await client.post(url, headers=auth_headers, json=gemini_payload)
                else:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                body: Any = {}
                try:
                    body = exc.response.json()
                except Exception:
                    body = exc.response.text
                category = self._categorize_error(exc.response.status_code, body)
                raise LLMClientError(
                    f"LLM request failed with status {exc.response.status_code}: {body}",
                    category=category,
                    status_code=exc.response.status_code,
                    response=body,
                ) from exc
            except httpx.RequestError as exc:
                raise LLMClientError("LLM request failed due to network error", category="network_error") from exc

            body = response.json()
            if self.provider == "gemini":
                return self._parse_gemini_response(body)

            choices = body.get("choices")
            if not choices or not isinstance(choices, list):
                raise LLMClientError("LLM response missing choices", category="api_error", response=body)
            message = choices[0].get("message")
            if not message or not isinstance(message, dict):
                raise LLMClientError("LLM response missing message payload", category="api_error", response=body)
            content = message.get("content")
            if content is None:
                raise LLMClientError("LLM response missing message content", category="api_error", response=body)
            return content

    @staticmethod
    def _parse_gemini_response(body: Any) -> str:
        if not isinstance(body, dict):
            raise LLMClientError("Gemini response is not a JSON object", category="api_error", response=body)
        candidates = body.get("candidates")
        if not candidates or not isinstance(candidates, list):
            raise LLMClientError("Gemini response missing candidates", category="api_error", response=body)
        candidate = candidates[0]
        if not isinstance(candidate, dict):
            raise LLMClientError("Gemini candidate is invalid", category="api_error", response=body)
        content = candidate.get("content") or candidate.get("message", {}).get("content")
        if content is None:
            raise LLMClientError("Gemini response candidate missing content", category="api_error", response=body)
        return LLMClient._extract_text(content)


    @staticmethod
    def _render_prompt(messages: list[dict[str, str]]) -> str:
        rendered = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            rendered.append(f"{role}: {content}")
        return "\n".join(rendered)
