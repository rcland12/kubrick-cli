"""Symbols used in terminal output, with a plain-ASCII fallback.

The Unicode set sticks to characters that common monospace fonts (Consolas,
Menlo, DejaVu, the Linux console font) all have and that every terminal draws
one cell wide: no emoji, no variation selectors. Set ``KUBRICK_ASCII=1`` (or
run with a non-UTF-8 locale) to use ASCII only.
"""

import os
import sys

_UNICODE = {
    "bullet": "●",
    "result": "└",
    "thinking": "*",
    "warn": "!",
    "check": "✓",
    "pointer": "›",
    "dot": "·",
    "arrow": "→",
    "ellipsis": "…",
    "up_down": "↑/↓",
    "more_above": "↑ more",
    "more_below": "↓ more",
}

_ASCII = {
    "bullet": "*",
    "result": "|",
    "thinking": "*",
    "warn": "!",
    "check": "+",
    "pointer": ">",
    "dot": "-",
    "arrow": "->",
    "ellipsis": "...",
    "up_down": "Up/Down",
    "more_above": "^ more",
    "more_below": "v more",
}


def use_ascii() -> bool:
    """Whether to avoid non-ASCII output."""
    setting = os.environ.get("KUBRICK_ASCII", "").strip().lower()
    if setting in ("1", "true", "yes", "on"):
        return True
    if setting in ("0", "false", "no", "off"):
        return False
    encoding = (getattr(sys.stdout, "encoding", None) or "").lower().replace("-", "")
    return bool(encoding) and encoding not in ("utf8", "utf16", "utf32")


def glyph(name: str) -> str:
    """The symbol called ``name`` for this terminal."""
    return (_ASCII if use_ascii() else _UNICODE)[name]
