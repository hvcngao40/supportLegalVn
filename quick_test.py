#!/usr/bin/env python3
"""Quick test of embedding functionality"""
import os
import sys

print("[1] Import PyTorch...")
import torch
print(f"[OK] PyTorch version: {torch.__version__}")

print("\n[2] Initialize Embedding Model directly...")
try:
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    print("[Loading] HuggingFaceEmbedding (this may take a while, downloading model...)")
    embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-base-en-v1.5")
    print(f"[OK] Embedding model loaded: {type(embed_model).__name__}")
except Exception as e:
    print(f"[ERROR] Failed to load embedding model: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n[3] Test embedding query...")
try:
    embedding = embed_model.get_query_embedding("test query")
    print(f"[OK] Successfully created embedding of length: {len(embedding)}")
except Exception as e:
    print(f"[ERROR] Failed to create embedding: {e}")
    sys.exit(1)

print("\n[SUCCESS] All steps completed!")

