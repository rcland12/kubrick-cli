"""Unit tests for the Anthropic provider (no network)."""

import json
from unittest.mock import Mock

import pytest

from kubrick_cli.messages import (
    MessageDone,
    TextDelta,
    ThinkingDelta,
    ToolCallEvent,
    ToolSpec,
)
from kubrick_cli.providers.anthropic_provider import (
    BETA_FALLBACK,
    BETA_THINKING_BINDING,
    AnthropicProvider,
    is_modern_model,
)
from kubrick_cli.providers.base import ProviderError
from kubrick_cli.providers.http import HttpStatusError

TOOLS = [ToolSpec("read_file", "Read a file", {"type": "object", "properties": {}})]


def sse(*events):
    """Encode events as an SSE byte stream split into small chunks."""
    payload = "".join(
        f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events
    ).encode("utf-8")
    chunks = [payload[i : i + 37] for i in range(0, len(payload), 37)] + [b""]
    response = Mock()
    response.read.side_effect = chunks
    return response


def fake_request(*responses):
    """Patchable endpoint.request returning queued responses or raising errors."""
    calls = []
    queue = list(responses)

    def request(method, path, body=None, headers=None, timeout=None):
        calls.append({"method": method, "path": path, "body": body, "headers": headers})
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return Mock(), item

    return request, calls


def make(model="claude-opus-5-5", **kwargs):
    provider = AnthropicProvider(api_key="sk-test", model=model, **kwargs)
    provider._sleep = lambda s: None
    return provider


SIMPLE_STREAM = [
    {"type": "message_start", "message": {"usage": {"input_tokens": 10}}},
    {
        "type": "content_block_start",
        "index": 0,
        "content_block": {"type": "text", "text": ""},
    },
    {
        "type": "content_block_delta",
        "index": 0,
        "delta": {"type": "text_delta", "text": "Hi"},
    },
    {"type": "content_block_stop", "index": 0},
    {
        "type": "message_delta",
        "delta": {"stop_reason": "end_turn"},
        "usage": {"output_tokens": 2},
    },
    {"type": "message_stop"},
]


class TestModelDetection:
    @pytest.mark.parametrize(
        "model,modern",
        [
            ("claude-opus-5-5", True),
            ("claude-sonnet-5-5", True),
            ("claude-haiku-5-5", True),
            ("claude-fable-5-1", True),
            ("claude-opus-4-6", True),
            ("claude-sonnet-4-6", True),
            ("claude-opus-4-8", True),
            ("claude-sonnet-4-5-20250929", False),
            ("claude-opus-4-1-20250805", False),
            ("claude-haiku-4-5", False),
            ("claude-haiku-4-5-20251001", False),
            ("claude-3-5-sonnet-20241022", False),
            ("claude-3-opus-20240229", False),
            ("claude-something-new", True),
            ("us.anthropic.claude-sonnet-4-5-20250929-v1:0", False),
        ],
    )
    def test_is_modern(self, model, modern):
        assert is_modern_model(model) is modern


class TestConversion:
    def test_system_tools_and_grouping(self):
        provider = make()
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hello"},
            {
                "role": "assistant",
                "content": "Reading",
                "tool_calls": [
                    {"id": "t1", "name": "read_file", "arguments": {"file_path": "a"}},
                    {"id": "t2", "name": "read_file", "arguments": {"file_path": "b"}},
                ],
            },
            {"role": "tool", "tool_call_id": "t1", "name": "read_file", "content": "A"},
            {
                "role": "tool",
                "tool_call_id": "t2",
                "name": "read_file",
                "content": "nope",
                "is_error": True,
            },
            {"role": "system", "content": "reminder"},
        ]
        converted = provider.convert_messages(messages)
        assert converted["system"] == "sys"
        msgs = converted["messages"]
        assert [m["role"] for m in msgs] == ["user", "assistant", "user", "user"]
        assistant = msgs[1]["content"]
        assert assistant[0] == {"type": "text", "text": "Reading"}
        assert assistant[1]["type"] == "tool_use" and assistant[1]["input"] == {
            "file_path": "a"
        }
        results = msgs[2]["content"]
        assert len(results) == 2
        assert results[0] == {
            "type": "tool_result",
            "tool_use_id": "t1",
            "content": "A",
        }
        assert results[1]["is_error"] is True
        assert (
            "<system-reminder>reminder</system-reminder>"
            in msgs[3]["content"][0]["text"]
        )

    def test_raw_replay_same_model(self):
        provider = make()
        raw_blocks = [
            {"type": "thinking", "thinking": "", "signature": "sig"},
            {"type": "text", "text": "ok"},
        ]
        messages = [
            {"role": "user", "content": "q"},
            {
                "role": "assistant",
                "content": "ok",
                "raw": {
                    "provider": "anthropic",
                    "model": "claude-opus-5-5",
                    "content": raw_blocks,
                },
            },
        ]
        msgs = provider.convert_messages(messages)["messages"]
        assert msgs[1]["content"] == raw_blocks
        stripped = provider.convert_messages(messages, strip_thinking=True)["messages"]
        assert stripped[1]["content"] == [{"type": "text", "text": "ok"}]

    def test_raw_ignored_for_other_model(self):
        provider = make(model="claude-sonnet-5-5")
        messages = [
            {"role": "user", "content": "q"},
            {
                "role": "assistant",
                "content": "ok",
                "raw": {
                    "provider": "anthropic",
                    "model": "claude-opus-5-5",
                    "content": [{"type": "thinking", "thinking": "", "signature": "x"}],
                },
            },
        ]
        msgs = provider.convert_messages(messages)["messages"]
        assert msgs[1]["content"] == [{"type": "text", "text": "ok"}]

    def test_empty_assistant_skipped(self):
        provider = make()
        msgs = provider.convert_messages(
            [{"role": "user", "content": "q"}, {"role": "assistant", "content": ""}]
        )["messages"]
        assert len(msgs) == 1

    def test_fallback_echo_rule(self):
        provider = make()
        raw_blocks = [
            {"type": "thinking", "thinking": "", "signature": "a"},
            {"type": "text", "text": "partial"},
            {"type": "tool_use", "id": "x", "name": "n", "input": {}},
            {"type": "fallback", "from": {"model": "a"}, "to": {"model": "b"}},
            {"type": "thinking", "thinking": "", "signature": "b"},
            {"type": "text", "text": "rest"},
        ]
        messages = [
            {"role": "user", "content": "q"},
            {
                "role": "assistant",
                "content": "",
                "raw": {
                    "provider": "anthropic",
                    "model": "claude-opus-5-5",
                    "content": raw_blocks,
                },
            },
        ]
        blocks = provider.convert_messages(messages)["messages"][1]["content"]
        assert [b["type"] for b in blocks] == ["text", "fallback", "thinking", "text"]


class TestRequestBody:
    def test_modern_body(self):
        provider = make()
        req = provider.build_request(
            [{"role": "user", "content": "q"}], TOOLS, {"temperature": 0.2}
        )
        body = req["body"]
        assert body["thinking"]["type"] == "adaptive"
        assert body["thinking"]["block_binding"] == {
            "prefix_mismatch_behavior": "drop_block"
        }
        assert body["output_config"] == {"effort": "high"}
        assert "temperature" not in body
        assert body["tools"][0]["eager_input_streaming"] is True
        assert body["max_tokens"] == 64000
        assert body["cache_control"] == {"type": "ephemeral"}
        assert body["fallbacks"] == "default"
        assert req["betas"] == [BETA_THINKING_BINDING, BETA_FALLBACK]

    def test_no_fallbacks_through_gateway(self):
        provider = make(base_url="https://gateway.example.com")
        req = provider.build_request([{"role": "user", "content": "q"}])
        assert "fallbacks" not in req["body"]
        assert BETA_FALLBACK not in req["betas"]

    def test_no_fallbacks_for_other_modern_models(self):
        provider = make(model="claude-opus-4-8")
        req = provider.build_request([{"role": "user", "content": "q"}])
        assert "fallbacks" not in req["body"]
        assert req["body"]["thinking"]["type"] == "adaptive"

    def test_legacy_body(self):
        provider = make(model="claude-sonnet-4-5-20250929")
        req = provider.build_request(
            [{"role": "user", "content": "q"}],
            TOOLS,
            {"temperature": 0.2, "max_tokens": 100},
        )
        body = req["body"]
        assert "thinking" not in body
        assert "output_config" not in body
        assert body["temperature"] == 0.2
        assert "eager_input_streaming" not in body["tools"][0]
        assert body["max_tokens"] == 100
        assert req["betas"] == []

    def test_effort_omitted_when_empty(self):
        provider = make(effort="")
        body = provider.build_request([{"role": "user", "content": "q"}])["body"]
        assert "output_config" not in body

    def test_headers(self):
        provider = make()
        request, calls = fake_request(sse(*SIMPLE_STREAM))
        provider.endpoint.request = request
        list(provider.stream_chat([{"role": "user", "content": "q"}]))
        headers = calls[0]["headers"]
        assert headers["x-api-key"] == "sk-test"
        assert headers["anthropic-version"] == "2023-06-01"
        assert headers["anthropic-beta"] == f"{BETA_THINKING_BINDING},{BETA_FALLBACK}"
        assert calls[0]["path"] == "/v1/messages"


class TestStreaming:
    def test_text_thinking_tool_use(self):
        events = [
            {
                "type": "message_start",
                "message": {
                    "usage": {"input_tokens": 5, "cache_read_input_tokens": 100}
                },
            },
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "thinking", "thinking": "", "signature": ""},
            },
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "thinking_delta", "thinking": "hmm"},
            },
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "signature_delta", "signature": "SIG"},
            },
            {"type": "content_block_stop", "index": 0},
            {
                "type": "content_block_start",
                "index": 1,
                "content_block": {"type": "text", "text": ""},
            },
            {
                "type": "content_block_delta",
                "index": 1,
                "delta": {"type": "text_delta", "text": "Héllo "},
            },
            {
                "type": "content_block_delta",
                "index": 1,
                "delta": {"type": "text_delta", "text": "world"},
            },
            {"type": "content_block_stop", "index": 1},
            {
                "type": "content_block_start",
                "index": 2,
                "content_block": {
                    "type": "tool_use",
                    "id": "tu1",
                    "name": "read_file",
                    "input": {},
                },
            },
            {
                "type": "content_block_delta",
                "index": 2,
                "delta": {"type": "input_json_delta", "partial_json": '{"file_'},
            },
            {
                "type": "content_block_delta",
                "index": 2,
                "delta": {"type": "input_json_delta", "partial_json": 'path": "a.py"}'},
            },
            {"type": "content_block_stop", "index": 2},
            {
                "type": "message_delta",
                "delta": {"stop_reason": "tool_use"},
                "usage": {"output_tokens": 42},
            },
            {"type": "message_stop"},
        ]
        provider = make()
        request, _ = fake_request(sse(*events))
        provider.endpoint.request = request
        out = list(provider.stream_chat([{"role": "user", "content": "q"}], TOOLS))

        thinking = [e.text for e in out if isinstance(e, ThinkingDelta)]
        text = "".join(e.text for e in out if isinstance(e, TextDelta))
        calls = [e.call for e in out if isinstance(e, ToolCallEvent)]
        done = [e for e in out if isinstance(e, MessageDone)]

        assert thinking == ["hmm"]
        assert text == "Héllo world"
        assert len(calls) == 1
        assert calls[0].id == "tu1" and calls[0].arguments == {"file_path": "a.py"}
        assert calls[0].parse_error is None
        assert len(done) == 1 and isinstance(out[-1], MessageDone)
        assert done[0].stop_reason == "tool_use"
        assert done[0].usage.input_tokens == 5
        assert done[0].usage.cache_read_tokens == 100
        assert done[0].usage.output_tokens == 42
        raw = done[0].raw
        assert raw["provider"] == "anthropic" and raw["model"] == "claude-opus-5-5"
        assert raw["content"][0] == {
            "type": "thinking",
            "thinking": "hmm",
            "signature": "SIG",
        }
        assert raw["content"][1] == {"type": "text", "text": "Héllo world"}
        assert raw["content"][2]["input"] == {"file_path": "a.py"}

    def test_invalid_tool_json(self):
        events = [
            {"type": "message_start", "message": {"usage": {}}},
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {
                    "type": "tool_use",
                    "id": "tu1",
                    "name": "write_file",
                    "input": {},
                },
            },
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {
                    "type": "input_json_delta",
                    "partial_json": '{"content": "unterminated',
                },
            },
            {"type": "content_block_stop", "index": 0},
            {
                "type": "message_delta",
                "delta": {"stop_reason": "max_tokens"},
                "usage": {},
            },
            {"type": "message_stop"},
        ]
        provider = make()
        request, _ = fake_request(sse(*events))
        provider.endpoint.request = request
        out = list(provider.stream_chat([{"role": "user", "content": "q"}], TOOLS))
        call = [e.call for e in out if isinstance(e, ToolCallEvent)][0]
        assert call.parse_error and "invalid tool input JSON" in call.parse_error
        assert call.arguments == {}
        assert out[-1].stop_reason == "max_tokens"
        assert out[-1].raw["content"][0]["input"] == {}

    def test_refusal(self):
        events = [
            {"type": "message_start", "message": {"usage": {}}},
            {
                "type": "message_delta",
                "delta": {
                    "stop_reason": "refusal",
                    "stop_details": {
                        "type": "refusal",
                        "category": "cyber",
                        "explanation": None,
                    },
                },
                "usage": {"output_tokens": 0},
            },
            {"type": "message_stop"},
        ]
        provider = make()
        request, _ = fake_request(sse(*events))
        provider.endpoint.request = request
        out = list(provider.stream_chat([{"role": "user", "content": "q"}]))
        assert out[-1].stop_reason == "refusal"
        assert "cyber" in out[-1].detail

    def test_stop_sequence_normalized_and_unknown_block_kept(self):
        events = [
            {"type": "message_start", "message": {"usage": {}}},
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {
                    "type": "fallback",
                    "from": {"model": "a"},
                    "to": {"model": "b"},
                },
            },
            {"type": "content_block_stop", "index": 0},
            {
                "type": "message_delta",
                "delta": {"stop_reason": "stop_sequence"},
                "usage": {},
            },
            {"type": "message_stop"},
        ]
        provider = make()
        request, _ = fake_request(sse(*events))
        provider.endpoint.request = request
        out = list(provider.stream_chat([{"role": "user", "content": "q"}]))
        assert out[-1].stop_reason == "end_turn"
        assert out[-1].raw["content"][0]["type"] == "fallback"

    def test_error_event(self):
        events = [
            {"type": "message_start", "message": {"usage": {}}},
            {"type": "error", "error": {"type": "overloaded_error", "message": "busy"}},
        ]
        provider = make()
        request, _ = fake_request(sse(*events))
        provider.endpoint.request = request
        with pytest.raises(ProviderError, match="overloaded_error"):
            list(provider.stream_chat([{"role": "user", "content": "q"}]))


class TestErrors:
    def test_retry_on_529(self):
        provider = make()
        request, calls = fake_request(
            HttpStatusError(529, '{"error": {"message": "Overloaded"}}'),
            sse(*SIMPLE_STREAM),
        )
        provider.endpoint.request = request
        out = list(provider.stream_chat([{"role": "user", "content": "q"}]))
        assert len(calls) == 2
        assert "".join(e.text for e in out if isinstance(e, TextDelta)) == "Hi"

    def test_retries_exhausted(self):
        provider = make()
        err = HttpStatusError(429, '{"error": {"message": "rate limited"}}')
        request, calls = fake_request(err, err, err)
        provider.endpoint.request = request
        with pytest.raises(ProviderError, match="rate limited"):
            list(provider.stream_chat([{"role": "user", "content": "q"}]))
        assert len(calls) == 3

    def test_signature_400_strips_thinking_and_retries(self):
        provider = make()
        messages = [
            {"role": "user", "content": "q"},
            {
                "role": "assistant",
                "content": "ok",
                "raw": {
                    "provider": "anthropic",
                    "model": "claude-opus-5-5",
                    "content": [
                        {"type": "thinking", "thinking": "", "signature": "bad"},
                        {"type": "text", "text": "ok"},
                    ],
                },
            },
            {"role": "user", "content": "next"},
        ]
        err = HttpStatusError(
            400,
            '{"error": {"message": "messages.1.content.0: Invalid `signature` in `thinking`"}}',
        )
        request, calls = fake_request(err, sse(*SIMPLE_STREAM))
        provider.endpoint.request = request
        list(provider.stream_chat(messages))
        assert len(calls) == 2
        assert calls[0]["body"]["messages"][1]["content"][0]["type"] == "thinking"
        assert calls[1]["body"]["messages"][1]["content"] == [
            {"type": "text", "text": "ok"}
        ]

    def test_401_message(self):
        provider = make()
        request, _ = fake_request(
            HttpStatusError(401, '{"error": {"message": "invalid x-api-key"}}')
        )
        provider.endpoint.request = request
        with pytest.raises(ProviderError, match="kubrick auth login anthropic"):
            list(provider.stream_chat([{"role": "user", "content": "q"}]))

    def test_other_400_not_retried(self):
        provider = make()
        request, calls = fake_request(
            HttpStatusError(400, '{"error": {"message": "bad"}}')
        )
        provider.endpoint.request = request
        with pytest.raises(ProviderError, match="bad"):
            list(provider.stream_chat([{"role": "user", "content": "q"}]))
        assert len(calls) == 1


class TestModelInfo:
    def test_context_window_cached(self):
        provider = make()
        provider.endpoint.get_json = Mock(return_value={"max_input_tokens": 1000000})
        assert provider.context_window() == 1000000
        assert provider.context_window() == 1000000
        assert provider.endpoint.get_json.call_count == 1

    def test_context_window_failure(self):
        provider = make()
        provider.endpoint.get_json = Mock(side_effect=ProviderError("down"))
        assert provider.context_window() is None

    def test_list_models_and_health(self):
        provider = make()
        provider.endpoint.get_json = Mock(
            return_value={
                "data": [{"id": "claude-opus-5-5"}, {"id": "claude-haiku-5-5"}]
            }
        )
        assert provider.list_models() == ["claude-opus-5-5", "claude-haiku-5-5"]
        assert provider.is_healthy() is True
        provider.endpoint.get_json = Mock(side_effect=ProviderError("down"))
        assert provider.is_healthy() is False
        assert provider.list_models() == []

    def test_generate_text_only(self):
        provider = make()
        request, calls = fake_request(sse(*SIMPLE_STREAM))
        provider.endpoint.request = request
        assert provider.generate([{"role": "user", "content": "q"}]) == "Hi"
        assert "tools" not in calls[0]["body"]
