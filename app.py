import json
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from unittest.mock import AsyncMock, MagicMock
# import traceback

import llama_index.core
# from torch.cuda import device

from api.models import HealthResponse
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

# Include Routers
from api.v1.endpoints import router as api_v1
app.include_router(api_v1, prefix="/api/v1", tags=["v1"])

# CORS Configuration
# allowed_origins = _parse_allowed_origins()
app.add_middleware(
    CORSMiddleware,
    # allow_origins=allowed_origins,
    allow_origins=["*"],  # For development; restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", response_model=HealthResponse)
async def health_check():
    return await build_health_status()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, workers=1)
