"""Minimal stdlib HTTP + Server-Sent Events helpers shared by providers."""

import http.client
import json
import ssl
from typing import Any, Dict, Iterator, Optional, Tuple
from urllib.parse import urlparse

from .base import ProviderError


class HttpEndpoint:
    """A base URL (scheme, host, port, path prefix) requests are made against."""

    def __init__(
        self, base_url: str, default_port: Optional[int] = None, timeout: int = 600
    ):
        """
        Args:
            base_url: e.g. ``https://api.openai.com/v1`` or ``localhost:11434/v1``
                (scheme defaults to http)
            default_port: Port to use when the URL has none (defaults per scheme)
            timeout: Socket timeout in seconds
        """
        if "://" not in base_url:
            base_url = f"http://{base_url}"
        parsed = urlparse(base_url)
        self.is_https = parsed.scheme == "https"
        self.host = parsed.hostname or "localhost"
        self.port = parsed.port or default_port or (443 if self.is_https else 80)
        self.prefix = parsed.path.rstrip("/")
        self.timeout = timeout

    @property
    def url(self) -> str:
        """Normalized base URL, for display."""
        scheme = "https" if self.is_https else "http"
        return f"{scheme}://{self.host}:{self.port}{self.prefix}"

    def connect(self, timeout: Optional[int] = None) -> http.client.HTTPConnection:
        """Open a connection to the endpoint."""
        timeout = timeout or self.timeout
        if self.is_https:
            return http.client.HTTPSConnection(
                self.host,
                self.port,
                timeout=timeout,
                context=ssl.create_default_context(),
            )
        return http.client.HTTPConnection(self.host, self.port, timeout=timeout)

    def request(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> Tuple[http.client.HTTPConnection, http.client.HTTPResponse]:
        """Send a request; returns the open connection and response.

        The caller must close the connection. Non-2xx responses raise
        ProviderError carrying the response body.
        """
        conn = self.connect(timeout)
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        all_headers = {"Content-Type": "application/json"} if payload else {}
        all_headers.update(headers or {})
        try:
            conn.request(method, self.prefix + path, body=payload, headers=all_headers)
            response = conn.getresponse()
        except (OSError, http.client.HTTPException) as e:
            conn.close()
            raise ProviderError(f"Cannot reach {self.url}: {e}") from e
        if not 200 <= response.status < 300:
            error_body = response.read().decode("utf-8", errors="replace")
            conn.close()
            raise HttpStatusError(response.status, error_body)
        return conn, response

    def get_json(
        self, path: str, headers: Optional[Dict[str, str]] = None, timeout: int = 10
    ):
        """GET a JSON document."""
        conn, response = self.request("GET", path, headers=headers, timeout=timeout)
        try:
            return json.loads(response.read().decode("utf-8"))
        finally:
            conn.close()


class HttpStatusError(ProviderError):
    """Non-2xx HTTP response."""

    def __init__(self, status: int, body: str):
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status}: {_error_message(body)}")


def _error_message(body: str) -> str:
    """Pull the human-readable message out of common JSON error shapes."""
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return body.strip()[:1000]
    if isinstance(data, dict):
        err = data.get("error", data)
        if isinstance(err, dict):
            return str(err.get("message") or err)[:1000]
        if isinstance(err, str):
            return err[:1000]
    return body.strip()[:1000]


def iter_sse_data(response: http.client.HTTPResponse) -> Iterator[str]:
    """Yield the ``data:`` payload of each Server-Sent Event line.

    Decodes on line boundaries so multi-byte UTF-8 characters split across
    reads are handled. Non-``data`` lines (``event:``, comments) are skipped,
    except that bare JSON lines are passed through for servers that stream
    newline-delimited JSON instead of SSE.
    """
    # read1 returns whatever has arrived; read(n) would block until n bytes
    # and make token streaming visibly laggy.
    use_read1 = isinstance(response, http.client.HTTPResponse)
    buffer = b""
    while True:
        chunk = response.read1(65536) if use_read1 else response.read(1024)
        if not chunk:
            break
        buffer += chunk
        while b"\n" in buffer:
            line_bytes, buffer = buffer.split(b"\n", 1)
            line = line_bytes.decode("utf-8", errors="replace").strip()
            if not line or line.startswith(":") or line.startswith("event:"):
                continue
            if line.startswith("data:"):
                yield line[5:].strip()
            elif line.startswith("{"):
                yield line
    tail = buffer.decode("utf-8", errors="replace").strip()
    if tail.startswith("data:"):
        yield tail[5:].strip()
    elif tail.startswith("{"):
        yield tail
