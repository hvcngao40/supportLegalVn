import os
import json
import httpx
import logging
from typing import Any, Optional, Dict, AsyncGenerator, cast
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)

from tools.llm_client_base import BaseLLMClient
from core.constants import traceable, _set_run_metadata

logger = logging.getLogger(__name__)

DEFAULT_GROQ_MODEL = "llama-3.1-8b-instant"


class GroqResponse:
    """Mock response object to match GeminiClient/DeepSeekClient interface."""

    def __init__(self, text: str, usage: Optional[Dict[str, Any]] = None):
        self.text = text
        self.usage = usage


class GroqClient(BaseLLMClient):
    """
    Groq API client with OpenAI compatibility.
    Provides extreme low-latency async content generation for the legal classifier.
    """

    def __init__(self, model_name: str = DEFAULT_GROQ_MODEL, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY must be set in environment.")

        self.model_name = model_name
        self.timeout = httpx.Timeout(15.0, connect=5.0)  # Increased timeout slightly

    def _build_payload(self, prompt: str, *, stream: bool, **kwargs: Any) -> Dict[str, Any]:
        system_content = kwargs.get("system_instruction") or "Bạn là một chuyên gia pháp luật Việt Nam."

        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt},
            ],
            "temperature": kwargs.get("temperature", 0.0),
            "stream": stream,
        }

        if stream:
            payload["stream_options"] = {"include_usage": True}

        for key in ("max_tokens", "top_p", "stop", "presence_penalty", "frequency_penalty"):
            value = kwargs.get(key)
            if value is not None:
                payload[key] = value

        return payload

    async def _raise_for_status_with_body(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return

        body = ""
        try:
            body = (await response.aread()).decode("utf-8", errors="replace")
        except Exception:
            body = response.text

        logger.error(
            "Groq API request failed (%s %s): %s",
            response.status_code,
            response.request.url,
            body.strip() or "<empty response body>",
        )
        response.raise_for_status()

    @traceable(name="GroqClient.generate_content_async", run_type="llm")
    @retry(
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        stop=stop_after_attempt(3),
        before_sleep=before_sleep_log(cast(Any, logger), logging.WARNING),
        reraise=True
    )
    async def generate_content_async(self, prompt: str, **kwargs: Any) -> Any:
        """
        Generates content using Groq Chat Completions API.
        Returns a GroqResponse object with a .text attribute.
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = self._build_payload(prompt, stream=False, **kwargs)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers)
            await self._raise_for_status_with_body(response)

            data = response.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage")

            try:
                if usage:
                    prompt_tokens = usage.get("prompt_tokens") or 0
                    completion_tokens = usage.get("completion_tokens") or 0
                    total_tokens = usage.get("total_tokens") or 0

                    from core.constants import calculate_token_cost
                    cost = calculate_token_cost("groq", self.model_name, prompt_tokens, completion_tokens)

                    _set_run_metadata(
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=total_tokens,
                        token_cost_usd=cost,
                        model=self.model_name,
                        provider="groq"
                    )
            except Exception as e:
                logger.warning(f"Failed to record token usage for Groq: {e}")

            return GroqResponse(text=content, usage=usage)

    @traceable(name="GroqClient.astream_query", run_type="llm")
    async def astream_query(self, prompt: str, **kwargs: Any) -> AsyncGenerator[Any, None]:
        """
        Streams content using Groq Chat Completions API with SSE.
        Yields GroqResponse-like objects with a .text attribute.
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = self._build_payload(prompt, stream=True, **kwargs)
        last_usage = None

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", "https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers) as response:
                await self._raise_for_status_with_body(response)

                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break

                        try:
                            data = json.loads(data_str)
                            usage = data.get("usage")
                            if usage:
                                last_usage = usage

                            content = ""
                            if data.get("choices") and len(data["choices"]) > 0:
                                content = data["choices"][0]["delta"].get("content", "")

                            if content or usage:
                                yield GroqResponse(text=content, usage=usage)
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to decode Groq SSE chunk: {line}")
                            continue

            if last_usage:
                try:
                    prompt_tokens = last_usage.get("prompt_tokens") or 0
                    completion_tokens = last_usage.get("completion_tokens") or 0
                    total_tokens = last_usage.get("total_tokens") or 0

                    from core.constants import calculate_token_cost
                    cost = calculate_token_cost("groq", self.model_name, prompt_tokens, completion_tokens)

                    _set_run_metadata(
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=total_tokens,
                        token_cost_usd=cost,
                        model=self.model_name,
                        provider="groq"
                    )
                except Exception as e:
                    logger.warning(f"Failed to record streaming token usage for Groq: {e}")
