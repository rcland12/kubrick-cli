# Triton Backend Setup for Kubrick CLI

Complete guide to setting up and configuring Triton Inference Server for use with Kubrick CLI.

## Requirements

Kubrick CLI requires a Triton Inference Server with a streaming LLM model that implements a specific HTTP endpoint.

### Server Requirements

- **Triton Inference Server** (version 2.x+)
- **HTTP Protocol** (gRPC not required)
- **Streaming Support** via Server-Sent Events (SSE)
- **Python Backend** (recommended for custom LLM integration)

### Default Configuration

- **Endpoint**: `http://localhost:8000`
- **Model Name**: `llm_decoupled`
- **Protocol**: HTTP with SSE streaming

## Required Endpoint

Your Triton model must implement the following custom endpoint:

### Endpoint Specification

- **Path**: `/v2/models/{model_name}/generate_stream`
- **Method**: `POST`
- **Content-Type**: `application/json`
- **Accept**: `text/event-stream`

### Request Format

The client sends a JSON payload with the following structure:

```json
{
  "text_input": "[{\"role\": \"user\", \"content\": \"Your message here\"}]",
  "parameters": {
    "streaming": true
  }
}
```

**Fields:**

- `text_input` (string): JSON-encoded array of message objects in OpenAI chat format
  - Each message has `role` (user/assistant/system) and `content`
  - Example: `[{"role": "user", "content": "Hello"}]`

- `parameters` (object): Streaming and generation options
  - `streaming` (boolean): Must be `true` for streaming responses
  - Additional parameters can be added (temperature, max_tokens, etc.)

### Response Format

The server must return an SSE (Server-Sent Events) stream with JSON chunks.

#### Option 1: Direct JSON Chunks

```
data: {"type": "chunk", "content": "Hello"}
data: {"type": "chunk", "content": " world"}
data: {"type": "complete"}
```

#### Option 2: Triton-Wrapped Format

```json
{
  "text_output": "{\"type\": \"chunk\", \"content\": \"text\"}",
  "outputs": [{ "data": ["{\"type\": \"chunk\", \"content\": \"text\"}"] }]
}
```

**Response Types:**

| Type       | Description                                | Required |
| ---------- | ------------------------------------------ | -------- |
| `chunk`    | Text/token chunk during streaming          | Yes      |
| `complete` | Marks end of stream                        | Yes      |
| `error`    | Error occurred (content has error message) | Optional |

**Example Stream:**

```
data: {"type": "chunk", "content": "The"}
data: {"type": "chunk", "content": " answer"}
data: {"type": "chunk", "content": " is"}
data: {"type": "chunk", "content": " 42"}
data: {"type": "complete"}
```

## Model Configuration

### Triton Model Repository Structure

```
model_repository/
└── llm_decoupled/
    ├── config.pbtxt
    └── 1/
        └── model.py
```

### config.pbtxt Example

```protobuf
name: "llm_decoupled"
backend: "python"
max_batch_size: 0

input [
  {
    name: "text_input"
    data_type: TYPE_STRING
    dims: [ 1 ]
  },
  {
    name: "parameters"
    data_type: TYPE_STRING
    dims: [ 1 ]
    optional: true
  }
]

output [
  {
    name: "text_output"
    data_type: TYPE_STRING
    dims: [ 1 ]
  }
]

instance_group [
  {
    kind: KIND_CPU
    count: 1
  }
]

model_transaction_policy {
  decoupled: True
}
```

**Key Configuration Points:**

- `backend: "python"` - Use Python backend for custom LLM integration
- `max_batch_size: 0` - Disable batching (handle one request at a time)
- `decoupled: True` - Enable streaming responses (0..N responses per request)
- `text_input` - Accepts message array as string
- `parameters` - Optional streaming/generation options
- `text_output` - Returns streaming response chunks

### Python Backend Implementation

Your `model.py` should:

1. Accept `text_input` and `parameters`
2. Parse JSON messages
3. Call your LLM (vLLM, OpenAI, etc.)
4. Stream responses as JSON chunks
5. Send completion signal

**Basic Structure:**

```python
import json
import triton_python_backend_utils as pb_utils

class TritonPythonModel:
    def execute(self, requests):
        responses = []
        for request in requests:
            # Parse input
            text_input = pb_utils.get_input_tensor_by_name(
                request, "text_input"
            ).as_numpy()[0][0].decode('utf-8')

            messages = json.loads(text_input)

            # Stream LLM responses
            for token in your_llm_stream(messages):
                chunk = {"type": "chunk", "content": token}
                output_tensor = pb_utils.Tensor(
                    "text_output",
                    np.array([[json.dumps(chunk).encode('utf-8')]], dtype=np.object_)
                )
                response = pb_utils.InferenceResponse([output_tensor])
                responses.append(response)

            # Send completion
            complete = {"type": "complete"}
            output_tensor = pb_utils.Tensor(
                "text_output",
                np.array([[json.dumps(complete).encode('utf-8')]], dtype=np.object_)
            )
            responses.append(pb_utils.InferenceResponse([output_tensor]))

        return responses
```

## LLM Backend Integration

### Option 1: vLLM

```python
from vllm import LLM, SamplingParams

llm = LLM(model="meta-llama/Llama-3-8B-Instruct")

def stream_generate(messages):
    # Convert to vLLM format and stream
    for output in llm.generate(prompt, sampling_params, use_tqdm=False):
        yield output.outputs[0].text
```

### Option 2: OpenAI API

```python
from openai import OpenAI

client = OpenAI(api_key="...")

def stream_generate(messages):
    stream = client.chat.completions.create(
        model="gpt-4",
        messages=messages,
        stream=True
    )
    for chunk in stream:
        if chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
```

### Option 3: Transformers

```python
from transformers import AutoModelForCausalLM, AutoTokenizer

model = AutoModelForCausalLM.from_pretrained("...")
tokenizer = AutoTokenizer.from_pretrained("...")

def stream_generate(messages):
    # Implement streaming with TextIteratorStreamer
    pass
```

## Health Check Endpoint

Kubrick CLI checks server health at startup using:

```
GET /v2/health/live
```

Ensure this endpoint returns HTTP 200 when Triton is running.

## Configuration in Kubrick

### Method 1: Config File

`~/.kubrick/config.json`:

```json
{
  "triton_url": "localhost:8000",
  "model_name": "llm_decoupled"
}
```

### Method 2: Environment Variables

```bash
export TRITON_URL=localhost:8000
export TRITON_MODEL_NAME=llm_decoupled
```

### Method 3: Command Line

```bash
kubrick --triton-url localhost:8000 --model-name llm_decoupled
```

## Testing Your Triton Setup

### 1. Check Server Health

```bash
curl http://localhost:8000/v2/health/live
```

Expected: HTTP 200

### 2. Test Streaming Endpoint

```bash
curl -X POST http://localhost:8000/v2/models/llm_decoupled/generate_stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "text_input": "[{\"role\":\"user\",\"content\":\"Say hello\"}]",
    "parameters": {"streaming": true}
  }'
```

Expected: SSE stream with JSON chunks

### 3. Test with Kubrick

```bash
# Run Kubrick test suite
pytest tests/test_triton.py

# Or run Kubrick CLI
kubrick
You: Say hello in one word
```

## Troubleshooting

### Connection Refused

**Problem:** Cannot connect to Triton server

**Solutions:**

- Check Triton is running: `curl http://localhost:8000/v2/health/live`
- Verify port 8000 is open: `netstat -tuln | grep 8000`
- Check firewall settings

### Model Not Found

**Problem:** `Model llm_decoupled not found`

**Solutions:**

- Verify model is in repository: `ls /path/to/model_repository/llm_decoupled`
- Check Triton logs for loading errors
- Ensure `config.pbtxt` is valid

### Streaming Not Working

**Problem:** No streaming responses or timeout

**Solutions:**

- Ensure `decoupled: True` in config.pbtxt
- Check SSE headers: `Accept: text/event-stream`
- Verify Python backend streams responses incrementally
- Check Triton logs for errors

### Invalid Response Format

**Problem:** Kubrick can't parse responses

**Solutions:**

- Ensure responses are JSON: `{"type": "chunk", "content": "..."}`
- Include `type` field in all responses
- Send `{"type": "complete"}` to end stream
- Check for proper JSON encoding (use `json.dumps()`)

## Performance Tuning

### GPU Configuration

For GPU-accelerated models:

```protobuf
instance_group [
  {
    kind: KIND_GPU
    count: 1
    gpus: [ 0 ]
  }
]
```

### Concurrent Requests

Adjust instance count for parallel processing:

```protobuf
instance_group [
  {
    count: 4  # Run 4 parallel instances
  }
]
```

### Model Warmup

Pre-load model at startup to reduce first-request latency.

## Example Implementations

See the `/triton/repository/llm_decoupled/` directory in the Kubrick repository for a complete working example with vLLM integration.

## Additional Resources

- [Triton Inference Server Documentation](https://docs.nvidia.com/deeplearning/triton-inference-server/)
- [Python Backend Guide](https://github.com/triton-inference-server/python_backend)
- [Decoupled Models](https://github.com/triton-inference-server/server/blob/main/docs/user_guide/decoupled_models.md)
- [vLLM Integration](https://github.com/vllm-project/vllm)

## Support

For Triton-specific issues:

- [Triton GitHub Issues](https://github.com/triton-inference-server/server/issues)
- [Triton Forums](https://forums.developer.nvidia.com/c/ai/triton-inference-server/)

For Kubrick integration issues:

- [Kubrick GitHub Issues](https://github.com/yourusername/kubrick/issues)
- See [WIKI.md](WIKI.md) for general troubleshooting
