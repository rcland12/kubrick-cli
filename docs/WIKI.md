# Kubrick CLI - Complete Documentation

Complete guide to using Kubrick CLI for AI-assisted coding.

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [Provider Support](#provider-support)
- [Configuration](#configuration)
- [Context Management](#context-management)
- [Available Tools](#available-tools)
- [Planning Mode](#planning-mode)
- [Special Commands](#special-commands)
- [Conversation Management](#conversation-management)
- [Troubleshooting](#troubleshooting)
- [Example Sessions](#example-sessions)
- [Development](#development)

## Features

- 🤖 **AI-powered coding assistant** with natural conversation
- 🔌 **Multi-provider support** - Use Triton, OpenAI, or Anthropic
- 🛠️ **Robust tool calling** for automatic file operations and commands
- 📋 **Planning Mode** - Intelligent task classification with optional plan-before-execute workflow
- 🔒 **Permission system** - Granular control over file writes and bash commands with session caching
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

### Option 1: PyPI (Recommended)

Install the latest stable release from PyPI:

```bash
pip install kubrick-cli
```

This is the easiest and most reliable method. The package is available on [PyPI](https://pypi.org/project/kubrick-cli/).

**Upgrade to latest version:**

```bash
pip install --upgrade kubrick-cli
```

### Option 2: Development Installation

For contributing or testing the latest changes:

```bash
git clone https://github.com/rcland12/kubrick-cli.git
cd kubrick-cli
pip install -e ".[dev]"
```

This installs the `kubrick` command globally in editable mode.

**Dependencies:** Only `rich` and `prompt_toolkit` for the CLI interface. No external LLM libraries required!

### Option 3: Docker

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

### Config File Location

All configuration is stored at `~/.kubrick/config.json`. Kubrick creates this automatically on first run with sensible defaults.

### Complete Configuration Reference

Here are all available configuration options:

```json
{
  // Provider Settings
  "provider": "triton",                    // LLM provider: "triton", "openai", or "anthropic"

  // Triton Provider Settings
  "triton_url": "localhost:8000",          // Triton server URL
  "triton_model": "llm_decoupled",         // Triton model name

  // OpenAI Provider Settings
  "openai_api_key": null,                  // OpenAI API key
  "openai_model": "gpt-4",                 // OpenAI model name

  // Anthropic Provider Settings
  "anthropic_api_key": null,               // Anthropic API key
  "anthropic_model": "claude-sonnet-4-5-20250929",  // Anthropic model name

  // General Settings
  "default_working_dir": null,             // Default working directory
  "auto_save_conversations": true,         // Auto-save conversations after each turn
  "max_conversations": 100,                // Max conversations to keep (auto-cleanup)

  // Agent Loop Settings
  "max_iterations": 15,                    // Maximum agentic iterations per turn
  "max_tools_per_turn": 5,                 // Maximum tools per iteration
  "total_timeout_seconds": 600,            // Total timeout for agent loop (10 min)
  "enable_parallel_tools": true,           // Enable parallel tool execution
  "max_parallel_workers": 3,               // Max parallel tool workers

  // Safety Settings
  "require_dangerous_command_confirmation": true,  // Confirm dangerous bash commands
  "tool_timeout_seconds": 30,              // Timeout for individual tools
  "max_file_size_mb": 10,                  // Maximum file size to read (MB)

  // Display Settings
  "display_mode": "natural",               // Display mode: "natural" or "technical"
  "show_tool_results": true,               // Show tool execution results
  "show_progress": true,                   // Show progress indicators
  "clean_display": true,                   // Suppress raw JSON tool calls (recommended)

  // Task Classification & Planning Settings
  "enable_task_classification": true,      // Enable automatic task classification (SIMPLE/COMPLEX/CONVERSATIONAL)
  "enable_planning_phase": true,           // Offer planning mode for COMPLEX tasks (default: no)

  // Task Evaluator Settings (Advanced)
  "enable_task_evaluator": false,          // EXPERIMENTAL: LLM-based completion detection (can interfere)
  "evaluator_model": null,                 // Model for evaluator (null = use main model)

  // Context Management Settings
  "enable_context_management": true,       // Enable automatic context management
  "context_usage_threshold": 0.75,         // Start trimming at 75% of available context
  "context_summarization_threshold": 0.85, // Summarize at 85% of available context
  "min_messages_to_keep": 4,               // Always preserve last N messages
  "max_tool_result_chars": 10000,          // Truncate tool results longer than this
  "max_output_tokens": 2048,               // Reserve tokens for LLM output

  // Model Context Windows (in tokens)
  "context_windows": {
    // OpenAI models
    "gpt-4": 128000,                       // Modern GPT-4 (128k context)
    "gpt-4-turbo": 128000,
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-3.5-turbo": 16385,

    // Anthropic models
    "claude-sonnet-4-5-20250929": 200000,  // Claude has 200k context
    "claude-opus-4-1-20250805": 200000,
    "claude-3-5-sonnet-20241022": 200000,

    // Triton/vLLM
    "llm_decoupled": 8192                  // Conservative default for Triton
  },
  "default_context_window": 8192,          // Fallback for unknown models
  "model_max_context_override": null       // Manual override for custom model configs
}
```

### Key Configuration Options Explained

#### Context Management (⭐ Important!)

These settings control how Kubrick manages conversation length to prevent context overflow:

| Setting | Default | Description |
|---------|---------|-------------|
| `enable_context_management` | `true` | Enable automatic context management |
| `model_max_context_override` | `null` | **Override context window** - Set this to match your vLLM `--max-model-len` if using custom Triton models |
| `max_output_tokens` | `2048` | Tokens reserved for LLM output (prevents input from using all space) |
| `context_usage_threshold` | `0.75` | Start trimming old messages at 75% usage |
| `context_summarization_threshold` | `0.85` | Summarize conversation at 85% usage |
| `min_messages_to_keep` | `4` | Always preserve last N messages |
| `max_tool_result_chars` | `10000` | Truncate large tool outputs |

**For Triton/vLLM users**: If you're loading models with custom context lengths (e.g., `--max-model-len 16384`), you MUST set:

```bash
/config model_max_context_override 16384
/config max_output_tokens 2048
```

See the [Context Management](#context-management) section for detailed guidance.

#### Agent Behavior

| Setting | Default | Description |
|---------|---------|-------------|
| `max_iterations` | `15` | How many times the agent can iterate |
| `max_tools_per_turn` | `5` | Maximum tools per iteration |
| `total_timeout_seconds` | `600` | Total time limit (10 minutes) |
| `enable_parallel_tools` | `true` | Run read-only tools in parallel |
| `max_parallel_workers` | `3` | Number of parallel tool workers |

#### Display Options

| Setting | Default | Description |
|---------|---------|-------------|
| `display_mode` | `"natural"` | Display style: `"natural"` (friendly) or `"technical"` (detailed) |
| `show_tool_results` | `true` | Show full tool execution results in output |
| `show_progress` | `true` | Show progress indicators and status messages |
| `clean_display` | `true` | **Suppress raw JSON tool calls** - Shows only clean output, hides technical JSON blocks ✨ |

**Clean Display Mode** (recommended): When enabled, Kubrick hides the raw `\`\`\`tool_call {...}` JSON blocks during streaming, giving you cleaner output while still showing:
- All agent responses and explanations
- Tool execution messages (`→ Called write_file`, `✓ succeeded`)
- Iteration progress and status
- Error messages and warnings

Disable with `/config clean_display false` if you want to see the raw JSON for debugging.

#### Safety & Limits

| Setting | Default | Description |
|---------|---------|-------------|
| `require_dangerous_command_confirmation` | `true` | Confirm dangerous bash commands (rm, sudo, etc.) |
| `tool_timeout_seconds` | `30` | Individual tool timeout |
| `max_file_size_mb` | `10` | Maximum file size to read |

**Permission System:** Kubrick includes a built-in permission system that prompts for approval before:
- Writing or editing files (`write_file`, `edit_file`)
- Creating directories (`create_directory`)
- Running bash commands (`run_bash`)

When prompted, you can choose:
- **Once**: Allow this single operation
- **Session**: Remember permission for this file/command for the entire session
- **All-bash**: Allow all bash commands for the session (file prompts still required)
- **Deny**: Block the operation

Permissions are cached in-memory per session, so you won't be repeatedly prompted for the same files or commands.

#### Task Evaluator (⚠️ Experimental)

| Setting | Default | Description |
|---------|---------|-------------|
| `enable_task_evaluator` | `false` | **EXPERIMENTAL** - Uses LLM to intelligently detect task completion |
| `evaluator_model` | `null` | Model for evaluator (null = use main model, or specify "gpt-4o-mini", etc.) |

**Note:** The task evaluator is currently **disabled by default** as it can sometimes interfere with the agent's tool calling behavior. It was designed to detect when tasks are complete or if the agent is stuck, but in practice it can cause the agent to apologize unnecessarily or stop prematurely. Leave it disabled unless you want to experiment with it.

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
You: /config                    # Show all configuration
You: /config triton_url myserver:8000
You: /config max_conversations 50
You: /config model_max_context_override 16384
```

### Common Configuration Examples

```bash
# For Triton/vLLM with custom context
/config model_max_context_override 16384
/config max_output_tokens 2048

# Adjust context management thresholds
/config context_usage_threshold 0.60     # Trim earlier (more aggressive)
/config context_summarization_threshold 0.75

# Increase max iterations for complex tasks
/config max_iterations 20

# Disable parallel tools (if causing issues)
/config enable_parallel_tools false
```

## Context Management

Kubrick includes sophisticated context management to prevent conversations from exceeding model limits. This prevents hallucinations and ensures stable, long-running conversations.

### How It Works

Context management operates in three stages:

1. **Normal Operation** (< 75% usage)
   - No intervention
   - Full conversation history preserved

2. **Trimming** (75% - 85% usage)
   - Removes oldest messages (except system prompt and recent N messages)
   - Adds a note about trimmed messages
   - Targets 60% usage to leave growth room

3. **Summarization** (> 85% usage)
   - Uses LLM to summarize middle conversation
   - Keeps: system prompt + summary + recent messages
   - Preserves important context while reducing tokens

4. **Emergency Reset** (exceeds 100%)
   - Rare, but prevents complete failure
   - Keeps only system prompt + last user message

### Provider-Specific Context Windows

| Provider | Model | Context Window | Output Reserved | Available |
|----------|-------|----------------|-----------------|-----------|
| **OpenAI** | gpt-4 | 128,000 | 2,048-4,096 | ~124k-126k |
| | gpt-4o | 128,000 | 2,048-4,096 | ~124k-126k |
| | gpt-3.5-turbo | 16,385 | 2,048-4,096 | ~12k-14k |
| **Anthropic** | Claude 3+ | 200,000 | 2,048-4,096 | ~196k-198k |
| **Triton/vLLM** | Custom | **Configure!** | 2,048+ | Depends |

### Monitoring Context Usage

Check your context usage anytime:

```bash
You: /context
```

This displays:
- Current token count
- Context window size
- Usage percentage
- Trim/summarize thresholds
- Warning if approaching limits

Example output:
```
┌────────────────────────────┐
│ Context Window Status      │
├──────────────┬─────────────┤
│ Metric       │ Value       │
├──────────────┼─────────────┤
│ Current      │ 5,234       │
│ Context      │ 128,000     │
│ Usage        │ 4.1%        │
│ Trim at      │ 75%         │
│ Summarize at │ 85%         │
└──────────────┴─────────────┘

✓ Context usage healthy
```

### Configuring for Triton/vLLM

**CRITICAL**: If you're using Triton/vLLM with custom model configurations, you MUST set the context window to match your deployment:

```bash
# Example: Gemma 3 27B with 16K context
# If you launched vLLM with: --max-model-len 16384
kubrick
/config model_max_context_override 16384
/config max_output_tokens 2048

# Example: Llama 3.3 70B with full 128K context
# If you launched vLLM with: --max-model-len 131072
/config model_max_context_override 131072
/config max_output_tokens 8192
```

**Why this matters**:
- Default for Triton is conservative (8,192 tokens)
- If your model supports more, you'll trim way too often
- If you set too high, you'll get hallucinations and errors

### Adjusting Context Behavior

```bash
# More aggressive trimming (trim earlier, use less context)
/config context_usage_threshold 0.60
/config context_summarization_threshold 0.75

# Less aggressive (use more context before trimming)
/config context_usage_threshold 0.85
/config context_summarization_threshold 0.92

# Adjust output reservation
/config max_output_tokens 4096     # For longer responses
/config max_output_tokens 1024     # For short, concise responses
```

### Troubleshooting Context Issues

#### "Context trimming too frequently"

**Symptoms**: Seeing "Context managed: trimmed" very often

**Solutions**:
1. Check your actual context window: `/context`
2. For OpenAI/Anthropic: Should be 128k/200k (if showing 8k, update Kubrick)
3. For Triton/vLLM: Set `model_max_context_override` to match your `--max-model-len`
4. Increase thresholds: `/config context_usage_threshold 0.85`
5. Reduce output reservation: `/config max_output_tokens 2048`

#### "Still getting hallucinations"

**Symptoms**: LLM outputs garbage, lyrics, or nonsense at end of response

**Solutions**:
1. Check context: `/context` - are you hitting limits?
2. Verify `model_max_context_override` matches your vLLM config
3. Reduce `max_output_tokens` to reserve more space for input
4. Some vLLM versions don't respect `max_tokens` properly - try smaller values

#### "Not trimming when I expect it to"

**Check**:
1. View usage: `/context`
2. Verify context management is enabled: `/config | grep context`
3. Lower thresholds: `/config context_usage_threshold 0.60`

### Best Practices

1. **OpenAI/Anthropic users**: Defaults are optimized, no changes needed
2. **Triton/vLLM users**: ALWAYS set `model_max_context_override` to match your deployment
3. **Monitor with `/context`** during long conversations
4. **Adjust output tokens** based on your use case:
   - Code snippets: 2048
   - Full files: 4096
   - Large files/detailed explanations: 8192
5. **Don't over-reserve** output tokens - reduces available conversation space

See [PROVIDER_CONTEXT_RECOMMENDATIONS.md](../PROVIDER_CONTEXT_RECOMMENDATIONS.md) for detailed provider-specific guidance.

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

## Planning Mode

Planning Mode is a feature that helps Kubrick tackle complex tasks by creating a detailed implementation plan before executing changes. This approach reduces errors, prevents wasted effort, and gives you control over what changes will be made.

### How Planning Mode Works

When Planning Mode is activated, Kubrick follows a structured workflow:

1. **Exploration Phase** (Read-only)
   - Agent explores your codebase using read-only tools
   - Reads relevant files, lists directory structures, searches for patterns
   - Understands existing architecture and dependencies
   - No changes are made during this phase

2. **Plan Creation**
   - Agent creates a detailed implementation plan including:
     - Overview of the approach
     - Step-by-step implementation tasks
     - Files that will be modified
     - Potential risks or concerns

3. **User Approval**
   - Plan is presented to you for review
   - You can:
     - **Approve**: Execute the plan as written
     - **Modify**: Provide feedback for the agent to adjust the plan
     - **Reject**: Cancel the task entirely

4. **Execution Phase** (Full tools)
   - After approval, agent executes with full write permissions
   - Follows the approved plan
   - Makes changes to files, runs commands, etc.

### When Planning Mode is Triggered

Kubrick uses intelligent task classification to determine when to offer Planning Mode:

#### Automatic Classification

**SIMPLE Tasks** (No planning prompt):
- Creating/modifying 1-3 files with clear requirements
- Single function additions or small edits
- Well-defined scope with 1-7 tool calls
- Examples:
  - "Create two Python scripts for healthcheck monitoring"
  - "Add a new function to module.py"
  - "Write a script and test file for it"
  - "Update the README and add an example file"

**COMPLEX Tasks** (Offers planning):
- Touching 4+ files with interdependencies
- Architectural changes or major refactoring
- Uncertain scope requiring exploration
- Multiple valid approaches needing user input
- Examples:
  - "Refactor the authentication system"
  - "Add logging to all Python files in the project"
  - "Debug why the tests are failing" (requires investigation)
  - "Redesign the database schema and update all related code"

When a COMPLEX task is detected, you'll see:
```
→ Task classified as COMPLEX
→ Execution mode: agentic_complex (model: best, max_iter: 15)

This looks complex. Create a plan first? [yes/no] (no):
```

**Note:** The default is "no" - Kubrick will execute immediately unless you choose to plan. This keeps you in control.

### Manual Planning with `/plan`

You can force Planning Mode for any task using the `/plan` command:

#### Interactive Mode
```bash
You> /plan
Planning Mode
Enter your task/request for planning:
Task> Refactor authentication system to use JWT tokens

→ Entering PLANNING MODE
[Agent explores codebase...]
```

#### Inline Mode
```bash
You> /plan Refactor authentication system to use JWT tokens

→ Entering PLANNING MODE
[Agent explores codebase...]
```

### Why Use Planning Mode?

**Benefits:**
- ✅ **Reduces mistakes**: Agent explores before making changes
- ✅ **User control**: Review and approve before any files are modified
- ✅ **Better approach**: Agent thinks through the full solution first
- ✅ **Catches issues**: Identifies potential problems before execution
- ✅ **Documentation**: Creates a clear record of what will be done

**Best for:**
- Architectural changes across multiple files
- Refactoring with unclear scope
- Tasks where multiple approaches are valid
- When you want to review before execution
- Learning how to implement something (see the plan!)

**Skip it for:**
- Quick file edits or additions (1-3 files)
- Well-defined, straightforward tasks
- When you trust the agent to proceed directly

### Configuring Planning Behavior

You can enable or disable the planning feature entirely:

```bash
# Disable planning prompts (always skip to execution)
You> /config enable_planning_phase false

# Re-enable planning prompts
You> /config enable_planning_phase true

# Disable task classification (treats all tasks as simple)
You> /config enable_task_classification false
```

### Example Planning Session

```bash
You> /plan Add a REST API endpoint for user profile updates

→ Creating plan for: Add a REST API endpoint for user profile updates

→ Entering PLANNING MODE
Agent will explore the codebase with read-only tools and create a plan.

→ Agent iteration 1/10
Assistant:
Let me explore the codebase to understand the existing API structure.

```tool_call
{"tool": "list_files", "parameters": {"pattern": "**/*.py"}}
```

[... exploration continues ...]

→ Agent iteration 2/10
Assistant:
## Implementation Plan

### Overview
We'll add a new REST API endpoint at PUT /api/users/{user_id}/profile
that allows authenticated users to update their profile information.

### Steps
1. Create profile update schema in schemas/user.py
2. Add PUT endpoint handler in routes/users.py
3. Implement validation for profile fields
4. Add authentication middleware check
5. Create integration tests in tests/test_user_routes.py
6. Update API documentation

### Files to Modify
- routes/users.py: Add new PUT endpoint
- schemas/user.py: Add ProfileUpdateSchema
- tests/test_user_routes.py: Add test coverage
- docs/api.md: Document new endpoint

### Risks
- Need to ensure proper authentication is enforced
- Profile updates should only allow whitelisted fields
- Rate limiting may be needed to prevent abuse

PLAN_COMPLETE

======================================================================
╭────────────────────── Implementation Plan ──────────────────────╮
│ [Plan details displayed in formatted panel]                      │
╰───────────────────────────────────────────────────────────────────╯
======================================================================

Approve this plan? [approve/modify/reject] (approve): approve
✓ Plan approved, proceeding with implementation

→ Executing plan...

[Agent implements the changes...]

✓ Plan execution complete in 8 iteration(s) with 12 tool call(s)
```

### Planning Mode Tools

During the Planning Phase, only **read-only tools** are available:

| Tool | Purpose |
|------|---------|
| `read_file` | Read file contents |
| `list_files` | List files matching glob patterns |
| `search_files` | Search for text patterns in files |
| `run_bash` | **Read-only commands only** (ls, grep, find, tree, etc.) |

**Restricted:** write_file, edit_file, create_directory, and destructive bash commands are blocked during planning.

### Tips for Effective Planning

1. **Use `/plan` for exploration**: Even if you're not sure what to do, let the agent explore and create a plan to understand the codebase better

2. **Provide modifications**: If the plan isn't quite right, choose "modify" and explain what needs adjustment

3. **Planning is educational**: Review the plans to learn about architectural patterns in your codebase

4. **Skip planning for simple tasks**: If you know exactly what needs to be done and it's 1-3 files, just ask directly

5. **Trust the classification**: Kubrick's classifier is conservative - if it suggests planning, consider accepting

## Special Commands

Use these commands during a Kubrick session:

| Command             | Description                                                             |
| ------------------- | ----------------------------------------------------------------------- |
| `/save`             | Manually save the current conversation                                  |
| `/plan`             | **Force planning mode** - Explore → Plan → Approve → Execute           |
| `/plan <task>`      | Force planning mode with inline task description                        |
| `/list [N]`         | List saved conversations (default: 20, shows numbered list)             |
| `/load <#\|ID>`     | Load a conversation by number (from /list) or ID                        |
| `/config`           | Show current configuration                                              |
| `/config KEY VALUE` | Update a configuration setting                                          |
| `/context`          | **Show context window usage and status** (tokens, thresholds, warnings) |
| `/delete ID`        | Delete a saved conversation                                             |
| `/debug`            | Show debug information (conversation ID, message count, provider, etc.) |
| `/debug prompt`     | Display the full system prompt being used                               |
| `/help`             | Show all available in-session commands with examples                    |
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
# Force planning mode for a complex task
You: /plan Refactor authentication to use JWT

# Interactive planning mode
You: /plan
Task> Add REST API endpoint for user profile updates

# List conversations
You: /list

# Show config
You: /config

# Update config
You: /config triton_url localhost:9000
You: /config model_max_context_override 16384

# Check context usage
You: /context

# Delete old conversation
You: /delete 20240115_120000

# Show debug info
You: /debug

# View system prompt
You: /debug prompt
```

### Common Configuration Commands

```bash
# For Triton/vLLM users with custom context
You: /config model_max_context_override 16384
You: /config max_output_tokens 2048
You: /context  # Verify settings

# Adjust context management behavior
You: /config context_usage_threshold 0.60
You: /config context_summarization_threshold 0.75

# Increase agent iterations for complex tasks
You: /config max_iterations 20

# Change provider mid-session (requires restart to take effect)
You: /config provider openai
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
2. Kubrick classifies your task (SIMPLE, COMPLEX, or CONVERSATIONAL)
3. For COMPLEX tasks, optionally enter Planning Mode for exploration and approval
4. The AI analyzes your request and chooses appropriate tools
5. Permission checks occur for file writes and bash commands (cached per session)
6. Tools are executed automatically (reads, writes, searches, commands)
7. Results are displayed and the AI continues the conversation
8. All operations happen in your working directory
9. Conversations are automatically saved to `~/.kubrick/conversations/`

## Best Practices

### For Users

- Be specific in your requests
- Let the AI use tools automatically (don't micromanage)
- Use `/plan` for complex refactoring or architectural changes
- Trust the task classifier - it defaults to "just do it" for good reason
- Use `/list` to find previous conversations
- Configure Triton URL once with `/config` and forget it
- Review permission prompts carefully to avoid accidental overwrites

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
