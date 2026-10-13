"""Interactive prompt, status bar, and permission prompts."""

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion, ThreadedCompleter
from prompt_toolkit.enums import EditingMode
from prompt_toolkit.filters import has_completions
from prompt_toolkit.formatted_text import HTML, FormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style

from .permissions import PromptAnswer
from .widgets import Choice, ask_text, dim_style, select, silence_cpr_warning


class SessionStats:
    """Counters for the current session, shown in the status bar."""

    def __init__(self):
        self.start_time = time.time()
        self.files_created = 0
        self.files_modified = 0
        self.lines_added = 0
        self.lines_deleted = 0
        self.tool_calls = 0
        self.commands_executed = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_read_tokens = 0

    def record_usage(self, usage):
        """Accumulate provider-reported token usage."""
        self.input_tokens += usage.input_tokens + usage.cache_write_tokens
        self.output_tokens += usage.output_tokens
        self.cache_read_tokens += usage.cache_read_tokens

    def record_tool(self, tool_name: str, args: Dict[str, Any], result: Dict[str, Any]):
        """Update counters after a tool ran."""
        self.tool_calls += 1
        if not result.get("success"):
            return
        if tool_name == "write_file":
            if str(result.get("result", "")).startswith("Created"):
                self.files_created += 1
            else:
                self.files_modified += 1
            self.lines_added += args.get("content", "").count("\n") + 1
        elif tool_name == "edit_file":
            self.files_modified += 1
            old = args.get("old_string", "").count("\n") + 1
            new = args.get("new_string", "").count("\n") + 1
            self.lines_added += max(new - old, 0)
            self.lines_deleted += max(old - new, 0)
        elif tool_name == "run_bash":
            self.commands_executed += 1

    def get_runtime(self) -> str:
        elapsed = int(time.time() - self.start_time)
        hours, rem = divmod(elapsed, 3600)
        minutes, seconds = divmod(rem, 60)
        if hours:
            return f"{hours}h {minutes}m"
        if minutes:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"


@dataclass
class SlashCommand:
    """A slash command, for /help and the completion menu."""

    name: str
    description: str
    args: str = ""
    # Choosing it from the menu waits for an argument instead of running it.
    needs_arg: bool = False


class SlashCompleter(Completer):
    """Completes /commands (and their first argument) at the start of the input."""

    def __init__(
        self,
        commands: List[SlashCommand],
        argument_choices: Optional[Callable[[str], List[Tuple[str, str]]]] = None,
    ):
        """
        Args:
            commands: Known commands
            argument_choices: ``argument_choices("/model") -> [(value, description)]``
        """
        self.commands = commands
        self.argument_choices = argument_choices

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/") or "\n" in text:
            return
        if " " not in text:
            typed = text.lower()
            for command in self.commands:
                if command.name.startswith(typed):
                    display = command.name + (
                        f" {command.args}" if command.args else ""
                    )
                    yield Completion(
                        command.name,
                        start_position=-len(text),
                        display=display,
                        display_meta=command.description,
                    )
            return
        name, _, partial = text.partition(" ")
        if " " in partial.lstrip() or self.argument_choices is None:
            return
        partial = partial.lstrip()
        try:
            options = self.argument_choices(name.lower())
        except Exception:
            return
        for value, description in options:
            if value.lower().startswith(partial.lower()):
                yield Completion(
                    value, start_position=-len(partial), display_meta=description
                )


class EnhancedPrompt:
    """Multiline input with history, a status bar, and a /command menu."""

    def __init__(
        self,
        status_provider: Callable[[], Dict[str, str]],
        history_file: Path,
        commands: Optional[List[SlashCommand]] = None,
        argument_choices: Optional[Callable[[str], List[Tuple[str, str]]]] = None,
        editing_mode: str = "emacs",
    ):
        """
        Args:
            status_provider: Returns the fields shown in the status bar
            history_file: Where input history is persisted
            commands: Slash commands offered when the input starts with "/"
            argument_choices: Completions for a command's argument (see SlashCompleter)
            editing_mode: "emacs" (default) or "vi" key bindings
        """
        self.status_provider = status_provider
        self.commands = {c.name: c for c in commands or []}
        dim = dim_style()
        self.style = Style.from_dict(
            {
                "bottom-toolbar": "bg:default fg:#888888 noreverse",
                "prompt": "bold green",
                "placeholder": dim,
                "sb.model": "fg:#5dade2",
                "sb.mode": "fg:#f39c12",
                "sb.ctx": "fg:#2ecc71",
                "sb.dir": "fg:#1abc9c",
                # A plain list rather than the default grey box.
                "completion-menu": "bg:default",
                "completion-menu.completion": "bg:default fg:default",
                "completion-menu.completion.current": "bg:default fg:ansicyan bold",
                "completion-menu.meta.completion": f"bg:default {dim}",
                "completion-menu.meta.completion.current": "bg:default fg:ansicyan",
                "scrollbar.background": "bg:default",
                "scrollbar.button": "bg:ansibrightblack",
            }
        )
        try:
            history = FileHistory(str(history_file))
        except OSError:
            history = None
        completer = None
        if commands:
            completer = ThreadedCompleter(SlashCompleter(commands, argument_choices))
        self.session = PromptSession(
            multiline=True,
            key_bindings=self._key_bindings(),
            style=self.style,
            bottom_toolbar=self._toolbar,
            history=history,
            # Must stay off: prompt_toolkit disables complete-while-typing with it.
            enable_history_search=False,
            mouse_support=False,
            completer=completer,
            complete_while_typing=True,
            reserve_space_for_menu=6,
            placeholder=FormattedText(
                [("class:placeholder", "Type a message, or / for commands")]
            ),
            editing_mode=EditingMode.VI if editing_mode == "vi" else EditingMode.EMACS,
        )
        silence_cpr_warning(self.session.app)

    def _key_bindings(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("enter")
        def _(event):
            """Enter submits, or runs the command highlighted in the menu."""
            buffer = event.app.current_buffer
            state = buffer.complete_state
            if state and state.current_completion:
                buffer.apply_completion(state.current_completion)
                command = self.commands.get(buffer.text.strip())
                if command and command.needs_arg:
                    buffer.insert_text(" ")
                    buffer.start_completion(select_first=False)
                    return
            if buffer.text.strip():
                buffer.validate_and_handle()

        @kb.add("escape", filter=has_completions)
        def _(event):
            """Esc closes the menu (and undoes a highlighted completion)."""
            event.app.current_buffer.cancel_completion()

        @kb.add("escape", "enter")
        def _(event):
            """Alt+Enter (or Esc then Enter) inserts a newline."""
            event.app.current_buffer.insert_text("\n")

        @kb.add("c-j")
        def _(event):
            """Ctrl+J inserts a newline (works in terminals without Alt)."""
            event.app.current_buffer.insert_text("\n")

        return kb

    def _toolbar(self):
        try:
            status = self.status_provider()
        except Exception:
            return ""
        try:
            width = os.get_terminal_size().columns
        except OSError:
            width = 100
        parts = [
            ("class:sb.model", status.get("model", "")),
            ("", "  "),
            ("class:sb.mode", status.get("mode", "")),
            ("", "  "),
            ("class:sb.ctx", status.get("context", "")),
            ("", "  "),
            ("", status.get("stats", "")),
        ]
        left = sum(len(t) for _, t in parts)
        directory = f"  {status.get('dir', '')}"
        pad = max(width - left - len(directory) - 1, 1)
        parts += [("", " " * pad), ("class:sb.dir", directory)]
        return parts

    def get_input(self, prompt_text: str = ">") -> str:
        """Read one message. Ctrl+D on empty input returns "exit"."""
        try:
            return self.session.prompt(HTML(f"<prompt>{prompt_text} </prompt>")).strip()
        except EOFError:
            return "exit"


def make_permission_prompt(renderer) -> Callable[..., PromptAnswer]:
    """Interactive permission prompt used by PermissionManager."""

    def prompt(
        title: str,
        detail: str,
        warning: Optional[str] = None,
        always: bool = True,
        rule: Optional[str] = None,
    ) -> PromptAnswer:
        renderer.permission_panel(title, detail, warning)
        choices = [Choice("y", "Yes", key="y")]
        if always:
            scope = f"'{rule}' commands" if rule else "file edits"
            choices.append(
                Choice(
                    "a", f"Yes, and allow {scope} for the rest of this session", key="a"
                )
            )
        choices.append(Choice("n", "No, and tell Kubrick what to do instead", key="n"))
        try:
            answer = select("Allow?", choices, default="y")
        except (KeyboardInterrupt, EOFError):
            answer = None
        if answer is None:
            return PromptAnswer(
                False, "The user interrupted and denied this action.", stop=True
            )
        if answer in ("y", "a"):
            return PromptAnswer(True, always=answer == "a")
        try:
            feedback = ask_text("What should Kubrick do instead? (Enter to stop)")
        except (KeyboardInterrupt, EOFError):
            feedback = ""
        if feedback:
            return PromptAnswer(
                False, f"The user denied this action and said: {feedback}"
            )
        return PromptAnswer(
            False,
            "The user denied this action. Wait for their next instruction.",
            stop=True,
        )

    return prompt
