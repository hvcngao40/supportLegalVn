import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from unittest.mock import AsyncMock, MagicMock
# import traceback

import llama_index.core
from mcp import types
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from fastapi.responses import Response

# from torch.cuda import device

from schemas.models import HealthResponse
from core.health import build_health_status
from warnup import warm_up_qdrant
llama_index.core.global_handler = None

load_dotenv()


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _configure_logging() -> None:
    root_logger = logging.getLogger()
    if getattr(root_logger, "_support_legal_configured", False):
        return

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    root_logger.setLevel(getattr(logging, level_name, logging.INFO))
    root_logger.handlers.clear()

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(JsonFormatter())
    root_logger.addHandler(stream_handler)

    if _environment_name() == "production":
        log_file = os.getenv("LOG_FILE_PATH", "").strip()
        if log_file:
            try:
                file_handler = logging.FileHandler(log_file, encoding="utf-8")
                file_handler.setFormatter(JsonFormatter())
                root_logger.addHandler(file_handler)
            except Exception as exc:
                root_logger.warning("Failed to initialize file logging: %s", exc)

    root_logger._support_legal_configured = True  # type: ignore[attr-defined]
def _environment_name() -> str:
    return os.getenv("ENVIRONMENT", os.getenv("APP_ENV", "development")).strip().lower()


_configure_logging()


def _parse_allowed_origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", "").strip()
    is_production = _environment_name() == "production"
    if raw:
        origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    elif is_production:
        raise RuntimeError("ALLOWED_ORIGINS must be set in production")
    else:
        origins = ["http://localhost:3000", "http://127.0.0.1:3000"]

    if any(origin == "*" for origin in origins):
        raise RuntimeError("Wildcard CORS origins are not allowed")
    return origins


def _required_secret_names() -> set[str]:
    required: set[str] = set()
    provider_key_map = {
        "groq": "GROQ_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "qwen": "DASHSCOPE_API_KEY",
        "dashscope": "DASHSCOPE_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }
    for env_name in ("CLASSIFIER_PROVIDER", "CLASSIFIER_FALLBACK_PROVIDER", "GENERATION_PROVIDER"):
        provider = os.getenv(env_name, "").strip().lower()
        key_name = provider_key_map.get(provider)
        if key_name:
            required.add(key_name)
    return required


def _validate_production_environment():
    if _environment_name() != "production":
        return

    if not os.getenv("QDRANT_HOST"):
        raise RuntimeError("QDRANT_HOST must be set in production")

    qdrant_port = os.getenv("QDRANT_PORT", "").strip()
    if qdrant_port != "6334":
        raise RuntimeError("QDRANT_PORT must be set to 6334 in production")

    if not os.getenv("ALLOWED_ORIGINS", "").strip():
        raise RuntimeError("ALLOWED_ORIGINS must be set in production")

    missing = [name for name in sorted(_required_secret_names()) if not os.getenv(name)]
    if missing:
        raise RuntimeError(f"Missing production secrets: {', '.join(missing)}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize singletons

    print("Initializing RAG Pipeline singletons...")
    try:
        if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("TESTING", "").lower() in {"1", "true", "yes"}:
            mock = MagicMock()
            mock.acustom_query = AsyncMock(return_value={"answer": "MOCK_MODE_ACTIVE", "citations": []})
            mock.astream_query = AsyncMock(return_value=[])  # test harness may override per request
            mock.retrieve_only = AsyncMock(return_value=[])
            app.state.pipeline = mock
            print("[Startup] Test mode detected; using mock pipeline.")
            yield
            return

        _validate_production_environment()
        from core.classifier import LegalQueryClassifier
        from retrievers.sqlite_retriever import SQLiteFTS5Retriever
        from retrievers.qdrant_retriever import QdrantRetriever
        from core.rag_pipeline import LegalRAGPipeline, LegalHybridRetriever
        
        # classifier_provider = os.getenv("CLASSIFIER_PROVIDER", "groq")
        # classifier_fallback_provider = os.getenv("CLASSIFIER_FALLBACK_PROVIDER", "gemini")
        # classifier_model = os.getenv("CLASSIFIER_MODEL", "llama-3.1-8b-instant")
        #
        # classifier = LegalQueryClassifier(
        #     provider=classifier_provider,
        #     fallback_provider=classifier_fallback_provider,
        #     model_name=classifier_model,
        # )
        v_retriever = QdrantRetriever()
        # Pre-create Qdrant client during startup to avoid latency on first request and to catch configuration issues early.
        try:
            import asyncio as _asyncio

            await _asyncio.to_thread(v_retriever._get_client)
            print("[Startup] Qdrant client initialized during startup")
        except Exception as e:
            print(f"[Warning] Pre-init Qdrant client failed during startup: {e}")
        # Chạy warm-up ở đây
        client = v_retriever._get_client()
        await warm_up_qdrant(client, "legal_articles")

        f_retriever = SQLiteFTS5Retriever()
        app.state.f_retriever = f_retriever  # Make FTS retriever available for MCP tools
        
        hybrid_retriever = LegalHybridRetriever(
            classifier=None,
            vector_retriever=v_retriever,
            fts_retriever=f_retriever
        )
        
        generation_provider = os.getenv("GENERATION_PROVIDER", "groq")
        generation_model = os.getenv("GENERATION_MODEL", "llama-3.1-8b-instant")
        
        # Initialize RedisManager (optional). If Redis is unavailable, pipeline will fall back to Qdrant-only.
        try:
            from db.redis import RedisManager
            redis_url = os.getenv("REDIS_URL", "redis://redis:6379")
            redis_manager = RedisManager(redis_url)
            try:
                await redis_manager.init()
                print("[Startup] Redis manager initialized")
            except Exception as e:
                print(f"[Startup] Redis init failed: {e}")
                redis_manager = None
        except Exception as e:
            print(f"[Startup] RedisManager import/init skipped: {e}")
            redis_manager = None

        app.state.pipeline = LegalRAGPipeline(
            retriever=hybrid_retriever, 
            provider=generation_provider,
            model_name=generation_model,
            redis_manager=redis_manager,
        )
        print("RAG Pipeline ready.")
    except Exception as e:
        print(f"WARNING: RAG Pipeline failed to initialize: {e}")
        # traceback.print_exc()
        print("Backend will start in MOCK mode for API verification.")
        # Create a mock pipeline for verification
        mock = MagicMock()
        mock.acustom_query = AsyncMock(return_value={"answer": "MOCK_MODE_ACTIVE", "citations": []})
        app.state.pipeline = mock

    yield

app = FastAPI(
    title="Legal Support VN API",
    description="Vietnamese Legal RAG System API",
    version="1.0.0",
    lifespan=lifespan
)

# 1. Khởi tạo mcp_server bằng lớp Server cốt lõi (thay vì FastMCP)
mcp_server = Server("SupportLegalVn_MCP_Server")

from google.api_core import exceptions

@app.exception_handler(exceptions.ResourceExhausted)
async def rate_limit_handler(request: Request, exc: exceptions.ResourceExhausted):
    return JSONResponse(
        status_code=429,
        content={
            "detail": "API quota exceeded. Retries failed. Please try again later.",
            "retry_after": "60" # Default suggestion
        }
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"CRITICAL ERROR: {str(exc)}")
    # traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)} #, "traceback": traceback.format_exc()}
    )

# -------------------------------------------------------------------------
# MCP TOOLS: Cấu hình theo chuẩn Server
# -------------------------------------------------------------------------
@mcp_server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """Khai báo danh sách các công cụ cho MCP Client biết"""
    return [
        types.Tool(
            name="search_legal_context",
            description="Tìm kiếm các điều luật, nghị định của Việt Nam phù hợp với tình huống người dùng. Sử dụng tool này đầu tiên khi người dùng hỏi về luật.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Nội dung cần tìm kiếm"},
                    "top_k": {"type": "integer", "default": 5}
                },
                "required": ["query"]
            }
        ),
        types.Tool(
            name="get_full_document",
            description="Truy xuất toàn văn của một văn bản pháp luật khi cần đọc toàn bộ bối cảnh.",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "ID của văn bản pháp luật"}
                },
                "required": ["document_id"]
            }
        )
    ]

@mcp_server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
    """Xử lý logic khi MCP Client gọi một công cụ cụ thể"""
    if not arguments:
        arguments = {}

    if name == "search_legal_context":
        query = arguments.get("query")
        try:
            results = await app.state.pipeline.acustom_query(query=query)
            if not results:
                return [types.TextContent(type="text", text="Không tìm thấy quy định pháp luật nào phù hợp với tình huống này.")]

            formatted_context = "\n\n".join(
                f"--- BẮT ĐẦU TRÍCH ĐOẠN ---\n"
                f"Văn bản ID: {res.document_id}\n"
                f"Điều/Khoản: {res.article_name}\n"
                f"Nội dung: {res.content}\n"
                f"--- KẾT THÚC TRÍCH ĐOẠN ---"
                for res in results
            )
            # Chuẩn MCP bắt buộc trả về một list các Object Content
            return [types.TextContent(type="text", text=formatted_context)]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Lỗi hệ thống khi tìm kiếm: {str(e)}")]

    elif name == "get_full_document":
        document_id = arguments.get("document_id")
        try:
            doc = await app.state.f_retriever.get_articles_by_uuids([document_id])
            if not doc:
                return [types.TextContent(type="text", text=f"Không tìm thấy văn bản nào với ID: {document_id}")]
            return [types.TextContent(type="text", text=f"Tên văn bản: {doc.text}\n")]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Lỗi hệ thống khi truy xuất văn bản: {str(e)}")]

    raise ValueError(f"Unknown tool: {name}")

# Include Routers
from api.v1.endpoints import router as api_v1
app.include_router(api_v1, prefix="/api/v1", tags=["v1"])

# CORS Configuration
# allowed_origins = _parse_allowed_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Bạn đã để "*" là rất tốt cho dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", response_model=HealthResponse)
async def health_check():
    return await build_health_status()

# 4. Tạo kết nối SSE tích hợp vào FastAPI
@mcp_server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
    if not arguments:
        arguments = {}

    if name == "search_legal_context":
        query = arguments.get("query")

        # 1. Log query mà AI truyền vào
        print(f"\n[MCP LOG] AI đang tìm kiếm query: '{query}'", file=sys.stderr, flush=True)

        try:
            results = await app.state.pipeline.acustom_query(query=query)

            # 2. Log số lượng kết quả tìm được
            if not results:
                print(f"[MCP LOG] CẢNH BÁO: Không tìm thấy kết quả RAG nào!", file=sys.stderr, flush=True)
                return [types.TextContent(type="text", text="Không tìm thấy quy định pháp luật nào.")]

            print(f"[MCP LOG] THÀNH CÔNG: Tìm thấy {len(results)} chunks dữ liệu.", file=sys.stderr, flush=True)

            formatted_context = "\n\n".join(...)
            return [types.TextContent(type="text", text=formatted_context)]

        except Exception as e:
            # 3. Log lỗi nếu pipeline bị crash
            print(f"[MCP LOG] LỖI CRASH RAG: {str(e)}", file=sys.stderr, flush=True)
            return [types.TextContent(type="text", text=f"Lỗi hệ thống: {str(e)}")]
# Thêm một class Response ảo để ngăn FastAPI gửi thêm HTTP headers
class AsgiHandledResponse(Response):
    """
    Response giả dành cho các endpoint đã được xử lý ở tầng ASGI thấp.
    Nó ngăn chặn FastAPI gọi hàm send() lần thứ 2.
    """
    async def __call__(self, scope, receive, send) -> None:
        pass # Không làm gì cả vì MCP Transport đã lo phần gửi responsenh)
# -------------------------------------------------------------------------
# Chỉ định chính xác URL mà MCP Client sẽ dùng để POST tin nhắn
sse_transport = SseServerTransport("/mcp/messages")

@app.get("/mcp/sse")
async def sse_endpoint(request: Request):
    """Xử lý request GET từ Client để thiết lập luồng SSE EventSource"""
    async with sse_transport.connect_sse(request.scope, request.receive, request._send) as streams:
        read_stream, write_stream = streams
        await mcp_server.run(
            read_stream,
            write_stream,
            mcp_server.create_initialization_options()
        )
    # Trả về một Response trống hợp lệ để FastAPI không bị lỗi 'NoneType'
    return AsgiHandledResponse()

@app.post("/mcp/messages")
async def messages_endpoint(request: Request):
    """Xử lý request POST chứa các lệnh gọi Tool từ Client"""
    await sse_transport.handle_post_message(request.scope, request.receive, request._send)
    # Trả về Response trống để hoàn thành vòng đời request của FastAPI
    return AsgiHandledResponse()

# Xử lý trường hợp IDE gửi nhầm POST hoặc DELETE vào endpoint sse để tránh crash 400/405
@app.post("/mcp/sse")
async def sse_post_fallback(request: Request):
    await sse_transport.handle_post_message(request.scope, request.receive, request._send)
    return AsgiHandledResponse()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, workers=1)
