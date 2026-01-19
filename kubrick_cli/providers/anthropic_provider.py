"""Anthropic provider adapter."""

import http.client
import json
import ssl
from typing import Dict, Iterator, List

from .base import ProviderAdapter, ProviderMetadata


class AnthropicProvider(ProviderAdapter):
    """Provider adapter for Anthropic API."""

    METADATA = ProviderMetadata(
        name="anthropic",
        display_name="Anthropic",
        description="Anthropic API (Claude 3.5 Sonnet, etc.)",
        config_fields=[
            {
                "key": "anthropic_api_key",
                "label": "Anthropic API key",
                "type": "password",
                "help_text": "Get your API key from: https://console.anthropic.com/settings/keys",
            },
            {
                "key": "anthropic_model",
                "label": "Model name",
                "type": "text",
                "default": "claude-3-5-sonnet-20241022",
            },
        ],
    )

    def __init__(self, anthropic_api_key: str, anthropic_model: str = "claude-3-5-sonnet-20241022"):
        """
        Initialize Anthropic provider.

        Args:
            anthropic_api_key: Anthropic API key
            anthropic_model: Model name (default: claude-3-5-sonnet-20241022)
        """
        self.api_key = anthropic_api_key
        self._model_name = anthropic_model
        self.base_url = "api.anthropic.com"
        self.timeout = 600
        self.api_version = "2023-06-01"

    def generate_streaming(
        self, messages: List[Dict[str, str]], stream_options: Dict = None
    ) -> Iterator[str]:
        """
        Generate streaming response from Anthropic.

        Args:
            messages: List of message dicts with 'role' and 'content'
            stream_options: Optional streaming parameters

        Yields:
            Text chunks as they arrive
        """
        # Anthropic requires system message to be separate
        system_message = ""
        conversation_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                conversation_messages.append(msg)

        # Build request payload
        payload = {
            "model": self._model_name,
            "messages": conversation_messages,
            "max_tokens": 4096,
            "stream": True,
        }

        if system_message:
            payload["system"] = system_message

        # Add optional parameters
        if stream_options:
            if "temperature" in stream_options:
                payload["temperature"] = stream_options["temperature"]
            if "max_tokens" in stream_options:
                payload["max_tokens"] = stream_options["max_tokens"]

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": self.api_version,
        }

        body = json.dumps(payload).encode("utf-8")

        # Create HTTPS connection
        context = ssl.create_default_context()
        conn = http.client.HTTPSConnection(
            self.base_url, 443, timeout=self.timeout, context=context
        )

        try:
            conn.request("POST", "/v1/messages", body=body, headers=headers)
            response = conn.getresponse()

            if response.status != 200:
                error_body = response.read().decode("utf-8")
                raise Exception(f"Anthropic API error {response.status}: {error_body}")

            # Read streaming response
            buffer = ""
            while True:
                chunk = response.read(1024)
                if not chunk:
                    break

                if isinstance(chunk, bytes):
                    chunk = chunk.decode("utf-8")

                buffer += chunk

                # Process complete lines
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()

                    if not line:
                        continue

                    # Anthropic SSE format
                    if line.startswith("data: "):
                        line = line[6:]

                    if line.startswith("event: "):
                        # Skip event lines
                        continue

                    try:
                        data = json.loads(line)

                        # Handle different event types
                        event_type = data.get("type")

                        if event_type == "content_block_delta":
                            # Extract text delta
                            delta = data.get("delta", {})
                            if delta.get("type") == "text_delta":
                                text = delta.get("text", "")
                                if text:
                                    yield text

                        elif event_type == "message_stop":
                            # End of stream
                            return

                    except json.JSONDecodeError:
                        # Skip malformed JSON
                        continue

        finally:
            conn.close()

    def generate(
        self, messages: List[Dict[str, str]], stream_options: Dict = None
    ) -> str:
        """
        Generate non-streaming response from Anthropic.

        Args:
            messages: List of message dicts with 'role' and 'content'
            stream_options: Optional parameters

        Returns:
            Complete response text
        """
        chunks = []
        for chunk in self.generate_streaming(messages, stream_options):
            chunks.append(chunk)
        return "".join(chunks)

    def is_healthy(self) -> bool:
        """
        Check if Anthropic API is accessible.

        Returns:
            True if healthy, False otherwise
        """
        try:
            # Simple health check - just verify we can connect
            context = ssl.create_default_context()
            conn = http.client.HTTPSConnection(
                self.base_url, 443, timeout=10, context=context
            )
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": self.api_version,
            }
            # Try to make a minimal request
            conn.request("GET", "/v1/models", headers=headers)
            response = conn.getresponse()
            conn.close()
            # Anthropic might not have a /v1/models endpoint, so we check for 404 as well
            return response.status in (200, 404)
        except Exception:
            return False

    @property
    def provider_name(self) -> str:
        """Get provider name."""
        return "anthropic"

    @property
    def model_name(self) -> str:
        """Get model name."""
        return self._model_name

    def set_model(self, model_name: str):
        """Set model name dynamically."""
        self._model_name = model_name
