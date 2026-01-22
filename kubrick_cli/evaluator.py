"""Task evaluation using a lightweight LLM checker."""

import json
from dataclasses import dataclass
from typing import Dict, List, Optional

from rich.console import Console

console = Console()


@dataclass
class EvaluationResult:
    """Result of task evaluation."""

    is_complete: bool
    confidence: float  # 0.0 to 1.0
    reasoning: str
    status: str  # planning, executing, verifying, stuck, complete, needs_clarification
    recommendation: str  # continue, stop, ask_user
    next_action: Optional[str] = None
    user_question: Optional[str] = None


class TaskEvaluator:
    """
    Lightweight LLM-based evaluator for task completion and status.

    Uses a cheap/fast model to periodically check if the agent has
    completed the task, is stuck, or needs user input.
    """

    def __init__(
        self,
        llm_client,
        provider_name: str,
        fast_model: Optional[str] = None,
        enabled: bool = True,
    ):
        """
        Initialize task evaluator.

        Args:
            llm_client: LLM client for evaluation
            provider_name: Provider name (for model selection)
            fast_model: Optional fast model name (uses main model if None)
            enabled: Whether evaluation is enabled
        """
        self.llm_client = llm_client
        self.provider_name = provider_name
        self.fast_model = fast_model
        self.enabled = enabled
        self.evaluation_count = 0
        self.last_status = None

    def should_evaluate(
        self,
        iteration: int,
        has_tool_calls: bool,
        response_length: int,
        max_iterations: int,
    ) -> bool:
        """
        Determine if we should run evaluation at this point.

        Smart triggers:
        1. Every 2 iterations (periodic monitoring)
        2. Always when no tool calls (might be done or stuck)
        3. When approaching max iterations (iteration >= max - 2)
        4. Long response without tools (might have forgotten)

        Args:
            iteration: Current iteration number
            has_tool_calls: Whether response has tool calls
            response_length: Length of response text
            max_iterations: Maximum iterations allowed

        Returns:
            True if evaluation should run
        """
        if not self.enabled:
            return False

        # Trigger 1: Periodic check every 2 iterations (after iteration 2)
        if iteration > 2 and iteration % 2 == 0:
            return True

        # Trigger 2: No tool calls (critical - might be done or stuck)
        if not has_tool_calls and iteration > 1:
            return True

        # Trigger 3: Approaching max iterations
        if iteration >= max_iterations - 2:
            return True

        # Trigger 4: Long response without tools
        if not has_tool_calls and response_length > 300:
            return True

        return False

    def evaluate(
        self,
        user_request: str,
        conversation_history: List[Dict],
        current_iteration: int,
        tool_calls_count: int,
        agent_response: str,
    ) -> EvaluationResult:
        """
        Evaluate task status using LLM.

        Args:
            user_request: Original user request
            conversation_history: Recent conversation messages
            current_iteration: Current iteration number
            tool_calls_count: Number of tool calls in last response
            agent_response: Agent's last response text

        Returns:
            EvaluationResult with status and recommendations
        """
        self.evaluation_count += 1

        # Build condensed conversation context (last 6 messages max)
        recent_messages = conversation_history[-6:]
        context = self._format_conversation(recent_messages)

        # Build evaluation prompt
        prompt = f"""You are a task completion evaluator. \
Analyze this agent conversation and determine the status.

**Original User Request:**
{user_request}

**Recent Conversation:**
{context}

**Current Status:**
- Iteration: {current_iteration}
- Tool calls in last response: {tool_calls_count}
- Agent's last response length: {len(agent_response)} characters

**Your Job:**
Determine if the agent has completed the user's request, is making progress, \
is stuck, or needs user input.

**Consider these questions:**
1. Has the agent ACTUALLY done what the user asked? (Not just talked about it)
2. If the request was to create/write code, has the agent RUN it to verify?
3. If the request was to create a file, has the agent VERIFIED it exists?
4. Is the agent stuck in a loop (repeating the same action)?
5. Is the agent describing what it will do without actually doing it?
6. Does the agent need user clarification or decision?

**Response Format (JSON only, no other text):**
```json
{{
  "is_complete": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation of why you made this determination",
  "status": "one of: planning|executing|verifying|stuck|complete|needs_clarification",
  "recommendation": "one of: continue|stop|ask_user",
  "next_action": "What the agent should do next (null if complete)",
  "user_question": "Question to ask user (null unless recommendation is ask_user)"
}}
```

**Status Definitions:**
- planning: Agent is analyzing or planning next steps
- executing: Agent is actively using tools to complete the task
- verifying: Agent is checking/testing their work
- stuck: Agent is repeating actions or not making progress
- complete: Task is fully done and verified
- needs_clarification: Agent needs user input to proceed

**Examples:**

User: "Write me a poem about cats"
Agent: "[writes a beautiful poem about cats]"
→ {{"is_complete": true, "status": "complete", "recommendation": "stop"}}

User: "Create a Python script that prints hello world"
Agent: "I'll create the script." [calls write_file]
→ {{"is_complete": false, "status": "executing", "recommendation": \
"continue", "next_action": "Agent should run the script to verify it works"}}

User: "Create hello.py"
Agent: "Let's start by creating the file." [no tool calls]
→ {{"is_complete": false, "status": "stuck", "recommendation": "continue", \
"next_action": "Agent should call write_file immediately"}}

User: "Fix the bug"
Agent: "I need more information about the bug"
→ {{"is_complete": false, "status": "needs_clarification", "recommendation": \
"ask_user", "user_question": "Can you describe the bug you're experiencing?"}}

Respond with ONLY the JSON object, no other text."""

        try:
            # Call LLM with low token limit (this is a small, focused task)
            messages = [{"role": "user", "content": prompt}]

            response = self.llm_client.generate(
                messages,
                stream_options={
                    "max_tokens": 300,  # Keep evaluation concise
                    "temperature": 0.3,  # Lower temperature for consistency
                },
            )

            # Parse JSON response
            result = self._parse_evaluation_response(response)

            # Store last status for tracking
            self.last_status = result.status

            # Log evaluation
            console.print(
                f"[dim]→ Evaluator check #{self.evaluation_count}: "
                f"{result.status} (confidence: {result.confidence:.0%})[/dim]"
            )

            return result

        except Exception as e:
            console.print(f"[yellow]⚠ Evaluation failed: {e}[/yellow]")
            # Fallback: assume continuing is safe
            return EvaluationResult(
                is_complete=False,
                confidence=0.0,
                reasoning=f"Evaluation error: {e}",
                status="executing",
                recommendation="continue",
            )

    def _format_conversation(self, messages: List[Dict]) -> str:
        """Format conversation messages for evaluation context."""
        formatted = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            # Truncate long messages
            if len(content) > 500:
                content = content[:500] + "... [truncated]"

            formatted.append(f"{role.upper()}: {content}")

        return "\n\n".join(formatted)

    def _parse_evaluation_response(self, response: str) -> EvaluationResult:
        """Parse LLM evaluation response into EvaluationResult."""
        # Extract JSON from response (might have markdown fences)
        json_start = response.find("{")
        json_end = response.rfind("}") + 1

        if json_start >= 0 and json_end > json_start:
            json_str = response[json_start:json_end]
            data = json.loads(json_str)

            return EvaluationResult(
                is_complete=data.get("is_complete", False),
                confidence=float(data.get("confidence", 0.5)),
                reasoning=data.get("reasoning", ""),
                status=data.get("status", "executing"),
                recommendation=data.get("recommendation", "continue"),
                next_action=data.get("next_action"),
                user_question=data.get("user_question"),
            )

        # Fallback if parsing fails
        raise ValueError(f"Could not parse evaluation response: {response}")

    def get_stats(self) -> Dict:
        """Get evaluation statistics."""
        return {
            "total_evaluations": self.evaluation_count,
            "last_status": self.last_status,
            "enabled": self.enabled,
        }
