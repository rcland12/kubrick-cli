"""Tests for the text-based tool calling protocol."""

from kubrick_cli.messages import ToolSpec
from kubrick_cli.tool_protocol import (
    parse_tool_calls,
    render_tools_prompt,
    strip_tool_calls,
    to_plain_messages,
)


def test_parses_fenced_calls():
    text = """I'll read it.

```tool_call
{"tool": "read_file", "parameters": {"file_path": "test.py"}}
```

```tool_call
{
  "tool": "write_file",
  "parameters": {"file_path": "out.txt", "content": "hi",},
}
```
"""
    calls = parse_tool_calls(text)
    assert [c.name for c in calls] == ["read_file", "write_file"]
    assert calls[0].arguments == {"file_path": "test.py"}
    assert calls[1].arguments["content"] == "hi"  # trailing commas tolerated
    assert calls[0].id != calls[1].id


def test_bare_json_fallback():
    calls = parse_tool_calls(
        '{"tool": "list_files", "parameters": {"pattern": "*.py"}}'
    )
    assert len(calls) == 1 and calls[0].name == "list_files"


def test_no_calls_in_plain_text():
    assert parse_tool_calls("Just text, no tools.") == []


def test_invalid_json_becomes_parse_error():
    calls = parse_tool_calls("```tool_call\n{not json}\n```")
    assert len(calls) == 1 and calls[0].parse_error


def test_strip_tool_calls():
    text = 'Before\n```tool_call\n{"tool": "x", "parameters": {}}\n```\nAfter'
    assert strip_tool_calls(text) == "Before\n\nAfter"


def test_to_plain_messages_flattens_tool_structure():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "do it"},
        {
            "role": "assistant",
            "content": "Reading.",
            "tool_calls": [
                {"id": "1", "name": "read_file", "arguments": {"file_path": "a"}}
            ],
        },
        {"role": "tool", "tool_call_id": "1", "name": "read_file", "content": "data"},
        {
            "role": "tool",
            "tool_call_id": "2",
            "name": "run_bash",
            "content": "boom",
            "is_error": True,
        },
        {"role": "assistant", "content": "Done."},
    ]
    plain = to_plain_messages(messages)
    assert [m["role"] for m in plain] == [
        "system",
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert (
        "```tool_call" in plain[2]["content"] and '"read_file"' in plain[2]["content"]
    )
    assert (
        "Result: data" in plain[3]["content"] and "Error: boom" in plain[3]["content"]
    )
    # Round trip: the flattened call parses back.
    assert parse_tool_calls(plain[2]["content"])[0].arguments == {"file_path": "a"}


def test_render_tools_prompt_lists_parameters():
    spec = ToolSpec(
        "read_file",
        "Read a file",
        {
            "type": "object",
            "properties": {"file_path": {"type": "string", "description": "path"}},
            "required": ["file_path"],
        },
    )
    prompt = render_tools_prompt([spec])
    assert "### read_file" in prompt and "`file_path` (string, required)" in prompt
