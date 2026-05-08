# Docker GPU Build Troubleshooting

## Problem: Network timeout during `pip install`

**Error:**
```
pip._vendor.urllib3.exceptions.ProtocolError: ('Connection broken: IncompleteRead(...)')
```

**Root Cause:**
- PyPI download interrupted (network unstable / large packages)
- Default pip timeout too short for large wheels

**Solution (Already Applied in Dockerfile.gpu):**
- ✅ `--default-timeout=1000` (1000 sec = 16 min)
- ✅ `--retries 5` (auto retry 5 times on failure)
- ✅ Fallback timeout=2000 + retries=10 if first attempt fails
- ✅ `--mount=type=cache` for pip cache reuse
- ✅ No build isolation (avoid recompile from source)

## How to Build

### Build with BuildKit cache (Recommended)
```bash
DOCKER_BUILDKIT=1 docker compose -f docker-compose.gpu.yml build --no-cache
```

### Or use regular builds
```bash
docker compose -f docker-compose.gpu.yml build
```

### Check build progress
```bash
# In Docker Desktop: open the build log in UI
# Or via CLI, add verbose flag (may not show build output)
docker compose -f docker-compose.gpu.yml build --progress=plain
```

## If Build Still Fails

### Option 1: Use local PyPI cache (if available)
```bash
# Set pip index URL to a mirror if your PyPI is slow
DOCKER_BUILDKIT=1 docker compose -f docker-compose.gpu.yml build \
  --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
```

### Option 2: Pre-download wheels on host (if you have bandwidth issues)
```bash
# Download all wheels to ./wheels/ locally
pip download -r requirements.txt -d ./wheels/

# Then modify Dockerfile to COPY ./wheels and install from there
# (not included in current version)
```

### Option 3: Split requirements.txt (Manual)
If `requirements.txt` is too large, split into:
- `requirements-core.txt` (small packages)
- `requirements-heavy.txt` (large packages like `llama-index`)

Then install separately in Dockerfile to reduce timeout pressure.

## Network Issue Workarounds

### 1. Increase system timeout (on host)
```bash
# Docker timeout settings (usually not needed if timeout flags are set)
# This is handled in Dockerfile.gpu already
```

### 2. Try a different PyPI mirror
- Aliyun (China): `https://mirrors.aliyun.com/pypi/simple/`
- Tsinghua (China): `https://pypi.tsinghua.edu.cn/simple`
- Official: `https://pypi.org/simple/`

### 3. Prewarm pip cache
```bash
# Before building, pre-download on host
pip install --dry-run -r requirements.txt
# Then build (should reuse cache)
```

## Current Dockerfile.gpu Strategy

```dockerfile
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install ... --timeout=1000 --retries 5 ... || \
    (pip install ... --timeout=2000 --retries 10)
```

**What this does:**
1. Mount pip cache (preserved between builds if using BuildKit)
2. Install with 1000s timeout, 5 retries
3. If fails, retry with 2000s timeout, 10 retries
4. Exponential backoff on network errors

## Testing

### Test build without running full stack
```bash
docker build -f Dockerfile.gpu -t legal-api-gpu:test .
```

### Then run just api-gpu
```bash
docker run --gpus all -p 8001:8000 legal-api-gpu:test
```

### Check GPU inside container
```bash
docker exec -it <container_id> nvidia-smi
```

## Prevention Tips

1. **Use BuildKit**: Enables cache mounting which speeds up rebuilds
2. **Build at off-peak hours**: Less PyPI congestion
3. **Keep requirements.txt pinned**: Avoid re-downloading already-built wheels
4. **Use prebuilt wheel cache**: If possible, mirror subset of PyPI locally
5. **Monitor network**: Check ISP/firewall limits on PyPI connections

---

**Next time you build, test with:**
```bash
DOCKER_BUILDKIT=1 docker compose -f docker-compose.gpu.yml build
```

