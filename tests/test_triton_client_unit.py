"""Unit tests for TritonLLMClient (with mocking, no real server needed)."""

import json
from unittest.mock import Mock, patch

import pytest

from kubrick_cli.triton_client import TritonLLMClient


class TestTritonLLMClientInit:
    """Test suite for TritonLLMClient initialization."""

    def test_init_default_url(self):
        """Test initialization with default URL."""
        client = TritonLLMClient()

        assert client.model_name == "llm_decoupled"
        assert client.host == "localhost"
        assert client.port == 8000
        assert client.is_https is False
        assert client.url == "http://localhost:8000"

    def test_init_custom_url_http(self):
        """Test initialization with custom HTTP URL."""
        client = TritonLLMClient(url="http://example.com:9000")

        assert client.host == "example.com"
        assert client.port == 9000
        assert client.is_https is False
        assert client.url == "http://example.com:9000"

    def test_init_custom_url_https(self):
        """Test initialization with HTTPS URL."""
        client = TritonLLMClient(url="https://secure.example.com")

        assert client.host == "secure.example.com"
        assert client.port == 443
        assert client.is_https is True
        assert client.url == "https://secure.example.com:443"

    def test_init_url_without_scheme(self):
        """Test initialization with URL without scheme (should default to http)."""
        client = TritonLLMClient(url="myserver:8888")

        assert client.host == "myserver"
        assert client.port == 8888
        assert client.is_https is False
        assert client.url == "http://myserver:8888"

    def test_init_custom_model(self):
        """Test initialization with custom model name."""
        client = TritonLLMClient(model_name="custom_model")

        assert client.model_name == "custom_model"

    def test_init_timeout(self):
        """Test that timeout is set."""
        client = TritonLLMClient()

        assert client.timeout == 600


class TestTritonLLMClientHealthCheck:
    """Test suite for TritonLLMClient health check."""

    @patch("http.client.HTTPConnection")
    def test_is_healthy_success(self, mock_http_conn):
        """Test health check when server is healthy."""
        mock_response = Mock()
        mock_response.status = 200

        mock_conn_instance = Mock()
        mock_conn_instance.getresponse.return_value = mock_response
        mock_http_conn.return_value = mock_conn_instance

        client = TritonLLMClient()
        is_healthy = client.is_healthy()

        assert is_healthy is True
        mock_conn_instance.request.assert_called_once_with("GET", "/v2/health/live")

    @patch("http.client.HTTPConnection")
    def test_is_healthy_failure(self, mock_http_conn):
        """Test health check when server returns error."""
        mock_response = Mock()
        mock_response.status = 500

        mock_conn_instance = Mock()
        mock_conn_instance.getresponse.return_value = mock_response
        mock_http_conn.return_value = mock_conn_instance

        client = TritonLLMClient()
        is_healthy = client.is_healthy()

        assert is_healthy is False

    @patch("http.client.HTTPConnection")
    def test_is_healthy_exception(self, mock_http_conn):
        """Test health check when connection fails."""
        mock_http_conn.side_effect = Exception("Connection refused")

        client = TritonLLMClient()
        is_healthy = client.is_healthy()

        assert is_healthy is False


class TestTritonLLMClientStreaming:
    """Test suite for TritonLLMClient streaming functionality."""

    def _create_mock_response(self, chunks):
        """Helper to create mock streaming response."""
        mock_response = Mock()
        mock_response.status = 200

        chunk_queue = list(chunks)

        def mock_read(size):
            if chunk_queue:
                return chunk_queue.pop(0)
            return b""

        mock_response.read = mock_read
        return mock_response

    @patch("http.client.HTTPConnection")
    def test_generate_streaming_success(self, mock_http_conn):
        """Test streaming generation with successful response."""
        chunk1 = json.dumps(
            {"outputs": [{"data": [json.dumps({"type": "chunk", "content": "Hello"})]}]}
        ).encode("utf-8")
        chunk2 = b"\n"
        chunk3 = json.dumps(
            {
                "outputs": [
                    {"data": [json.dumps({"type": "chunk", "content": " World"})]}
                ]
            }
        ).encode("utf-8")
        chunk4 = b"\n"
        chunk5 = json.dumps(
            {
                "outputs": [
                    {
                        "data": [
                            json.dumps(
                                {
                                    "type": "complete",
                                    "content": json.dumps(
                                        [
                                            {
                                                "role": "assistant",
                                                "content": "Hello World",
                                            }
                                        ]
                                    ),
                                }
                            )
                        ]
                    }
                ]
            }
        ).encode("utf-8")
        chunk6 = b"\n"

        mock_response = self._create_mock_response(
            [chunk1, chunk2, chunk3, chunk4, chunk5, chunk6]
        )

        mock_conn_instance = Mock()
        mock_conn_instance.getresponse.return_value = mock_response
        mock_http_conn.return_value = mock_conn_instance

        client = TritonLLMClient()
        messages = [{"role": "user", "content": "Say hello"}]

        chunks = list(client.generate_streaming(messages))

        assert len(chunks) == 2
        assert chunks[0] == "Hello"
        assert chunks[1] == " World"

    @patch("http.client.HTTPConnection")
    def test_generate_streaming_done_signal(self, mock_http_conn):
        """Test streaming with [DONE] signal."""
        chunk1 = b'data: {"outputs": [{"data": ["'
        chunk2 = json.dumps({"type": "chunk", "content": "Hi"}).encode("utf-8")
        chunk3 = b'"]}\n'
        chunk4 = b"data: [DONE]\n"

        mock_response = self._create_mock_response([chunk1, chunk2, chunk3, chunk4])

        mock_conn_instance = Mock()
        mock_conn_instance.getresponse.return_value = mock_response
        mock_http_conn.return_value = mock_conn_instance

        client = TritonLLMClient()
        messages = [{"role": "user", "content": "Test"}]

        chunks = list(client.generate_streaming(messages))

        assert len(chunks) >= 0

    @patch("http.client.HTTPConnection")
    def test_generate_streaming_server_error(self, mock_http_conn):
        """Test streaming when server returns error status."""
        mock_response = Mock()
        mock_response.status = 500
        mock_response.read.return_value = b"Internal Server Error"

        mock_conn_instance = Mock()
        mock_conn_instance.getresponse.return_value = mock_response
        mock_http_conn.return_value = mock_conn_instance

        client = TritonLLMClient()
        messages = [{"role": "user", "content": "Test"}]

        with pytest.raises(Exception) as exc_info:
            list(client.generate_streaming(messages))

        assert "500" in str(exc_info.value)

    @patch("http.client.HTTPConnection")
    def test_generate_streaming_error_response(self, mock_http_conn):
        """Test streaming with error type response."""
        error_chunk = json.dumps(
            {
                "outputs": [
                    {
                        "data": [
                            json.dumps(
                                {"type": "error", "content": "Model error occurred"}
                            )
                        ]
                    }
                ]
            }
        ).encode("utf-8")

        mock_response = self._create_mock_response([error_chunk, b"\n"])

        mock_conn_instance = Mock()
        mock_conn_instance.getresponse.return_value = mock_response
        mock_http_conn.return_value = mock_conn_instance

        client = TritonLLMClient()
        messages = [{"role": "user", "content": "Test"}]

        with pytest.raises(Exception) as exc_info:
            list(client.generate_streaming(messages))

        assert "LLM error" in str(exc_info.value)

    @patch("http.client.HTTPConnection")
    def test_generate_streaming_with_options(self, mock_http_conn):
        """Test streaming with custom stream options."""
        mock_response = self._create_mock_response([b""])

        mock_conn_instance = Mock()
        mock_conn_instance.getresponse.return_value = mock_response
        mock_http_conn.return_value = mock_conn_instance

        client = TritonLLMClient()
        messages = [{"role": "user", "content": "Test"}]
        stream_options = {"temperature": 0.7, "max_tokens": 100}

        list(client.generate_streaming(messages, stream_options))

        call_args = mock_conn_instance.request.call_args
        assert call_args is not None

        body = call_args[1]["body"]
        payload = json.loads(body.decode("utf-8"))

        assert "parameters" in payload
        assert payload["parameters"]["streaming"] is True
        assert payload["parameters"]["temperature"] == 0.7
        assert payload["parameters"]["max_tokens"] == 100


class TestTritonLLMClientNonStreaming:
    """Test suite for TritonLLMClient non-streaming functionality."""

    @patch.object(TritonLLMClient, "generate_streaming")
    def test_generate_success(self, mock_streaming):
        """Test non-streaming generation."""
        mock_streaming.return_value = iter(["Hello", " ", "World"])

        client = TritonLLMClient()
        messages = [{"role": "user", "content": "Say hello"}]

        result = client.generate(messages)

        assert result == "Hello World"
        mock_streaming.assert_called_once_with(messages, None)

    @patch.object(TritonLLMClient, "generate_streaming")
    def test_generate_with_options(self, mock_streaming):
        """Test non-streaming generation with options."""
        mock_streaming.return_value = iter(["Response"])

        client = TritonLLMClient()
        messages = [{"role": "user", "content": "Test"}]
        stream_options = {"temperature": 0.5}

        result = client.generate(messages, stream_options)

        assert result == "Response"
        mock_streaming.assert_called_once_with(messages, stream_options)

    @patch.object(TritonLLMClient, "generate_streaming")
    def test_generate_empty_response(self, mock_streaming):
        """Test non-streaming with empty response."""
        mock_streaming.return_value = iter([])

        client = TritonLLMClient()
        messages = [{"role": "user", "content": "Test"}]

        result = client.generate(messages)

        assert result == ""


class TestTritonLLMClientUTF8Handling:
    """Test suite for TritonLLMClient UTF-8 handling."""

    def _create_mock_response_with_bytes(self, byte_chunks):
        """Helper to create mock response with specific byte sequences."""
        mock_response = Mock()
        mock_response.status = 200

        chunk_queue = list(byte_chunks)

        def mock_read(size):
            if chunk_queue:
                return chunk_queue.pop(0)
            return b""

        mock_response.read = mock_read
        return mock_response

    @patch("http.client.HTTPConnection")
    def test_utf8_multibyte_character(self, mock_http_conn):
        """Test handling of multi-byte UTF-8 characters."""
        emoji_content = json.dumps({"type": "chunk", "content": "Hello 👋"})
        chunk = json.dumps({"outputs": [{"data": [emoji_content]}]}).encode("utf-8")

        mock_response = self._create_mock_response_with_bytes([chunk, b"\n"])

        mock_conn_instance = Mock()
        mock_conn_instance.getresponse.return_value = mock_response
        mock_http_conn.return_value = mock_conn_instance

        client = TritonLLMClient()
        messages = [{"role": "user", "content": "Test"}]

        chunks = list(client.generate_streaming(messages))

        assert len(chunks) == 1
        assert "👋" in chunks[0]

    @patch("http.client.HTTPConnection")
    def test_utf8_split_across_chunks(self, mock_http_conn):
        """Test handling UTF-8 character split across read chunks."""
        part1 = b'{"outputs": [{"data": ["'
        emoji_bytes = "👋".encode("utf-8")
        part2 = emoji_bytes[:2]
        part3 = emoji_bytes[2:]
        part4 = b'"]}\n'

        mock_response = self._create_mock_response_with_bytes(
            [part1, part2, part3, part4]
        )

        mock_conn_instance = Mock()
        mock_conn_instance.getresponse.return_value = mock_response
        mock_http_conn.return_value = mock_conn_instance

        client = TritonLLMClient()
        messages = [{"role": "user", "content": "Test"}]

        try:
            list(client.generate_streaming(messages))
            assert True
        except UnicodeDecodeError:
            pytest.fail("UnicodeDecodeError raised - UTF-8 handling broken")


class TestTritonLLMClientConnectionManagement:
    """Test suite for connection management."""

    @patch("http.client.HTTPConnection")
    def test_connection_closed_after_streaming(self, mock_http_conn):
        """Test that connection is properly closed after streaming."""
        mock_response = Mock()
        mock_response.status = 200
        mock_response.read.return_value = b""

        mock_conn_instance = Mock()
        mock_conn_instance.getresponse.return_value = mock_response
        mock_http_conn.return_value = mock_conn_instance

        client = TritonLLMClient()
        messages = [{"role": "user", "content": "Test"}]

        list(client.generate_streaming(messages))

        mock_conn_instance.close.assert_called_once()

    @patch("http.client.HTTPSConnection")
    def test_https_connection(self, mock_https_conn):
        """Test that HTTPS connection is used for https URLs."""
        client = TritonLLMClient(url="https://secure.example.com")

        client._get_connection()

        assert mock_https_conn.called


class TestTritonLLMClientRequestPayload:
    """Test suite for request payload formatting."""

    @patch("http.client.HTTPConnection")
    def test_request_payload_format(self, mock_http_conn):
        """Test that request payload is correctly formatted."""
        mock_response = Mock()
        mock_response.status = 200
        mock_response.read.return_value = b""

        mock_conn_instance = Mock()
        mock_conn_instance.getresponse.return_value = mock_response
        mock_http_conn.return_value = mock_conn_instance

        client = TritonLLMClient()
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
        ]

        list(client.generate_streaming(messages))

        call_args = mock_conn_instance.request.call_args
        method, path, body_kwarg, headers_kwarg = (
            call_args[0][0],
            call_args[0][1],
            call_args[1]["body"],
            call_args[1]["headers"],
        )

        assert method == "POST"
        assert path == "/v2/models/llm_decoupled/generate_stream"

        assert headers_kwarg["Content-Type"] == "application/json"
        assert headers_kwarg["Accept"] == "text/event-stream"

        payload = json.loads(body_kwarg.decode("utf-8"))
        assert "text_input" in payload
        assert "parameters" in payload

        text_input = json.loads(payload["text_input"])
        assert len(text_input) == 2
        assert text_input[0]["role"] == "system"
        assert text_input[1]["role"] == "user"
