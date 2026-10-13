"""Context window tracking and compaction."""

from typing import Any, Dict, List, Optional, Tuple

from .messages import Usage, message_text_for_counting
from .tool_protocol import to_plain_messages

# Fallback context windows when neither config nor the backend says.
DEFAULT_WINDOWS = {
    "anthropic": 200000,
    "openai": 128000,
    "bedrock": 200000,
    "openai_compatible": 32768,
    "triton": 32768,
}
# Known model families (prefix match on the model id, longest first).
MODEL_WINDOWS = {
    "claude-haiku-4-5": 200000,
    "claude-sonnet-4-5": 200000,
    "claude-opus-4-5": 200000,
    "claude-opus-4-1": 200000,
    "claude-3": 200000,
    "claude-": 1000000,  # Claude 4.6+ / 5.x
    "gpt-5": 400000,
    "gpt-4.1": 1000000,
    "gpt-4o": 128000,
    "gpt-4": 128000,
}

SUMMARY_PREFIX = "[Summary of the earlier conversation, written to save context]"

SUMMARY_INSTRUCTIONS = """Summarize the conversation above so the work can continue \
from the summary alone. Include:
- The user's goals and explicit requests, verbatim where wording matters
- Key decisions, constraints, and user preferences
- Files read or changed, with the important details of each change
- Commands run and their outcomes (tests passing/failing, errors)
- Current state: what is done, what is in progress, what remains
Be specific and complete; omit pleasantries."""


class TokenCounter:
    """Heuristic token estimates (~3.5 characters per token for code and prose)."""

    CHARS_PER_TOKEN = 3.5

    @classmethod
    def estimate_tokens(cls, text: str) -> int:
        return int(len(text or "") / cls.CHARS_PER_TOKEN)

    @classmethod
    def count_message_tokens(cls, message: Dict[str, Any]) -> int:
        return 4 + cls.estimate_tokens(message_text_for_counting(message))

    @classmethod
    def count_messages_tokens(cls, messages: List[Dict[str, Any]]) -> int:
        return sum(cls.count_message_tokens(m) for m in messages)


class ToolResultTruncator:
    """Caps tool output size before it enters the conversation."""

    def __init__(self, max_chars: int = 30000):
        self.max_chars = max_chars

    def truncate_result(self, result: str, tool_name: str) -> str:
        """Keep the head and tail of oversized output."""
        result = str(result)
        if len(result) <= self.max_chars:
            return result
        keep_start = int(self.max_chars * 0.7)
        keep_end = self.max_chars - keep_start
        dropped = len(result) - self.max_chars
        return (
            result[:keep_start]
            + f"\n\n... [truncated {dropped} characters of {tool_name} output] ...\n\n"
            + result[-keep_end:]
        )


class ContextManager:
    """
    Tracks how full the context window is and compacts the conversation.

    Token counts come from provider-reported usage when available (exact), plus
    a heuristic estimate for messages added since the last response.
    """

    def __init__(self, provider, config: Dict[str, Any]):
        """
        Args:
            provider: ProviderAdapter (for window discovery and summarization)
            config: Effective configuration values
        """
        self.provider = provider
        self.config = config
        self.usage_threshold = float(config.get("context_usage_threshold") or 0.8)
        self.context_window = self._resolve_window()
        configured_output = config.get("max_output_tokens")
        self.max_output_tokens = int(configured_output) if configured_output else None
        # Budget reserved for the response when deciding whether to compact.
        self.reserved_output = min(
            self.max_output_tokens or 8192, self.context_window // 4
        )
        self._reported_tokens: Optional[int] = None
        self._reported_message_count = 0
        self.last_usage: Optional[Usage] = None

    def _resolve_window(self) -> int:
        configured = self.config.get("context_window")
        if configured:
            return int(configured)
        try:
            reported = self.provider.context_window()
        except Exception:
            reported = None
        if reported:
            return int(reported)
        model = (self.provider.model_name or "").lower()
        for prefix in sorted(MODEL_WINDOWS, key=len, reverse=True):
            if prefix in model:
                return MODEL_WINDOWS[prefix]
        return DEFAULT_WINDOWS.get(self.provider.provider_name, 32768)

    # --- Accounting ----------------------------------------------------------

    def record_usage(self, usage: Optional[Usage], messages: List[Dict[str, Any]]):
        """Record provider-reported usage for the response just appended to ``messages``."""
        if usage is None or usage.context_tokens == 0:
            return
        self.last_usage = usage
        self._reported_tokens = usage.context_tokens + usage.output_tokens
        self._reported_message_count = len(messages)

    def current_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """Best estimate of the tokens the conversation occupies."""
        if self._reported_tokens is not None and self._reported_message_count <= len(
            messages
        ):
            added = messages[self._reported_message_count :]
            return self._reported_tokens + TokenCounter.count_messages_tokens(added)
        return TokenCounter.count_messages_tokens(messages)

    def usage_ratio(self, messages: List[Dict[str, Any]]) -> float:
        """Fraction of the usable window (window minus reserved output) in use."""
        usable = max(self.context_window - self.reserved_output, 1)
        return self.current_tokens(messages) / usable

    def needs_compaction(self, messages: List[Dict[str, Any]]) -> bool:
        return self.usage_ratio(messages) >= self.usage_threshold

    # --- Compaction ----------------------------------------------------------

    def compact(
        self, messages: List[Dict[str, Any]], focus: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Replace older turns with a summary, keeping the system prompt and the
        most recent turn(s) intact.

        Cuts only at user-message boundaries so tool calls stay paired with
        their results. Provider-native replay data (``raw``) is dropped from the
        kept messages: Claude's thinking blocks are bound to the history that
        produced them, which compaction changes.

        Args:
            messages: The conversation
            focus: Optional user guidance for what the summary should emphasize

        Returns:
            (new_messages, info) where info has tokens_before/tokens_after/action
        """
        before = self.current_tokens(messages)
        system = [m for m in messages[:1] if m["role"] == "system"]
        body = messages[len(system) :]

        cut = self._choose_cut(body)
        if cut == 0:
            # One enormous turn: shrink old tool outputs inside it instead.
            new_body = self._shrink_tool_results(body)
            action = "shrunk_tool_results"
        else:
            summary = self._summarize(system + body[:cut], focus)
            summary_msg = {"role": "user", "content": f"{SUMMARY_PREFIX}\n\n{summary}"}
            new_body = [summary_msg] + body[cut:]
            action = "summarized"

        new_messages = system + [_without_raw(m) for m in new_body]
        self._reported_tokens = None
        after = TokenCounter.count_messages_tokens(new_messages)
        return new_messages, {
            "action": action,
            "tokens_before": before,
            "tokens_after": after,
        }

    def _choose_cut(self, body: List[Dict[str, Any]]) -> int:
        """Index in ``body`` where the kept tail starts (0 = nothing to summarize)."""
        user_starts = [i for i, m in enumerate(body) if m["role"] == "user"]
        if len(user_starts) <= 1:
            return 0
        tail_budget = int((self.context_window - self.reserved_output) * 0.3)
        # Keep as many recent turns as fit in the tail budget, but at least the last.
        cut = user_starts[-1]
        for start in reversed(user_starts[:-1]):
            if TokenCounter.count_messages_tokens(body[start:]) > tail_budget:
                break
            cut = start
        return 0 if cut == user_starts[0] else cut

    def _summarize(self, messages: List[Dict[str, Any]], focus: Optional[str]) -> str:
        transcript = to_plain_messages(messages)
        # Leave room for the summary itself; trim the oldest content if needed.
        budget_chars = int(
            (self.context_window - 12000) * TokenCounter.CHARS_PER_TOKEN * 0.8
        )
        while (
            sum(len(m["content"]) for m in transcript) > budget_chars
            and len(transcript) > 2
        ):
            transcript.pop(1)
        instructions = SUMMARY_INSTRUCTIONS
        if focus:
            instructions += f"\n\nThe user asked the summary to focus on: {focus}"
        request = transcript + [{"role": "user", "content": instructions}]
        if request[0]["role"] != "system":
            request.insert(
                0, {"role": "system", "content": "You summarize coding sessions."}
            )
        try:
            # No small max_tokens: reasoning models spend part of the budget thinking.
            summary = self.provider.generate(request, stream_options={}).strip()
        except Exception as e:
            summary = ""
            error = str(e)
        else:
            error = None
        if not summary:
            reason = f" (summarization failed: {error})" if error else ""
            summary = f"{len(messages) - 1} earlier messages were removed to free context{reason}."
        return summary

    @staticmethod
    def _shrink_tool_results(body: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        tool_indices = [i for i, m in enumerate(body) if m["role"] == "tool"]
        keep_recent = set(tool_indices[-4:])
        shrunk = []
        for i, msg in enumerate(body):
            if (
                msg["role"] == "tool"
                and i not in keep_recent
                and len(msg["content"]) > 500
            ):
                msg = dict(msg)
                msg["content"] = (
                    msg["content"][:300] + "\n[...older output removed to save context]"
                )
            shrunk.append(msg)
        return shrunk


def _without_raw(message: Dict[str, Any]) -> Dict[str, Any]:
    if "raw" not in message:
        return message
    message = dict(message)
    message.pop("raw")
    return message
