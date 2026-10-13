"""The agentic loop: call the model, run the tools it asks for, repeat."""

import concurrent.futures
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from .context_manager import ToolResultTruncator
from .glyphs import glyph
from .messages import MessageDone, TextDelta, ThinkingDelta, ToolCall, ToolCallEvent
from .providers.base import ProviderError, ToolsNotSupportedError
from .tool_protocol import parse_tool_calls, strip_tool_calls, to_plain_messages
from .tools import READ_ONLY_TOOLS, get_tool_specs


@dataclass
class TurnResult:
    """Outcome of one user turn."""

    # "end_turn", "refusal", "max_iterations", "interrupted", "denied", "error"
    reason: str
    iterations: int = 0
    tool_calls: int = 0
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.reason in ("end_turn", "denied")


_TEMPLATE_MARKERS = re.compile(
    r"<\|[a-z_]+\|>|</?reasoning>|<tool_call>|<function[=>]|<\|tool_call"
)
# A JSON object at the very end of the reply that carries a tool argument.
_TRAILING_ARGS = re.compile(
    r'\{\s*"(?:file_path|command|pattern|directory|path|old_string|content)"\s*:'
    r"[^{}]*\}\s*$"
)
_BROKEN_CALL_NUDGE = (
    "Your last message contained a tool call written as text, so it didn't run. "
    "If you meant to call a tool, call it now using the tool-calling interface "
    "(not text). If you were finished, give your final answer."
)


def looks_like_broken_tool_call(text: str) -> bool:
    """Whether a reply with no tool calls seems to contain a malformed one."""
    if not text:
        return False
    return bool(_TEMPLATE_MARKERS.search(text) or _TRAILING_ARGS.search(text.strip()))


class AgentLoop:
    """
    Runs one user turn to completion.

    The model is called repeatedly; whenever it requests tools, they are
    permission-checked, executed, and their results appended. The turn ends
    when the model replies without tool calls (like Claude Code), on refusal,
    on interrupt, or after ``max_iterations`` model calls.
    """

    def __init__(
        self,
        provider,
        tool_executor,
        permissions,
        renderer,
        context_manager=None,
        max_iterations: int = 50,
        tool_calling: str = "auto",
        max_tool_result_chars: int = 30000,
        max_parallel_workers: int = 4,
        enable_parallel_tools: bool = True,
        session_stats=None,
        system_prompt_builder: Optional[Callable[[bool], str]] = None,
    ):
        """
        Args:
            provider: ProviderAdapter
            tool_executor: ToolExecutor
            permissions: PermissionManager
            renderer: display.Renderer
            context_manager: Optional ContextManager (compaction + usage tracking)
            max_iterations: Model calls allowed per user turn
            tool_calling: "auto", "native", or "text"
            max_tool_result_chars: Cap on each tool result added to the conversation
            max_parallel_workers: Thread pool size for read-only tools
            enable_parallel_tools: Run independent read-only tools concurrently
            session_stats: Optional ui.SessionStats to update
            system_prompt_builder: ``builder(text_protocol) -> str``; used to
                rewrite the system prompt if we fall back to text tool calling
        """
        self.provider = provider
        self.tool_executor = tool_executor
        self.permissions = permissions
        self.renderer = renderer
        self.context_manager = context_manager
        self.max_iterations = max_iterations
        self.truncator = ToolResultTruncator(max_tool_result_chars)
        self.max_parallel_workers = max_parallel_workers
        self.enable_parallel_tools = enable_parallel_tools
        self.session_stats = session_stats
        self.system_prompt_builder = system_prompt_builder
        self.tools = get_tool_specs()
        if tool_calling == "text" or (
            tool_calling == "auto" and not provider.supports_native_tools
        ):
            self.text_protocol = True
        else:
            self.text_protocol = False
        self.tool_calling = tool_calling

    # --- Public --------------------------------------------------------------

    def run(self, messages: List[Dict[str, Any]]) -> TurnResult:
        """Run the loop until the model ends its turn. Mutates ``messages`` in place."""
        result = TurnResult(reason="end_turn")
        nudged = False
        while result.iterations < self.max_iterations:
            result.iterations += 1
            self._maybe_compact(messages)

            try:
                response = self._call_model(messages)
            except KeyboardInterrupt:
                self.renderer.end_response()
                self.renderer.warning("Interrupted.")
                result.reason = "interrupted"
                return result
            except ProviderError as e:
                self.renderer.end_response()
                self.renderer.error(f"Model request failed: {e}")
                result.reason, result.error = "error", str(e)
                return result

            text, calls, done = response
            assistant: Dict[str, Any] = {"role": "assistant", "content": text}
            if calls:
                assistant["tool_calls"] = [c.to_dict() for c in calls]
            if done.raw:
                assistant["raw"] = done.raw
            messages.append(assistant)
            if self.context_manager:
                self.context_manager.record_usage(done.usage, messages)
            if self.session_stats and done.usage:
                self.session_stats.record_usage(done.usage)

            if done.stop_reason == "refusal":
                detail = f" ({done.detail})" if done.detail else ""
                self.renderer.warning(f"The model declined this request{detail}.")
                result.reason = "refusal"
                if calls:
                    self._append_results(
                        messages, calls, {}, "Not run: the response was refused."
                    )
                return result

            if not calls:
                if not nudged and looks_like_broken_tool_call(text):
                    # Open-weight models sometimes emit a tool call as plain text
                    # (often with chat-template tokens); ask once for a real call.
                    nudged = True
                    self.renderer.notice(
                        "The model wrote a tool call as text; asking it to retry."
                    )
                    messages.append({"role": "user", "content": _BROKEN_CALL_NUDGE})
                    continue
                if done.stop_reason == "max_tokens":
                    self.renderer.warning(
                        "Response hit the output token limit and was cut off "
                        "(raise max_output_tokens to allow longer replies)."
                    )
                return result

            if done.stop_reason == "max_tokens":
                # Tool arguments may be cut off mid-way; don't run them.
                self.renderer.warning(
                    "Output limit reached mid tool call; asking the model to retry."
                )
                self._append_results(
                    messages,
                    calls,
                    {},
                    "Not run: your response hit the output token limit before this tool "
                    "call was complete. Retry with smaller pieces (e.g. split large files "
                    "into several edits).",
                )
                continue

            outcome = self._run_tools(messages, calls)
            result.tool_calls += len(calls)
            if outcome is not None:
                result.reason = outcome
                return result

        self.renderer.warning(
            f"Stopped after {self.max_iterations} model calls this turn "
            "(max_iterations). Say 'continue' to keep going."
        )
        result.reason = "max_iterations"
        return result

    # --- Model call ----------------------------------------------------------

    def _call_model(self, messages):
        """Stream one response; returns (text, tool_calls, MessageDone)."""
        options: Dict[str, Any] = {}
        if self.context_manager and self.context_manager.max_output_tokens:
            options["max_tokens"] = self.context_manager.max_output_tokens

        while True:
            text_parts: List[str] = []
            calls: List[ToolCall] = []
            done = MessageDone()
            got_events = False
            self.renderer.begin_response(hide_tool_blocks=self.text_protocol)
            try:
                if self.text_protocol:
                    # Servers without tool support often reject tool-role messages too.
                    request, tools = to_plain_messages(messages), None
                else:
                    request, tools = messages, self.tools
                for event in self.provider.stream_chat(
                    request, tools=tools, options=options
                ):
                    got_events = True
                    if isinstance(event, TextDelta):
                        text_parts.append(event.text)
                        self.renderer.text(event.text)
                    elif isinstance(event, ThinkingDelta):
                        self.renderer.thinking(event.text)
                    elif isinstance(event, ToolCallEvent):
                        calls.append(event.call)
                    elif isinstance(event, MessageDone):
                        done = event
            except ToolsNotSupportedError as e:
                if got_events or self.tool_calling == "native":
                    raise ProviderError(str(e)) from e
                self._switch_to_text_protocol(messages, str(e))
                continue
            except KeyboardInterrupt:
                if text_parts:
                    messages.append(
                        {"role": "assistant", "content": "".join(text_parts)}
                    )
                raise
            finally:
                self.renderer.end_response()

            text = "".join(text_parts)
            if self.text_protocol:
                calls = parse_tool_calls(text)
                text = strip_tool_calls(text) if calls else text
            return text, calls, done

    def _switch_to_text_protocol(self, messages, reason: str):
        self.renderer.warning(
            "This model/server doesn't accept native tool definitions; switching to "
            "text-based tool calling for this session. "
            "(Set tool_calling to 'text' to skip this check.)"
        )
        self.renderer.notice(f"  server said: {reason[:200]}")
        self.text_protocol = True
        if self.system_prompt_builder and messages and messages[0]["role"] == "system":
            messages[0] = {
                "role": "system",
                "content": self.system_prompt_builder(True),
            }

    def _maybe_compact(self, messages):
        cm = self.context_manager
        if not cm or not cm.needs_compaction(messages):
            return
        self.renderer.notice(
            f"Context {cm.usage_ratio(messages):.0%} full; summarizing earlier conversation"
            f"{glyph('ellipsis')}"
        )
        new_messages, info = cm.compact(messages)
        messages[:] = new_messages
        self.renderer.notice(
            f"Compacted ({info['action']}): ~{info['tokens_before']:,} {glyph('arrow')} "
            f"~{info['tokens_after']:,} tokens"
        )

    # --- Tools ---------------------------------------------------------------

    def _run_tools(self, messages, calls: List[ToolCall]) -> Optional[str]:
        """Execute tool calls and append results. Returns a stop reason or None."""
        results: Dict[str, Dict[str, Any]] = {}
        approved: List[ToolCall] = []
        stop_reason = None

        try:
            for call in calls:
                self.renderer.tool_call(call.name, call.arguments)
                if call.parse_error:
                    results[call.id] = {
                        "success": False,
                        "error": f"Could not parse tool call ({call.parse_error}). "
                        "Send valid JSON arguments.",
                    }
                    self.renderer.tool_result(call.name, results[call.id])
                    continue
                decision = self.permissions.check(call.name, call.arguments)
                if not decision.allowed:
                    message = decision.message or "The user denied this tool call."
                    results[call.id] = {"success": False, "error": message}
                    self.renderer.tool_result(call.name, results[call.id])
                    if decision.stop:
                        stop_reason = "denied"
                    continue
                approved.append(call)

            if stop_reason == "denied":
                # Like Claude Code: a plain "no" hands control back to the user.
                for call in approved:
                    results[call.id] = {
                        "success": False,
                        "error": "Not run: the user stopped.",
                    }
            else:
                self._execute(approved, results)
        except KeyboardInterrupt:
            self.renderer.warning("Interrupted.")
            self._append_results(messages, calls, results, "Interrupted by the user.")
            return "interrupted"

        self._append_results(messages, calls, results, "Not run.")
        return stop_reason

    def _execute(self, calls: List[ToolCall], results: Dict[str, Dict[str, Any]]):
        """Run approved calls: consecutive read-only calls in parallel, others in order."""
        i = 0
        while i < len(calls):
            batch = [calls[i]]
            if self.enable_parallel_tools and calls[i].name in READ_ONLY_TOOLS:
                while (
                    i + len(batch) < len(calls)
                    and calls[i + len(batch)].name in READ_ONLY_TOOLS
                ):
                    batch.append(calls[i + len(batch)])
            if len(batch) > 1:
                with concurrent.futures.ThreadPoolExecutor(
                    self.max_parallel_workers
                ) as pool:
                    futures = {
                        pool.submit(
                            self.tool_executor.execute, c.name, dict(c.arguments)
                        ): c
                        for c in batch
                    }
                    for future in concurrent.futures.as_completed(futures):
                        results[futures[future].id] = future.result()
                for call in batch:
                    self.renderer.tool_result(call.name, results[call.id])
            else:
                call = batch[0]
                results[call.id] = self.tool_executor.execute(
                    call.name, dict(call.arguments)
                )
                self.renderer.tool_result(call.name, results[call.id])
            for call in batch:
                if self.session_stats:
                    self.session_stats.record_tool(
                        call.name, call.arguments, results[call.id]
                    )
            i += len(batch)

    def _append_results(self, messages, calls, results, missing_text: str):
        """Append one tool message per call (every call must get a result)."""
        for call in calls:
            outcome = results.get(call.id, {"success": False, "error": missing_text})
            if outcome.get("success"):
                content, is_error = str(outcome.get("result", "")), False
            else:
                content, is_error = str(outcome.get("error", "failed")), True
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": call.name,
                    "content": self.truncator.truncate_result(content, call.name),
                    "is_error": is_error,
                }
            )
