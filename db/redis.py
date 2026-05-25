from typing import List, Optional, Dict, Any
import os
import json
import logging
import asyncio
import numpy as np
from uuid import uuid4
from datetime import datetime

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

class RedisManager:
    """
    Async Redis manager using Redis Stack for vector search and semantic caching.
    Features:
    - Vector similarity search using Redis Stack (FT.SEARCH)
    - Session history storage with TTL
    - Retrieval result caching
    - JSON-safe serialization
    """
    def __init__(self, url: Optional[str] = None):
        self.url = url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self._client: Optional[aioredis.Redis] = None
        self.vector_dimension = 384  # Default for HuggingFace embeddings
        self.session_ttl = 7 * 24 * 3600  # 7 days

    async def init(self):
        """Initialize Redis connection and set up indexes if needed."""
        if self._client:
            return
        
        self._client = aioredis.from_url(self.url, decode_responses=False)
        # Test connection
        try:
            await self._client.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.exception("Redis ping failed: %s", e)
            raise

    async def close(self):
        """Close Redis connection gracefully."""
        if self._client:
            try:
                await self._client.close()
            except Exception:
                pass
            self._client = None

    async def _create_index_if_not_exists(self, index_name: str = "documents_idx"):
        """Create Redis search index for vector similarity if it doesn't exist."""
        if self._client is None:
            raise RuntimeError("Redis client not initialized")
        
        try:
            # Check if index exists
            await self._client.execute_command("FT.INFO", index_name)
            logger.info(f"Index {index_name} already exists")
        except Exception as e:
            if "unknown index" in str(e).lower():
                # Create new index with VECTOR field
                try:
                    schema_def = [
                        "documents_idx",  # index name
                        "ON", "HASH",  # search on HASH type
                        "PREFIX", "1", "doc:",  # key prefix
                        "SCHEMA",
                        "embedding", "VECTOR", "HNSW", "6",  # 6 params for HNSW
                        "TYPE", "FLOAT32",
                        "DIM", str(self.vector_dimension),
                        "DISTANCE_METRIC", "COSINE",
                        "doc_id", "TEXT", "SORTABLE",
                        "snippet", "TEXT",
                        "score", "NUMERIC", "SORTABLE",
                        "source", "TEXT",
                        "created_at", "NUMERIC", "SORTABLE",
                    ]
                    await self._client.execute_command("FT.CREATE", *schema_def)
                    logger.info(f"Created index {index_name}")
                except Exception as create_err:
                    if "already exists" not in str(create_err).lower():
                        logger.warning(f"Index creation warning: {create_err}")
            else:
                logger.warning(f"Index check warning: {e}")

    async def vector_search(
        self, 
        index: str, 
        embedding: List[float], 
        k: int = 5, 
        threshold: float = 0.95
    ) -> List[Dict[str, Any]]:
        """
        Perform vector similarity search using Redis Stack.
        
        Args:
            index: Index name (e.g., "documents_idx")
            embedding: Query embedding vector
            k: Number of results to return
            threshold: Similarity threshold (0.0 to 1.0). Results below threshold are filtered out.
        
        Returns:
            List of documents with similarity scores
        """
        if self._client is None:
            raise RuntimeError("Redis client not initialized")
        
        try:
            # Ensure index exists
            await self._create_index_if_not_exists(index)
            
            # Prepare embedding for redis search (pack as binary float32)
            embedding_array = np.array(embedding, dtype=np.float32)
            embedding_bytes = embedding_array.tobytes()
            
            # Build KNN query: search for k nearest vectors with HNSW
            # FT.SEARCH index "@embedding:[VECTOR_RANGE $radius $vector]" PARAMS 2 radius 0 vector <bytes>
            query_str = f"@embedding:[VECTOR_RANGE $eps $vector]"
            
            results = await self._client.execute_command(
                "FT.SEARCH",
                index,
                query_str,
                "PARAMS", "3",
                "eps", str(1.0 - threshold),  # Convert threshold to epsilon (distance)
                "vector", embedding_bytes,
                "LIMIT", "0", str(k),
                "SORTBY", "score",
                "ASC"
            )
            
            # Parse results
            parsed = []
            if results and len(results) > 1:
                # results[0] is the count, results[1:] are alternating doc_ids and field arrays
                for i in range(1, len(results), 2):
                    doc_id = results[i].decode("utf-8") if isinstance(results[i], bytes) else results[i]
                    fields = results[i + 1] if i + 1 < len(results) else []
                    
                    # Reconstruct document from field pairs
                    doc_dict = {"id": doc_id}
                    for j in range(0, len(fields), 2):
                        key = fields[j].decode("utf-8") if isinstance(fields[j], bytes) else fields[j]
                        value = fields[j + 1]
                        
                        if key == "score":
                            doc_dict["score"] = float(value.decode("utf-8") if isinstance(value, bytes) else value)
                        elif key == "doc_id":
                            doc_dict["doc_id"] = value.decode("utf-8") if isinstance(value, bytes) else value
                        else:
                            doc_dict[key] = value.decode("utf-8") if isinstance(value, bytes) else value
                    
                    # Only include results meeting threshold
                    if doc_dict.get("score", 0.0) >= threshold:
                        parsed.append(doc_dict)
            
            logger.info(f"Vector search returned {len(parsed)} results from {len(results) // 2} candidates")
            return parsed
        except Exception as e:
            logger.warning(f"Vector search failed (falling back to Qdrant): {e}")
            return []

    async def new_document(
        self,
        doc_id: str,
        embedding: List[float],
        snippet: str,
        score: float = 0.0,
        source: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Store a new document with vector embedding in Redis."""
        if self._client is None:
            raise RuntimeError("Redis client not initialized")
        
        try:
            doc_key = f"doc:{uuid4()}"
            
            # Prepare embedding as binary float32
            embedding_array = np.array(embedding, dtype=np.float32)
            embedding_bytes = embedding_array.tobytes()
            
            doc_data = {
                "embedding": embedding_bytes,
                "doc_id": doc_id,
                "snippet": snippet,
                "score": str(score),
                "source": source,
                "created_at": str(int(datetime.now().timestamp())),
            }
            
            # Add metadata if provided
            if metadata:
                for k, v in metadata.items():
                    doc_data[k] = json.dumps(v) if isinstance(v, dict) else str(v)
            
            await self._client.hset(doc_key, mapping=doc_data)
            logger.debug(f"Stored document {doc_key}")
            return doc_key
        except Exception as e:
            logger.error(f"Failed to store document: {e}")
            raise

    async def save_cached_retrieval(
        self,
        query_embedding: List[float],
        retrievals: List[Dict[str, Any]],
        session_id: Optional[str] = None
    ) -> str:
        """Save retrieval results to cache for quick retrieval on semantic matching."""
        if self._client is None:
            raise RuntimeError("Redis client not initialized")
        
        try:
            cache_key = f"cache:retrieval:{uuid4()}"
            
            cache_data = {
                "embedding": np.array(query_embedding, dtype=np.float32).tobytes(),
                "retrievals": json.dumps(retrievals),
                "session_id": session_id or "unknown",
                "created_at": str(int(datetime.now().timestamp())),
            }
            
            await self._client.hset(cache_key, mapping=cache_data)
            # Set expiration (24 hours for retrieval cache)
            await self._client.expire(cache_key, 24 * 3600)
            logger.debug(f"Saved cached retrieval {cache_key}")
            return cache_key
        except Exception as e:
            logger.error(f"Failed to save cached retrieval: {e}")
            raise

    async def get_session(self, session_id: str) -> List[Dict[str, Any]]:
        """Retrieve chat session history."""
        if self._client is None:
            raise RuntimeError("Redis client not initialized")
        
        try:
            raw = await self._client.get(f"session:{session_id}")
            if not raw:
                return []
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8")
            return json.loads(raw)
        except Exception as e:
            logger.warning(f"Failed to get session: {e}")
            return []

    async def append_session(self, session_id: str, message: Dict[str, Any]):
        """Append a message to session history."""
        if self._client is None:
            raise RuntimeError("Redis client not initialized")
        
        try:
            history = await self.get_session(session_id)
            history.append(message)
            await self._client.set(
                f"session:{session_id}", 
                json.dumps(history),
                ex=self.session_ttl
            )
            logger.debug(f"Appended message to session {session_id}")
        except Exception as e:
            logger.error(f"Failed to append session data: {e}")

    async def exists(self, key: str) -> bool:
        """Check if a key exists."""
        if self._client is None:
            return False
        try:
            return await self._client.exists(key) > 0
        except Exception:
            return False

    async def get(self, key: str) -> Optional[str]:
        """Retrieve string value from Redis."""
        if self._client is None:
            return None
        try:
            value = await self._client.get(key)
            if isinstance(value, bytes):
                return value.decode("utf-8")
            return value
        except Exception:
            return None

    async def set(self, key: str, value: str, ex: Optional[int] = None):
        """Store string value in Redis with optional expiration."""
        if self._client is None:
            raise RuntimeError("Redis client not initialized")
        try:
            await self._client.set(key, value, ex=ex)
        except Exception as e:
            logger.error(f"Failed to set {key}: {e}")

    async def delete(self, key: str):
        """Delete a key from Redis."""
        if self._client is None:
            return
        try:
            await self._client.delete(key)
        except Exception as e:
            logger.error(f"Failed to delete {key}: {e}")

    async def clear(self):
        """Clear all data in the current database (use carefully!)."""
        if self._client is None:
            return
        try:
            await self._client.flushdb()
            logger.warning("Redis database cleared")
        except Exception as e:
            logger.error(f"Failed to clear database: {e}")

