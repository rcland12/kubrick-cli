# Kubrick CLI Changelog

## Version 0.1.7

### Major Architectural Improvements

#### 1. Sequential Observe-Act Loop Architecture

**Complete redesign of agent execution model for reliability over speed.**

- **Sequential Execution**: Changed from parallel batching to iterative observe-act loop
- **One Step at a Time**: Agent now observes results before deciding next action
- **Immediate Feedback**: Mistakes caught immediately, not 5 iterations later
- **Self-Correcting**: Agent can adapt based on what it learns at each step

**Configuration Changes**:

```json
{
  "max_iterations": 25, // Increased from 15 (more steps needed for sequential)
  "max_tools_per_turn": 2, // Reduced from 5 (forces observe-act loop)
  "enable_parallel_tools": false // Sequential by default (was true)
}
```

**Benefits**:

- Much more reliable task completion
- Agent sees results before proceeding
- Fewer failed attempts and retries
- Better debugging and error recovery
- More predictable behavior

**Trade-offs**:

- Slower execution (6-8 iterations vs 2-3)
- More API calls per task
- Higher token usage (but fewer wasted tokens on failures)

#### 2. Permission System with Directory Caching

**Arrow-key selection for file writes and bash commands with persistent permissions.**

- **Interactive Permissions**: Uses questionary for clean arrow-key selection
- **Directory-Based Caching**: Permissions persist for entire directories
- **Session Caching**: "For this conversation" option stores in memory
- **Flexible Control**:
  - "Yes, just this once" - One-time approval
  - "Yes, for this conversation" - Session-wide approval
  - "Yes, always in this directory" - Permanent directory permission
  - "No, not this time" - Reject this action
  - "No, never in this directory" - Permanent directory block

**Storage**: `~/.kubrick/config.json` now includes `directory_permissions` field

**Example**:

```
Kubrick wants to write to: /home/user/project/src/main.py

How would you like to respond?
❯ Yes, just this once
  Yes, for this conversation
  Yes, always in this directory
  No, not this time
  No, never in this directory
```

### Enhanced System Prompts

#### 3. Critical: Never Show Code Instead of Writing It

**Fixed #1 most common bug: Agent displaying code in markdown instead of calling write_file.**

- **New Prominent Warning**: Added explicit section showing wrong vs correct approach
- **Anti-Pattern Example**: Shows exact mistake (displaying Dockerfile in markdown block)
- **New Rule #10**: "NEVER SHOW CODE IN MARKDOWN INSTEAD OF WRITING"
- **Clear Message**: "Showing code ≠ Writing code. Use write_file tool, not markdown blocks!"

**Impact**: Prevents agent from showing code to user and then returning empty responses.

#### 4. Docker & DevOps Best Practices

**Comprehensive Docker guidance to prevent common mistakes.**

- Check for pyproject.toml vs requirements.txt before creating Dockerfiles
- Multi-stage builds for production images
- Security best practices (non-root users, minimal base images)
- Health checks and proper signal handling
- Cache optimization strategies

**Critical Addition**: Warning about glob pattern limitations

- Python glob doesn't support bash brace expansion `{file1,file2,file3}`
- Documented in system prompt, planning prompt, and ARCHITECTURE.md

#### 5. Sequential Execution Guidance

**Explicit examples teaching observe-act loop pattern.**

- Example 4 shows wrong (batching) vs correct (sequential) approach
- Clear iteration-by-iteration walkthrough
- Emphasis on observing results before next action
- Tool result trust guidance

### Bug Fixes

#### Critical Fixes

1. **Tool Calls Not Executing Before TASK_COMPLETE** (Critical)
   - **Issue**: Agent included TASK_COMPLETE in same response as write_file, completion check happened before tool execution
   - **Fix**: Only exit if `is_complete and not tool_calls`
   - **Impact**: Tools now execute properly before completion

2. **Planning Mode Apology Loop** (Critical)
   - **Issue**: Agent returned empty responses saying "I'm sorry, but I can't proceed without results"
   - **Root Cause**: Planning mode was copying entire base_messages with conflicting system prompts
   - **Fix**: Created clean planning-only messages without main system prompt
   - **Impact**: Planning mode now explores reliably

3. **Empty Response Infinite Loop** (Critical)
   - **Issue**: Agent returned 10+ consecutive empty responses
   - **Fix**: Updated completion detector to catch empty responses (len == 0)
   - **Impact**: Prevents infinite loops

4. **Agent Hallucinating Tool Results** (Critical)
   - **Issue**: Agent returned fake JSON like `{"files": ["requirements.txt"]}` without tool calls
   - **Fix**: Added hallucination detector that stops if agent returns JSON without valid tool calls
   - **Added**: "CRITICAL: Never Hallucinate Tool Results" system prompt section
   - **Impact**: Prevents agent from making up results

5. **Premature Completion** (High Priority)
   - **Issue**: Agent said "Successfully created. Now, let's verify..." but completion detector saw "successfully" and stopped
   - **Fix**: Added continuation_patterns that check BEFORE conclusive_patterns
   - **Patterns**: `now let's`, `next I'll`, `need to verify`, etc.
   - **Impact**: Agent completes full task instead of stopping mid-work

6. **Glob Pattern Brace Expansion** (High Priority)
   - **Issue**: `list_files(pattern="{requirements.txt,pyproject.toml}")` returned 0 results
   - **Root Cause**: Python pathlib.glob() doesn't support bash brace expansion
   - **Fix**: Added explicit warnings in system prompt, planning prompt, and ARCHITECTURE.md
   - **Workaround**: Check files individually or use wildcards
   - **Impact**: Agent can now find dependency files

7. **Self-Doubt Loop** (Medium Priority)
   - **Issue**: Agent said "It seems like the file was not created successfully" even after ✓ succeeded message
   - **Fix**: Added "TRUST TOOL SUCCESS MESSAGES" rule to Professional Behavior section
   - **Impact**: Agent trusts tool results instead of second-guessing

8. **F-String Formatting Bug** (Medium Priority)
   - **Issue**: Failed to start with "Invalid format specifier ' ["..."]' for object of type 'str'"
   - **Root Cause**: Added `{"files": ["..."]}` in system prompt without escaping curly braces
   - **Fix**: Changed to `{{"files": ["..."]}}` (double braces for escaping)
   - **Impact**: Application starts without errors

#### Test Fixes

9. **test_conclusive_response_here_is_summary**
   - **Issue**: Test expected "here is the summary" to be detected as conclusive
   - **Root Cause**: Pattern only matched "here is" for creative content (poem, story, joke)
   - **Fix**: Added "summary" to the list: `r"\bhere(?:'s| is) (?:the |a )?(?:poem|story|joke|summary)"`
   - **Impact**: Test passes, agent correctly detects summary responses as conclusive

### Files Added

- `ARCHITECTURE.md` - Comprehensive documentation of sequential observe-act loop architecture
- Updated system prompts throughout codebase

### Files Modified

- `kubrick_cli/main.py`:
  - Lines 70-74: SafetyManager now receives kubrick_config and working_dir for persistent permissions
  - Lines 360-489: Added Docker & DevOps Best Practices section
  - Lines 491-547: Added Self-Verification section
  - Lines 553-590: Added Docker-Specific Best Practices with glob pattern warning
  - Lines 577-578: Critical warning about glob pattern limitations
  - Lines 592-614: Enhanced Professional Behavior section with tool trust guidance
  - Lines 616-647: Added "Agentic Behavior - SEQUENTIAL EXECUTION" section
  - Lines 651-666: Added "CRITICAL: Never Hallucinate Tool Results" section
  - Lines 673-676: Strengthened tool call format requirement
  - Lines 766-767: New Rule #10: NEVER SHOW CODE IN MARKDOWN INSTEAD OF WRITING
  - Lines 787-822: Added prominent "CRITICAL: Never Show Code Instead of Writing It" section
  - Lines 822-876: Example 4 showing sequential observe-act loop

- `kubrick_cli/config.py`:
  - Lines 96-100: Updated default config values (max_iterations: 25, max_tools_per_turn: 2, enable_parallel_tools: false)
  - Lines 153-155: Added directory_permissions field
  - Lines 176-208: Added get_directory_permission and set_directory_permission methods

- `kubrick_cli/safety.py`:
  - Lines 3, 9-12: Added questionary and Path imports
  - Lines 82-99: Updated **init** to accept kubrick_config and working_dir
  - Lines 219-345: Rewrote check_file_write_permission with arrow-key selection and directory caching
  - Lines 347-471: Updated check_bash_permission with same approach

- `kubrick_cli/planning.py`:
  - Lines 78-80: Fixed critical bug - removed base_messages.copy() to avoid conflicting prompts
  - Lines 82-99: Created clean planning-specific system prompt
  - Lines 95-99: Added critical rules: "ACT IMMEDIATELY", "DON'T APOLOGIZE"
  - Lines 130-131: Added warning about glob pattern limitations
  - Lines 139-142: Added note for Docker tasks to check dependency files

- `kubrick_cli/agent_loop.py`:
  - Lines 308-313: Fixed completion check to only exit if `is_complete and not tool_calls`
  - Lines 344: Same fix for evaluator completion
  - Lines 419-450: Fixed completion detector stuck loop threshold (4→8 iterations), added empty response detection
  - Lines 96-112: Added continuation pattern detection to prevent premature completion
  - Lines 438-452: Added hallucination detector
  - Lines 453-462: Added message when limiting tool calls
  - Line 119: Fixed conclusive pattern to include "summary"

- `pyproject.toml`:
  - Line 7: Version bumped to 0.1.7
  - Line 19: Added questionary>=2.0.0 dependency

### Known Issues

**Glob Pattern Limitations**:

- Python's pathlib.glob() doesn't support bash brace expansion `{file1,file2,file3}`
- Workaround: Check files individually or use wildcards like `*requirements*.txt`
- Fully documented in ARCHITECTURE.md and system prompts

### Migration Notes

**For Existing Users**:

- Sequential execution is now default - tasks will be slower but much more reliable
- Permission system activates on first file write or bash command
- All existing functionality preserved
- Config changes apply automatically to new conversations

**Configuration Impact**:

- Existing config files automatically upgraded with new defaults
- You can override defaults: `/config max_tools_per_turn 5` to re-enable batching
- Permission cache stored in `~/.kubrick/config.json`

**Behavioral Changes**:

- Agent now works more slowly but completes tasks correctly
- More iterations per task (typical: 6-10 instead of 2-4)
- Agent observes results before proceeding (observe-act loop)
- Parallel execution disabled by default (can re-enable per task)

### Recommendations

1. **Keep sequential execution enabled** - Much more reliable, worth the slowdown
2. **Trust the permission system** - Directory-based caching prevents repeated prompts
3. **For debugging**: Use `/debug prompt` to see full system prompt
4. **Review ARCHITECTURE.md** - Understand the reasoning behind architectural changes
5. **Update regularly**: `pip install --upgrade kubrick-cli`

### Testing

All changes tested with:

- Simple file operations (create, edit, read)
- Complex multi-step tasks (Docker/pytest scenario)
- Permission system (various approval combinations)
- Planning mode (exploration and plan generation)
- Error conditions (hallucination detection, empty responses)

**Test Results**:

- ✅ Sequential execution working reliably
- ✅ Permission system caching correctly
- ✅ Planning mode explores without apology loops
- ✅ Completion detection prevents premature exits
- ✅ Hallucination detector stops fake results
- ✅ All pytest tests passing (102 tests)

---

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
  "clean_display": true // Default: enabled
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
  "clean_display": true, // Hide JSON tool calls (default: enabled)
  "enable_task_evaluator": false, // Experimental evaluator (default: disabled)
  "evaluator_model": "gpt-4o-mini" // Model for task evaluation
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
