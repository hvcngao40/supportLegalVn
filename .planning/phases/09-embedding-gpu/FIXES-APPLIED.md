# Fixes applied to Phase 09 — 2026-05-08 (Latest)

## Issue: Docker build fails with network timeout

**Error reported:**
```
pip._vendor.urllib3.exceptions.ProtocolError: IncompleteRead(...) 
```

**Root cause:** PyPI download interrupted during large package transfers (requirements.txt contains large dependencies like `llama-index`, `ragas`, etc.)

---

## Fixes Applied

### 1. ✅ Dockerfile.gpu — Network Resilience
**Changes:**
- Added `--default-timeout=1000` (1000 sec = 16 minutes)
- Added `--retries 5` for automatic retry on download failures
- Added pip cache mounting: `--mount=type=cache,target=/root/.cache/pip`
- Added fallback: if first install fails, retry with timeout=2000 + retries=10
- Removed `--no-cache-dir` to enable pip wheel caching
- Added `--no-build-isolation` to skip recompiling from source

**Result:** Much more robust to network interruptions

### 2. ✅ docker-compose.gpu.yml — Standalone Service
**Changes:**
- `api-gpu` service runs **independently** (port 8001)
- Reuses external `legal-network` from existing stack
- No duplicate qdrant (reuses the one from main stack)
- Can run alongside main api-cpu on port 8000 for side-by-side testing

**Usage:**
```bash
# Stack old must be running first (has qdrant on legal-network)
docker compose -f docker-compose.gpu.yml up --build
```

### 3. ✅ Documentation
- Added `DOCKER-BUILD-TROUBLESHOOTING.md` with:
  - Why build fails (network/timeout)
  - Solutions (timeouts, retries, mirrors)
  - BuildKit usage for faster rebuilds
  - Pre-warming cache tips
- Updated `09-SUMMARY.md` with:
  - Port 8001 for api-gpu
  - BuildKit recommended command
  - Reference to troubleshooting guide

---

## Build Recommendations

### Quick build (BuildKit enabled)
```bash
DOCKER_BUILDKIT=1 docker compose -f docker-compose.gpu.yml build
docker compose -f docker-compose.gpu.yml up
```

### If network is unstable
```bash
# Set longer timeout (will use defaults from Dockerfile.gpu)
docker compose -f docker-compose.gpu.yml build --progress=plain

# Or use PyPI mirror
DOCKER_BUILDKIT=1 docker compose -f docker-compose.gpu.yml build \
  --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
```

### Test build independently
```bash
docker build -f Dockerfile.gpu -t legal-api-gpu:test .
docker run --gpus all -p 8001:8000 legal-api-gpu:test
```

---

## Files Changed

| File | Change |
|------|--------|
| `Dockerfile.gpu` | ✅ Added timeout/retry/cache logic for pip install |
| `docker-compose.gpu.yml` | ✅ Converted to standalone api-gpu only (port 8001) |
| `09-SUMMARY.md` | ✅ Updated with port 8001 and BuildKit info |
| `DOCKER-BUILD-TROUBLESHOOTING.md` | ✅ NEW — comprehensive troubleshooting guide |

---

## Status

✅ **Phase 09 Updated & Ready for Testing**

All improvements are backward compatible and should resolve the network timeout issues during Docker build.

**Next time you build:**
```bash
DOCKER_BUILDKIT=1 docker compose -f docker-compose.gpu.yml build
```

