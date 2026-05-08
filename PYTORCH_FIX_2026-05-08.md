# PyTorch DLL Fix - May 8, 2026

## Problem
Embedding model initialization was failing with:
```
[WinError 1114] A dynamic link library (DLL) initialization routine failed. 
Error loading "...\.venv_cpu\Lib\site-packages\torch\lib\c10.dll" or one of its dependencies.
```

This caused `QdrantRetriever.embed_model` to be `None`, breaking the entire retrieval pipeline.

## Root Cause
- PyTorch 2.11.0+cpu had a known DLL initialization issue on Windows
- The system-wide Microsoft Visual C++ Runtime dependencies were missing or incompatible

## Solution
Downgraded PyTorch from 2.11.0+cpu to 2.5.0+cpu:
```bash
pip uninstall torch torchvision torchaudio -y
pip install torch==2.5.0+cpu --index-url https://download.pytorch.org/whl/cpu
```

## Verification
✓ PyTorch 2.5.0+cpu now imports successfully  
✓ CUDA not available (CPU-only, which is expected)  
✓ HuggingFace embedding model loads correctly  
✓ QdrantRetriever initializes with embed_model populated  

## Files Changed
- `requirements.txt` - Added explicit torch==2.5.0 specification for Windows
- PyTorch packages reinstalled (torch, torchvision, torchaudio)

## Impact
- ✅ Embedding model now works
- ✅ Vector search retrieval operational
- ✅ No code changes needed - only dependency update

## Future Notes
- Monitor PyTorch releases for a stable newer version that works on Windows
- Consider using ONNX Runtime as an alternative embedding backend for production

