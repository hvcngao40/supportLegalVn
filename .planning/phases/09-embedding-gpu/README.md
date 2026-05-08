# Phase 09: Embedding GPU Support — Quick Reference

## What's implemented?

- **EMBEDDING_DEVICE env var**: Controls embedding runtime (auto|cpu|cuda)
- **Unit tests**: 7 tests validating device selection logic ✅
- **GPU Docker support**: Dockerfile.gpu + docker-compose.gpu.yml
- **CPU-safe default**: Main docker-compose.yml uses auto-detect (no forcing)

## Run modes

### Local (Python) — CPU mode
```powershell
$env:EMBEDDING_DEVICE = 'cpu'
python app.py
```

### Local (Python) — GPU mode (requires CUDA 12+ on disk)
```powershell
$env:EMBEDDING_DEVICE = 'cuda'
python app.py
```

### Docker — CPU mode (safe on any machine)
```bash
docker compose up --build
```

### Docker — GPU mode (requires NVIDIA Container Toolkit)
```bash
# Install NVIDIA Container Toolkit first:
# https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html

# Option 1: Standalone `api-gpu` only, reusing existing `qdrant` on `legal-network`
docker compose -f docker-compose.gpu.yml up --build

# Option 2: Merge with base compose (for overrides)
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build
```

### GPU API endpoint
- `api-gpu` maps to host port **8001**
- Example: `http://localhost:8001/health`
- Main API vẫn chạy ở `http://localhost:8000`

## Testing

### Unit tests
```bash
pytest tests/test_embeddings_device.py -v
# Result: 7/7 PASSED ✅
```

### Integration test (CPU)
```bash
python tests/integration_compose_cpu.py
# Tests: docker start, health check, /api/v1/test-rag, cleanup
```

## Environment variables

| Var | Values | Example | Notes |
|-----|--------|---------|-------|
| `EMBEDDING_DEVICE` | auto, cpu, cuda, gpu | `auto` (default) | Controls embedding runtime |
| `FORCE_DISABLE_CUDA` | 1/true/yes or empty | (unset) | If set, overrides auto to cpu |

## Files

- `core/embeddings.py` — VietnameseSBERTProvider with device selection
- `retrievers/qdrant_retriever.py` — HuggingFaceEmbedding with device hint
- `Dockerfile.gpu` — CUDA 12.4 + cuDNN9 base image
- `docker-compose.gpu.yml` — standalone `api-gpu` service on port 8001
- `tests/test_embeddings_device.py` — Device selection unit tests
- `tests/integration_compose_cpu.py` — CPU integration test

## Troubleshooting

### "OSError: DLL initialization routine failed" (Windows local)
- Common issue with torch CPU/GPU mismatch
- Ensure virtual environment is clean
- Recommendation: Use Docker for GPU testing

### "NVIDIA Container Toolkit not found"
- GPU Docker requires NVIDIA Container Toolkit
- See installation link above
- Docker Desktop (Mac/Windows) has GPU support built-in if enabled

### GPU not detected
- Verify: `nvidia-smi` runs on host
- Check Dockerfile.gpu matches your CUDA version
- Current default: CUDA 12.4

## Next phase ideas
- Add GPU memory monitoring (OOM alerts)
- Performance benchmarking (GPU vs CPU latency)
- Multi-GPU support (if needed)

