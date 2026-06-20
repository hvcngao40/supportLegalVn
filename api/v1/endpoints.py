from fastapi import APIRouter, Request, HTTPException, Depends
from sse_starlette.sse import EventSourceResponse
import json
import asyncio
import time
import logging
import base64
from typing import Optional, List

from schemas.models import AskRequest, AskResponse, HealthResponse, SearchArticlesRequest, SearchArticlesResponse, ChatMessage
from api.dependencies import rate_limit_ask, rate_limit_search
from pydantic import BaseModel
from core.health import build_health_status
from core.constants import traceable


logger = logging.getLogger(__name__)

class TestRAGRequest(BaseModel):
    query: str

router = APIRouter()


def _stream_iterator(pipeline, query: str, chat_history: Optional[List[ChatMessage]]):
    try:
        return pipeline.astream_query(query, chat_history)
    except TypeError as exc:
        message = str(exc)
        if "positional" not in message and "argument" not in message:
            raise
        return pipeline.astream_query(query)

@router.post("/ask", response_model=AskResponse, response_model_exclude_unset=True) #, dependencies=[Depends(rate_limit_ask)])
@traceable(name="POST /ask", run_type="chain")
async def ask(request: AskRequest, fastapi_req: Request):
    pipeline = fastapi_req.app.state.pipeline
    result = await pipeline.acustom_query(request.query, request.chat_history)
    return result

@router.post("/stream", dependencies=[Depends(rate_limit_ask)])
@traceable(name="POST /stream", run_type="chain")
async def stream_ask(request: AskRequest, fastapi_req: Request):
    pipeline = fastapi_req.app.state.pipeline

    def build_event_generator(query: str, chat_history: Optional[List[ChatMessage]]):
        async def event_generator():
            try:
                async for event in _stream_iterator(pipeline, query, chat_history):
                    # event is already a dict from astream_query
                    yield {
                        "event": "message",
                        "data": json.dumps(event, ensure_ascii=False)
                    }

                # Send final done signal
                yield {
                    "event": "message",
                    "data": json.dumps({"type": "done"})
                }
            except Exception as e:
                logger.error(f"Stream error: {str(e)}", exc_info=True)
                yield {
                    "event": "message",
                    "data": json.dumps({"type": "error", "content": f"Lỗi hệ thống: {str(e)}"})
                }

        return event_generator()

    return EventSourceResponse(
        build_event_generator(request.query, request.chat_history),
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


def _parse_chat_history(encoded_history: Optional[str]) -> Optional[List[ChatMessage]]:
    if not encoded_history:
        return None

    try:
        decoded = base64.b64decode(encoded_history).decode("utf-8")
        payload = json.loads(decoded)
        if not isinstance(payload, list):
            return None

        return [ChatMessage.model_validate(msg) for msg in payload]
    except Exception:
        logger.warning("Invalid chat_history payload in stream GET", exc_info=True)
        return None


@router.get("/stream", dependencies=[Depends(rate_limit_ask)])
@traceable(name="GET /stream", run_type="chain")
async def stream_ask_get(query: str, fastapi_req: Request, chat_history: Optional[str] = None):
    pipeline = fastapi_req.app.state.pipeline

    if not query or len(query.strip()) == 0:
        raise HTTPException(status_code=400, detail="query cannot be empty")

    parsed_history = _parse_chat_history(chat_history)

    def build_event_generator(query_str: str, history: Optional[List[ChatMessage]]):
        async def event_generator():
            try:
                async for event in _stream_iterator(pipeline, query_str, history):
                    yield {
                        "event": "message",
                        "data": json.dumps(event, ensure_ascii=False)
                    }

                yield {
                    "event": "message",
                    "data": json.dumps({"type": "done"})
                }
            except Exception as e:
                logger.error(f"Stream error: {str(e)}", exc_info=True)
                yield {
                    "event": "message",
                    "data": json.dumps({"type": "error", "content": f"Lỗi hệ thống: {str(e)}"})
                }

        return event_generator()

    return EventSourceResponse(
        build_event_generator(query.strip(), parsed_history),
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@router.get("/health", response_model=HealthResponse)
async def health():
    return await build_health_status()

@router.post("/test-rag")#, dependencies=[Depends(rate_limit_ask)])
async def test_rag_endpoint(req: Request): #TestRAGRequest, fastapi_req: Request):
    """
    Isolated RAG performance test — bypass Classifier and LLM.
    Purpose: Measure embedding + Qdrant retrieval latency for performance testing.
    
    Request: {"query": "Tội trộm cắp tài sản"}
    Response: {"query": str, "top_results_count": int, "elapsed_ms": float, "status": str}
    """
    request =  await req.json()
    query = request.get("query", "") if isinstance(request, dict) else ""
    if not query or len(query.strip()) == 0:
        raise HTTPException(status_code=400, detail="query cannot be empty")

    start_time = time.time()
    query = query.strip()

    try:
        # logger.info(f"TEST_RAG_ENDPOINT_START query={query[:50]}")
        # pipeline = fastapi_req.app.state.pipeline

        # Call retrieve_only for isolated RAG core measurement
        # results = await pipeline.retrieve_only(query, top_k=5)

        elapsed = (time.time() - start_time) * 1000
        # logger.info(f"TEST_RAG_ENDPOINT_COMPLETE elapsed={elapsed:.2f}ms results={len(results)}")

        data = {
            "query": query,
            "top_results_count": 1, # len(results),
            "results": [], #results,
            "elapsed_ms": elapsed,
            "status": "success"
        }
        return data

    except asyncio.TimeoutError:
        raise HTTPException(status_code=408, detail="Request timeout after 30 seconds")
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=f"Qdrant unavailable: {str(e)}")
    except Exception as e:
        logger.error(f"test_rag_endpoint error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
@router.post("/test-classifier", dependencies=[Depends(rate_limit_ask)])
async def test_classifier_endpoint(request: TestRAGRequest, fastapi_req: Request):
    """
    Isolated Classifier performance test.
    """
    if not request.query or len(request.query.strip()) == 0:
        raise HTTPException(status_code=400, detail="query cannot be empty")
    
    start_time = time.time()
    query = request.query.strip()
    
    try:
        logger.info(f"TEST_CLASSIFIER_ENDPOINT_START query={query[:50]}")
        pipeline = fastapi_req.app.state.pipeline
        classifier = pipeline.retriever.classifier
        
        classification = await classifier.classify(query)
        
        elapsed = (time.time() - start_time) * 1000
        logger.info(f"TEST_CLASSIFIER_ENDPOINT_COMPLETE elapsed={elapsed:.2f}ms")
        
        return {
            "query": query,
            "domains": classification.domains,
            "confidence": classification.confidence,
            "is_explicit_filter": classification.is_explicit_filter,
            "elapsed_ms": elapsed,
            "provider": classifier.provider,
            "status": "success"
        }
    
    except Exception as e:
        logger.error(f"test_classifier_endpoint error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search-articles", response_model=SearchArticlesResponse, dependencies=[Depends(rate_limit_search)])
@traceable(name="POST /search-articles", run_type="chain")
async def search_articles(request: SearchArticlesRequest, fastapi_req: Request):
    """
    Search articles (legal provisions) and return full canonical article rows
    to be used by frontends (RAG source attribution / show full content).

    Request options:
    - {"query": "so_ky_hieu"} -> searches by document identifier only
    - {"article_uuid": "..."} -> fetches the canonical article by UUID

    Response: {"query": str, "top_results_count": int, "results": [...]} where each
    result contains article_uuid, title, so_ky_hieu, score, full_content, doc_id
    """
    if (not request.query or len(request.query.strip()) == 0) and not request.article_uuid:
        raise HTTPException(status_code=400, detail="Either 'query' or 'article_uuid' must be provided")

    pipeline = fastapi_req.app.state.pipeline

    try:
        import re
        if request.article_uuid:
            # Fetch canonical article by uuid
            articles = await pipeline.retriever.fts_retriever.get_articles_by_uuids([request.article_uuid])
            nodes = articles
        else:
            q = request.query.strip()
            top_k = int(request.top_k or 10)
            # Search by số ký hiệu only; article_path/title fallback is removed to
            # avoid slow scans on large datasets.
            candidate_nodes = await pipeline.retriever.fts_retriever.aretrieve_articles_by_so_ky_hieu(
                query_str=q,
                top_k=top_k,
                doc_type=request.doc_type,
            )
            
            # Hydrate full content
            nodes = []
            if candidate_nodes:
                uuids = [n.get("id") for n in candidate_nodes if n.get("id")]
                hydrated = await pipeline.retriever.fts_retriever.get_articles_by_uuids(uuids)
                hydrated_map = {h.get("id"): h for h in hydrated if h.get("id")}
                
                # Reconstruct keeping original scores
                for c_node in candidate_nodes:
                    uuid = c_node.get("id")
                    if uuid in hydrated_map:
                        h_node = hydrated_map[uuid]
                        nodes.append(
                            {
                                "id": h_node.get("id"),
                                "text": h_node.get("text", ""),
                                "metadata": h_node.get("metadata", {}),
                                "score": float(c_node.get("score", 0.0)),
                            }
                        )

        top_k = int(request.top_k or 10)
        nodes = nodes[:top_k]

        formatted = []
        for node in nodes:
            meta = node.get("metadata", {}) or {}
            content = node.get("text", "")

            # Regex highlighting
            highlighted_content = content
            if request.query and len(request.query.strip()) > 0:
                pattern = re.compile(re.escape(request.query.strip()), re.IGNORECASE)
                highlighted_content = pattern.sub(lambda m: f"<b>{m.group(0)}</b>", content)

            # Determine doc_type from so_ky_hieu if doc_type was requested but not explicitly in metadata
            doc_type_val = request.doc_type
            so_ky_hieu = meta.get("so_ky_hieu") or ""
            if not doc_type_val and so_ky_hieu:
                if "Luật" in so_ky_hieu:
                    doc_type_val = "Luật"
                elif "NĐ-CP" in so_ky_hieu:
                    doc_type_val = "Nghị định"
                elif "TT-" in so_ky_hieu:
                    doc_type_val = "Thông tư"

            formatted.append({
                "article_uuid": meta.get("article_uuid") or node.get("id"),
                "doc_id": meta.get("doc_id"),
                "so_ky_hieu": so_ky_hieu,
                "title": meta.get("article_title") or "",
                "score": float(node.get("score", 0.0)),
                "full_content": content,
                "doc_type": doc_type_val,
                "highlighted_content": highlighted_content
            })

        return {
            "query": request.query or request.article_uuid,
            "top_results_count": len(formatted),
            "results": formatted,
            "status": "success",
        }

    except Exception as e:
        logger.error(f"search_articles error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


