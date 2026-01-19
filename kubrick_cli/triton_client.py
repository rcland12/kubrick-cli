"""Triton client for streaming LLM requests using HTTP only (no dependencies)."""

import http.client
import json
import ssl
from typing import Dict, Iterator, List
from urllib.parse import urlparse


class TritonLLMClient:
    """Client for interacting with Triton LLM backend using HTTP (no extra dependencies)."""

    def __init__(
        self,
        url: str = "localhost:8000",
        model_name: str = "llm_decoupled",
    ):
        """
        Initialize Triton LLM client.

        Args:
            url: Triton server URL (host:port, default: localhost:8000)
            model_name: Name of the Triton model to use
        """
        self.model_name = model_name

        # Parse URL
        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"http://{url}"

        parsed = urlparse(url)
        self.is_https = parsed.scheme == "https"
        self.host = parsed.hostname or "localhost"
        self.port = parsed.port or (443 if self.is_https else 8000)
        self.timeout = 600
        self.url = f"{parsed.scheme}://{self.host}:{self.port}"

    def _get_connection(self) -> http.client.HTTPConnection:
        """Create an HTTP(S) connection."""
        if self.is_https:
            context = ssl.create_default_context()
            return http.client.HTTPSConnection(
                self.host, self.port, timeout=self.timeout, context=context
            )
        else:
            return http.client.HTTPConnection(
                self.host, self.port, timeout=self.timeout
            )

    def generate_streaming(
        self,
        messages: List[Dict[str, str]],
        stream_options: Dict = None,
    ) -> Iterator[str]:
        """
        Generate streaming response from LLM.

        Args:
            messages: List of message dicts with 'role' and 'content'
            stream_options: Optional streaming parameters

        Yields:
            Text chunks as they arrive
        """
        # Build request payload
        if stream_options is None:
            stream_options = {"streaming": True}
        else:
            stream_options = {"streaming": True, **stream_options}

        # Build the request payload using the custom generate_stream format
        payload = {
            "text_input": json.dumps(messages),
            "parameters": stream_options,
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

        body = json.dumps(payload).encode("utf-8")
        path = f"/v2/models/{self.model_name}/generate_stream"

        conn = None
        try:
            conn = self._get_connection()
            conn.request("POST", path, body=body, headers=headers)
            response = conn.getresponse()

            if response.status not in (200, 201):
                error_body = response.read().decode("utf-8")
                raise Exception(
                    f"Server returned {response.status}: {error_body}"
                )

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

                    # Remove SSE "data: " prefix if present
                    if line.startswith("data: "):
                        line = line[6:]

                    # Check for end signal
                    if line == "[DONE]":
                        return

                    try:
                        data = json.loads(line)

                        # Handle both text_output and outputs formats
                        output_data = None
                        if "text_output" in data:
                            output_data = data["text_output"]
                        elif "outputs" in data and len(data["outputs"]) > 0:
                            output_data = data["outputs"][0].get("data", [""])[
                                0
                            ]

                        if output_data:
                            # Parse the actual response
                            try:
                                chunk_data = json.loads(output_data)

                                if chunk_data.get("type") == "chunk":
                                    yield chunk_data.get("content", "")
                                elif chunk_data.get("type") == "complete":
                                    # Stream is complete
                                    return
                                elif chunk_data.get("type") == "error":
                                    raise Exception(
                                        f"LLM error: {chunk_data.get('content')}"
                                    )
                            except (json.JSONDecodeError, TypeError):
                                # If not JSON, treat as plain text chunk
                                yield output_data

                    except json.JSONDecodeError:
                        # If line is not JSON, skip it
                        continue

        finally:
            if conn:
                conn.close()

    def generate(
        self,
        messages: List[Dict[str, str]],
        stream_options: Dict = None,
    ) -> str:
        """
        Generate non-streaming response from LLM.

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
        """Check if Triton server is healthy."""
        try:
            conn = self._get_connection()
            conn.request("GET", "/v2/health/live")
            response = conn.getresponse()
            conn.close()
            return response.status == 200
        except Exception:
            return False
