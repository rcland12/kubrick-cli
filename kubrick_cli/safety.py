"""Safety manager for dangerous command detection and validation."""

import re
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

console = Console()


@dataclass
class SafetyConfig:
    """Safety configuration settings."""

    max_iterations: int = 15
    max_tools_per_turn: int = 5
    total_timeout_seconds: int = 600
    tool_timeout_seconds: int = 30
    max_file_size_mb: int = 10
    require_dangerous_command_confirmation: bool = True

    @classmethod
    def from_config(cls, config: Dict) -> "SafetyConfig":
        """
        Create SafetyConfig from configuration dict.

        Args:
            config: Configuration dictionary

        Returns:
            SafetyConfig instance
        """
        return cls(
            max_iterations=config.get("max_iterations", 15),
            max_tools_per_turn=config.get("max_tools_per_turn", 5),
            total_timeout_seconds=config.get("total_timeout_seconds", 600),
            tool_timeout_seconds=config.get("tool_timeout_seconds", 30),
            max_file_size_mb=config.get("max_file_size_mb", 10),
            require_dangerous_command_confirmation=config.get(
                "require_dangerous_command_confirmation", True
            ),
        )


class SafetyManager:
    """
    Manages safety checks for tool execution.

    Features:
    - Dangerous command detection
    - User confirmation prompts
    - File size limits
    - Timeout enforcement
    """

    # Dangerous bash command patterns
    DANGEROUS_PATTERNS = [
        (r"\brm\s+-rf\s+/", "Recursive delete from root"),
        (r"\brm\s+-rf\s+~", "Recursive delete from home"),
        (r"\brm\s+-rf\s+\*", "Recursive delete all files"),
        (r"\brm\s+-rf", "Recursive force delete"),
        (r"\bsudo\b", "Elevated privileges"),
        (r"\bchmod\s+777", "Overly permissive permissions"),
        (r"\bchmod\s+-R\s+777", "Recursive overly permissive permissions"),
        (r">\s*/dev/", "Writing to device files"),
        (r"\bgit\s+push\s+--force", "Force push to git"),
        (r"\bgit\s+push\s+-f", "Force push to git (short form)"),
        (r"\bmkfs\b", "Format filesystem"),
        (r"\bdd\s+.*of=/dev", "Writing to block device"),
        (r"\b:(\()\|:\1&", "Fork bomb"),
        (r"\bcurl\b.*\|\s*bash", "Pipe curl to bash"),
        (r"\bwget\b.*\|\s*bash", "Pipe wget to bash"),
        (r"\beval\b.*\$\(", "Eval with command substitution"),
    ]

    def __init__(self, config: SafetyConfig):
        """
        Initialize safety manager.

        Args:
            config: SafetyConfig instance
        """
        self.config = config

    def validate_bash_command(
        self, command: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate a bash command for dangerous patterns.

        Args:
            command: The bash command to validate

        Returns:
            Tuple of (is_safe, warning_message)
            - is_safe: True if safe, False if dangerous
            - warning_message: Description of the danger (if any)
        """
        command_lower = command.lower()

        # Check each dangerous pattern
        for pattern, description in self.DANGEROUS_PATTERNS:
            if re.search(pattern, command_lower, re.IGNORECASE):
                return False, f"Dangerous command detected: {description}"

        return True, None

    def get_user_confirmation(
        self, warning: str, command: str
    ) -> bool:
        """
        Get user confirmation for a dangerous command.

        Args:
            warning: Warning message
            command: The dangerous command

        Returns:
            True if user confirms, False otherwise
        """
        if not self.config.require_dangerous_command_confirmation:
            # Auto-allow if confirmation disabled
            return True

        # Display warning
        console.print(
            Panel(
                f"[bold red]⚠️  WARNING[/bold red]\n\n"
                f"{warning}\n\n"
                f"[bold]Command:[/bold]\n"
                f"[yellow]{command}[/yellow]\n\n"
                f"This command could be dangerous.",
                border_style="red",
                title="Safety Check",
            )
        )

        # Ask for confirmation
        confirmed = Confirm.ask(
            "[bold red]Do you want to execute this command?[/bold red]",
            default=False,
        )

        if confirmed:
            console.print("[yellow]⚠️  Proceeding with caution...[/yellow]")
        else:
            console.print("[green]✓ Command cancelled[/green]")

        return confirmed

    def validate_file_size(self, file_path: str, size_bytes: int) -> bool:
        """
        Validate file size against limits.

        Args:
            file_path: Path to the file
            size_bytes: File size in bytes

        Returns:
            True if within limits, False otherwise
        """
        max_bytes = self.config.max_file_size_mb * 1024 * 1024

        if size_bytes > max_bytes:
            console.print(
                f"[yellow]⚠️  File {file_path} exceeds size limit "
                f"({size_bytes / 1024 / 1024:.1f}MB > {self.config.max_file_size_mb}MB)[/yellow]"
            )
            return False

        return True

    def check_iteration_limit(
        self, current: int, max_iterations: int
    ) -> bool:
        """
        Check if iteration limit has been reached.

        Args:
            current: Current iteration number
            max_iterations: Maximum allowed iterations

        Returns:
            True if within limit, False otherwise
        """
        if current >= max_iterations:
            console.print(
                f"[yellow]⚠️  Max iteration limit reached ({max_iterations})[/yellow]"
            )
            return False

        return True

    def check_tool_limit(
        self, current: int, max_tools: int
    ) -> bool:
        """
        Check if tool call limit has been reached.

        Args:
            current: Current number of tool calls
            max_tools: Maximum allowed tools

        Returns:
            True if within limit, False otherwise
        """
        if current > max_tools:
            console.print(
                f"[yellow]⚠️  Too many tool calls ({current} > {max_tools})[/yellow]"
            )
            return False

        return True
