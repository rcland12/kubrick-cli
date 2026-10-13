"""Triton provider adapter."""

from typing import Any, Dict, Iterator, List, Optional

from ..messages import MessageDone, TextDelta, ToolSpec
from ..tool_protocol import to_plain_messages
from ..triton_client import TritonLLMClient
from .base import ProviderAdapter, ProviderError, ProviderMetadata

# Generation options forwarded to the Triton model as request parameters.
_PASSTHROUGH_OPTIONS = ("max_tokens", "temperature")


class TritonProvider(ProviderAdapter):
    """Provider adapter for Triton Inference Server.

    Triton models speak Kubrick's custom text streaming protocol (see
    docs/TRITON.md), so tool calling uses the text ``tool_call`` protocol.
    """

    METADATA = ProviderMetadata(
        name="triton",
        display_name="NVIDIA Triton",
        description="Self-hosted Triton Inference Server (text-based tool calling)",
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

    supports_native_tools = False

    def __init__(
        self, triton_url: str = "localhost:8000", triton_model: str = "llm_decoupled"
    ):
        """
        Initialize Triton provider.

        Args:
            triton_url: Triton server URL (default: localhost:8000)
            triton_model: Triton model name (default: llm_decoupled)
        """
        self.client = TritonLLMClient(url=triton_url, model_name=triton_model)
        self._url = triton_url
        self._model_name = triton_model

    def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[ToolSpec]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Any]:
        """Stream a text response; ``tools`` is ignored (text protocol only)."""
        params = {k: v for k, v in (options or {}).items() if k in _PASSTHROUGH_OPTIONS}
        try:
            for chunk in self.client.generate_streaming(
                to_plain_messages(messages), params
            ):
                if chunk:
                    yield TextDelta(chunk)
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"Triton ({self.client.url}): {e}") from e
        yield MessageDone(stop_reason="end_turn")

    def is_healthy(self) -> bool:
        """Check if Triton server is healthy."""
        return self.client.is_healthy()

    def set_model(self, model_name: str):
        """Switch the Triton model used for subsequent requests."""
        self._model_name = model_name
        self.client.model_name = model_name

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
