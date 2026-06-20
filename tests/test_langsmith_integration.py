import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any, Dict
from core.constants import calculate_token_cost, traceable, _set_run_metadata
from tools.gemini_client import GeminiClient
from tools.groq_client import GroqClient
from tools.deepseek_client import DeepSeekClient
from core.rag_pipeline import LegalRAGPipeline, LegalHybridRetriever


def test_calculate_token_cost() -> None:
    """Tests the token cost calculator with different models and fallback values."""
    # Gemini Flash pricing: $0.075 / 1M input, $0.30 / 1M output
    cost_gemini = calculate_token_cost("gemini", "gemini-2.0-flash", 1_000_000, 1_000_000)
    assert cost_gemini == pytest.approx(0.075 + 0.30)

    # Groq pricing: $0.05 / 1M input, $0.08 / 1M output
    cost_groq = calculate_token_cost("groq", "llama-3.1-8b-instant", 1_000_000, 1_000_000)
    assert cost_groq == pytest.approx(0.05 + 0.08)

    # DeepSeek pricing: $0.14 / 1M input, $0.28 / 1M output
    cost_deepseek = calculate_token_cost("deepseek", "deepseek-chat", 1_000_000, 1_000_000)
    assert cost_deepseek == pytest.approx(0.14 + 0.28)

    # OpenRouter default pricing: $0.15 / 1M input, $0.60 / 1M output
    cost_or = calculate_token_cost("openrouter", "some-random-model", 1_000_000, 1_000_000)
    assert cost_or == pytest.approx(0.15 + 0.60)


def test_traceable_fail_safe_no_import() -> None:
    """Verifies that the traceable decorator does not break function execution."""
    @traceable(name="Test Trace", run_type="chain")
    def dummy_func(x: int) -> int:
        return x + 1

    assert dummy_func(5) == 6


@pytest.mark.asyncio
async def test_gemini_client_token_metadata_tracking() -> None:
    """Tests that GeminiClient correctly extracts token usage and records metadata."""
    # Mock Google GenAI Client
    mock_genai_client = MagicMock()
    mock_generate_content = AsyncMock()
    mock_genai_client.aio.models.generate_content = mock_generate_content

    # Mock Gemini response with usage metadata
    mock_response = MagicMock()
    mock_usage = MagicMock()
    mock_usage.prompt_token_count = 100
    mock_usage.response_token_count = 200
    mock_usage.total_token_count = 300
    mock_response.usage_metadata = mock_usage
    mock_generate_content.return_value = mock_response

    with patch("google.genai.Client", return_value=mock_genai_client):
        # We pass an API key so constructor doesn't raise error
        client = GeminiClient(model_name="gemini-2.0-flash", api_key="fake-key")

        with patch("tools.gemini_client._set_run_metadata") as mock_set_metadata:
            res = await client.generate_content_async("Hello")
            assert res == mock_response
            # Check if metadata is recorded
            mock_set_metadata.assert_called_once()
            _, kwargs = mock_set_metadata.call_args
            assert kwargs["prompt_tokens"] == 100
            assert kwargs["completion_tokens"] == 200
            assert kwargs["total_tokens"] == 300
            assert kwargs["provider"] == "gemini"


@pytest.mark.asyncio
async def test_groq_client_token_metadata_tracking() -> None:
    """Tests that GroqClient correctly extracts token usage and records metadata."""
    # Mock httpx AsyncClient
    mock_http_response = MagicMock()
    mock_http_response.status_code = 200
    mock_http_response.json.return_value = {
        "choices": [{"message": {"content": "Groq Response"}}],
        "usage": {
            "prompt_tokens": 150,
            "completion_tokens": 50,
            "total_tokens": 200
        }
    }

    mock_client_instance = MagicMock()
    mock_client_instance.post = AsyncMock(return_value=mock_http_response)
    mock_client_instance.__aenter__.return_value = mock_client_instance

    with patch("httpx.AsyncClient", return_value=mock_client_instance):
        client = GroqClient(model_name="llama-3.1-8b-instant", api_key="fake-key")

        with patch("tools.groq_client._set_run_metadata") as mock_set_metadata:
            res = await client.generate_content_async("Hello")
            assert res.text == "Groq Response"
            assert res.usage["prompt_tokens"] == 150
            # Check if metadata is recorded
            mock_set_metadata.assert_called_once()
            _, kwargs = mock_set_metadata.call_args
            assert kwargs["prompt_tokens"] == 150
            assert kwargs["completion_tokens"] == 50
            assert kwargs["total_tokens"] == 200
            assert kwargs["provider"] == "groq"


@pytest.mark.asyncio
async def test_deepseek_client_token_metadata_tracking() -> None:
    """Tests that DeepSeekClient correctly extracts token usage and records metadata."""
    # Mock httpx AsyncClient
    mock_http_response = MagicMock()
    mock_http_response.status_code = 200
    mock_http_response.json.return_value = {
        "choices": [{"message": {"content": "DeepSeek Response"}}],
        "usage": {
            "prompt_tokens": 80,
            "completion_tokens": 40,
            "total_tokens": 120
        }
    }

    mock_client_instance = MagicMock()
    mock_client_instance.post = AsyncMock(return_value=mock_http_response)
    mock_client_instance.__aenter__.return_value = mock_client_instance

    with patch("httpx.AsyncClient", return_value=mock_client_instance):
        client = DeepSeekClient(model_name="deepseek-chat", api_key="fake-key")

        with patch("tools.deepseek_client._set_run_metadata") as mock_set_metadata:
            res = await client.generate_content_async("Hello")
            assert res.text == "DeepSeek Response"
            assert res.usage["prompt_tokens"] == 80
            # Check if metadata is recorded
            mock_set_metadata.assert_called_once()
            _, kwargs = mock_set_metadata.call_args
            assert kwargs["prompt_tokens"] == 80
            assert kwargs["completion_tokens"] == 40
            assert kwargs["total_tokens"] == 120
            assert kwargs["provider"] == "deepseek"


@pytest.mark.asyncio
async def test_pipeline_cache_hit_metadata() -> None:
    """Tests that LegalRAGPipeline sets cache_hit metadata on Cache Hit."""
    mock_retriever = MagicMock()
    # Mock embedding query
    mock_retriever.vector_retriever._embed_query = AsyncMock(return_value=[0.1, 0.2])

    # Mock Redis manager
    mock_redis = MagicMock()
    # Cache HIT: returns high-score node
    mock_redis.vector_search = AsyncMock(return_value=[{
        "id": "123",
        "score": 0.99,
        "text": "cached result",
        "metadata": {"so_ky_hieu": "123", "article_title": "Title", "article_uuid": "uuid-1"}
    }])

    # Mock retriever fallback search just in case
    mock_retriever.aretrieve_with_embedding = AsyncMock(return_value=[])

    pipeline = LegalRAGPipeline(
        retriever=mock_retriever,
        provider="gemini",
        llm=MagicMock(),
        redis_manager=mock_redis
    )

    with patch("core.rag_pipeline._set_run_metadata") as mock_set_metadata:
        # We disable LLM generation env so it returns immediately
        with patch.dict("os.environ", {"ENABLE_LLM_GENERATION": "false"}):
            res = await pipeline.acustom_query("question")
            assert res["status"] == "ready_for_llm"
            assert res["retrievals"][0]["source"] == "123 - Title"

            # Verify _set_run_metadata called with cache_hit=True and token_cost_usd=0.0
            mock_set_metadata.assert_any_call(cache_hit=True)
            mock_set_metadata.assert_any_call(token_cost_usd=0.0)
