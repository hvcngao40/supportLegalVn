import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock
import base64
import json
from app import app

client = TestClient(app)

@pytest.fixture
def mock_pipeline():
    mock = MagicMock()
    mock.acustom_query = AsyncMock(return_value={
        "answer": "Test Answer",
        "citations": [{"source": "Doc 1", "text": "Snippet", "score": 0.9}],
        "detected_domains": ["Civil"],
        "confidence_score": 0.95
    })
    
    async def mock_stream(query):
        yield "Token1 "
        yield "Token2"
        
    mock.astream_query = mock_stream
    return mock

def test_health():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"ok", "degraded"}
    assert payload["service"] == "legal-api"

def test_ask(mock_pipeline):
    # Mock the app state
    app.state.pipeline = mock_pipeline
    
    response = client.post("/api/v1/ask", json={"query": "test query"})
    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "Test Answer"
    assert len(data["citations"]) == 1


def test_ask_ready_for_llm_response():
    mock_pipeline = MagicMock()
    mock_pipeline.acustom_query = AsyncMock(return_value={
        "status": "ready_for_llm",
        "prompt": "PROMPT_TEXT",
        "retrievals": [
            {"source": "Doc 1", "text": "Snippet", "score": 0.9, "article_uuid": "uuid-1"}
        ],
        "metadata": {"cache_hit": False, "used_cache_threshold": 0.95},
    })
    app.state.pipeline = mock_pipeline

    response = client.post("/api/v1/ask", json={"query": "test query"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready_for_llm"
    assert data["prompt"] == "PROMPT_TEXT"
    assert len(data["retrievals"]) == 1
    assert data["metadata"]["cache_hit"] is False
    assert "answer" not in data

def test_stream(mock_pipeline):
    app.state.pipeline = mock_pipeline
    
    with client.stream("POST", "/api/v1/stream", json={"query": "test query"}) as response:
        assert response.status_code == 200
        # SSE responses are text/event-stream
        lines = [line.decode("utf-8") if isinstance(line, bytes) else line for line in response.iter_lines() if line]
        assert len(lines) >= 2
        # Check first frame (event + data)
        assert "event: message" in lines[0]
        assert "data:" in lines[1]
        assert "Token1" in lines[1]


def test_stream_get_chat_history_uses_chatmessage_shape(mock_pipeline):
    captured = {}

    async def mock_stream(query, chat_history=None):
        captured["query"] = query
        captured["chat_history"] = chat_history
        yield {"type": "token", "content": "ok"}

    mock_pipeline.astream_query = mock_stream
    app.state.pipeline = mock_pipeline

    encoded_history = base64.b64encode(
        json.dumps([
            {"role": "user", "content": "Xin chao"},
            {"role": "assistant", "content": "Chao ban"}
        ]).encode("utf-8")
    ).decode("utf-8")

    with client.stream("GET", "/api/v1/stream", params={"query": "test query", "chat_history": encoded_history}) as response:
        assert response.status_code == 200
        lines = [line.decode("utf-8") if isinstance(line, bytes) else line for line in response.iter_lines() if line]
        assert any("data:" in line for line in lines)

    history = captured["chat_history"]
    assert history is not None
    assert len(history) == 2
    assert history[0].role == "user"
    assert history[0].content == "Xin chao"

