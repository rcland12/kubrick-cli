"""Animated display components for clean tool execution visualization."""

import threading
from typing import Optional

from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner

console = Console()


class ToolSpinner:
    """Animated spinner for tool execution."""

    # Tool-specific verbs (NO EMOJIS)
    TOOL_CONFIGS = {
        "write_file": {"verb": "Writing"},
        "edit_file": {"verb": "Editing"},
        "read_file": {"verb": "Reading"},
        "run_bash": {"verb": "Running"},
        "search_code": {"verb": "Searching"},
        "list_files": {"verb": "Listing"},
        "get_file_info": {"verb": "Inspecting"},
        "default": {"verb": "Calling"},
    }

    def __init__(self, tool_name: str, parameters: dict):
        """
        Initialize tool spinner.

        Args:
            tool_name: Name of the tool being executed
            parameters: Tool parameters
        """
        self.tool_name = tool_name
        self.parameters = parameters
        self.live = None
        self.spinner = None
        self._stop_event = threading.Event()

        # Get tool-specific configuration
        config = self.TOOL_CONFIGS.get(tool_name, self.TOOL_CONFIGS["default"])
        self.verb = config["verb"]

        # Build display message
        self.message = self._build_message()

    def _build_message(self) -> str:
        """Build display message based on tool and parameters."""
        # Extract relevant parameter for display
        detail = ""

        if self.tool_name == "write_file" and "file_path" in self.parameters:
            detail = self.parameters["file_path"]
        elif self.tool_name == "edit_file" and "file_path" in self.parameters:
            detail = self.parameters["file_path"]
        elif self.tool_name == "read_file" and "file_path" in self.parameters:
            detail = self.parameters["file_path"]
        elif self.tool_name == "run_bash" and "command" in self.parameters:
            cmd = self.parameters["command"]
            # Truncate long commands
            detail = cmd if len(cmd) <= 50 else cmd[:47] + "..."
        elif self.tool_name == "search_code" and "pattern" in self.parameters:
            detail = f'"{self.parameters["pattern"]}"'

        if detail:
            return f"{self.verb} {detail}"
        else:
            return f"Calling {self.tool_name}"

    def start(self):
        """Start the spinner animation."""
        self.spinner = Spinner("dots", text=self.message, style="cyan")
        self.live = Live(self.spinner, console=console, refresh_per_second=10)
        self.live.start()

    def stop(self, success: bool = True, error_msg: Optional[str] = None):
        """
        Stop the spinner and show completion status.

        Args:
            success: Whether the tool execution succeeded
            error_msg: Optional error message if failed
        """
        if self.live:
            self.live.stop()

        # Show completion message (NO EMOJIS per user request)
        if success:
            console.print(f"[green]{self.message}[/green]")
        else:
            error_display = f" - {error_msg}" if error_msg else ""
            console.print(f"[red]{self.message}{error_display}[/red]")

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        success = exc_type is None
        error_msg = str(exc_val) if exc_val else None
        self.stop(success=success, error_msg=error_msg)


class ThinkingIndicator:
    """Animated thinking indicator for agent processing."""

    def __init__(self, message: str = "Agent thinking"):
        """
        Initialize thinking indicator.

        Args:
            message: Message to display
        """
        self.message = message
        self.live = None
        self.spinner = None

    def start(self):
        """Start the thinking animation."""
        self.spinner = Spinner("dots", text=self.message, style="dim cyan")
        self.live = Live(self.spinner, console=console, refresh_per_second=10)
        self.live.start()

    def stop(self):
        """Stop the thinking animation."""
        if self.live:
            self.live.stop()

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()


class StreamBuffer:
    """
    Buffer for streaming text that detects and suppresses tool calls.

    Parses streaming chunks to detect when tool call JSON blocks appear,
    allowing them to be suppressed and replaced with clean animations.
    """

    def __init__(self, enabled: bool = True):
        """
        Initialize stream buffer.

        Args:
            enabled: Whether to suppress tool calls (if False, shows raw output)
        """
        self.enabled = enabled
        self.accumulated = ""  # All text accumulated so far
        self.last_display_pos = 0  # Position up to which we've displayed
        self.in_tool_call = False
        self.tool_call_start = -1

    def process_chunk(self, chunk: str) -> tuple[str, Optional[dict]]:
        """
        Process a streaming chunk.

        Args:
            chunk: Text chunk from LLM

        Returns:
            Tuple of (text_to_display, tool_call_dict_if_complete)
        """
        if not self.enabled:
            return chunk, None

        # Add chunk to accumulated text
        self.accumulated += chunk
        display_text = ""
        tool_call = None

        # Look for tool call markers in accumulated text
        if not self.in_tool_call:
            # Check if we're entering a tool call
            tool_call_match = self.accumulated.find(
                "```tool_call", self.last_display_pos
            )
            if tool_call_match >= 0:
                # Display everything up to the tool call marker
                display_text = self.accumulated[self.last_display_pos : tool_call_match]
                self.last_display_pos = tool_call_match
                self.in_tool_call = True
                self.tool_call_start = tool_call_match
            else:
                # No tool call found - display the new chunk as normal
                # Display everything from last position to current end
                display_text = self.accumulated[self.last_display_pos :]
                self.last_display_pos = len(self.accumulated)
        else:
            # We're in a tool call, look for the closing ```
            # Find closing ``` after the opening
            close_match = self.accumulated.find(
                "```", self.tool_call_start + 13
            )  # +13 for "```tool_call\n"
            if close_match >= 0:
                # Found end of tool call
                # Extract and parse the tool call
                tool_call_text = self.accumulated[
                    self.tool_call_start : close_match + 3
                ]
                tool_call = self._parse_tool_call(tool_call_text)

                # Skip past the entire tool call block
                self.last_display_pos = close_match + 3
                self.in_tool_call = False
                self.tool_call_start = -1

        return display_text, tool_call

    def _parse_tool_call(self, text: str) -> Optional[dict]:
        """
        Parse tool call JSON from text.

        Args:
            text: Full tool call block including markers

        Returns:
            Parsed tool call dict or None if parsing fails
        """
        import json
        import re

        try:
            # Extract JSON between ```tool_call and ```
            pattern = r"```tool_call\s*\n(.*?)\n```"
            match = re.search(pattern, text, re.DOTALL)
            if match:
                json_str = match.group(1).strip()
                return json.loads(json_str)
        except (json.JSONDecodeError, AttributeError):
            pass

        return None

    def reset(self):
        """Reset buffer state."""
        self.accumulated = ""
        self.last_display_pos = 0
        self.in_tool_call = False
        self.tool_call_start = -1
