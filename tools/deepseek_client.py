import os
import httpx
import logging
from typing import Any, Optional, Dict
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


class DeepSeekResponse:
    """Mock response object to match GeminiClient interface."""

    def __init__(self, text: str, usage: Optional[Dict[str, Any]] = None):
        self.text = text
        self.usage = usage


class DeepSeekClient(BaseLLMClient):
    """
    DeepSeek API client with OpenAI compatibility.
    Provides async content generation for the legal classifier.
    """

    def __init__(self, model_name: str = "deepseek-chat", api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY must be set in environment.")

        self.model_name = model_name
        self.base_url = "https://api.deepseek.com"
        self.timeout = httpx.Timeout(20.0, connect=5.0)

    @traceable(name="DeepSeekClient.generate_content_async", run_type="llm")
    @retry(
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException, httpx.HTTPStatusError)),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True
    )
    async def generate_content_async(self, prompt: str, **kwargs: Any) -> Any:
        """
        Generates content using DeepSeek Chat Completions API.
        Returns a DeepSeekResponse object with a .text attribute.
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # Merge system prompt if provided in kwargs or use default
        system_content = kwargs.get("system_instruction", "You are a helpful assistant.")

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt}
            ],
            "stream": False,
            "response_format": {"type": "json_object"} if kwargs.get("json_mode") else None
        }

        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.post("/chat/completions", json=payload, headers=headers)
            response.raise_for_status()

            data = response.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage")

            try:
                if usage:
                    prompt_tokens = usage.get("prompt_tokens") or 0
                    completion_tokens = usage.get("completion_tokens") or 0
                    total_tokens = usage.get("total_tokens") or 0

                    from core.constants import calculate_token_cost
                    cost = calculate_token_cost("deepseek", self.model_name, prompt_tokens, completion_tokens)

                    _set_run_metadata(
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=total_tokens,
                        token_cost_usd=cost,
                        model=self.model_name,
                        provider="deepseek"
                    )
            except Exception as e:
                logger.warning(f"Failed to record token usage for DeepSeek: {e}")

            return DeepSeekResponse(text=content, usage=usage)
