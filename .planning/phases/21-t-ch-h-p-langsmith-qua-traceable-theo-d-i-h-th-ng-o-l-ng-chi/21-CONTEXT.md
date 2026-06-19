# Phase 21: Tích hợp LangSmith qua @traceable để theo dõi hệ thống, đo lường chi phí token và tốc độ - Context

**Gathered:** 2026-06-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 21 delivers LangSmith integration via `@traceable` to trace and monitor public FastAPI API endpoints (`/ask`, `/stream`, `GET /stream`, `/search-articles`). It captures detailed sub-step execution latency, token counts, and token costs for Classifier, Vector Search (Qdrant), Keyword Search (SQLite FTS5), RRF Fusion, Redis cache, and LLM Generation.

</domain>

<decisions>
## Implementation Decisions

### Phạm vi giám sát (Granularity & Tracing Scope)
- **D-01:** Giám sát cả luồng API E2E và chi tiết từng bước con trong RAG pipeline:
  - Query Rewrite, Query Classifier.
  - Redis cache lookup/cache hit.
  - Vector Search (Qdrant), Keyword Search (SQLite FTS5), RRF Fusion.
  - LLM Generation (Gemini, Groq, DeepSeek, OpenRouter).
- **D-02:** Sử dụng `@traceable` bọc trực tiếp các API call method của các Client Wrapper (`tools/*_client.py`) để đo lường chính xác latency mạng/API ngoại vi.
- **D-03:** Chia nhỏ các bước truy xuất thành các span riêng biệt trong LangSmith: Cache Lookup, Vector Search, Keyword Search, và RRF Fusion để dễ dàng khoanh vùng các bottleneck về hiệu năng.
- **D-04:** Tracing generator function `_stream_iterator` / `astream_query` dưới dạng stream run giúp LangSmith đo lường chính xác tổng thời gian truyền tải từ chunk đầu tiên đến chunk cuối cùng.

### Đo lường Token và Chi phí (Token & Cost Tracking)
- **D-05:** Đo lường token và chi phí bằng cách lấy thông tin trực tiếp từ API responses (ví dụ: `usage_metadata` từ Gemini, `usage` từ Groq/DeepSeek) và ghi nhận vào LangSmith run metadata/inputs.
- **D-06:** Định nghĩa cấu hình bảng giá của các LLM Provider (USD per 1M tokens) trong `core/constants.py` hoặc `.env` để dễ bảo trì và cập nhật khi nhà cung cấp thay đổi bảng giá.
- **D-07:** Khi cache hit xảy ra trong Redis, ghi nhận `cache_hit: True` và `token_cost_usd: 0.0` trong metadata của run để loại trừ chi phí sinh của LLM.

### Cấu hình & Cơ chế Fail-Safe (Environment & Resilience)
- **D-08:** Bọc các hoạt động của `@traceable` bằng cơ chế fail-safe: tự động tắt trace hoặc catch tất cả lỗi liên quan đến kết nối hoặc thiếu API Key của LangSmith, đảm bảo không bao giờ gây gián đoạn hoặc trả về lỗi 500 cho API public.
- **D-09:** Sử dụng biến môi trường tiêu chuẩn `LANGCHAIN_TRACING_V2=true/false` để tự động bật/tắt trace.

### the agent's Discretion
- Hệ thống tự động quyết định cách đặt tên dự án (LangSmith Project Name) và định dạng metadata tag phù hợp (ví dụ: `project_name="supportlegal"`, tag: `session_id`, `provider`, `query_type`).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### API Endpoints
- [api/v1/endpoints.py](file:///c:/Users/hvcng/PycharmProjects/supportLegalVn/api/v1/endpoints.py) — Defines public API endpoints to trace (`/ask`, `/stream`, `GET /stream`, `/search-articles`).

### Core Logic & Providers
- [core/rag_pipeline.py](file:///c:/Users/hvcng/PycharmProjects/supportLegalVn/core/rag_pipeline.py) — Contains the RAG pipeline execution logic, caching, and generation steps.
- [core/classifier.py](file:///c:/Users/hvcng/PycharmProjects/supportLegalVn/core/classifier.py) — Query Classifier logic.
- [tools/gemini_client.py](file:///c:/Users/hvcng/PycharmProjects/supportLegalVn/tools/gemini_client.py) — Gemini client wrapper.
- [tools/groq_client.py](file:///c:/Users/hvcng/PycharmProjects/supportLegalVn/tools/groq_client.py) — Groq client wrapper.
- [tools/deepseek_client.py](file:///c:/Users/hvcng/PycharmProjects/supportLegalVn/tools/deepseek_client.py) — DeepSeek client wrapper.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `tools/` client wrappers: Already encapsulate LLM provider-specific client initializations and async generate/astream methods.
- `core/security.py`: `llm_circuit_breaker` wraps LLM calls, providing a central place or pattern for resilient execution.

### Established Patterns
- Client wrappers return response objects containing token usage info, which can be extracted.
- Redis integration for cache is already implemented in `core/rag_pipeline.py`.

### Integration Points
- Decorating the methods in `tools/*_client.py` and `core/rag_pipeline.py` with LangSmith `@traceable`.
- Adding LangSmith environment variables to `.env.example`, `.env`, `.env.local`, etc.

</code_context>

<specifics>
## Specific Ideas

- No specific requirements — open to standard approaches.

</specifics>

<deferred>
## Deferred Ideas

- None — discussion stayed within phase scope.

</deferred>

---

*Phase: 21-t-ch-h-p-langsmith-qua-traceable-theo-d-i-h-th-ng-o-l-ng-chi*
*Context gathered: 2026-06-19*
