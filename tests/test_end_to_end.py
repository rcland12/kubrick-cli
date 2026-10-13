"""End-to-end: `kubrick -p` against a fake OpenAI-compatible server."""

import io
import json

import pytest

from kubrick_cli import main as main_module
from tests.fake_openai_server import FakeOpenAIServer


@pytest.fixture
def run_kubrick(monkeypatch, temp_workspace):
    def run(server, prompt, *extra):
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        monkeypatch.setenv("KUBRICK_PROVIDER", "openai_compatible")
        monkeypatch.setenv("KUBRICK_OPENAI_COMPATIBLE_BASE_URL", server.base_url)
        monkeypatch.setenv("KUBRICK_OPENAI_COMPATIBLE_MODEL", "test-model")
        return main_module.main(["-p", prompt, "-C", str(temp_workspace), *extra])

    return run


def test_tool_loop_edits_file(run_kubrick, temp_workspace, capsys):
    (temp_workspace / "greet.py").write_text("print('hello')\n")
    script = [
        {
            "text": "Let me look.",
            "tool_calls": [("read_file", {"file_path": "greet.py"})],
        },
        {
            "tool_calls": [
                (
                    "edit_file",
                    {
                        "file_path": "greet.py",
                        "old_string": "hello",
                        "new_string": "goodbye",
                    },
                )
            ]
        },
        {"text": "Changed the greeting to goodbye."},
    ]
    with FakeOpenAIServer(script) as server:
        code = run_kubrick(
            server, "change hello to goodbye", "--permission-mode", "accept_edits"
        )
    assert code == 0
    assert (temp_workspace / "greet.py").read_text() == "print('goodbye')\n"
    out = capsys.readouterr().out
    assert "Changed the greeting to goodbye." in out

    # Second request carries the assistant tool call and the tool result.
    second = server.requests[1]["messages"]
    assert second[-2]["tool_calls"][0]["function"]["name"] == "read_file"
    assert second[-1]["role"] == "tool" and "print('hello')" in second[-1]["content"]
    assert server.requests[0]["tools"][0]["type"] == "function"


def test_print_mode_denies_unapproved_edits(run_kubrick, temp_workspace):
    script = [
        {"tool_calls": [("write_file", {"file_path": "x.txt", "content": "data"})]},
        {"text": "I could not write the file."},
    ]
    with FakeOpenAIServer(script) as server:
        code = run_kubrick(server, "write x.txt")
    assert code == 0
    assert not (temp_workspace / "x.txt").exists()
    tool_result = server.requests[1]["messages"][-1]
    assert "permission" in tool_result["content"].lower()


def test_falls_back_to_text_protocol_when_tools_unsupported(
    run_kubrick, temp_workspace
):
    (temp_workspace / "a.txt").write_text("alpha\n")
    script = [
        {
            "status": 400,
            "error": "registry.ollama.ai/library/tiny does not support tools",
        },
        {
            "text": 'Reading.\n```tool_call\n{"tool": "read_file", "parameters": '
            '{"file_path": "a.txt"}}\n```'
        },
        {"text": "It says alpha."},
    ]
    with FakeOpenAIServer(script) as server:
        code = run_kubrick(server, "what is in a.txt?")
    assert code == 0
    retry = server.requests[1]
    assert "tools" not in retry
    assert (
        "tool_call" in retry["messages"][0]["content"]
    )  # protocol added to system prompt
    final = server.requests[2]["messages"]
    assert final[-1]["role"] == "user" and "alpha" in final[-1]["content"]


def test_conversation_saved_and_continued(run_kubrick, temp_workspace, isolated_home):
    with FakeOpenAIServer(
        [{"text": "First answer."}, {"text": "Second answer."}]
    ) as server:
        assert run_kubrick(server, "first") == 0
        assert run_kubrick(server, "second", "--continue") == 0
    convs = list((isolated_home / ".kubrick" / "conversations").glob("*.json"))
    assert len(convs) == 1
    messages = json.loads(convs[0].read_text())["messages"]
    assert [m["role"] for m in messages] == [
        "system",
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert server.requests[1]["messages"][2]["content"] == "First answer."


def test_unreachable_server_reports_error(run_kubrick, monkeypatch):
    class Dead:
        base_url = "http://127.0.0.1:9/v1"

    assert run_kubrick(Dead(), "hello") == 1


def test_display_helpers():
    from kubrick_cli.display import describe_tool_call

    assert (
        describe_tool_call("run_bash", {"command": "cd /x/y && pytest -q"})
        == "Bash(pytest -q)"
    )
