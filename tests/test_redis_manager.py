"""
Unit tests for RedisManager - db/redis.py

Tests vector insertion, retrieval, and session management.
"""

import os
import pytest
import numpy as np
from db.redis import RedisManager

pytestmark = pytest.mark.asyncio


class TestRedisManagerBasic:
    """Test basic RedisManager functionality."""

    async def test_connect_and_session_roundtrip(self):
        """Test basic session append/get roundtrip."""
        url = os.getenv("REDIS_URL", "redis://localhost:6379")
        mgr = RedisManager(url)
        try:
            await mgr.init()
            
            # Test session roundtrip
            await mgr.append_session("test-session", {"role": "user", "content": "hello"})
            history = await mgr.get_session("test-session")
            
            assert isinstance(history, list)
            assert len(history) > 0
            assert any(m.get("content") == "hello" for m in history)
        finally:
            await mgr.close()

    async def test_set_and_get(self):
        """Test basic set/get operations."""
        url = os.getenv("REDIS_URL", "redis://localhost:6379")
        mgr = RedisManager(url)
        try:
            await mgr.init()
            
            await mgr.set("test_key", "test_value", ex=3600)
            value = await mgr.get("test_key")
            
            assert value == "test_value"
            
            # Clean up
            await mgr.delete("test_key")
        finally:
            await mgr.close()

    async def test_exists(self):
        """Test key existence check."""
        url = os.getenv("REDIS_URL", "redis://localhost:6379")
        mgr = RedisManager(url)
        try:
            await mgr.init()
            
            await mgr.set("exists_key", "value")
            exists = await mgr.exists("exists_key")
            
            assert exists is True
            
            not_exists = await mgr.exists("nonexistent_key")
            assert not_exists is False
            
            # Clean up
            await mgr.delete("exists_key")
        finally:
            await mgr.close()


class TestRedisManagerVectorOperations:
    """Test vector storage and search operations."""

    async def test_new_document_storage(self):
        """Test storing a document with embedding."""
        url = os.getenv("REDIS_URL", "redis://localhost:6379")
        mgr = RedisManager(url)
        try:
            await mgr.init()
            
            embedding = np.random.rand(384).tolist()  # Random 384-dim vector
            
            doc_key = await mgr.new_document(
                doc_id="test_doc_1",
                embedding=embedding,
                snippet="Test snippet content",
                score=0.92,
                source="Test Source - Article 1",
                metadata={"category": "labor_law"}
            )
            
            assert doc_key.startswith("doc:")
            assert await mgr.exists(doc_key)
        finally:
            await mgr.close()

    async def test_vector_search_empty_index(self):
        """Test vector search on empty or new index."""
        url = os.getenv("REDIS_URL", "redis://localhost:6379")
        mgr = RedisManager(url)
        try:
            await mgr.init()
            
            embedding = np.random.rand(384).tolist()
            
            # Search should return empty list or list of results
            results = await mgr.vector_search(
                "documents_idx_test",
                embedding,
                k=5,
                threshold=0.95
            )
            
            assert isinstance(results, list)
        finally:
            await mgr.close()

    async def test_save_cached_retrieval(self):
        """Test saving retrieval results to cache."""
        url = os.getenv("REDIS_URL", "redis://localhost:6379")
        mgr = RedisManager(url)
        try:
            await mgr.init()
            
            query_embedding = np.random.rand(384).tolist()
            retrievals = [
                {
                    "doc_id": "art_1",
                    "snippet": "Điều 1: Về lao động",
                    "score": 0.92
                },
                {
                    "doc_id": "art_2",
                    "snippet": "Điều 2: Về bảo hiểm",
                    "score": 0.88
                }
            ]
            
            cache_key = await mgr.save_cached_retrieval(
                query_embedding,
                retrievals,
                session_id="test_session"
            )
            
            assert cache_key.startswith("cache:retrieval:")
            assert await mgr.exists(cache_key)
        finally:
            await mgr.close()


class TestRedisManagerSessionManagement:
    """Test session history management."""

    async def test_multiple_session_append(self):
        """Test creating a session with multiple messages."""
        url = os.getenv("REDIS_URL", "redis://localhost:6379")
        mgr = RedisManager(url)
        try:
            await mgr.init()
            
            session_id = "session_test_multi"
            
            message1 = {"role": "user", "content": "Hỏi về luật nhân sự"}
            message2 = {"role": "assistant", "content": "Luật nhân sự quy định..."}
            
            await mgr.append_session(session_id, message1)
            await mgr.append_session(session_id, message2)
            
            history = await mgr.get_session(session_id)
            assert len(history) >= 2
            assert message1 in history or any(m.get("content") == message1["content"] for m in history)
        finally:
            await mgr.close()

    async def test_session_persistence(self):
        """Test that session data persists across retrievals."""
        url = os.getenv("REDIS_URL", "redis://localhost:6379")
        mgr = RedisManager(url)
        try:
            await mgr.init()
            
            session_id = "session_persist_multi"
            
            message = {"role": "user", "content": "Test persistence message"}
            await mgr.append_session(session_id, message)
            
            # Retrieve multiple times
            history1 = await mgr.get_session(session_id)
            history2 = await mgr.get_session(session_id)
            
            assert len(history1) == len(history2)
        finally:
            await mgr.close()

    async def test_empty_session(self):
        """Test retrieving a non-existent session."""
        url = os.getenv("REDIS_URL", "redis://localhost:6379")
        mgr = RedisManager(url)
        try:
            await mgr.init()
            
            session_id = "nonexistent_session_empty"
            history = await mgr.get_session(session_id)
            assert history == []
        finally:
            await mgr.close()


class TestRedisManagerErrorHandling:
    """Test error handling in RedisManager."""

    async def test_operations_without_init(self):
        """Test that operations fail gracefully without initialization."""
        url = os.getenv("REDIS_URL", "redis://localhost:6379")
        mgr = RedisManager(url)
        
        embedding = np.random.rand(384).tolist()
        
        # Operations should raise RuntimeError without init
        with pytest.raises(RuntimeError):
            await mgr.vector_search("test_index", embedding)
        
        with pytest.raises(RuntimeError):
            await mgr.new_document("doc_1", embedding, "snippet")

    async def test_invalid_redis_url(self):
        """Test handling of invalid Redis URL."""
        mgr = RedisManager("redis://invalid-host:9999")
        
        # Should raise exception on init
        with pytest.raises(Exception):
            await mgr.init()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
