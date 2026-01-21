"""Multi-step agentic execution loop with completion detection."""

import re
from typing import Dict, List, Tuple

from rich.console import Console

console = Console()

try:
    from .display import DisplayManager
except ImportError:
    DisplayManager = None

try:
    from .scheduler import ToolScheduler
except ImportError:
    ToolScheduler = None


class CompletionDetector:
    """Detects when an agent has completed its task."""

    COMPLETION_MARKERS = [
        "TASK_COMPLETE",
        "PLAN_COMPLETE",
        "[COMPLETE]",
        "[DONE]",
    ]

    @staticmethod
    def is_complete(
        response_text: str,
        has_tool_calls: bool,
        iteration: int,
        max_iterations: int,
    ) -> Tuple[bool, str]:
        """
        Determine if the agent has completed its task.

        Args:
            response_text: The agent's response text
            has_tool_calls: Whether the response contains tool calls
            iteration: Current iteration number
            max_iterations: Maximum allowed iterations

        Returns:
            Tuple of (is_complete, reason)
        """
        for marker in CompletionDetector.COMPLETION_MARKERS:
            if marker in response_text:
                return True, f"explicit_marker:{marker}"

        if iteration >= max_iterations:
            return True, "max_iterations_reached"

        if not has_tool_calls:
            if CompletionDetector._looks_conclusive(response_text):
                return True, "conclusive_response"

        return False, "continuing"

    @staticmethod
    def _looks_conclusive(text: str) -> bool:
        """
        Check if text looks like a conclusive response.

        This is a heuristic to detect when the agent is done without
        explicitly saying so.
        """
        text_lower = text.lower()

        conclusive_patterns = [
            r"\b(done|completed|finished|ready)\b",
            r"\b(successfully|all set|good to go)\b",
            r"\bhere(?:'s| is) (?:the |a )?(?:summary|result)",
            r"\b(?:task|work|changes) (?:is |are )?(?:complete|done|finished)",
            r"\blet me know if you need",
            r"\bthat(?:'s| should do it)",
            r"\beverything(?:'s| is) (?:set|ready|done)",
        ]

        for pattern in conclusive_patterns:
            if re.search(pattern, text_lower):
                return True

        return False


class AgentLoop:
    """
    Multi-step agentic execution loop.

    Runs iteratively until the task is complete or max iterations reached.
    """

    def __init__(
        self,
        llm_client,
        tool_executor,
        max_iterations: int = 15,
        max_tools_per_turn: int = 5,
        timeout_seconds: int = 600,
        stream_options: Dict = None,
        display_manager=None,
        tool_scheduler=None,
        context_manager=None,
    ):
        """
        Initialize the agent loop.

        Args:
            llm_client: LLM client instance (e.g., TritonLLMClient)
            tool_executor: Tool executor instance
            max_iterations: Maximum number of iterations
            max_tools_per_turn: Maximum tools per turn
            timeout_seconds: Total timeout in seconds
            stream_options: Optional streaming options
            display_manager: Optional DisplayManager instance for natural language display
            tool_scheduler: Optional ToolScheduler for parallel execution
            context_manager: Optional ContextManager for context window management
        """
        self.llm_client = llm_client
        self.tool_executor = tool_executor
        self.max_iterations = max_iterations
        self.max_tools_per_turn = max_tools_per_turn
        self.timeout_seconds = timeout_seconds
        self.stream_options = stream_options or {}
        self.display_manager = display_manager
        self.tool_scheduler = tool_scheduler
        self.context_manager = context_manager

        # Initialize tool result truncator if context management is enabled
        if context_manager:
            from .context_manager import ToolResultTruncator

            max_chars = context_manager.config.get("max_tool_result_chars", 10000)
            self.truncator = ToolResultTruncator(max_chars=max_chars)
        else:
            self.truncator = None

    def run(
        self,
        messages: List[Dict],
        tool_parser,
        display_callback=None,
    ) -> Dict:
        """
        Run the agentic loop.

        Args:
            messages: Conversation messages (will be modified in-place)
            tool_parser: Function to parse tool calls from text
            display_callback: Optional callback for displaying streaming response

        Returns:
            Dict with execution results and metadata
        """
        iteration = 0
        total_tool_calls = 0

        while iteration < self.max_iterations:
            iteration += 1

            console.print(
                f"\n[dim]→ Agent iteration {iteration}/{self.max_iterations}[/dim]"
            )

            console.print("[bold cyan]Assistant:[/bold cyan]")
            chunks = []

            try:
                for chunk in self.llm_client.generate_streaming(
                    messages, stream_options=self.stream_options
                ):
                    console.print(chunk, end="")
                    chunks.append(chunk)

                console.print("\n")

            except Exception as e:
                console.print(f"\n[red]Error during LLM generation: {e}[/red]")
                return {
                    "success": False,
                    "error": str(e),
                    "iterations": iteration,
                    "tool_calls": total_tool_calls,
                }

            response_text = "".join(chunks)

            messages.append({"role": "assistant", "content": response_text})

            if display_callback:
                display_callback(response_text)

            tool_calls = tool_parser(response_text)

            is_complete, reason = CompletionDetector.is_complete(
                response_text=response_text,
                has_tool_calls=len(tool_calls) > 0,
                iteration=iteration,
                max_iterations=self.max_iterations,
            )

            if is_complete:
                console.print(f"\n[green]✓ Task complete ({reason})[/green]")
                return {
                    "success": True,
                    "completion_reason": reason,
                    "iterations": iteration,
                    "tool_calls": total_tool_calls,
                }

            if tool_calls:
                if len(tool_calls) > self.max_tools_per_turn:
                    console.print(
                        f"[yellow]⚠ Too many tool calls ({len(tool_calls)}), "
                        f"limiting to {self.max_tools_per_turn}[/yellow]"
                    )
                    tool_calls = tool_calls[: self.max_tools_per_turn]

                console.print(
                    f"\n[yellow]Executing {len(tool_calls)} tool(s)...[/yellow]\n"
                )

                if self.tool_scheduler and len(tool_calls) > 1:
                    execution_results = self.tool_scheduler.execute_tools(tool_calls)
                else:
                    execution_results = [
                        self.tool_executor.execute(tool_name, params)
                        for tool_name, params in tool_calls
                    ]

                tool_results = []
                for (tool_name, parameters), result in zip(
                    tool_calls, execution_results
                ):
                    if self.display_manager:
                        self.display_manager.display_tool_call(tool_name, parameters)
                        self.display_manager.display_tool_result(
                            tool_name, result, result["success"]
                        )
                    else:
                        console.print(f"[cyan]→ Called {tool_name}[/cyan]")
                        if result["success"]:
                            console.print(f"[green]✓ {tool_name} succeeded[/green]")
                        else:
                            console.print(
                                f"[red]✗ {tool_name} failed: {result['error']}[/red]"
                            )

                    if result["success"]:
                        result_text = str(result["result"])
                        # Truncate tool result if context management is enabled
                        if self.truncator:
                            result_text = self.truncator.truncate_result(
                                result_text, tool_name
                            )
                        tool_results.append(f"Tool: {tool_name}\nResult: {result_text}")
                    else:
                        error_text = str(result["error"])
                        # Truncate error messages too (though typically short)
                        if self.truncator:
                            error_text = self.truncator.truncate_result(
                                error_text, tool_name
                            )
                        tool_results.append(f"Tool: {tool_name}\nError: {error_text}")

                    total_tool_calls += 1

                tool_results_text = "\n\n".join(tool_results)
                messages.append(
                    {
                        "role": "user",
                        "content": f"Tool execution results:\n\n{tool_results_text}",
                    }
                )

                continue

            console.print(
                "[yellow]⚠ No tool calls and task not marked complete. Continuing...[/yellow]"
            )

        console.print(
            f"\n[yellow]⚠ Max iterations ({self.max_iterations}) reached[/yellow]"
        )
        return {
            "success": True,
            "completion_reason": "max_iterations",
            "iterations": iteration,
            "tool_calls": total_tool_calls,
        }
