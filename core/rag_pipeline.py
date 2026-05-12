import os
import asyncio
import time

import aiosqlite
from typing import List, Dict, Any, Optional, AsyncGenerator, Tuple

import torch
from llama_index.core.retrievers import BaseRetriever
from llama_index.core import QueryBundle
from llama_index.core.schema import NodeWithScore, TextNode
from sentence_transformers import CrossEncoder

# from sentence_transformers import CrossEncoder

from core.classifier import LegalQueryClassifier
from core.constants import SQLITE_PATH
from retrievers.sqlite_retriever import SQLiteFTS5Retriever
from retrievers.qdrant_retriever import QdrantRetriever
from tools.gemini_client import GeminiClient
from tools.groq_client import GroqClient
from tools.deepseek_client import DeepSeekClient
from tools.qwen_dashscope_client import QwenDashScopeClient
from tools.qwen_ollama_client import QwenOllamaClient
from tools.openrouter_client import OpenRouterClient
from core.security import llm_circuit_breaker
from db.qdrant import QdrantManager
# import torch



def _unique_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _node_article_uuid(node: NodeWithScore) -> str:
    return str(node.node.metadata.get("article_uuid") or node.node.node_id)


def _build_context_str(nodes: List[NodeWithScore]) -> str:
    return "\n\n".join(
        f"Văn bản: {n.node.metadata.get('so_ky_hieu')} - {n.node.metadata.get('article_title')}\n"
        f"Nội dung:\n{n.node.get_content()}"
        for n in nodes
    )


def _get_legal_priority(node: NodeWithScore) -> int:
    so_ky_hieu = node.node.metadata.get("so_ky_hieu") or ""
    if "QH" in so_ky_hieu:
        return 1
    elif "NĐ-CP" in so_ky_hieu or "CP" in so_ky_hieu or "TT" in so_ky_hieu:
        return 2
    elif "UBND" in so_ky_hieu:
        return 3
    return 2


def _build_article_rerank_text(node: TextNode, max_chars: int = 4000) -> str:
    title = node.metadata.get("article_title") or node.metadata.get("so_ky_hieu") or ""
    content = node.get_content() or ""
    content = " ".join(content.split())
    if len(content) > max_chars:
        content = content[:max_chars]
    return f"{title}\n{content}".strip()


class LegalHybridRetriever(BaseRetriever):
    """
    Article-first hybrid retriever.

    Primary path:
    1. Qdrant semantic search over legal_articles.
    2. SQLite BM25 over article titles.
    3. Fuse article candidates.
    4. Rerank article candidates.

    Legacy fallback:
    5. Chunk-level vector + FTS search, then map back to article candidates.
    """

    def __init__(
        self,
        classifier: LegalQueryClassifier,
        vector_retriever: QdrantRetriever,
        fts_retriever: SQLiteFTS5Retriever,
        db_path: str = os.getenv("SQLITE_DB_PATH", SQLITE_PATH),
        rrf_k: int = 60,
        top_k: int = 5,
        article_top_k: int = 20,
        title_bm25_top_k: int = 20,
        rerank_input_size: int = 30,
        use_classifier: bool = True,
        use_fts_fallback: bool = True,
    ):
        self.classifier = classifier
        self.vector_retriever = vector_retriever
        self.fts_retriever = fts_retriever
        self.db_path = db_path
        self.rrf_k = rrf_k
        self.top_k = top_k
        self.article_top_k = article_top_k
        self.title_bm25_top_k = title_bm25_top_k
        self.rerank_input_size = rerank_input_size
        self.use_classifier = use_classifier
        self.use_fts_fallback = use_fts_fallback

        reranker_model = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
        try:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self._reranker = CrossEncoder(reranker_model, device=device)
            print(f"[OK] Reranker loaded: {reranker_model} on {device}")
        except Exception as e:
            print(f"[Warning] Failed to load reranker: {e}. Reranking will be skipped.")
            self._reranker = None
        # self._reranker = None  # Reranker is currently disabled due to loading issues; can be re-enabled when resolved.

        super().__init__()

    def _accumulate_rrf(
        self,
        results: List[NodeWithScore],
        fused_scores: Dict[str, float],
        node_by_uuid: Dict[str, NodeWithScore],
    ) -> None:
        for rank, res in enumerate(results):
            article_uuid = _node_article_uuid(res)
            fused_scores[article_uuid] = fused_scores.get(article_uuid, 0.0) + 1.0 / (
                self.rrf_k + rank + 1
            )
            if article_uuid not in node_by_uuid:
                node_by_uuid[article_uuid] = res

    async def _legacy_chunk_fallback(self, query_bundle: QueryBundle, query_str: str) -> List[NodeWithScore]:
        legacy_chunk_nodes = await asyncio.gather(
            self.vector_retriever.aretrieve_with_filter(query_bundle),
            self.fts_retriever.aretrieve(query_str),
        )

        fused_chunk_scores: Dict[str, float] = {}
        article_uuid_to_score: Dict[str, float] = {}

        for source_nodes in legacy_chunk_nodes:
            for rank, res in enumerate(source_nodes):
                cid = res.node.node_id
                fused_chunk_scores[cid] = fused_chunk_scores.get(cid, 0.0) + 1.0 / (
                    self.rrf_k + rank + 1
                )
                article_uuid = res.node.metadata.get("article_uuid")
                if article_uuid:
                    article_uuid_to_score[article_uuid] = max(
                        article_uuid_to_score.get(article_uuid, 0.0),
                        fused_chunk_scores[cid],
                    )

        if not article_uuid_to_score:
            return []

        top_article_uuids = sorted(
            article_uuid_to_score,
            key=article_uuid_to_score.get,
            reverse=True,
        )[: self.top_k]

        if not top_article_uuids:
            return []

        articles = await self.fts_retriever.get_articles_by_uuids(top_article_uuids)
        article_map = {n.node.metadata.get("article_uuid"): n for n in articles}

        results: List[NodeWithScore] = []
        for aid in top_article_uuids:
            article_node = article_map.get(aid)
            if article_node is None:
                continue
            results.append(
                NodeWithScore(
                    node=TextNode(
                        text=article_node.node.get_content(),
                        id_=article_node.node.node_id,
                        metadata=article_node.node.metadata,
                    ),
                    score=float(article_uuid_to_score.get(aid, 0.0)),
                )
            )

        return results

    async def _retrieve_article_candidates(
        self,
        query_bundle: QueryBundle,
        query_str: str,
    ) -> List[NodeWithScore]:
        """
        Primary retrieval path: Qdrant article semantic search + BM25 on article title.
        """
        qdrant_task = self.vector_retriever.aretrieve_articles(
            query_bundle,
            top_k=self.article_top_k,
        )
        bm25_task = self.fts_retriever.aretrieve_articles_by_title(
            query_str,
            top_k=self.title_bm25_top_k,
        )

        article_stage_start = time.time()
        article_nodes, title_nodes = await asyncio.gather(qdrant_task, bm25_task)
        print(
            "[Retriever] Candidate gather time: "
            f"{time.time() - article_stage_start:.2f}s "
            f"(qdrant={len(article_nodes)}, bm25={len(title_nodes)})"
        )

        if not article_nodes and not title_nodes:
            if not self.use_fts_fallback:
                return []
            return await self._legacy_chunk_fallback(query_bundle, query_str)

        fused_scores: Dict[str, float] = {}
        node_by_uuid: Dict[str, NodeWithScore] = {}

        self._accumulate_rrf(article_nodes, fused_scores, node_by_uuid)
        self._accumulate_rrf(title_nodes, fused_scores, node_by_uuid)

        if not fused_scores:
            return []

        ranked_article_uuids = sorted(
            fused_scores,
            key=fused_scores.get,
            reverse=True,
        )[: max(self.article_top_k, self.title_bm25_top_k, self.rerank_input_size)]

        hydrate_start = time.time()
        hydrated_articles = await self.fts_retriever.get_articles_by_uuids(ranked_article_uuids)
        hydrated_by_uuid = {
            str(item.node.metadata.get("article_uuid") or item.node.node_id): item
            for item in hydrated_articles
        }

        results: List[NodeWithScore] = []
        for aid in ranked_article_uuids:
            hydrated = hydrated_by_uuid.get(aid)
            if hydrated is not None:
                results.append(
                    NodeWithScore(
                        node=hydrated.node,
                        score=float(fused_scores.get(aid, 0.0)),
                    )
                )
                continue

            # Fallback: keep candidate node if canonical article row was not found.
            node = node_by_uuid.get(aid)
            if node is None:
                continue
            results.append(
                NodeWithScore(
                    node=node.node,
                    score=float(fused_scores.get(aid, 0.0)),
                )
            )

        print(
            "[Retriever] Hydration time: "
            f"{time.time() - hydrate_start:.2f}s, hydrated: {len(hydrated_articles)}"
        )

        return results

    async def _aretrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        query_str = query_bundle.query_str

        start_time = time.time()
        if self.use_classifier and self.classifier is not None:
            try:
                _classification = await self.classifier.classify(query_str)
                _domains = getattr(_classification, "domains", []) or []
            except Exception:
                pass

        classifier_time = time.time()
        print(f"[Retriever] Classification time: {classifier_time - start_time:.2f}s, domains: {_domains if 'domains' in locals() else 'N/A'}")

        article_candidates = await self._retrieve_article_candidates(query_bundle, query_str)
        retriever_time = time.time()
        print(f"[Retriever] Article retrieval time: {retriever_time - classifier_time:.2f}s, candidates found: {len(article_candidates)}")

        if not article_candidates:
            return []

        if self._reranker is not None:
            rerank_pool = article_candidates[: self.rerank_input_size]
            valid_pairs: List[Tuple[str, str]] = []
            valid_nodes: List[NodeWithScore] = []

            for candidate in rerank_pool:
                content = _build_article_rerank_text(candidate.node)
                if content.strip():
                    valid_pairs.append((query_str, content))
                    valid_nodes.append(candidate)

            if valid_pairs:
                scores = self._reranker.predict(valid_pairs)
                reranked = sorted(zip(valid_nodes, scores), key=lambda x: -x[1])
                results = [
                    NodeWithScore(node=item[0].node, score=float(item[1]))
                    for item in reranked[: self.top_k]
                ]
                if results:
                    print("[Retriever] Reranking time: {:.2f}s".format(time.time() - retriever_time))
                    return results

        # Fallback when reranker is absent or produces no output.
        return article_candidates[: self.top_k]

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        return asyncio.run(self._aretrieve(query_bundle))


class LegalRAGPipeline:
    """
    Article-first RAG Pipeline:
    - retrieve full articles
    - generate answer from article context
    - emit article-level citations
    """

    def __init__(
        self,
        retriever: LegalHybridRetriever,
        provider: str = "gemini",
        model_name: Optional[str] = None,
        llm: Optional[Any] = None,
    ):
        self.retriever = retriever
        if llm:
            self.client = llm
        else:
            self.client = self._get_client(provider, model_name)
        
        self.cache_mgr = QdrantManager()


        self.qa_prompt_template = (
            "Bạn là một chuyên gia pháp luật Việt Nam cao cấp. "
            "Hãy trả lời câu hỏi của người dùng dựa trên các tài liệu pháp luật (các Điều luật) được cung cấp dưới đây.\n"
            "---------------------\n"
            "{context_str}\n"
            "---------------------\n"
            "Yêu cầu về cấu trúc câu trả lời (IRAC):\n"
            "1. Vấn đề (Issue): Tóm tắt ngắn gọn vấn đề pháp lý của người dùng.\n"
            "2. Quy định (Rule): Trích dẫn chính xác các Điều, Khoản từ các văn bản pháp luật liên quan. "
            "Sử dụng định dạng: 'Theo [Khoản], [Điều], [Tên văn bản]...'.\n"
            "3. Phân tích (Analysis): Giải thích cách các quy định trên áp dụng vào trường hợp cụ thể của người dùng.\n"
            "4. Kết luận (Conclusion): Đưa ra lời khuyên hoặc hướng giải quyết cuối cùng.\n\n"
            "Lưu ý quan trọng:\n"
            "- Nếu thông tin không có trong tài liệu, hãy nói rõ 'Tôi không tìm thấy quy định cụ thể cho vấn đề này trong cơ sở dữ liệu'.\n"
            "- Tuyệt đối không được bịa đặt (hallucinate) số hiệu văn bản hoặc nội dung luật.\n"            
            "{chat_history_str}"
            "Câu hỏi: {query_str}\n"
            "Trả lời:"
        )

    def _get_client(self, provider: str, model_name: Optional[str]) -> Any:
        provider = provider.lower()
        if provider == "gemini":
            return GeminiClient(model_name=model_name or "gemini-2.0-flash")
        elif provider == "groq":
            return GroqClient(model_name=model_name or "llama-3.1-8b-instant")
        elif provider == "deepseek":
            return DeepSeekClient(model_name=model_name or "deepseek-chat")
        elif provider == "dashscope":
            return QwenDashScopeClient(model_name=model_name or "qwen-plus")
        elif provider == "ollama":
            return QwenOllamaClient(model_name=model_name or os.getenv("OLLAMA_MODEL", "qwen-2.5:3b"))
        elif provider == "openrouter":
            return OpenRouterClient(model_name=model_name)
        else:
            raise ValueError(f"Unsupported generation provider: {provider}")

    async def arewrite_query(self, query: str, chat_history: List[Any]) -> str:
        if not chat_history:
            return query
            
        history_str = "\n".join([f"{msg.role.capitalize()}: {msg.content}" for msg in chat_history])
        rewrite_prompt = (
            "Dựa vào lịch sử trò chuyện dưới đây, hãy viết lại câu hỏi tiếp theo của người dùng "
            "thành một câu hỏi duy nhất, độc lập và rõ ràng, chứa đầy đủ ngữ cảnh để có thể tìm kiếm tài liệu pháp luật. "
            "Nếu câu hỏi đã rõ ràng, hãy giữ nguyên. Không trả lời câu hỏi, chỉ viết lại câu hỏi.\n\n"
            f"Lịch sử:\n{history_str}\n\n"
            f"Câu hỏi tiếp theo: {query}\n\n"
            "Câu hỏi được viết lại:"
        )
        try:
            response = await llm_circuit_breaker.call(self.client.generate_content_async, rewrite_prompt)
            rewritten = response.text.strip()
            print(f"[RAG Pipeline] Query rewritten: '{query}' -> '{rewritten}'")
            return rewritten
        except Exception as e:
            print(f"[RAG Pipeline] Query rewrite failed: {e}")
            return query

    def _format_chat_history(self, chat_history: Optional[List[Any]]) -> str:
        if not chat_history:
            return ""
        history_str = "Lịch sử trò chuyện gần đây:\n"
        for msg in chat_history:
            history_str += f"{msg.role.capitalize()}: {msg.content}\n"
        return history_str + "\n"

    async def acustom_query(self, query_str: str, chat_history: Optional[List[Any]] = None) -> Dict[str, Any]:
        """Execute the full RAG pipeline."""
        start_time = time.time()
        
        search_query = query_str
        if chat_history:
            search_query = await self.arewrite_query(query_str, chat_history)
            
        # 0. Check Semantic Cache
        query_vector = await self.retriever.vector_retriever._embed_query(search_query)
        if not query_vector:
            print(f"[RAG Pipeline] Warning: Failed to embed query for semantic cache check.")
        if query_vector:
            cached_data = await self.cache_mgr.check_semantic_cache(query_vector)
            if cached_data:
                print(f"[RAG Pipeline] Semantic Cache HIT")
                return {
                    "answer": cached_data.get("answer"),
                    "citations": cached_data.get("citations", []),
                    "detected_domains": [],
                    "confidence_score": 1.0,
                    "is_cached": True
                }


        nodes = await self.retriever.aretrieve(search_query)

        print(f"[RAG Pipeline] Retrieved {len(nodes)} nodes in {time.time() - start_time:.2f}s")

        nodes.sort(key=lambda n: (_get_legal_priority(n), -float(n.score)))

        context_str = _build_context_str(nodes)
        chat_history_str = self._format_chat_history(chat_history)

        prompt = self.qa_prompt_template.format(
            context_str=context_str,
            chat_history_str=chat_history_str,
            query_str=query_str,
        )

        response = await llm_circuit_breaker.call(self.client.generate_content_async, prompt)

            
        print(

            f"[RAG Pipeline] Generated prompt of length {len(prompt)} characters, time taken: {time.time() - start_time:.2f}s")

        citations = []
        seen_sources = set()
        for n in nodes:
            source_name = f"{n.node.metadata.get('so_ky_hieu')} - {n.node.metadata.get('article_title')}"
            if source_name in seen_sources:
                continue
            seen_sources.add(source_name)
            
            citations.append(
                {
                    "source": source_name,
                    "text": n.node.get_content()[:300] + "...",
                    "score": float(n.score),
                    "article_uuid": str(n.node.metadata.get("article_uuid") or n.node.node_id),
                }
            )

        # Save to Cache (Moved after citations are extracted)
        if query_vector:
            await self.cache_mgr.save_to_cache(search_query, query_vector, response.text, citations)

        return {
            "answer": response.text,
            "citations": citations,
            "detected_domains": [],
            "confidence_score": 0.0,
        }


    async def astream_query(self, query_str: str, chat_history: Optional[List[Any]] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream the RAG response with metadata."""
        search_query = query_str
        if chat_history:
            search_query = await self.arewrite_query(query_str, chat_history)
            
        # 0. Check Semantic Cache
        query_vector = await self.retriever.vector_retriever._embed_query(search_query)
        if query_vector:
            cached_data = await self.cache_mgr.check_semantic_cache(query_vector)
            if cached_data:
                print(f"[RAG Pipeline] Semantic Cache HIT (Streaming)")
                yield {"type": "citations", "data": cached_data.get("citations", [])}
                yield {"type": "token", "content": cached_data.get("answer")}
                yield {"type": "is_cached", "data": True}
                return


        # 1. Retrieval
        nodes = await self.retriever.aretrieve(search_query)

        nodes.sort(key=lambda n: (_get_legal_priority(n), -float(n.score)))

        # 2. Yield Citations immediately (Option A)
        citations = []
        seen_sources = set()
        for n in nodes:
            source_name = f"{n.node.metadata.get('so_ky_hieu')} - {n.node.metadata.get('article_title')}"
            if source_name in seen_sources:
                continue
            seen_sources.add(source_name)
            citations.append({
                "source": source_name,
                "text": n.node.get_content()[:300] + "...",
                "score": float(n.score),
                "article_uuid": str(n.node.metadata.get("article_uuid") or n.node.node_id),
            })
        yield {"type": "citations", "data": citations}

        # 3. Start Classification in background (don't wait for it to start streaming)
        classification_task = None
        if hasattr(self.retriever, "classifier") and self.retriever.classifier:
            classification_task = asyncio.create_task(llm_circuit_breaker.call(self.retriever.classifier.classify, search_query))

        # 4. Prompt construction
        context_str = _build_context_str(nodes)
        chat_history_str = self._format_chat_history(chat_history)
        prompt = self.qa_prompt_template.format(
            context_str=context_str,
            chat_history_str=chat_history_str,
            query_str=query_str,
        )

        full_response = ""
        async for chunk in llm_circuit_breaker.astream_call(self.client.astream_query, prompt):
            if chunk.text:
                full_response += chunk.text
                yield {"type": "token", "content": chunk.text}

            
            # Check if classification is ready while streaming
            if classification_task and classification_task.done():
                try:
                    classification = classification_task.result()
                    yield {
                        "type": "classification", 
                        "domains": classification.domains,
                        "confidence": classification.confidence
                    }
                    classification_task = None # Only yield once
                except Exception as e:
                    print(f"[RAG Pipeline] Classification failed: {e}")
                    classification_task = None

        # 6. Final classification check if not already sent
        if classification_task:
            try:
                classification = await classification_task
                yield {
                    "type": "classification", 
                    "domains": classification.domains,
                    "confidence": classification.confidence
                }
            except Exception as e:
                print(f"[RAG Pipeline] Classification failed at end: {e}")
        
        # 6. Save to Cache
        if query_vector and full_response:
            await self.cache_mgr.save_to_cache(search_query, query_vector, full_response, citations)



    async def retrieve_only(self, query_str: str, top_k: int = 15) -> List[Dict[str, Any]]:
        """
        Isolated retrieval without LLM generation or classifier overhead.
        Purpose: Direct measurement of embedding + Qdrant latency for performance testing.

        Returns list of dicts with: id, score, title, so_ky_hieu
        """
        import time

        query_bundle = QueryBundle(query_str=query_str)

        # Direct retrieval without classification
        start = time.time()
        results = await self.retriever._aretrieve(query_bundle)
        latency_ms = (time.time() - start) * 1000

        # Limit to top_k
        top_results = results[:top_k]

        # Format for testing
        formatted = []
        for node in top_results:
            formatted.append(
                {
                    "id": node.node.node_id,
                    "score": float(node.score),
                    "title": node.node.metadata.get("article_title", ""),
                    "so_ky_hieu": node.node.metadata.get("so_ky_hieu", ""),
                    "retrieval_latency_ms": latency_ms,
                }
            )

        return formatted
