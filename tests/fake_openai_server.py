"""A scripted OpenAI-compatible streaming server for end-to-end tests."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeOpenAIServer:
    """Serves /v1/models and streams scripted /v1/chat/completions responses.

    Each script entry is a dict with optional ``text``, ``tool_calls``
    (list of (name, arguments_dict)), ``reasoning``, ``finish_reason``, or
    ``status``/``error`` to return an HTTP error.
    """

    def __init__(
        self, script, models=("test-model",), max_model_len=None, responses_api=True
    ):
        self.script = list(script)
        self.requests = []
        self.models = models
        # Serve OpenAI's Responses API on POST /v1/responses (else 404, like a gateway).
        self.responses_api = responses_api
        self.max_model_len = max_model_len
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.path == "/v1/models":
                    data = [{"id": m, "object": "model"} for m in server.models]
                    if server.max_model_len:
                        for d in data:
                            d["max_model_len"] = server.max_model_len
                    self._json(200, {"data": data})
                else:
                    self._json(404, {"error": "not found"})

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length))
                server.requests.append(body)
                step = (
                    server.script.pop(0)
                    if server.script
                    else {"text": "(script exhausted)"}
                )
                if step.get("status"):
                    self._json(step["status"], {"error": {"message": step["error"]}})
                    return
                if self.path.endswith("/responses") and not server.responses_api:
                    self._json(404, {"error": {"message": "Not found"}})
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                chunks = (
                    server._responses_events(step)
                    if self.path.endswith("/responses")
                    else server._chunks(step)
                )
                for chunk in chunks:
                    self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                    self.wfile.flush()
                self.wfile.write(b"data: [DONE]\n\n")

            def _json(self, status, payload):
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self.httpd.server_address[1]}/v1"

    def _chunks(self, step):
        def delta(d, finish=None):
            return {"choices": [{"index": 0, "delta": d, "finish_reason": finish}]}

        if step.get("reasoning"):
            yield delta({"reasoning_content": step["reasoning"]})
        text = step.get("text", "")
        for i in range(0, len(text), 7):
            yield delta({"content": text[i : i + 7]})
        for idx, (name, args) in enumerate(step.get("tool_calls", [])):
            raw = json.dumps(args)
            yield delta(
                {
                    "tool_calls": [
                        {
                            "index": idx,
                            "id": f"call_{idx}",
                            "type": "function",
                            "function": {"name": name, "arguments": ""},
                        }
                    ]
                }
            )
            for i in range(0, len(raw), 5):
                yield delta(
                    {
                        "tool_calls": [
                            {"index": idx, "function": {"arguments": raw[i : i + 5]}}
                        ]
                    }
                )
        finish = step.get("finish_reason") or (
            "tool_calls" if step.get("tool_calls") else "stop"
        )
        yield delta({}, finish)
        yield {"choices": [], "usage": {"prompt_tokens": 1000, "completion_tokens": 50}}

    def _responses_events(self, step):
        """The same scripted step as Responses API stream events."""
        if step.get("reasoning"):
            yield {
                "type": "response.reasoning_summary_text.delta",
                "delta": step["reasoning"],
            }
            yield {
                "type": "response.output_item.done",
                "item": {
                    "type": "reasoning",
                    "id": "rs_1",
                    "summary": [{"type": "summary_text", "text": step["reasoning"]}],
                    "encrypted_content": "ENCRYPTED",
                    "status": "completed",
                },
            }
        text = step.get("text", "")
        for i in range(0, len(text), 7):
            yield {"type": "response.output_text.delta", "delta": text[i : i + 7]}
        if text:
            yield {
                "type": "response.output_item.done",
                "item": {
                    "type": "message",
                    "id": "msg_1",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": text}],
                },
            }
        for idx, (name, args) in enumerate(step.get("tool_calls", [])):
            yield {
                "type": "response.output_item.done",
                "item": {
                    "type": "function_call",
                    "id": f"fc_{idx}",
                    "call_id": f"call_{idx}",
                    "name": name,
                    "arguments": json.dumps(args),
                },
            }
        yield {
            "type": "response.completed",
            "response": {
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 50,
                    "input_tokens_details": {"cached_tokens": 200},
                }
            },
        }

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
