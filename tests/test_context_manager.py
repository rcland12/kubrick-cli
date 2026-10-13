"""Tests for context tracking and compaction."""

from kubrick_cli.context_manager import SUMMARY_PREFIX, ContextManager
from kubrick_cli.messages import Usage


class FakeProvider:
    provider_name = "openai_compatible"
    model_name = "qwen"

    def __init__(self, window=None, summary="SUMMARY"):
        self.window = window
        self.summary = summary
        self.summarized = None

    def context_window(self):
        return self.window

    def generate(self, messages, stream_options=None):
        self.summarized = messages
        return self.summary


def turn(i, size=100):
    return [
        {"role": "user", "content": f"request {i} " + "x" * size},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": f"c{i}", "name": "read_file", "arguments": {}}],
            "raw": {"provider": "anthropic", "content": [{"type": "thinking"}]},
        },
        {
            "role": "tool",
            "tool_call_id": f"c{i}",
            "name": "read_file",
            "content": "y" * size,
        },
        {"role": "assistant", "content": f"done {i}"},
    ]


def test_window_resolution_order():
    assert ContextManager(FakeProvider(window=65536), {}).context_window == 65536
    assert (
        ContextManager(
            FakeProvider(window=65536), {"context_window": 8000}
        ).context_window
        == 8000
    )
    assert ContextManager(FakeProvider(), {}).context_window == 32768
    claude = FakeProvider()
    claude.provider_name, claude.model_name = "anthropic", "claude-opus-5-5"
    assert ContextManager(claude, {}).context_window == 1000000
    claude.model_name = "claude-haiku-4-5"
    assert ContextManager(claude, {}).context_window == 200000


def test_reported_usage_drives_estimate():
    cm = ContextManager(FakeProvider(window=10000), {})
    messages = [{"role": "system", "content": "s"}] + turn(1)
    cm.record_usage(Usage(input_tokens=5000, output_tokens=100), messages)
    assert cm.current_tokens(messages) == 5100
    messages.append({"role": "user", "content": "z" * 350})
    assert 5100 < cm.current_tokens(messages) < 5300


def test_compaction_cuts_at_user_boundary_and_drops_raw():
    provider = FakeProvider(window=20000)
    cm = ContextManager(provider, {})
    messages = [{"role": "system", "content": "sys"}]
    for i in range(6):
        messages += turn(i, size=4000)
    new, info = cm.compact(messages)
    assert new[0]["content"] == "sys"
    assert new[1]["role"] == "user" and new[1]["content"].startswith(SUMMARY_PREFIX)
    assert "SUMMARY" in new[1]["content"]
    assert new[2]["role"] == "user" and new[2]["content"].startswith("request")
    assert all("raw" not in m for m in new)
    # every kept tool result still has its call
    call_ids = {c["id"] for m in new for c in m.get("tool_calls", [])}
    assert all(m["tool_call_id"] in call_ids for m in new if m["role"] == "tool")
    assert info["tokens_after"] < info["tokens_before"]
    assert provider.summarized[-1]["role"] == "user"


def test_single_long_turn_shrinks_old_tool_output():
    cm = ContextManager(FakeProvider(window=8000), {})
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "go"}]
    for i in range(8):
        messages += turn(i, size=2000)[1:3]
    new, info = cm.compact(messages)
    assert info["action"] == "shrunk_tool_results"
    tool_contents = [m["content"] for m in new if m["role"] == "tool"]
    assert "removed to save context" in tool_contents[0]
    assert tool_contents[-1] == "y" * 2000


def test_summary_failure_falls_back_to_note():
    class Failing(FakeProvider):
        def generate(self, messages, stream_options=None):
            raise RuntimeError("down")

    cm = ContextManager(Failing(window=20000), {})
    messages = [{"role": "system", "content": "s"}]
    for i in range(4):
        messages += turn(i, size=4000)
    new, _ = cm.compact(messages)
    assert "summarization failed" in new[1]["content"]
