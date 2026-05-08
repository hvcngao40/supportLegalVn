# Phase 09 — Build & Run Quick Start

## Prerequisites
- Docker with GPU support (NVIDIA Container Toolkit or Docker Desktop GPU enabled)
- Old stack running: `docker compose up -d` (for qdrant on legal-network)

## Start ai-gpu for Testing

```bash
# Option 1: BuildKit build (Fast, with cache)
DOCKER_BUILDKIT=1 docker compose -f docker-compose.gpu.yml build
docker compose -f docker-compose.gpu.yml up

# Option 2: Standard build
docker compose -f docker-compose.gpu.yml up --build

# Option 3: Detached mode (background)
docker compose -f docker-compose.gpu.yml up -d --build
```

## Test the Service

```bash
# Check health
curl http://localhost:8001/health

# Test RAG endpoint (GPU mode)
curl -X POST http://localhost:8001/api/v1/test-rag \
  -H "Content-Type: application/json" \
  -d '{"query":"Tội trộm cắp tài sản"}'

# Compare with CPU version (old API)
curl -X POST http://localhost:8000/api/v1/test-rag \
  -H "Content-Type: application/json" \
  -d '{"query":"Tội trộm cắp tài sản"}'
```

## Verify GPU is Being Used

```bash
# Inside the container
docker exec legal-api-gpu nvidia-smi

# Or check logs for GPU mode
docker logs legal-api-gpu | grep "Embedding device mode"
# Should see: "Embedding device mode: requested=cuda -> using device=cuda"
```

## Stop

```bash
docker compose -f docker-compose.gpu.yml down
```

## If Build Fails

See file: `.planning/phases/09-embedding-gpu/DOCKER-BUILD-TROUBLESHOOTING.md`

Common fix:
```bash
# Use longer timeout and mirror if needed
DOCKER_BUILDKIT=1 docker compose -f docker-compose.gpu.yml build \
  --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
```

---

## Checklist

- [ ] Old stack running: `docker compose up`
- [ ] New api-gpu built: `docker compose -f docker-compose.gpu.yml build`
- [ ] Running: `docker compose -f docker-compose.gpu.yml up`
- [ ] Health check passes: `curl http://localhost:8001/health`
- [ ] GPU detected: `docker exec legal-api-gpu nvidia-smi`
- [ ] RAG test works: `curl -X POST http://localhost:8001/api/v1/test-rag ...`

