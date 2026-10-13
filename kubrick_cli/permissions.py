"""Permission checks before tools run (Claude Code-style modes)."""

import re
import shlex
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Set, Tuple

from .tools import FILE_WRITE_TOOLS, READ_ONLY_TOOLS

MODES = ("default", "accept_edits", "plan", "bypass")
MODE_DESCRIPTIONS = {
    "default": "Ask before editing files or running commands",
    "accept_edits": "Edit files in the project without asking; ask for commands",
    "plan": "Read-only: investigate and propose a plan",
    "bypass": "Never ask (dangerous commands still need a yes)",
}

# Commands that only read state. A command is auto-approved when every
# segment of a pipeline/chain starts with one of these.
READ_ONLY_COMMANDS = {
    "ls",
    "cat",
    "head",
    "tail",
    "wc",
    "grep",
    "egrep",
    "rg",
    "pwd",
    "which",
    "file",
    "stat",
    "du",
    "df",
    "tree",
    "echo",
    "sort",
    "cut",
    "diff",
    "basename",
    "dirname",
    "realpath",
    "whoami",
    "uname",
}
READ_ONLY_GIT = {"status", "diff", "log", "show", "ls-files", "blame", "rev-parse"}
# For "always allow", these tools are keyed by their first two words
# ("git commit", "npm test") instead of just the first.
_SUBCOMMAND_TOOLS = {
    "git",
    "npm",
    "npx",
    "yarn",
    "pnpm",
    "cargo",
    "go",
    "docker",
    "kubectl",
    "pip",
    "uv",
    "poetry",
    "make",
    "dotnet",
    "mvn",
    "gradle",
}
# Command separators, including a lone "&" (background) so "true & rm x" splits.
_SPLIT_RE = re.compile(r"&&|\|\||[|;&\n]")
_UNSAFE_RE = re.compile(r"[<>`]|\$\(")
# Redirects that discard output; stripped before analysis so `cmd 2>/dev/null` and
# `cmd 2>&1` don't make a read-only command look like it writes files.
_HARMLESS_REDIRECT_RE = re.compile(
    r"\s*(?:[012&]?>>?\s*/dev/null|[12]>&[12])(?=\s|$|[|;&])"
)
_FIND_UNSAFE = {"-exec", "-execdir", "-delete", "-ok", "-okdir", "-fls"}


@dataclass
class Decision:
    """Outcome of a permission check."""

    allowed: bool
    # Sent back to the model as the tool result when denied.
    message: Optional[str] = None
    # A denial that should end the turn and hand control back to the user.
    stop: bool = False


def _segments(command: str) -> Tuple[str, List[str]]:
    """The command without harmless redirects, and its pipeline/chain segments."""
    cleaned = _HARMLESS_REDIRECT_RE.sub("", command)
    return cleaned, [s.strip() for s in _SPLIT_RE.split(cleaned) if s.strip()]


def _segment_read_only(segment: str) -> bool:
    try:
        words = shlex.split(segment)
    except ValueError:
        return False
    if not words:
        return True
    name = words[0]
    args = words[1:]
    # Flags that make otherwise read-only tools write files or run programs.
    if any(a.startswith(("--output", "--pre")) for a in args):
        return False
    if name == "cd":
        return True  # only affects the segments after it, which are checked too
    if name == "git":
        return bool(args) and args[0] in READ_ONLY_GIT
    if name == "find":
        return not any(a in _FIND_UNSAFE or a.startswith("-fprint") for a in args)
    if name not in READ_ONLY_COMMANDS:
        return False
    if name in ("sort", "tree") and any(a.startswith("-o") for a in args):
        return False
    return True


def _segment_rule(segment: str) -> str:
    try:
        words = shlex.split(segment)
    except ValueError:
        words = segment.split()
    if not words:
        return segment
    if words[0] in _SUBCOMMAND_TOOLS and len(words) > 1:
        return f"{words[0]} {words[1]}"
    if (
        re.fullmatch(r"python[0-9.]*", words[0])
        and words[1:2] == ["-m"]
        and len(words) > 2
    ):
        return " ".join(words[:3])  # "python -m pytest", not every python script
    return words[0]


def is_read_only_command(command: str) -> bool:
    """Whether a shell command only reads state (safe to run without asking)."""
    cleaned, segments = _segments(command)
    if _UNSAFE_RE.search(cleaned):
        return False
    return all(_segment_read_only(s) for s in segments)


def command_rule(command: str) -> Optional[str]:
    """The prefix an "always allow" answer for this command applies to.

    That's the one non-read-only program it runs (``git commit``, ``pytest``),
    ignoring ``cd`` and read-only helpers. None when "always" can't be offered:
    the command runs several different programs or redirects into files.
    """
    cleaned, segments = _segments(command)
    if _UNSAFE_RE.search(cleaned):
        return None
    rules = {_segment_rule(s) for s in segments if not _segment_read_only(s)}
    return rules.pop() if len(rules) == 1 else None


def matches_rules(command: str, prefixes: Set[str]) -> bool:
    """Whether every part of ``command`` is read-only or allowed by ``prefixes``."""
    cleaned, segments = _segments(command)
    if not prefixes or _UNSAFE_RE.search(cleaned):
        return False
    return all(
        _segment_read_only(s) or any(s == p or s.startswith(p + " ") for p in prefixes)
        for s in segments
    )


class PermissionManager:
    """
    Decides whether a tool call may run, prompting the user when needed.

    Modes:
        default       Ask before file edits and non-read-only commands.
        accept_edits  Edit files inside the working directory without asking;
                      still ask for commands.
        plan          Read-only: edits and non-read-only commands are refused.
        bypass        Never ask (dangerous commands still ask when interactive).

    Reads and writes outside the working directory always ask (except bypass).
    """

    def __init__(
        self,
        mode: str,
        tool_executor,
        safety_manager=None,
        prompt: Optional[Callable[[str, str, str], "PromptAnswer"]] = None,
    ):
        """
        Args:
            mode: One of MODES
            tool_executor: ToolExecutor (for path resolution)
            safety_manager: SafetyManager for dangerous-command detection
            prompt: ``prompt(title, detail, warning) -> PromptAnswer``; None
                means non-interactive (anything that needs asking is denied)
        """
        if mode not in MODES:
            raise ValueError(
                f"Unknown permission mode {mode!r}; choose from {', '.join(MODES)}"
            )
        self.mode = mode
        self.tool_executor = tool_executor
        self.safety_manager = safety_manager
        self.prompt = prompt
        self.allowed_command_prefixes: Set[str] = set()
        self.allow_all_edits = False

    def check(self, tool_name: str, args: Dict) -> Decision:
        """Return whether ``tool_name(args)`` may run."""
        if self.mode == "bypass" and tool_name != "run_bash":
            return Decision(True)

        if tool_name in READ_ONLY_TOOLS:
            path = args.get("file_path") or args.get("directory") or "."
            if self.tool_executor.is_inside_working_dir(path):
                return Decision(True)
            return self._ask(
                "Read outside the working directory?",
                f"{tool_name}: {self.tool_executor.resolve_path(path)}",
            )

        if tool_name in FILE_WRITE_TOOLS:
            if self.mode == "plan":
                return Decision(False, _PLAN_DENIAL)
            path = args.get("file_path") or args.get("path") or ""
            inside = self.tool_executor.is_inside_working_dir(path)
            if inside and (self.mode == "accept_edits" or self.allow_all_edits):
                return Decision(True)
            title = (
                "Edit file?" if inside else "Edit a file OUTSIDE the working directory?"
            )
            answer = self._ask(
                title,
                _describe_edit(tool_name, args, self.tool_executor),
                always=inside,
            )
            if answer.allowed and answer.always:
                self.allow_all_edits = True
            return answer

        if tool_name == "run_bash":
            return self._check_command(args.get("command", ""))

        return Decision(False, f"Unknown tool: {tool_name}")

    def _check_command(self, command: str) -> Decision:
        warning = None
        if self.safety_manager is not None:
            is_safe, warning = self.safety_manager.validate_bash_command(command)
            if is_safe:
                warning = None

        if warning is None:
            if is_read_only_command(command):
                return Decision(True)
            if self.mode == "plan":
                return Decision(False, _PLAN_DENIAL)
            if self.mode == "bypass":
                return Decision(True)
            if matches_rules(command, self.allowed_command_prefixes):
                return Decision(True)
        elif self.mode == "plan":
            return Decision(False, _PLAN_DENIAL)
        elif self.prompt is None:
            # Nobody to confirm with: refuse rather than silently run it, even in bypass.
            return Decision(
                False,
                f"Refused: {warning}. Kubrick is running non-interactively, so this "
                "command can't be confirmed. Find a safer alternative or ask the user.",
            )

        rule = command_rule(command)
        answer = self._ask(
            "Run command?",
            command,
            warning=warning,
            always=warning is None and rule is not None,
            rule=rule,
        )
        if answer.allowed and answer.always and rule:
            self.allowed_command_prefixes.add(rule)
        return answer

    def _ask(
        self,
        title: str,
        detail: str,
        warning: Optional[str] = None,
        always: bool = True,
        rule: Optional[str] = None,
    ) -> "PromptAnswer":
        if self.prompt is None:
            return PromptAnswer(
                False,
                "Permission denied: this action needs approval and Kubrick is running "
                "non-interactively. Rerun with --permission-mode accept_edits or bypass "
                "to allow it.",
            )
        return self.prompt(title, detail, warning, always, rule)


@dataclass
class PromptAnswer(Decision):
    """A Decision from the user, possibly with "always allow" set."""

    always: bool = False


_PLAN_DENIAL = (
    "Plan mode is active: only read-only tools may run. Finish investigating and present "
    "a plan; the user will exit plan mode (/plan) to let you make changes."
)


def _describe_edit(tool_name: str, args: Dict, tool_executor) -> str:
    path = args.get("file_path") or args.get("path") or ""
    resolved = tool_executor.resolve_path(path) if path else path
    if tool_name == "write_file":
        content = args.get("content", "")
        lines = len(content.splitlines())
        preview = "\n".join(content.splitlines()[:20])
        more = "\n..." if lines > 20 else ""
        return f"write_file {resolved} ({lines} lines)\n\n{preview}{more}"
    if tool_name == "edit_file":
        old = "\n".join(
            "- " + line for line in args.get("old_string", "").splitlines()[:15]
        )
        new = "\n".join(
            "+ " + line for line in args.get("new_string", "").splitlines()[:15]
        )
        suffix = " (all occurrences)" if args.get("replace_all") else ""
        return f"edit_file {resolved}{suffix}\n\n{old}\n{new}"
    return f"{tool_name} {resolved}"
