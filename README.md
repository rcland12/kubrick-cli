# Kubrick CLI

[![CI](https://github.com/rcland12/kubrick-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/rcland12/kubrick-cli/actions/workflows/ci.yml)
[![CD](https://github.com/rcland12/kubrick-cli/actions/workflows/cd.yml/badge.svg)](https://github.com/rcland12/kubrick-cli/actions/workflows/cd.yml)
[![Security](https://github.com/rcland12/kubrick-cli/actions/workflows/security.yml/badge.svg)](https://github.com/rcland12/kubrick-cli/actions/workflows/security.yml)
[![PyPI version](https://badge.fury.io/py/kubrick-cli.svg)](https://badge.fury.io/py/kubrick-cli)
[![Python Versions](https://img.shields.io/pypi/pyversions/kubrick-cli.svg)](https://pypi.org/project/kubrick-cli/)
[![Downloads](https://pepy.tech/badge/kubrick-cli)](https://pepy.tech/project/kubrick-cli)
[![Docker Pulls](https://img.shields.io/docker/pulls/rcland12/kubrick-cli.svg)](https://hub.docker.com/r/rcland12/kubrick-cli)
[![Docker Image Size](https://img.shields.io/docker/image-size/rcland12/kubrick-cli/latest.svg)](https://hub.docker.com/r/rcland12/kubrick-cli)
[![codecov](https://codecov.io/gh/rcland12/kubrick-cli/branch/master/graph/badge.svg)](https://codecov.io/gh/rcland12/kubrick-cli)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/rcland12/kubrick-cli/badge)](https://securityscorecards.dev/viewer/?uri=github.com/rcland12/kubrick-cli)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

An agentic coding CLI in the spirit of Claude Code — but provider-agnostic and built to work
well with **local models**. Kubrick reads and edits your code, runs commands, and iterates until
the task is done, using native tool calling on Ollama, vLLM, llama.cpp, LM Studio, Anthropic,
OpenAI, and Amazon Bedrock (Triton is supported with a text-based tool protocol).

## Installation

```bash
pip install kubrick-cli                 # core (local servers, Anthropic, OpenAI, Triton)
pip install 'kubrick-cli[bedrock]'      # + Amazon Bedrock (boto3)
pip install 'kubrick-cli[keyring]'      # + store API keys in the OS keychain
pip install 'kubrick-cli[all]'          # everything
```

Requires Python 3.9+. A Docker image is also available — see [DOCKER.md](docs/DOCKER.md).
`uv tool install kubrick-cli` or `pipx install kubrick-cli` keeps it in its own environment.

**Updating:** `kubrick update` (or `/update` in a session) checks PyPI and runs the right
upgrade for how Kubrick was installed: `uv tool upgrade`, `pipx upgrade`, or pip in its
virtualenv. Docker and source checkouts get the command to run instead. `kubrick update
--check` only reports. Kubrick also checks once a day and mentions new releases at startup;
turn that off with `/config check_for_updates false`.

## Quick start

Run `kubrick` and the setup wizard walks you through choosing a provider. Or configure it
directly:

**Local model (Ollama, vLLM, llama.cpp, LM Studio)** — any OpenAI-compatible server:

```bash
# On the GPU box (Ollama example): serve on the LAN with a usable context window
OLLAMA_HOST=0.0.0.0 OLLAMA_CONTEXT_LENGTH=32768 ollama serve

# On your machine
kubrick setup        # "Local model server" > Ollama > type gpu-box:11434 > pick a model
kubrick
```

**Anthropic**

```bash
kubrick auth login anthropic             # stored encrypted (or in the OS keychain)
kubrick --provider anthropic             # default model: claude-opus-5-5
```

**OpenAI**

```bash
export OPENAI_API_KEY=...                # env vars work too and take precedence
kubrick --provider openai                # default model: gpt-5
```

**Amazon Bedrock** — uses your normal AWS credentials (profiles, SSO); Kubrick stores none:

```bash
aws sso login --profile work
kubrick setup        # choose "Amazon Bedrock", enter a model / inference profile ID
```

**Triton Inference Server** — see [TRITON.md](docs/TRITON.md).

## Usage

```
> fix the failing test in tests/test_parser.py

● Bash(pytest -q tests/test_parser.py)
  └ Exit code: 1 ...
● Read(src/parser.py)
  └ Read 212 lines
● Edit(src/parser.py)
  └ Edited src/parser.py (1 replacement(s))
● Bash(pytest -q tests/test_parser.py)
  └ Exit code: 0

Fixed the off-by-one in parse_range (src/parser.py:88); the test now passes.
```

Kubrick asks before editing files or running commands (read-only commands like `git status`
run without asking). Pick "Yes, and allow ..." (or press `a`) to allow that kind of action for
the rest of the session, or start with `--permission-mode accept_edits`. `/plan` switches to a
read-only planning mode.

Type `/` to open the command menu. It filters as you type (`/pr` shows `/provider`); press
↑/↓ to pick one, Tab to complete, Esc to close, or just keep typing and Enter sends what you
typed. `/provider`, `/model` and `/permissions` without an argument open a picker.

**Terminals.** Kubrick works in any terminal, including tmux/screen, Windows Terminal, and
Emacs (`vterm`, `eat`, `ansi-term`; in `M-x shell` and other dumb terminals menus become
numbered prompts). Set `KUBRICK_ASCII=1` if your font is missing symbols,
`KUBRICK_SIMPLE_UI=1` to always use numbered prompts, `NO_COLOR=1` to drop color, and
`/config editing_mode vi` for vi key bindings.

Non-interactive / scripting:

```bash
kubrick -p "summarize what this repo does"
git diff | kubrick -p "review this diff for bugs"
kubrick -p "update the changelog" --permission-mode accept_edits
kubrick -c                      # continue the most recent conversation
```

Put project-specific instructions (build/test commands, conventions) in a `KUBRICK.md` at the
repo root — `CLAUDE.md` and `AGENTS.md` are read too. `/init` generates one for you.

## Development

```bash
make dev        # .venv with an editable install + dev tools (needs uv)
make run        # run it against a throwaway playground project, with its own ~/.kubrick
make test       # tests; `make lint` runs the CI checks
make sandbox    # run it in Docker: only the project is visible, installs stay inside
make reset      # delete .venv and .dev/ (everything above lives there)
```

`make run DIR=~/src/project` points it at a real project; `make reset-home` re-runs the setup
wizard. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Features

- Native tool calling on every provider, with automatic fallback to a text protocol for models
  or servers that don't support tools
- Claude Code-style permission modes, plan mode, and project instruction files
- Local-model friendly: context-window auto-detection (vLLM, Ollama), reasoning/`<think>`
  display, recovery of unparsed `<tool_call>` output
- Automatic context compaction, conversation history (`-c`, `-r`, `/list`, `/load`)
- API keys kept out of config files: env vars, OS keychain, or a machine-bound encrypted store
- Streaming output, parallel read-only tools, ripgrep-backed search

## Documentation

- [WIKI.md](docs/WIKI.md) — commands, flags, permissions, configuration, troubleshooting
- [PROVIDERS.md](docs/PROVIDERS.md) — setting up each provider and local servers
- [SECURITY.md](docs/SECURITY.md) — credential storage and security policy
- [DOCKER.md](docs/DOCKER.md) — running in Docker
- [TRITON.md](docs/TRITON.md) — Triton backend setup
- [TESTING.md](docs/TESTING.md) — development and testing
- [CICD.md](docs/CICD.md) — CI, releases, and publishing

## License

MIT License - See [LICENSE](LICENSE)
