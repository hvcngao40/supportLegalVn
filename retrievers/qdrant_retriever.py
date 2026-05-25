import os
import time
import hashlib
import random
from typing import List, Optional

from llama_index.core import QueryBundle
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels
# from torch.nn.functional import embedding

from core.constants import SAFE_EMBEDDING_MODEL_NAME
from core.retrieval_types import RetrievalNode, make_retrieval_node
from core.qdrant_config import resolve_qdrant_connection


class QdrantRetriever:
    """
    Wrapper for Qdrant vector search.

    This version supports two retrieval modes:
    1. Article-level retrieval from the `legal_articles` collection.
    2. Chunk-level retrieval from the legacy `legal_chunks` collection.

    The article-level search is the primary path for the new legal pipeline.
    """

    def __init__(
        self,
        collection_name: str = "legal_articles",
        host: str = os.getenv("QDRANT_HOST", "localhost"),
        port: int = int(os.getenv("QDRANT_PORT", 6334)),

        top_k: int = 1,
        embed_model_name: str = None,
    ):
        self._embed_mode = "random" #os.getenv("EMBEDDING_MODE", "model").strip().lower()
        self._random_embed_dim = int(os.getenv("EMBEDDING_DIM", "768"))
        self._warned_random_mode = False

        requested_model = embed_model_name or os.getenv(
            "EMBEDDING_MODEL_NAME", SAFE_EMBEDDING_MODEL_NAME
        )

        try:
            from llama_index.embeddings.huggingface import HuggingFaceEmbedding

            # Mirror EMBEDDING_DEVICE behavior used elsewhere to allow easy CPU/GPU switching.
            device_pref = os.getenv("EMBEDDING_DEVICE", "auto").lower()
            if device_pref not in ("auto", "cpu", "cuda", "gpu"):
                device_pref = "auto"

            if device_pref == "auto":
                device = "cuda" if (os.getenv("FORCE_DISABLE_CUDA", "") == "" and __import__("torch").cuda.is_available()) else "cpu"
            elif device_pref in ("cuda", "gpu"):
                device = "cuda"
            else:
                device = "cpu"
            if self._embed_mode == "random":
                # print("[QdrantRetriever] EMBEDDING_MODE=random: skipping model init")
                self.embed_model = None
            else:
                pass
                # print(f"[QdrantRetriever] Initializing embedding model '{requested_model}' on device: {device}")

            # Pass device hint to HuggingFaceEmbedding if supported.
            try:
                if self._embed_mode != "random":
                    self.embed_model = HuggingFaceEmbedding(model_name=requested_model, model_kwargs={"device": device})
            except TypeError:
                # Older versions may not accept model_kwargs; fall back to simple constructor.
                if self._embed_mode != "random":
                    self.embed_model = HuggingFaceEmbedding(model_name=requested_model)
        except Exception as e:
            # print(f"[Warning] Qdrant embed model unavailable: {e}")
            self.embed_model = None

        settings = resolve_qdrant_connection(default_host=host, default_port=port)
        self._client = None
        self._client_host = settings.host
        self._client_port = settings.port
        self.collection_name = collection_name
        self.top_k = top_k

    def _get_client(self):
        if self._client is not None:
            return self._client

        start = time.perf_counter()
        try:
            self._client = AsyncQdrantClient(
                host=self._client_host,
                port=self._client_port,
                prefer_grpc=True,
                check_compatibility=False,
            )

            elapsed = time.perf_counter() - start
            # print(f"[QdrantRetriever] Created AsyncQdrantClient in {elapsed:.2f}s")
        except Exception as e:
            elapsed = time.perf_counter() - start
            # print(f"[Warning] Qdrant client unavailable: {e} (setup took {elapsed:.2f}s)")
            self._client = None

        return self._client

    async def _embed_query(self, query_str: str):
        if self._embed_mode == "random":
            if not self._warned_random_mode:
                # print("[QdrantRetriever] Using random embeddings for load testing")
                self._warned_random_mode = True
            seed = int(hashlib.sha256(query_str.encode("utf-8")).hexdigest()[:8], 16)
            rng = random.Random(seed)
            return [rng.random() for _ in range(self._random_embed_dim)]
        if self.embed_model is None:
            return None
        return await self.embed_model.aget_query_embedding(query_str)

    async def aretrieve_articles(
        self,
        query: QueryBundle,
        top_k: Optional[int] = None,
        query_filter: Optional[qmodels.Filter] = None,
        query_embedding: Optional[List[float]] = None,
    ) -> List[RetrievalNode]:

        """
        Primary path:
        Search the `legal_articles` collection and return article-level nodes.
        """
        retrieval_start = time.time()

        if self.embed_model is None and self._embed_mode != "random":
            return []

        client = self._get_client()
        if client is None:
            return []

        if query_embedding is None:
            embed_start = time.time()
            query_embedding = await self._embed_query(query.query_str)
            embed_duration = time.time() - embed_start
            # print(f"[QdrantRetriever] Embedding took {embed_duration:.2f}s")

        if query_embedding is None:
            return []

        limit = top_k or self.top_k

        qdrant_start = time.time()
        try:
            response = await client.query_points(
                collection_name="legal_articles",
                using="dense",
                query=qmodels.NearestQuery(nearest=query_embedding),  # Ăn HNSW Index
                query_filter=query_filter,  # Ăn Payload Index
                limit=limit,
                with_payload=["article_uuid"],
                # Keep payload small in candidate stage; full text is hydrated from SQLite later.
                # with_payload=[
                #     "article_uuid",
                #     "doc_id",
                #     "so_ky_hieu",
                #     "article_title",
                #     "article_path",
                # ],
            )
            hits = response.points
            qdrant_duration = time.time() - qdrant_start
            # print(f"[QdrantRetriever] Qdrant query took {qdrant_duration:.2f}s, hits: {len(hits)}")
        except Exception as e:
            # print(f"[Error] Qdrant article search failed: {repr(e)}")
            return []

        nodes: List[RetrievalNode] = []
        parse_total = 0.0
        metadata_total = 0.0
        node_ctor_total = 0.0
        append_total = 0.0
        map_total_start = time.perf_counter()

        for hit in hits:
            t0 = time.perf_counter()
            payload = hit.payload or {}
            t1 = time.perf_counter()

            # field_name optimization: only article_uuid is retrieved from Qdrant
            # Full metadata will be hydrated from SQLite FTS later
            article_uuid = payload.get("article_uuid", str(hit.id))
            metadata = {
                "article_uuid": article_uuid,
                "type": "ARTICLE",
            }
            t2 = time.perf_counter()

            node = make_retrieval_node(
                node_id=article_uuid,
                # Minimal text placeholder; canonical full content is fetched from SQLite later.
                text=article_uuid,
                metadata=metadata,
                score=hit.score,
            )
            t3 = time.perf_counter()

            nodes.append(node)
            t4 = time.perf_counter()

            parse_total += t1 - t0
            metadata_total += t2 - t1
            node_ctor_total += t3 - t2
            append_total += t4 - t3

        map_total = time.perf_counter() - map_total_start
        hit_count = len(hits)
        if hit_count:
            # print(
            #     "[QdrantRetriever] Post-query map stats: "
            #     f"total={map_total:.2f}s, hits={hit_count}, "
            #     f"avg_parse={parse_total / hit_count * 1000:.2f}ms, "
            #     f"avg_metadata={metadata_total / hit_count * 1000:.2f}ms, "
            #     f"avg_node_ctor={node_ctor_total / hit_count * 1000:.2f}ms, "
            #     f"avg_append={append_total / hit_count * 1000:.2f}ms"
            # )
            pass

        total_duration = time.time() - retrieval_start
        # print(f"[QdrantRetriever] Total aretrieve_articles: {total_duration:.2f}s")
        
        return nodes

    async def aretrieve_with_filter(
        self,
        query: QueryBundle,
        domains: Optional[List[str]] = None,
    ) -> List[RetrievalNode]:
        """
        Legacy / fallback path:
        Search the configured collection (default: legal_chunks).

        This is still kept for compatibility with older code paths.
        """
        retrieval_start = time.time()

        if self.embed_model is None and self._embed_mode != "random":
            return []

        client = self._get_client()
        if client is None:
            return []

        embed_start = time.time()
        query_embedding = await self._embed_query(query.query_str)
        embed_duration = time.time() - embed_start
        # print(f"[QdrantRetriever] Embedding took {embed_duration:.2f}s")
        
        if query_embedding is None:
            return []

        query_filter = None
        if domains and "General" not in domains:
            query_filter = qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="domain",
                        match=qmodels.MatchAny(any=domains),
                    )
                ]
            )

        qdrant_start = time.time()
        try:
            response = await client.query_points(
                collection_name=self.collection_name,
                query=qmodels.NearestQuery(nearest=query_embedding),
                using="dense",
                query_filter=query_filter,
                limit=self.top_k,
                # Keep payload small in candidate stage; full text is hydrated from SQLite later.
                with_payload=[
                    "article_uuid",
                    "doc_id",
                    "so_ky_hieu",
                    "article_title",
                    "article_path",
                ],
            )
            hits = response.points
            qdrant_duration = time.time() - qdrant_start
            # print(f"[QdrantRetriever] Qdrant query took {qdrant_duration:.2f}s, hits: {len(hits)}")
        except Exception as e:
            # print(f"[Error] Qdrant search failed: {repr(e)}")
            return []

        nodes: List[RetrievalNode] = []
        for hit in hits:
            payload = hit.payload or {}

            metadata = dict(payload)
            metadata.setdefault("type", "CHUNK")

            nodes.append(
                make_retrieval_node(
                    node_id=str(hit.id),
                    text=payload.get("content", ""),
                    metadata=metadata,
                    score=hit.score,
                )
            )

        total_duration = time.time() - retrieval_start
        # print(f"[QdrantRetriever] Total aretrieve_with_filter: {total_duration:.2f}s")
        
        return nodes

    async def aretrieve(self, query_str: str) -> List[RetrievalNode]:
        """Simple string-based retrieval against the configured collection."""
        return await self.aretrieve_with_filter(QueryBundle(query_str))

    def close(self):
        if self._client:
            self._client.close()
