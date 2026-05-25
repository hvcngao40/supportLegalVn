# Plan: Phase 19 - Redis Cache Deployment

## Goal

Triển khai Redis (Redis Stack) làm cache layer chính để lưu retrieval results và session history, thay thế phần semantic cache không-kp cho Qdrant, giảm độ trễ query và giảm tải cho Qdrant vector search. Không thay đổi contract API — khi LLM generation bị tắt, endpoint chỉ trả về prompt + retrieval context cho FE để redirect tới LLM của người dùng.

**Success Metrics**:
- Query latency giảm 40%+ cho cache hits
- Memory footprint Qdrant giảm 30%+
- Cache hit rate > 60% trong production workload
- All existing tests pass; no regression

## Wave 1: Docker & Redis Infrastructure

- [ ] **Docker Compose Update**: Sử dụng `redis/redis-stack` image để tận dụng vector similarity search (Redis Stack vectors).
  - Configure persistence (RDB/AOF) and memory settings in mounted `redis.conf`.
  - Thêm `maxmemory 2gb` và `maxmemory-policy allkeys-lru` để kiểm soát OOM.
  - Healthcheck: `redis-cli ping` (or `redis-cli -h 127.0.0.1 -p 6379 ping`).

- [ ] **Local Development**: Cập nhật `.env.example` với Redis connection string and control flags
  - `REDIS_HOST=redis` (Docker mode)
  - `REDIS_PORT=6379`
  - `REDIS_DB=0`
  - `REDIS_PASSWORD=` (optional)
  - `ENABLE_LLM_GENERATION=false` (DEFAULT: false — LLM calls disabled by default)

## Wave 2: Python Redis Client & Dependency Injection

- [ ] **Add Dependency**: `pip install redis[hiredis]` into `requirements.txt` (use `redis.asyncio` for async support)

- [ ] **Create Redis Module**: `db/redis.py`
  - `RedisManager` with async methods: `get()`, `set()`, `delete()`, `exists()`, `clear()`, and `vector_search()` wrapping Redis Stack vector ops.
  - Use `redis.asyncio.ConnectionPool(max_connections=50)` and `hiredis` parser where supported.
  - JSON safe serialization for cached retrievals (no pickles).
  - Retry/backoff logic and timeouts (5s default)

- [ ] **Dependency Injection**: Update `api/dependencies.py`
  - Initialize `redis_manager` singleton and inject into FastAPI dependency graph
  - Graceful shutdown on app stop

## Wave 3: RAG Pipeline Cache Integration (Semantic matching)

- [ ] **Semantic Cache Strategy** (DECISION LOCKED):
  - Use Redis Stack vector similarity search (Redis vectors) as the semantic cache store.
  - **Default similarity threshold: High (>0.95)** — very strict by default.
  - **Cache Contents (MINIMAL)**: Only cache retrieval results (list of document ids/snippets and metadata) + session history. **Do NOT cache LLM responses.**

- [ ] **Cache vs Qdrant flow (DECISION LOCKED)**:
  - Perform **cache lookup in parallel with Qdrant vector search** on each query, then compare results. If Redis cache yields a high-confidence match (>=0.95), prefer returning cached retrievals; otherwise use Qdrant results.
  - This parallel approach preserves Qdrant as the source of truth for indexing while allowing faster short-circuit on cache hits.

- [ ] **Query/Key Strategy**:
  - Use Redis vector index for similarity; cache entries store: embedding vector, retrieved doc ids, snippets, created_at, and metadata. Keys organized under `cache:semantic:{uuid}` and vector index mapping.
  - For deterministic lookup, compute the query embedding and run Redis vector similarity query (no naive string hashing for semantics).

- [ ] **Async Support**: Use `redis.asyncio` for non-blocking pipeline integration with FastAPI.

## Wave 4: API Behavior — LLM Interception & Prompt Return (DECISION LOCKED)

- [ ] **LLM Generation Disabled by Default**: Controlled via env var `ENABLE_LLM_GENERATION` (default: `false`). When `false`, the system MUST NOT call any LLM. Instead:
  - Prepare the final RAG prompt (including retrieved docs, citations, and any system instructions) and return it to the client along with retrieval context.
  - Preserve the existing `/ask` API contract surface; behavior controlled by `ENABLE_LLM_GENERATION`. (No new endpoints required.)

- [ ] **Response Format (example)** — when LLM disabled:
```json
{
  "status": "ready_for_llm",
  "prompt": "<pre-built RAG prompt text>",
  "retrievals": [ { "doc_id": "...", "snippet": "...", "score": 0.92 }, ... ],
  "metadata": { "cache_hit": true|false, "used_cache_threshold": 0.95 }
}
```

- [ ] **Client (FE) Responsibility**: Frontend receives `prompt` and may forward it to ChatGPT/Gemini or display for user copy-paste. The backend does not perform LLM quota-consuming calls when disabled.

- [ ] **Config/Control**: Allow overriding per-request via query param `?skip_llm=true` (optional) but default gating is through `ENABLE_LLM_GENERATION` env var.

## Wave 5: Testing & Validation (adjusted)

- [ ] **Unit Tests**: `tests/test_redis_manager.py`
  - Test vector index store and similarity query wrapper
  - Test get/set/delete for retrieval payloads and session history

- [ ] **Integration Tests**: `tests/test_rag_cache_integration.py`
  - Verify parallel cache+qdrant flow and cache preference when threshold met
  - Verify response when `ENABLE_LLM_GENERATION=false` returns `prompt` payload

- [ ] **Performance Tests**: `tests/test_cache_performance.py`
  - Measure cache hit latency (target <10ms)
  - Measure Qdrant memory reduction and overall throughput

- [ ] **Docker Integration Test**:
  - Start docker-compose with Redis Stack
  - Verify app container can perform Redis vector queries
  - Verify healthcheck and persistence across restarts

## Verification (UAT)

- [ ] **Functional**:
  - [ ] Redis Stack service starts with docker-compose
  - [ ] App connects to Redis successfully
  - [ ] Repeated semantically-similar queries (>=0.95) return cached retrievals
  - [ ] `/ask` returns `prompt` + retrievals when LLM disabled

- [ ] **Performance**:
  - [ ] Cache hit latency < 10ms
  - [ ] Memory usage of Qdrant reduced

- [ ] **Resilience**:
  - [ ] App continues if Redis down (fallback to Qdrant)

## Dependencies & Notes

- **Depends on**: Phase 17 (API Gateway) for rate limiting improvements
- **Prepared by**: Phase 18 (Qdrant performance optimization)
- **Rollback**: Use `REDIS_ENABLED=false` or `ENABLE_LLM_GENERATION=true` to revert to full LLM generation in backend

---

*Phase: 19-redis-cache-deployment*  
*Plan updated: 2026-05-24*

