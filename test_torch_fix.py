#!/usr/bin/env python3
"""Test PyTorch and Embedding Model"""
import sys
import os

print("[Step 1] Testing PyTorch import...")
try:
    import torch
    print(f"[OK] PyTorch {torch.__version__} imported successfully")
    print(f"  CUDA available: {torch.cuda.is_available()}")
except Exception as e:
    print(f"[FAIL] PyTorch import failed: {e}")
    sys.exit(1)

print("\n[Step 2] Testing LlamaIndex HuggingFace Embedding...")
try:
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    print("[OK] HuggingFaceEmbedding imported successfully")
except Exception as e:
    print(f"[FAIL] HuggingFaceEmbedding import failed: {e}")
    sys.exit(1)

print("\n[Step 3] Testing QdrantRetriever...")
try:
    from retrievers.qdrant_retriever import QdrantRetriever
    retriever = QdrantRetriever()
    
    if retriever.embed_model is None:
        print("[FAIL] embed_model is None - FAILED")
        sys.exit(1)
    else:
        print(f"[OK] QdrantRetriever initialized successfully")
        print(f"  embed_model: {type(retriever.embed_model).__name__}")
        print(f"  client: {retriever._get_client() is not None}")
except Exception as e:
    print(f"[FAIL] QdrantRetriever failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n[SUCCESS] All tests passed!")


