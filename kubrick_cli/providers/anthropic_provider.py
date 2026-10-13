"""Anthropic provider adapter (Messages API over raw HTTP)."""

import json
import re
import time
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import urlparse

from ..messages import (
    MessageDone,
    TextDelta,
    ThinkingDelta,
    ToolCall,
    ToolCallEvent,
    ToolSpec,
    Usage,
    group_tool_results,
    parse_arguments,
)
from .base import ProviderAdapter, ProviderError, ProviderMetadata
from .http import HttpEndpoint, HttpStatusError, iter_sse_data

API_VERSION = "2023-06-01"
BETA_THINKING_BINDING = "thinking-binding-controls-2026-08-01"
BETA_FALLBACK = "server-side-fallback-2026-07-01"

# Models that accept server-side refusal fallbacks (``fallbacks: "default"``).
FALLBACK_MODELS = {
    "claude-opus-5-5",
    "claude-opus-5",
    "claude-sonnet-5-5",
    "claude-fable-5-1",
}

RETRYABLE_STATUSES = {429, 500, 502, 503, 529}
MAX_RETRIES = 2

_THINKING_TYPES = ("thinking", "redacted_thinking")

# claude-<family>-<major>[-<minor>][-<yyyymmdd>]
_NEW_STYLE_RE = re.compile(r"^claude-([a-z]+)-(\d+)(?:-(\d{1,2}))?(?:-\d{8})?$")
# claude-<major>[-<minor>]-<family>[-<yyyymmdd>] (Claude 3.x naming)
_OLD_STYLE_RE = re.compile(r"^claude-(\d+)(?:-(\d{1,2}))?-([a-z]+)(?:-\d{8})?$")


def _strip_prefixes(model: str) -> str:
    """Drop gateway/region prefixes (``us.anthropic.``) and Bedrock suffixes (``-v1:0``)."""
    model = model.strip().lower()
    if "claude-" in model:
        model = model[model.index("claude-") :]
    model = model.split(":")[0].split("@")[0]
    return re.sub(r"-v\d+$", "", model)


def is_modern_model(model: str) -> bool:
    """Whether a model supports adaptive thinking, effort and eager tool streaming.

    Modern: Fable/Mythos (any version), Opus/Sonnet >= 4.6, Haiku >= 5.
    Unrecognized ids are treated as modern so new releases work by default.
    """
    model = _strip_prefixes(model)
    if _OLD_STYLE_RE.match(model) or model in ("claude-2", "claude-instant-1"):
        return False
    match = _NEW_STYLE_RE.match(model)
    if not match:
        return True
    family, major, minor = match.group(1), int(match.group(2)), int(match.group(3) or 0)
    version = (major, minor)
    if family in ("fable", "mythos"):
        return True
    if family in ("opus", "sonnet"):
        return version >= (4, 6)
    if family == "haiku":
        return version >= (5, 0)
    return True


def _normalize_stop_reason(reason: Optional[str]) -> str:
    if reason in (None, "end_turn", "stop_sequence"):
        return "end_turn"
    return reason


class AnthropicProvider(ProviderAdapter):
    """Provider adapter for the Anthropic Messages API."""

    METADATA = ProviderMetadata(
        name="anthropic",
        display_name="Anthropic (Claude)",
        description="Claude Opus, Sonnet, Haiku with an Anthropic Console API key",
        config_fields=[
            {
                "key": "anthropic_api_key",
                "label": "Anthropic API key",
                "type": "secret",
                "env": ["ANTHROPIC_API_KEY"],
                "help_text": "Get your API key from: https://console.anthropic.com/settings/keys",
            },
            {
                "key": "anthropic_model",
                "label": "Model",
                "type": "model",
                "default": "claude-opus-5-5",
            },
            {
                "key": "anthropic_base_url",
                "label": "API base URL",
                "type": "url",
                "default": "https://api.anthropic.com",
                "help_text": "Change only when routing through a gateway or proxy",
                "advanced": True,
            },
            {
                "key": "anthropic_effort",
                "label": "Effort",
                "type": "text",
                "default": "high",
                "required": False,
                "choices": [
                    ("low", "Fastest and cheapest"),
                    ("medium", "Balanced"),
                    ("high", "Recommended for coding"),
                    ("xhigh", "Harder problems; slower"),
                    ("max", "Most thorough; slowest"),
                ],
                "help_text": "How much the model thinks before answering "
                "(only sent to models that support effort).",
            },
        ],
    )

    def __init__(
        self,
        api_key: str,
        model: str = "claude-opus-5-5",
        base_url: str = "https://api.anthropic.com",
        effort: str = "high",
    ):
        """
        Initialize Anthropic provider.

        Args:
            api_key: Anthropic API key
            model: Model id (default: claude-opus-5-5)
            base_url: API base URL (gateways/proxies)
            effort: Effort level sent to models that support it ("" to omit)
        """
        self.api_key = api_key
        self._model_name = model
        self.base_url = base_url or "https://api.anthropic.com"
        self.effort = effort or None
        self.endpoint = HttpEndpoint(self.base_url, timeout=600)
        self._context_windows: Dict[str, Optional[int]] = {}

    # --- Properties -----------------------------------------------------------

    @property
    def provider_name(self) -> str:
        """Get provider name."""
        return "anthropic"

    @property
    def model_name(self) -> str:
        """Get model name."""
        return self._model_name

    @property
    def _is_first_party(self) -> bool:
        host = urlparse(
            self.base_url if "://" in self.base_url else f"https://{self.base_url}"
        )
        return host.hostname == "api.anthropic.com"

    # --- Request building -----------------------------------------------------

    def _headers(self, betas: List[str]) -> Dict[str, str]:
        headers = {
            "x-api-key": self.api_key or "",
            "anthropic-version": API_VERSION,
            "Accept": "text/event-stream",
        }
        if betas:
            headers["anthropic-beta"] = ",".join(betas)
        return headers

    def _replay_blocks(
        self, raw_content: List[Dict[str, Any]], strip_thinking: bool
    ) -> List:
        """Replay stored content blocks, applying the fallback echo rule."""
        blocks = list(raw_content)
        fallback_positions = [
            i for i, b in enumerate(blocks) if b.get("type") == "fallback"
        ]
        if fallback_positions:
            last = fallback_positions[-1]
            dropped = _THINKING_TYPES + ("tool_use",)
            blocks = [
                b
                for i, b in enumerate(blocks)
                if not (i < last and b.get("type") in dropped)
            ]
        if strip_thinking:
            blocks = [b for b in blocks if b.get("type") not in _THINKING_TYPES]
        return blocks

    def convert_messages(
        self, messages: List[Dict[str, Any]], strip_thinking: bool = False
    ) -> Dict[str, Any]:
        """Convert provider-neutral messages to ``system`` + ``messages``.

        Args:
            messages: Conversation in the neutral format
            strip_thinking: Drop thinking blocks from replayed raw content

        Returns:
            Dict with ``system`` (str) and ``messages`` (list)
        """
        system_parts: List[str] = []
        out: List[Dict[str, Any]] = []
        leading = True

        for run in group_tool_results(messages):
            msg = run[0]
            role = msg["role"]

            if role == "system":
                if leading:
                    system_parts.append(msg.get("content") or "")
                else:
                    text = (
                        f"<system-reminder>{msg.get('content') or ''}</system-reminder>"
                    )
                    out.append(
                        {"role": "user", "content": [{"type": "text", "text": text}]}
                    )
                continue
            leading = False

            if role == "tool":
                results = []
                for tool_msg in run:
                    block = {
                        "type": "tool_result",
                        "tool_use_id": tool_msg.get("tool_call_id"),
                        "content": tool_msg.get("content") or "",
                    }
                    if tool_msg.get("is_error"):
                        block["is_error"] = True
                    results.append(block)
                out.append({"role": "user", "content": results})
            elif role == "assistant":
                raw = msg.get("raw") or {}
                if (
                    raw.get("provider") == "anthropic"
                    and raw.get("model") == self._model_name
                    and isinstance(raw.get("content"), list)
                ):
                    blocks = self._replay_blocks(raw["content"], strip_thinking)
                else:
                    blocks = []
                    if msg.get("content"):
                        blocks.append({"type": "text", "text": msg["content"]})
                    for call in msg.get("tool_calls") or []:
                        blocks.append(
                            {
                                "type": "tool_use",
                                "id": call["id"],
                                "name": call["name"],
                                "input": call.get("arguments") or {},
                            }
                        )
                if blocks:
                    out.append({"role": "assistant", "content": blocks})
            else:
                out.append(
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": msg.get("content") or ""}],
                    }
                )

        return {"system": "\n\n".join(p for p in system_parts if p), "messages": out}

    def build_request(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[ToolSpec]] = None,
        options: Optional[Dict[str, Any]] = None,
        strip_thinking: bool = False,
    ) -> Dict[str, Any]:
        """Build the request body and beta list.

        Returns:
            Dict with ``body`` and ``betas``
        """
        options = options or {}
        modern = is_modern_model(self._model_name)
        converted = self.convert_messages(messages, strip_thinking=strip_thinking)
        betas: List[str] = []

        body: Dict[str, Any] = {
            "model": self._model_name,
            "messages": converted["messages"],
            "max_tokens": options.get("max_tokens") or (64000 if modern else 8192),
            "stream": True,
            "cache_control": {"type": "ephemeral"},
        }
        if converted["system"]:
            body["system"] = converted["system"]

        if tools:
            body["tools"] = []
            for tool in tools:
                spec = {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.parameters
                    or {"type": "object", "properties": {}},
                }
                if modern:
                    spec["eager_input_streaming"] = True
                body["tools"].append(spec)

        if modern:
            body["thinking"] = {
                "type": "adaptive",
                "display": "summarized",
                "block_binding": {"prefix_mismatch_behavior": "drop_block"},
            }
            betas.append(BETA_THINKING_BINDING)
            if self.effort:
                body["output_config"] = {"effort": self.effort}
        elif "temperature" in options:
            body["temperature"] = options["temperature"]

        if self._model_name in FALLBACK_MODELS and self._is_first_party:
            body["fallbacks"] = "default"
            betas.append(BETA_FALLBACK)

        return {"body": body, "betas": betas}

    # --- Streaming ------------------------------------------------------------

    def _sleep(self, seconds: float):
        """Sleep between retries (patched in tests)."""
        time.sleep(seconds)

    def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[ToolSpec]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Any]:
        """Stream one response from the Messages API."""
        strip_thinking = False
        attempt = 0
        while True:
            request = self.build_request(messages, tools, options, strip_thinking)
            try:
                conn, response = self.endpoint.request(
                    "POST",
                    "/v1/messages",
                    request["body"],
                    self._headers(request["betas"]),
                )
            except HttpStatusError as e:
                if e.status == 401:
                    raise ProviderError(
                        "Anthropic rejected the API key (401). "
                        "Run `kubrick auth login anthropic` to set a new one."
                    ) from e
                if e.status == 400 and "signature" in e.body and not strip_thinking:
                    strip_thinking = True
                    continue
                if e.status in RETRYABLE_STATUSES and attempt < MAX_RETRIES:
                    attempt += 1
                    self._sleep(2**attempt)
                    continue
                raise ProviderError(f"Anthropic API error: {e}") from e
            try:
                yield from self._parse_stream(response)
            finally:
                conn.close()
            return

    def _parse_stream(self, response) -> Iterator[Any]:
        blocks: Dict[int, Dict[str, Any]] = {}
        partial_json: Dict[int, str] = {}
        usage = Usage()
        stop_reason: Optional[str] = None
        stop_details: Optional[Dict[str, Any]] = None

        for data in iter_sse_data(response):
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue
            etype = event.get("type")

            if etype == "message_start":
                u = (event.get("message") or {}).get("usage") or {}
                usage.input_tokens = u.get("input_tokens", 0) or 0
                usage.cache_read_tokens = u.get("cache_read_input_tokens", 0) or 0
                usage.cache_write_tokens = u.get("cache_creation_input_tokens", 0) or 0
                usage.output_tokens = u.get("output_tokens", 0) or 0

            elif etype == "content_block_start":
                index = event.get("index", len(blocks))
                block = dict(event.get("content_block") or {})
                if block.get("type") == "tool_use":
                    block["input"] = {}
                    partial_json[index] = ""
                blocks[index] = block
                if block.get("type") == "text" and block.get("text"):
                    yield TextDelta(block["text"])

            elif etype == "content_block_delta":
                index = event.get("index")
                block = blocks.get(index)
                delta = event.get("delta") or {}
                dtype = delta.get("type")
                if block is None:
                    continue
                if dtype == "text_delta":
                    text = delta.get("text", "")
                    block["text"] = block.get("text", "") + text
                    if text:
                        yield TextDelta(text)
                elif dtype == "thinking_delta":
                    text = delta.get("thinking", "")
                    block["thinking"] = block.get("thinking", "") + text
                    if text:
                        yield ThinkingDelta(text)
                elif dtype == "signature_delta":
                    block["signature"] = block.get("signature", "") + delta.get(
                        "signature", ""
                    )
                elif dtype == "input_json_delta":
                    partial_json[index] = partial_json.get(index, "") + delta.get(
                        "partial_json", ""
                    )

            elif etype == "content_block_stop":
                index = event.get("index")
                block = blocks.get(index)
                if block is not None and block.get("type") == "tool_use":
                    raw_args = partial_json.pop(index, "")
                    try:
                        args = parse_arguments(raw_args)
                        block["input"] = args
                        call = ToolCall(
                            block.get("id", ""), block.get("name", ""), args
                        )
                    except ValueError as e:
                        block["input"] = {}
                        call = ToolCall(
                            block.get("id", ""),
                            block.get("name", ""),
                            {},
                            parse_error=f"invalid tool input JSON: {e}",
                        )
                    yield ToolCallEvent(call)

            elif etype == "message_delta":
                delta = event.get("delta") or {}
                if delta.get("stop_reason"):
                    stop_reason = delta["stop_reason"]
                if delta.get("stop_details"):
                    stop_details = delta["stop_details"]
                u = event.get("usage") or {}
                if "output_tokens" in u:
                    usage.output_tokens = u["output_tokens"] or 0
                if u.get("input_tokens"):
                    usage.input_tokens = u["input_tokens"]

            elif etype == "error":
                err = event.get("error") or {}
                raise ProviderError(
                    f"Anthropic stream error: {err.get('type', 'error')}: {err.get('message', '')}"
                )

            elif etype == "message_stop":
                break

        content = [blocks[i] for i in sorted(blocks)]
        # Tool-use blocks with unparseable input are replayed with empty input
        # so the history stays valid; the error result tells the model why.
        normalized = _normalize_stop_reason(stop_reason)
        detail = None
        if normalized == "refusal":
            details = stop_details or {}
            category = details.get("category")
            explanation = details.get("explanation")
            parts = [
                p for p in (category and f"category: {category}", explanation) if p
            ]
            detail = "; ".join(parts) or "The model declined this request."
        yield MessageDone(
            stop_reason=normalized,
            usage=usage,
            raw={
                "provider": "anthropic",
                "model": self._model_name,
                "content": content,
            },
            detail=detail,
        )

    # --- Model info -----------------------------------------------------------

    def _auth_headers(self) -> Dict[str, str]:
        return {"x-api-key": self.api_key or "", "anthropic-version": API_VERSION}

    def is_healthy(self) -> bool:
        """Check that the API is reachable and the key is accepted."""
        try:
            self.endpoint.get_json(
                "/v1/models", headers=self._auth_headers(), timeout=10
            )
            return True
        except Exception:
            return False

    def list_models(self) -> List[str]:
        """Model ids available to this key."""
        try:
            data = self.endpoint.get_json(
                "/v1/models?limit=100", headers=self._auth_headers(), timeout=10
            )
        except Exception:
            return []
        return [m.get("id") for m in data.get("data", []) if m.get("id")]

    def context_window(self) -> Optional[int]:
        """Context window from the Models API (``max_input_tokens``), cached per model."""
        model = self._model_name
        if model not in self._context_windows:
            try:
                data = self.endpoint.get_json(
                    f"/v1/models/{model}", headers=self._auth_headers(), timeout=10
                )
                value = data.get("max_input_tokens")
                self._context_windows[model] = int(value) if value else None
            except Exception:
                self._context_windows[model] = None
        return self._context_windows[model]
