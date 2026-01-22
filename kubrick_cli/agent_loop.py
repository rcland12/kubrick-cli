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

try:
    from .animated_display import StreamBuffer, ThinkingIndicator, ToolSpinner
except ImportError:
    StreamBuffer = None
    ThinkingIndicator = None
    ToolSpinner = None


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

        # Check for phrases indicating the agent is about to START work (not conclusive)
        starting_patterns = [
            r"\blet'?s? start",
            r"\bi'?ll (?:start|begin|create|write)",
            r"\bi'?m (?:going to|about to)",
            r"\bfirst,? (?:i'?ll|let'?s|we'?ll)",
            r"\bnext,? (?:i'?ll|let'?s|we'?ll)",
            r"\bstep \d+",
            r"\bhere'?s? (?:the |a )?plan",
            r"\bwe (?:can|will|should) (?:start|begin|create)",
        ]

        for pattern in starting_patterns:
            if re.search(pattern, text_lower):
                return False  # Not conclusive, agent is about to start

        # Expanded patterns to catch genuine completions
        conclusive_patterns = [
            r"\b(done|completed|finished|ready)\b",
            r"\b(successfully|all set|good to go)\b",
            r"\bhere(?:'s| is) (?:the |a )?(?:poem|story|joke)",  # Only for creative content
            r"\b(?:task|work|changes) (?:is |are )?(?:complete|done|finished)",
            r"\blet me know if you need",
            r"\bthat(?:'s| should do it)",
            r"\beverything(?:'s| is) (?:set|ready|done)",
            r"\bhope (?:this|that) helps",
            r"\b(?:enjoy|hope you (?:like|enjoy))",
            r"\b(?:there you go|here you are)",
            r"\bfeel free to",
            r"\bif you (?:need|want) (?:anything|more)",
        ]

        for pattern in conclusive_patterns:
            if re.search(pattern, text_lower):
                return True

        # Only check creative content for ACTUAL creative content (poems, stories)
        # Don't treat plans or descriptions as complete
        if len(text) > 300:  # Raised threshold
            # Very specific creative markers - only for actual creative writing
            specific_creative = [
                r"\b(?:poem|haiku|limerick|sonnet)\b.*\n.*\n",  # Poem with line breaks
                r"once upon a time",  # Story beginning
                r"(?:roses are red|twinkle.*little star)",  # Nursery rhymes
            ]

            for marker in specific_creative:
                if re.search(marker, text_lower, re.DOTALL):
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
        task_evaluator=None,
        clean_display: bool = False,
        session_stats=None,
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
            task_evaluator: Optional TaskEvaluator for intelligent completion detection
            clean_display: Enable clean display mode with animations (suppress raw JSON)
            session_stats: Optional session statistics tracker for UI updates
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
        self.task_evaluator = task_evaluator
        self.clean_display = clean_display
        self.session_stats = session_stats

        # Initialize tool result truncator if context management is enabled
        if context_manager:
            from .context_manager import ToolResultTruncator

            max_chars = context_manager.config.get("max_tool_result_chars", 10000)
            self.truncator = ToolResultTruncator(max_chars=max_chars)
        else:
            self.truncator = None

        # Initialize stream buffer for clean display
        if self.clean_display and StreamBuffer:
            self.stream_buffer = StreamBuffer(enabled=True)
        else:
            self.stream_buffer = None

    def run(
        self,
        messages: List[Dict],
        tool_parser,
        display_callback=None,
        user_request: str = None,
    ) -> Dict:
        """
        Run the agentic loop.

        Args:
            messages: Conversation messages (will be modified in-place)
            tool_parser: Function to parse tool calls from text
            display_callback: Optional callback for displaying streaming response
            user_request: Original user request (for evaluator context)

        Returns:
            Dict with execution results and metadata
        """
        # Set running status at start
        if self.session_stats:
            self.session_stats.running_status = "Agent running..."

        iteration = 0
        total_tool_calls = 0

        try:
            while iteration < self.max_iterations:
                iteration += 1

                console.print(
                    f"\n[dim]→ Agent iteration {iteration}/{self.max_iterations}[/dim]"
                )

                # Check and manage context before each LLM call
                if self.context_manager:
                    messages, context_info = self.context_manager.check_and_manage(
                        messages, reserve_output_tokens=True
                    )
                    if context_info.get("action_taken"):
                        console.print(
                            f"[yellow]→ Context managed: {context_info['action_taken']} "
                            f"({context_info['tokens_before']} → "
                            f"{context_info['tokens_after']} tokens, "
                            f"reserved {context_info['reserved_output_tokens']} "
                            "for output)[/yellow]"
                        )

                console.print("[bold cyan]Assistant:[/bold cyan]")
                chunks = []
                suppressed_tool_calls = []

                # Add max_tokens to stream_options if context manager is enabled
                stream_opts = self.stream_options.copy()
                if self.context_manager and "max_tokens" not in stream_opts:
                    stream_opts["max_tokens"] = self.context_manager.max_output_tokens

                try:
                    for chunk in self.llm_client.generate_streaming(
                        messages, stream_options=stream_opts
                    ):
                        # Process chunk through stream buffer if clean display enabled
                        if self.stream_buffer:
                            display_text, tool_call = self.stream_buffer.process_chunk(
                                chunk
                            )
                            if tool_call:
                                suppressed_tool_calls.append(tool_call)
                            if display_text:
                                console.print(display_text, end="")
                        else:
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

                # Reset stream buffer for next iteration
                if self.stream_buffer:
                    self.stream_buffer.reset()

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

                # Use evaluator for intelligent completion/status checking
                if self.task_evaluator and user_request:
                    should_eval = self.task_evaluator.should_evaluate(
                        iteration=iteration,
                        has_tool_calls=len(tool_calls) > 0,
                        response_length=len(response_text),
                        max_iterations=self.max_iterations,
                    )

                    if should_eval:
                        eval_result = self.task_evaluator.evaluate(
                            user_request=user_request,
                            conversation_history=messages,
                            current_iteration=iteration,
                            tool_calls_count=len(tool_calls),
                            agent_response=response_text,
                        )

                        console.print(
                            f"[dim]→ Evaluator: {eval_result.reasoning}[/dim]"
                        )

                        # Handle evaluator recommendations
                        if (
                            eval_result.recommendation == "stop"
                            and eval_result.is_complete
                        ):
                            console.print(
                                "\n[green]✓ Task complete "
                                f"(evaluator: {eval_result.status})[/green]"
                            )
                            return {
                                "success": True,
                                "completion_reason": f"evaluator_{eval_result.status}",
                                "iterations": iteration,
                                "tool_calls": total_tool_calls,
                            }

                        elif eval_result.recommendation == "ask_user":
                            # Ask user for clarification
                            console.print(
                                "\n[yellow]→ Agent needs clarification[/yellow]"
                            )
                            if eval_result.user_question:
                                from rich.prompt import Prompt

                                user_response = Prompt.ask(
                                    f"[bold cyan]{eval_result.user_question}[/bold cyan]"
                                )
                                # Add user's response to conversation
                                messages.append(
                                    {
                                        "role": "user",
                                        "content": f"User clarification: {user_response}",
                                    }
                                )
                                continue

                        elif eval_result.status == "stuck":
                            # Agent is stuck - give helpful feedback
                            console.print(
                                f"\n[yellow]→ Agent appears stuck: {eval_result.reasoning}[/yellow]"
                            )
                            if eval_result.next_action:
                                console.print(
                                    f"[dim]Hint: {eval_result.next_action}[/dim]"
                                )

                                # Ask if user wants to intervene
                                from rich.prompt import Prompt

                                choice = Prompt.ask(
                                    "[bold]Continue or stop?[/bold]",
                                    choices=["continue", "stop", "help"],
                                    default="continue",
                                )

                                if choice == "stop":
                                    console.print(
                                        "\n[yellow]Task stopped by user[/yellow]"
                                    )
                                    return {
                                        "success": False,
                                        "completion_reason": "user_stopped",
                                        "iterations": iteration,
                                        "tool_calls": total_tool_calls,
                                    }
                                elif choice == "help":
                                    help_msg = Prompt.ask(
                                        "[bold cyan]What guidance should I give the "
                                        "agent?[/bold cyan]"
                                    )
                                    messages.append(
                                        {
                                            "role": "user",
                                            "content": f"User guidance: {help_msg}",
                                        }
                                    )
                                    continue

                # Safety check: If agent keeps responding without tools at high iterations,
                # it might be stuck. Only apply this after several iterations.
                if not tool_calls and iteration >= 4:
                    # Check if this looks like a stuck loop (agent keeps talking without acting)
                    if len(response_text) > 50:
                        console.print(
                            "\n[yellow]→ Multiple iterations without tool calls. "
                            "Possible stuck loop detected.[/yellow]"
                        )
                        return {
                            "success": True,
                            "completion_reason": "no_tools_stuck_loop",
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

                    # Always show what tools are being executed
                    console.print(
                        f"\n[yellow]Executing {len(tool_calls)} tool(s)...[/yellow]\n"
                    )

                # Execute tools
                if self.tool_scheduler and len(tool_calls) > 1:
                    # Parallel execution
                    execution_results = self.tool_scheduler.execute_tools(tool_calls)
                else:
                    # Sequential execution
                    execution_results = []
                    for tool_name, params in tool_calls:
                        result = self.tool_executor.execute(tool_name, params)
                        execution_results.append(result)

                tool_results = []
                for (tool_name, parameters), result in zip(
                    tool_calls, execution_results
                ):
                    # Always show tool execution info (unless using display manager)
                    if self.display_manager:
                        self.display_manager.display_tool_call(tool_name, parameters)
                        self.display_manager.display_tool_result(
                            tool_name, result, result["success"]
                        )
                    else:
                        # Show tool execution - clean display only affects spinners, not this
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
        finally:
            # Clear running status when agent is done
            if self.session_stats:
                self.session_stats.running_status = None
