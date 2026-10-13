"""Unit tests for TritonProvider (text-protocol adapter over TritonLLMClient)."""

import json
from unittest.mock import patch

import pytest

from kubrick_cli.messages import MessageDone, TextDelta, ToolSpec
from kubrick_cli.providers.base import ProviderError
from kubrick_cli.providers.triton_provider import TritonProvider


def collect(provider, messages, **kwargs):
    return list(provider.stream_chat(messages, **kwargs))


class TestTritonProvider:
    def test_metadata_and_flags(self):
        provider = TritonProvider()
        assert provider.supports_native_tools is False
        assert provider.provider_name == "triton"
        assert provider.model_name == "llm_decoupled"
        assert provider.url == "localhost:8000"
        keys = {f["key"] for f in TritonProvider.METADATA.config_fields}
        assert keys == {"triton_url", "triton_model"}

    def test_stream_yields_text_then_done(self):
        provider = TritonProvider()
        with patch.object(
            provider.client, "generate_streaming", return_value=iter(["Hel", "", "lo"])
        ):
            events = collect(provider, [{"role": "user", "content": "hi"}])
        assert [e.text for e in events if isinstance(e, TextDelta)] == ["Hel", "lo"]
        assert isinstance(events[-1], MessageDone)
        assert events[-1].stop_reason == "end_turn"

    def test_flattens_tool_history_and_passes_options(self):
        provider = TritonProvider()
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "read it"},
            {
                "role": "assistant",
                "content": "ok",
                "tool_calls": [
                    {
                        "id": "c1",
                        "name": "read_file",
                        "arguments": {"file_path": "a.py"},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "c1",
                "name": "read_file",
                "content": "data",
            },
        ]
        tool = ToolSpec("read_file", "Read", {"type": "object", "properties": {}})
        with patch.object(
            provider.client, "generate_streaming", return_value=iter([])
        ) as gen:
            collect(
                provider,
                messages,
                tools=[tool],
                options={"max_tokens": 100, "temperature": 0.1, "model": "ignored"},
            )
        sent, params = gen.call_args[0]
        assert params == {"max_tokens": 100, "temperature": 0.1}
        assert [m["role"] for m in sent] == ["system", "user", "assistant", "user"]
        assert all(set(m) == {"role", "content"} for m in sent)
        assert "```tool_call" in sent[2]["content"]
        assert "read_file" in json.dumps(sent[3])

    def test_client_errors_become_provider_errors(self):
        provider = TritonProvider()
        with patch.object(
            provider.client,
            "generate_streaming",
            side_effect=Exception("Server returned 500"),
        ):
            with pytest.raises(ProviderError, match="500"):
                collect(provider, [{"role": "user", "content": "x"}])

    def test_generate_helper(self):
        provider = TritonProvider()
        with patch.object(
            provider.client, "generate_streaming", return_value=iter(["a", "b"])
        ):
            assert provider.generate([{"role": "user", "content": "x"}]) == "ab"

    def test_set_model_updates_client(self):
        provider = TritonProvider()
        provider.set_model("other")
        assert provider.model_name == "other"
        assert provider.client.model_name == "other"

    def test_is_healthy_delegates(self):
        provider = TritonProvider()
        with patch.object(provider.client, "is_healthy", return_value=True):
            assert provider.is_healthy() is True
