# Testing

The suite runs in about 13 seconds with no network, model server, API keys, or GPU, and
never touches your real `~/.kubrick`.

```bash
make dev                                      # once: .venv with Kubrick + dev tools
make test                                     # everything
make test ARGS="tests/test_permissions.py"    # one file
.venv/bin/pytest tests/test_agent_loop.py -k denial   # filter by name
.venv/bin/pytest --lf                         # rerun last failures
make lint                                     # black --check + flake8, as CI runs them
```

Coverage: `.venv/bin/pytest --cov=kubrick_cli --cov-report=term-missing`.

## How the tests are isolated

`tests/conftest.py` has an autouse fixture that, for every test:

- points `HOME` at a temporary directory (so `~/.kubrick` is fresh)
- clears provider API-key variables and `KUBRICK_*` overrides
- forces the encrypted-file credential store, so the OS keychain is never touched

`tests/fake_openai_server.py` is a real HTTP server on localhost that streams scripted
Chat Completions responses (text, reasoning, tool calls). `tests/test_end_to_end.py`
runs `kubrick -p ...` against it. That is the best place for new behavior tests; prefer it
over mocking internals.

## Layout

| File | Covers |
|---|---|
| `test_end_to_end.py` | `kubrick -p` against the fake server: tools, permissions, piped input |
| `test_agent_loop.py` | agent loop with a scripted provider: denials, refusals, interrupts, parallel tools |
| `test_openai_provider.py` | OpenAI / local-server provider: streaming, reasoning, tool-call recovery |
| `test_anthropic_provider.py` | Anthropic request building, thinking, retries (mocked HTTP) |
| `test_bedrock_provider.py` | Bedrock Converse with a fake boto3 client |
| `test_triton_provider.py`, `test_triton_client_unit.py` | Triton provider and client |
| `test_tool_calling.py` | text tool-call protocol (fallback for servers without tools) |
| `test_tool_executor.py` | file, search, and shell tools |
| `test_permissions.py` | permission modes, read-only commands, "always allow" rules |
| `test_safety.py` | dangerous-command patterns |
| `test_context_manager.py` | context tracking and compaction |
| `test_credentials.py` | encrypted credential store |
| `test_config.py` | settings precedence, migrations, saved conversations |
| `test_ui.py` | `/` command menu, pickers, permission prompt, setup wizard |
| `test_updater.py` | `kubrick update`: version checks, install detection |

`test_ui.py` drives real prompt_toolkit sessions through a pipe, spacing out keystrokes
the way a person would type. Wizard tests replace `setup_wizard.select` / `ask_text` with
scripted answers.

## CI

`ci.yml` runs the lint job (black, flake8, bandit) and `pytest` on Python 3.9–3.13 on
Ubuntu for every push and pull request. See [CICD.md](CICD.md).

To reproduce a failure on another Python version without touching your system:

```bash
uv venv --python 3.9 /tmp/k39
uv pip install --python /tmp/k39/bin/python -e ".[dev]"
/tmp/k39/bin/pytest
```

## Manual testing

```bash
make run                         # interactive, on a throwaway copy of examples/playground
make run ARGS='-p "fix the bugs" --permission-mode accept_edits'
make sandbox                     # same, inside Docker
make playground                  # restore the playground's bugs
make reset-home                  # forget dev config/keys, so the setup wizard runs again
```

Useful environment variables while testing the UI: `KUBRICK_SIMPLE_UI=1` (numbered prompts
instead of menus, as in Emacs `M-x shell`), `KUBRICK_ASCII=1`, `NO_COLOR=1`.
