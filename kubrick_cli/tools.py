"""Tool definitions and execution handlers."""

import subprocess
from pathlib import Path
from typing import Any, Dict

# Directories to always exclude from list_files and search_files
# These are typically large, irrelevant, or auto-generated
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
    "target",  # Rust/Java builds
    ".gradle",
    ".idea",
    ".vscode",
    ".DS_Store",
    "*.egg-info",
    ".terraform",
}

TOOL_DEFINITIONS = [
    {
        "name": "read_file",
        "description": "Read the contents of a file from the filesystem",
        "read_only": True,
        "estimated_duration": 1,
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The absolute or relative path to the file to read",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Write content to a file (creates or overwrites). "
            "After writing Python scripts, immediately run them with run_bash. "
            "After creating files, verify with list_files or read_file."
        ),
        "read_only": False,
        "estimated_duration": 2,
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The absolute or relative path to the file to write",
                },
                "content": {
                    "type": "string",
                    "description": "The content to write to the file",
                },
            },
            "required": ["file_path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": (
            "Edit a file by replacing a specific string with new content. "
            "Must read the file first to see current contents. "
            "After editing, verify changes if needed."
        ),
        "read_only": False,
        "estimated_duration": 2,
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The path to the file to edit",
                },
                "old_string": {
                    "type": "string",
                    "description": "The exact string to find and replace",
                },
                "new_string": {
                    "type": "string",
                    "description": "The new string to replace with",
                },
            },
            "required": ["file_path", "old_string", "new_string"],
        },
    },
    {
        "name": "list_files",
        "description": (
            "List files matching a glob pattern. "
            "Automatically excludes .git, node_modules, and other common directories. "
            "Use specific patterns (e.g., 'src/**/*.py') instead of broad patterns "
            "(e.g., '**/*'). Limited to 500 files."
        ),
        "read_only": True,
        "estimated_duration": 1,
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": (
                        "Glob pattern to match files (e.g., '*.py', 'src/**/*.ts'). "
                        "Use SPECIFIC patterns, not '**/*'"
                    ),
                },
                "directory": {
                    "type": "string",
                    "description": "Directory to search in (defaults to current directory)",
                },
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "search_files",
        "description": "Search for text content within files using grep-like functionality",
        "read_only": True,
        "estimated_duration": 2,
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Text pattern or regex to search for",
                },
                "file_pattern": {
                    "type": "string",
                    "description": "File glob pattern to search within (e.g., '*.py')",
                },
                "directory": {
                    "type": "string",
                    "description": "Directory to search in (defaults to current directory)",
                },
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "run_bash",
        "description": (
            "Execute a bash command and return its output. "
            "ALWAYS use this to run Python scripts after creating them (e.g., 'python script.py'). "
            "Use for testing, verification, and execution."
        ),
        "read_only": False,
        "estimated_duration": 5,
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The bash command to execute",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "create_directory",
        "description": "Create a new directory",
        "read_only": False,
        "estimated_duration": 1,
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The path of the directory to create",
                },
            },
            "required": ["path"],
        },
    },
]


class ToolExecutor:
    """Handles execution of tools."""

    def __init__(
        self,
        working_dir: str = None,
        safety_manager=None,
        max_list_files: int = 500,
    ):
        """
        Initialize tool executor.

        Args:
            working_dir: Working directory for file operations (defaults to current directory)
            safety_manager: Optional SafetyManager for validation
            max_list_files: Maximum number of files to return from list_files (default: 500)
        """
        self.working_dir = Path(working_dir) if working_dir else Path.cwd()
        self.safety_manager = safety_manager
        self.max_list_files = max_list_files

    def _resolve_path(self, path: str) -> Path:
        """Resolve a path relative to working directory."""
        p = Path(path)
        if p.is_absolute():
            return p
        return (self.working_dir / p).resolve()

    def _should_exclude_path(self, path: Path) -> bool:
        """
        Check if a path should be excluded from listing/searching.

        Args:
            path: Path to check

        Returns:
            True if path should be excluded
        """
        # Check each part of the path
        for part in path.parts:
            if part in EXCLUDED_DIRECTORIES:
                return True
            # Handle glob patterns like *.egg-info
            for excluded in EXCLUDED_DIRECTORIES:
                if "*" in excluded and part.endswith(excluded.replace("*", "")):
                    return True
        return False

    def execute(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool with given parameters.

        Args:
            tool_name: Name of the tool to execute
            parameters: Tool parameters

        Returns:
            Dict with 'success', 'result', and optionally 'error' keys
        """
        try:
            if tool_name == "read_file":
                return self._read_file(parameters)
            elif tool_name == "write_file":
                return self._write_file(parameters)
            elif tool_name == "edit_file":
                return self._edit_file(parameters)
            elif tool_name == "list_files":
                return self._list_files(parameters)
            elif tool_name == "search_files":
                return self._search_files(parameters)
            elif tool_name == "run_bash":
                return self._run_bash(parameters)
            elif tool_name == "create_directory":
                return self._create_directory(parameters)
            else:
                return {
                    "success": False,
                    "error": f"Unknown tool: {tool_name}",
                }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    def _read_file(self, params: Dict) -> Dict:
        """Read a file."""
        file_path = self._resolve_path(params["file_path"])

        if not file_path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        content = file_path.read_text()
        return {
            "success": True,
            "result": f"Content of {file_path}:\n\n{content}",
        }

    def _write_file(self, params: Dict) -> Dict:
        """Write to a file."""
        file_path = self._resolve_path(params["file_path"])
        content = params["content"]

        file_path.parent.mkdir(parents=True, exist_ok=True)

        file_path.write_text(content)
        return {
            "success": True,
            "result": f"Successfully wrote {len(content)} characters to {file_path}",
        }

    def _edit_file(self, params: Dict) -> Dict:
        """Edit a file by replacing text."""
        file_path = self._resolve_path(params["file_path"])
        old_string = params["old_string"]
        new_string = params["new_string"]

        if not file_path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        content = file_path.read_text()

        if old_string not in content:
            return {
                "success": False,
                "error": f"String not found in file: {old_string[:100]}...",
            }

        new_content = content.replace(old_string, new_string, 1)
        file_path.write_text(new_content)

        return {
            "success": True,
            "result": f"Successfully edited {file_path}",
        }

    def _list_files(self, params: Dict) -> Dict:
        """
        List files matching a pattern with intelligent filtering.

        Automatically excludes common directories like .git, node_modules, etc.
        Limits results to prevent context overflow.
        """
        pattern = params["pattern"]
        directory = params.get("directory", ".")
        search_dir = self._resolve_path(directory)

        files = []
        directories = []
        excluded_count = 0

        for match in search_dir.glob(pattern):
            # Skip excluded paths (e.g., .git, node_modules)
            if self._should_exclude_path(match):
                excluded_count += 1
                continue

            try:
                rel_path = match.relative_to(search_dir)
                if match.is_file():
                    files.append(str(rel_path))
                elif match.is_dir():
                    directories.append(str(rel_path) + "/")
            except (ValueError, OSError):
                # Skip paths that can't be processed
                continue

            # Check if we've hit the limit
            total_items = len(files) + len(directories)
            if total_items >= self.max_list_files:
                break

        files.sort()
        directories.sort()

        # Check if we hit the limit
        total_found = len(files) + len(directories)
        hit_limit = total_found >= self.max_list_files

        if not files and not directories:
            if excluded_count > 0:
                result = (
                    f"No files or directories found matching pattern: {pattern}\n"
                    f"(Excluded {excluded_count} items from .git, node_modules, etc.)"
                )
            else:
                result = f"No files or directories found matching pattern: {pattern}"
        else:
            dir_count = len(directories)
            file_count = len(files)

            result = f"Found {dir_count} directories and {file_count} files"

            if excluded_count > 0:
                result += f" (excluded {excluded_count} from .git, node_modules, etc.)"

            if hit_limit:
                result += f"\n⚠️  LIMIT REACHED: Showing first {self.max_list_files} items only."
                result += "\n💡 Use more specific patterns (e.g., 'src/**/*.py' instead of '**/*')"

            result += ":\n"

            if directories:
                show_dirs = directories[: min(50, len(directories))]
                result += "\nDirectories:\n" + "\n".join(show_dirs)
                if len(directories) > 50:
                    result += f"\n... and {len(directories) - 50} more directories"

            if files:
                show_files = files[: min(100, len(files))]
                result += "\n\nFiles:\n" + "\n".join(show_files)
                if len(files) > 100:
                    result += f"\n... and {len(files) - 100} more files"

        return {"success": True, "result": result}

    def _search_files(self, params: Dict) -> Dict:
        """
        Search for text in files with intelligent filtering.

        Automatically excludes common directories like .git, node_modules, etc.
        """
        pattern = params["pattern"]
        file_pattern = params.get("file_pattern", "**/*")
        directory = params.get("directory", ".")
        search_dir = self._resolve_path(directory)

        results = []
        files_searched = 0
        files_excluded = 0

        for file_path in search_dir.glob(file_pattern):
            if not file_path.is_file():
                continue

            # Skip excluded paths
            if self._should_exclude_path(file_path):
                files_excluded += 1
                continue

            files_searched += 1

            try:
                content = file_path.read_text()
                lines = content.split("\n")

                for line_num, line in enumerate(lines, 1):
                    if pattern in line:
                        rel_path = file_path.relative_to(search_dir)
                        results.append(f"{rel_path}:{line_num}: {line.strip()}")
            except (UnicodeDecodeError, PermissionError):
                continue

        if not results:
            result = f"No matches found for pattern: {pattern}"
            if files_excluded > 0:
                result += (
                    f"\n(Searched {files_searched} files, excluded {files_excluded} "
                    "from .git, node_modules, etc.)"
                )
        else:
            result = f"Found {len(results)} matches in {files_searched} files"
            if files_excluded > 0:
                result += f" (excluded {files_excluded})"
            result += ":\n" + "\n".join(results[:50])
            if len(results) > 50:
                result += f"\n... and {len(results) - 50} more"

        return {"success": True, "result": result}

    def _run_bash(self, params: Dict) -> Dict:
        """Run a bash command."""
        command = params["command"]

        if self.safety_manager:
            is_safe, warning = self.safety_manager.validate_bash_command(command)

            if not is_safe:
                confirmed = self.safety_manager.get_user_confirmation(warning, command)

                if not confirmed:
                    return {
                        "success": False,
                        "error": "Command cancelled by user (dangerous command)",
                    }

        try:
            timeout = 30
            if self.safety_manager and hasattr(self.safety_manager, "config"):
                timeout = self.safety_manager.config.tool_timeout_seconds

            # nosec B602: shell=True is required for bash command execution
            # Commands are validated by SafetyManager before execution
            result = subprocess.run(
                command,
                shell=True,  # nosec
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.working_dir,
            )

            output = result.stdout
            if result.stderr:
                output += f"\nSTDERR:\n{result.stderr}"

            return {
                "success": True,
                "result": f"Command: {command}\nExit code: {result.returncode}\n\n{output}",
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"Command timed out after {timeout} seconds",
            }

    def _create_directory(self, params: Dict) -> Dict:
        """Create a directory."""
        path = self._resolve_path(params["path"])
        path.mkdir(parents=True, exist_ok=True)
        return {
            "success": True,
            "result": f"Created directory: {path}",
        }


def get_tools_prompt() -> str:
    """Get a formatted string describing available tools for the LLM."""
    tools_desc = ""

    for tool in TOOL_DEFINITIONS:
        tools_desc += f"### {tool['name']}\n"
        tools_desc += f"{tool['description']}\n\n"

        props = tool["parameters"].get("properties", {})
        required = tool["parameters"].get("required", [])

        if props:
            tools_desc += "**Parameters:**\n"
            for param_name, param_info in props.items():
                req_marker = " (required)" if param_name in required else " (optional)"
                param_desc = param_info.get("description", "No description")
                tools_desc += f"- `{param_name}`: {param_desc}{req_marker}\n"

        tools_desc += "\n"

    return tools_desc
