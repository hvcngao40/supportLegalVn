# Phase 09 Context: Hỗ trợ Embedding bằng GPU

Mục tiêu ngắn gọn:

- Cho phép chạy quá trình tạo embedding trên GPU hoặc CPU theo biến môi trường `EMBEDDING_DEVICE` (auto|cpu|cuda).
- Cung cấp fallback an toàn về CPU khi GPU không khả dụng hoặc khi admin ép tắt bằng `FORCE_DISABLE_CUDA`.

Lý do:

- Một số môi trường phát triển/triển khai có GPU và muốn tận dụng để giảm latency embedding.
- Cần một cách bật/tắt rõ ràng (env var) để so sánh CPU vs GPU ở môi trường test local và production.

Hiện trạng:

- Codebase đã có `core/embeddings.py` và `retrievers/qdrant_retriever.py` tạo model embedding.
- Đã thêm một bản nháp kế hoạch (`PLAN.md`) nhưng chưa theo cấu trúc GSD chuẩn (09-*.md files).

Liên kết tham khảo:

- `.planning/ROADMAP.md` — roadmap chính
- `docker-compose.yml` — compose hiện tại (đã thêm EMBEDDING_DEVICE trong env khi thử trước)

