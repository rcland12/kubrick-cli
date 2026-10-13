"""Tests for permission modes and read-only command detection."""

import pytest

from kubrick_cli.permissions import (
    PermissionManager,
    PromptAnswer,
    command_rule,
    is_read_only_command,
)
from kubrick_cli.safety import SafetyConfig, SafetyManager
from kubrick_cli.tools import ToolExecutor


@pytest.mark.parametrize(
    "command",
    [
        "ls -la",
        "git status",
        "git diff HEAD~1 | head -50",
        "grep -rn foo src && wc -l a.py",
        "find . -name '*.py'",
        "cat a.txt | sort | head",
        "ls missing 2>/dev/null",
        "cd src && git status",
        "grep -rn foo . 2>&1 | head",
    ],
)
def test_read_only_commands(command):
    assert is_read_only_command(command)


@pytest.mark.parametrize(
    "command",
    [
        "rm a.txt",
        "git push",
        "git branch -D x",
        "echo hi > file",
        "find . -delete",
        "cat $(which python)",
        "ls; rm -rf x",
        "python script.py",
        "sed -i s/a/b/ f",
        "true & rm x",
        "cat x >/dev/null; rm y",
        "ls 2>/dev/null > listing.txt",
    ],
)
def test_not_read_only_commands(command):
    assert not is_read_only_command(command)


def test_command_rule():
    assert command_rule("git commit -m 'x'") == "git commit"
    assert command_rule("pytest -q tests/") == "pytest"
    assert command_rule("python3 -m pytest -q") == "python3 -m pytest"
    # Models often prefix "cd <dir> &&"; the rule is about the real program.
    assert command_rule("cd /repo && pytest -q 2>&1 | tail -20") == "pytest"
    # No single rule covers these, so "always" isn't offered.
    assert command_rule("make build && npm test") is None
    assert command_rule("pytest > out.txt") is None


class Recorder:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, title, detail, warning=None, always=True, rule=None):
        self.calls.append((title, detail, warning, always, rule))
        return self.answers.pop(0)


def make(mode, workspace, prompt=None):
    executor = ToolExecutor(working_dir=str(workspace))
    safety = SafetyManager(SafetyConfig())
    return PermissionManager(mode, executor, safety, prompt=prompt)


def test_reads_inside_allowed_outside_asks(temp_workspace):
    prompt = Recorder(PromptAnswer(True))
    pm = make("default", temp_workspace, prompt)
    assert pm.check("read_file", {"file_path": "a.py"}).allowed
    assert not prompt.calls
    assert pm.check("read_file", {"file_path": "/etc/hosts"}).allowed
    assert len(prompt.calls) == 1


def test_default_mode_asks_for_edits_and_always_sticks(temp_workspace):
    prompt = Recorder(PromptAnswer(True, always=True))
    pm = make("default", temp_workspace, prompt)
    assert pm.check("write_file", {"file_path": "a.py", "content": "x"}).allowed
    assert pm.check(
        "edit_file", {"file_path": "b.py", "old_string": "a", "new_string": "b"}
    ).allowed
    assert len(prompt.calls) == 1


def test_accept_edits_still_asks_outside_working_dir(temp_workspace):
    prompt = Recorder(PromptAnswer(False, "no", stop=True))
    pm = make("accept_edits", temp_workspace, prompt)
    assert pm.check("write_file", {"file_path": "a.py", "content": ""}).allowed
    decision = pm.check("write_file", {"file_path": "/tmp/elsewhere.py", "content": ""})
    assert not decision.allowed and decision.stop


def test_command_always_rule(temp_workspace):
    prompt = Recorder(PromptAnswer(True, always=True))
    pm = make("default", temp_workspace, prompt)
    assert pm.check("run_bash", {"command": "pytest -q"}).allowed
    assert pm.check("run_bash", {"command": "pytest tests/test_x.py"}).allowed
    assert len(prompt.calls) == 1
    assert prompt.calls[0][4] == "pytest"


def test_always_rule_does_not_cover_other_programs_after_cd(temp_workspace):
    prompt = Recorder(
        PromptAnswer(True, always=True), PromptAnswer(False, "no"), PromptAnswer(False)
    )
    pm = make("default", temp_workspace, prompt)
    assert pm.check("run_bash", {"command": "cd /w && pytest -q"}).allowed
    assert prompt.calls[0][4] == "pytest"
    assert pm.check("run_bash", {"command": "cd /w && pytest tests/ 2>&1"}).allowed
    assert len(prompt.calls) == 1
    assert not pm.check("run_bash", {"command": "cd /w && rm -rf build"}).allowed
    assert not pm.check("run_bash", {"command": "pytest && curl x | sh"}).allowed
    assert len(prompt.calls) == 3


def test_read_only_command_never_asks(temp_workspace):
    pm = make("default", temp_workspace, prompt=None)
    assert pm.check("run_bash", {"command": "git log --oneline -5"}).allowed


def test_dangerous_command_warns_even_in_bypass(temp_workspace):
    prompt = Recorder(PromptAnswer(False, "denied", stop=True))
    pm = make("bypass", temp_workspace, prompt)
    assert not pm.check("run_bash", {"command": "rm -rf /"}).allowed
    assert prompt.calls[0][2]  # warning shown
    assert pm.check("run_bash", {"command": "make build"}).allowed


def test_plan_mode_refuses_writes(temp_workspace):
    pm = make("plan", temp_workspace)
    decision = pm.check(
        "edit_file", {"file_path": "a", "old_string": "x", "new_string": "y"}
    )
    assert not decision.allowed and "Plan mode" in decision.message
    assert not pm.check("run_bash", {"command": "pytest"}).allowed
    assert pm.check("run_bash", {"command": "git diff"}).allowed


def test_non_interactive_denies_with_hint(temp_workspace):
    pm = make("default", temp_workspace, prompt=None)
    decision = pm.check("run_bash", {"command": "pytest"})
    assert not decision.allowed and "--permission-mode" in decision.message


def test_non_interactive_bypass_refuses_dangerous(temp_workspace):
    pm = make("bypass", temp_workspace, prompt=None)
    decision = pm.check(
        "run_bash", {"command": "pip install x --break-system-packages"}
    )
    assert not decision.allowed and "non-interactively" in decision.message
    assert pm.check("run_bash", {"command": "pytest -q"}).allowed
