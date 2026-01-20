# #!/usr/bin/env python3
# """Simple test script for the HTTP-based Triton client."""

# import sys
# from kubrick_cli.triton_client import TritonLLMClient


# def test_http_client():
#     """Test HTTP client with no external dependencies."""
#     print("\n" + "="*60)
#     print("Testing Kubrick HTTP Client")
#     print("="*60 + "\n")

#     # Initialize client
#     print("1. Initializing HTTP client...")
#     client = TritonLLMClient(
#         url="localhost:8000",
#         model_name="llm_decoupled",
#     )
#     print("   ✓ Client initialized")

#     # Test health check
#     print("\n2. Checking server health...")
#     is_healthy = client.is_healthy()
#     assert is_healthy, "Server is not responding"
#     print("   ✓ Server is healthy")

#     # Test streaming inference
#     print("\n3. Testing streaming inference...")
#     print("   Sending: 'Say hello in one word'")
#     print("   Response: ", end="", flush=True)

#     messages = [
#         {"role": "user", "content": "Say hello in one word."}
#     ]

#     full_response = ""
#     for chunk in client.generate_streaming(messages):
#         print(chunk, end="", flush=True)
#         full_response += chunk

#     print("\n")

#     assert full_response, "Empty response received"
#     print(f"   ✓ Got response: {repr(full_response[:50])}")


# def main():
#     """Run the test."""
#     print("\n" + "="*60)
#     print("Kubrick Triton Client Test")
#     print("="*60)

#     result = test_http_client()

#     # Print summary
#     print("\n" + "="*60)
#     print("Test Summary")
#     print("="*60)

#     if result:
#         print("HTTP: ✓ PASSED")
#         print("="*60 + "\n")
#         print("All tests PASSED! ✓\n")
#         return 0
#     else:
#         print("HTTP: ✗ FAILED")
#         print("="*60 + "\n")
#         print("Tests FAILED! ✗\n")
#         return 1


# if __name__ == "__main__":
#     sys.exit(main())
