"""Context management for keeping conversations within model limits."""

from typing import Any, Dict, List, Tuple

from rich.console import Console

console = Console()


class TokenCounter:
    """
    Lightweight token counter using heuristic estimation.

    Uses character-based estimation with provider-specific multipliers.
    Good enough for context management without heavyweight dependencies.
    """

    PROVIDER_RATIOS = {
        "openai": 4.0,  # ~4 chars per token for GPT models
        "anthropic": 3.8,  # Claude tends to be slightly more efficient
        "triton": 4.0,  # Assume similar to GPT (configurable)
    }

    @staticmethod
    def estimate_tokens(text: str, provider: str = "openai") -> int:
        """
        Estimate token count for text based on provider.

        Args:
            text: Text to estimate tokens for
            provider: Provider name (openai, anthropic, triton)

        Returns:
            Estimated token count
        """
        if not text:
            return 0

        ratio = TokenCounter.PROVIDER_RATIOS.get(provider, 4.0)
        return int(len(text) / ratio)

    @staticmethod
    def count_message_tokens(message: Dict, provider: str) -> int:
        """
        Count tokens in a single message (role + content).

        Args:
            message: Message dict with 'role' and 'content'
            provider: Provider name

        Returns:
            Estimated token count for this message
        """
        role_tokens = 2
        content_tokens = TokenCounter.estimate_tokens(
            message.get("content", ""), provider
        )
        return role_tokens + content_tokens

    @staticmethod
    def count_messages_tokens(messages: List[Dict], provider: str) -> int:
        """
        Count total tokens across all messages.

        Args:
            messages: List of message dicts
            provider: Provider name

        Returns:
            Estimated total token count
        """
        return sum(TokenCounter.count_message_tokens(msg, provider) for msg in messages)


class ToolResultTruncator:
    """
    Truncates large tool results before adding to message history.

    Prevents scenarios where a single 'read_file' of a 10MB file
    consumes the entire context window.
    """

    def __init__(self, max_chars: int = 10000):
        """
        Initialize truncator.

        Args:
            max_chars: Maximum characters per tool result
        """
        self.max_chars = max_chars

    def truncate_result(self, result: str, tool_name: str) -> str:
        """
        Truncate a tool result if it exceeds max_chars.

        Strategy:
        - For short results: return as-is
        - For long results: Keep beginning and end, add ellipsis
        - Add metadata about truncation

        Args:
            result: Tool result string
            tool_name: Name of the tool (for context in truncation message)

        Returns:
            Truncated result (or original if under limit)
        """
        result_str = str(result)

        if len(result_str) <= self.max_chars:
            return result_str

        keep_start = int(self.max_chars * 0.7)
        keep_end = int(self.max_chars * 0.3)
        truncated_chars = len(result_str) - self.max_chars

        return (
            result_str[:keep_start]
            + f"\n\n... [truncated {truncated_chars} characters from {tool_name} output] ...\n\n"
            + result_str[-keep_end:]
        )


class MessageSummarizer:
    """
    Generates summaries of conversation history.

    Used when context is critically high and simple trimming won't suffice.
    Creates a condensed representation of middle conversation turns.
    """

    def __init__(self, llm_client, max_summary_tokens: int = 500):
        """
        Initialize summarizer.

        Args:
            llm_client: LLM provider for generating summaries
            max_summary_tokens: Target size for summary
        """
        self.llm_client = llm_client
        self.max_summary_tokens = max_summary_tokens

    def summarize_messages(self, messages: List[Dict]) -> str:
        """
        Summarize a sequence of messages into a condensed form.

        Args:
            messages: List of messages to summarize

        Returns:
            Summary text suitable for injection as a user message
        """
        summary_prompt = self._build_summarization_prompt(messages)

        try:
            summary = self.llm_client.generate(
                summary_prompt,
                stream_options={"max_tokens": self.max_summary_tokens},
            )
            return f"[Context Summary]\n{summary}"
        except Exception as e:
            console.print(f"[red]Summarization failed: {e}[/red]")
            return (
                f"[Context Summary] {len(messages)} messages removed "
                "due to context limits."
            )

    def _build_summarization_prompt(self, messages: List[Dict]) -> List[Dict]:
        """
        Build prompt asking LLM to summarize conversation history.

        Args:
            messages: Messages to summarize

        Returns:
            Prompt messages for summarization
        """
        conversation_text = "\n\n".join(
            [f"{msg['role']}: {msg['content']}" for msg in messages]
        )

        return [
            {
                "role": "system",
                "content": "You are a conversation summarizer. Create concise summaries.",
            },
            {
                "role": "user",
                "content": (
                    f"Summarize this conversation segment in under 500 tokens, "
                    f"focusing on key decisions, code changes, and important context:\n\n"
                    f"{conversation_text}"
                ),
            },
        ]


class ContextManager:
    """
    Manages conversation context to stay within model limits.

    Responsibilities:
    - Track token usage in real-time
    - Enforce context window limits
    - Trigger interventions (trim/summarize) when needed
    - Preserve system messages and recent context
    """

    def __init__(
        self,
        provider_name: str,
        model_name: str,
        config: Dict[str, Any],
        llm_client=None,
    ):
        """
        Initialize context manager with provider-specific settings.

        Args:
            provider_name: Provider (openai, anthropic, triton)
            model_name: Model name for window size lookup
            config: Configuration dict with context management settings
            llm_client: Optional LLM client for summarization
        """
        self.provider_name = provider_name
        self.model_name = model_name
        self.config = config
        self.token_counter = TokenCounter()
        self.llm_client = llm_client

        self.context_window = self._get_context_window()
        self.max_output_tokens = config.get("max_output_tokens", 2048)

        self.usage_threshold = config.get("context_usage_threshold", 0.75)
        self.summarization_threshold = config.get(
            "context_summarization_threshold", 0.85
        )
        self.min_messages_to_keep = config.get("min_messages_to_keep", 4)

        # Initialize summarizer if LLM client is available
        if llm_client:
            self.summarizer = MessageSummarizer(llm_client, max_summary_tokens=500)
        else:
            self.summarizer = None

    def _get_context_window(self) -> int:
        """
        Get context window size for current model.

        Uses model_max_context_override if set, otherwise uses model-specific defaults.

        Returns:
            Context window size in tokens
        """
        # Check for manual override first (for custom vLLM configurations)
        override = self.config.get("model_max_context_override")
        if override is not None:
            return int(override)

        # Otherwise use model-specific defaults
        context_windows = self.config.get("context_windows", {})
        return context_windows.get(
            self.model_name, self.config.get("default_context_window", 8192)
        )

    def check_and_manage(
        self, messages: List[Dict], reserve_output_tokens: bool = True
    ) -> Tuple[List[Dict], Dict]:
        """
        Check current token usage and manage context if needed.

        Args:
            messages: Current conversation messages
            reserve_output_tokens: Whether to reserve tokens for LLM output (default: True)

        Returns:
            Tuple of (managed_messages, metadata)
        """
        current_tokens = self.token_counter.count_messages_tokens(
            messages, self.provider_name
        )

        # Calculate available context (reserving space for output)
        available_context = self.context_window
        if reserve_output_tokens:
            available_context -= self.max_output_tokens

        metadata = {
            "tokens_before": current_tokens,
            "tokens_after": current_tokens,
            "action_taken": None,
            "reserved_output_tokens": (
                self.max_output_tokens if reserve_output_tokens else 0
            ),
        }

        usage_ratio = current_tokens / available_context

        if usage_ratio >= self.summarization_threshold:
            messages = self._summarize_and_trim(messages)
            metadata["action_taken"] = "summarized"
        elif usage_ratio >= self.usage_threshold:
            # Target 60% of available context to leave room for growth
            target_tokens = int(available_context * 0.6)
            messages = self._trim_messages(messages, target_tokens)
            metadata["action_taken"] = "trimmed"

        current_tokens = self.token_counter.count_messages_tokens(
            messages, self.provider_name
        )

        if current_tokens > available_context:
            console.print("[red]⚠ Context critically full. Emergency reset.[/red]")
            messages = self._emergency_reset(messages)
            metadata["action_taken"] = "emergency_reset"

        metadata["tokens_after"] = self.token_counter.count_messages_tokens(
            messages, self.provider_name
        )

        return messages, metadata

    def _trim_messages(self, messages: List[Dict], target_tokens: int) -> List[Dict]:
        """
        Trim oldest messages while preserving system and recent context.

        Strategy:
        1. Always preserve system message (index 0)
        2. Always preserve last N messages (min_messages_to_keep)
        3. Drop oldest user/assistant pairs from middle

        Args:
            messages: Messages to trim
            target_tokens: Target token count

        Returns:
            Trimmed messages list
        """
        if len(messages) <= self.min_messages_to_keep + 1:
            return messages

        system_msg = messages[0]
        recent_msgs = messages[-(self.min_messages_to_keep) :]
        middle_msgs = messages[1 : -(self.min_messages_to_keep)]

        trimmed_middle = []
        accumulated_tokens = self.token_counter.count_message_tokens(
            system_msg, self.provider_name
        ) + sum(
            self.token_counter.count_message_tokens(m, self.provider_name)
            for m in recent_msgs
        )

        for msg in reversed(middle_msgs):
            msg_tokens = self.token_counter.count_message_tokens(
                msg, self.provider_name
            )
            if accumulated_tokens + msg_tokens <= target_tokens:
                trimmed_middle.insert(0, msg)
                accumulated_tokens += msg_tokens
            else:
                break

        result = [system_msg] + trimmed_middle + recent_msgs

        if len(trimmed_middle) < len(middle_msgs):
            dropped = len(middle_msgs) - len(trimmed_middle)
            result.insert(
                1,
                {
                    "role": "user",
                    "content": (
                        f"[Context Note] {dropped} older messages trimmed "
                        "to manage context."
                    ),
                },
            )

        return result

    def _summarize_and_trim(self, messages: List[Dict]) -> List[Dict]:
        """
        Summarize middle messages and keep system + recent.

        Args:
            messages: Messages to summarize

        Returns:
            Summarized messages list
        """
        if len(messages) <= self.min_messages_to_keep + 1:
            return messages

        system_msg = messages[0]
        recent_msgs = messages[-(self.min_messages_to_keep) :]
        middle_msgs = messages[1 : -(self.min_messages_to_keep)]

        if not middle_msgs:
            return messages

        # Try to use LLM-based summarization if available
        if self.summarizer:
            try:
                console.print("[yellow]→ Summarizing conversation history...[/yellow]")
                summary_text = self.summarizer.summarize_messages(middle_msgs)
                summary_note = {
                    "role": "user",
                    "content": summary_text,
                }
            except Exception as e:
                console.print(f"[red]Summarization failed: {e}[/red]")
                # Fallback to simple note
                summary_note = {
                    "role": "user",
                    "content": (
                        f"[Context Summary] {len(middle_msgs)} messages were compressed "
                        "to manage context window limits."
                    ),
                }
        else:
            # Fallback to simple note if no summarizer available
            summary_note = {
                "role": "user",
                "content": (
                    f"[Context Summary] {len(middle_msgs)} messages were compressed "
                    "to manage context window limits."
                ),
            }

        return [system_msg, summary_note] + recent_msgs

    def _emergency_reset(self, messages: List[Dict]) -> List[Dict]:
        """
        Emergency: Keep only system + last user message.

        Args:
            messages: Messages to reset

        Returns:
            Minimal messages list
        """
        system_msg = messages[0] if messages else {"role": "system", "content": ""}
        last_msg = (
            messages[-1] if len(messages) > 1 else {"role": "user", "content": "..."}
        )

        return [
            system_msg,
            {
                "role": "user",
                "content": (
                    "[CONTEXT_RESET] Previous conversation exceeded context limits. "
                    f"Starting fresh. Last message: {last_msg.get('content', '...')}"
                ),
            },
        ]
