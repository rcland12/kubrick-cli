"""Terminal rendering for the agent loop."""

import os
import re
import sys
from typing import Any, Dict, Optional

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

from .glyphs import glyph


def describe_tool_call(tool_name: str, args: Dict[str, Any]) -> str:
    """One-line human description of a tool call."""
    if tool_name in ("read_file", "write_file", "edit_file"):
        label = {"read_file": "Read", "write_file": "Write", "edit_file": "Edit"}[
            tool_name
        ]
        detail = args.get("file_path", "?")
        if tool_name == "read_file" and args.get("offset"):
            detail += f" (from line {args['offset']})"
        return f"{label}({detail})"
    if tool_name == "list_files":
        where = args.get("directory")
        return f"List({args.get('pattern', '')}{' in ' + where if where else ''})"
    if tool_name == "search_files":
        scope = f" in {args['file_pattern']}" if args.get("file_pattern") else ""
        return f"Search({args.get('pattern', '')!r}{scope})"
    if tool_name == "run_bash":
        command = args.get("command", "").strip()
        # Models often prefix "cd <working dir> &&" even though commands already run there.
        command = re.sub(r"^cd\s+\S+\s*&&\s*", "", command).replace("\n", " \\n ")
        if len(command) > 100:
            command = command[:97] + "..."
        return f"Bash({command})"
    if tool_name == "create_directory":
        return f"Mkdir({args.get('path', '?')})"
    return f"{tool_name}({', '.join(f'{k}={v!r}' for k, v in list(args.items())[:3])})"


class ToolCallHider:
    """Suppresses ```tool_call blocks from streamed text (text tool protocol)."""

    OPEN = "```tool_call"
    CLOSE = "```"

    def __init__(self):
        self.pending = ""
        self.inside = False

    def feed(self, chunk: str) -> str:
        self.pending += chunk
        out = []
        while self.pending:
            if self.inside:
                # Skip past the opening fence line, then look for the closing fence.
                idx = self.pending.find(
                    self.CLOSE,
                    len(self.OPEN) if self.pending.startswith(self.OPEN) else 0,
                )
                if idx < 0:
                    return "".join(out)
                self.pending = self.pending[idx + len(self.CLOSE) :]
                self.inside = False
                continue
            idx = self.pending.find(self.OPEN)
            if idx >= 0:
                out.append(self.pending[:idx])
                self.pending = self.pending[idx:]
                self.inside = True
                continue
            # Hold back a possible partial fence at the end.
            keep = 0
            for n in range(min(len(self.OPEN) - 1, len(self.pending)), 0, -1):
                if self.OPEN.startswith(self.pending[-n:]):
                    keep = n
                    break
            out.append(self.pending[: len(self.pending) - keep])
            self.pending = self.pending[len(self.pending) - keep :]
            break
        return "".join(out)

    def flush(self) -> str:
        text = "" if self.inside else self.pending
        self.pending = ""
        self.inside = False
        return text


class Renderer:
    """Prints streamed model output and tool activity.

    In print mode (``kubrick -p``), only the model's text goes to stdout and
    everything else goes to stderr, so output can be piped.
    """

    def __init__(
        self,
        show_thinking: bool = True,
        print_mode: bool = False,
        working_dir: Optional[str] = None,
    ):
        self.show_thinking = show_thinking
        # Paths under the working dir are shown relative to it.
        self._prefix = os.path.join(os.path.realpath(working_dir or os.getcwd()), "")
        self.print_mode = print_mode
        self.out = Console(highlight=False)
        self.status = Console(stderr=True, highlight=False) if print_mode else self.out
        self._mode: Optional[str] = None  # "text" | "thinking" while streaming
        self._hider: Optional[ToolCallHider] = None

    # --- Streaming -----------------------------------------------------------

    def begin_response(self, hide_tool_blocks: bool = False):
        self._mode = None
        self._hider = ToolCallHider() if hide_tool_blocks else None

    def text(self, chunk: str):
        if self._hider:
            chunk = self._hider.feed(chunk)
        if not chunk:
            return
        if self._mode != "text" and not chunk.strip():
            return  # whitespace between reasoning spans or tool calls: don't print blank lines
        if self._mode == "thinking":
            self.status.print()
        if self._mode != "text" and not self.print_mode:
            self.out.print()
            chunk = chunk.lstrip("\n")
        self._mode = "text"
        self.out.print(chunk, end="", markup=False, soft_wrap=True)

    def thinking(self, chunk: str):
        if not self.show_thinking or not chunk:
            return
        if self._mode != "thinking":
            self.status.print(
                f"\n[dim italic]{glyph('thinking')} Thinking{glyph('ellipsis')}[/dim italic]"
            )
            self._mode = "thinking"
        self.status.print(escape(chunk), end="", style="dim italic", soft_wrap=True)

    def end_response(self):
        if self._hider:
            rest = self._hider.flush()
            self._hider = None
            if rest:
                self.text(rest)
        if self._mode is not None:
            (self.out if self._mode == "text" else self.status).print()
        self._mode = None

    # --- Tools ---------------------------------------------------------------

    def tool_call(self, tool_name: str, args: Dict[str, Any]):
        self.status.print(
            f"\n[bold cyan]{glyph('bullet')}[/bold cyan] "
            f"{escape(self._relative(describe_tool_call(tool_name, args)))}"
        )

    def _relative(self, text: str) -> str:
        return text.replace(self._prefix, "").replace(self._prefix.rstrip(os.sep), ".")

    def tool_result(self, tool_name: str, result: Dict[str, Any]):
        result = {
            k: self._relative(v) if isinstance(v, str) else v for k, v in result.items()
        }
        if result.get("success"):
            text = str(result.get("result", ""))
            lines = text.splitlines()
            preview = lines[0] if lines else "(no output)"
            if tool_name == "read_file":
                preview = f"Read {len(lines)} lines"
            elif tool_name == "run_bash" and len(lines) > 1:
                body = [line for line in lines[1:] if line.strip()][:4]
                preview = lines[0] + ("\n    " + "\n    ".join(body) if body else "")
                if len(lines) > 5:
                    preview += (
                        f"\n    {glyph('ellipsis')} ({len(lines) - 5} more lines)"
                    )
            if len(preview) > 600:
                preview = preview[:600] + glyph("ellipsis")
            self.status.print(f"  [dim]{glyph('result')} {escape(preview)}[/dim]")
        else:
            error = str(result.get("error", "failed")).splitlines()
            message = error[0] if error else "failed"
            self.status.print(f"  [red]{glyph('result')} {escape(message[:300])}[/red]")

    # --- Messages ------------------------------------------------------------

    def notice(self, message: str):
        self.status.print(f"[dim]{escape(message)}[/dim]")

    def warning(self, message: str):
        self.status.print(f"[yellow]{escape(message)}[/yellow]")

    def error(self, message: str):
        self.status.print(f"[red]{escape(message)}[/red]")

    def permission_panel(self, title: str, detail: str, warning: Optional[str] = None):
        body = escape(self._relative(detail))
        if warning:
            body = f"[bold red]{glyph('warn')} {escape(warning)}[/bold red]\n\n{body}"
        self.status.print(
            Panel(body, title=f"[bold]{escape(title)}[/bold]", border_style="yellow")
        )


def is_interactive() -> bool:
    """Whether stdin and stdout are terminals."""
    return sys.stdin.isatty() and sys.stdout.isatty()
