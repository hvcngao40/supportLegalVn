# Phase 19: Redis Cache Deployment - Context

**Gathered:** 2026-05-24  
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase này tập trung vào việc triển khai Redis làm cache layer chính, thay thế phần đáng kể của Qdrant semantic cache, để cải thiện độ trễ và độ bền của hệ thống. Redis sẽ xử lý:
- Query result caching (high-frequency queries)
- Session management
- Rate limit tracking
- LLM response cache (non-semantic)

Qdrant vẫn được giữ lại cho vector search và semantic operations.
</domain>

<decisions>
## Implementation Decisions

### 1. Redis Purpose & Scope (LOCKED)
- **Mục đích chính**: Dùng Redis (Redis Stack) làm semantic cache cho retrieval results và lưu session history. **Không** cache LLM responses.
- **Cache Contents (MINIMAL)**:
  - Retrievals: list of `doc_id`, `snippet`, `score`, `source` và các metadata cần thiết
  - Session history: `session:{session_id}` (TTL: 7 days)
  - **Không lưu**: LLM-generated responses (user requested to manage LLM externally)

### 2. Semantic Matching Strategy (LOCKED)
- **Mechanism**: Use Redis Stack's vector similarity search (Redis vectors) — compute query embedding and run Redis vector similarity lookup.
- **Default Similarity Threshold**: High (>0.95). This is the default; can be made configurable later.

### 3. Cache vs Qdrant Flow (LOCKED)
- **Execution**: Run Redis cache lookup in parallel with Qdrant vector search for each incoming query. Compare results; if Redis returns a match meeting threshold (>=0.95), prefer Redis retrievals; otherwise use Qdrant's results.
- **Rationale**: preserves Qdrant as primary index while allowing fast short-circuit on strict semantic cache hits.

### 4. LLM Calls & Prompt Return (LOCKED)
- **Behavior**: All backend LLM generation calls are disabled by default. Backend will prepare the final RAG prompt and return it to client instead of calling any LLM.
- **Control**: Environment variable `ENABLE_LLM_GENERATION=false` (DEFAULT: false). When set to `true`, backend resumes calling configured LLM providers.
- **API Contract**: Do not add new endpoints solely for this behavior. Existing `/ask` will return a structured payload containing `prompt` and `retrievals` when LLM generation is disabled.

### 5. Integration Points
- **API Layer**: `api/dependencies.py` — initialize `RedisManager` and expose via DI
- **RAG Pipeline**: `core/rag_pipeline.py` — run cache lookup in parallel with Qdrant, produce prompt and return when LLM disabled
- **Health Checks**: Add Redis check to `/health` reporting `connected`/`disconnected` and basic memory stats

### 6. Docker / Infra
- **Redis Image**: Use `redis/redis-stack:latest` (or pinned tag) to support vector operations
- **Persistence & Memory**: RDB/AOF as configured, `maxmemory 2gb`, `maxmemory-policy allkeys-lru`

### 7. Client Configuration & Safety
- **Library**: `redis.asyncio` + `hiredis` where appropriate
- **Serialization**: JSON for retrieval payloads (no pickle)
- **Timeouts/Retry**: 5s operation timeout, exponential backoff retries

</decisions>

<canonical_refs>
## Canonical References

- `docker-compose.yml` — Redis service configuration
- `docker-compose.gpu.yml` — GPU variant configuration  
- `api/dependencies.py` — Redis client initialization
- `core/rag_pipeline.py` — RAG pipeline caching logic
- `api/v1/health.py` — Health check endpoints
- `requirements.txt` — Dependency management
- `scripts/redis_migration.py` — Migration helper (if needed)

</canonical_refs>

<specifics>
## Specific Ideas

- **Query Hash**: MD5(query_text + filters) để consistent cache keys
- **Warm-up**: Có thể pre-populate cache từ Phase 18 Qdrant semantic cache
- **Monitoring**: Sử dụng redis-py metics hay redis_exporter cho Prometheus
- **Testing**: Integration tests đủ bao gồm cache hit/miss scenarios

</specifics>

<deferred>
## Deferred Ideas

- Cluster mode Redis (multi-node) — dành cho Milestone v3.1+
- Sentinel high availability — khi có SLA requirement
- Redis Streams cho event sourcing — out of scope v3.0

</deferred>

---
*Phase: 19-redis-cache-deployment*  
*Context gathered: 2026-05-24*

