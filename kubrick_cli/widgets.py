"""Arrow-key pickers and text inputs that degrade to numbered prompts.

Full menus need a cursor-addressable terminal. On dumb terminals (Emacs
``M-x shell``, ``TERM=dumb``), when input isn't a TTY, or with
``KUBRICK_SIMPLE_UI=1``, the same calls fall back to plain numbered prompts.
"""

import os
import sys
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence

from rich.console import Console
from rich.markup import escape
from rich.prompt import Prompt

from .glyphs import glyph

console = Console()

_TRUTHY = ("1", "true", "yes", "on")


@dataclass
class Choice:
    """One option in a picker."""

    value: Any
    label: str
    description: str = ""
    # Marked "(current)": the setting in effect right now.
    current: bool = False
    # Single-key shortcut (e.g. "y") that picks this option immediately.
    key: str = ""


def rich_ui_available() -> bool:
    """Whether arrow-key menus can be drawn in this terminal."""
    if os.environ.get("KUBRICK_SIMPLE_UI", "").strip().lower() in _TRUTHY:
        return False
    try:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            return False
    except (AttributeError, ValueError):
        return False
    return os.environ.get("TERM", "") not in ("dumb", "unknown")


def silence_cpr_warning(app) -> None:
    """Don't print prompt_toolkit's "terminal doesn't support CPR" warning.

    Some terminals (Emacs term modes, serial consoles, test harnesses) never answer
    cursor-position requests; prompt_toolkit copes fine, the warning is just noise.
    """
    app.renderer.cpr_not_supported_callback = None


def dim_style() -> str:
    """prompt_toolkit style for de-emphasized text ("dim" needs prompt_toolkit 3.0.52+)."""
    from prompt_toolkit.styles import Style

    try:
        Style.from_dict({"x": "dim"}).get_attrs_for_style_str("class:x")
        return "dim"
    except ValueError:
        return "fg:ansibrightblack"


def menu_style():
    """prompt_toolkit style shared by menus and the input prompt."""
    from prompt_toolkit.styles import Style

    # Without color, mark the selection with reverse video instead.
    selected = "reverse" if os.environ.get("NO_COLOR") else "fg:ansicyan bold"
    dim = dim_style()
    return Style.from_dict(
        {
            "title": "bold",
            "pointer": selected,
            "selected": selected,
            "current": "fg:ansigreen",
            "description": dim,
            "hint": dim,
            "label": "fg:ansicyan",
            "placeholder": dim,
        }
    )


def select(
    title: str,
    choices: Sequence[Choice],
    default: Any = None,
    filterable: bool = False,
    max_visible: int = 10,
    summary: Optional[str] = None,
) -> Optional[Any]:
    """
    Let the user pick one of ``choices``.

    Args:
        title: Question shown above the options
        choices: Options, in display order
        default: Value to start on (else the ``current`` choice, else the first)
        filterable: Typing filters the list (for long lists such as models)
        max_visible: Rows shown before the list scrolls
        summary: Label printed with the answer afterwards (default: ``title``)

    Returns:
        The chosen value, or None if the user cancelled with Esc.

    Raises:
        KeyboardInterrupt: Ctrl+C
    """
    if not choices:
        return None
    start = next((i for i, c in enumerate(choices) if c.value == default), None)
    if start is None:
        start = next((i for i, c in enumerate(choices) if c.current), 0)
    if rich_ui_available():
        picked = _select_menu(title, list(choices), start, filterable, max_visible)
    else:
        picked = _select_numbered(title, list(choices), start)
    if picked is not None:
        console.print(
            f"[dim]{escape(summary or title)}[/dim] [cyan]{escape(picked.label)}[/cyan]"
        )
    return None if picked is None else picked.value


def _select_menu(
    title: str,
    choices: List[Choice],
    start: int,
    filterable: bool,
    max_visible: int,
) -> Optional[Choice]:
    from prompt_toolkit.application import Application, get_app
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.keys import Keys
    from prompt_toolkit.layout import Layout, Window
    from prompt_toolkit.layout.controls import FormattedTextControl

    state = {"index": start, "top": 0, "filter": ""}

    def visible() -> List[Choice]:
        text = state["filter"].lower()
        if not text:
            return choices
        return [
            c
            for c in choices
            if text in c.label.lower() or text in c.description.lower()
        ]

    def move(delta: int, wrap: bool = True):
        count = len(visible())
        if not count:
            return
        index = state["index"] + delta
        state["index"] = index % count if wrap else max(0, min(index, count - 1))

    def render():
        items = visible()
        width = max(get_app().output.get_size().columns, 20)
        rows = max(min(max_visible, get_app().output.get_size().rows - 4), 3)
        index = state["index"] = max(0, min(state["index"], len(items) - 1))
        # Scroll just enough to keep the selection in view.
        top = min(state["top"], index)
        top = max(top, index - rows + 1, 0)
        state["top"] = top
        shown = items[top : top + rows]

        numbered = not filterable and len(choices) <= 9
        label_width = min(max((len(c.label) for c in shown), default=0), width // 2)
        out = [("class:title", title), ("", "\n")]
        if filterable:
            if state["filter"]:
                out.append(("class:label", f"  Filter: {state['filter']}\n"))
            elif len(choices) > rows:
                out.append(("class:hint", "  Type to filter\n"))
        if top > 0:
            out.append(("class:hint", f"    {glyph('more_above')}\n"))
        for offset, choice in enumerate(shown):
            i = top + offset
            selected = i == index
            line = [
                ("class:pointer", f" {glyph('pointer')} ") if selected else ("", "   ")
            ]
            prefix = f"{i + 1}. " if numbered else ""
            line.append(
                (
                    "class:selected" if selected else "",
                    prefix + choice.label.ljust(label_width),
                )
            )
            used = 3 + len(prefix) + label_width
            if choice.current:
                line.append(("class:current", " (current)"))
                used += 10
            if choice.description and width - used > 8:
                room = width - used - 3
                text = choice.description
                if len(text) > room:
                    text = text[: room - len(glyph("ellipsis"))] + glyph("ellipsis")
                line.append(("class:description", "  " + text))
            out.extend(line + [("", "\n")])
        if not items:
            out.append(("class:hint", "    (no matches)\n"))
        if top + rows < len(items):
            out.append(("class:hint", f"    {glyph('more_below')}\n"))
        dot = glyph("dot")
        out.append(
            (
                "class:hint",
                f"  {glyph('up_down')} move {dot} Enter select {dot} Esc cancel",
            )
        )
        return out

    kb = KeyBindings()

    @kb.add("up")
    @kb.add("c-p")
    def _(event):
        move(-1)

    @kb.add("down")
    @kb.add("c-n")
    def _(event):
        move(1)

    @kb.add("pageup")
    def _(event):
        move(-max_visible, wrap=False)

    @kb.add("pagedown")
    def _(event):
        move(max_visible, wrap=False)

    @kb.add("enter")
    def _(event):
        items = visible()
        if items:
            event.app.exit(result=items[state["index"]])

    @kb.add("escape", eager=True)
    @kb.add("c-g")
    def _(event):
        event.app.exit(result=None)

    @kb.add("c-c")
    def _(event):
        event.app.exit(exception=KeyboardInterrupt())

    if filterable:

        @kb.add("backspace")
        def _(event):
            state["filter"] = state["filter"][:-1]
            state["index"] = 0

        @kb.add(Keys.Any)
        def _(event):
            if event.data.isprintable():
                state["filter"] += event.data
                state["index"] = 0

    else:

        @kb.add("k")
        def _(event):
            move(-1)

        @kb.add("j")
        def _(event):
            move(1)

        def bind_pick(key: str, choice: Choice):
            @kb.add(key)
            def _(event):
                event.app.exit(result=choice)

        if len(choices) <= 9:
            for i, choice in enumerate(choices):
                bind_pick(str(i + 1), choice)
        for choice in choices:
            if choice.key:
                bind_pick(choice.key, choice)

    app = Application(
        layout=Layout(
            Window(
                FormattedTextControl(render, focusable=True, show_cursor=False),
                dont_extend_height=True,
                wrap_lines=False,
            )
        ),
        key_bindings=kb,
        style=menu_style(),
        full_screen=False,
        erase_when_done=True,
        mouse_support=False,
    )
    silence_cpr_warning(app)
    return app.run()


def _select_numbered(title: str, choices: List[Choice], start: int) -> Optional[Choice]:
    console.print(f"[bold]{escape(title)}[/bold]")
    for i, choice in enumerate(choices, 1):
        key = f" [dim]({choice.key})[/dim]" if choice.key else ""
        current = " [green](current)[/green]" if choice.current else ""
        description = (
            f"  [dim]{escape(choice.description)}[/dim]" if choice.description else ""
        )
        console.print(
            f"  [cyan]{i}.[/cyan] {escape(choice.label)}{key}{current}{description}"
        )
    while True:
        try:
            answer = Prompt.ask(
                "[cyan]Choose a number[/cyan]", default=str(start + 1)
            ).strip()
        except EOFError:
            return None
        if answer.isdigit() and 1 <= int(answer) <= len(choices):
            return choices[int(answer) - 1]
        for choice in choices:
            if answer.lower() in (choice.key.lower(), choice.label.lower()) or (
                answer == str(choice.value)
            ):
                return choice
        console.print(f"[yellow]Enter a number from 1 to {len(choices)}.[/yellow]")


def ask_text(
    label: str,
    default: str = "",
    example: str = "",
    password: bool = False,
) -> str:
    """
    Read one line of text. Empty input returns ``default``.

    Args:
        label: Prompt label
        default: Value used when the user just presses Enter (shown dimmed)
        example: Hint printed on the line above
        password: Hide what is typed

    Raises:
        KeyboardInterrupt: Ctrl+C
        EOFError: Ctrl+D
    """
    if example:
        console.print(f"  [dim]{escape(example)}[/dim]")
    if not rich_ui_available():
        kwargs = {"password": password}
        if default and not password:
            kwargs["default"] = default
        else:
            kwargs.update(default="", show_default=False)
        return Prompt.ask(f"[cyan]{escape(label)}[/cyan]", **kwargs).strip() or default

    from prompt_toolkit import PromptSession
    from prompt_toolkit.formatted_text import FormattedText

    placeholder = None
    if default and not password:
        placeholder = FormattedText([("class:placeholder", default)])
    session = PromptSession(
        FormattedText([("class:label", label), ("", ": ")]),
        is_password=password,
        placeholder=placeholder,
        style=menu_style(),
    )
    silence_cpr_warning(session.app)
    return session.prompt().strip() or default


def ask_block(label: str, example: str = "") -> str:
    """
    Read a pasted multi-line block (e.g. ``KEY=VALUE`` lines) without echoing it.

    In a full terminal the paste lands in one hidden input and Enter submits it. On
    dumb terminals, lines are read until an empty one.

    Raises:
        KeyboardInterrupt: Ctrl+C
        EOFError: Ctrl+D
    """
    if example:
        console.print(f"  [dim]{escape(example)}[/dim]")
    if not rich_ui_available():
        import getpass

        console.print(
            f"[cyan]{escape(label)}[/cyan] [dim](end with an empty line)[/dim]"
        )
        lines = []
        while True:
            line = getpass.getpass("")
            if not line.strip():
                return "\n".join(lines)
            lines.append(line)

    from prompt_toolkit import PromptSession
    from prompt_toolkit.formatted_text import FormattedText
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.keys import Keys
    from prompt_toolkit.layout.processors import Processor, Transformation

    class Summary(Processor):
        """Show how much was pasted instead of the text (or a row of asterisks)."""

        def apply_transformation(self, ti):
            size = len(ti.document.text)
            label = f"[{size} characters pasted, hidden]" if size else ""
            return Transformation(
                [("class:hint", label)],
                source_to_display=lambda i: 0,
                display_to_source=lambda i: 0,
            )

    kb = KeyBindings()

    @kb.add(Keys.BracketedPaste)
    def _(event):
        # One line: the parser doesn't need the newlines, and Enter then submits.
        text = event.data.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
        event.current_buffer.insert_text(text)

    session = PromptSession(
        FormattedText([("class:label", label), ("", ": ")]),
        key_bindings=kb,
        input_processors=[Summary()],
        style=menu_style(),
    )
    silence_cpr_warning(session.app)
    return session.prompt()
