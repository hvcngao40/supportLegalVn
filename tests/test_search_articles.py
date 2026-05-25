from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock
import pytest

from app import app


@pytest.fixture(autouse=True)
def mock_pipeline():
    # Replace the app.state.pipeline with a mock that has retriever and fts_retriever
    mock = MagicMock()
    mock.retriever = MagicMock()
    mock.retriever.aretrieve = AsyncMock()
    mock.retriever.fts_retriever = MagicMock()
    mock.retriever.fts_retriever.get_articles_by_uuids = AsyncMock()
    mock.retriever.fts_retriever.aretrieve_articles_by_so_ky_hieu = AsyncMock()
    app.state.pipeline = mock
    return mock


def test_search_by_query_returns_results(mock_pipeline):
    node = {
        "id": "uuid-1",
        "text": "Nội dung điều 1 về trộm cắp tài sản",
        "metadata": {
            "article_uuid": "uuid-1",
            "article_title": "Điều 1",
            "so_ky_hieu": "123/2024/NĐ-CP",
        },
        "score": 0.9,
    }
    mock_pipeline.retriever.fts_retriever.aretrieve_articles_by_so_ky_hieu.return_value = [node]
    mock_pipeline.retriever.fts_retriever.get_articles_by_uuids.return_value = [node]

    client = TestClient(app)
    resp = client.post("/api/v1/search-articles", json={"query": "trộm cắp", "top_k": 5})
    assert resp.status_code == 200
    j = resp.json()
    assert j["top_results_count"] == 1
    result = j["results"][0]
    assert result["article_uuid"] == "uuid-1"
    assert "full_content" in result
    
    # Assert highlighting worked
    assert "<b>trộm cắp</b>" in result["highlighted_content"].lower()
    
    # Assert doc_type mapping worked based on so_ky_hieu
    assert result["doc_type"] == "Nghị định"

def test_search_with_explicit_doc_type(mock_pipeline):
    node = {
        "id": "uuid-3",
        "text": "Nội dung",
        "metadata": {"article_uuid": "uuid-3", "so_ky_hieu": "123/Luật"},
        "score": 0.8,
    }
    mock_pipeline.retriever.fts_retriever.aretrieve_articles_by_so_ky_hieu.return_value = [node]
    mock_pipeline.retriever.fts_retriever.get_articles_by_uuids.return_value = [node]

    client = TestClient(app)
    resp = client.post("/api/v1/search-articles", json={"query": "nội dung", "doc_type": "Luật"})
    assert resp.status_code == 200
    j = resp.json()
    assert j["results"][0]["doc_type"] == "Luật"



def test_search_by_uuid_fetches_article(mock_pipeline):
    node = {
        "id": "uuid-2",
        "text": "Nội dung điều 2",
        "metadata": {
            "article_uuid": "uuid-2",
            "article_title": "Điều 2",
            "so_ky_hieu": "Văn bản B",
        },
        "score": 1.0,
    }
    mock_pipeline.retriever.fts_retriever.get_articles_by_uuids.return_value = [node]

    client = TestClient(app)
    resp = client.post("/api/v1/search-articles", json={"article_uuid": "uuid-2"})
    assert resp.status_code == 200
    j = resp.json()
    assert j["top_results_count"] == 1
    assert j["results"][0]["article_uuid"] == "uuid-2"


def test_validation_error_when_no_query_or_uuid():
    client = TestClient(app)
    resp = client.post("/api/v1/search-articles", json={})
    assert resp.status_code == 400


def test_internal_exception_returns_500(mock_pipeline):
    mock_pipeline.retriever.fts_retriever.aretrieve_articles_by_so_ky_hieu.side_effect = Exception("boom")
    client = TestClient(app)
    resp = client.post("/api/v1/search-articles", json={"query": "x"})
    assert resp.status_code == 500

