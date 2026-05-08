#!/usr/bin/env python
"""
Integration test for embedding GPU support (CPU mode).
This script runs docker compose (CPU) and validates /api/v1/test-rag endpoint.
"""

import subprocess
import time
import requests
import json
import sys
import os

def run_command(cmd, shell=True, timeout=300):
    """Run command and return stdout/stderr."""
    try:
        result = subprocess.run(
            cmd,
            shell=shell,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timeout"

def wait_for_api(max_retries=30, interval=2):
    """Wait for API to be healthy."""
    for i in range(max_retries):
        try:
            resp = requests.get("http://localhost:8000/health", timeout=5)
            if resp.status_code == 200:
                print(f"✅ API is healthy (attempt {i+1})")
                return True
        except requests.RequestException as e:
            print(f"⏳ Waiting for API... (attempt {i+1}, error: {type(e).__name__})")
            time.sleep(interval)
    return False

def test_rag_endpoint():
    """Test /api/v1/test-rag endpoint."""
    payload = {"query": "Tội trộm cắp tài sản"}
    headers = {"Content-Type": "application/json"}
    
    try:
        resp = requests.post(
            "http://localhost:8000/api/v1/test-rag",
            json=payload,
            headers=headers,
            timeout=30
        )
        if resp.status_code != 200:
            print(f"❌ test-rag returned {resp.status_code}: {resp.text}")
            return False
        
        data = resp.json()
        print(f"✅ test-rag response: {json.dumps(data, indent=2)}")
        
        # Verify response structure
        required_keys = ["query", "top_results_count", "elapsed_ms", "status"]
        for key in required_keys:
            if key not in data:
                print(f"❌ Missing key '{key}' in response")
                return False
        
        if data.get("status") != "success":
            print(f"❌ Status is not 'success': {data.get('status')}")
            return False
        
        elapsed_ms = data.get("elapsed_ms")
        if not isinstance(elapsed_ms, (int, float)) or elapsed_ms < 0:
            print(f"❌ Invalid elapsed_ms: {elapsed_ms}")
            return False
        
        print(f"✅ All checks passed! Elapsed: {elapsed_ms:.2f}ms")
        return True
        
    except Exception as e:
        print(f"❌ test-rag request failed: {e}")
        return False

def main():
    print("=" * 60)
    print("Phase 09 Integration Test (CPU mode)")
    print("=" * 60)
    
    # Step 1: Start docker compose
    print("\n[Step 1] Starting docker compose (CPU mode)...")
    returncode, stdout, stderr = run_command(
        "docker compose up --build -d",
        timeout=600
    )
    if returncode != 0:
        print(f"❌ Failed to start docker compose:\n{stderr}")
        return False
    print("✅ Docker compose started")
    
    # Step 2: Wait for API health
    print("\n[Step 2] Waiting for API to be healthy...")
    if not wait_for_api():
        print("❌ API failed to become healthy")
        # Try to get logs for debugging
        _, logs, _ = run_command("docker compose logs api", timeout=30)
        print("Docker logs:", logs[-500:] if len(logs) > 500 else logs)
        return False
    
    # Step 3: Test RAG endpoint
    print("\n[Step 3] Testing /api/v1/test-rag endpoint...")
    if not test_rag_endpoint():
        return False
    
    # Step 4: Cleanup
    print("\n[Step 4] Cleaning up docker compose...")
    run_command("docker compose down", timeout=60)
    print("✅ Cleanup complete")
    
    print("\n" + "=" * 60)
    print("✅ ALL INTEGRATION TESTS PASSED (CPU mode)")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

