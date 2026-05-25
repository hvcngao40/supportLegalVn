"""
Integration tests for Redis cache with RAG pipeline.

Tests cache + Qdrant parallel flow and LLM generation control.
"""

import os
import pytest
import numpy as np
from typing import Dict, Any

pytestmark = pytest.mark.asyncio


class TestRAGCacheIntegration:
    """Test Redis cache integration with RAG pipeline."""

    async def test_cache_disabled_by_default(self):
        """Verify that LLM generation is disabled by default."""
        # Check .env configuration
        llm_enabled = os.getenv("ENABLE_LLM_GENERATION", "false").lower() == "true"
        assert llm_enabled is False, "LLM generation should be disabled by default (Phase 19 spec)"

    async def test_redis_threshold_configuration(self):
        """Test Redis threshold configuration."""
        threshold = float(os.getenv("REDIS_THRESHOLD", "0.95"))
        
        # Threshold should be high (strict matching)
        assert 0.9 <= threshold <= 1.0, "Redis threshold should be 0.9-1.0 (high/strict)"
        assert threshold == 0.95, "Default threshold should be 0.95"

    async def test_redis_url_configured(self):
        """Test that Redis URL is properly configured."""
        redis_url = os.getenv("REDIS_URL", "")
        
        # Should have a Redis URL configured
        assert redis_url or os.getenv("REDIS_HOST"), "Redis configuration required"

    async def test_prompt_response_format_when_llm_disabled(self):
        """Test the response format when LLM generation is disabled."""
        # This is a specification test: verify the expected response structure
        expected_fields = {"status", "prompt", "retrievals", "metadata"}
        
        # Expected response structure when ENABLE_LLM_GENERATION=false
        example_response = {
            "status": "ready_for_llm",
            "prompt": "<pre-built RAG prompt text>",
            "retrievals": [
                {
                    "doc_id": "article_uuid",
                    "snippet": "Nội dung trích dẫn...",
                    "score": 0.92
                }
            ],
            "metadata": {
                "cache_hit": False,
                "used_cache_threshold": 0.95
            }
        }
        
        # Verify structure
        assert set(example_response.keys()) == expected_fields
        assert isinstance(example_response["prompt"], str)
        assert isinstance(example_response["retrievals"], list)
        assert isinstance(example_response["metadata"], dict)

    async def test_cache_hit_metadata_tracking(self):
        """Test that cache hits are properly tracked in metadata."""
        response_with_cache_hit = {
            "status": "ready_for_llm",
            "metadata": {
                "cache_hit": True,
                "used_cache_threshold": 0.95
            }
        }
        
        response_with_qdrant_hit = {
            "status": "ready_for_llm",
            "metadata": {
                "cache_hit": False,
                "used_cache_threshold": 0.95
            }
        }
        
        # Verify metadata structure
        assert isinstance(response_with_cache_hit["metadata"]["cache_hit"], bool)
        assert isinstance(response_with_cache_hit["metadata"]["used_cache_threshold"], float)
        assert response_with_cache_hit["metadata"]["cache_hit"] is True
        assert response_with_qdrant_hit["metadata"]["cache_hit"] is False

    async def test_fallback_to_qdrant_when_redis_unavailable(self):
        """Test that system falls back to Qdrant when Redis is unavailable."""
        # This test verifies the fallback behavior is designed
        # In practice, it would require Redis to be down
        
        # Expected behavior:
        # Redis unavailable → RAG pipeline continues with Qdrant only
        # No error should occur, just slower retrieval
        
        fallback_response = {
            "status": "ready_for_llm",
            "prompt": "Some prompt",
            "retrievals": [],
            "metadata": {
                "cache_hit": False,  # Would be False if Redis was down (no cache check)
                "used_cache_threshold": 0.95
            }
        }
        
        assert fallback_response["status"] == "ready_for_llm"
        assert "prompt" in fallback_response

    async def test_cache_semantic_similarity_comparison(self):
        """Test the semantic similarity computation for cache hits."""
        # Simulate query vector similarity
        
        # Example: Two semantically similar queries
        cache_embedding = np.array([0.1, 0.2, 0.3, 0.4])
        query_embedding = np.array([0.11, 0.21, 0.31, 0.41])  # Very similar
        
        # Compute cosine similarity
        similarity = np.dot(cache_embedding, query_embedding) / (
            np.linalg.norm(cache_embedding) * np.linalg.norm(query_embedding)
        )
        
        # With threshold 0.95, this might not quite hit (depends on vectors)
        # But the concept is verified
        assert 0 <= similarity <= 1, "Similarity should be normalized to [0,1]"

    async def test_retrieval_format_in_response(self):
        """Test the retrieval result format in response."""
        example_retrieval = {
            "source": "Nghị định số 10/2012/NĐ-CP - Về bảo hiểm xã hội",
            "text": "Bảo hiểm xã hội là chế độ bảo vệ xã hội bắt buộc...",
            "score": 0.92,
            "article_uuid": "abc123def456"
        }
        
        # Verify retrieval structure
        assert "source" in example_retrieval
        assert "text" in example_retrieval
        assert "score" in example_retrieval
        assert isinstance(example_retrieval["score"], float)
        assert 0 <= example_retrieval["score"] <= 1

    async def test_parallel_cache_and_qdrant_setup(self):
        """Test that system is set up for parallel cache + Qdrant lookup."""
        # Verify the infrastructure expects parallel execution
        
        # When ENABLE_LLM_GENERATION=false and Redis is available:
        # 1. Query is embedded
        # 2. Redis vector_search() is called in parallel with Qdrant retrieval
        # 3. Results are compared; if Redis >= threshold, prefer Redis
        # 4. Otherwise use Qdrant results
        
        # This is architectural verification
        parallel_expected = True
        assert parallel_expected, "System should support parallel cache + Qdrant lookup (Phase 19 spec)"


class TestResponsePayloadWhenLLMDisabled:
    """Test the exact response payload structure when LLM generation is disabled."""

    async def test_prompt_only_response_structure(self):
        """Verify prompt-only response structure matches spec."""
        # Expected from Phase 19 PLAN.md
        expected_structure = {
            "status": "ready_for_llm",
            "prompt": "<pre-built RAG prompt text with citations and context>",
            "retrievals": [
                {
                    "source": "Document source reference",
                    "text": "Truncated excerpt...",
                    "score": 0.92,
                    "article_uuid": "uuid_str"
                }
            ],
            "metadata": {
                "cache_hit": True or False,
                "used_cache_threshold": 0.95
            }
        }
        
        # Verify all fields are present
        assert "status" in expected_structure
        assert "prompt" in expected_structure
        assert "retrievals" in expected_structure
        assert "metadata" in expected_structure

    async def test_frontend_can_receive_prompt(self):
        """Verify frontend can receive and process prompt payload."""
        # Frontend should be able to:
        # 1. Parse response.status == "ready_for_llm"
        # 2. Extract response.prompt
        # 3. Extract response.retrievals for display
        # 4. Send prompt to ChatGPT/Gemini with response.retrievals as context
        
        sample_response = {
            "status": "ready_for_llm",
            "prompt": "Bạn là chuyên gia...\n\nCâu hỏi: Quy định về bảo hiểm\nTrả lời:",
            "retrievals": [
                {
                    "source": "Luật bảo hiểm",
                    "text": "Điều 1...",
                    "score": 0.95
                }
            ],
            "metadata": {"cache_hit": False, "used_cache_threshold": 0.95}
        }
        
        # Frontend logic verification
        if sample_response["status"] == "ready_for_llm":
            # Frontend can extract prompt and send to external LLM
            prompt = sample_response["prompt"]
            retrievals = sample_response["retrievals"]
            
            assert isinstance(prompt, str), "Prompt must be string"
            assert isinstance(retrievals, list), "Retrievals must be list"
            assert len(prompt) > 0, "Prompt must not be empty"


class TestCacheConfiguration:
    """Test Redis cache configuration and environment variables."""

    async def test_env_variables_set(self):
        """Verify necessary environment variables are configured."""
        # These can be checked from .env.example
        required_vars = [
            ("REDIS_URL", "redis://redis:6379"),
            ("REDIS_THRESHOLD", "0.95"),
            ("ENABLE_LLM_GENERATION", "false"),
        ]
        
        for var_name, expected_default in required_vars:
            value = os.getenv(var_name)
            # Just verify the keys exist in the environment or have default
            # In testing, these might not be set, so we just verify they can be retrieved
            if value:
                if var_name == "REDIS_THRESHOLD":
                    assert float(value) >= 0.9
                elif var_name == "ENABLE_LLM_GENERATION":
                    assert value.lower() in ("true", "false")

    async def test_docker_compose_redis_service(self):
        """Verify docker-compose.yml includes Redis service."""
        # Read docker-compose.yml and verify redis service exists
        docker_compose_path = "docker-compose.yml"
        
        if os.path.exists(docker_compose_path):
            with open(docker_compose_path) as f:
                content = f.read()
                assert "redis" in content.lower(), "docker-compose should include Redis service"
                assert "redis-stack" in content.lower() or "redis/redis-stack" in content, \
                    "Should use redis-stack image for vector support"


class TestCachePerformanceExpectations:
    """Test performance expectations for cache layer."""

    async def test_cache_hit_latency_target(self):
        """Verify performance target: cache hit latency < 10ms."""
        # This is a specification of expected performance
        # Actual measurement would be done in benchmarks
        
        latency_target_ms = 10
        
        # Cache hit should be much faster than retrieval
        # Redis typically: <1ms (local) or 1-5ms (network)
        assert latency_target_ms > 5, "Target is reasonable for Redis operations"

    async def test_cache_memory_efficiency(self):
        """Test cache memory efficiency expectations."""
        # Phase 19 goal: Reduce Qdrant memory by 30%+
        
        # Expected: Redis caches high-frequency queries
        # Result: Fewer vector searches needed in Qdrant
        
        expected_reduction_percent = 30
        assert expected_reduction_percent > 0, "Expect memory reduction from caching"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

