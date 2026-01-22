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

AI-assisted coding CLI tool supporting local LLMs via Triton, OpenAI, and Anthropic.

## Installation

### PyPI

```bash
pip install kubrick-cli
```

### Docker

Run using the wrapper script (handles file permissions automatically):

```bash
curl -fsSL https://raw.githubusercontent.com/rcland12/kubrick-cli/master/scripts/install-kubrick-docker.sh | sh
kubrick-docker
```

Or run manually with `docker run` (include `--user $(id -u):$(id -g)` to prevent root-owned files):

```bash
docker run --rm -it \
  --network host \
  --user $(id -u):$(id -g) \
  -v ${HOME}:/home/kubrick \
  -v ${PWD}:/workspace \
  rcland12/kubrick-cli
```

See [DOCKER.md](https://github.com/rcland12/kubrick-cli/blob/master/docs/DOCKER.md) for detailed setup and troubleshooting.

## Quick Start

```bash
# Start Kubrick (runs setup wizard on first launch)
kubrick

# View available commands
You: /help
```

## Example

```
You: Create a Python function to calculate fibonacci numbers with memoization

Assistant: I'll create a fibonacci function with memoization.

Tool: write_file
File: fibonacci.py

✓ Created fibonacci.py with memoized fibonacci function
```

## Requirements

- Python 3.8+
- LLM Provider: Triton Inference Server (default), OpenAI API, or Anthropic API

## Features

- Multi-provider support (Triton, OpenAI, Anthropic)
- Automatic file operations (read, write, edit)
- Code search with glob patterns and grep
- Bash command execution
- Real-time streaming responses
- Automatic context management
- Conversation history with persistence
- In-session configuration

## Documentation

- [WIKI.md](https://github.com/rcland12/kubrick-cli/blob/master/docs/WIKI.md) - Complete guide, commands, and configuration
- [PROVIDERS.md](https://github.com/rcland12/kubrick-cli/blob/master/docs/PROVIDERS.md) - Multi-provider setup
- [DOCKER.md](https://github.com/rcland12/kubrick-cli/blob/master/docs/DOCKER.md) - Docker usage and troubleshooting
- [TRITON.md](https://github.com/rcland12/kubrick-cli/blob/master/docs/TRITON.md) - Triton backend setup
- [CONTEXT_MANAGEMENT_QUICKSTART.md](https://github.com/rcland12/kubrick-cli/blob/master/CONTEXT_MANAGEMENT_QUICKSTART.md) - Context window configuration
- [TESTING.md](https://github.com/rcland12/kubrick-cli/blob/master/docs/TESTING.md) - Development and testing

## License

MIT License - See [LICENSE](LICENSE)
