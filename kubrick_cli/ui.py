"""Enhanced UI components for Kubrick CLI."""

import time
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from rich.console import Console

console = Console()


class SessionStats:
    """Track statistics for the current session."""

    def __init__(self):
        """Initialize session statistics."""
        self.start_time = time.time()
        self.files_created = 0
        self.files_modified = 0
        self.files_read = 0
        self.lines_added = 0
        self.lines_deleted = 0
        self.tool_calls = 0
        self.commands_executed = 0
        self.total_tokens = 0
        self.input_chars = 0
        self.iterations = 0

    def get_runtime(self) -> str:
        """Get formatted runtime."""
        elapsed = time.time() - self.start_time
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)

        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"

    def get_file_changes(self) -> str:
        """Get summary of file changes."""
        if self.files_created == 0 and self.files_modified == 0:
            return "No changes"

        parts = []
        if self.files_created > 0:
            parts.append(f"+{self.files_created} created")
        if self.files_modified > 0:
            parts.append(f"~{self.files_modified} modified")
        return ", ".join(parts)

    def get_code_changes(self) -> str:
        """Get summary of code changes."""
        if self.lines_added == 0 and self.lines_deleted == 0:
            return "0"

        parts = []
        if self.lines_added > 0:
            parts.append(f"+{self.lines_added}")
        if self.lines_deleted > 0:
            parts.append(f"-{self.lines_deleted}")
        return " ".join(parts)


class EnhancedPrompt:
    """Enhanced prompt with multiline support and status bar."""

    def __init__(
        self,
        working_dir: str,
        stats: SessionStats,
        context_manager=None,
        conversation_id: str = "",
    ):
        """
        Initialize enhanced prompt.

        Args:
            working_dir: Current working directory
            stats: Session statistics object
            context_manager: Optional context manager for token info
            conversation_id: Current conversation ID
        """
        self.working_dir = working_dir
        self.stats = stats
        self.context_manager = context_manager
        self.conversation_id = conversation_id
        self.current_input_length = 0

        # Create custom key bindings
        self.key_bindings = self._create_key_bindings()

        # Create prompt style (NO background colors, only text colors)
        self.style = Style.from_dict(
            {
                "prompt": "bold green",
                "separator": "#444444",
                "statusbar": "fg:#888888 nobold noitalic nounderline noreverse",
                "statusbar.help": "fg:#5dade2 nobold noitalic nounderline noreverse",
                "statusbar.time": "fg:#f39c12 nobold noitalic nounderline noreverse",
                "statusbar.iterations": "fg:#9b59b6 nobold noitalic nounderline noreverse",
                "statusbar.tools": "fg:#e74c3c nobold noitalic nounderline noreverse",
                "statusbar.files": "fg:#3498db nobold noitalic nounderline noreverse",
                "statusbar.lines": "fg:#2ecc71 nobold noitalic nounderline noreverse",
                "statusbar.tokens": "fg:#e67e22 nobold noitalic nounderline noreverse",
                "statusbar.chars": "fg:#95a5a6 nobold noitalic nounderline noreverse",
                "statusbar.directory": "fg:#1abc9c nobold noitalic nounderline noreverse",
            }
        )

        # Create prompt session
        self.session = PromptSession(
            multiline=True,  # Allow multiline editing, Enter submits, Alt+Enter for newlines
            key_bindings=self.key_bindings,
            style=self.style,
            bottom_toolbar=self._get_bottom_toolbar,
            enable_history_search=True,
            complete_while_typing=False,
            mouse_support=False,  # Disable to allow terminal scrolling
        )

    def _create_key_bindings(self) -> KeyBindings:
        """Create custom key bindings."""
        kb = KeyBindings()

        # Enter always submits (like Claude Code)
        @kb.add("enter")
        def _(event):
            """Handle Enter key - always submit."""
            buffer = event.app.current_buffer
            if buffer.text.strip():  # Only submit if there's text
                buffer.validate_and_handle()

        @kb.add("c-d")
        def _(event):
            """Ctrl+D also submits the input."""
            buffer = event.app.current_buffer
            if buffer.text.strip():
                buffer.validate_and_handle()

        @kb.add("escape", "enter")
        def _(event):
            """Alt+Enter adds a new line (for multiline input)."""
            event.app.current_buffer.insert_text("\n")

        return kb

    def _continuation_prompt(self, width, line_number, is_soft_wrap):
        """Prompt for continuation lines."""
        return HTML("<prompt>... </prompt>")

    def _get_bottom_toolbar(self):
        """Generate bottom toolbar with status information."""
        # Update input length
        try:
            from prompt_toolkit import get_app

            app = get_app()
            if app and app.current_buffer:
                self.current_input_length = len(app.current_buffer.text)
        except Exception:
            pass

        # Get stats
        runtime = self.stats.get_runtime()

        # Get working directory (shortened)
        work_dir = self.working_dir
        try:
            work_dir = Path(work_dir).name or work_dir
            if len(work_dir) > 30:
                work_dir = "..." + work_dir[-27:]
        except Exception:
            pass

        # Get terminal width for separator line
        try:
            import os

            term_width = os.get_terminal_size().columns
        except Exception:
            term_width = 120

        # Build toolbar sections with unique colors for each stat
        toolbar_parts = []

        # Thin separator line above (using lower one-eighth block for minimal visual weight)
        toolbar_parts.append(("class:separator", "▁" * term_width + "\n"))

        # Help section (left)
        toolbar_parts.extend(
            [
                ("class:statusbar.help", "Type /help for options"),
            ]
        )

        # Stats section (center)
        stats_parts = []

        if self.stats.iterations > 0:
            stats_parts.append(
                (
                    "class:statusbar.iterations",
                    f"  Iterations: {self.stats.iterations}",
                )
            )

        if self.stats.tool_calls > 0:
            stats_parts.append(
                ("class:statusbar.tools", f"  Tools: {self.stats.tool_calls}")
            )

        if self.stats.files_created > 0 or self.stats.files_modified > 0:
            file_str = []
            if self.stats.files_created > 0:
                file_str.append(f"+{self.stats.files_created}")
            if self.stats.files_modified > 0:
                file_str.append(f"~{self.stats.files_modified}")
            stats_parts.append(
                ("class:statusbar.files", f"  Files: {' '.join(file_str)}")
            )

        if self.stats.lines_added > 0 or self.stats.lines_deleted > 0:
            lines_str = []
            if self.stats.lines_added > 0:
                lines_str.append(f"+{self.stats.lines_added}")
            if self.stats.lines_deleted > 0:
                lines_str.append(f"-{self.stats.lines_deleted}")
            stats_parts.append(
                ("class:statusbar.lines", f"  Lines: {' '.join(lines_str)}")
            )

        if self.stats.total_tokens > 0:
            stats_parts.append(
                (
                    "class:statusbar.tokens",
                    f"  Tokens: {self.stats.total_tokens}",
                )
            )

        stats_parts.append(("class:statusbar.time", f"  Runtime: {runtime}"))

        if self.current_input_length > 0:
            stats_parts.append(
                (
                    "class:statusbar.chars",
                    f"  Chars: {self.current_input_length}",
                )
            )

        toolbar_parts.extend(stats_parts)

        # Directory section (right)
        # Calculate spacing to right-align directory
        left_text = "Type /help for options"
        stats_text = "".join(text for _, text in stats_parts)
        right_text = f"  Dir: {work_dir}"

        used_space = len(left_text) + len(stats_text) + len(right_text)
        remaining = term_width - used_space

        if remaining > 0:
            toolbar_parts.append(("class:statusbar", " " * remaining))

        toolbar_parts.extend(
            [
                ("class:statusbar.directory", f"  Dir: {work_dir}"),
            ]
        )

        return toolbar_parts

    def get_input(self, prompt_text: str = "You") -> str:
        """
        Get user input with enhanced multiline support.

        Args:
            prompt_text: Text to display in the prompt

        Returns:
            User input string
        """
        try:
            user_input = self.session.prompt(
                HTML(f"<prompt>{prompt_text}> </prompt>"),
            )
            return user_input.strip()
        except KeyboardInterrupt:
            raise
        except EOFError:
            # Ctrl+D on empty input means exit
            return "exit"


def create_enhanced_prompt(
    working_dir: str,
    stats: SessionStats,
    context_manager=None,
    conversation_id: str = "",
) -> EnhancedPrompt:
    """
    Create an enhanced prompt instance.

    Args:
        working_dir: Current working directory
        stats: Session statistics
        context_manager: Optional context manager
        conversation_id: Current conversation ID

    Returns:
        EnhancedPrompt instance
    """
    return EnhancedPrompt(working_dir, stats, context_manager, conversation_id)
