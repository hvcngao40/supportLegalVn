# docker-compose.gpu.yml — Complete & Ready to Run

✅ **File is now COMPLETE and STANDALONE**

## What's included

```yaml
services:
  ✓ api              (FastAPI with Dockerfile.gpu, CUDA enabled)
  ✓ qdrant           (Vector DB with 6GB memory for GPU inference)

networks:
  ✓ legal-network    (dedicated network)

volumes:
  ✓ qdrant_data      (persistent storage)

environment:
  ✓ EMBEDDING_DEVICE=cuda  (force GPU mode)
  ✓ QDRANT_HOST=qdrant     (service discovery)
  ✓ All production configs  (.env file loaded)

monitoring:
  ✓ Health checks    (API + Qdrant)
  ✓ Restart policy   (unless-stopped)
  ✓ GPU device       (nvidia - 1 GPU requested)
```

## Run Commands

### Standalone (Recommended)
```bash
docker compose -f docker-compose.gpu.yml up --build
```

### With base override (if you prefer)
```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build
```

## Prerequisites

- Docker with GPU support enabled
- NVIDIA Container Toolkit installed (for Linux)
- Docker Desktop GPU enabled (for Mac/Windows)
- NVIDIA drivers installed
- `docker compose` v2+

## Verify GPU Access Inside Container

```bash
# Inside running container
nvidia-smi

# Or from host
docker exec legal-api-gpu nvidia-smi
```

## Environment Variables

- `EMBEDDING_DEVICE=cuda` — Forces GPU mode
- `QDRANT_HOST=qdrant` — Auto-discovery via service name
- `QDRANT_PORT=6334` — gRPC port
- All other configs from `.env` file (loaded automatically)

## What Changed

1. ✅ Added complete `services` section with both api + qdrant
2. ✅ Added explicit `networks` definition  
3. ✅ Added `volumes` declaration
4. ✅ Added `version: '3.9'` header
5. ✅ Increased Qdrant memory to 6GB (GPU inference needs more)
6. ✅ Added named containers (`legal-api-gpu`, `legal-qdrant-gpu`)
7. ✅ Added GPU device mapping with nvidia driver

## Status

✅ **READY TO DEPLOY**

```bash
docker compose -f docker-compose.gpu.yml up --build
```

That's it!

