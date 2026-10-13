"""Provider-neutral conversation messages and streaming events.

Every provider converts to and from these shapes, so the agent loop, context
manager, and conversation persistence never deal with vendor wire formats.

Message dicts (JSON-serializable so conversations can be saved as-is)::

    {"role": "system", "content": str}
    {"role": "user", "content": str}
    {"role": "assistant", "content": str,
     "tool_calls": [{"id": str, "name": str, "arguments": dict}],   # optional
     "raw": {"provider": str, "model": str, "content": list}}       # optional
    {"role": "tool", "tool_call_id": str, "name": str, "content": str,
     "is_error": bool}

``raw`` holds the provider's own content blocks for an assistant turn (thinking
blocks with signatures, fallback markers, ...). The provider that produced it
replays it verbatim; every other provider ignores it and rebuilds the turn from
``content`` + ``tool_calls``.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolCall:
    """A tool invocation requested by the model."""

    id: str
    name: str
    arguments: Dict[str, Any]
    # Set when the model's argument JSON could not be parsed. The call is
    # answered with an error result instead of being executed.
    parse_error: Optional[str] = None

    def __post_init__(self):
        self.name = clean_tool_name(self.name)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for storage in an assistant message."""
        return {"id": self.id, "name": self.name, "arguments": self.arguments}


# Chat-template control tokens some models (gpt-oss "harmony") leak into tool names,
# e.g. "read_file<|channel|>commentary".
_TEMPLATE_JUNK = re.compile(r"<\|.*$", re.S)


def clean_tool_name(name: str) -> str:
    """Strip template tokens and a "functions." namespace from a model's tool name."""
    name = _TEMPLATE_JUNK.sub("", name or "").strip()
    if name.startswith("functions."):
        name = name[len("functions.") :]
    return name


@dataclass
class Usage:
    """Token usage reported by a provider for one response."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def context_tokens(self) -> int:
        """Tokens the prompt occupied in the context window."""
        return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens


# --- Stream events -----------------------------------------------------------


@dataclass
class TextDelta:
    """A chunk of visible response text."""

    text: str


@dataclass
class ThinkingDelta:
    """A chunk of model reasoning (displayed dimmed, never sent back as text)."""

    text: str


@dataclass
class ToolCallEvent:
    """A fully-assembled tool call (emitted once its arguments are complete)."""

    call: ToolCall


@dataclass
class MessageDone:
    """End of one model response."""

    # Normalized: "end_turn", "tool_use", "max_tokens", "refusal", or the
    # provider's own value when it doesn't map cleanly.
    stop_reason: str = "end_turn"
    usage: Optional[Usage] = None
    # Provider-native assistant content to store in the message's "raw" field.
    raw: Optional[Dict[str, Any]] = None
    # Human-readable detail for refusals and other abnormal stops.
    detail: Optional[str] = None


@dataclass
class ToolSpec:
    """A tool definition offered to the model."""

    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)


# --- Helpers -----------------------------------------------------------------


def parse_arguments(raw: str) -> Dict[str, Any]:
    """Parse a tool-call argument string into a dict.

    Raises:
        ValueError: If the string is not a JSON object.
    """
    if not raw or not raw.strip():
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(
            f"tool arguments must be a JSON object, got {type(value).__name__}"
        )
    return value


def message_text_for_counting(message: Dict[str, Any]) -> str:
    """Flatten a message into text for heuristic token counting."""
    parts = [message.get("content") or ""]
    for call in message.get("tool_calls") or []:
        parts.append(call.get("name", ""))
        parts.append(json.dumps(call.get("arguments", {})))
    return "\n".join(parts)


def group_tool_results(messages: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """Split messages into runs, grouping consecutive ``tool`` messages.

    Returns a list where each item is either a single non-tool message wrapped
    in a list, or a list of consecutive tool-result messages. Providers that
    need all results of one assistant turn in a single user message (Anthropic,
    Bedrock) use this.
    """
    runs: List[List[Dict[str, Any]]] = []
    for msg in messages:
        if msg["role"] == "tool" and runs and runs[-1][0]["role"] == "tool":
            runs[-1].append(msg)
        else:
            runs.append([msg])
    return runs


class ThinkTagSplitter:
    """Routes inline reasoning (``<think>...</think>``, ``<thinking>...</thinking>``)
    in streamed text to ThinkingDelta.

    Some servers and models (Qwen/DeepSeek via local servers, Amazon Nova) put their
    chain of thought in the text instead of a separate reasoning field.
    """

    TAGS = (("<think>", "</think>"), ("<thinking>", "</thinking>"))

    def __init__(self):
        self.close: Optional[str] = None  # closing tag while inside a reasoning span
        self.pending = ""

    def feed(self, text: str) -> List[Any]:
        self.pending += text
        events: List[Any] = []
        while self.pending:
            if self.close:
                idx = self.pending.find(self.close)
                if idx >= 0:
                    self._emit(events, self.pending[:idx])
                    self.pending = self.pending[idx + len(self.close) :]
                    self.close = None
                    continue
                candidates = [self.close]
            else:
                hits = [
                    (self.pending.find(o), o, c)
                    for o, c in self.TAGS
                    if o in self.pending
                ]
                if hits:
                    idx, opening, closing = min(hits)
                    self._emit(events, self.pending[:idx])
                    self.pending = self.pending[idx + len(opening) :]
                    self.close = closing
                    continue
                candidates = [o for o, _ in self.TAGS]
            # Hold back a possible partial tag at the end of the buffer.
            keep = 0
            for tag in candidates:
                for n in range(min(len(tag) - 1, len(self.pending)), 0, -1):
                    if tag.startswith(self.pending[-n:]):
                        keep = max(keep, n)
                        break
            self._emit(events, self.pending[: len(self.pending) - keep])
            self.pending = self.pending[len(self.pending) - keep :]
            break
        return events

    def flush(self) -> List[Any]:
        events: List[Any] = []
        self._emit(events, self.pending)
        self.pending = ""
        return events

    def _emit(self, events: List[Any], text: str):
        if text:
            events.append(ThinkingDelta(text) if self.close else TextDelta(text))
