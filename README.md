# Kubrick CLI

An AI-assisted coding CLI tool powered by your own Triton LLM backend. Like Claude Code, but self-hosted.

## Installation

### Local Installation

```bash
pip install -e .
kubrick
```

### Docker

```bash
cd /path/to/your/project
docker run --rm -it \
  --network host \
  -v ~/.kubrick:/kubrick \
  -v $(pwd):/workspace \
  rcland12/kubrick-cli
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
- Triton Inference Server with streaming LLM model
- Default endpoint: `http://localhost:8000`
- Default model: `llm_decoupled`

## Documentation

- **[WIKI.md](docs/WIKI.md)** - Complete features, commands, and usage guide
- **[TRITON.md](docs/TRITON.md)** - Triton backend setup and requirements
- **[DOCKER.md](docs/DOCKER.md)** - Docker setup and troubleshooting

## Configuration

Config stored at `~/.kubrick/config.json`. Override with environment variables:

```bash
export TRITON_URL=localhost:8000
export TRITON_MODEL_NAME=llm_decoupled
```

## License

MIT License - See [LICENSE](LICENSE)
