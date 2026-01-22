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

An AI-assisted coding CLI tool powered by your own Triton LLM backend. Like Claude Code, but self-hosted.

## Installation

### PyPI (Recommended)

Install the latest stable release from PyPI:

```bash
pip install kubrick-cli
kubrick
```

### Development Installation

For contributing or testing the latest changes:

```bash
git clone https://github.com/rcland12/kubrick-cli.git
cd kubrick-cli
pip install -e ".[dev]"
kubrick
```

### Docker

#### Understanding Docker File Permissions

**CRITICAL:** When using Docker, Kubrick creates files in your project. Without proper configuration, these files will be owned by root, causing permission issues.

**The Solution:**
- **Option 1 (Recommended):** Use the `kubrick-docker` wrapper - handles permissions automatically
- **Option 2:** Use Docker Compose with exported UID/GID environment variables
- **Option 3:** Include `--user $(id -u):$(id -g)` in every Docker command

#### Quick Install (Recommended)

Install the `kubrick-docker` wrapper for easy usage:

```bash
# Install from GitHub (installs to ~/.local/bin/kubrick-docker)
curl -fsSL https://raw.githubusercontent.com/rcland12/kubrick-cli/master/scripts/install-kubrick-docker.sh | sh

# Add to PATH if needed (add to ~/.bashrc or ~/.zshrc)
export PATH="$HOME/.local/bin:$PATH"

# Run from any project directory
cd /path/to/your/project
kubrick-docker
```

**Benefits:**
- ✅ Automatically handles UID/GID (no configuration needed)
- ✅ Smart image fallback (Docker Hub → GHCR → Local build)
- ✅ Simple command from any directory
- ✅ Files always owned by you, never root

**Uninstall:**
```bash
curl -fsSL https://raw.githubusercontent.com/rcland12/kubrick-cli/master/scripts/uninstall-kubrick-docker.sh | sh
```

#### Docker Compose

Use Docker Compose for a convenient alias-style workflow.

**Setup (Required):** Export UID/GID in your shell config (`~/.bashrc` or `~/.zshrc`):

```bash
export UID=$(id -u)
export GID=$(id -g)
```

**Usage:**

```bash
cd /path/to/your/project
docker compose -f /path/to/kubrick-cli/docker-compose.yaml run --rm kubrick
```

#### Manual Docker Commands

**IMPORTANT:** Always include `--user $(id -u):$(id -g)` to avoid file permission issues!

```bash
cd /path/to/your/project

# From Docker Hub
docker run --rm -it \
  --network host \
  --user $(id -u):$(id -g) \
  -v ${HOME}:/home/kubrick \
  -v ${PWD}:/workspace \
  -v /etc/localtime:/etc/localtime:ro \
  -v /etc/timezone:/etc/timezone:ro \
  rcland12/kubrick-cli

# From GitHub Container Registry
docker run --rm -it \
  --network host \
  --user $(id -u):$(id -g) \
  -v ${HOME}:/home/kubrick \
  -v ${PWD}:/workspace \
  -v /etc/localtime:/etc/localtime:ro \
  -v /etc/timezone:/etc/timezone:ro \
  ghcr.io/rcland12/kubrick-cli
```

**Why `--user` is required:**
- Without it, Docker runs as root and creates root-owned files
- With it, files are owned by you and compatible with pip installation
- The container uses `chmod 1777` on directories (same as VS Code Dev Containers)

See **[DOCKER.md](https://github.com/rcland12/kubrick-cli/blob/master/docs/DOCKER.md)** for detailed Docker usage, UID/GID configuration, and troubleshooting.

## Quick Start

```bash
# Basic usage
kubrick

# Custom Triton server
kubrick --triton-url my-server:8000

# Load previous conversation
kubrick --load 20240118_143022
```

## Requirements

- Python 3.8+
- LLM Provider (choose one):
  - **Triton Inference Server** with streaming LLM model (default: `http://localhost:8000`)
  - **OpenAI API** (GPT-4, GPT-3.5-turbo, etc.)
  - **Anthropic API** (Claude models)

## Documentation

- **[WIKI.md](https://github.com/rcland12/kubrick-cli/blob/master/docs/WIKI.md)** - Complete features, commands, and usage guide
- **[PROVIDERS.md](https://github.com/rcland12/kubrick-cli/blob/master/docs/PROVIDERS.md)** - Multi-provider setup (Triton, OpenAI, Anthropic)
- **[CONTEXT_MANAGEMENT_QUICKSTART.md](https://github.com/rcland12/kubrick-cli/blob/master/CONTEXT_MANAGEMENT_QUICKSTART.md)** - Context window configuration and troubleshooting
- **[TRITON.md](https://github.com/rcland12/kubrick-cli/blob/master/docs/TRITON.md)** - Triton backend setup and requirements
- **[TESTING.md](https://github.com/rcland12/kubrick-cli/blob/master/docs/TESTING.md)** - Testing guide and CI/CD setup
- **[DOCKER.md](https://github.com/rcland12/kubrick-cli/blob/master/docs/DOCKER.md)** - Docker setup and troubleshooting

## Key Features

### 🎯 Intelligent Context Management
Kubrick automatically manages conversation length to prevent context overflow and hallucinations:
- **Automatic trimming** at 75% context usage
- **LLM-based summarization** at 85% usage
- **Smart token reservation** for output
- **Provider-optimized defaults** (OpenAI: 128k, Claude: 200k, Triton: configurable)

**For Triton/vLLM users**: Set your context window to match your model:
```bash
kubrick
/config model_max_context_override 16384  # Match your --max-model-len
/context  # Check status
```

See [CONTEXT_MANAGEMENT_QUICKSTART.md](CONTEXT_MANAGEMENT_QUICKSTART.md) for details.

### 🔧 In-Session Commands

Monitor and configure Kubrick while running:
```bash
/context   # Show context usage and limits
/config    # View all configuration
/help      # Show all available commands
```

## Configuration

Config stored at `~/.kubrick/config.json`. Override with environment variables or in-session commands:

```bash
# Environment variables
export TRITON_URL=localhost:8000
export TRITON_MODEL_NAME=llm_decoupled

# In-session configuration
/config model_max_context_override 16384
/config max_output_tokens 2048
```

See [docs/WIKI.md](docs/WIKI.md) for complete configuration reference.

## Development

### Install Development Dependencies

```bash
pip install -e ".[dev]"
```

### Run Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=kubrick_cli --cov-report=term-missing

# Run specific test file
pytest tests/test_tool_executor.py -v
```

See [TESTING.md](https://github.com/rcland12/kubrick-cli/blob/master/docs/TESTING.md) for detailed testing documentation.

### Code Quality

```bash
# Format code
black kubrick_cli tests

# Check linting
flake8 kubrick_cli
```

## License

MIT License - See [LICENSE](LICENSE)
