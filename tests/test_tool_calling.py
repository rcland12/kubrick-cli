#!/usr/bin/env python3
"""Test tool calling parsing."""

from kubrick_cli.main import KubrickCLI
from kubrick_cli.config import KubrickConfig


def test_tool_call_parsing():
    """Test that tool call parsing works correctly."""
    print("\n" + "="*60)
    print("Testing Tool Call Parsing")
    print("="*60 + "\n")

    config = KubrickConfig(skip_wizard=True)
    cli = KubrickCLI(config=config)

    # Test 1: Correct format with markdown fence
    print("1. Testing correct format with ```tool_call fence...")
    text1 = """I'll read that file for you.

```tool_call
{
  "tool": "read_file",
  "parameters": {
    "file_path": "test.py"
  }
}
```
"""
    tool_calls = cli.parse_tool_calls(text1)
    assert len(tool_calls) == 1, f"Expected 1 tool call, got {len(tool_calls)}"
    assert tool_calls[0][0] == "read_file", f"Expected read_file, got {tool_calls[0][0]}"
    assert tool_calls[0][1]["file_path"] == "test.py"
    print("   ✓ Correctly parsed tool call with markdown fence")

    # Test 2: Multiple tool calls
    print("\n2. Testing multiple tool calls...")
    text2 = """I'll read the file first:

```tool_call
{
  "tool": "read_file",
  "parameters": {
    "file_path": "config.txt"
  }
}
```

Then I'll write a new file:

```tool_call
{
  "tool": "write_file",
  "parameters": {
    "file_path": "output.txt",
    "content": "Hello World"
  }
}
```
"""
    tool_calls = cli.parse_tool_calls(text2)
    assert len(tool_calls) == 2, f"Expected 2 tool calls, got {len(tool_calls)}"
    assert tool_calls[0][0] == "read_file"
    assert tool_calls[1][0] == "write_file"
    print("   ✓ Correctly parsed multiple tool calls")

    # Test 3: Fallback parser (no markdown fence)
    print("\n3. Testing fallback parser (missing markdown fence)...")
    text3 = """Here's the tool call:

{
  "tool": "list_files",
  "parameters": {
    "pattern": "*.py"
  }
}
"""
    tool_calls = cli.parse_tool_calls(text3)
    assert len(tool_calls) == 1, f"Expected 1 tool call, got {len(tool_calls)}"
    assert tool_calls[0][0] == "list_files"
    print("   ✓ Fallback parser correctly detected tool call without fence")

    # Test 4: No tool calls
    print("\n4. Testing text without tool calls...")
    text4 = "This is just regular text without any tool calls."
    tool_calls = cli.parse_tool_calls(text4)
    assert len(tool_calls) == 0, f"Expected 0 tool calls, got {len(tool_calls)}"
    print("   ✓ Correctly returned empty list for text without tool calls")

    # Test 5: Real example from conversation.log
    print("\n5. Testing real example from conversation.log...")
    text5 = """{
  "tool": "read_file",
  "parameters": {
    "file_path": "repository/llm_decoupled/config.pbtxt"
  }
}"""
    tool_calls = cli.parse_tool_calls(text5)
    assert len(tool_calls) == 1, f"Expected 1 tool call, got {len(tool_calls)}"
    assert tool_calls[0][0] == "read_file"
    assert tool_calls[0][1]["file_path"] == "repository/llm_decoupled/config.pbtxt"
    print("   ✓ Successfully parsed the problematic example from conversation.log")

    print("\n" + "="*60)
    print("All tests PASSED! ✓")
    print("="*60 + "\n")
    print("Tool calling parsing is working correctly!")
    print("Both primary parser (with markdown fence) and fallback parser")
    print("(without fence) are functioning as expected.\n")


if __name__ == "__main__":
    import sys
    try:
        success = test_tool_call_parsing()
        sys.exit(0 if success else 1)
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        print(traceback.format_exc())
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        print(traceback.format_exc())
        sys.exit(1)
