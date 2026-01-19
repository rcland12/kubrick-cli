# Kubrick CLI - Complete Documentation

Complete guide to using Kubrick CLI for AI-assisted coding.

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [Available Tools](#available-tools)
- [Special Commands](#special-commands)
- [Conversation Management](#conversation-management)
- [Troubleshooting](#troubleshooting)
- [Example Sessions](#example-sessions)
- [Development](#development)

## Features

- 🤖 **AI-powered coding assistant** with natural conversation
- 🛠️ **Robust tool calling** for automatic file operations and commands
- 📁 **File operations**: read, write, edit with pattern matching
- 🔍 **Code search** with glob patterns and grep-like functionality
- 💻 **Bash command integration** for running scripts and commands
- 🌊 **Real-time streaming responses** via HTTP (no external LLM libraries)
- 💾 **Automatic conversation persistence** with searchable history
- ⚙️ **Configuration management** with multiple override levels
- 📂 **Conversation history** saved in `~/.kubrick`
- 🔧 **Improved system prompts** with clear tool calling examples
- 🛡️ **Fallback parser** for resilient tool call detection
- 🐳 **Docker support** with working directory mounting

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

Run in a container without installing anything:

```bash
cd /path/to/your/project
docker run --rm -it \
  --network host \
  -v ~/.kubrick:/kubrick \
  -v $(pwd):/workspace \
  rcland12/kubrick-cli:latest
```

See [DOCKER.md](DOCKER.md) for complete Docker setup.

## Usage

### Basic Commands

```bash
# Start in current directory
kubrick

# Custom Triton server
kubrick --triton-url my-server:8000

# Custom model name
kubrick --model-name my-llm-model

# Set working directory
kubrick --working-dir /path/to/project

# Load previous conversation
kubrick --load 20240118_143022
```

### Command-Line Options

| Option | Environment Variable | Description |
|--------|---------------------|-------------|
| `--triton-url` | `TRITON_URL` | Triton server HTTP URL |
| `--model-name` | `TRITON_MODEL_NAME` | Triton model name |
| `--working-dir` | - | Working directory for file operations |
| `--load` | - | Load previous conversation by ID |

**Priority order:** CLI arguments > Environment variables > Config file > Defaults

## Configuration

### Config File

Configuration is stored at `~/.kubrick/config.json`:

```json
{
  "triton_url": "localhost:8000",
  "model_name": "llm_decoupled",
  "default_working_dir": null,
  "auto_save_conversations": true,
  "max_conversations": 100
}
```

### Environment Variables

Override config with environment variables:

```bash
export TRITON_URL=my-server:8000
export TRITON_MODEL_NAME=llm_decoupled
kubrick
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
  {"tool": "read_file", "parameters": {"file_path": "main.py"}}
  ```

- **write_file** - Create or overwrite files
  ```json
  {"tool": "write_file", "parameters": {"file_path": "test.py", "content": "..."}}
  ```

- **edit_file** - Replace text in files
  ```json
  {"tool": "edit_file", "parameters": {"file_path": "main.py", "old_text": "...", "new_text": "..."}}
  ```

- **create_directory** - Create directories
  ```json
  {"tool": "create_directory", "parameters": {"dir_path": "src/utils"}}
  ```

### Code Search

- **list_files** - Find files by pattern (glob)
  ```json
  {"tool": "list_files", "parameters": {"pattern": "**/*.py"}}
  ```

- **search_files** - Search for text in files (grep-like)
  ```json
  {"tool": "search_files", "parameters": {"pattern": "def main", "file_pattern": "*.py"}}
  ```

### Command Execution

- **run_bash** - Execute bash commands
  ```json
  {"tool": "run_bash", "parameters": {"command": "pytest tests/"}}
  ```

## Special Commands

Use these commands during a Kubrick session:

| Command | Description |
|---------|-------------|
| `/save` | Manually save the current conversation |
| `/list [N]` | List saved conversations (default: 20) |
| `/config` | Show current configuration |
| `/config KEY VALUE` | Update a configuration setting |
| `/delete ID` | Delete a saved conversation |
| `/help` | Show help information |
| `exit` or `quit` | Save and exit |

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

```bash
# Load by ID
kubrick --load 20240118_143022

# List available conversations
You: /list 20
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
   -v $(pwd):/workspace
   ```

3. Only files in the mounted directory are accessible

See [DOCKER.md](DOCKER.md) for detailed troubleshooting.

## Example Sessions

### Creating a New File

```
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
```

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
```

## Development

### Running Tests

```bash
pip install -e ".[dev]"
pytest tests/
pytest tests/test_triton.py
pytest --cov=kubrick_cli tests/
```

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
