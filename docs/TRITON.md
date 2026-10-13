# Triton Backend Setup for Kubrick CLI

How to serve a model from NVIDIA Triton Inference Server so Kubrick can use it.

> **Is Triton the right choice?** For most local setups, an OpenAI-compatible
> server (Ollama, vLLM, llama.cpp, LM Studio) is simpler and supports native tool
> calling — see [PROVIDERS.md](PROVIDERS.md). Use Triton when your infrastructure
> already runs it.

## How Kubrick talks to Triton

- **Protocol:** HTTP `POST /v2/models/{model}/generate_stream` with Server-Sent Events.
- **Health check:** `GET /v2/health/live` (must return 200).
- **Tool calling:** text-based. Triton models stream plain text, so Kubrick
  describes its tools in the system prompt and the model calls them by writing
  fenced blocks:

  ````
  ```tool_call
  {"tool": "read_file", "parameters": {"file_path": "src/app.py"}}
  ```
  ````

  Tool results come back as a user message. No special model support is needed,
  but instruction-tuned coding models follow the format far more reliably.

### Request

```json
{
  "text_input": "[{\"role\": \"system\", \"content\": \"...\"}, {\"role\": \"user\", \"content\": \"Hello\"}]",
  "parameters": {"streaming": true, "temperature": 0.7, "max_tokens": 2048}
}
```

- `text_input` — JSON-encoded list of `{"role", "content"}` messages (roles:
  `system`, `user`, `assistant`). Maps to the model's `text_input` tensor.
- `parameters` — Triton's generate extension passes this object as **request
  parameters**, not as an input tensor. Read it in the model with
  `request.parameters()`. `temperature` and `max_tokens` are only sent when set.

### Response

Each SSE event carries the `text_output` tensor:

```
data: {"model_name": "llm_decoupled", "model_version": "1", "text_output": "{\"type\": \"chunk\", \"content\": \"Hel\"}"}
data: {"model_name": "llm_decoupled", "model_version": "1", "text_output": "{\"type\": \"chunk\", \"content\": \"lo\"}"}
data: {"model_name": "llm_decoupled", "model_version": "1", "text_output": "{\"type\": \"complete\"}"}
```

`text_output` should be a JSON chunk:

| `type`     | Meaning                                         |
| ---------- | ----------------------------------------------- |
| `chunk`    | `content` is the next piece of text             |
| `complete` | End of the response                             |
| `error`    | Generation failed; `content` is the message     |

A `text_output` that isn't a JSON object with a `type` is treated as raw text,
so a model that streams plain tokens also works — but the JSON form lets the
model report errors and end the stream explicitly.

## Example model

A complete, working example lives in
[`examples/triton/llm_decoupled/`](../examples/triton/llm_decoupled/):

```
examples/triton/llm_decoupled/
├── config.pbtxt
└── 1/model.py
```

### config.pbtxt

```protobuf
name: "llm_decoupled"
backend: "python"
max_batch_size: 0
model_transaction_policy { decoupled: true }
input  [ { name: "text_input"  data_type: TYPE_STRING dims: [ 1 ] } ]
output [ { name: "text_output" data_type: TYPE_STRING dims: [ 1 ] } ]
instance_group [ { kind: KIND_GPU count: 1 } ]
```

- `decoupled: true` — lets one request produce many responses (streaming).
- `max_batch_size: 0` with `dims: [ 1 ]` — the input arrives with shape `(1,)`,
  so index it with `[0]`.
- There is **no** `parameters` input: request parameters are not tensors.

### model.py essentials

A decoupled Python model must answer through each request's **response sender**
and return `None` from `execute()`; returning a list of responses only works for
non-decoupled models.

```python
def execute(self, requests):
    for request in requests:
        sender = request.get_response_sender()
        try:
            raw = pb_utils.get_input_tensor_by_name(request, "text_input").as_numpy()[0]
            messages = json.loads(raw.decode("utf-8"))
            params = json.loads(request.parameters() or "{}")
            for text in stream_tokens(messages, params):   # your LLM here
                self._send(sender, {"type": "chunk", "content": text})
            self._send(sender, {"type": "complete"})
        except Exception as e:
            self._send(sender, {"type": "error", "content": str(e)})
        finally:
            sender.send(flags=pb_utils.TRITONSERVER_RESPONSE_COMPLETE_FINAL)
    return None
```

The example implements `stream_tokens` with Hugging Face `transformers`
(`apply_chat_template` + `TextIteratorStreamer` on a background thread) using
`Qwen/Qwen2.5-Coder-7B-Instruct` in bf16, which fits a 24 GB GPU. Change
`MODEL_ID` in `model.py` to use another model.

## Running it

The stock `nvcr.io/nvidia/tritonserver:<yy.mm>-py3` image has the Python
backend but **not** PyTorch or Transformers. Build a small image on top:

```dockerfile
FROM nvcr.io/nvidia/tritonserver:24.08-py3
RUN pip install --no-cache-dir torch transformers accelerate
```

```bash
docker build -t triton-llm .
docker run --rm --gpus all -p 8000:8000 \
  -v $PWD/examples/triton:/models \
  -v $HOME/.cache/huggingface:/root/.cache/huggingface \
  triton-llm tritonserver --model-repository=/models
```

Pick a Triton tag that matches your NVIDIA driver (see the
[framework support matrix](https://docs.nvidia.com/deeplearning/frameworks/support-matrix/)).

## Configuring Kubrick

Run `kubrick` and choose **NVIDIA Triton** in the setup wizard, or edit
`~/.kubrick/config.json`:

```json
{
  "provider": "triton",
  "triton_url": "localhost:8000",
  "triton_model": "llm_decoupled"
}
```

Environment variables override the config file:

```bash
export KUBRICK_TRITON_URL=gpu-box:8000
export KUBRICK_TRITON_MODEL=llm_decoupled
kubrick --provider triton
```

`triton_url` accepts `host:port` (HTTP) or a full `http://` / `https://` URL.

Set the context window to match your model so Kubrick trims history in time,
e.g. `/config context_window 32768`.

## Testing your server

```bash
# Health
curl -i http://localhost:8000/v2/health/live

# Streaming
curl -N -X POST http://localhost:8000/v2/models/llm_decoupled/generate_stream \
  -H "Content-Type: application/json" \
  -d '{"text_input": "[{\"role\":\"user\",\"content\":\"Say hello\"}]", "parameters": {"streaming": true}}'
```

You should see a series of `data: {...}` lines ending with a `complete` chunk.

Kubrick's own Triton tests are mocked and need no server:

```bash
pytest tests/test_triton_client_unit.py tests/test_triton_provider.py
```

## Troubleshooting

**Connection refused** — check `curl http://<host>:8000/v2/health/live`, that
the port is published (`-p 8000:8000`), and firewall rules.

**Model not found / failed to load** — check the Triton startup log. Common
causes: `torch`/`transformers` missing from the image, wrong directory layout
(`<repo>/llm_decoupled/config.pbtxt` and `<repo>/llm_decoupled/1/model.py`), or
out of GPU memory.

**Request hangs or returns nothing** — the model must be `decoupled: true`,
use `request.get_response_sender()`, and always finish with
`TRITONSERVER_RESPONSE_COMPLETE_FINAL` (put it in a `finally`).

**`unexpected inference input 'parameters'`** — remove the `parameters`
input from `config.pbtxt`; read `request.parameters()` instead.

**The model talks about tools instead of calling them** — smaller models
sometimes ignore the `tool_call` format. Use a stronger instruction-tuned
coding model, or serve it through an OpenAI-compatible server (vLLM, Ollama)
to get native tool calling.

## Performance notes

- One `instance_group` instance handles one request at a time with the example
  model. For concurrent users, raise `count` (memory permitting) or put vLLM
  behind the model instead of `transformers`.
- Pin a GPU with `instance_group [ { kind: KIND_GPU count: 1 gpus: [ 0 ] } ]`.

## Resources

- [Triton Inference Server docs](https://docs.nvidia.com/deeplearning/triton-inference-server/)
- [Python backend](https://github.com/triton-inference-server/python_backend)
- [Decoupled models](https://github.com/triton-inference-server/server/blob/main/docs/user_guide/decoupled_models.md)
- [Generate extension](https://github.com/triton-inference-server/server/blob/main/docs/protocol/extension_generate.md)
- Kubrick issues: <https://github.com/rcland12/kubrick-cli/issues>
