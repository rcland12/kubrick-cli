"""Base provider adapter interface."""

from abc import ABC, abstractmethod
from typing import Dict, Iterator, List, Optional


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
        config_fields: List[Dict[str, str]],
    ):
        """
        Initialize provider metadata.

        Args:
            name: Internal provider name (e.g., "triton", "openai")
            display_name: Human-readable name (e.g., "Triton", "OpenAI")
            description: Brief description shown in setup wizard
            config_fields: List of configuration field definitions
                Each field should be a dict with:
                - key: Config key name (e.g., "openai_api_key")
                - label: Display label (e.g., "OpenAI API key")
                - type: Field type ("text", "password", "url")
                - default: Default value (optional)
                - help_text: Help text or URL (optional)
        """
        self.name = name
        self.display_name = display_name
        self.description = description
        self.config_fields = config_fields


class ProviderAdapter(ABC):
    """
    Abstract base class for LLM provider adapters.

    All provider implementations must inherit from this class and implement
    the required methods for streaming and non-streaming generation.

    To create a truly plug-and-play provider:
    1. Inherit from ProviderAdapter
    2. Define METADATA as a class attribute with ProviderMetadata
    3. Implement all abstract methods
    4. Place the file in kubrick_cli/providers/ directory

    The provider will be automatically discovered and available in the setup wizard.
    """

    # Providers should override this with their metadata
    METADATA: Optional[ProviderMetadata] = None

    @abstractmethod
    def generate_streaming(
        self, messages: List[Dict[str, str]], stream_options: Dict = None
    ) -> Iterator[str]:
        """
        Generate streaming response from LLM.

        Args:
            messages: List of message dicts with 'role' and 'content'
            stream_options: Optional streaming parameters

        Yields:
            Text chunks as they arrive
        """
        pass

    @abstractmethod
    def generate(
        self, messages: List[Dict[str, str]], stream_options: Dict = None
    ) -> str:
        """
        Generate non-streaming response from LLM.

        Args:
            messages: List of message dicts with 'role' and 'content'
            stream_options: Optional parameters

        Returns:
            Complete response text
        """
        pass

    @abstractmethod
    def is_healthy(self) -> bool:
        """
        Check if the provider is healthy and accessible.

        Returns:
            True if healthy, False otherwise
        """
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """
        Get the name of this provider.

        Returns:
            Provider name (e.g., "triton", "openai", "anthropic")
        """
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """
        Get the model name being used.

        Returns:
            Model name/identifier
        """
        pass

    def set_model(self, model_name: str):
        """
        Set the model name dynamically (optional, for model switching).

        Args:
            model_name: New model name

        Note:
            Default implementation does nothing. Override in subclasses
            that support model switching.
        """
        pass
