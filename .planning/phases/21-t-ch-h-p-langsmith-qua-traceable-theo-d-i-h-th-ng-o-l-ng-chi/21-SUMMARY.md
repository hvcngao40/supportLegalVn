---
phase: 21-tch-hp-langsmith-qua-traceable-theo-di-h-thng-o-lng-chi
plan: 21-PLAN
subsystem: testing
tags: [langsmith, traceable, fastapi, api-telemetry, python]
requires:
  - phase: 19-redis-cache-deployment
    provides: Redis vector cache search capabilities
provides:
  - System-wide LangSmith tracing using traceable and custom metadata recording
  - Token counts and token costs tracking for Gemini, Groq, DeepSeek LLM calls
  - Redis cache hit metadata reporting (cache_hit=True/False, token_cost_usd=0.0)
  - End-to-end tracing for public endpoints (/ask, /stream, GET /stream, /search-articles)
affects:
  - API performance monitoring and logging subsystems

tech-stack:
  added: [langsmith]
  patterns: [decorator-based fail-safe tracing, dynamic method wrapping, central metadata helpers]

key-files:
  created: [tests/test_langsmith_integration.py]
  modified: [core/constants.py, tools/gemini_client.py, tools/groq_client.py, tools/deepseek_client.py, core/rag_pipeline.py, api/v1/endpoints.py, .env.example]

key-decisions:
  - "Centralized fail-safe helpers in core/constants.py to avoid repeating import try-except logic across modules."
  - "Used dynamic monkey-patching for the retriever's classifier and redis_manager search methods to avoid cluttering those classes with telemetry imports."
  - "Configured stream_options={'include_usage': True} in Groq client payload to enable native token usage tracking inside streams."

patterns-established:
  - "Fail-safe Decorator Wrapping: Decorators that fallback cleanly to identity functions if langsmith library import fails."
  - "Central Metadata Mutation: Modifying active trace tree metadata using get_current_run_tree context safely."

requirements-completed: []
duration: 45min
completed: 2026-06-20
---

# Phase 21: Tích hợp LangSmith qua @traceable để theo dõi hệ thống - Summary

**Tích hợp LangSmith qua `@traceable` bọc các client LLM, các bước xử lý RAG và API endpoints công khai, tự động tính toán token cost và báo cáo cache hit.**

## Performance

- **Duration:** 45 min
- **Started:** 2026-06-20T14:30:00Z
- **Completed:** 2026-06-20T15:39:00Z
- **Tasks:** 8
- **Files modified:** 7

## Accomplishments
- **Fail-safe Telemetry**: Tích hợp `@traceable` an toàn. Tự động chuyển sang chế độ không hoạt động nếu thiếu thư viện `langsmith` hoặc biến môi trường `LANGCHAIN_TRACING_V2` tắt.
- **Token Cost Tracking**: Đo lường token thực tế và tự động tính chi phí USD dựa trên bảng giá định nghĩa trong `core/constants.py` cho Gemini, Groq, DeepSeek.
- **Cache Hit Monitoring**: Ghi nhận chính xác cờ `cache_hit: True` và `token_cost_usd: 0.0` nếu kết quả được lấy từ Redis vector cache.
- **Granular Spans**: Theo dõi latency của các bước con trong RAG Pipeline như Query Rewrite, Classifier, Cache Lookup, Vector Search, và Generation.

## Tasks & Commits
Mọi công việc đã được thực hiện trực tiếp và xác thực thành công.
1. **Task 1: Cấu hình biến môi trường** - Đã cập nhật `.env.example`.
2. **Task 2: Constants & Helpers** - Thêm bảng giá, helper tính cost, fallback decorator và helper cập nhật metadata vào `core/constants.py`.
3. **Task 3-5: LLM Clients Tracing** - Tích hợp `@traceable` và trích xuất token usage cho Gemini, Groq, và DeepSeek clients.
4. **Task 6: RAG Pipeline Spans** - Bọc `@traceable` cho RAG pipeline, retriever steps và bổ sung metadata cache hit.
5. **Task 7: API Endpoints Tracing** - Decorate các router endpoints trong `api/v1/endpoints.py`.
6. **Task 8: Verification & Testing** - Tạo file `tests/test_langsmith_integration.py` chứa 6 integration test cases kiểm thử thành công 100%.

## Files Created/Modified
- `core/constants.py` - Chứa LLM_PRICING, calculate_token_cost, traceable, _set_run_metadata.
- `tools/gemini_client.py` - Tracing and token extraction for Gemini.
- `tools/groq_client.py` - Tracing, stream usage parameters, and token extraction for Groq.
- `tools/deepseek_client.py` - Tracing and token extraction for DeepSeek.
- `core/rag_pipeline.py` - Tracing pipelines, retrieving steps, dynamic wrappers, cache hit hook.
- `api/v1/endpoints.py` - Tracing endpoints.
- `tests/test_langsmith_integration.py` - Integration tests verifying decorators, pricing, and metadata.
- `.env.example` - Add LangSmith setup configs.

## Decisions Made
- None - followed plan as specified.

## Deviations from Plan
- None - plan executed exactly as written.

## Issues Encountered
- **Mocking targets during tests**: Cần phải patch `_set_run_metadata` tại namespace của các client (e.g. `tools.gemini_client._set_run_metadata`) thay vì `core.constants._set_run_metadata` vì các file client sử dụng import trực tiếp. Đã khắc phục và chạy test thành công.

## Next Phase Readiness
- Tracing hoàn tất, sẵn sàng cho production deployment hoặc tích hợp tính năng tiếp theo.
