"""System prompt construction."""

import platform
import subprocess
from datetime import date
from pathlib import Path
from typing import List, Optional

from .messages import ToolSpec

# Project instruction files, first match wins per directory.
INSTRUCTION_FILES = ("KUBRICK.md", "CLAUDE.md", "AGENTS.md")
MAX_INSTRUCTIONS_CHARS = 40000

BASE_PROMPT = """You are Kubrick, an AI coding agent working in the user's terminal. \
You help with software engineering tasks: reading and changing code, running commands, \
debugging, and explaining.

# How to work
- Use the tools to inspect the project before answering questions about it or changing it. \
Don't guess at file contents or project structure.
- Read a file before editing it. Make focused edits with edit_file; use write_file for new \
files or complete rewrites.
- When the user asks for a change, make it with the tools. Showing code in your reply does \
not change any file; never print code for the user to paste instead of writing it.
- Match the existing code's style, naming, and conventions. Don't add dependencies the \
project doesn't already use without saying so.
- After changing code, verify it when you can: run the relevant tests, build, or a quick check.
- When a step fails, read the error and fix the cause rather than retrying blindly.
- Independent read-only lookups can be issued together in one turn.
- Never run destructive commands (deleting data, force-pushing, rewriting history) unless the \
user asked for exactly that.

# Communicating
- Be concise and direct. Lead with the answer or the result.
- When you finish a task, briefly say what you changed and how you verified it. If something \
is unverified or failed, say so plainly.
- Reference code as path:line so the user can find it.
- Ask the user only when you are genuinely blocked on a decision that is theirs to make."""


def _git_summary(working_dir: Path) -> Optional[str]:
    try:
        branch = subprocess.run(  # nosec B603 B607 - fixed argv
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if branch.returncode != 0:
        return None
    return f"Git repository: yes (branch {branch.stdout.strip()})"


def load_project_instructions(
    working_dir: Path, kubrick_dir: Optional[Path] = None
) -> List[str]:
    """Collect instruction files: user-level, then project root and its parents.

    Files closer to the working directory come last so they take precedence.
    """
    sections = []
    if kubrick_dir is not None:
        user_file = Path(kubrick_dir) / "KUBRICK.md"
        if user_file.is_file():
            sections.append((user_file, user_file.read_text(errors="replace")))

    found = []
    current = Path(working_dir).resolve()
    home = Path.home().resolve()
    for directory in [current, *current.parents]:
        for name in INSTRUCTION_FILES:
            candidate = directory / name
            if candidate.is_file():
                found.append((candidate, candidate.read_text(errors="replace")))
                break
        if directory == home or (directory / ".git").exists():
            break
    sections.extend(reversed(found))

    rendered = []
    budget = MAX_INSTRUCTIONS_CHARS
    for path, text in sections:
        text = text.strip()
        if not text or budget <= 0:
            continue
        text = text[:budget]
        budget -= len(text)
        rendered.append(f"Contents of {path}:\n\n{text}")
    return rendered


def build_system_prompt(
    working_dir: Path,
    tools: Optional[List[ToolSpec]] = None,
    text_tool_protocol: bool = False,
    kubrick_dir: Optional[Path] = None,
) -> str:
    """Build the session's system prompt.

    The prompt is built once per conversation and not changed afterwards:
    providers cache it, and Claude's thinking blocks are bound to it.

    Args:
        working_dir: The agent's working directory
        tools: Tools to describe inline (only for the text tool protocol)
        text_tool_protocol: Whether the model calls tools via ``tool_call`` blocks
        kubrick_dir: Kubrick data dir, for the user-level KUBRICK.md
    """
    parts = [BASE_PROMPT]

    env_lines = [
        f"Working directory: {working_dir}",
        f"Platform: {platform.system()} {platform.release()}",
        f"Date: {date.today().isoformat()}",
    ]
    git = _git_summary(Path(working_dir))
    if git:
        env_lines.append(git)
    parts.append("# Environment\n" + "\n".join(env_lines))

    instructions = load_project_instructions(Path(working_dir), kubrick_dir)
    if instructions:
        parts.append(
            "# Project instructions\n"
            "The user provided these instructions. Follow them; they override the defaults "
            "above.\n\n" + "\n\n".join(instructions)
        )

    if text_tool_protocol and tools:
        from .tool_protocol import render_tools_prompt

        parts.append(render_tools_prompt(tools))

    return "\n\n".join(parts)
