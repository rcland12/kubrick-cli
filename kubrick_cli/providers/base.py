"""Base provider adapter interface."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Iterator, List, Optional

from ..messages import MessageDone, TextDelta, ToolSpec


class ProviderError(Exception):
    """A provider request failed in a way worth showing to the user verbatim."""


class ToolsNotSupportedError(ProviderError):
    """The backend rejected native tool definitions (e.g. an Ollama model without tools)."""


class ProviderMetadata:
    """
    Metadata for a provider that describes its configuration needs.

    This allows providers to be self-describing and enables automatic
    setup wizard generation and provider discovery.
    """

    def __init__(
        self,
        name: str,
        display_name: str,
        description: str,
        config_fields: List[Dict[str, Any]],
    ):
        """
        Initialize provider metadata.

        Args:
            name: Internal provider name (e.g., "triton", "openai")
            display_name: Human-readable name (e.g., "Triton", "OpenAI")
            description: Brief description shown in setup wizard
            config_fields: List of configuration field definitions
                Each field is a dict with:
                - key: Config key name (e.g., "openai_api_key")
                - label: Display label (e.g., "OpenAI API key")
                - type: Field type ("text", "secret", "url", or "model": the
                  wizard offers the provider's ``list_models()`` as a menu)
                - default: Default value (optional; a field with a default
                  or ``required: False`` is optional)
                - required: Whether a value must be provided (default True)
                - env: Environment variables checked for the value, in order
                - help_text: Help text or URL (optional)
                - choices: ``[(value, description), ...]`` shown as a menu
                - advanced: Not asked in the setup wizard (change with /config)

                ``secret`` fields are stored in the credential store, never in
                config.json.
        """
        self.name = name
        self.display_name = display_name
        self.description = description
        self.config_fields = config_fields

    @property
    def secret_fields(self) -> List[Dict[str, Any]]:
        """Config fields that hold credentials."""
        return [
            f for f in self.config_fields if f.get("type") in ("secret", "password")
        ]


class ProviderAdapter(ABC):
    """
    Abstract base class for LLM provider adapters.

    To create a plug-and-play provider:
    1. Inherit from ProviderAdapter
    2. Define METADATA as a class attribute with ProviderMetadata
    3. Implement ``stream_chat`` and the name properties
    4. Place the file in kubrick_cli/providers/

    The provider is discovered automatically and offered in the setup wizard.
    Constructor parameters are filled from config fields whose key equals the
    parameter name or ends with ``_<parameter name>``.
    """

    METADATA: Optional[ProviderMetadata] = None

    #: Whether ``stream_chat`` accepts ``tools`` and emits ToolCallEvents.
    #: Providers without native tool calling get the text tool protocol instead.
    supports_native_tools: bool = True

    @abstractmethod
    def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[ToolSpec]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Any]:
        """
        Stream one model response.

        Args:
            messages: Conversation in the format described in ``messages.py``
            tools: Tools the model may call (ignored if not supported)
            options: Generation options (``max_tokens``, ``temperature``)

        Yields:
            TextDelta, ThinkingDelta and ToolCallEvent objects, then exactly
            one MessageDone.

        Raises:
            ProviderError: On API errors, with a message fit for display
        """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider name (e.g., "triton", "openai", "anthropic")."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Model identifier in use."""

    def set_model(self, model_name: str):
        """Switch models for subsequent requests."""
        self._model_name = model_name

    def is_healthy(self) -> bool:
        """Cheap connectivity check run at startup."""
        return True

    def list_models(self) -> List[str]:
        """Model identifiers the backend offers (empty if unknown)."""
        return []

    def context_window(self) -> Optional[int]:
        """Context window of the current model as reported by the backend, if known."""
        return None

    # --- Text-only conveniences used by summarization ------------------------

    def generate_streaming(
        self, messages: List[Dict[str, Any]], stream_options: Dict = None
    ) -> Iterator[str]:
        """Stream only the response text, without tools."""
        for event in self.stream_chat(messages, tools=None, options=stream_options):
            if isinstance(event, TextDelta):
                yield event.text

    def generate(
        self, messages: List[Dict[str, Any]], stream_options: Dict = None
    ) -> str:
        """Return the complete response text, without tools."""
        return "".join(self.generate_streaming(messages, stream_options))

    @staticmethod
    def _done_if_missing(seen_done: bool) -> Iterator[MessageDone]:
        """Yield a fallback MessageDone when a stream ended without one."""
        if not seen_done:
            yield MessageDone(stop_reason="end_turn")
