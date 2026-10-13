"""Tests for the OpenAI / OpenAI-compatible providers."""

import json

import pytest

from kubrick_cli.messages import (
    MessageDone,
    TextDelta,
    ThinkingDelta,
    ThinkTagSplitter,
    ToolCallEvent,
    ToolSpec,
)
from kubrick_cli.providers.base import ToolsNotSupportedError
from kubrick_cli.providers.openai_provider import (
    OpenAICompatibleProvider,
    OpenAIProvider,
)
from tests.fake_openai_server import FakeOpenAIServer

TOOLS = [ToolSpec("read_file", "Read", {"type": "object", "properties": {}})]


def collect(provider, messages=None, tools=None):
    return list(
        provider.stream_chat(messages or [{"role": "user", "content": "hi"}], tools)
    )


def test_convert_messages():
    msgs = [
        {"role": "system", "content": "s"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "c1", "name": "read_file", "arguments": {"file_path": "a"}}
            ],
            "raw": {"provider": "anthropic", "content": []},
        },
        {
            "role": "tool",
            "tool_call_id": "c1",
            "name": "read_file",
            "content": "boom",
            "is_error": True,
        },
    ]
    out = OpenAICompatibleProvider.convert_messages(msgs)
    assert out[1]["tool_calls"][0]["function"] == {
        "name": "read_file",
        "arguments": '{"file_path": "a"}',
    }
    assert "raw" not in out[1]
    assert out[2] == {"role": "tool", "tool_call_id": "c1", "content": "Error: boom"}


def test_streams_text_reasoning_tools_and_usage():
    script = [
        {
            "reasoning": "hmm",
            "text": "Hello there",
            "tool_calls": [("read_file", {"file_path": "x.py"})],
        }
    ]
    with FakeOpenAIServer(script) as server:
        provider = OpenAICompatibleProvider(model="m", base_url=server.base_url)
        events = collect(provider, tools=TOOLS)
        body = server.requests[0]
    assert "".join(e.text for e in events if isinstance(e, TextDelta)) == "Hello there"
    assert any(isinstance(e, ThinkingDelta) and e.text == "hmm" for e in events)
    calls = [e.call for e in events if isinstance(e, ToolCallEvent)]
    assert calls[0].name == "read_file" and calls[0].arguments == {"file_path": "x.py"}
    done = events[-1]
    assert isinstance(done, MessageDone) and done.stop_reason == "tool_use"
    assert done.usage.input_tokens == 1000
    assert body["stream_options"] == {"include_usage": True}
    assert body["tools"][0]["function"]["name"] == "read_file"


def test_tools_not_supported_raises():
    with FakeOpenAIServer(
        [{"status": 400, "error": "model does not support tools"}]
    ) as server:
        provider = OpenAICompatibleProvider(model="m", base_url=server.base_url)
        with pytest.raises(ToolsNotSupportedError):
            collect(provider, tools=TOOLS)


def test_retries_without_stream_options():
    script = [
        {"status": 400, "error": "Unrecognized field stream_options"},
        {"text": "ok"},
    ]
    with FakeOpenAIServer(script) as server:
        provider = OpenAICompatibleProvider(model="m", base_url=server.base_url)
        events = collect(provider)
        assert "stream_options" not in server.requests[1]
    assert any(isinstance(e, TextDelta) for e in events)


def test_hermes_tool_call_in_text_is_recovered():
    call_json = '{"name": "read_file", "arguments": {"file_path": "a"}}'
    text = f"Sure.\n<tool_call>\n{call_json}\n</tool_call>"
    with FakeOpenAIServer([{"text": text}]) as server:
        provider = OpenAICompatibleProvider(model="m", base_url=server.base_url)
        events = collect(provider, tools=TOOLS)
    calls = [e.call for e in events if isinstance(e, ToolCallEvent)]
    assert calls and calls[0].arguments == {"file_path": "a"}
    assert events[-1].stop_reason == "tool_use"


def test_invalid_arguments_become_parse_error():
    provider = OpenAICompatibleProvider(model="m", base_url="http://x/v1")
    calls = {}
    provider._accumulate_tool_call(
        calls,
        {"index": 0, "id": "a", "function": {"name": "read_file", "arguments": "{bad"}},
    )
    call = provider._finish_tool_call(calls[0])
    assert call.parse_error and call.arguments == {}


def test_tool_calls_without_index():
    calls = {}
    acc = OpenAICompatibleProvider._accumulate_tool_call
    acc(calls, {"id": "a", "function": {"name": "f", "arguments": {"x": 1}}})
    acc(calls, {"id": "b", "function": {"name": "g", "arguments": "{}"}})
    assert [c["name"] for c in calls.values()] == ["f", "g"]
    assert json.loads(calls[0]["arguments"]) == {"x": 1}


def test_think_tag_splitter_handles_split_tags():
    for pieces in (
        ["<thi", "nk>plan", "ning</th", "ink>Answer"],
        ["<think", "ing> plan", "ning </thin", "king>Answer"],  # Amazon Nova style
    ):
        splitter = ThinkTagSplitter()
        events = []
        for piece in pieces:
            events += splitter.feed(piece)
        events += splitter.flush()
        thinking = "".join(e.text for e in events if isinstance(e, ThinkingDelta))
        text = "".join(e.text for e in events if isinstance(e, TextDelta))
        assert thinking.strip() == "planning" and text == "Answer"


def test_context_window_from_vllm():
    with FakeOpenAIServer([], models=("m",), max_model_len=65536) as server:
        provider = OpenAICompatibleProvider(model="m", base_url=server.base_url)
        assert provider.context_window() == 65536
        assert provider.list_models() == ["m"]


def test_openai_uses_max_completion_tokens():
    provider = OpenAIProvider(api_key="k", model="gpt-5")
    body = provider._build_body(
        [{"role": "user", "content": "x"}], None, {"max_tokens": 100}
    )
    assert body["max_completion_tokens"] == 100 and "max_tokens" not in body
    assert provider._headers()["Authorization"] == "Bearer k"
    local = OpenAICompatibleProvider(model="m")
    assert "Authorization" not in local._headers()


def test_openai_uses_the_responses_api_with_reasoning_replay():
    script = [
        {"reasoning": "look first", "tool_calls": [("read_file", {"file_path": "a"})]},
        {"text": "Done."},
    ]
    with FakeOpenAIServer(script) as server:
        provider = OpenAIProvider(api_key="k", model="gpt-6", base_url=server.base_url)
        messages = [
            {"role": "system", "content": "be brief"},
            {"role": "user", "content": "read a"},
        ]
        events = collect(provider, messages, TOOLS)
        assert "".join(e.text for e in events if isinstance(e, ThinkingDelta)) == (
            "look first"
        )
        call = next(e.call for e in events if isinstance(e, ToolCallEvent))
        assert call.name == "read_file" and call.arguments == {"file_path": "a"}
        done = events[-1]
        assert done.stop_reason == "tool_use"
        assert done.usage.input_tokens == 800 and done.usage.cache_read_tokens == 200

        messages += [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [call.to_dict()],
                "raw": done.raw,
            },
            {"role": "tool", "tool_call_id": call.id, "content": "contents"},
        ]
        events = collect(provider, messages, TOOLS)
        assert "".join(e.text for e in events if isinstance(e, TextDelta)) == "Done."

        first, second = server.requests
        assert first["instructions"] == "be brief" and first["store"] is False
        assert first["tools"][0]["name"] == "read_file"
        replayed = [item.get("type") for item in second["input"]]
        assert replayed == [None, "reasoning", "function_call", "function_call_output"]
        assert second["input"][1]["encrypted_content"] == "ENCRYPTED"
        assert "status" not in second["input"][1]


def test_openai_falls_back_to_chat_completions_without_responses():
    with FakeOpenAIServer([{"text": "hi"}], responses_api=False) as server:
        provider = OpenAIProvider(api_key="k", model="gpt-5", base_url=server.base_url)
        # The 404 consumes the scripted step's slot only after the fallback request.
        server.script.insert(0, {"text": "unused"})
        events = collect(provider)
        assert provider.use_responses_api is False
        assert any(isinstance(e, TextDelta) for e in events)
