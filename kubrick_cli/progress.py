"""Progress tracking and visualization for multi-step tasks."""

from typing import Optional

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)

console = Console()


class ProgressTracker:
    """
    Tracks and displays progress for multi-step agentic tasks.

    Provides visual feedback during long-running operations.
    """

    def __init__(self, enabled: bool = True):
        """
        Initialize progress tracker.

        Args:
            enabled: Whether progress tracking is enabled
        """
        self.enabled = enabled
        self.progress: Optional[Progress] = None
        self.current_task: Optional[TaskID] = None
        self.step_count = 0
        self.total_steps = 0

    def start(self, total_steps: int = None, description: str = "Working"):
        """
        Start progress tracking.

        Args:
            total_steps: Total number of steps (if known)
            description: Initial description
        """
        if not self.enabled:
            return

        self.total_steps = total_steps or 0
        self.step_count = 0

        if total_steps:
            self.progress = Progress(
                SpinnerColumn(),
                TextColumn("[bold cyan]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeElapsedColumn(),
                console=console,
            )
        else:
            self.progress = Progress(
                SpinnerColumn(),
                TextColumn("[bold cyan]{task.description}"),
                TimeElapsedColumn(),
                console=console,
            )

        self.progress.start()
        self.current_task = self.progress.add_task(description, total=total_steps)

    def update(self, description: str = None, advance: int = 1, completed: int = None):
        """
        Update progress.

        Args:
            description: New description (optional)
            advance: Amount to advance (default: 1)
            completed: Set absolute completion (optional)
        """
        if not self.enabled or not self.progress:
            return

        if completed is not None:
            self.step_count = completed
            self.progress.update(self.current_task, completed=completed)
        else:
            self.step_count += advance
            self.progress.update(self.current_task, advance=advance)

        if description:
            self.progress.update(self.current_task, description=description)

    def update_description(self, description: str):
        """
        Update just the description.

        Args:
            description: New description
        """
        if not self.enabled or not self.progress:
            return

        self.progress.update(self.current_task, description=description)

    def step(self, description: str):
        """
        Mark a step complete with new description.

        Args:
            description: Description of the new step
        """
        if not self.enabled or not self.progress:
            console.print(f"[dim]→ {description}[/dim]")
            return

        self.step_count += 1
        step_info = ""
        if self.total_steps > 0:
            step_info = f"[Step {self.step_count}/{self.total_steps}] "

        self.progress.update(
            self.current_task,
            description=f"{step_info}{description}",
            advance=1,
        )

    def complete(self, message: str = "Complete"):
        """
        Mark progress as complete.

        Args:
            message: Completion message
        """
        if not self.enabled or not self.progress:
            return

        if self.total_steps:
            self.progress.update(self.current_task, completed=self.total_steps)

        self.progress.update(self.current_task, description=message)
        self.progress.stop()
        self.progress = None
        self.current_task = None

    def stop(self):
        """Stop progress tracking."""
        if not self.enabled or not self.progress:
            return

        self.progress.stop()
        self.progress = None
        self.current_task = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self.progress:
            self.stop()
