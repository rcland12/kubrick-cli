"""Text-based tool calling for backends without native function calling.

The model is told to emit fenced blocks::

    ```tool_call
    {"tool": "read_file", "parameters": {"file_path": "x.py"}}
    ```

This module renders those instructions, parses the blocks back out, and
flattens the provider-neutral conversation (which may contain native tool
calls and tool results) into plain user/assistant text.
"""

import json
import re
import uuid
from typing import Any, Dict, List

from .messages import ToolCall, ToolSpec

FENCE = "tool_call"

_FENCED_RE = re.compile(r"```tool_call\s*\n(.*?)\n\s*```", re.DOTALL)
_BARE_RE = re.compile(
    r'(\{\s*"tool"\s*:\s*"[^"]+"\s*,\s*"parameters"\s*:\s*\{.*?\}\s*\})', re.DOTALL
)
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


def render_tools_prompt(tools: List[ToolSpec]) -> str:
    """System-prompt section describing the tools and the call format."""
    lines = [
        "# Tool calling",
        "",
        "To use a tool, write a fenced block exactly like this (one block per call):",
        "",
        "```tool_call",
        '{"tool": "read_file", "parameters": {"file_path": "src/app.py"}}',
        "```",
        "",
        "After your tool calls, stop and wait: the results arrive in the next message. "
        "When the task is done, reply normally without any tool_call block.",
        "",
        "## Available tools",
        "",
    ]
    for tool in tools:
        lines.append(f"### {tool.name}")
        lines.append(tool.description)
        props = tool.parameters.get("properties", {})
        required = set(tool.parameters.get("required", []))
        if props:
            lines.append("Parameters:")
            for name, info in props.items():
                flag = "required" if name in required else "optional"
                lines.append(
                    f"- `{name}` ({info.get('type', 'any')}, {flag}): {info.get('description', '')}"
                )
        lines.append("")
    return "\n".join(lines)


def parse_tool_calls(text: str) -> List[ToolCall]:
    """Extract tool calls from model text.

    Fenced ``tool_call`` blocks are preferred; bare ``{"tool": ..., "parameters": ...}``
    objects are accepted as a fallback when no fenced block is present.
    """
    blocks = _FENCED_RE.findall(text)
    if not blocks:
        blocks = [m.group(1) for m in _BARE_RE.finditer(text)]

    calls = []
    for block in blocks:
        cleaned = _TRAILING_COMMA_RE.sub(r"\1", block.strip())
        call_id = f"call_{uuid.uuid4().hex[:12]}"
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            calls.append(
                ToolCall(call_id, "unknown", {}, parse_error=f"invalid JSON: {e}")
            )
            continue
        if not isinstance(data, dict) or not data.get("tool"):
            continue
        params = data.get("parameters", {})
        if not isinstance(params, dict):
            calls.append(
                ToolCall(
                    call_id,
                    data["tool"],
                    {},
                    parse_error="parameters must be an object",
                )
            )
            continue
        calls.append(ToolCall(call_id, data["tool"], params))
    return calls


def strip_tool_calls(text: str) -> str:
    """Remove fenced tool_call blocks from text (for display)."""
    return _FENCED_RE.sub("", text).strip()


def to_plain_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Flatten a conversation into role/content pairs with no tool structure.

    Assistant tool calls become ``tool_call`` blocks; tool results become a
    user message. Consecutive same-role messages are merged so the result
    alternates cleanly.
    """
    plain: List[Dict[str, str]] = []

    def append(role: str, content: str):
        if plain and plain[-1]["role"] == role and role != "system":
            plain[-1]["content"] += "\n\n" + content
        else:
            plain.append({"role": role, "content": content})

    for msg in messages:
        role = msg["role"]
        if role == "assistant":
            parts = [msg.get("content") or ""]
            for call in msg.get("tool_calls") or []:
                block = json.dumps(
                    {"tool": call["name"], "parameters": call["arguments"]}
                )
                parts.append(f"```{FENCE}\n{block}\n```")
            append("assistant", "\n\n".join(p for p in parts if p))
        elif role == "tool":
            status = "Error" if msg.get("is_error") else "Result"
            append(
                "user",
                f"Tool: {msg.get('name', '')}\n{status}: {msg.get('content', '')}",
            )
        else:
            append(role, msg.get("content") or "")
    return plain
