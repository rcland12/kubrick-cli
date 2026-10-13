# Kubrick CLI Changelog

## Version 0.2.0

A rewrite of the core around native tool calling and a Claude Code-style agent loop. Kubrick
is now provider-agnostic and tuned for local models.

### Added

- **Native tool calling on every provider**: providers convert a shared, provider-neutral
  conversation format (`kubrick_cli/messages.py`) to their own wire format and stream text,
  reasoning, and tool-call events. Triton keeps the text-based `tool_call` protocol, which is
  also the automatic fallback for any server that rejects tool definitions.
- **OpenAI-compatible provider** (`openai_compatible`) for Ollama, vLLM, llama.cpp, LM Studio,
  and hosted compatible APIs:
  - context-window detection (vLLM `max_model_len`, Ollama `/api/ps`)
  - `reasoning_content` / `<think>` handling
  - recovery of Hermes-style `<tool_call>` text
  - automatic retry without `stream_options`
  - the setup wizard lists the server's models
- **Amazon Bedrock provider** (`bedrock`, `pip install 'kubrick-cli[bedrock]'`) using the
  Converse streaming API. Tested live in commercial regions and GovCloud. Highlights:
  - **credentials**: an AWS profile/SSO, a `.env` file (`bedrock_credentials_file`),
    `KEY=VALUE` / `export KEY=VALUE` blocks pasted with `kubrick auth login bedrock` or
    `/login` (kept in the encrypted store), the default chain, or Bedrock API keys
    (`AWS_BEARER_TOKEN_BEDROCK`)
  - **expiring keys**: reloads them once when they expire mid-session, then prompts for a
    hidden paste and retries the request. A known expiry is shown at startup.
  - **models**:
    - a bare model ID switches automatically to its cross-region inference profile
      (`us.`, `us-gov.`, `eu.`, `apac.`) when Bedrock requires one
    - models without tool use fall back to the text protocol
    - `<thinking>` output is shown as reasoning
    - clearer errors for models an account can't use
- **Anthropic provider rewrite**:
  - default model `claude-opus-5-5`
  - adaptive thinking with summarized display
  - `anthropic_effort` setting
  - prompt caching
  - server-side refusal fallback on supported models
  - thinking blocks preserved across tool calls
  - retries on 429/5xx/529
  - configurable `anthropic_base_url`
- **OpenAI provider**: uses the Responses API, which gpt-6-era models require for tools.
  The model's encrypted reasoning is passed back between steps, and gateways without
  `/responses` fall back to Chat Completions. Default model `gpt-5`, configurable
  `openai_base_url`.
- **Credential store**:
  - environment variables first, then the OS keychain (`[keyring]` extra), then
    `~/.kubrick/credentials.json` encrypted with a machine-bound key
  - optional `credential_max_age_days` to force re-login
  - new `kubrick auth login|logout|status` commands
- **Permission modes** `default`, `accept_edits`, `plan`, `bypass`, set with
  `--permission-mode` or `/permissions`:
  - "always allow" answers per session: all edits, or a command prefix
  - read-only commands run without asking
  - reads and edits outside the working directory ask
  - denying with feedback redirects the agent
- **Plan mode** (`/plan`): read-only investigation before making changes.
- **Print mode** (`-p`): non-interactive single prompt, piped stdin, stdout/stderr split for
  scripting.
- **Project instructions**: `KUBRICK.md` (or `CLAUDE.md` / `AGENTS.md`) in the project and
  its parents, plus `~/.kubrick/KUBRICK.md`, are loaded into the system prompt. `/init`
  generates one.
- **Context compaction**: provider-reported token usage, automatic summarization at
  `context_usage_threshold`, cuts only at turn boundaries so tool calls stay paired with
  results, and `/compact [focus]`.
- **Command-line flags**: `-c/--continue`, `-r/--resume`, `-m/--model`, `-C/--working-dir`,
  `--tool-calling`, `--max-iterations`, `--version`, and a `kubrick setup` subcommand.
- **New slash commands**: `/clear`, `/compact`, `/model`, `/provider`, `/plan`,
  `/permissions`, `/init`, `/status`, `/login`, `/debug messages`.
- **Settings sources**: `KUBRICK_<KEY>` environment overrides for any setting, and session
  overrides that are never saved.
- **Tests**: end-to-end tests against a scripted OpenAI-compatible server, plus agent loop,
  provider, credential, permission, context, and terminal UI tests. The `dev` extra now
  includes boto3, so CI runs the Bedrock tests.
- **Command menu**: typing `/` lists commands with descriptions and filters as you type.
  Arrow keys pick one, Tab completes, Esc closes, and Enter without touching the menu sends
  what was typed. Arguments complete too (providers, models, modes, saved conversations,
  config keys), and unambiguous prefixes run directly (`/pro` runs `/provider`).
- **Pickers**: `/provider`, `/model`, and `/permissions` without an argument open an
  arrow-key menu with the current choice marked. The new `/setup` command reruns the wizard
  in a session, and switching to an unconfigured provider offers to set it up.
- **Setup wizard**:
  - arrow-key menus throughout
  - "Local model server" asks which server (Ollama, vLLM, llama.cpp, LM Studio) and takes a
    plain `host:port` (`http://` and `/v1` are added)
  - checks the connection live, with fixes for remote servers when it fails
  - asks for an API key only when the server wants one
  - reports the model's context window
  - lists models for Anthropic, OpenAI, and Bedrock, which also checks the API key
  - skips advanced settings such as base URLs (change those with `/config`)
- **Permission prompts** are an arrow-key menu (`y`/`a`/`n` and number keys still work).
- **Terminal compatibility**:
  - numbered-prompt fallback for dumb terminals (Emacs `M-x shell`), with
    `KUBRICK_SIMPLE_UI=1` to force it
  - symbols that render in common fonts, or `KUBRICK_ASCII=1` for ASCII only
  - `NO_COLOR` support
  - `editing_mode: vi`
- **`kubrick update` / `/update`**: checks PyPI and upgrades using the method Kubrick was
  installed with (`uv tool`, pipx, or pip in a virtualenv); Docker and source checkouts get
  instructions instead. `--check` only reports, and `--yes` upgrades without asking. A daily
  background check (cached, never blocks startup) mentions new releases; disable it with
  `check_for_updates: false`.
- **Dev environment**: a `Makefile` (`make dev/run/test/lint/sandbox/reset`) that keeps
  everything in `.venv/` and `.dev/`, a Docker sandbox (`docker/sandbox.Dockerfile`, with Python and Node.js), and a
  buggy `examples/playground` project to try the agent on.

### Changed

- **Agent loop**: the model calls tools until it replies without any, as in Claude Code.
  Tool results are proper tool messages, every tool call always gets a result, and refusals,
  interrupts, and responses cut off at the token limit are handled explicitly. The default
  `max_iterations` is now 50.
- **Tools**:
  - `read_file` returns numbered lines with `offset`/`limit` paging and refuses binary or
    oversized files
  - `edit_file` requires a unique match unless `replace_all` is set
  - `search_files` takes a regex and uses ripgrep when available
  - `run_bash` has a per-call `timeout`, closed stdin, and an exit code in the result
  - arguments are validated against each tool's schema before running
- **Display**: model text is streamed without rich-markup interpretation, reasoning is
  dimmed, and tool calls show as one line each (`● Edit(path)`).
- **System prompt**: concise and Claude Code-style, built once per conversation. Keeps the
  0.1.7 rule that changes are made with tools, not shown as code for the user to paste
  (local models often do that).
- **Default provider** is `openai_compatible`. Setting `KUBRICK_PROVIDER` skips the setup
  wizard.
- **Docs**:
  - `docs/CICD.md` and `docs/TESTING.md` rewritten to match the workflows (release on a
    version bump reaching `master`; TestPyPI from `staging`)
  - the other docs updated for the new wizard, commands, `kubrick update`, and dev
    environment
- **CI**:
  - GitHub Actions bumped: `actions/upload-artifact` v7, `docker/setup-buildx-action`
    v4, `docker/build-push-action` v7
  - Dependabot now opens its PRs against `staging`
  - Security Scanning can be run by hand from the Actions tab (`workflow_dispatch`)
  - the test job runs on `ubuntu-24.04`, because `ubuntu-latest` moves to Ubuntu 26.04
    on 2026-10-19 and there is no Python 3.9 build for it
  - Codecov action v7 with the `files` input (the old `file` input was ignored), and
    the `CODECOV_TOKEN` secret passed when set
- **Requirements**: Python 3.9 or newer, and `cryptography` is now a dependency.

### Removed

- The task classifier, LLM task evaluator, execution strategy and model-tier switching (which
  silently replaced the configured model), regex completion heuristics and `TASK_COMPLETE`
  markers, the automatic planning phase (replaced by `/plan`), and the progress tracker,
  scheduler, and animated display modules.
- Obsolete settings are dropped from `config.json` on load: `enable_task_classification`,
  `enable_task_evaluator`, `clean_display`, `display_mode`, `context_windows`,
  `model_max_context_override`, and others.

### Fixed

- The OSSF Scorecard job failed on every run: with `publish_results` it rejects workflows that
  have write permissions at the top level or container jobs. It now has its own workflow,
  `scorecard.yml`.
- Tool names with leaked chat-template tokens (gpt-oss: `read_file<|channel|>commentary`)
  are cleaned up. Before, the bad name was sent back to Bedrock and broke the conversation.
- Whitespace between reasoning blocks no longer prints blank lines.
- When a model writes a tool call as text instead of calling the tool (common with
  open-weight models such as gpt-oss), Kubrick asks it once to retry, instead of
  silently ending the turn.
- "Always allow" for a command like `cd /repo && pytest` saved the rule `cd`, which then
  auto-approved any command starting with `cd`. Rules now come from the real program
  (`pytest`, `git commit`, `python -m pytest`), and each part of a chained command
  (`&&`, `;`, `|`, `&`) must be read-only or allowed on its own.
- `2>/dev/null` was flagged as "writing to device files", and stopped read-only commands
  from being auto-approved.
- `OpenAI-compatible` base URLs without `/v1` (e.g. `http://host:11434`) now work.
- `kubrick -p` no longer hangs when stdin is an idle pipe (cron, IDE terminals, agent harnesses).
- Quitting without sending a message no longer saves an empty conversation.
- `--provider` no longer permanently rewrites the saved provider.
- `kubrick --help` no longer launches the setup wizard on a fresh machine.
- The Triton client no longer crashes on `text_output` values that parse as JSON scalars
  (`"42"`, `"null"`).
- Streaming reads whatever bytes have arrived instead of waiting for fixed-size buffers.
- `/config` no longer displays API keys.
- Tests no longer write to the real `~/.kubrick`.
- `docs/TRITON.md`:
  - the example model now uses the decoupled response sender
  - request parameters are read correctly
  - a working example is included under `examples/triton/`
  - removed references to CLI flags and environment variables that don't exist

### Security

- Plaintext API keys found in `config.json` from 0.1.x are migrated into the credential store
  and removed from the file. Consider rotating them.
- `~/.kubrick` is created with mode `0700`; credential files are written with `0600`.
- `.env` and `.env.*` are gitignored (except `.env.example`), so credential files kept in a
  checkout can't be committed by accident. Pasted AWS keys are hidden as you type (only
  the length is shown).

## Version 0.1.6

### Enhancements

#### 1. Clean Display Mode

- **Suppressed JSON Tool Calls**: Raw `\`\`\`tool_call` JSON blocks are now hidden during streaming for cleaner output
- **Full Visibility Maintained**: All agent responses, tool execution messages, and progress indicators remain visible
- **Configurable**: Enable/disable via `clean_display` config option (enabled by default)
- **Benefits**:
  - Cleaner, more professional interface
  - Reduced visual clutter
  - Full transparency into agent actions
  - All functionality preserved

**Configuration**:
```json
{
  "clean_display": true  // Default: enabled
}
```

**What You See**:
- Agent natural language responses
- Tool execution status (`→ Called write_file`, `✓ write_file succeeded`)
- Iteration progress (`→ Agent iteration 1/15`)
- Context management messages

**What's Hidden**:
- Only the raw JSON `\`\`\`tool_call {...}` blocks

See [docs/CLEAN_DISPLAY_MODE.md](docs/CLEAN_DISPLAY_MODE.md) for details.

#### 2. Running Status Indicator

- **Persistent Status Bar**: Shows animated spinner when agent is active
- **Always Visible**: Replaces "Type /help for options" with `⠋ Agent running...` during processing
- **Automatic Management**: Status set at agent start, cleared on completion (via finally block)
- **Better UX**: Eliminates the "frozen program" feeling during LLM thinking
- **No Emojis**: Clean, professional display without emoji clutter

**Status Lifecycle**:
- During agent work: `⠋ Agent running...` in status bar
- During tool execution: Spinner with action description (`⠙ Writing /path/to/file.py`)
- After completion: Status bar returns to normal (`Type /help for options`)

**Benefits**:
- Continuous feedback that system is working
- Professional, polished interface
- Clear understanding of agent activity
- Reduces user anxiety during long operations

See [docs/RUNNING_STATUS_INDICATOR.md](docs/RUNNING_STATUS_INDICATOR.md) for details.

#### 3. Enhanced Session Statistics

- **New SessionStats Class**: Centralized tracking of session metrics in `kubrick_cli/ui.py`
- **Real-time Statistics**: Live updates in status bar
  - Runtime duration
  - Files created/modified
  - Lines added/deleted
  - Tool calls executed
- **Running Status Integration**: SessionStats now manages running indicator state
- **Spinner Animation**: Braille pattern spinner for minimal visual footprint

**Display Example**:
```
Type /help for options    Runtime: 45s  Files: +3  Lines: +127  Tools: 8  Tokens: 15234
```

#### 4. Animated Display System

- **New Module**: `kubrick_cli/animated_display.py` for managing display states
- **StreamBuffer**: Intelligent buffer that suppresses JSON while preserving all other content
- **ToolProgress**: Clean tool execution display without emojis
- **Tool-Specific Verbs**: Context-aware action descriptions
  - `write_file` → "Writing"
  - `edit_file` → "Editing"
  - `run_bash` → "Running"
  - `search_code` → "Searching"

#### 5. Critical Bug Fixes

**StreamBuffer Display Bug** (Critical):
- **Issue**: Agent stopped generating tool calls, kept apologizing
- **Root Cause**: StreamBuffer was suppressing ALL text when no tool call was present
- **Fix**: Properly handle non-tool-call content - display everything normally when no JSON blocks detected
- **Impact**: Agent now works reliably for all tasks

**Task Evaluator Issues**:
- **Issue**: Evaluator causing agent to stop working or apologize repeatedly
- **Fix**: Disabled by default (`enable_task_evaluator: false`)
- **Status**: Marked as experimental feature

**Indentation Error**:
- **Issue**: `UnboundLocalError` in evaluator code
- **Fix**: Properly indented evaluator logic inside conditional block

See [docs/v0.1.6_FIXES.md](docs/v0.1.6_FIXES.md) for detailed analysis.

#### 6. Security Infrastructure

- **New Security Workflow**: Comprehensive automated security scanning (`.github/workflows/security.yml`)
- **Multiple Scanners**:
  - CodeQL: Semantic code analysis
  - Bandit: Python security linter
  - Semgrep: Static analysis for vulnerabilities
  - Safety: Dependency vulnerability checking
  - Trivy: Docker image vulnerability scanning
- **OSSF Scorecard**: Automated security health metrics
- **Security Badge**: Added to README for transparency

**New Documentation**:
- `docs/SECURITY.md` - Security policy, reporting vulnerabilities, best practices
- Security scanning results visible in GitHub Actions

#### 7. Documentation Improvements

**README.md Simplification**:
- Reduced from 240 lines to 99 lines
- Removed extensive Docker permission explanations (moved to DOCKER.md)
- Removed provider flag examples (setup wizard handles this)
- Added practical example showing Kubrick in action
- Simplified features list (no emojis)
- More professional and approachable for new users

**WIKI.md Enhancements**:
- Added "Display Options" section documenting `clean_display`
- Added "Task Evaluator" section with experimental warning
- Documented all new configuration options
- Enhanced troubleshooting sections
- Added usage examples for new features

**New Documentation Files**:
- `docs/CLEAN_DISPLAY_MODE.md` - Complete guide to clean display
- `docs/RUNNING_STATUS_INDICATOR.md` - Running status implementation details
- `docs/v0.1.6_FIXES.md` - Critical bug fix documentation
- `docs/SECURITY.md` - Security policy and guidelines

#### 8. Configuration Updates

**New Options**:
```json
{
  "clean_display": true,              // Hide JSON tool calls (default: enabled)
  "enable_task_evaluator": false,     // Experimental evaluator (default: disabled)
  "evaluator_model": "gpt-4o-mini"    // Model for task evaluation
}
```

**Updated Defaults**:
- `clean_display`: `true` - Cleaner output by default
- `enable_task_evaluator`: `false` - Disabled to prevent interference

#### 9. Code Quality Improvements

- **Removed Unused Variable**: Fixed unused `full_path` variable in `main.py:609`
- **Black Formatting**: Applied black formatting across all modified files
- **Flake8 Compliance**: Resolved linting issues
- **Type Annotations**: Improved type hints in new modules

### Bug Fixes

1. **Critical: StreamBuffer suppression bug** - Agent now generates tool calls properly
2. **Task evaluator interference** - Disabled by default to prevent agent disruption
3. **Indentation error in evaluator** - Fixed UnboundLocalError
4. **Display freeze perception** - Running status indicator provides continuous feedback
5. **Unused variable cleanup** - Removed unused `full_path` and `file_path` variables

### Files Added

- `kubrick_cli/ui.py` - SessionStats and UI helper classes
- `kubrick_cli/animated_display.py` - StreamBuffer and display management
- `kubrick_cli/evaluator.py` - Task evaluator (experimental)
- `.github/workflows/security.yml` - Security scanning workflow
- `docs/SECURITY.md` - Security policy and guidelines
- `docs/CLEAN_DISPLAY_MODE.md` - Clean display documentation
- `docs/RUNNING_STATUS_INDICATOR.md` - Status indicator documentation
- `docs/v0.1.6_FIXES.md` - Critical bug fix documentation

### Files Modified

- `kubrick_cli/main.py` - Integration of SessionStats, clean display, and running status
- `kubrick_cli/agent_loop.py` - Enhanced display integration, status management, fixed evaluator bug
- `kubrick_cli/config.py` - Added new configuration options with defaults
- `kubrick_cli/context_manager.py` - Improved context handling
- `kubrick_cli/__init__.py` - Export new UI classes
- `kubrick_cli/scheduler.py` - Minor formatting updates
- `README.md` - Simplified and modernized (240 → 99 lines)
- `docs/WIKI.md` - Comprehensive updates for new features
- `pyproject.toml` - Version bump to 0.1.6
- `.github/workflows/cd.yml` - Enhanced CD workflow

### Migration Notes

**For Existing Users**:
- Clean display is enabled by default - disable with `/config clean_display false` if needed
- Task evaluator is disabled by default - enable with `/config enable_task_evaluator true` (experimental)
- All existing functionality preserved - new features enhance UX without breaking changes

**Configuration**:
- No config changes required - new defaults work well
- Optional: Explore clean display mode for better UX
- Optional: Try task evaluator (experimental, may cause issues)

### Testing

All changes tested with:
- Simple tasks (file creation, editing)
- Complex tasks (multi-step planning and execution)
- Long-running operations (verify status indicator)
- Error conditions (verify clean error display)

**Test Results**:
- ✅ Agent generates tool calls properly
- ✅ Clean display suppresses only JSON
- ✅ Running status indicator works reliably
- ✅ Tool execution messages always visible
- ✅ Tasks complete successfully

### Known Issues

**Minor: First Iteration Apology**
- Occasionally the agent says "I apologize for the confusion" on iteration 1-2
- Does not prevent task completion
- Cosmetic issue only

### Recommendations

1. **Keep clean_display enabled** (default) - Better UX, fully functional
2. **Keep task_evaluator disabled** (default) - Prevents interference
3. **For debugging**: Disable clean_display temporarily to see raw JSON
4. **Update regularly**: `pip install --upgrade kubrick-cli`

---

## Version 0.1.5

### Enhancements

#### 1. Docker Wrapper Installation Scripts

- **One-Command Install**: Easy installation via `curl | sh` for streamlined Docker usage
- **`kubrick-docker` Wrapper**: Creates a convenient CLI wrapper that handles all Docker complexity
- **Smart Image Fallback**: Automatically tries Docker Hub → GHCR → Local build (if configured)
- **Automatic Configuration**:
  - Installs to `~/.local/bin/kubrick-docker`
  - Handles all volume mounts automatically
  - Uses caller's UID/GID for correct file permissions
  - Detects TTY for interactive mode
  - Creates config directory before mounting (prevents root-owned dirs)

**Installation:**

```bash
# Install
curl -fsSL https://raw.githubusercontent.com/rcland12/kubrick-cli/master/scripts/install-kubrick-docker.sh | sh

# Uninstall
curl -fsSL https://raw.githubusercontent.com/rcland12/kubrick-cli/master/scripts/uninstall-kubrick-docker.sh | sh
```

**Usage:**

```bash
cd /path/to/your/project
kubrick-docker
kubrick-docker --triton-url my-server:8000
```

**Advanced Configuration:**

The wrapper respects environment variables for customization:

- `KUBRICK_DOCKERHUB_IMAGE`: Override Docker Hub image
- `KUBRICK_GHCR_IMAGE`: Override GHCR image
- `KUBRICK_BUILD_CONTEXT`: Enable local build fallback
- `KUBRICK_NETWORK_MODE`: Change network mode (default: host)

**Files Added:**

- `scripts/install-kubrick-docker.sh` - Installation script
- `scripts/uninstall-kubrick-docker.sh` - Uninstallation script

#### 2. GitHub Container Registry Support

- **Dual Docker Registry Publishing**: Docker images now published to both Docker Hub and GitHub Container Registry
- **GitHub Packages Integration**: Images available at `ghcr.io/rcland12/kubrick-cli`
- **Registry Options**:
  - Docker Hub: `docker pull rcland12/kubrick-cli:latest`
  - GitHub Packages: `docker pull ghcr.io/rcland12/kubrick-cli:latest`

**Benefits:**

- Better integration with GitHub ecosystem
- Version tracking linked to GitHub releases
- Package visibility on GitHub profile
- Redundancy if one registry has issues
- Free unlimited storage and bandwidth for public repos

**Documentation Updated:**

- **README.md**:
  - Added prominent "Understanding Docker File Permissions" section
  - Restructured Docker installation with 3 clear options
  - Added benefits list for wrapper script
  - Added Docker Compose setup instructions
  - All examples include `--user $(id -u):$(id -g)`
- **docs/DOCKER.md**:
  - Added comprehensive "Understanding File Permissions" section
  - Restructured with three installation methods
  - All manual Docker commands include `--user $(id -u):$(id -g)`
  - Docker Compose section emphasizes UID/GID export requirement
  - Enhanced permission troubleshooting with 4 solutions
  - Added technical details about `chmod 1777` approach
- **docs/WIKI.md**:
  - Updated Docker installation section with wrapper option
  - All Docker commands include `--user $(id -u):$(id -g)`
  - Added permission troubleshooting with before/after examples
- **Consistency**: Every Docker command in all documentation now includes proper UID/GID handling
- CD workflow automatically publishes to both registries

#### 3. Code Quality Improvements

- **Fixed unused variables**: Removed unused `result` variable in `kubrick_cli/planning.py`
- **Fixed display preview**: Tool result previews now properly displayed (was creating preview but not showing it)
- **Fixed flake8 issues**: Resolved f-string and unused variable warnings in tests
- **Added security annotation**: Added `# nosec` comment for validated shell=True usage in tools.py

---

## Version 0.1.3

### Enhancements

#### 1. Conversation Loading from File Paths

- **Enhanced `--load` option**: Can now load conversations from arbitrary file paths, not just conversation IDs
- **Flexible loading**:
  - By ID: `kubrick --load 20240118_143022` (loads from `~/.kubrick/conversations/`)
  - By path: `kubrick --load /path/to/conversation.json` (loads from anywhere)
  - Supports relative paths: `kubrick --load ../saved/conv.json`
  - Supports `~` expansion: `kubrick --load ~/backup/conversation.json`

**Use Cases:**

- Share conversations between machines
- Load exported/backed-up conversations
- Load conversations from custom locations
- Integrate with version control (e.g., save conversations in project repos)

**Example:**

```bash
# Export a conversation
cp ~/.kubrick/conversations/20240118_143022.json ~/my-project/ai-session.json

# Load it later from project directory
kubrick --load ~/my-project/ai-session.json
```

#### 2. Improved Help Documentation

- **Enhanced `/help` command**: Now shows all available in-session commands
- **Added missing commands to help**:
  - `/debug` - Show debug information (conversation ID, messages, provider, model)
  - `/debug prompt` - Display the full system prompt
  - `exit` / `quit` - Save and exit (was working but not documented)
- **Clarified `--load` usage**: Added note explaining `--load` is a startup argument, not an in-session command
- **Updated CLI `--help`**: Main help now includes all in-session commands
- **Consistent documentation**: All help text now matches across `/help`, `--help`, and WIKI.md

**Before:**

```
/help only showed: /save, /list, /config, /delete (missing /debug, exit/quit)
```

**After:**

```
/help shows: /save, /list, /load, /config, /delete, /debug, /debug prompt, /help, exit, quit
```

#### 3. In-Session Conversation Loading with Numbered Selection

- **New `/load` in-session command**: Load conversations without restarting Kubrick
- **Numbered selection**: `/list` now shows numbered conversations for easy loading
- **Three loading modes**:
  - By number: `/load 1` (loads conversation #1 from last `/list`)
  - By ID: `/load 20240118_143022` (loads by conversation ID)
  - By path: `/load /path/to/conversation.json` (loads from file path)

**User Workflow:**

```bash
You: /list
# Shows numbered table:
# #  ID                Messages  Working Dir        Modified
# 1  20240119_120000  15        /home/user/proj    2024-01-19 12:00
# 2  20240118_143022  23        /home/user/proj    2024-01-18 14:30

You: /load 1
# ✓ Loaded conversation 20240119_120000 (15 messages)
```

**Benefits:**

- No need to restart Kubrick to switch conversations
- Simple numbered selection instead of copying long IDs
- Seamless workflow: list → load by number
- Still supports loading by ID or file path for flexibility

**Updated Help:**

- `/help` now shows `/load <#|ID>` command
- `/list` displays hint: "Use '/load <#>' to load a conversation by number"
- Main CLI help (`kubrick --help`) updated with `/load` command

---

## Version 0.1.2 - Testing Infrastructure & UTF-8 Fix

### New Features

#### 1. Comprehensive Test Suite

- **100+ Unit Tests**: Added comprehensive pytest test suite with full mocking
- **test_tool_executor.py**: 22 tests for file operations, bash commands, directory creation
- **test_safety.py**: 32 tests for dangerous command detection and safety validation
- **test_completion_detector.py**: 24 tests for agent loop completion logic
- **test_triton_client_unit.py**: 22 tests for Triton client with mocked HTTP connections
- **No External Dependencies**: All tests use mocking - no Triton server required
- **Fast Execution**: All 102 tests run in ~0.6 seconds

#### 2. CI/CD Integration

- **GitHub Actions Workflow**: Automated testing on push and pull requests
- **Multi-Python Testing**: Tests run on Python 3.8, 3.9, 3.10, 3.11, 3.12
- **Multi-OS Testing**: Tests on Ubuntu, macOS, and Windows
- **Code Coverage**: Automated coverage reporting with 49% overall coverage
- **Code Quality**: Automated linting (flake8) and formatting checks (black)

#### 3. Test Coverage Highlights

- **100% coverage** - SafetyManager (security-critical component)
- **95% coverage** - TritonLLMClient (including UTF-8 fix validation)
- **92% coverage** - ToolExecutor (file operations and command execution)
- **83% coverage** - TritonProvider
- **79% coverage** - ProviderAdapter base class
- **77% coverage** - KubrickConfig

#### 4. Developer Tools

- **pytest Integration**: Professional testing framework with fixtures and mocking
- **pytest-cov**: Coverage reporting and analysis
- **pytest-mock**: Enhanced mocking capabilities
- **conftest.py**: Shared test fixtures and configuration
- **TESTING.md**: Comprehensive testing documentation

### Bug Fixes

#### UTF-8 Decoding Error (Critical Fix)

**Issue**: `'utf-8' codec can't decode bytes in position 1022-1023: unexpected end of data`

**Root Cause**: TritonLLMClient was decoding 1024-byte chunks immediately, which could split multi-byte UTF-8 characters (emojis, special characters) in the middle.

**Solution**:

- Changed streaming logic to keep data as bytes until complete lines are received
- Only decode complete lines (newlines are single-byte safe split points)
- Added error handling for malformed data
- Added comprehensive tests to validate UTF-8 handling, including split multi-byte characters

**Impact**: Fixed streaming responses with emojis, international characters, and other multi-byte UTF-8 content.

### Testing

Run the test suite:

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run with coverage
pytest --cov=kubrick_cli --cov-report=term-missing

# Run specific test file
pytest tests/test_tool_executor.py -v
```

### Documentation

- **TESTING.md**: Complete testing guide with examples
- **Updated README.md**: Added Development section with testing instructions
- **Test Coverage Reports**: Available in CI/CD pipeline

### Development Improvements

- Added flake8 to dev dependencies for code linting
- Added pytest-mock for enhanced test mocking capabilities
- Organized tests with clear class structure and fixtures
- Added pytest markers for test categorization (unit, integration, slow)

### Files Added

- `tests/test_tool_executor.py` - ToolExecutor unit tests
- `tests/test_safety.py` - SafetyManager unit tests
- `tests/test_completion_detector.py` - CompletionDetector unit tests
- `tests/test_triton_client_unit.py` - TritonLLMClient unit tests
- `tests/conftest.py` - Shared pytest fixtures
- `TESTING.md` - Testing documentation
- `.github/workflows/test.yml` - CI/CD test workflow (optional, ci.yml already covers this)

### Files Modified

- `kubrick_cli/triton_client.py` - Fixed UTF-8 decoding bug in streaming
- `pyproject.toml` - Added pytest-mock and flake8 dependencies
- `pytest.ini` - Added test markers and configuration
- `README.md` - Added Development and Testing sections

---

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
