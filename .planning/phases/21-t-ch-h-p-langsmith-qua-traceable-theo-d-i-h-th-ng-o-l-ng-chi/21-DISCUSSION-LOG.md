# Phase 21: Tích hợp LangSmith qua @traceable để theo dõi hệ thống, đo lường chi phí token và tốc độ - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-19
**Phase:** 21-t-ch-h-p-langsmith-qua-traceable-theo-d-i-h-th-ng-o-l-ng-chi
**Areas discussed:** Phạm vi giám sát, Đo lường Token và Chi phí, Cấu hình & Cơ chế Fail-Safe

---

## Phạm vi giám sát

| Option | Description | Selected |
|--------|-------------|----------|
| Giám sát E2E + Chi tiết từng bước con | Classifier, Qdrant/SQLite, RRF, LLM, Redis Cache | ✓ |
| Chỉ giám sát E2E | Chỉ trace request/response của các endpoint | |
| Tùy bạn quyết định | Hệ thống tự động chọn | |

**User's choice:** Giám sát E2E + Chi tiết từng bước con
**Notes:** User wants to monitor the detailed execution of the internal components of the RAG pipeline.

### Giám sát LLM
- **Selected option:** Áp dụng trực tiếp tại các method/hàm gọi API của từng provider (Gemini, Groq, DeepSeek).
- **Notes:** Ensures we capture external API call latency precisely.

### Giám sát Retrieval & Cache
- **Selected option:** Chia nhỏ thành các span riêng biệt: Cache Lookup, Vector Search, Keyword Search, và RRF Fusion.
- **Notes:** Allows easy bottleneck profiling.

### Giám sát Stream
- **Selected option:** Trace hàm generator astream_query / _stream_iterator dưới dạng stream run.
- **Notes:** Measures overall duration of streaming output.

---

## Đo lường Token và Chi phí

| Option | Description | Selected |
|--------|-------------|----------|
| Đọc trực tiếp từ object Response của API | usage_metadata/usage | ✓ |
| Tự động hoàn toàn | Để LangSmith tự phân tích text | |
| Tùy bạn quyết định | Hệ thống tự động chọn | |

**User's choice:** Đọc trực tiếp từ object Response của API
**Notes:** Provides accurate token usage.

### Cấu hình Bảng giá
- **Selected option:** Định nghĩa bảng giá (USD per 1M tokens) trong `core/constants.py` hoặc `.env`.
- **Notes:** Makes it easy to update pricing without modifying model client implementations.

### Cache Hit Pricing
- **Selected option:** Ghi nhận `cache_hit: True` và `token_cost_usd: 0.0` trong metadata.
- **Notes:** Correctly handles cached runs to avoid LLM cost calculation errors.

---

## Cấu hình & Cơ chế Fail-Safe

| Option | Description | Selected |
|--------|-------------|----------|
| Bọc/Xử lý để tự động tắt trace hoặc bỏ qua lỗi LangSmith | Đảm bảo API chính không bao giờ bị gián đoạn hay trả về lỗi 500 | ✓ |
| Raise exception và ghi nhận lỗi nghiêm trọng | Để nhà phát triển phát hiện ngay lập tức | |
| Tùy bạn quyết định | Hệ thống tự động chọn | |

**User's choice:** Bọc/Xử lý để tự động tắt trace hoặc bỏ qua lỗi LangSmith
**Notes:** Public API availability is the highest priority; telemetry should never break production flow.

### Tracing Toggle
- **Selected option:** Sử dụng biến môi trường tiêu chuẩn của LangChain (`LANGCHAIN_TRACING_V2=true/false`).
- **Notes:** Native SDK behavior is preferred.

---

## the agent's Discretion

- Project name config and specific metadata tagging keys (e.g. `session_id`, `provider`) are left to the agent's implementation choice.

## Deferred Ideas

- None.
