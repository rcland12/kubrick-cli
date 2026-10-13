"""OpenAI and OpenAI-compatible (Ollama, vLLM, llama.cpp, LM Studio) providers."""

import json
import re
import uuid
from typing import Any, Dict, Iterator, List, Optional

from ..messages import (
    TextDelta,
    ThinkTagSplitter,
    MessageDone,
    ThinkingDelta,
    ToolCall,
    ToolCallEvent,
    ToolSpec,
    Usage,
    parse_arguments,
)
from .base import (
    ProviderAdapter,
    ProviderError,
    ProviderMetadata,
    ToolsNotSupportedError,
)
from .http import HttpEndpoint, HttpStatusError, iter_sse_data


def normalize_server_url(url: str) -> str:
    """Turn what people type for a local server into an OpenAI API base URL.

    ``192.168.1.5:11434`` -> ``http://192.168.1.5:11434/v1``. A URL that
    already has a path (``https://gateway/openai``) is left alone.
    """
    url = (url or "").strip().rstrip("/")
    if not url:
        return url
    if "://" not in url:
        url = f"http://{url}"
    scheme, _, rest = url.partition("://")
    if "/" not in rest:
        url = f"{scheme}://{rest}/v1"
    return url


_FINISH_REASONS = {
    "stop": "end_turn",
    "tool_calls": "tool_use",
    "function_call": "tool_use",
    "length": "max_tokens",
    "content_filter": "refusal",
}

# Phrases servers use when a model/deployment can't take `tools`.
_NO_TOOLS_MARKERS = (
    "does not support tools",
    "tools are not supported",
    "tool-call-parser",
    "enable-auto-tool-choice",
    "tool choice",
    "tool_choice",
)

# Hermes/Qwen-style tool calls that leak into content when the server has no
# tool-call parser configured.
_TEXT_TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)


class _ChatCompletionsProvider(ProviderAdapter):
    """Shared implementation of the ``/chat/completions`` streaming protocol."""

    #: Request field for the output cap (OpenAI's newer models reject max_tokens).
    max_tokens_field = "max_tokens"

    def __init__(self, base_url: str, api_key: Optional[str], model: str):
        self.endpoint = HttpEndpoint(base_url)
        self.api_key = api_key or None
        self._model_name = model
        self._send_stream_usage = True
        self._context_window: Optional[int] = None
        self._context_window_probed = False

    # --- ProviderAdapter -----------------------------------------------------

    @property
    def model_name(self) -> str:
        return self._model_name

    def set_model(self, model_name: str):
        self._model_name = model_name
        self._context_window_probed = False

    def is_healthy(self) -> bool:
        try:
            self.endpoint.get_json("/models", headers=self._headers())
            return True
        except Exception:
            return False

    def list_models(self) -> List[str]:
        try:
            data = self.endpoint.get_json("/models", headers=self._headers())
        except Exception:
            return []
        return sorted(m.get("id", "") for m in data.get("data", []) if m.get("id"))

    def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[ToolSpec]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Any]:
        body = self._build_body(messages, tools, options or {})
        try:
            conn, response = self.endpoint.request(
                "POST", "/chat/completions", body=body, headers=self._headers()
            )
        except HttpStatusError as e:
            lowered = e.body.lower()
            if self._send_stream_usage and "stream_options" in lowered:
                # Older servers reject stream_options; retry once without it.
                self._send_stream_usage = False
                yield from self.stream_chat(messages, tools, options)
                return
            if tools and any(marker in lowered for marker in _NO_TOOLS_MARKERS):
                raise ToolsNotSupportedError(str(e)) from e
            if e.status == 401:
                raise ProviderError(
                    f"{e} — check the API key (`kubrick auth login {self.provider_name}`)"
                ) from e
            raise
        try:
            yield from self._parse_stream(response)
        finally:
            conn.close()

    # --- Request building ----------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "text/event-stream"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _build_body(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[ToolSpec]],
        options: Dict,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "model": self._model_name,
            "messages": self.convert_messages(messages),
            "stream": True,
        }
        if self._send_stream_usage:
            body["stream_options"] = {"include_usage": True}
        if tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
        if options.get("max_tokens"):
            body[self.max_tokens_field] = options["max_tokens"]
        if options.get("temperature") is not None:
            body["temperature"] = options["temperature"]
        return body

    @staticmethod
    def convert_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert provider-neutral messages to Chat Completions messages."""
        converted = []
        for msg in messages:
            role = msg["role"]
            if role == "assistant":
                out: Dict[str, Any] = {
                    "role": "assistant",
                    "content": msg.get("content") or "",
                }
                if msg.get("tool_calls"):
                    out["tool_calls"] = [
                        {
                            "id": call["id"],
                            "type": "function",
                            "function": {
                                "name": call["name"],
                                "arguments": json.dumps(call["arguments"]),
                            },
                        }
                        for call in msg["tool_calls"]
                    ]
                converted.append(out)
            elif role == "tool":
                content = msg.get("content") or ""
                if msg.get("is_error"):
                    content = f"Error: {content}"
                converted.append(
                    {
                        "role": "tool",
                        "tool_call_id": msg["tool_call_id"],
                        "content": content,
                    }
                )
            else:
                converted.append({"role": role, "content": msg.get("content") or ""})
        return converted

    # --- Response parsing ----------------------------------------------------

    def _parse_stream(self, response) -> Iterator[Any]:
        splitter = ThinkTagSplitter()
        calls: Dict[int, Dict[str, str]] = {}
        text_parts: List[str] = []
        finish_reason = None
        usage = None

        for data in iter_sse_data(response):
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            if chunk.get("error"):
                err = chunk["error"]
                raise ProviderError(
                    err.get("message", str(err)) if isinstance(err, dict) else err
                )
            if chunk.get("usage"):
                u = chunk["usage"]
                cached = (u.get("prompt_tokens_details") or {}).get(
                    "cached_tokens"
                ) or 0
                usage = Usage(
                    input_tokens=(u.get("prompt_tokens") or 0) - cached,
                    output_tokens=u.get("completion_tokens") or 0,
                    cache_read_tokens=cached,
                )
            for choice in chunk.get("choices") or []:
                delta = choice.get("delta") or {}
                reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                if reasoning:
                    yield ThinkingDelta(reasoning)
                if delta.get("content"):
                    text_parts.append(delta["content"])
                    yield from splitter.feed(delta["content"])
                for tc in delta.get("tool_calls") or []:
                    self._accumulate_tool_call(calls, tc)
                if choice.get("finish_reason"):
                    finish_reason = choice["finish_reason"]

        yield from splitter.flush()

        tool_calls = [self._finish_tool_call(calls[i]) for i in sorted(calls)]
        if not tool_calls:
            tool_calls = self._tool_calls_from_text("".join(text_parts))
        for call in tool_calls:
            yield ToolCallEvent(call)

        stop = _FINISH_REASONS.get(finish_reason or "stop", finish_reason or "end_turn")
        if tool_calls and stop == "end_turn":
            # Several local servers report "stop" even when they returned tool calls.
            stop = "tool_use"
        yield MessageDone(stop_reason=stop, usage=usage)

    @staticmethod
    def _accumulate_tool_call(calls: Dict[int, Dict[str, str]], tc: Dict[str, Any]):
        index = tc.get("index")
        if index is None:
            # Servers that omit the index send each call whole, or continue the last one.
            if tc.get("id") and all(c["id"] != tc["id"] for c in calls.values()):
                index = len(calls)
            else:
                index = max(calls) if calls else 0
        entry = calls.setdefault(index, {"id": "", "name": "", "arguments": ""})
        if tc.get("id"):
            entry["id"] = tc["id"]
        fn = tc.get("function") or {}
        if fn.get("name") and not entry["name"]:
            entry["name"] = fn["name"]
        args = fn.get("arguments")
        if isinstance(args, dict):  # some servers send parsed objects
            entry["arguments"] = json.dumps(args)
        elif args:
            entry["arguments"] += args

    @staticmethod
    def _finish_tool_call(entry: Dict[str, str]) -> ToolCall:
        call_id = entry["id"] or f"call_{uuid.uuid4().hex[:12]}"
        try:
            return ToolCall(call_id, entry["name"], parse_arguments(entry["arguments"]))
        except ValueError as e:
            return ToolCall(
                call_id, entry["name"], {}, parse_error=f"invalid arguments: {e}"
            )

    @staticmethod
    def _tool_calls_from_text(text: str) -> List[ToolCall]:
        """Recover Hermes-style ``<tool_call>`` blocks the server didn't parse."""
        calls = []
        for match in _TEXT_TOOL_CALL_RE.finditer(text):
            call_id = f"call_{uuid.uuid4().hex[:12]}"
            try:
                data = json.loads(match.group(1))
                args = data.get("arguments", data.get("parameters", {}))
                if isinstance(args, str):
                    args = parse_arguments(args)
                calls.append(ToolCall(call_id, data["name"], args))
            except (ValueError, KeyError, TypeError, AttributeError) as e:
                calls.append(
                    ToolCall(call_id, "unknown", {}, parse_error=f"invalid call: {e}")
                )
        return calls


class OpenAIProvider(_ChatCompletionsProvider):
    """Provider adapter for the hosted OpenAI API."""

    METADATA = ProviderMetadata(
        name="openai",
        display_name="OpenAI (GPT)",
        description="OpenAI API (GPT models)",
        config_fields=[
            {
                "key": "openai_api_key",
                "label": "OpenAI API key",
                "type": "secret",
                "env": ["OPENAI_API_KEY"],
                "help_text": "Get your API key from: https://platform.openai.com/api-keys",
            },
            {
                "key": "openai_model",
                "label": "Model",
                "type": "model",
                "default": "gpt-5",
            },
            {
                "key": "openai_base_url",
                "label": "API base URL",
                "type": "url",
                "default": "https://api.openai.com/v1",
                "help_text": "Change only for a proxy or gateway in front of OpenAI.",
                "advanced": True,
            },
        ],
    )

    max_tokens_field = "max_completion_tokens"

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-5",
        base_url: str = "https://api.openai.com/v1",
    ):
        super().__init__(base_url=base_url, api_key=api_key, model=model)
        # The Responses API supports tools together with reasoning on every current
        # model; Chat Completions is the fallback for gateways without /responses.
        self.use_responses_api = True

    @property
    def provider_name(self) -> str:
        return "openai"

    def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[ToolSpec]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Any]:
        if not self.use_responses_api:
            yield from super().stream_chat(messages, tools, options)
            return
        body = self._responses_body(messages, tools, options or {})
        try:
            conn, response = self.endpoint.request(
                "POST", "/responses", body=body, headers=self._headers()
            )
        except HttpStatusError as e:
            if e.status in (404, 405):
                self.use_responses_api = False
                yield from super().stream_chat(messages, tools, options)
                return
            if e.status == 401:
                raise ProviderError(
                    f"{e} — check the API key (`kubrick auth login openai`)"
                ) from e
            raise
        try:
            yield from self._parse_responses_stream(response)
        finally:
            conn.close()

    # --- Responses API -------------------------------------------------------

    def _responses_body(self, messages, tools, options) -> Dict[str, Any]:
        system = [m.get("content") or "" for m in messages if m["role"] == "system"]
        body: Dict[str, Any] = {
            "model": self._model_name,
            "input": self._responses_input(messages),
            "stream": True,
            # Stateless: replay encrypted reasoning ourselves instead of storing it.
            "store": False,
            "include": ["reasoning.encrypted_content"],
            "reasoning": {"summary": "auto"},
        }
        if system:
            body["instructions"] = "\n\n".join(system)
        if tools:
            body["tools"] = [
                {
                    "type": "function",
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                }
                for t in tools
            ]
        if options.get("max_tokens"):
            body["max_output_tokens"] = options["max_tokens"]
        return body

    def _responses_input(self, messages) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for msg in messages:
            role = msg["role"]
            if role == "system":
                continue
            if role == "tool":
                content = msg.get("content") or ""
                if msg.get("is_error"):
                    content = f"Error: {content}"
                items.append(
                    {
                        "type": "function_call_output",
                        "call_id": msg["tool_call_id"],
                        "output": content,
                    }
                )
                continue
            if role == "assistant":
                raw = msg.get("raw")
                if (
                    isinstance(raw, dict)
                    and raw.get("provider") == "openai_responses"
                    and raw.get("model") == self._model_name
                    and raw.get("content")
                ):
                    # Replay output items verbatim (keeps encrypted reasoning).
                    items.extend(raw["content"])
                    continue
                if msg.get("content"):
                    items.append({"role": "assistant", "content": msg["content"]})
                for call in msg.get("tool_calls") or []:
                    items.append(
                        {
                            "type": "function_call",
                            "call_id": call["id"],
                            "name": call["name"],
                            "arguments": json.dumps(call.get("arguments") or {}),
                        }
                    )
                continue
            items.append({"role": "user", "content": msg.get("content") or ""})
        return items

    def _parse_responses_stream(self, response) -> Iterator[Any]:
        output_items: List[Dict[str, Any]] = []
        calls: List[ToolCall] = []
        usage = None
        stop = "end_turn"
        detail = None
        for data in iter_sse_data(response):
            if data == "[DONE]":
                break
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue
            kind = event.get("type", "")
            if kind == "response.output_text.delta":
                if event.get("delta"):
                    yield TextDelta(event["delta"])
            elif kind in (
                "response.reasoning_summary_text.delta",
                "response.reasoning_text.delta",
            ):
                if event.get("delta"):
                    yield ThinkingDelta(event["delta"])
            elif kind == "response.reasoning_summary_part.done":
                yield ThinkingDelta("\n\n")
            elif kind == "response.output_item.done":
                item = event.get("item") or {}
                output_items.append(item)
                if item.get("type") == "function_call":
                    call = self._responses_tool_call(item)
                    calls.append(call)
                    yield ToolCallEvent(call)
            elif kind in ("response.completed", "response.incomplete"):
                result = event.get("response") or {}
                usage = self._responses_usage(result.get("usage"))
                if kind == "response.incomplete":
                    reason = (result.get("incomplete_details") or {}).get("reason", "")
                    stop = "refusal" if reason == "content_filter" else "max_tokens"
                    detail = f"OpenAI stopped the response ({reason or 'incomplete'})."
            elif kind in ("response.failed", "error"):
                err = (
                    (event.get("response") or {}).get("error")
                    or event.get("error")
                    or event
                )
                message = err.get("message") if isinstance(err, dict) else str(err)
                raise ProviderError(f"OpenAI: {message}")
            elif kind == "response.refusal.delta" and event.get("delta"):
                yield TextDelta(event["delta"])
                stop = "refusal"
        if calls and stop == "end_turn":
            stop = "tool_use"
        yield MessageDone(
            stop_reason=stop,
            usage=usage,
            detail=detail,
            raw={
                "provider": "openai_responses",
                "model": self._model_name,
                "content": [_replayable(item) for item in output_items],
            },
        )

    @staticmethod
    def _responses_tool_call(item: Dict[str, Any]) -> ToolCall:
        call_id = item.get("call_id") or f"call_{uuid.uuid4().hex[:12]}"
        try:
            args = parse_arguments(item.get("arguments") or "{}")
        except ValueError as e:
            return ToolCall(
                call_id, item.get("name", ""), {}, parse_error=f"invalid arguments: {e}"
            )
        return ToolCall(call_id, item.get("name", ""), args)

    @staticmethod
    def _responses_usage(u: Optional[Dict[str, Any]]) -> Optional[Usage]:
        if not u:
            return None
        cached = (u.get("input_tokens_details") or {}).get("cached_tokens") or 0
        return Usage(
            input_tokens=(u.get("input_tokens") or 0) - cached,
            output_tokens=u.get("output_tokens") or 0,
            cache_read_tokens=cached,
        )


def _replayable(item: Dict[str, Any]) -> Dict[str, Any]:
    """An output item as it can be sent back as input (no server-only fields)."""
    return {k: v for k, v in item.items() if k != "status"}


class OpenAICompatibleProvider(_ChatCompletionsProvider):
    """Any server speaking the OpenAI Chat Completions API (local or hosted)."""

    METADATA = ProviderMetadata(
        name="openai_compatible",
        display_name="Local model server",
        description="Ollama, vLLM, llama.cpp, LM Studio, or any OpenAI-compatible API",
        config_fields=[
            {
                "key": "openai_compatible_base_url",
                "label": "Server address",
                "type": "url",
                "default": "http://localhost:11434/v1",
                "help_text": (
                    "host:port of the server, e.g. localhost:11434 or "
                    "192.168.1.50:8000 (http:// and /v1 are added for you)"
                ),
            },
            {
                "key": "openai_compatible_model",
                "label": "Model",
                "type": "model",
                "help_text": "The model ID as the server knows it (e.g. qwen3-coder:30b).",
            },
            {
                "key": "openai_compatible_api_key",
                "label": "API key (leave blank if the server has none)",
                "type": "secret",
                "required": False,
                "env": ["OPENAI_COMPATIBLE_API_KEY"],
            },
        ],
    )

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434/v1",
        api_key: Optional[str] = None,
    ):
        super().__init__(
            base_url=normalize_server_url(base_url), api_key=api_key, model=model
        )

    @property
    def provider_name(self) -> str:
        return "openai_compatible"

    def context_window(self) -> Optional[int]:
        """Ask the server how much context the loaded model has (vLLM, Ollama)."""
        if self._context_window_probed:
            return self._context_window
        self._context_window_probed = True
        self._context_window = self._probe_vllm() or self._probe_ollama()
        return self._context_window

    def _probe_vllm(self) -> Optional[int]:
        try:
            data = self.endpoint.get_json("/models", headers=self._headers(), timeout=5)
        except Exception:
            return None
        for model in data.get("data", []):
            if model.get("id") == self._model_name and model.get("max_model_len"):
                return int(model["max_model_len"])
        return None

    def _probe_ollama(self) -> Optional[int]:
        """Context length of the model as currently loaded by Ollama (``/api/ps``)."""
        root = HttpEndpoint(self.endpoint.url.rsplit("/v1", 1)[0])
        try:
            data = root.get_json("/api/ps", timeout=5)
        except Exception:
            return None
        for model in data.get("models", []):
            names = {model.get("name"), model.get("model")}
            if self._model_name in names and model.get("context_length"):
                return int(model["context_length"])
        return None
