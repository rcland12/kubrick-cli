# Kubrick CLI

An AI-assisted coding CLI tool powered by your own Triton LLM backend. Like Claude Code, but self-hosted.

## Installation

### Local Installation

```bash
pip install -e .
kubrick
```

### Docker

Available from Docker Hub or GitHub Container Registry:

```bash
cd /path/to/your/project

# From Docker Hub
docker run --rm -it \
  --network host \
  -v ${HOME}:/home/kubrick \
  -v ${PWD}:/workspace \
  -v /etc/localtime:/etc/localtime:ro \
  -v /etc/timezone:/etc/timezone:ro \
  rcland12/kubrick-cli

# From GitHub Container Registry
docker run --rm -it \
  --network host \
  -v ${HOME}:/home/kubrick \
  -v ${PWD}:/workspace \
  -v /etc/localtime:/etc/localtime:ro \
  -v /etc/timezone:/etc/timezone:ro \
  ghcr.io/rcland12/kubrick-cli
```

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
