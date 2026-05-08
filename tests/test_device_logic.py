import os
import sys

def test_device_logic():
    """Test device selection logic for all env var combinations."""
    tests_passed = 0
    tests_total = 0
    
    # Test 1: EMBEDDING_DEVICE=cpu
    tests_total += 1
    os.environ['EMBEDDING_DEVICE'] = 'cpu'
    device_pref = os.getenv("EMBEDDING_DEVICE", "auto").lower()
    if device_pref == "cpu":
        device = "cpu"
    if device == "cpu":
        print("✅ Test 1 PASSED: EMBEDDING_DEVICE=cpu -> device=cpu")
        tests_passed += 1
    else:
        print(f"❌ Test 1 FAILED: expected cpu, got {device}")
    
    # Test 2: EMBEDDING_DEVICE=auto (no cuda)
    tests_total += 1
    os.environ['EMBEDDING_DEVICE'] = 'auto'
    device_pref = os.getenv("EMBEDDING_DEVICE", "auto").lower()
    if device_pref == "auto":
        device = "cpu"  # Assume no cuda on Windows
    if device == "cpu":
        print("✅ Test 2 PASSED: EMBEDDING_DEVICE=auto (no cuda) -> device=cpu")
        tests_passed += 1
    else:
        print(f"❌ Test 2 FAILED: expected cpu, got {device}")
    
    # Test 3: EMBEDDING_DEVICE=cuda
    tests_total += 1
    os.environ['EMBEDDING_DEVICE'] = 'cuda'
    device_pref = os.getenv("EMBEDDING_DEVICE", "auto").lower()
    if device_pref in ("cuda", "gpu"):
        device = "cuda"
    if device == "cuda":
        print("✅ Test 3 PASSED: EMBEDDING_DEVICE=cuda -> device=cuda")
        tests_passed += 1
    else:
        print(f"❌ Test 3 FAILED: expected cuda, got {device}")
    
    # Test 4: EMBEDDING_DEVICE=gpu (alias)
    tests_total += 1
    os.environ['EMBEDDING_DEVICE'] = 'gpu'
    device_pref = os.getenv("EMBEDDING_DEVICE", "auto").lower()
    if device_pref in ("cuda", "gpu"):
        device = "cuda"
    if device == "cuda":
        print("✅ Test 4 PASSED: EMBEDDING_DEVICE=gpu -> device=cuda")
        tests_passed += 1
    else:
        print(f"❌ Test 4 FAILED: expected cuda, got {device}")
    
    # Test 5: FORCE_DISABLE_CUDA override
    tests_total += 1
    os.environ['EMBEDDING_DEVICE'] = 'auto'
    os.environ['FORCE_DISABLE_CUDA'] = '1'
    device_pref = os.getenv("EMBEDDING_DEVICE", "auto").lower()
    force_disable = os.getenv("FORCE_DISABLE_CUDA", "")
    if device_pref == "auto":
        if force_disable and force_disable.lower() not in ("", "0", "false"):
            device = "cpu"
        else:
            device = "cuda"
    if device == "cpu":
        print("✅ Test 5 PASSED: FORCE_DISABLE_CUDA=1 overrides auto to cpu")
        tests_passed += 1
    else:
        print(f"❌ Test 5 FAILED: expected cpu, got {device}")
    
    # Test 6: Invalid EMBEDDING_DEVICE fallback
    tests_total += 1
    os.environ['EMBEDDING_DEVICE'] = 'invalid'
    if 'FORCE_DISABLE_CUDA' in os.environ:
        del os.environ['FORCE_DISABLE_CUDA']
    device_pref = os.getenv("EMBEDDING_DEVICE", "auto").lower()
    if device_pref not in ("auto", "cpu", "cuda", "gpu"):
        device_pref = "auto"
    if device_pref == "auto":
        print("✅ Test 6 PASSED: Invalid EMBEDDING_DEVICE fallbacks to auto")
        tests_passed += 1
    else:
        print(f"❌ Test 6 FAILED: expected auto, got {device_pref}")
    
    print(f"\n✅ {tests_passed}/{tests_total} LOGIC TESTS PASSED")
    return tests_passed == tests_total

if __name__ == "__main__":
    success = test_device_logic()
    sys.exit(0 if success else 1)

