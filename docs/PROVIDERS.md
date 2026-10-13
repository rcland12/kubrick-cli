# Providers

Kubrick talks to models through provider adapters. All of them use the same agent loop,
tools, and permission system; they differ only in how they reach the model.

| Provider | `provider` value | Tool calling | Credentials |
| --- | --- | --- | --- |
| Local model server (Ollama, vLLM, llama.cpp, LM Studio, or any OpenAI-compatible API) | `openai_compatible` | native (auto-fallback to text) | optional API key |
| Anthropic | `anthropic` | native | `ANTHROPIC_API_KEY` or stored key |
| OpenAI | `openai` | native | `OPENAI_API_KEY` or stored key |
| Amazon Bedrock | `bedrock` | native (Converse API) | AWS credential chain |
| Triton Inference Server | `triton` | text protocol | none |

## Choosing and configuring a provider

- `kubrick setup` runs the setup wizard (also runs automatically on first launch).
- `kubrick --provider NAME [--model MODEL]` overrides the provider/model for one session.
- In a session: `/provider` and `/model` open pickers (or take a name), for this session only;
  `/setup` reruns the wizard; `/config KEY VALUE` saves to `~/.kubrick/config.json`.

### Where settings come from

Each setting resolves in this order:

1. Session overrides (`--provider`, `--model`, `/model`, `/provider`)
2. `KUBRICK_<KEY>` environment variables, e.g. `KUBRICK_PROVIDER=anthropic`,
   `KUBRICK_OPENAI_COMPATIBLE_BASE_URL=http://gpu-box:11434/v1`. Values are parsed as JSON
   when possible (`KUBRICK_MAX_ITERATIONS=20` is a number).
3. `~/.kubrick/config.json`
4. The provider's defaults

Setting `KUBRICK_PROVIDER` skips the first-run wizard, which is handy for CI and Docker.

API keys never go in `config.json`. They resolve from the provider's environment variable
first, then the credential store (`kubrick auth login`). See
[SECURITY.md](SECURITY.md#credential-storage).

```bash
kubrick auth login anthropic     # prompt for a key and store it
kubrick auth status              # where each provider's key comes from (never the value)
kubrick auth logout anthropic    # remove a stored key (no provider = all)
```

---

## Local model servers (`openai_compatible`)

Shown as "Local model server" in the wizard. Use this for anything that speaks the OpenAI Chat Completions API: Ollama, vLLM, llama.cpp
(`llama-server`), LM Studio, and hosted OpenAI-compatible services.

| Config key | Default | Meaning |
| --- | --- | --- |
| `openai_compatible_base_url` | `http://localhost:11434/v1` | Server base URL; `host:port` alone works (`http://` and `/v1` are added) |
| `openai_compatible_model` | (required) | Model ID as the server knows it |
| `openai_compatible_api_key` | none | Optional; env `OPENAI_COMPATIBLE_API_KEY` |

```json
{
  "provider": "openai_compatible",
  "openai_compatible_base_url": "http://gpu-box:8000/v1",
  "openai_compatible_model": "Qwen/Qwen3-Coder-30B-A3B-Instruct"
}
```

The setup wizard asks which server you run (Ollama, vLLM, llama.cpp, LM Studio, or something
else), then for its `host:port` (e.g. `192.168.1.50:11434`; `http://` and `/v1` are added). It
checks the connection right away, with fixes for remote servers if it fails, and asks for
an API key only if the server wants one. You pick a model from the server's list, and it
reports the model's context window.

### Context window (important for local models)

The system prompt plus tool definitions take several thousand tokens before you type
anything, and coding sessions grow fast. Kubrick determines the context window in this order:

1. `context_window` in config (set it with `/config context_window 32768`)
2. Reported by the server: vLLM's `max_model_len` from `/v1/models`, or the loaded model's
   `context_length` from Ollama's `/api/ps`
3. Known model families, else 32768 for local servers

At startup Kubrick warns if the window is under 16k tokens. When usage reaches
`context_usage_threshold` (80% by default), older turns are summarized automatically.

### Ollama

```bash
OLLAMA_HOST=0.0.0.0 OLLAMA_CONTEXT_LENGTH=32768 ollama serve
ollama pull qwen3-coder:30b
```

- `OLLAMA_HOST=0.0.0.0` makes Ollama listen on the LAN instead of only localhost.
- `OLLAMA_CONTEXT_LENGTH`: Ollama's default context is small, and the OpenAI-compatible
  endpoint can't change it per request. Prompts that don't fit are **silently truncated**,
  which cuts off the system prompt and tool definitions and makes the model act confused.
  Use 32768 or more if your GPU memory allows.
- Base URL: `http://HOST:11434/v1`. Use a model with tool support; for models without it,
  Kubrick falls back to the text protocol (below).

### vLLM

```bash
vllm serve Qwen/Qwen3-Coder-30B-A3B-Instruct \
  --host 0.0.0.0 --port 8000 \
  --max-model-len 65536 \
  --enable-auto-tool-choice --tool-call-parser hermes
```

- `--enable-auto-tool-choice --tool-call-parser hermes` turns on native tool calling for
  Qwen-family models (other families use other parsers; see the vLLM docs). Without them
  vLLM rejects requests that include tools, and Kubrick falls back to the text protocol.
- `--max-model-len` sets the context window; Kubrick reads it from `/v1/models`
  automatically.
- Base URL: `http://HOST:8000/v1`.

### llama.cpp

```bash
llama-server -m model.gguf --host 0.0.0.0 --port 8080 -c 32768 --jinja
```

- `--jinja` enables the model's chat template, which llama.cpp needs for tool calling.
- `-c` sets the context size; llama.cpp doesn't report it, so also set
  `/config context_window 32768`.
- Base URL: `http://HOST:8080/v1`.

### LM Studio

Start the local server from the Developer tab (enable "Serve on Local Network" to reach it
from another machine). Base URL: `http://HOST:1234/v1`. Set the model's context length when
loading it, and mirror it with `/config context_window`.

### Serving from a Windows machine to Linux/macOS

If the GPU box runs Windows (e.g. a 4090 desktop) and Kubrick runs elsewhere:

1. Bind the server to `0.0.0.0` (`OLLAMA_HOST=0.0.0.0` as a user or system environment
   variable for Ollama, `--host 0.0.0.0` for vLLM / llama.cpp, "Serve on Local Network" in
   LM Studio).
2. Add a Windows Firewall inbound rule for the port, e.g. in an admin PowerShell:
   `New-NetFirewallRule -DisplayName "Ollama" -Direction Inbound -Protocol TCP -LocalPort 11434 -Action Allow`
3. If the server runs in WSL2 or Docker Desktop, publish the port (`docker run -p 8000:8000 ...`).
   WSL2 doesn't expose its ports on the LAN by default; use mirrored networking
   (`networkingMode=mirrored` in `.wslconfig`) or a `netsh interface portproxy` rule.
4. Check from the client: `curl http://WINDOWS-HOST:11434/v1/models`.

### Tool calling modes

`tool_calling` (config key or `--tool-calling`):

- `auto` (default): use native tool calling. If the server rejects tool definitions (for
  example Ollama's "does not support tools", or vLLM without a tool parser), Kubrick switches
  to the text protocol for the rest of the session and tells you.
- `native`: always send native tools; a rejection is an error.
- `text`: never send native tools. The tools are described in the system prompt and the model
  writes fenced `tool_call` JSON blocks, which Kubrick parses. The conversation is sent as
  plain user/assistant text.

Kubrick also handles common local-server quirks:

- **Unparsed tool calls**: if a model prints Hermes/Qwen-style
  `<tool_call>{"name": ..., "arguments": ...}</tool_call>` text because the server has no
  tool parser, Kubrick recovers the calls.
- **Reasoning**: `reasoning_content` / `reasoning` fields and inline `<think>...</think>`
  blocks are shown dimmed as thinking, not mixed into the answer (`show_thinking` turns this
  off).
- Servers that report `finish_reason: "stop"` alongside tool calls, omit tool-call indexes, or
  reject `stream_options` are handled.

---

## Anthropic

| Config key | Default | Meaning |
| --- | --- | --- |
| `anthropic_api_key` | (required) | env `ANTHROPIC_API_KEY`, or `kubrick auth login anthropic` |
| `anthropic_model` | `claude-opus-5-5` | Model ID |
| `anthropic_base_url` | `https://api.anthropic.com` | Change for an API gateway or proxy |
| `anthropic_effort` | `high` | `low`, `medium`, `high`, `xhigh`, `max`; only sent to models that support effort |

```json
{
  "provider": "anthropic",
  "anthropic_model": "claude-sonnet-5-5",
  "anthropic_effort": "medium"
}
```

- Current models (Claude 4.6 and later) run with adaptive thinking; summarized reasoning
  shows dimmed while the model works. Thinking blocks are passed back unchanged between tool
  calls, as the API requires.
- Prompt caching is enabled on every request, which makes long agent sessions much cheaper.
- On `claude-opus-5-5`, `claude-opus-5`, `claude-sonnet-5-5`, and `claude-fable-5-1`,
  requests to `api.anthropic.com` opt into server-side refusal fallback: if the model's
  safety classifier declines a request, the API retries it on a fallback model. A refusal
  that still stands ends the turn with a message.
- Rate limits and overloads (429/5xx/529) are retried automatically.

## OpenAI

| Config key | Default | Meaning |
| --- | --- | --- |
| `openai_api_key` | (required) | env `OPENAI_API_KEY`, or `kubrick auth login openai` |
| `openai_model` | `gpt-5` | Model ID |
| `openai_base_url` | `https://api.openai.com/v1` | Change for a proxy or gateway |

```json
{ "provider": "openai", "openai_model": "gpt-5" }
```

Kubrick uses OpenAI's Responses API, which current reasoning models (gpt-6 and later)
require for tool use, and passes the model's encrypted reasoning back between steps. If
`openai_base_url` points at a gateway without `/responses`, it falls back to Chat
Completions automatically.

## Amazon Bedrock

Uses the Bedrock **Converse** streaming API on `bedrock-runtime`, so any Bedrock model with
tool use works: Claude, gpt-oss, Nova, Llama 3.3/4, Mistral/Devstral, Qwen, DeepSeek, Kimi,
MiniMax, Nemotron, Grok, and others, in commercial regions and GovCloud. Models without tool
support (e.g. Llama 3 8B/70B) fall back to the text tool protocol automatically. Requires
`pip install 'kubrick-cli[bedrock]'`.

| Config key | Default | Meaning |
| --- | --- | --- |
| `bedrock_model` | (required) | Model ID or inference profile ID |
| `bedrock_region` | blank | AWS region; blank uses the credentials' `AWS_REGION` or the profile's region |
| `bedrock_profile` | blank | Named AWS profile (wins over the other sources) |
| `bedrock_credentials_file` | blank | `.env`-style file with `AWS_ACCESS_KEY_ID=...` lines |

### Credentials

`kubrick setup` asks how you get AWS credentials. Kubrick uses the first of these that is
configured:

1. **An AWS profile** (`bedrock_profile`): `~/.aws/credentials`, SSO
   (`aws sso login --profile work`), or `credential_process`.
2. **A `.env` file** (`bedrock_credentials_file`): `KEY=VALUE` or `export KEY=VALUE` lines
   (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, optionally
   `AWS_REGION` and an expiry such as `AWS_TOKEN_EXPIRATION`). Keep it `chmod 600`.
3. **Pasted credentials**: `kubrick auth login bedrock` or `/login` reads the same lines
   from a hidden paste and keeps them in Kubrick's encrypted credential store.
4. **The default AWS chain**: `AWS_*` environment variables, instance roles, or a Bedrock
   API key in `AWS_BEARER_TOKEN_BEDROCK`.

For **temporary keys** (e.g. 8-hour keys from a company portal): when they expire, Kubrick
first re-reads the file or profile, then asks you to paste new ones, and retries the
request; nothing is lost. If the block includes an expiry, Kubrick shows it at startup and
asks for new keys before a request would fail. Pasted keys go back into the `.env` file if
you use one, otherwise into the encrypted store.

**Bedrock API keys** (bearer tokens) work too: put `AWS_BEARER_TOKEN_BEDROCK=...` in the
paste or file. Short-term keys last up to 12 hours; AWS recommends long-term keys only for
exploration.

### Models

- Many newer models can only be called through a cross-region inference profile
  (`us.`, `us-gov.`, `eu.`, `apac.` + model ID). If you give the bare model ID, Kubrick
  switches to the profile automatically.
- "Not available for this account" means the AWS account hasn't been granted that model.
  Request it in the Bedrock console's model catalog (Anthropic models need a one-time
  use-case form; some need an AWS Marketplace subscription).
- IAM needs `bedrock:InvokeModel` and `bedrock:InvokeModelWithResponseStream`, plus
  `bedrock:ListFoundationModels` / `ListInferenceProfiles` for the model list.
- Throttling is retried automatically.

### OpenAI-compatible endpoints (runtime and mantle)

Bedrock also serves the OpenAI Chat Completions API. To use it, choose **Local model server
→ Something else** with a Bedrock API key as the API key:

| Endpoint | Base URL | Notes |
| --- | --- | --- |
| `bedrock-runtime` | `https://bedrock-runtime.REGION.amazonaws.com/openai/v1` | No model list; type the model ID (`openai.gpt-oss-120b-1:0`) |
| `bedrock-mantle` | `https://bedrock-mantle.REGION.api.aws/v1` | Lists its models; IDs without version suffix (`openai.gpt-oss-120b`) |

The native `bedrock` provider is usually the better choice: it accepts AWS keys directly
(no API key needed), supports more models, and handles expiring credentials.

## Triton

Kubrick speaks Triton's HTTP `generate_stream` endpoint with a JSON chunk protocol. Triton
models get tools through the text protocol. See [TRITON.md](TRITON.md) for the model
contract and a working example model.

| Config key | Default |
| --- | --- |
| `triton_url` | `localhost:8000` |
| `triton_model` | `llm_decoupled` |

Environment overrides: `KUBRICK_TRITON_URL`, `KUBRICK_TRITON_MODEL`.

---

## Adding a provider

1. Create `kubrick_cli/providers/<name>_provider.py` with a class that inherits
   `ProviderAdapter` (`kubrick_cli/providers/base.py`).
2. Set `METADATA = ProviderMetadata(name=..., display_name=..., description=...,
   config_fields=[...])`. Each field has `key`, `label`, `type` (`text`, `url`, `model`, or
   `secret`), and optionally `default`, `required`, `env` (environment variables checked for
   secrets), `help_text`, `choices` (`[(value, description), ...]`, shown as a menu), and
   `advanced` (not asked in the wizard; set with `/config`). The wizard offers a `model`
   field's values from `list_models()`. Secret fields are stored in the credential store, never in
   `config.json`.
3. Constructor parameters are filled from fields whose key equals the parameter name or ends
   with `_<parameter>` (`myprov_api_key` → `api_key`).
4. Implement `stream_chat(messages, tools=None, options=None)`. It receives the
   provider-neutral conversation (see `kubrick_cli/messages.py`) and yields `TextDelta`,
   `ThinkingDelta`, and `ToolCallEvent` objects, then exactly one `MessageDone` (stop reason,
   usage, and optional `raw` provider-native content to replay on later turns). Raise
   `ProviderError` with a readable message on failure, and `ToolsNotSupportedError` if the
   backend rejects tool definitions.
5. Implement the `provider_name` and `model_name` properties. Optionally override
   `is_healthy`, `list_models`, and `context_window`, and set
   `supports_native_tools = False` to use the text protocol.

The provider is discovered automatically and appears in the setup wizard.
