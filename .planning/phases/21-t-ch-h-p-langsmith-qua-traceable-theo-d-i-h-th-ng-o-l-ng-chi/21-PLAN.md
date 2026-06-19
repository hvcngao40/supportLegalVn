---
wave: 1
depends_on: []
files_modified:
  - core/constants.py
  - .env.example
  - tools/gemini_client.py
  - tools/groq_client.py
  - tools/deepseek_client.py
  - core/rag_pipeline.py
  - api/v1/endpoints.py
  - tests/test_langsmith_integration.py
autonomous: true
---

# Plan: Phase 21 - Tích hợp LangSmith qua @traceable để theo dõi hệ thống

## Goal

Tích hợp LangSmith qua `@traceable` để theo dõi các bước trong các luồng API public (`/ask`, `/stream`, `GET /stream`, `/search-articles`), đo lường chi phí token và tốc độ thực thi, đồng thời duy trì cơ chế fail-safe để không làm gián đoạn API chính nếu xảy ra lỗi kết nối hay thiếu API key.

## Must-Haves
- **M-01 (Phạm vi)**: Tracing toàn bộ API public E2E và các bước con (Query Rewrite, Classifier, Cache, Retrieval, Fusion, Generation).
- **M-02 (Token & Cost)**: Đo lường chính xác token từ API response và tính toán chi phí dựa trên pricing configuration.
- **M-03 (Cache Cost)**: Khi cache hit xảy ra trong Redis, ghi nhận `cache_hit: True` và `token_cost_usd: 0.0` trong metadata.
- **M-04 (Resilience)**: Cơ chế fail-safe bảo vệ hệ thống không bị crash/trả về lỗi 500 khi không có LangSmith key hoặc mất kết nối mạng.
- **M-05 (Toggle)**: Sử dụng biến môi trường tiêu chuẩn `LANGCHAIN_TRACING_V2=true/false` để bật/tắt trace.

---

## Wave 1: Cấu hình và Bảng giá (Constants & Environment Setup)

<task>
<description>Cấu hình biến môi trường & Bảng giá trong Constants</description>
<read_first>
- core/constants.py
- .env.example
</read_first>
<action>
1. Cập nhật `.env.example` với các biến môi trường LangSmith tiêu chuẩn:
   - `LANGCHAIN_TRACING_V2=false`
   - `LANGCHAIN_ENDPOINT="https://api.smith.langchain.com"`
   - `LANGCHAIN_API_KEY=""`
   - `LANGCHAIN_PROJECT="supportlegal"`
2. Cập nhật `core/constants.py` để định nghĩa bảng giá `LLM_PRICING` (USD per 1M tokens) cho các model/provider:
   - Gemini (ví dụ: gemini-2.0-flash input: $0.075, output: $0.30)
   - Groq (llama-3.1-8b-instant: input: $0.05, output: $0.08)
   - DeepSeek (deepseek-chat: input: $0.14, output: $0.28)
3. Implement hàm helper `calculate_token_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> float` trong `core/constants.py` hoặc một file utility tương ứng để tính toán chi phí token dựa trên bảng giá.
</action>
<acceptance_criteria>
- `core/constants.py` chứa cấu trúc bảng giá `LLM_PRICING` và hàm `calculate_token_cost`.
- `.env.example` chứa đầy đủ các biến môi trường LangSmith mẫu.
</acceptance_criteria>
</task>

---

## Wave 2: Tracing LLM Clients & Response Extraction

<task>
<description>Tích hợp @traceable & Đo lường Token cho Client Wrappers</description>
<read_first>
- tools/gemini_client.py
- tools/groq_client.py
- tools/deepseek_client.py
</read_first>
<action>
1. Import `@traceable` từ `langsmith` trong các file client wrappers. Bọc phần import và decorator bằng cơ chế try-except để nếu thư viện không tồn tại hoặc lỗi import, client vẫn chạy bình thường.
2. Decorate các phương thức generate/stream chính như `generate_content_async` và `astream_query` (hoặc các phương thức sinh response tương đương) của `GeminiClient`, `GroqClient`, và `DeepSeekClient` bằng `@traceable`.
3. Trích xuất thông tin token từ Response object:
   - Gemini: `response.usage_metadata`
   - Groq/DeepSeek: `response.usage`
4. Gọi `calculate_token_cost` để tính chi phí và đính kèm token counts + cost vào metadata của LangSmith run (sử dụng context manager `run_tree` hoặc truyền trực tiếp vào metadata).
5. Đảm bảo toàn bộ logic ghi nhận/tracing được bao bọc để catch tất cả exception, ngăn chặn telemetry lỗi làm gián đoạn quá trình gọi LLM.
</action>
<acceptance_criteria>
- Các file `tools/gemini_client.py`, `tools/groq_client.py`, `tools/deepseek_client.py` sử dụng `@traceable` cho các hàm gọi LLM.
- LLM client vẫn hoạt động bình thường khi `LANGCHAIN_TRACING_V2=false` hoặc khi không có API key.
- LangSmith run metadata chứa các trường token usage và calculated cost tương ứng.
</acceptance_criteria>
</task>

---

## Wave 3: Tracing RAG Pipeline & Internal Steps (Sub-spans)

<task>
<description>Decorate RAG Pipeline & Internal Steps</description>
<read_first>
- core/rag_pipeline.py
</read_first>
<action>
1. Decorate phương thức `acustom_query` và `astream_query` trong `core/rag_pipeline.py` bằng `@traceable(name="LegalRAGPipeline.query")`.
2. Tạo các span con (sử dụng `@traceable` hoặc context manager thích hợp) cho từng bước trong pipeline để đo đạc thời gian chạy riêng biệt:
   - Query Rewrite (`arewrite_query`).
   - Classifier step (`retriever.classifier.classify`).
   - Redis Cache check (`redis_manager.vector_search`) và ghi nhận cache hit/miss.
   - Vector Search (`vector_retriever.aretrieve_with_embedding`).
   - SQLite FTS (`fts_retriever.get_articles_by_uuids` hoặc `fts_retriever.aretrieve`).
   - RRF Fusion.
3. Trong `acustom_query` và `astream_query`, nếu trúng Redis cache (cache hit), đính kèm metadata `cache_hit=True` và `token_cost_usd=0.0` vào run hiện tại để biểu thị không mất chi phí LLM. Ngược lại, đính kèm `cache_hit=False`.
</action>
<acceptance_criteria>
- `core/rag_pipeline.py` được bọc bằng `@traceable`.
- LangSmith hiển thị đúng sơ đồ cây (trường con) gồm các bước Classifier, Cache Lookup, Vector Search, và Generation.
- Metadata của run chứa thông tin `cache_hit` chính xác.
</acceptance_criteria>
</task>

---

## Wave 4: Telemetry cho Public API Endpoints & Streams

<task>
<description>Trace API Endpoints and SSE Streams</description>
<read_first>
- api/v1/endpoints.py
</read_first>
<action>
1. Decorate các route handlers trong `api/v1/endpoints.py`: `/ask`, `/stream`, `GET /stream`, và `/search-articles` bằng `@traceable`.
2. Đối với luồng stream (`/stream` và `GET /stream`), bọc hàm generator `_stream_iterator` / `astream_query` bằng traceable span để đo đạc thời gian từ lúc bắt đầu sinh cho tới chunk cuối cùng được truyền đi.
3. Đảm bảo toàn bộ error handling bảo vệ route handlers không bị crash/lỗi 500 do lỗi phát sinh từ LangSmith SDK.
</action>
<acceptance_criteria>
- Các endpoint API public trong `api/v1/endpoints.py` có `@traceable`.
- Luồng streaming SSE chạy mượt mà và được trace đầy đủ trong LangSmith từ chunk đầu đến chunk cuối.
</acceptance_criteria>
</task>

---

## Wave 5: Verification & Testing

<task>
<description>Tạo Integration Tests cho LangSmith Tracing</description>
<read_first>
- conftest.py
</read_first>
<action>
1. Tạo một file test mới `tests/test_langsmith_integration.py`.
2. Viết các test cases để kiểm thử:
   - Các API endpoints hoạt động bình thường khi `LANGCHAIN_TRACING_V2=false`.
   - Hàm `calculate_token_cost` hoạt động chính xác cho các provider.
   - Kiểm tra mock cơ chế fail-safe: giả lập lỗi kết nối LangSmith và đảm bảo API vẫn trả về kết quả 200 thành công.
   - Kiểm tra metadata cache hit: giả lập Redis cache hit và đảm bảo `cache_hit` và `token_cost_usd` được thiết lập đúng trong metadata giả định.
3. Chạy toàn bộ test suite để đảm bảo không có regressions.
</action>
<acceptance_criteria>
- File `tests/test_langsmith_integration.py` được tạo thành công.
- Lệnh chạy test `pytest tests/test_langsmith_integration.py` pass 100%.
</acceptance_criteria>
</task>

---

## Verification

### Automated Tests
- Chạy lệnh test: `pytest tests/test_langsmith_integration.py`
- Chạy toàn bộ unit tests: `pytest`

### Manual Verification
- Thiết lập `LANGCHAIN_TRACING_V2=true` và cấu hình `LANGCHAIN_API_KEY` của môi trường dev.
- Gửi yêu cầu qua endpoint `/ask` và `/stream`.
- Đăng nhập vào LangSmith UI và kiểm tra xem project `supportlegal` có nhận được trace run tương ứng hay không, kiểm tra cấu trúc cây các bước con (sub-spans) và thông tin metadata (token, cost, cache_hit).
- Thử tắt mạng hoặc cấu hình API Key sai để xác minh cơ chế fail-safe.

---

## Artifacts This Phase Produces

### New Files
- `tests/test_langsmith_integration.py`

### Symbols Created/Modified
- `core/constants.py`: `LLM_PRICING`, `calculate_token_cost()`
- `tools/gemini_client.py`: `@traceable` wrapper for generation methods
- `tools/groq_client.py`: `@traceable` wrapper for generation methods
- `tools/deepseek_client.py`: `@traceable` wrapper for generation methods
- `core/rag_pipeline.py`: `@traceable` wrappers and sub-spans for pipeline execution steps
- `api/v1/endpoints.py`: `@traceable` wrappers for router endpoints and generator iterator

---

*Phase: 21-t-ch-h-p-langsmith-qua-traceable-theo-d-i-h-th-ng-o-l-ng-chi*  
*Plan updated: 2026-06-19*
