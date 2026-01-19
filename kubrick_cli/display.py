"""Display manager for natural language tool output."""

import json
from typing import Any, Dict

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

console = Console()


class DisplayManager:
    """
    Manages display of tool calls and results in natural language.

    Supports multiple display modes:
    - natural: Human-friendly descriptions (default)
    - json: Raw JSON panels (old behavior)
    - verbose: Both natural + JSON
    """

    def __init__(self, config: Dict):
        """
        Initialize display manager.

        Args:
            config: Configuration dict with display settings
        """
        self.display_mode = config.get("display_mode", "natural")
        self.show_tool_results = config.get("show_tool_results", True)

    def display_tool_call(self, tool_name: str, parameters: Dict[str, Any]):
        """
        Display a tool call in the configured mode.

        Args:
            tool_name: Name of the tool being called
            parameters: Tool parameters
        """
        if self.display_mode == "natural":
            self._display_natural_tool_call(tool_name, parameters)
        elif self.display_mode == "json":
            self._display_json_tool_call(tool_name, parameters)
        elif self.display_mode == "verbose":
            self._display_natural_tool_call(tool_name, parameters)
            self._display_json_tool_call(tool_name, parameters)

    def display_tool_result(
        self, tool_name: str, result: Dict[str, Any], success: bool
    ):
        """
        Display a tool execution result.

        Args:
            tool_name: Name of the tool that was executed
            result: Result dictionary
            success: Whether the execution succeeded
        """
        if not self.show_tool_results:
            return

        if self.display_mode == "natural":
            self._display_natural_result(tool_name, result, success)
        elif self.display_mode in ("json", "verbose"):
            self._display_json_result(tool_name, result, success)

    def _display_natural_tool_call(
        self, tool_name: str, parameters: Dict[str, Any]
    ):
        """Display tool call in natural language."""
        description = self._get_natural_description(tool_name, parameters)
        console.print(f"[cyan]→ {description}[/cyan]")

    def _display_json_tool_call(
        self, tool_name: str, parameters: Dict[str, Any]
    ):
        """Display tool call as JSON panel."""
        tool_data = {"tool": tool_name, "parameters": parameters}
        json_str = json.dumps(tool_data, indent=2)
        syntax = Syntax(json_str, "json", theme="monokai", line_numbers=False)
        console.print(Panel(syntax, title="Tool Call", border_style="cyan"))

    def _display_natural_result(
        self, tool_name: str, result: Dict[str, Any], success: bool
    ):
        """Display result in natural language."""
        if success:
            # Extract key information from result
            result_text = result.get("result", "")

            # Truncate long results for display
            if len(result_text) > 200:
                preview = result_text[:200] + "..."
                console.print(
                    f"[green]✓ {tool_name} succeeded[/green] [dim](output truncated)[/dim]"
                )
            else:
                console.print(f"[green]✓ {tool_name} succeeded[/green]")
        else:
            error = result.get("error", "Unknown error")
            console.print(f"[red]✗ {tool_name} failed: {error}[/red]")

    def _display_json_result(
        self, tool_name: str, result: Dict[str, Any], success: bool
    ):
        """Display result as JSON panel."""
        json_str = json.dumps(result, indent=2)
        syntax = Syntax(json_str, "json", theme="monokai", line_numbers=False)
        border_style = "green" if success else "red"
        title = f"Result: {tool_name}"
        console.print(Panel(syntax, title=title, border_style=border_style))

    def _get_natural_description(
        self, tool_name: str, parameters: Dict[str, Any]
    ) -> str:
        """
        Generate natural language description for a tool call.

        Args:
            tool_name: Name of the tool
            parameters: Tool parameters

        Returns:
            Human-friendly description
        """
        if tool_name == "read_file":
            file_path = parameters.get("file_path", "unknown")
            return f"Reading {file_path}"

        elif tool_name == "write_file":
            file_path = parameters.get("file_path", "unknown")
            content_length = len(parameters.get("content", ""))
            return (
                f"Writing {content_length} characters to {file_path}"
            )

        elif tool_name == "edit_file":
            file_path = parameters.get("file_path", "unknown")
            return f"Editing {file_path}"

        elif tool_name == "list_files":
            pattern = parameters.get("pattern", "*")
            directory = parameters.get("directory", ".")
            return f"Listing files matching '{pattern}' in {directory}"

        elif tool_name == "search_files":
            pattern = parameters.get("pattern", "")
            file_pattern = parameters.get("file_pattern", "**/*")
            return f"Searching for '{pattern}' in files matching '{file_pattern}'"

        elif tool_name == "run_bash":
            command = parameters.get("command", "")
            # Truncate long commands
            if len(command) > 60:
                command = command[:60] + "..."
            return f"Running bash command: {command}"

        elif tool_name == "create_directory":
            path = parameters.get("path", "unknown")
            return f"Creating directory {path}"

        else:
            # Fallback for unknown tools
            return f"Calling {tool_name}"
