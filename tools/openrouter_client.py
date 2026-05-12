import json
import logging
import os
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, Optional, cast

import httpx
from tenacity import before_sleep_log, retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from tools.llm_client_base import BaseLLMClient

logger = logging.getLogger(__name__)

DEFAULT_OPENROUTER_MODEL = "openai/gpt-4o-mini"
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass
class ProviderResponse:
    text: str


class OpenRouterClient(BaseLLMClient):
    """OpenRouter chat client using the OpenAI-compatible chat completions API."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY must be set in environment.")

        self.model_name = model_name or os.getenv("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL)
        self.base_url = (base_url or os.getenv("OPENROUTER_BASE_URL", DEFAULT_OPENROUTER_BASE_URL)).rstrip("/")
        self.timeout = httpx.Timeout(float(os.getenv("CLASSIFIER_PROVIDER_TIMEOUT", "20")), connect=5.0)
        self.app_url = os.getenv("OPENROUTER_APP_URL", "").strip()
        self.app_title = os.getenv("OPENROUTER_APP_TITLE", "").strip()

    def _build_headers(self) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.app_url:
            headers["HTTP-Referer"] = self.app_url
        if self.app_title:
            headers["X-Title"] = self.app_title
        return headers

    def _build_payload(self, prompt: str, *, stream: bool, **kwargs: Any) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": kwargs.get("system_instruction") or "Bạn là một chuyên gia pháp luật Việt Nam."},
                {"role": "user", "content": prompt},
            ],
            "temperature": kwargs.get("temperature", 0.0),
            "stream": stream,
        }

        for key in ("max_tokens", "top_p", "stop", "presence_penalty", "frequency_penalty"):
            value = kwargs.get(key)
            if value is not None:
                payload[key] = value

        return payload

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError)),
        wait=wait_exponential(multiplier=1, min=1, max=6),
        stop=stop_after_attempt(3),
        before_sleep=before_sleep_log(cast(Any, logger), logging.WARNING),
        reraise=True,
    )
    async def generate_content_async(self, prompt: str, **kwargs: Any) -> ProviderResponse:
        payload = self._build_payload(prompt, stream=False, **kwargs)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=self._build_headers())
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        return ProviderResponse(text=str(content).strip())

    async def astream_query(self, prompt: str, **kwargs: Any) -> AsyncGenerator[ProviderResponse, None]:
        payload = self._build_payload(prompt, stream=True, **kwargs)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=self._build_headers(),
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip() or not line.startswith("data: "):
                        continue

                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break

                    try:
                        data = json.loads(data_str)
                        content = data["choices"][0]["delta"].get("content", "")
                        if content:
                            yield ProviderResponse(text=str(content))
                    except json.JSONDecodeError:
                        logger.warning("Failed to decode OpenRouter SSE chunk: %s", line)
                        continue

