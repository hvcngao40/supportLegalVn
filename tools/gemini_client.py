import os
import asyncio
import logging
from typing import Any, Optional, AsyncGenerator

from google import genai
from google.genai import errors
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception,
    before_sleep_log
)

from core.constants import traceable, _set_run_metadata

logger = logging.getLogger(__name__)


def is_retryable_error(exception: Exception) -> bool:
    """Kiểm tra xem lỗi có nằm trong nhóm cần retry không (Rate limit, Server error)."""
    if isinstance(exception, errors.APIError):
        # 429: Too Many Requests / Resource Exhausted
        # 500: Internal Server Error
        # 503: Service Unavailable
        if exception.code in (429, 500, 503):
            return True
    return False


class GeminiClient:
    """
    Centralized Gemini client with robust retry logic and error handling.
    Wraps the new Google GenAI SDK calls.
    """

    def __init__(self, model_name: str = "gemini-2.0-flash", api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY must be set in environment.")

        # SDK mới khởi tạo qua Client object thay vì configure global
        self.client = genai.Client(api_key=self.api_key)
        self.model_name = model_name

    @traceable(name="GeminiClient.generate_content_async", run_type="llm")
    @retry(
        # Sử dụng hàm check lỗi custom do SDK mới gộp chung vào APIError
        retry=retry_if_exception(is_retryable_error),
        wait=wait_exponential(multiplier=2, min=45, max=120),
        stop=stop_after_attempt(5),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True
    )
    async def generate_content_async(self, prompt: str, **kwargs: Any) -> Any:
        """
        Generates content with automatic retries on rate limits or server errors.
        """
        try:
            # SDK mới sử dụng client.aio.models cho các tác vụ bất đồng bộ
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt,
                **kwargs
            )
            try:
                if response and getattr(response, "usage_metadata", None):
                    prompt_tokens = response.usage_metadata.prompt_token_count or 0
                    completion_tokens = response.usage_metadata.response_token_count or 0
                    total_tokens = response.usage_metadata.total_token_count or 0

                    from core.constants import calculate_token_cost
                    cost = calculate_token_cost("gemini", self.model_name, prompt_tokens, completion_tokens)

                    _set_run_metadata(
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=total_tokens,
                        token_cost_usd=cost,
                        model=self.model_name,
                        provider="gemini"
                    )
            except Exception as e:
                logger.warning(f"Failed to record token usage for Gemini: {e}")

            return response
        except errors.APIError as e:
            if e.code == 429:
                logger.warning(f"Quota exceeded for {self.model_name}. Retrying...")
            raise e
        except Exception as e:
            logger.error(f"Unexpected Gemini error: {e}")
            raise e

    @traceable(name="GeminiClient.astream_query", run_type="llm")
    async def astream_query(self, prompt: str, **kwargs: Any) -> AsyncGenerator[Any, None]:
        """
        Streams content with basic error handling.
        Note: Retrying streams is complex; for now, we just handle the exception.
        """
        try:
            # Gọi hàm stream bất đồng bộ
            response = await self.client.aio.models.generate_content_stream(
                model=self.model_name,
                contents=prompt,
                **kwargs
            )
            last_usage = None
            async for chunk in response:
                if getattr(chunk, "usage_metadata", None):
                    last_usage = chunk.usage_metadata
                yield chunk

            if last_usage:
                try:
                    prompt_tokens = last_usage.prompt_token_count or 0
                    completion_tokens = last_usage.response_token_count or 0
                    total_tokens = last_usage.total_token_count or 0

                    from core.constants import calculate_token_cost
                    cost = calculate_token_cost("gemini", self.model_name, prompt_tokens, completion_tokens)

                    _set_run_metadata(
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=total_tokens,
                        token_cost_usd=cost,
                        model=self.model_name,
                        provider="gemini"
                    )
                except Exception as e:
                    logger.warning(f"Failed to record streaming token usage for Gemini: {e}")
        except errors.APIError as e:
            if e.code == 429:
                logger.error("Quota exceeded during streaming.")
            raise e
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            raise e