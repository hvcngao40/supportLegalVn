import json
import sys
import types

import httpx
import pytest

from app import _required_secret_names
from core.classifier import LegalQueryClassifier
from tools.openrouter_client import DEFAULT_OPENROUTER_MODEL, OpenRouterClient
import tools.openrouter_client as openrouter_module


class _FakeResponse:
    def __init__(self, *, status_code: int = 200, payload=None, lines=None):
        self.status_code = status_code
        self._payload = payload or {}
        self._lines = lines or []
        self.request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")

    def raise_for_status(self):
        if self.status_code >= 400:
            response = httpx.Response(self.status_code, request=self.request, content=json.dumps(self._payload).encode("utf-8"))
            response.raise_for_status()

    def json(self):
        return self._payload

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeStreamContext:
    def __init__(self, response: _FakeResponse):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs
        self.post_calls = []
        self.stream_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json, headers):
        self.post_calls.append((url, json, headers))
        return _FakeResponse(payload={"choices": [{"message": {"content": "OK"}}]})

    def stream(self, method, url, json, headers):
        self.stream_calls.append((method, url, json, headers))
        response = _FakeResponse(
            payload={},
            lines=[
                'data: {"choices": [{"delta": {"content": "Xin chào"}}]}',
                "data: [DONE]",
            ],
        )
        return _FakeStreamContext(response)


@pytest.mark.asyncio
async def test_openrouter_client_uses_openai_compatible_payload_and_headers(monkeypatch):
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_APP_URL", "https://example.com")
    monkeypatch.setenv("OPENROUTER_APP_TITLE", "supportLegalVn")

    fake_client = _FakeAsyncClient()
    monkeypatch.setattr(openrouter_module.httpx, "AsyncClient", lambda timeout=None: fake_client)

    client = OpenRouterClient()
    result = await client.generate_content_async(
        "Xin chào",
        temperature=0.2,
        max_tokens=128,
        system_instruction="Bạn là trợ lý pháp luật.",
    )

    assert client.model_name == DEFAULT_OPENROUTER_MODEL
    assert result.text == "OK"
    assert fake_client.post_calls
    _, payload, headers = fake_client.post_calls[0]
    assert payload["model"] == DEFAULT_OPENROUTER_MODEL
    assert payload["stream"] is False
    assert payload["temperature"] == 0.2
    assert payload["max_tokens"] == 128
    assert payload["messages"][0] == {"role": "system", "content": "Bạn là trợ lý pháp luật."}
    assert payload["messages"][1] == {"role": "user", "content": "Xin chào"}
    assert headers["Authorization"] == "Bearer test-key"
    assert headers["HTTP-Referer"] == "https://example.com"
    assert headers["X-Title"] == "supportLegalVn"


@pytest.mark.asyncio
async def test_openrouter_streaming_uses_same_payload_shape(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    fake_client = _FakeAsyncClient()
    monkeypatch.setattr(openrouter_module.httpx, "AsyncClient", lambda timeout=None: fake_client)

    client = OpenRouterClient(model_name="openai/gpt-4o-mini")
    chunks = []
    async for chunk in client.astream_query("Xin chào"):
        chunks.append(chunk.text)

    assert chunks == ["Xin chào"]
    assert fake_client.stream_calls
    method, url, payload, headers = fake_client.stream_calls[0]
    assert method == "POST"
    assert url.endswith("/chat/completions")
    assert payload["model"] == "openai/gpt-4o-mini"
    assert payload["stream"] is True
    assert payload["messages"][1] == {"role": "user", "content": "Xin chào"}
    assert headers["Authorization"] == "Bearer test-key"


def test_classifier_factory_supports_openrouter(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    classifier = LegalQueryClassifier(provider="openrouter", model_name="openai/gpt-4o-mini")
    client = classifier._get_client("openrouter")

    assert isinstance(client, OpenRouterClient)
    assert client.model_name == "openai/gpt-4o-mini"


def test_rag_pipeline_factory_supports_openrouter(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    fake_qdrant_retriever = types.ModuleType("retrievers.qdrant_retriever")
    fake_qdrant_retriever.QdrantRetriever = object
    fake_sqlite_retriever = types.ModuleType("retrievers.sqlite_retriever")
    fake_sqlite_retriever.SQLiteFTS5Retriever = object
    fake_db_qdrant = types.ModuleType("db.qdrant")
    fake_db_qdrant.QdrantManager = object
    fake_sentence_transformers = types.ModuleType("sentence_transformers")
    fake_sentence_transformers.CrossEncoder = object

    monkeypatch.setitem(sys.modules, "retrievers.qdrant_retriever", fake_qdrant_retriever)
    monkeypatch.setitem(sys.modules, "retrievers.sqlite_retriever", fake_sqlite_retriever)
    monkeypatch.setitem(sys.modules, "db.qdrant", fake_db_qdrant)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_sentence_transformers)

    from core.rag_pipeline import LegalRAGPipeline

    pipeline = LegalRAGPipeline.__new__(LegalRAGPipeline)
    client = LegalRAGPipeline._get_client(pipeline, "openrouter", "openai/gpt-4o-mini")

    assert isinstance(client, OpenRouterClient)
    assert client.model_name == "openai/gpt-4o-mini"


def test_required_secret_names_include_openrouter(monkeypatch):
    monkeypatch.setenv("CLASSIFIER_PROVIDER", "openrouter")
    monkeypatch.setenv("CLASSIFIER_FALLBACK_PROVIDER", "gemini")
    monkeypatch.setenv("GENERATION_PROVIDER", "openrouter")

    assert "OPENROUTER_API_KEY" in _required_secret_names()


