"""Tool definitions and execution handlers."""

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from .messages import ToolSpec

# Directories always excluded from list_files and search_files.
EXCLUDED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "venv",
    "env",
    ".env",
    "build",
    "dist",
    ".next",
    ".nuxt",
    "target",
    ".gradle",
    ".idea",
    ".vscode",
    ".DS_Store",
    "*.egg-info",
    ".terraform",
}

DEFAULT_READ_LIMIT = 2000
MAX_LINE_CHARS = 2000
MAX_OUTPUT_CHARS = 30000

TOOL_DEFINITIONS = [
    {
        "name": "read_file",
        "description": (
            "Read a text file. Returns lines prefixed with line numbers (`   12\\tcode`). "
            f"Reads up to {DEFAULT_READ_LIMIT} lines by default; use offset/limit for "
            "large files. Always read a file before editing it."
        ),
        "read_only": True,
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file (absolute or relative to the working dir)",
                },
                "offset": {
                    "type": "integer",
                    "description": "1-based line number to start reading from",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines to read",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Create a file or overwrite it entirely with the given content. Prefer edit_file "
            "for changes to existing files. Parent directories are created as needed."
        ),
        "read_only": False,
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to write",
                },
                "content": {"type": "string", "description": "The full file content"},
            },
            "required": ["file_path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": (
            "Replace an exact string in a file. old_string must match the file exactly "
            "(including indentation) and be unique unless replace_all is true; include "
            "surrounding lines to make it unique. Read the file first. Do not include the "
            "line-number prefixes from read_file output."
        ),
        "read_only": False,
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to edit",
                },
                "old_string": {
                    "type": "string",
                    "description": "Exact text to replace",
                },
                "new_string": {"type": "string", "description": "Replacement text"},
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace every occurrence (default false)",
                },
            },
            "required": ["file_path", "old_string", "new_string"],
        },
    },
    {
        "name": "list_files",
        "description": (
            "Find files by glob pattern, e.g. '**/*.py' or 'src/**/*.ts'. Common build, "
            "dependency and VCS directories are excluded. Results are capped at 500."
        ),
        "read_only": True,
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern"},
                "directory": {
                    "type": "string",
                    "description": "Directory to search (default: working directory)",
                },
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "search_files",
        "description": (
            "Search file contents with a regular expression. Returns matching lines as "
            "path:line: text. Narrow with file_pattern (a glob such as '*.py')."
        ),
        "read_only": True,
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regular expression to search for",
                },
                "file_pattern": {
                    "type": "string",
                    "description": "Glob restricting which files are searched",
                },
                "directory": {
                    "type": "string",
                    "description": "Directory to search (default: working directory)",
                },
                "case_insensitive": {"type": "boolean", "description": "Ignore case"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "run_bash",
        "description": (
            "Run a shell command in the working directory and return stdout, stderr and the "
            "exit code. Use it to run tests, builds, git and other CLI tools. Prefer the "
            "file tools over cat/sed/grep for reading, editing and searching files. "
            "Commands are non-interactive; avoid ones that wait for input."
        ),
        "read_only": False,
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The command to run"},
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default from config, max 600)",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "create_directory",
        "description": "Create a directory (and any missing parents).",
        "read_only": False,
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory to create"},
            },
            "required": ["path"],
        },
    },
]

TOOLS_BY_NAME = {t["name"]: t for t in TOOL_DEFINITIONS}
READ_ONLY_TOOLS = {t["name"] for t in TOOL_DEFINITIONS if t["read_only"]}
FILE_WRITE_TOOLS = {"write_file", "edit_file", "create_directory"}

_JSON_TYPES = {
    "string": str,
    "integer": int,
    "boolean": bool,
    "number": (int, float),
    "object": dict,
    "array": list,
}


def get_tool_specs() -> List[ToolSpec]:
    """Tool definitions in provider-neutral form."""
    return [
        ToolSpec(t["name"], t["description"], t["parameters"]) for t in TOOL_DEFINITIONS
    ]


def validate_arguments(tool_name: str, arguments: Dict[str, Any]) -> Optional[str]:
    """Check arguments against the tool's schema; returns an error message or None."""
    tool = TOOLS_BY_NAME.get(tool_name)
    if tool is None:
        return f"Unknown tool: {tool_name}. Available: {', '.join(TOOLS_BY_NAME)}"
    schema = tool["parameters"]
    missing = [name for name in schema.get("required", []) if name not in arguments]
    if missing:
        return f"Missing required parameter(s) for {tool_name}: {', '.join(missing)}"
    for name, value in arguments.items():
        prop = schema["properties"].get(name)
        if prop is None:
            continue  # tolerate extra keys from smaller models
        expected = _JSON_TYPES.get(prop.get("type"))
        if expected is None or value is None:
            continue
        if (
            prop["type"] == "integer"
            and isinstance(value, str)
            and value.strip().isdigit()
        ):
            arguments[name] = int(value)
            continue
        if prop["type"] == "boolean" and isinstance(value, str):
            if value.lower() in ("true", "false"):
                arguments[name] = value.lower() == "true"
                continue
        if not isinstance(value, expected) or (
            prop["type"] in ("integer", "number") and isinstance(value, bool)
        ):
            return f"Parameter '{name}' of {tool_name} must be of type {prop['type']}"
    return None


def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    head = int(limit * 0.7)
    tail = limit - head
    omitted = len(text) - limit
    return (
        f"{text[:head]}\n\n... [{omitted} characters truncated] ...\n\n{text[-tail:]}"
    )


class ToolExecutor:
    """Executes tools against the filesystem and shell."""

    def __init__(
        self,
        working_dir: str = None,
        safety_manager=None,
        max_list_files: int = 500,
        bash_timeout: int = 120,
        max_file_size_mb: int = 10,
    ):
        """
        Initialize tool executor.

        Args:
            working_dir: Working directory for file operations (default: cwd)
            safety_manager: Optional SafetyManager (used for file size limits)
            max_list_files: Maximum number of results from list_files
            bash_timeout: Default timeout for run_bash in seconds
            max_file_size_mb: Largest file read_file will load
        """
        self.working_dir = Path(working_dir).resolve() if working_dir else Path.cwd()
        self.safety_manager = safety_manager
        self.max_list_files = max_list_files
        self.bash_timeout = bash_timeout
        self.max_file_size_mb = max_file_size_mb
        if safety_manager is not None and hasattr(safety_manager, "config"):
            self.max_file_size_mb = safety_manager.config.max_file_size_mb

    def resolve_path(self, path: str) -> Path:
        """Resolve a path relative to the working directory."""
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = self.working_dir / p
        return p.resolve()

    # Backwards-compatible alias
    _resolve_path = resolve_path

    def is_inside_working_dir(self, path: str) -> bool:
        """Whether a path resolves inside the working directory."""
        try:
            self.resolve_path(path).relative_to(self.working_dir)
            return True
        except ValueError:
            return False

    def _should_exclude_path(self, path: Path) -> bool:
        """Whether a path is inside an excluded directory."""
        for part in path.parts:
            if part in EXCLUDED_DIRECTORIES:
                return True
            for excluded in EXCLUDED_DIRECTORIES:
                if "*" in excluded and part.endswith(excluded.replace("*", "")):
                    return True
        return False

    def execute(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool with given parameters.

        Returns:
            Dict with 'success' and either 'result' or 'error'
        """
        error = validate_arguments(tool_name, parameters)
        if error:
            return {"success": False, "error": error}
        handler = getattr(self, f"_{tool_name}", None)
        if handler is None:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
        try:
            return handler(parameters)
        except Exception as e:
            return {"success": False, "error": f"{type(e).__name__}: {e}"}

    # --- File tools ----------------------------------------------------------

    def _read_file(self, params: Dict) -> Dict:
        file_path = self.resolve_path(params["file_path"])
        if not file_path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}
        if file_path.is_dir():
            return {
                "success": False,
                "error": f"{file_path} is a directory; use list_files",
            }
        size = file_path.stat().st_size
        if size > self.max_file_size_mb * 1024 * 1024:
            return {
                "success": False,
                "error": (
                    f"{file_path} is {size / 1024 / 1024:.1f}MB, over the "
                    f"{self.max_file_size_mb}MB limit. Use run_bash with head/grep instead."
                ),
            }
        data = file_path.read_bytes()
        if b"\x00" in data[:8192]:
            return {
                "success": False,
                "error": f"{file_path} appears to be a binary file",
            }
        lines = data.decode("utf-8", errors="replace").splitlines()

        offset = max(int(params.get("offset") or 1), 1)
        limit = int(params.get("limit") or DEFAULT_READ_LIMIT)
        selected = lines[offset - 1 : offset - 1 + limit]
        if not lines:
            return {"success": True, "result": f"{file_path} is empty"}
        if not selected:
            return {
                "success": False,
                "error": f"offset {offset} is past the end of the file ({len(lines)} lines)",
            }
        numbered = []
        for number, line in enumerate(selected, start=offset):
            if len(line) > MAX_LINE_CHARS:
                line = line[:MAX_LINE_CHARS] + " [line truncated]"
            numbered.append(f"{number:>6}\t{line}")
        result = "\n".join(numbered)
        end = offset + len(selected) - 1
        if offset > 1 or end < len(lines):
            result += f"\n\n[Showing lines {offset}-{end} of {len(lines)}]"
        return {"success": True, "result": result}

    def _write_file(self, params: Dict) -> Dict:
        file_path = self.resolve_path(params["file_path"])
        content = params["content"]
        existed = file_path.exists()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        verb = "Overwrote" if existed else "Created"
        line_count = content.count("\n") + (
            0 if content.endswith("\n") or not content else 1
        )
        return {"success": True, "result": f"{verb} {file_path} ({line_count} lines)"}

    def _edit_file(self, params: Dict) -> Dict:
        file_path = self.resolve_path(params["file_path"])
        old_string = params["old_string"]
        new_string = params["new_string"]
        if not file_path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}
        if old_string == new_string:
            return {
                "success": False,
                "error": "old_string and new_string are identical",
            }
        if old_string == "":
            return {
                "success": False,
                "error": "old_string is empty; use write_file instead",
            }

        content = file_path.read_text()
        count = content.count(old_string)
        if count == 0:
            hint = ""
            if re.match(r"^\s*\d+\t", old_string):
                hint = " (remove the line-number prefixes copied from read_file output)"
            return {
                "success": False,
                "error": f"old_string not found in {file_path}{hint}",
            }
        if count > 1 and not params.get("replace_all"):
            return {
                "success": False,
                "error": (
                    f"old_string matches {count} places in {file_path}. Include more "
                    "surrounding context to make it unique, or set replace_all."
                ),
            }
        if params.get("replace_all"):
            new_content = content.replace(old_string, new_string)
        else:
            new_content = content.replace(old_string, new_string, 1)
        file_path.write_text(new_content)
        replaced = count if params.get("replace_all") else 1
        return {
            "success": True,
            "result": f"Edited {file_path} ({replaced} replacement(s))",
        }

    def _create_directory(self, params: Dict) -> Dict:
        path = self.resolve_path(params["path"])
        path.mkdir(parents=True, exist_ok=True)
        return {"success": True, "result": f"Created directory: {path}"}

    # --- Search tools --------------------------------------------------------

    def _list_files(self, params: Dict) -> Dict:
        pattern = params["pattern"]
        search_dir = self.resolve_path(params.get("directory") or ".")
        if not search_dir.is_dir():
            return {"success": False, "error": f"Not a directory: {search_dir}"}

        matches = []
        excluded = 0
        for match in search_dir.glob(pattern):
            try:
                rel = match.relative_to(search_dir)
            except ValueError:
                continue
            if self._should_exclude_path(rel):
                excluded += 1
                continue
            matches.append(str(rel) + ("/" if match.is_dir() else ""))
            if len(matches) >= self.max_list_files:
                break

        if not matches:
            note = (
                f" ({excluded} excluded from .git, node_modules, etc.)"
                if excluded
                else ""
            )
            return {"success": True, "result": f"No files match {pattern!r}{note}"}

        matches.sort()
        header = f"{len(matches)} match(es) for {pattern!r} in {search_dir}"
        if len(matches) >= self.max_list_files:
            header += f" (limit {self.max_list_files} reached; use a narrower pattern)"
        return {"success": True, "result": header + ":\n" + "\n".join(matches)}

    def _search_files(self, params: Dict) -> Dict:
        pattern = params["pattern"]
        file_pattern = params.get("file_pattern")
        search_dir = self.resolve_path(params.get("directory") or ".")
        ignore_case = bool(params.get("case_insensitive"))
        if not search_dir.is_dir():
            return {"success": False, "error": f"Not a directory: {search_dir}"}
        try:
            regex = re.compile(pattern, re.IGNORECASE if ignore_case else 0)
        except re.error as e:
            return {"success": False, "error": f"Invalid regular expression: {e}"}

        results = self._ripgrep(pattern, file_pattern, search_dir, ignore_case)
        if results is None:
            results = self._python_grep(regex, file_pattern, search_dir)

        if not results:
            return {"success": True, "result": f"No matches for {pattern!r}"}
        shown = results[:200]
        text = f"{len(results)} match(es) for {pattern!r}:\n" + "\n".join(shown)
        if len(results) > len(shown):
            text += f"\n... and {len(results) - len(shown)} more (narrow the search)"
        return {"success": True, "result": _truncate(text)}

    def _ripgrep(
        self,
        pattern: str,
        file_pattern: Optional[str],
        search_dir: Path,
        ignore_case: bool,
    ) -> Optional[List[str]]:
        """Search with ripgrep if installed; None if unavailable."""
        rg = shutil.which("rg")
        if not rg:
            return None
        cmd = [
            rg,
            "--line-number",
            "--no-heading",
            "--color=never",
            "--max-columns=500",
        ]
        if ignore_case:
            cmd.append("--ignore-case")
        for excluded in EXCLUDED_DIRECTORIES:
            cmd += ["--glob", f"!{excluded}"]
        if file_pattern:
            cmd += ["--glob", file_pattern]
        cmd += ["--regexp", pattern, "."]
        try:
            proc = subprocess.run(  # nosec B603 - argv list, no shell
                cmd, cwd=search_dir, capture_output=True, text=True, timeout=60
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if proc.returncode not in (0, 1):
            return None
        return [
            line[2:] if line.startswith("./") else line
            for line in proc.stdout.splitlines()
        ]

    def _python_grep(
        self, regex, file_pattern: Optional[str], search_dir: Path
    ) -> List[str]:
        """Pure-Python fallback search."""
        results = []
        glob = file_pattern if file_pattern and "/" in file_pattern else "**/*"
        for file_path in search_dir.glob(glob):
            if not file_path.is_file():
                continue
            rel = file_path.relative_to(search_dir)
            if self._should_exclude_path(rel):
                continue
            if (
                file_pattern
                and "/" not in file_pattern
                and not file_path.match(file_pattern)
            ):
                continue
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    for line_num, line in enumerate(f, 1):
                        if regex.search(line):
                            results.append(f"{rel}:{line_num}:{line.rstrip()[:500]}")
            except (UnicodeDecodeError, PermissionError, OSError):
                continue
            if len(results) > 5000:
                break
        return results

    # --- Shell ---------------------------------------------------------------

    def _run_bash(self, params: Dict) -> Dict:
        command = params["command"]
        timeout = min(int(params.get("timeout") or self.bash_timeout), 600)
        env = dict(os.environ)
        env.setdefault("GIT_PAGER", "cat")
        env.setdefault("PAGER", "cat")
        try:
            # nosec B602: running shell commands is this tool's purpose; every
            # command passes through PermissionManager before reaching here.
            proc = subprocess.run(
                command,
                shell=True,  # nosec
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.working_dir,
                stdin=subprocess.DEVNULL,
                env=env,
            )
        except subprocess.TimeoutExpired as e:
            partial = (e.stdout or "") if isinstance(e.stdout, str) else ""
            return {
                "success": False,
                "error": f"Command timed out after {timeout}s\n{_truncate(partial)}",
            }

        output = proc.stdout
        if proc.stderr:
            output += ("\n" if output else "") + f"[stderr]\n{proc.stderr}"
        result = f"Exit code: {proc.returncode}\n{_truncate(output.strip())}".rstrip()
        # A non-zero exit is information for the model, not a tool failure.
        return {"success": True, "result": result}
