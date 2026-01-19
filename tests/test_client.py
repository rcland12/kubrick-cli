#!/usr/bin/env python3
"""Simple test script for the HTTP-based Triton client."""

import sys
from kubrick_cli.triton_client import TritonLLMClient


def test_http_client():
    """Test HTTP client with no external dependencies."""
    print("\n" + "="*60)
    print("Testing Kubrick HTTP Client")
    print("="*60 + "\n")

    # Initialize client
    print("1. Initializing HTTP client...")
    try:
        client = TritonLLMClient(
            url="localhost:8000",
            model_name="llm_decoupled",
        )
        print("   ✓ Client initialized")
    except Exception as e:
        print(f"   ✗ Failed to initialize: {e}")
        return False

    # Test health check
    print("\n2. Checking server health...")
    try:
        is_healthy = client.is_healthy()
        if is_healthy:
            print("   ✓ Server is healthy")
        else:
            print("   ✗ Server is not responding")
            return False
    except Exception as e:
        print(f"   ✗ Health check failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False

    # Test streaming inference
    print("\n3. Testing streaming inference...")
    print("   Sending: 'Say hello in one word'")
    print("   Response: ", end="", flush=True)

    messages = [
        {"role": "user", "content": "Say hello in one word."}
    ]

    try:
        full_response = ""
        for chunk in client.generate_streaming(messages):
            print(chunk, end="", flush=True)
            full_response += chunk

        print("\n")

        if full_response:
            print(f"   ✓ Got response: {repr(full_response[:50])}")
            return True
        else:
            print("   ✗ Empty response")
            return False

    except Exception as e:
        print(f"\n   ✗ Streaming failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False


def main():
    """Run the test."""
    print("\n" + "="*60)
    print("Kubrick Triton Client Test")
    print("="*60)

    result = test_http_client()

    # Print summary
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)

    if result:
        print("HTTP: ✓ PASSED")
        print("="*60 + "\n")
        print("All tests PASSED! ✓\n")
        return 0
    else:
        print("HTTP: ✗ FAILED")
        print("="*60 + "\n")
        print("Tests FAILED! ✗\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
