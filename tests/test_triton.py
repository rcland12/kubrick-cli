#!/usr/bin/env python3
"""Test script for Triton LLM using HTTP client (no external dependencies)."""

import sys
from kubrick_cli.triton_client import TritonLLMClient


def test_http_protocol():
    """Test HTTP protocol using the custom HTTP client."""
    print(f"\n{'=' * 60}")
    print(f"Testing HTTP protocol")
    print(f"{'=' * 60}\n")

    # Initialize client
    print("Test 1: Initializing HTTP client...")
    client = TritonLLMClient(
        url="localhost:8000",
        model_name="llm_decoupled",
    )
    print("  ✓ Client initialized")

    # Test server health
    print("\nTest 2: Checking if server is alive...")
    is_healthy = client.is_healthy()
    assert is_healthy, "Server is not responding"
    print("  ✓ Server is alive and healthy")

    # Test streaming inference
    print("\nTest 3: Testing streaming inference...")
    print("  → Sending request: 'Say hello in one word.'")

    messages = [
        {"role": "user", "content": "Say hello in one word."}
    ]

    full_response = ""
    chunk_count = 0

    for chunk in client.generate_streaming(messages):
        chunk_count += 1
        full_response += chunk
        # Print first few chunks
        if chunk_count <= 3:
            print(f"  ← Received chunk {chunk_count}: {repr(chunk)}")

    if chunk_count > 3:
        print(f"  ← ... ({chunk_count - 3} more chunks)")

    print(f"\n  ✓ Full response: {repr(full_response)}")

    assert full_response, "Empty response received"
    print("  ✓ Streaming inference PASSED!")


def test_non_streaming():
    """Test non-streaming (complete) response."""
    print(f"\n{'=' * 60}")
    print(f"Testing Non-Streaming Response")
    print(f"{'=' * 60}\n")

    client = TritonLLMClient(
        url="localhost:8000",
        model_name="llm_decoupled",
    )
    print("  ✓ Client initialized")

    print("\nTest: Sending non-streaming request...")
    messages = [
        {"role": "user", "content": "Count from 1 to 3."}
    ]

    response = client.generate(messages)
    print(f"  ✓ Full response: {repr(response)}")

    assert response, "Empty response received"
    print("  ✓ Non-streaming inference PASSED!")


def main() -> int:
    """Run all tests."""
    print("\n" + "=" * 60)
    print("Triton LLM HTTP Client Test Suite")
    print("=" * 60)

    results = {}

    # Test 1: HTTP streaming
    try:
        results["http_streaming"] = test_http_protocol()
    except Exception as e:
        print(f"\n✗ Fatal error testing HTTP streaming: {e}")
        import traceback
        print(traceback.format_exc())
        results["http_streaming"] = False

    # Test 2: Non-streaming
    try:
        results["non_streaming"] = test_non_streaming()
    except Exception as e:
        print(f"\n✗ Fatal error testing non-streaming: {e}")
        import traceback
        print(traceback.format_exc())
        results["non_streaming"] = False

    # Print summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    for test_name, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{test_name.replace('_', ' ').title()}: {status}")

    all_passed = all(results.values())
    print("\n" + "=" * 60)
    if all_passed:
        print("All tests PASSED! ✓")
        print("=" * 60 + "\n")
        return 0
    else:
        print("Some tests FAILED! ✗")
        print("=" * 60 + "\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
