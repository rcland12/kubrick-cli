# Kubrick CLI - Complete Documentation

Complete guide to using Kubrick CLI for AI-assisted coding.

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [Provider Support](#provider-support)
- [Configuration](#configuration)
- [Available Tools](#available-tools)
- [Special Commands](#special-commands)
- [Conversation Management](#conversation-management)
- [Troubleshooting](#troubleshooting)
- [Example Sessions](#example-sessions)
- [Development](#development)

## Features

- 🤖 **AI-powered coding assistant** with natural conversation
- 🔌 **Multi-provider support** - Use Triton, OpenAI, or Anthropic
- 🛠️ **Robust tool calling** for automatic file operations and commands
- 📁 **File operations**: read, write, edit with pattern matching
- 🔍 **Code search** with glob patterns and grep-like functionality
- 💻 **Bash command integration** for running scripts and commands
- 🌊 **Real-time streaming responses** via HTTP (no external LLM libraries for Triton)
- 💾 **Automatic conversation persistence** with searchable history
- ⚙️ **Configuration management** with multiple override levels
- 📂 **Conversation history** saved in `~/.kubrick`
- 🔧 **Improved system prompts** with clear tool calling examples
- 🛡️ **Fallback parser** for resilient tool call detection
- 🐳 **Docker support** with working directory mounting
- ✅ **Comprehensive test suite** with 100+ unit tests

## Installation

### Option 1: Local Installation

Install from source:

```bash
cd /path/to/kubrick
pip install -e .
```

This installs the `kubrick` command globally.

**Dependencies:** Only `rich` and `prompt_toolkit` for the CLI interface. No external LLM libraries required!

### Option 2: Docker

Run in a container without installing anything. Available from Docker Hub or GitHub Container Registry.

#### Recommended: Use the kubrick-docker Wrapper

```bash
# Install wrapper (handles UID/GID automatically)
curl -fsSL https://raw.githubusercontent.com/rcland12/kubrick-cli/master/scripts/install-kubrick-docker.sh | sh

# Run from any project
cd /path/to/your/project
kubrick-docker
```

#### Or Use Docker Commands Directly

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

**Why `--user` is required:** Without it, files are created as root and you'll have permission issues. The wrapper script handles this automatically.

See [DOCKER.md](DOCKER.md) for complete Docker setup, UID/GID configuration, and troubleshooting.

## Usage

### Basic Commands

```bash
# Start in current directory (uses default provider from config)
kubrick

# Use Triton provider (default)
kubrick --triton-url my-server:8000 --triton-model llm_decoupled

# Use OpenAI provider
kubrick --provider openai --openai-model gpt-4

# Use Anthropic provider
kubrick --provider anthropic --anthropic-model claude-sonnet-4-5-20250929

# Set working directory
kubrick --working-dir /path/to/project

# Load previous conversation
kubrick --load 20240118_143022
```

See [PROVIDERS.md](PROVIDERS.md) for detailed multi-provider setup and configuration.

### Command-Line Options

#### Provider Selection

| Option       | Environment Variable | Description                                      |
| ------------ | -------------------- | ------------------------------------------------ |
| `--provider` | -                    | LLM provider: `triton`, `openai`, or `anthropic` |

#### Triton Provider Options

| Option           | Environment Variable | Description                                      |
| ---------------- | -------------------- | ------------------------------------------------ |
| `--triton-url`   | `TRITON_URL`         | Triton server HTTP URL (default: localhost:8000) |
| `--triton-model` | `TRITON_MODEL`       | Triton model name (default: llm_decoupled)       |

#### OpenAI Provider Options

| Option             | Environment Variable | Description                   |
| ------------------ | -------------------- | ----------------------------- |
| `--openai-api-key` | `OPENAI_API_KEY`     | OpenAI API key (required)     |
| `--openai-model`   | `OPENAI_MODEL`       | OpenAI model (default: gpt-4) |

#### Anthropic Provider Options

| Option                | Environment Variable | Description                                           |
| --------------------- | -------------------- | ----------------------------------------------------- |
| `--anthropic-api-key` | `ANTHROPIC_API_KEY`  | Anthropic API key (required)                          |
| `--anthropic-model`   | `ANTHROPIC_MODEL`    | Anthropic model (default: claude-sonnet-4-5-20250929) |

#### General Options

| Option          | Environment Variable | Description                                   |
| --------------- | -------------------- | --------------------------------------------- |
| `--working-dir` | -                    | Working directory for file operations         |
| `--load`        | -                    | Load previous conversation by ID or file path |

**Priority order:** CLI arguments > Environment variables > Config file > Defaults

## Provider Support

Kubrick supports multiple LLM providers, allowing you to use:

### Triton Inference Server (Default)

- **Self-hosted**: Run your own LLM models
- **No API costs**: Complete control and privacy
- **Streaming support**: Real-time responses via HTTP
- **Setup**: See [TRITON.md](TRITON.md) for Triton configuration

### OpenAI

- **Easy setup**: Just add your API key
- **Models**: GPT-4, GPT-3.5-turbo, and more
- **Quick start**: `kubrick --provider openai --openai-model gpt-4`

### Anthropic (Claude)

- **Claude models**: Claude Sonnet, Opus, etc.
- **High quality**: State-of-the-art language understanding
- **Quick start**: `kubrick --provider anthropic --anthropic-model claude-sonnet-4-5-20250929`

### Custom Providers

Want to add support for another LLM? See [PROVIDERS.md](PROVIDERS.md) for a guide on creating custom provider adapters. The system is designed to be plug-and-play - just drop a new provider file in and it's automatically discovered!

## Configuration

### Config File

Configuration is stored at `~/.kubrick/config.json`:

```json
{
  "provider": "triton",
  "triton_url": "localhost:8000",
  "triton_model": "llm_decoupled",
  "openai_api_key": null,
  "openai_model": "gpt-4",
  "anthropic_api_key": null,
  "anthropic_model": "claude-sonnet-4-5-20250929",
  "default_working_dir": null,
  "auto_save_conversations": true,
  "max_conversations": 100,
  "max_iterations": 15,
  "max_tools_per_turn": 5
}
```

### Environment Variables

Override config with environment variables:

```bash
# Triton provider
export TRITON_URL=my-server:8000
export TRITON_MODEL=llm_decoupled

# OpenAI provider
export OPENAI_API_KEY=sk-...
export OPENAI_MODEL=gpt-4

# Anthropic provider
export ANTHROPIC_API_KEY=sk-ant-...
export ANTHROPIC_MODEL=claude-sonnet-4-5-20250929

kubrick --provider openai
```

### In-Session Configuration

Update config while running:

```bash
You: /config triton_url myserver:8000
You: /config max_conversations 50
```

## Available Tools

The AI assistant can automatically use these tools:

### File Operations

- **read_file** - Read file contents

  ```json
  { "tool": "read_file", "parameters": { "file_path": "main.py" } }
  ```

- **write_file** - Create or overwrite files

  ```json
  {
    "tool": "write_file",
    "parameters": { "file_path": "test.py", "content": "..." }
  }
  ```

- **edit_file** - Replace text in files

  ```json
  {
    "tool": "edit_file",
    "parameters": {
      "file_path": "main.py",
      "old_text": "...",
      "new_text": "..."
    }
  }
  ```

- **create_directory** - Create directories
  ```json
  { "tool": "create_directory", "parameters": { "dir_path": "src/utils" } }
  ```

### Code Search

- **list_files** - Find files by pattern (glob)

  ```json
  { "tool": "list_files", "parameters": { "pattern": "**/*.py" } }
  ```

- **search_files** - Search for text in files (grep-like)
  ```json
  {
    "tool": "search_files",
    "parameters": { "pattern": "def main", "file_pattern": "*.py" }
  }
  ```

### Command Execution

- **run_bash** - Execute bash commands
  ```json
  { "tool": "run_bash", "parameters": { "command": "pytest tests/" } }
  ```

## Special Commands

Use these commands during a Kubrick session:

| Command             | Description                                                             |
| ------------------- | ----------------------------------------------------------------------- |
| `/save`             | Manually save the current conversation                                  |
| `/list [N]`         | List saved conversations (default: 20, shows numbered list)             |
| `/load <#\|ID>`     | Load a conversation by number (from /list) or ID                        |
| `/config`           | Show current configuration                                              |
| `/config KEY VALUE` | Update a configuration setting                                          |
| `/delete ID`        | Delete a saved conversation                                             |
| `/debug`            | Show debug information (conversation ID, message count, provider, etc.) |
| `/debug prompt`     | Display the full system prompt being used                               |
| `/help`             | Show all available in-session commands                                  |
| `exit` or `quit`    | Save conversation and exit Kubrick                                      |

**Loading Conversations:**

You can load conversations in two ways:

1. **In-session (new!)**: Use `/list` to see numbered conversations, then `/load <#>`:

   ```bash
   You: /list
   # Shows numbered list of conversations
   You: /load 1              # Load conversation #1 from the list
   You: /load 20240118_143022  # Or load by ID
   ```

2. **At startup**: Use `--load` when starting Kubrick:
   ```bash
   kubrick --load 20240118_143022              # Load by ID
   kubrick --load /path/to/conversation.json   # Load by file path
   ```

### Examples

```bash
# List conversations
You: /list

# Show config
You: /config

# Update config
You: /config triton_url localhost:9000

# Delete old conversation
You: /delete 20240115_120000
```

## Conversation Management

### Automatic Saving

Kubrick automatically saves conversations to `~/.kubrick/conversations/` after each turn.

### Loading Conversations

Kubrick supports loading conversations in two ways:

#### 1. By Conversation ID (from ~/.kubrick/conversations/)

```bash
# Load by ID (searches in ~/.kubrick/conversations/)
kubrick --load 20240118_143022

# List available conversations to find IDs
You: /list 20
```

#### 2. By File Path (from anywhere)

```bash
# Load from absolute path
kubrick --load /path/to/conversation.json

# Load from relative path
kubrick --load ../saved-conversations/session.json

# Load from home directory (~ expansion supported)
kubrick --load ~/backup/important-conversation.json
```

**Use Cases:**

- **Share conversations**: Export a conversation JSON and share with team members
- **Version control**: Save conversations in your project repo for documentation
- **Backup/restore**: Keep important conversations backed up outside ~/.kubrick
- **Cross-machine**: Move conversations between development machines

**Example Workflow:**

```bash
# Save a conversation to your project
cp ~/.kubrick/conversations/20240118_143022.json ~/my-project/ai-debug-session.json

# Commit to version control
git add ai-debug-session.json
git commit -m "Add AI debugging session"

# Load it later (on any machine with the repo)
kubrick --load ~/my-project/ai-debug-session.json
```

### Conversation Files

Each conversation is saved as JSON:

```json
{
  "id": "20240118_143022",
  "messages": [...],
  "metadata": {
    "working_dir": "/path/to/project",
    "triton_url": "localhost:8000"
  }
}
```

## Troubleshooting

### Tool Calling Issues

**Problem:** LLM not using tools properly

**Solution:** Ensure the LLM outputs tool calls in this format:

````markdown
```tool_call
{
  "tool": "read_file",
  "parameters": {
    "file_path": "example.py"
  }
}
```
````

**Fallback:** Even without markdown fences, Kubrick can detect raw JSON tool calls (you'll see a warning).

**Test:** Run `pytest tests/test_tool_calling.py` to verify tool call detection.

**Model Requirements:** Use a capable model (GPT-4, Claude, Llama 3+, etc.) that can follow structured output instructions.

### Connection Issues

**Cannot connect to Triton:**

1. Verify Triton is running:

   ```bash
   curl http://localhost:8000/v2/health/live
   ```

2. Check config:

   ```bash
   You: /config
   ```

3. Update URL:
   ```bash
   export TRITON_URL=localhost:8000
   # or
   You: /config triton_url localhost:8000
   ```

**Docker network issues:**

- Ensure `--network host` mode is used
- Triton must be accessible at `localhost:8000` on the host

### File Access Issues (Docker)

**Files not found:**

1. Run Docker from your project directory:

   ```bash
   cd /path/to/project
   ```

2. Include working directory mount:

   ```bash
   -v ${PWD}:/workspace
   ```

3. Only files in the mounted directory are accessible

**Permission Issues:**

Files created as root? You forgot the `--user` flag!

```bash
# Wrong (creates root-owned files)
docker run --rm -it --network host \
  -v ${HOME}:/home/kubrick -v ${PWD}:/workspace \
  rcland12/kubrick-cli

# Correct (creates files owned by you)
docker run --rm -it --network host --user $(id -u):$(id -g) \
  -v ${HOME}:/home/kubrick -v ${PWD}:/workspace \
  rcland12/kubrick-cli
```

**Easiest solution:** Use the `kubrick-docker` wrapper which handles this automatically.

See [DOCKER.md](DOCKER.md) for detailed troubleshooting.

## Example Sessions

### Creating a New File

````
You: Create a Python script that sorts a list of numbers
Assistant: I'll create a Python script to sort numbers for you.

```tool_call
{
  "tool": "write_file",
  "parameters": {
    "file_path": "sort_numbers.py",
    "content": "def sort_numbers(numbers):\n    return sorted(numbers)\n\nif __name__ == \"__main__\":\n    nums = [5, 2, 8, 1, 9]\n    print(f\"Original: {nums}\")\n    print(f\"Sorted: {sort_numbers(nums)}\")\n"
  }
}
````

✓ Created file: sort_numbers.py

```

### Searching Code

```

You: Find all TODO comments in Python files
Assistant: Searching for TODO comments...

```tool_call
{"tool": "search_files", "parameters": {"pattern": "TODO", "file_pattern": "*.py"}}
```

Found 3 matches in 2 files.

````

## Development

### Running Tests

```bash
pip install -e ".[dev]"
pytest tests/
pytest tests/test_triton.py
pytest --cov=kubrick_cli tests/
````

### Project Structure

```
kubrick/
├── kubrick_cli/          # Main package
│   ├── main.py          # CLI entry point
│   ├── config.py        # Configuration
│   ├── triton_client.py # HTTP client
│   └── tools.py         # Tool executor
├── tests/               # Test suite
├── pyproject.toml       # Package config
└── Dockerfile           # Docker image
```

### Code Formatting

```bash
black kubrick_cli/
```

## How It Works

1. You type questions or requests in natural language
2. The AI analyzes your request and chooses appropriate tools
3. Tools are executed automatically (reads, writes, searches, commands)
4. Results are displayed and the AI continues the conversation
5. All operations happen in your working directory
6. Conversations are automatically saved to `~/.kubrick/conversations/`

## Best Practices

### For Users

- Be specific in your requests
- Let the AI use tools automatically (don't micromanage)
- Use `/list` to find previous conversations
- Configure Triton URL once with `/config` and forget it

### For LLM Models

- Use capable models (GPT-4, Claude 3.5+, Llama 3.1 70B+)
- Ensure the model can follow structured output formats
- Models should be trained on tool/function calling

### For Triton Setup

- See [TRITON.md](TRITON.md) for backend requirements
- Use streaming-enabled models
- Ensure proper SSE (Server-Sent Events) support

## Contributing

Contributions welcome\! Please ensure:

- Tests pass: `pytest tests/`
- Code is formatted: `black kubrick_cli/`
- Documentation is updated

## Links

- [Triton Setup](TRITON.md)
- [Docker Guide](DOCKER.md)
- [GitHub Issues](https://github.com/yourusername/kubrick/issues)
