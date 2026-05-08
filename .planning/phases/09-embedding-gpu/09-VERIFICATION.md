# Phase 09 Verification

## Verification checklist

Wave 1 — Device selection & logging
- [ ] Start app with `EMBEDDING_DEVICE=auto` on a non-GPU host: logs show using device=cpu and app boots.
- [ ] Start app with `EMBEDDING_DEVICE=cpu`: logs show using device=cpu.
- [ ] Start app with `EMBEDDING_DEVICE=cuda` on a GPU host (or with FORCE_DISABLE_CUDA unset): logs show requested=cuda -> using device=cuda.

Wave 2 — Unit tests
- [ ] `pytest tests/test_embeddings_device.py` passes locally (mock torch.cuda.is_available variations).

Wave 3 — Integration
- [ ] CPU: `docker compose up --build` runs, call `POST /api/v1/test-rag` returns `status: "success"` and `elapsed_ms` numeric.
- [ ] GPU (optional): `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build` on GPU host runs, container can run `nvidia-smi`, POST /api/v1/test-rag returns success, and logs indicate cuda device.

Performance expectations (example)
- GPU run should generally reduce embedding latency; set local benchmark thresholds after initial runs.

Failure modes & remediation
- If model load fails on cuda, fall back to SAFE_EMBEDDING_MODEL_NAME and log error.
- If compose GPU fails due to driver, document steps to install NVIDIA Container Toolkit and recommended Docker Desktop settings.

