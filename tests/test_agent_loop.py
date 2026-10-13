"""Tests for the agent loop using a scripted provider."""

from kubrick_cli.agent_loop import AgentLoop
from kubrick_cli.display import Renderer
from kubrick_cli.messages import MessageDone, TextDelta, ToolCall, ToolCallEvent, Usage
from kubrick_cli.permissions import PermissionManager, PromptAnswer
from kubrick_cli.providers.base import ProviderAdapter
from kubrick_cli.tools import ToolExecutor


class ScriptedProvider(ProviderAdapter):
    """Replays a list of responses: each is a list of events (MessageDone appended)."""

    def __init__(self, responses, native=True):
        self.responses = list(responses)
        self.requests = []
        self.supports_native_tools = native

    def stream_chat(self, messages, tools=None, options=None):
        self.requests.append({"messages": [dict(m) for m in messages], "tools": tools})
        step = self.responses.pop(0)
        if isinstance(step, Exception):
            raise step
        done = None
        for event in step:
            if isinstance(event, MessageDone):
                done = event
            else:
                yield event
        yield done or MessageDone(
            stop_reason=(
                "tool_use"
                if any(isinstance(e, ToolCallEvent) for e in step)
                else "end_turn"
            )
        )

    @property
    def provider_name(self):
        return "scripted"

    @property
    def model_name(self):
        return "scripted"


def call(name, cid="c1", parse_error=None, **args):
    return ToolCallEvent(ToolCall(cid, name, args, parse_error=parse_error))


def make_loop(provider, workspace, mode="bypass", prompt=None, **kwargs):
    executor = ToolExecutor(working_dir=str(workspace))
    permissions = PermissionManager(mode, executor, prompt=prompt)
    return AgentLoop(provider, executor, permissions, Renderer(), **kwargs)


def convo():
    return [{"role": "system", "content": "s"}, {"role": "user", "content": "go"}]


def test_runs_tools_until_model_stops(temp_workspace):
    (temp_workspace / "a.txt").write_text("hi\n")
    provider = ScriptedProvider(
        [
            [TextDelta("Reading"), call("read_file", file_path="a.txt")],
            [TextDelta("It says hi.")],
        ]
    )
    messages = convo()
    result = make_loop(provider, temp_workspace).run(messages)
    assert (
        result.reason == "end_turn"
        and result.iterations == 2
        and result.tool_calls == 1
    )
    assert [m["role"] for m in messages] == [
        "system",
        "user",
        "assistant",
        "tool",
        "assistant",
    ]
    assert "hi" in messages[3]["content"] and messages[3]["tool_call_id"] == "c1"


def test_parallel_read_only_results_keep_order(temp_workspace):
    for name in "abc":
        (temp_workspace / f"{name}.txt").write_text(name * 3)
    provider = ScriptedProvider(
        [
            [
                call("read_file", "1", file_path="a.txt"),
                call("read_file", "2", file_path="b.txt"),
                call("read_file", "3", file_path="c.txt"),
            ],
            [TextDelta("done")],
        ]
    )
    messages = convo()
    make_loop(provider, temp_workspace).run(messages)
    tool_msgs = [m for m in messages if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_msgs] == ["1", "2", "3"]
    assert "bbb" in tool_msgs[1]["content"]


def test_plain_denial_stops_turn(temp_workspace):
    def prompt(*args, **kwargs):
        return PromptAnswer(False, "denied", stop=True)

    provider = ScriptedProvider(
        [
            [
                call("write_file", "1", file_path="x", content="y"),
                call("read_file", "2", file_path="x"),
            ],
        ]
    )
    messages = convo()
    result = make_loop(provider, temp_workspace, mode="default", prompt=prompt).run(
        messages
    )
    assert result.reason == "denied"
    assert not (temp_workspace / "x").exists()
    results = [m for m in messages if m["role"] == "tool"]
    assert len(results) == 2 and all(
        m["is_error"] for m in results
    )  # every call answered


def test_denial_with_feedback_continues(temp_workspace):
    def prompt(*args, **kwargs):
        return PromptAnswer(False, "The user denied this action and said: use b.txt")

    provider = ScriptedProvider(
        [
            [call("write_file", file_path="a.txt", content="1")],
            [TextDelta("ok")],
        ]
    )
    messages = convo()
    result = make_loop(provider, temp_workspace, mode="default", prompt=prompt).run(
        messages
    )
    assert result.reason == "end_turn"
    assert "use b.txt" in messages[3]["content"]


def test_max_tokens_with_tool_call_is_not_executed(temp_workspace):
    provider = ScriptedProvider(
        [
            [
                call("write_file", file_path="big.txt", content="partial"),
                MessageDone(stop_reason="max_tokens"),
            ],
            [TextDelta("retrying smaller")],
        ]
    )
    messages = convo()
    make_loop(provider, temp_workspace).run(messages)
    assert not (temp_workspace / "big.txt").exists()
    assert "output token limit" in messages[3]["content"]


def test_refusal_stops(temp_workspace):
    provider = ScriptedProvider(
        [[TextDelta("No."), MessageDone(stop_reason="refusal", detail="cyber")]]
    )
    result = make_loop(provider, temp_workspace).run(convo())
    assert result.reason == "refusal"


def test_parse_error_reported_to_model(temp_workspace):
    provider = ScriptedProvider(
        [
            [call("read_file", parse_error="invalid JSON")],
            [TextDelta("fixed")],
        ]
    )
    messages = convo()
    make_loop(provider, temp_workspace).run(messages)
    assert messages[3]["is_error"] and "Could not parse" in messages[3]["content"]


def test_invalid_arguments_rejected_before_running(temp_workspace):
    provider = ScriptedProvider([[call("edit_file", file_path="a")], [TextDelta("ok")]])
    messages = convo()
    make_loop(provider, temp_workspace).run(messages)
    assert "Missing required parameter" in messages[3]["content"]


def test_max_iterations(temp_workspace):
    provider = ScriptedProvider([[call("list_files", pattern="*")]] * 3)
    result = make_loop(provider, temp_workspace, max_iterations=3).run(convo())
    assert result.reason == "max_iterations" and result.iterations == 3


def test_interrupt_during_stream_keeps_partial_text(temp_workspace):
    class Interrupting(ScriptedProvider):
        def stream_chat(self, messages, tools=None, options=None):
            yield TextDelta("partial ")
            raise KeyboardInterrupt

    messages = convo()
    result = make_loop(Interrupting([]), temp_workspace).run(messages)
    assert result.reason == "interrupted"
    assert messages[-1] == {"role": "assistant", "content": "partial "}


def test_text_protocol_sends_flat_messages(temp_workspace):
    (temp_workspace / "a.txt").write_text("alpha")
    provider = ScriptedProvider(
        [
            [
                TextDelta(
                    '```tool_call\n{"tool": "read_file", "parameters": {"file_path": "a.txt"}}\n```'
                )
            ],
            [TextDelta("alpha it is")],
        ],
        native=False,
    )
    messages = convo()
    loop = make_loop(provider, temp_workspace)
    assert loop.text_protocol
    loop.run(messages)
    second = provider.requests[1]
    assert second["tools"] is None
    assert all(m["role"] in ("system", "user", "assistant") for m in second["messages"])
    assert messages[2]["tool_calls"][0]["name"] == "read_file"


def test_usage_recorded_in_stats(temp_workspace):
    from kubrick_cli.ui import SessionStats

    stats = SessionStats()
    provider = ScriptedProvider(
        [[TextDelta("hi"), MessageDone(usage=Usage(10, 5, 100))]]
    )
    make_loop(provider, temp_workspace, session_stats=stats).run(convo())
    assert (stats.input_tokens, stats.output_tokens, stats.cache_read_tokens) == (
        10,
        5,
        100,
    )


def test_tool_names_lose_leaked_template_tokens():
    from kubrick_cli.messages import ToolCall

    assert ToolCall("1", "read_file<|channel|>commentary", {}).name == "read_file"
    assert ToolCall("2", "functions.run_bash", {}).name == "run_bash"
    assert ToolCall("3", " list_files ", {}).name == "list_files"


def test_tool_call_written_as_text_gets_one_nudge(temp_workspace):
    broken = '<reasoning>Need the file.{"file_path":"package.json","offset":1}'
    provider = ScriptedProvider(
        [[TextDelta(broken)], [TextDelta(broken)], [TextDelta("unused")]]
    )
    messages = convo()
    result = make_loop(provider, temp_workspace).run(messages)
    assert result.iterations == 2  # nudged once, then accepted the turn's end
    nudges = [m for m in messages if m["role"] == "user" and "as text" in m["content"]]
    assert len(nudges) == 1


def test_broken_tool_call_detection():
    from kubrick_cli.agent_loop import looks_like_broken_tool_call

    assert looks_like_broken_tool_call("ok<|call|>read_file")
    assert looks_like_broken_tool_call('Let me look. {"command": "ls -la"}')
    assert not looks_like_broken_tool_call("All 4 tests pass.")
    assert not looks_like_broken_tool_call('Config is {"a": 1} and works.')
