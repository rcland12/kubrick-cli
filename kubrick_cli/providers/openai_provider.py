"""OpenAI provider adapter."""

import http.client
import json
import ssl
from typing import Dict, Iterator, List

from .base import ProviderAdapter, ProviderMetadata


class OpenAIProvider(ProviderAdapter):
    """Provider adapter for OpenAI API."""

    METADATA = ProviderMetadata(
        name="openai",
        display_name="OpenAI",
        description="OpenAI API (GPT-4, GPT-3.5, etc.)",
        config_fields=[
            {
                "key": "openai_api_key",
                "label": "OpenAI API key",
                "type": "password",
                "help_text": "Get your API key from: https://platform.openai.com/api-keys",
            },
            {
                "key": "openai_model",
                "label": "Model name",
                "type": "text",
                "default": "gpt-4",
            },
        ],
    )

    def __init__(self, openai_api_key: str, openai_model: str = "gpt-4"):
        """
        Initialize OpenAI provider.

        Args:
            openai_api_key: OpenAI API key
            openai_model: Model name (default: gpt-4)
        """
        self.api_key = openai_api_key
        self._model_name = openai_model
        self.base_url = "api.openai.com"
        self.timeout = 600

    def generate_streaming(
        self, messages: List[Dict[str, str]], stream_options: Dict = None
    ) -> Iterator[str]:
        """
        Generate streaming response from OpenAI.

        Args:
            messages: List of message dicts with 'role' and 'content'
            stream_options: Optional streaming parameters

        Yields:
            Text chunks as they arrive
        """
        payload = {
            "model": self._model_name,
            "messages": messages,
            "stream": True,
        }

        if stream_options:
            if "temperature" in stream_options:
                payload["temperature"] = stream_options["temperature"]
            if "max_tokens" in stream_options:
                payload["max_tokens"] = stream_options["max_tokens"]

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        body = json.dumps(payload).encode("utf-8")

        context = ssl.create_default_context()
        conn = http.client.HTTPSConnection(
            self.base_url, 443, timeout=self.timeout, context=context
        )

        try:
            conn.request("POST", "/v1/chat/completions", body=body, headers=headers)
            response = conn.getresponse()

            if response.status != 200:
                error_body = response.read().decode("utf-8")
                raise Exception(f"OpenAI API error {response.status}: {error_body}")

            buffer = ""
            while True:
                chunk = response.read(1024)
                if not chunk:
                    break

                if isinstance(chunk, bytes):
                    chunk = chunk.decode("utf-8")

                buffer += chunk

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()

                    if not line:
                        continue

                    if line.startswith("data: "):
                        line = line[6:]

                    if line == "[DONE]":
                        return

                    try:
                        data = json.loads(line)
                        if "choices" in data and len(data["choices"]) > 0:
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                    except json.JSONDecodeError:
                        continue

        finally:
            conn.close()

    def generate(
        self, messages: List[Dict[str, str]], stream_options: Dict = None
    ) -> str:
        """
        Generate non-streaming response from OpenAI.

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
        Check if OpenAI API is accessible.

        Returns:
            True if healthy, False otherwise
        """
        try:
            context = ssl.create_default_context()
            conn = http.client.HTTPSConnection(
                self.base_url, 443, timeout=10, context=context
            )
            headers = {
                "Authorization": f"Bearer {self.api_key}",
            }
            conn.request("GET", "/v1/models", headers=headers)
            response = conn.getresponse()
            conn.close()
            return response.status == 200
        except Exception:
            return False

    @property
    def provider_name(self) -> str:
        """Get provider name."""
        return "openai"

    @property
    def model_name(self) -> str:
        """Get model name."""
        return self._model_name

    def set_model(self, model_name: str):
        """Set model name dynamically."""
        self._model_name = model_name
