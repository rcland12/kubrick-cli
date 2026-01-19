"""Triton provider adapter."""

from typing import Dict, Iterator, List

from ..triton_client import TritonLLMClient
from .base import ProviderAdapter, ProviderMetadata


class TritonProvider(ProviderAdapter):
    """Provider adapter for Triton Inference Server."""

    METADATA = ProviderMetadata(
        name="triton",
        display_name="Triton",
        description="Self-hosted Triton Inference Server (default)",
        config_fields=[
            {
                "key": "triton_url",
                "label": "Triton server URL",
                "type": "url",
                "default": "localhost:8000",
            },
            {
                "key": "triton_model",
                "label": "Triton model name",
                "type": "text",
                "default": "llm_decoupled",
            },
        ],
    )

    def __init__(self, triton_url: str = "localhost:8000", triton_model: str = "llm_decoupled"):
        """
        Initialize Triton provider.

        Args:
            triton_url: Triton server URL (default: localhost:8000)
            triton_model: Triton model name (default: llm_decoupled)
        """
        self.client = TritonLLMClient(url=triton_url, model_name=triton_model)
        self._url = triton_url
        self._model_name = triton_model

    def generate_streaming(
        self, messages: List[Dict[str, str]], stream_options: Dict = None
    ) -> Iterator[str]:
        """
        Generate streaming response from Triton.

        Args:
            messages: List of message dicts with 'role' and 'content'
            stream_options: Optional streaming parameters

        Yields:
            Text chunks as they arrive
        """
        yield from self.client.generate_streaming(messages, stream_options)

    def generate(
        self, messages: List[Dict[str, str]], stream_options: Dict = None
    ) -> str:
        """
        Generate non-streaming response from Triton.

        Args:
            messages: List of message dicts with 'role' and 'content'
            stream_options: Optional parameters

        Returns:
            Complete response text
        """
        return self.client.generate(messages, stream_options)

    def is_healthy(self) -> bool:
        """
        Check if Triton server is healthy.

        Returns:
            True if healthy, False otherwise
        """
        return self.client.is_healthy()

    @property
    def provider_name(self) -> str:
        """Get provider name."""
        return "triton"

    @property
    def model_name(self) -> str:
        """Get model name."""
        return self._model_name

    @property
    def url(self) -> str:
        """Get Triton server URL."""
        return self._url
