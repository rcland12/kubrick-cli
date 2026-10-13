# Kubrick CLI Guide

Kubrick is an agentic coding assistant for the terminal. You describe a task; the model reads
files, searches, edits, and runs commands through tools, and keeps going until it replies
without calling a tool. Every provider (local servers, Anthropic, OpenAI, Bedrock, Triton) uses
the same loop, tools, and permission rules.

- [Starting Kubrick](#starting-kubrick)
- [Slash commands](#slash-commands)
- [Tools](#tools)
- [Permissions](#permissions)
- [Plan mode](#plan-mode)
- [Project instructions (KUBRICK.md)](#project-instructions-kubrickmd)
- [Context management](#context-management)
- [Conversations](#conversations)
- [Configuration reference](#configuration-reference)
- [Credentials](#credentials)
- [Troubleshooting](#troubleshooting)

Provider setup is covered in [PROVIDERS.md](PROVIDERS.md).

## Starting Kubrick

```bash
kubrick                                   # interactive session in the current directory
kubrick "fix the failing test"            # interactive, with a first message
kubrick -p "summarize this repo"          # answer once, print, exit
git diff | kubrick -p "review this diff"  # piped input is appended to the prompt
kubrick -c                                # continue the most recent conversation
```

### Flags

| Flag | Meaning |
| --- | --- |
| `prompt` (positional) | Initial message |
| `-p`, `--print` | Non-interactive: run the prompt, print the answer to stdout (status goes to stderr), exit. Exit code 0 on success, 1 on error. Used automatically when there is no terminal. |
| `-c`, `--continue` | Continue the most recent saved conversation |
| `-r`, `--resume`, `--load ID` | Resume a conversation by ID or JSON file path |
| `--provider NAME` | Provider for this session (`openai_compatible`, `anthropic`, `openai`, `bedrock`, `triton`) |
| `-m`, `--model NAME` | Model for this session |
| `-C`, `--working-dir DIR` | Directory the agent works in (default: current) |
| `--permission-mode MODE` | `default`, `accept_edits`, `plan`, or `bypass` for this session |
| `--tool-calling MODE` | `auto`, `native`, or `text` |
| `--max-iterations N` | Model calls allowed per turn |
| `--version` | Print the version |

Session flags are never written to `config.json`.

### Subcommands

| Command | Meaning |
| --- | --- |
| `kubrick setup` | Run the setup wizard (choose a provider, enter settings and keys) |
| `kubrick auth login [provider]` | Prompt for and store a provider's API key (default: configured provider). For `bedrock`, paste `AWS_...=` lines |
| `kubrick auth logout [provider]` | Delete stored keys (all providers if none given) |
| `kubrick auth status` | Show where each key comes from: env var, store, expired, or not set |
| `kubrick update [--check] [--yes]` | Check PyPI and upgrade the way Kubrick was installed (uv tool, pipx, pip); `--check` only reports |

### Keys

- **Enter** submits; **Alt+Enter** (or Esc then Enter) or **Ctrl+J** inserts a newline
- **Ctrl+C** interrupts the agent mid-response or mid-tool; at the prompt, press twice to quit
- **Ctrl+D** or `exit` saves and quits
- Input history is saved in `~/.kubrick/history`

The status bar shows the provider and model, the permission mode, context usage, tool and file
counts, and the working directory.

## Slash commands

| Command | Meaning |
| --- | --- |
| `/help` | List commands and keys. Typing `/` also opens a menu of commands that filters as you type (↑/↓ to pick, Tab to complete, Esc to close) |
| `/clear` | Save and start a new conversation |
| `/compact [focus]` | Summarize the conversation now, optionally telling the summary what to emphasize |
| `/context` | Context window size, estimated usage, compaction threshold, last reported token usage |
| `/model [name]` | Pick from the models the server lists, or switch to `name`, for this session |
| `/provider [name]` | Pick or switch the provider for this session; offers to set up one that isn't configured |
| `/setup` | Run the setup wizard and switch to the result |
| `/login` | Enter new credentials for the current provider (for Bedrock: paste AWS keys) |
| `/plan` | Toggle plan mode |
| `/permissions [mode]` | Show the session's allow-rules and pick a mode, or set `mode` |
| `/init` | Ask the agent to write a `KUBRICK.md` for this project |
| `/status` | Provider, model, tool-calling mode, credential store, token totals |
| `/save` | Save the conversation now (conversations also auto-save after every turn) |
| `/list [N]` | List saved conversations (default 20) |
| `/load <#\|id>` | Resume a conversation by its `/list` number or ID |
| `/delete <id>` | Delete a saved conversation |
| `/config` | Show every setting |
| `/config KEY` | Show one setting |
| `/config KEY VALUE` | Save a setting to `config.json` (VALUE is parsed as JSON when possible). Provider settings take effect on restart. API keys are rejected here; use `kubrick auth login`. |
| `/debug prompt` | Show the system prompt |
| `/debug messages` | Show the last 10 messages as JSON |
| `/update` | Check for a new release and install it (restart afterwards) |
| `/exit` | Save and quit (also `exit`, `quit`, Ctrl+D) |
| `exit`, `quit` | Save and quit |

## Tools

| Tool | What it does |
| --- | --- |
| `read_file` | Reads a text file with line numbers; up to 2000 lines by default, with `offset`/`limit` for paging. Refuses binary files and files over `max_file_size_mb`. |
| `write_file` | Creates or overwrites a file, creating parent directories |
| `edit_file` | Replaces an exact string. It must match exactly once unless `replace_all` is set. |
| `list_files` | Glob search (e.g. `src/**/*.py`), max 500 results; skips `.git`, `node_modules`, virtualenvs, build output |
| `search_files` | Regex search over file contents, using ripgrep when installed; optional `file_pattern` and `case_insensitive` |
| `run_bash` | Runs a shell command in the working directory with stdin closed. Returns the exit code and output; times out after `tool_timeout_seconds` (max 600). |
| `create_directory` | Creates a directory |

Arguments are validated against each tool's schema before anything runs; invalid calls are
returned to the model as errors. Consecutive read-only calls run in parallel. Tool output over
`max_tool_result_chars` is truncated (head and tail kept).

## Permissions

Every tool call passes a permission check first.

| Mode | File reads | File edits | Shell commands |
| --- | --- | --- | --- |
| `default` | allowed in the working dir | ask | ask (read-only commands allowed) |
| `accept_edits` | allowed in the working dir | allowed in the working dir | ask (read-only commands allowed) |
| `plan` | allowed in the working dir | refused | read-only commands only |
| `bypass` | allowed | allowed | allowed (dangerous commands still ask) |

Rules that apply in every mode except `bypass`:

- **Outside the working directory**: reading or editing a file outside the working directory
  always asks, even in `accept_edits`.
- **Read-only commands run without asking**: `ls`, `cat`, `head`, `tail`, `wc`, `grep`, `rg`,
  `find` (without `-exec`/`-delete`), `tree`, `diff`, `git status/diff/log/show/ls-files/blame/rev-parse`,
  and similar. Pipelines and `&&` chains qualify only if every part is read-only and there are
  no redirections or `$(...)`.
- **Dangerous commands** (`rm -rf`, `sudo`, `chmod 777`, force-push, `curl | bash`, `mkfs`,
  `dd` to devices, ...) always show a warning and ask, including in `bypass` mode when
  someone is at the terminal.

When asked, answer:

- `y`: allow this once.
- `a`: allow it for the rest of the session. For edits, this allows all edits in the working
  directory. For commands, it allows the command's prefix: the first word (`pytest`), or the
  first two words for tools with subcommands (`git commit`, `npm test`, `docker build`, ...).
- `n`: deny. You can then type what the agent should do instead, and the agent continues with
  that guidance. Press Enter with nothing typed to stop the turn and get the prompt back.

In non-interactive runs (`-p`, no terminal), anything that would ask is denied and the model is
told to rerun with `--permission-mode accept_edits` or `bypass`.

## Plan mode

`/plan` (or `--permission-mode plan`) makes the agent read-only: it can read, search, and run
read-only commands, but edits and other commands are refused with a message telling the model
to present a plan. Ask for the plan, review it, then run `/plan` again to restore the previous
mode and let it make the changes.

## Project instructions (KUBRICK.md)

Kubrick adds instruction files to the system prompt at the start of each conversation:

- `~/.kubrick/KUBRICK.md`: your personal instructions for every project
- In the working directory and each parent directory, up to the repository root (the directory
  containing `.git`) or your home directory: the first of `KUBRICK.md`, `CLAUDE.md`, or
  `AGENTS.md` found in each directory. Files closer to the working directory take precedence.

Good contents: build/test/lint commands, architecture notes, conventions, things to avoid.
`/init` asks the agent to write one by analyzing the repo. Instructions are capped at 40,000
characters.

## Context management

The context window is resolved in this order:

1. `context_window` from config
2. What the backend reports: vLLM's `max_model_len`, Ollama's loaded `context_length`, or
   Anthropic's model `max_input_tokens`
3. Known model families (e.g. current Claude models 1M, `gpt-5` 400k), else a per-provider
   default (32,768 for local servers and Triton)

Token usage comes from provider-reported usage when available, plus an estimate for messages
added since. Before each model call, if usage exceeds `context_usage_threshold` (80%) of the
window minus the reserved output space, Kubrick **compacts**: older turns are replaced by a
model-written summary, and the most recent turns are kept verbatim. If there is only one long
turn, older tool outputs inside it are shortened instead. `/compact [focus]` does this on
demand; `/context` shows the numbers.

## Conversations

Conversations are saved after every turn to `~/.kubrick/conversations/<id>.json`, keeping the
`max_conversations` most recent. Resume with `kubrick -c` (most recent), `kubrick -r <id or path>`,
or `/list` then `/load <#>`. A resumed conversation gets a fresh system prompt for the current
directory.

## Configuration reference

Settings live in `~/.kubrick/config.json` (or `$KUBRICK_HOME/config.json`). Any setting can be
overridden by a `KUBRICK_<KEY>` environment variable (values parsed as JSON when possible) or
for one session by CLI flags. Provider-specific keys (`openai_compatible_base_url`,
`anthropic_model`, `bedrock_region`, ...) are listed in [PROVIDERS.md](PROVIDERS.md).

| Key | Default | Meaning |
| --- | --- | --- |
| `provider` | `openai_compatible` | Active provider |
| `max_iterations` | `50` | Model calls allowed per user turn; then Kubrick stops and you can say "continue" |
| `tool_calling` | `auto` | `auto` (native, falling back to text if the server rejects tools), `native`, `text` |
| `enable_parallel_tools` | `true` | Run consecutive read-only tool calls concurrently |
| `max_parallel_workers` | `4` | Thread pool size for parallel tools |
| `permission_mode` | `default` | `default`, `accept_edits`, `plan`, `bypass` |
| `tool_timeout_seconds` | `120` | Default `run_bash` timeout |
| `max_file_size_mb` | `10` | Largest file `read_file` will load |
| `credential_store` | `auto` | `auto` (OS keychain if available, else encrypted file), `keyring`, `file` |
| `credential_max_age_days` | `null` | If set, stored keys older than this are treated as missing (forces re-login) |
| `enable_context_management` | `true` | Track context usage and compact automatically |
| `context_window` | `null` | Context window in tokens; overrides what the backend reports |
| `context_usage_threshold` | `0.8` | Compact when this fraction of the usable window is in use |
| `max_output_tokens` | `null` | Max tokens per response; `null` uses the provider default |
| `max_tool_result_chars` | `30000` | Cap on each tool result added to the conversation |
| `show_thinking` | `true` | Show model reasoning (dimmed) while it works |
| `editing_mode` | `emacs` | Key bindings in the input box: `emacs` or `vi` |
| `check_for_updates` | `true` | Check PyPI once a day and mention new releases at startup |
| `auto_save_conversations` | `true` | Save conversations after each turn |
| `max_conversations` | `100` | Saved conversations to keep |

Settings from older versions that no longer apply are removed from `config.json` automatically.

## Credentials

API keys are never written to `config.json`. Each key resolves from its environment variable
(`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENAI_COMPATIBLE_API_KEY`) first, then the
credential store: the OS keychain when available (install `kubrick-cli[keyring]`), otherwise
`~/.kubrick/credentials.json` encrypted with a machine-bound key. If a required key is
missing in an interactive session, Kubrick asks for it and stores it. Bedrock uses the AWS
credential chain. Details: [SECURITY.md](SECURITY.md#credential-storage).

## Troubleshooting

**The local model ignores instructions, forgets tools, or behaves erratically.**
The context window is probably too small and prompts are being truncated. On Ollama, start the
server with `OLLAMA_CONTEXT_LENGTH=32768` (or more); on vLLM raise `--max-model-len`; on
llama.cpp raise `-c`. Then check `/context`, or set `/config context_window <tokens>` to match
the server. Kubrick warns at startup when the window is under 16k.

**"This model/server doesn't accept native tool definitions; switching to text-based tool
calling."** The server rejected `tools` (an Ollama model without tool support, or vLLM without
`--enable-auto-tool-choice --tool-call-parser ...`). Kubrick continues with the text protocol.
Enable tool calling on the server for better results, or set `tool_calling` to `text` to skip
the check.

**401 / authentication errors.** Run `kubrick auth status`. An exported `ANTHROPIC_API_KEY` /
`OPENAI_API_KEY` takes precedence over keys stored with `kubrick auth login`, so an old key in
your shell profile overrides a new stored one. Remove or update the export, or store the new
key with `kubrick auth login <provider>`.

**"unreadable (machine key changed)" or "expired" in `auth status`.** The machine key was
deleted, the store was copied from another machine, or `credential_max_age_days` passed. Run
`kubrick auth login <provider>`.

**Cannot reach the provider.** Check the URL (`host:port` is enough for local servers) with
`curl <base_url>/models`. For a server on another machine, make sure it listens on `0.0.0.0`
and the firewall allows the port (see [PROVIDERS.md](PROVIDERS.md#serving-from-a-windows-machine-to-linuxmacos)).

**Bedrock AccessDenied / expired token.** Enable the model in the Bedrock console, grant
`bedrock:InvokeModelWithResponseStream`, and for SSO run `aws sso login --profile <name>`.

**The agent stopped with "Stopped after N model calls".** It hit `max_iterations`; reply
"continue" or raise the limit.
