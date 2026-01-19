"""Tool definitions and execution handlers."""

import glob
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List

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
        "description": "Write content to a file, creating it if it doesn't exist or overwriting if it does",
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
        "description": "Edit a file by replacing a specific string with new content",
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
        "description": "List files and directories matching a glob pattern (e.g., '*.py' for current dir, '**/*.py' for recursive, '**/*' for all)",
        "read_only": True,
        "estimated_duration": 1,
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern to match files (e.g., '*.py', 'src/**/*.ts')",
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
        "description": "Execute a bash command and return its output",
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

    def __init__(self, working_dir: str = None, safety_manager=None):
        """
        Initialize tool executor.

        Args:
            working_dir: Working directory for file operations (defaults to current directory)
            safety_manager: Optional SafetyManager for validation
        """
        self.working_dir = Path(working_dir) if working_dir else Path.cwd()
        self.safety_manager = safety_manager

    def _resolve_path(self, path: str) -> Path:
        """Resolve a path relative to working directory."""
        p = Path(path)
        if p.is_absolute():
            return p
        return (self.working_dir / p).resolve()

    def execute(
        self, tool_name: str, parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
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

        # Create parent directories if needed
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
        """List files matching a pattern."""
        pattern = params["pattern"]
        directory = params.get("directory", ".")
        search_dir = self._resolve_path(directory)

        # Use glob to find matching files and directories
        files = []
        directories = []

        for match in search_dir.glob(pattern):
            rel_path = match.relative_to(search_dir)
            if match.is_file():
                files.append(str(rel_path))
            elif match.is_dir():
                directories.append(str(rel_path) + "/")

        files.sort()
        directories.sort()

        # Combine results
        matches = directories + files

        if not matches:
            result = f"No files or directories found matching pattern: {pattern}"
        else:
            dir_count = len(directories)
            file_count = len(files)
            result = f"Found {dir_count} directories and {file_count} files:\n"

            if directories:
                result += "\nDirectories:\n" + "\n".join(directories)
            if files:
                result += "\n\nFiles:\n" + "\n".join(files)

        return {"success": True, "result": result}

    def _search_files(self, params: Dict) -> Dict:
        """Search for text in files."""
        pattern = params["pattern"]
        file_pattern = params.get("file_pattern", "**/*")
        directory = params.get("directory", ".")
        search_dir = self._resolve_path(directory)

        results = []

        # Find files matching the file pattern
        for file_path in search_dir.glob(file_pattern):
            if not file_path.is_file():
                continue

            try:
                content = file_path.read_text()
                lines = content.split("\n")

                for line_num, line in enumerate(lines, 1):
                    if pattern in line:
                        rel_path = file_path.relative_to(search_dir)
                        results.append(
                            f"{rel_path}:{line_num}: {line.strip()}"
                        )
            except (UnicodeDecodeError, PermissionError):
                # Skip binary files or files we can't read
                continue

        if not results:
            result = f"No matches found for pattern: {pattern}"
        else:
            result = f"Found {len(results)} matches:\n" + "\n".join(
                results[:50]
            )
            if len(results) > 50:
                result += f"\n... and {len(results) - 50} more"

        return {"success": True, "result": result}

    def _run_bash(self, params: Dict) -> Dict:
        """Run a bash command."""
        command = params["command"]

        # Safety check: validate command with SafetyManager
        if self.safety_manager:
            is_safe, warning = self.safety_manager.validate_bash_command(
                command
            )

            if not is_safe:
                # Request user confirmation for dangerous command
                confirmed = self.safety_manager.get_user_confirmation(
                    warning, command
                )

                if not confirmed:
                    return {
                        "success": False,
                        "error": "Command cancelled by user (dangerous command)",
                    }

        try:
            # Use timeout from safety config if available
            timeout = 30
            if (
                self.safety_manager
                and hasattr(self.safety_manager, "config")
            ):
                timeout = self.safety_manager.config.tool_timeout_seconds

            result = subprocess.run(
                command,
                shell=True,
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

        # List parameters more clearly
        props = tool["parameters"].get("properties", {})
        required = tool["parameters"].get("required", [])

        if props:
            tools_desc += "**Parameters:**\n"
            for param_name, param_info in props.items():
                req_marker = (
                    " (required)" if param_name in required else " (optional)"
                )
                param_desc = param_info.get("description", "No description")
                tools_desc += f"- `{param_name}`: {param_desc}{req_marker}\n"

        tools_desc += "\n"

    return tools_desc
