# Kubrick CLI Changelog

## Version 0.1.1 - Tool Calling Robustness Update

### Improvements

#### 1. Enhanced System Prompt

- **Explicit Tool Instructions**: System prompt now includes detailed, step-by-step instructions for tool usage
- **Concrete Examples**: Added multiple examples showing correct tool call format
- **Directive Language**: Changed from passive suggestions to active imperatives ("MUST use tools")
- **Format Emphasis**: Highlighted the exact markdown fence format required

#### 2. Fallback Tool Call Parser

- **Resilient Parsing**: Added secondary parser that detects tool calls even without markdown fences
- **Warning System**: Notifies user when fallback parser is used
- **Broader Compatibility**: Works with LLMs that may not follow formatting exactly

#### 3. Improved Tool Documentation

- **Clearer Parameter Lists**: Tool parameters now displayed with required/optional markers
- **Better Descriptions**: More detailed parameter descriptions
- **Simplified Format**: Removed redundant text, focused on clarity

#### 4. New Debug Commands

- `/debug` - Show current session information
- `/debug prompt` - Display full system prompt for inspection
- `/help` - Show all available commands

#### 5. Testing

- Added `test_tool_calling.py` to verify parser functionality
- Tests both primary and fallback parsers
- Validates real-world examples from failed conversations

### Bug Fixes

- Fixed issue where LLMs would output tool calls without proper markdown fences
- Improved tool call detection reliability
- Better error messages for malformed tool calls

### Documentation

- Added troubleshooting section to README
- Documented tool call format requirements
- Added debugging workflow for tool calling issues

---

## Version 0.1.0 - Configuration & Persistence Update

### New Features

#### 1. Automatic Configuration Management

- **Config Directory**: `~/.kubrick/` automatically created on first run
- **Config File**: `~/.kubrick/config.json` stores user preferences
- **No Setup Required**: Directory creation happens automatically - no setup.py or special permissions needed

#### 2. Conversation Persistence

- **Auto-Save**: All conversations automatically saved after each turn
- **Conversation Directory**: Stored in `~/.kubrick/conversations/`
- **Load Previous Conversations**: Resume any previous conversation with `--load` flag
- **Conversation Cleanup**: Automatically removes oldest conversations when max limit reached (default: 100)

#### 3. Configuration System

Default configuration values:

```json
{
  "triton_url": "localhost:8000",
  "model_name": "llm_decoupled",
  "use_openai": false,
  "default_working_dir": null,
  "auto_save_conversations": true,
  "max_conversations": 100
}
```

#### 4. Special Commands

New in-session commands for managing conversations and configuration:

- `/save` - Manually save current conversation
- `/list [N]` - List saved conversations (default: 20 most recent)
- `/config` - Display current configuration
- `/config KEY VALUE` - Update configuration value
- `/delete ID` - Delete a saved conversation

#### 5. CLI Enhancements

**New Command-Line Options:**

```bash
# Load a previous conversation
kubrick --load 20240118_143022

# Configuration now falls back to ~/.kubrick/config.json
kubrick  # Uses config.json defaults
```

**Command-Line Precedence:**

1. Command-line arguments (highest priority)
2. Environment variables
3. Config file (`~/.kubrick/config.json`)
4. Built-in defaults (lowest priority)

### Technical Details

#### Files Added

- `kubrick_cli/config.py` - Configuration management module
- `test_config.py` - Test suite for configuration system
- `CHANGELOG.md` - This file

#### Files Modified

- `kubrick_cli/main.py` - Integrated configuration and persistence
- `kubrick_cli/__init__.py` - Export new modules
- `README.md` - Updated documentation

#### Architecture

```
~/.kubrick/
├── config.json                    # User configuration
└── conversations/
    ├── 20240118_143022.json      # Saved conversation
    ├── 20240118_150330.json      # Another conversation
    └── ...
```

Each conversation file contains:

```json
{
  "id": "20240118_143022",
  "messages": [
    { "role": "system", "content": "..." },
    { "role": "user", "content": "..." },
    { "role": "assistant", "content": "..." }
  ],
  "metadata": {
    "working_dir": "/path/to/project",
    "triton_url": "localhost:8000",
    "model_name": "llm_decoupled",
    "use_openai": false,
    "saved_at": "2024-01-18T14:30:22.123456"
  }
}
```

### Usage Examples

#### Basic Usage

```bash
# Start Kubrick (creates ~/.kubrick on first run)
kubrick

# Inside session:
You: Create a Python script
Assistant: [Creates script]

You: /save
# Conversation saved as 20240118_143022

You: exit
# Auto-saves and exits
```

#### Managing Conversations

```bash
# List recent conversations
kubrick
You: /list
# Shows table of saved conversations

# Load a previous conversation
kubrick --load 20240118_143022
# Continues from where you left off

# Delete old conversations
You: /delete 20240118_120000
# Conversation deleted
```

#### Configuration Management

```bash
# View current config
You: /config
# Shows all settings

# Update Triton URL
You: /config triton_url myserver:8000
# Persisted to ~/.kubrick/config.json

# Next time you run kubrick, it uses the new default
kubrick
# Automatically connects to myserver:8000
```

### Testing

Run the configuration test suite:

```bash
python test_config.py
```

This verifies:

- Directory creation
- Config file creation and updates
- Conversation saving/loading
- Conversation listing and deletion
- Config value persistence

### Migration Notes

**For Existing Users:**

- No action required - ~/.kubrick created automatically on next run
- Existing command-line usage remains unchanged
- New features are opt-in via special commands

**Permissions:**

- No special permissions required
- All files created in user home directory (~/.kubrick)
- Standard file permissions (644 for files, 755 for directories)

### Future Enhancements

Potential features for future releases:

- Conversation search and filtering
- Export conversations to markdown
- Conversation tags and categories
- Conversation statistics and analytics
- Multi-profile support
- Cloud sync for conversations
