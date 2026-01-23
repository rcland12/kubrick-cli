"""Safety manager for dangerous command detection and validation."""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Set, Tuple

import questionary
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

    def __init__(self, config: SafetyConfig, kubrick_config=None, working_dir=None):
        """
        Initialize safety manager.

        Args:
            config: SafetyConfig instance
            kubrick_config: KubrickConfig instance for persistent permissions
            working_dir: Current working directory
        """
        self.config = config
        self.kubrick_config = kubrick_config
        self.working_dir = str(Path(working_dir or os.getcwd()).resolve())

        # Session-only permission caching (temporary)
        self.allowed_file_writes: Set[str] = (
            set()
        )  # Specific file paths allowed for this session
        self.allow_all_file_writes: bool = (
            False  # Blanket permission for all writes (session)
        )
        self.allowed_bash_commands: Set[str] = (
            set()
        )  # Specific commands allowed (session)
        self.allow_all_bash: bool = False  # Blanket permission for bash (session)

    def validate_bash_command(self, command: str) -> Tuple[bool, Optional[str]]:
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

        for pattern, description in self.DANGEROUS_PATTERNS:
            if re.search(pattern, command_lower, re.IGNORECASE):
                return False, f"Dangerous command detected: {description}"

        return True, None

    def get_user_confirmation(self, warning: str, command: str) -> bool:
        """
        Get user confirmation for a dangerous command.

        Args:
            warning: Warning message
            command: The dangerous command

        Returns:
            True if user confirms, False otherwise
        """
        if not self.config.require_dangerous_command_confirmation:
            return True

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

    def check_iteration_limit(self, current: int, max_iterations: int) -> bool:
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

    def check_tool_limit(self, current: int, max_tools: int) -> bool:
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

    def check_file_write_permission(
        self, file_path: str, operation: str = "write_file"
    ) -> bool:
        """
        Check if file write operation is permitted.

        Checks in order:
        1. Session blanket permission (allow_all_file_writes)
        2. Session-specific file permission (allowed_file_writes set)
        3. Persistent directory permission (from config)
        4. Prompt user with arrow-key selection

        Args:
            file_path: Path to the file
            operation: Type of operation (write_file, edit_file, create_directory)

        Returns:
            True if permitted, False otherwise
        """
        # If blanket session permission granted, allow
        if self.allow_all_file_writes:
            return True

        # Resolve to absolute path for consistent checking
        abs_path = str(Path(file_path).resolve())

        # Check if this specific path was already allowed in this session
        if abs_path in self.allowed_file_writes:
            return True

        # Check persistent directory permission (from config)
        if self.kubrick_config:
            dir_permission = self.kubrick_config.get_directory_permission(
                self.working_dir, operation
            )
            if dir_permission == "allow":
                return True
            elif dir_permission == "deny":
                console.print(
                    f"[red]✗ Operation denied by directory rule: {self.working_dir}[/red]"
                )
                return False

        # Prompt user for permission with arrow-key selection
        console.print(
            Panel(
                f"[bold yellow]🔒 File Permission Required[/bold yellow]\n\n"
                f"[bold]Operation:[/bold] {operation}\n"
                f"[bold]File:[/bold] {file_path}\n"
                f"[bold]Directory:[/bold] {self.working_dir}\n\n"
                f"Kubrick wants to modify this file.",
                border_style="yellow",
                title="Permission Request",
            )
        )

        try:
            choice = questionary.select(
                "How would you like to respond?",
                choices=[
                    "Yes, just this once",
                    "Yes, for this conversation",
                    "Yes, always in this directory",
                    "No, not this time",
                    "No, never in this directory",
                ],
                style=questionary.Style(
                    [
                        ("selected", "fg:cyan bold"),
                        ("pointer", "fg:cyan bold"),
                        ("highlighted", "fg:cyan"),
                    ]
                ),
            ).ask()

            if choice is None:  # User pressed Ctrl+C
                console.print("[yellow]✗ Operation cancelled[/yellow]")
                return False

            if choice == "Yes, just this once":
                console.print("[green]✓ Allowed once[/green]")
                return True

            elif choice == "Yes, for this conversation":
                self.allowed_file_writes.add(abs_path)
                console.print(
                    f"[green]✓ Allowed for this conversation: {file_path}[/green]"
                )
                return True

            elif choice == "Yes, always in this directory":
                if self.kubrick_config:
                    self.kubrick_config.set_directory_permission(
                        self.working_dir, operation, "allow"
                    )
                    console.print(
                        f"[green]✓ {operation} always allowed in {self.working_dir}[/green]"
                    )
                else:
                    # Fallback to session permission
                    self.allowed_file_writes.add(abs_path)
                    console.print(
                        f"[green]✓ Allowed for this conversation: {file_path}[/green]"
                    )
                return True

            elif choice == "No, not this time":
                console.print("[yellow]✗ Operation denied[/yellow]")
                return False

            elif choice == "No, never in this directory":
                if self.kubrick_config:
                    self.kubrick_config.set_directory_permission(
                        self.working_dir, operation, "deny"
                    )
                    console.print(
                        f"[red]✗ {operation} permanently denied in {self.working_dir}[/red]"
                    )
                else:
                    console.print("[red]✗ Operation denied[/red]")
                return False

            return False

        except Exception as e:
            # Fallback to simple confirmation on error
            console.print(f"[yellow]Error with selection menu: {e}[/yellow]")
            from rich.prompt import Confirm

            return Confirm.ask("Allow this operation?", default=False)

    def check_bash_permission(self, command: str, is_dangerous: bool = False) -> bool:
        """
        Check if bash command execution is permitted.

        Checks in order:
        1. Session blanket permission (allow_all_bash)
        2. Session-specific command permission (allowed_bash_commands set)
        3. Persistent directory permission (from config)
        4. Prompt user with arrow-key selection

        Args:
            command: The bash command
            is_dangerous: Whether the command was flagged as dangerous

        Returns:
            True if permitted, False otherwise
        """
        # If blanket session permission granted, allow (but still check dangerous commands)
        if self.allow_all_bash and not is_dangerous:
            return True

        # Check if this specific command was already allowed in this session
        if command in self.allowed_bash_commands:
            return True

        # For dangerous commands, use existing validation flow
        if is_dangerous:
            return False  # Will be handled by validate_bash_command

        # Check persistent directory permission (from config)
        if self.kubrick_config:
            dir_permission = self.kubrick_config.get_directory_permission(
                self.working_dir, "run_bash"
            )
            if dir_permission == "allow":
                return True
            elif dir_permission == "deny":
                console.print(
                    f"[red]✗ Bash commands denied by directory rule: {self.working_dir}[/red]"
                )
                return False

        # Prompt user for permission with arrow-key selection
        console.print(
            Panel(
                f"[bold yellow]🔒 Bash Permission Required[/bold yellow]\n\n"
                f"[bold]Command:[/bold]\n"
                f"[yellow]{command}[/yellow]\n"
                f"[bold]Directory:[/bold] {self.working_dir}\n\n"
                f"Kubrick wants to execute this command.",
                border_style="yellow",
                title="Permission Request",
            )
        )

        try:
            choice = questionary.select(
                "How would you like to respond?",
                choices=[
                    "Yes, just this once",
                    "Yes, for this conversation",
                    "Yes, always in this directory",
                    "No, not this time",
                    "No, never in this directory",
                ],
                style=questionary.Style(
                    [
                        ("selected", "fg:cyan bold"),
                        ("pointer", "fg:cyan bold"),
                        ("highlighted", "fg:cyan"),
                    ]
                ),
            ).ask()

            if choice is None:  # User pressed Ctrl+C
                console.print("[yellow]✗ Command cancelled[/yellow]")
                return False

            if choice == "Yes, just this once":
                console.print("[green]✓ Allowed once[/green]")
                return True

            elif choice == "Yes, for this conversation":
                self.allowed_bash_commands.add(command)
                console.print("[green]✓ Allowed for this conversation[/green]")
                return True

            elif choice == "Yes, always in this directory":
                if self.kubrick_config:
                    self.kubrick_config.set_directory_permission(
                        self.working_dir, "run_bash", "allow"
                    )
                    console.print(
                        f"[green]✓ Bash commands always allowed in {self.working_dir}[/green]"
                    )
                else:
                    # Fallback to session permission
                    self.allow_all_bash = True
                    console.print(
                        "[green]✓ Allowed all bash commands for this conversation[/green]"
                    )
                return True

            elif choice == "No, not this time":
                console.print("[yellow]✗ Command denied[/yellow]")
                return False

            elif choice == "No, never in this directory":
                if self.kubrick_config:
                    self.kubrick_config.set_directory_permission(
                        self.working_dir, "run_bash", "deny"
                    )
                    console.print(
                        f"[red]✗ Bash commands permanently denied in {self.working_dir}[/red]"
                    )
                else:
                    console.print("[red]✗ Command denied[/red]")
                return False

            return False

        except Exception as e:
            # Fallback to simple confirmation on error
            console.print(f"[yellow]Error with selection menu: {e}[/yellow]")
            return Confirm.ask("Allow this command?", default=False)
