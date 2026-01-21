# Kubrick CLI

An AI-assisted coding CLI tool powered by your own Triton LLM backend. Like Claude Code, but self-hosted.

## Installation

### Local Installation

```bash
pip install -e .
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
- **[TRITON.md](https://github.com/rcland12/kubrick-cli/blob/master/docs/TRITON.md)** - Triton backend setup and requirements
- **[TESTING.md](https://github.com/rcland12/kubrick-cli/blob/master/docs/TESTING.md)** - Testing guide and CI/CD setup
- **[DOCKER.md](https://github.com/rcland12/kubrick-cli/blob/master/docs/DOCKER.md)** - Docker setup and troubleshooting

## Configuration

Config stored at `~/.kubrick/config.json`. Override with environment variables:

```bash
export TRITON_URL=localhost:8000
export TRITON_MODEL_NAME=llm_decoupled
```

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
