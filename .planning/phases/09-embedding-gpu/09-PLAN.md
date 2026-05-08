# Phase 09 Plan: Hỗ trợ Embedding bằng GPU

**Phase:** 09 — Embedding GPU support
**Milestone:** v3.0 Production Scaling & Resilience
**Status:** PLAN
**Date Created:** 2026-05-08
**Context:** `09-CONTEXT.md`

---

## Executive summary

Cho phép bật/tắt runtime tạo embedding giữa CPU và GPU bằng biến môi trường `EMBEDDING_DEVICE` và `FORCE_DISABLE_CUDA`. Mục tiêu là có fallback an toàn, hướng dẫn Docker/Docker Compose cho GPU, và suite tests để verify cả hai chế độ.

## Scope
- Sửa `core/embeddings.py` và `retrievers/qdrant_retriever.py` để tôn trọng `EMBEDDING_DEVICE`.
- Thêm/ cập nhật Dockerfile(s) và `docker-compose.gpu.yml` để hỗ trợ GPU builds và runtime.
- Thêm unit/integration tests và tài liệu chạy thử.

## Execution steps (waves)

### Wave 1 — Device selection & logging
- Implement ENV-based device selection in `core/embeddings.py`.
- Mirror same selection in `retrievers/qdrant_retriever.py` and pass device hint to embedding wrappers when possible.

### Wave 2 — Requirements & tests
- Update `requirements.txt` notes (ensure sentence-transformers present).
- Add unit tests `tests/test_embeddings_device.py` (mock torch.cuda).

### Wave 3 — Docker & Compose
- Create `Dockerfile.gpu` (CUDA-enabled base) and `docker-compose.gpu.yml` (override) for GPU runs.
- Ensure default `docker-compose.yml` remains safe for CPU.

### Wave 4 — Integration & verification
- Run CPU compose and confirm `/api/v1/test-rag` passes.
- (Optional) Run GPU compose on host with NVIDIA runtime and confirm GPU visible and performance improved.

## Files to edit/create
- Edit: `core/embeddings.py`, `retrievers/qdrant_retriever.py`, `docker-compose.yml`, `.env.example`, `requirements.txt`.
- Create: `Dockerfile.gpu`, `docker-compose.gpu.yml`, `tests/test_embeddings_device.py`, small docs.

## Acceptance criteria
1. App boots in CPU mode and `POST /api/v1/test-rag` returns JSON with `elapsed_ms` and `status: "success"`.
2. On GPU-capable host using GPU compose override, the container sees GPU and logs show device=cuda.
3. Unit tests for device selection pass.

## Risks & mitigations
- Torch/CUDA wheel mismatch: separate GPU Dockerfile and document recommended wheel.
- OOM: recommend small default model and allow FORCE_DISABLE_CUDA.

---

Next steps: implement Wave 1 (code changes) and Wave 2 (unit tests). See `09-VERIFICATION.md` for detailed verification procedure.

