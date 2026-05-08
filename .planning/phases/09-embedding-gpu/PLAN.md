# Phase 09: Hỗ trợ Embedding bằng GPU (EMBEDDING_DEVICE)

Ngày: 2026-05-08

## Mục tiêu ngắn gọn
- Cho phép chạy quá trình tạo embedding trên GPU hoặc CPU theo biến môi trường `EMBEDDING_DEVICE` (giá trị: `auto` | `cpu` | `cuda`).
- Cung cấp fallback an toàn về CPU khi GPU không khả dụng hoặc khi admin ép tắt bằng `FORCE_DISABLE_CUDA`.
- Cập nhật Docker / Docker Compose và phụ thuộc để hỗ trợ chạy local cả hai chế độ (CPU/GPU).

## TL;DR
- Thêm logic lựa chọn device trong `core/embeddings.py` và đồng bộ với `retrievers/qdrant_retriever.py`.
- Cập nhật `requirements.txt` / `Dockerfile` để support cả CPU và GPU builds (sẽ tạo `Dockerfile.gpu` để giữ rõ ràng).
- Thêm `docker-compose.gpu.yml` (override) để chạy với GPU runtime.
- Viết tests (unit + integration) và tài liệu chạy thử (/api/v1/test-rag làm smoke test).

## Giả định
- Host có thể không có GPU (Windows dev thường không), nên default phải an toàn (auto -> cpu khi không có cuda).
- Nếu chạy container trên máy có GPU thì developer sẽ có driver/nvidia-container-toolkit hoặc Docker Desktop hỗ trợ GPU.

## Phạm vi
- Sửa code server để tôn trọng `EMBEDDING_DEVICE` và `FORCE_DISABLE_CUDA`.
- Cập nhật Dockerfile(s) + compose override cho GPU run.
- Thêm tests và tài liệu vận hành.
- KHÔNG: thay đổi model mặc định, không deploy CI GPU runner (tùy chọn sau).

## Chi tiết các bước (high-level)
1. Design (short)
   - ENV vars: `EMBEDDING_DEVICE` (auto|cpu|cuda), `FORCE_DISABLE_CUDA` (optional, truthy để off GPU).
   - Device selection policy: if EMBEDDING_DEVICE==auto -> use cuda if torch.cuda.is_available() and not FORCE_DISABLE_CUDA else cpu; if ==cuda -> try cuda (fail will be reported); if ==cpu -> force cpu.

2. Code changes
   - `core/embeddings.py`:
     - Implement selection logic and clear logging: "Embedding device mode: requested=... -> using device=...".
     - Keep fallback to `SAFE_EMBEDDING_MODEL_NAME` when requested model fails to load.
   - `retrievers/qdrant_retriever.py`:
     - Apply same selection and pass device hint to `HuggingFaceEmbedding` via `model_kwargs={"device": device}` when supported; fallback when constructor signature doesn't accept it.
   - Check other places where embedding models are created (search repo) and make consistent.

3. Dependencies
   - Update `requirements.txt`:
     - Ensure `sentence-transformers` is present (or documented) and keep `torch` unspecified (document recommended torch install per system).
     - Document optional `onnxruntime` vs `onnxruntime-gpu` if using ONNX-based providers.

4. Docker / Compose
   - Create `Dockerfile.gpu` (separate) that uses a CUDA-enabled base image and installs torch-cu wheel matching chosen CUDA.
   - Keep existing `Dockerfile` for CPU builds.
   - Create `docker-compose.gpu.yml` that:
     - Sets build args or uses `Dockerfile.gpu`.
     - Runs service with `--gpus all` / `runtime: "nvidia"` (document host requirements).
   - Update top-level `docker-compose.yml` to NOT force `EMBEDDING_DEVICE=cuda` by default; instead document how to enable GPU via override file or .env.

5. Tests
   - Unit tests:
     - `tests/test_embeddings_device.py` to mock `torch.cuda.is_available()` and verify device selection and fallback.
   - Integration tests (local):
     - Script to run CPU compose and call POST `/api/v1/test-rag` to validate response and elapsed_ms exists.
     - Optional GPU integration script requiring NVIDIA runtime to verify container sees GPU and endpoint returns success faster.

6. Documentation & Rollout
   - Add README snippet with commands to run CPU / GPU locally.
   - Add `.planning/phases/09-embedding-gpu/README-RUN.md` (optional) with troubleshooting tips (drivers, torch wheel, OOM mitigations).

## Files to edit / create
- Edit:
  - `core/embeddings.py` (device selection + logging)
  - `retrievers/qdrant_retriever.py` (HuggingFaceEmbedding device hint)
  - `docker-compose.yml` (remove forced EMBEDDING_DEVICE=cuda; document override)
  - `.env.example` (document EMBEDDING_DEVICE, FORCE_DISABLE_CUDA)
  - `requirements.txt` (add notes / sentence-transformers if missing)
  - `api/v1/endpoints.py` (validate `test-rag` response contract; it already exists)
- Create:
  - `.planning/phases/09-embedding-gpu/PLAN.md` (this file)
  - `Dockerfile.gpu` (CUDA-enabled image)
  - `docker-compose.gpu.yml` (override compose)
  - `tests/test_embeddings_device.py` (unit)
  - `tests/integration_compose_cpu.sh` and `tests/integration_compose_gpu.sh` (or python scripts)
  - `docs/embedding-gpu.md` (run & troubleshooting)

## Acceptance criteria (UAT)
1. CPU mode (default/explicit): app starts and `/api/v1/test-rag` returns JSON with keys `query`, `top_results_count`, `results`, `elapsed_ms`, `status: "success"`.
2. GPU mode: on host with GPU + proper runtime, running with `docker-compose -f docker-compose.yml -f docker-compose.gpu.yml up --build` results in container that can see GPU (you can run `nvidia-smi` inside) and `/api/v1/test-rag` returns success. Server logs should include: "Embedding device mode: requested=cuda -> using device=cuda".
3. Unit tests pass locally (`pytest tests/test_embeddings_device.py`).

## Rủi ro và giảm thiểu
- Image size and torch/CUDA wheel mismatch: giảm thiểu bằng tách GPU Dockerfile và document rõ phiên bản torch+CUDA; không hard-pin wheel trong requirements.
- OOM trên GPU: giới hạn batch_size, recommend model nhỏ cho default, provide FORCE_DISABLE_CUDA env var.
- Host missing driver/runtime: document prerequisites (NVIDIA driver + nvidia-container-toolkit / Docker Desktop GPU support).

## Estimate effort
- Medium — ~3–5 developer-days (design + code + docker + tests + docs).

## Run commands (examples)
- CPU (default):
```powershell
docker compose up --build
```

- GPU (host must support NVIDIA runtime):
```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build
```

## Smoke test (local)
- Call the existing endpoint:
```bash
curl -X POST "http://localhost:8000/api/v1/test-rag" -H "Content-Type: application/json" -d '{"query":"Tội trộm cắp tài sản"}'
```
- Expected: JSON with `elapsed_ms` and `status: "success"`.

## Checklist (taskable)
- [ ] Finalize decision: `Dockerfile.gpu` vs ARG-based single Dockerfile. (Recommendation: `Dockerfile.gpu` separate)
- [ ] Implement code changes (`core/embeddings.py`, `retrievers/qdrant_retriever.py`).
- [ ] Update `requirements.txt` and `.env.example`.
- [ ] Add `Dockerfile.gpu` and `docker-compose.gpu.yml`.
- [ ] Remove forced `EMBEDDING_DEVICE=cuda` from main `docker-compose.yml` (make GPU opt-in).
- [ ] Add unit tests and integration scripts.
- [ ] Run local verification (CPU), document results.
- [ ] (Optional) Run GPU verification on machine with GPU and adjust docs.

---

Nếu bạn muốn, tôi sẽ tiếp tục bằng cách tạo các file thay đổi code và test cơ bản (bắt đầu với `core/embeddings.py` và `tests/test_embeddings_device.py`) theo kế hoạch. Vui lòng xác nhận:
- Có muốn tôi tạo luôn `Dockerfile.gpu` (tôi sẽ dùng pytorch official CUDA image với placeholder cho phiên bản)?
- Hoặc bạn muốn dùng ARG-based single Dockerfile?

