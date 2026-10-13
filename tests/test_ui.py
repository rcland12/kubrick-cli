"""Tests for the interactive pieces: /command menu, pickers, and the setup wizard."""

import threading
import time

import pytest
from prompt_toolkit.application import create_app_session
from prompt_toolkit.document import Document
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from kubrick_cli import glyphs, setup_wizard, widgets
from kubrick_cli.config import KubrickConfig
from kubrick_cli.main import COMMANDS, _is_command, help_text
from kubrick_cli.providers.openai_provider import normalize_server_url
from kubrick_cli.ui import EnhancedPrompt, SlashCompleter, make_permission_prompt
from kubrick_cli.widgets import Choice
from tests.fake_openai_server import FakeOpenAIServer

DOWN = "\x1b[B"


def _completions(completer, text):
    return [c.text for c in completer.get_completions(Document(text), None)]


def _run_with_keys(target, keys, delay=0.4):
    """Run ``target()`` in a prompt_toolkit session fed ``keys`` one step at a time.

    Steps are spaced out so asynchronous completion has finished before the next
    key arrives, as it would for a person typing.
    """
    with create_pipe_input() as pipe:

        def feed():
            for key in keys:
                time.sleep(delay)
                pipe.send_text(key)

        thread = threading.Thread(target=feed, daemon=True)
        with create_app_session(input=pipe, output=DummyOutput()):
            thread.start()
            result = target()
        thread.join()
    return result


# --- URL normalization ---------------------------------------------------------


@pytest.mark.parametrize(
    "typed, expected",
    [
        ("192.168.1.56:11434", "http://192.168.1.56:11434/v1"),
        ("localhost:8000/", "http://localhost:8000/v1"),
        ("http://box:11434", "http://box:11434/v1"),
        ("http://box:11434/v1", "http://box:11434/v1"),
        ("https://gateway.corp/openai", "https://gateway.corp/openai"),
        ("  box:1234  ", "http://box:1234/v1"),
    ],
)
def test_normalize_server_url(typed, expected):
    assert normalize_server_url(typed) == expected


# --- Slash command completion ----------------------------------------------------


def test_slash_completer_matches_prefixes():
    completer = SlashCompleter(COMMANDS)
    assert _completions(completer, "/pr") == ["/provider"]
    assert set(_completions(completer, "/p")) == {"/provider", "/plan", "/permissions"}
    assert len(_completions(completer, "/")) == len(COMMANDS)


def test_slash_completer_stays_out_of_normal_text():
    completer = SlashCompleter(COMMANDS)
    assert _completions(completer, "fix /pr") == []
    assert _completions(completer, "/plan\nmore") == []
    assert _completions(completer, "/zzz") == []


def test_slash_completer_completes_arguments():
    def choices(command):
        return {"/model": [("qwen3:32b", "current"), ("llama3:8b", "")]}.get(
            command, []
        )

    completer = SlashCompleter(COMMANDS, choices)
    assert _completions(completer, "/model q") == ["qwen3:32b"]
    assert _completions(completer, "/model ") == ["qwen3:32b", "llama3:8b"]
    assert _completions(completer, "/model qwen3:32b extra") == []


def _prompt(tmp_path):
    return EnhancedPrompt(
        lambda: {}, tmp_path / "history", commands=COMMANDS, argument_choices=None
    )


def test_enter_without_arrows_submits_what_was_typed(tmp_path):
    result = _run_with_keys(lambda: _prompt(tmp_path).get_input(), ["/pr", "\r"])
    assert result == "/pr"


def test_arrow_then_enter_runs_the_highlighted_command(tmp_path):
    result = _run_with_keys(lambda: _prompt(tmp_path).get_input(), ["/pr", DOWN, "\r"])
    assert result == "/provider"


def test_command_that_needs_an_argument_waits_for_it(tmp_path):
    result = _run_with_keys(
        lambda: _prompt(tmp_path).get_input(), ["/loa", DOWN, "\r", "abc", "\r"]
    )
    assert result == "/load abc"


def test_is_command():
    assert _is_command("/model qwen")
    assert not _is_command("/etc/hosts has a typo")
    assert not _is_command("hello")


def test_help_lists_every_command():
    text = help_text()
    assert all(c.name in text for c in COMMANDS)


# --- Pickers ---------------------------------------------------------------------

CHOICES = [
    Choice("a", "Alpha"),
    Choice("b", "Bravo", current=True),
    Choice("c", "Charlie"),
]


def _menu(keys, choices=CHOICES, filterable=False, start=0):
    return _run_with_keys(
        lambda: widgets._select_menu("Pick", choices, start, filterable, 10),
        keys,
        delay=0.15,
    )


def test_menu_arrows_and_enter():
    assert _menu([DOWN, DOWN, "\r"]).value == "c"
    assert _menu([DOWN, DOWN, DOWN, "\r"]).value == "a"  # wraps around


def test_menu_number_and_letter_shortcuts():
    assert _menu(["2"]).value == "b"
    keyed = [Choice("y", "Yes", key="y"), Choice("n", "No", key="n")]
    assert _menu(["n"], choices=keyed).value == "n"


def test_menu_escape_cancels():
    assert _menu(["\x1b"]) is None


def test_menu_filtering():
    models = [Choice(m, m) for m in ("llama3:8b", "qwen3:32b", "qwen3:8b", "mistral")]
    assert (
        _menu(["qw", DOWN, "\r"], choices=models, filterable=True).value == "qwen3:8b"
    )


def test_select_starts_on_current_and_falls_back_to_numbers(monkeypatch):
    asked = {}

    def fake_ask(prompt, default=None, **kwargs):
        asked["default"] = default
        return "3"

    monkeypatch.setattr(widgets.Prompt, "ask", fake_ask)
    assert widgets.select("Pick", CHOICES) == "c"  # stdin isn't a TTY under pytest
    assert asked["default"] == "2"  # the current choice


def test_simple_ui_env_disables_menus(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setenv("KUBRICK_SIMPLE_UI", "1")
    assert not widgets.rich_ui_available()


def test_ascii_glyphs(monkeypatch):
    monkeypatch.setenv("KUBRICK_ASCII", "1")
    assert glyphs.glyph("pointer") == ">"
    monkeypatch.setenv("KUBRICK_ASCII", "0")
    assert glyphs.glyph("pointer") == "›"


# --- Permission prompt -----------------------------------------------------------


class _Renderer:
    def permission_panel(self, *args):
        pass


@pytest.mark.parametrize(
    "picked, allowed, always, stop",
    [("y", True, False, False), ("a", True, True, False), (None, False, False, True)],
)
def test_permission_prompt(monkeypatch, picked, allowed, always, stop):
    monkeypatch.setattr("kubrick_cli.ui.select", lambda *a, **k: picked)
    answer = make_permission_prompt(_Renderer())("Run command?", "ls", rule="ls")
    assert (answer.allowed, answer.always, answer.stop) == (allowed, always, stop)


def test_permission_prompt_no_with_feedback(monkeypatch):
    monkeypatch.setattr("kubrick_cli.ui.select", lambda *a, **k: "n")
    monkeypatch.setattr("kubrick_cli.ui.ask_text", lambda *a, **k: "use pytest -x")
    answer = make_permission_prompt(_Renderer())("Run command?", "pytest")
    assert not answer.allowed and not answer.stop
    assert "use pytest -x" in answer.message


# --- Setup wizard ----------------------------------------------------------------


def _script(monkeypatch, selections, texts):
    """Answer the wizard's menus and text prompts from lists."""
    selections, texts = list(selections), list(texts)
    seen = []

    def fake_select(title, choices, **kwargs):
        seen.append(title)
        answer = selections.pop(0)
        return answer(choices) if callable(answer) else answer

    monkeypatch.setattr(setup_wizard, "select", fake_select)
    monkeypatch.setattr(setup_wizard, "ask_text", lambda *a, **k: texts.pop(0))
    return seen


def _value_of(label):
    return lambda choices: next(c.value for c in choices if c.label == label)


def test_wizard_local_server_adds_scheme_and_v1(monkeypatch, tmp_path):
    with FakeOpenAIServer([], models=("qwen3:32b", "llama3:8b")) as server:
        address = server.base_url.split("://")[1].rsplit("/v1", 1)[0]
        _script(
            monkeypatch,
            [_value_of("Local model server"), _value_of("Ollama"), "qwen3:32b"],
            [address],
        )
        config = KubrickConfig(skip_wizard=True, kubrick_dir=tmp_path / "k")
        settings = setup_wizard.SetupWizard.run(config)
    assert settings == {
        "provider": "openai_compatible",
        "openai_compatible_base_url": f"http://{address}/v1",
        "openai_compatible_model": "qwen3:32b",
    }


def test_wizard_unreachable_server_offers_retry(monkeypatch, tmp_path):
    with FakeOpenAIServer([], models=("m1",)) as server:
        good = server.base_url
        seen = _script(
            monkeypatch,
            [_value_of("vLLM"), "retry", "m1"],
            ["127.0.0.1:9", good],
        )
        config = KubrickConfig(skip_wizard=True, kubrick_dir=tmp_path / "k")
        meta = setup_wizard.ProviderFactory.get_provider_metadata("openai_compatible")
        settings = setup_wizard.SetupWizard.configure_provider(config, meta)
    assert "What now?" in seen
    assert settings["openai_compatible_base_url"] == good
    assert settings["openai_compatible_model"] == "m1"


def test_wizard_escape_cancels(monkeypatch, tmp_path):
    _script(monkeypatch, [None], [])
    config = KubrickConfig(skip_wizard=True, kubrick_dir=tmp_path / "k")
    with pytest.raises(KeyboardInterrupt):
        setup_wizard.SetupWizard.run(config)


def test_wizard_hosted_provider_stores_key_and_lists_models(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "kubrick_cli.providers.anthropic_provider.AnthropicProvider.list_models",
        lambda self: ["claude-opus-5-5", "claude-sonnet-5-5"],
    )
    monkeypatch.setattr(setup_wizard, "prompt_secret", lambda *a: "sk-ant-test")
    _script(
        monkeypatch,
        [_value_of("Anthropic (Claude)"), "high", _value_of("claude-sonnet-5-5")],
        [],
    )
    config = KubrickConfig(skip_wizard=True, kubrick_dir=tmp_path / "k")
    settings = setup_wizard.SetupWizard.run(config)
    assert settings == {
        "provider": "anthropic",
        "anthropic_effort": "high",
        "anthropic_model": "claude-sonnet-5-5",
    }
    assert config.credentials.get("anthropic_api_key") == "sk-ant-test"


def test_ask_block_keeps_pasted_lines(monkeypatch):
    monkeypatch.setattr(widgets, "rich_ui_available", lambda: True)
    paste = (
        "\x1b[200~export AWS_ACCESS_KEY_ID=A1\nexport AWS_SECRET_ACCESS_KEY=S1\x1b[201~"
    )
    text = _run_with_keys(lambda: widgets.ask_block("AWS credentials"), [paste, "\r"])
    from kubrick_cli.aws_credentials import parse_env_text

    assert parse_env_text(text) == {
        "AWS_ACCESS_KEY_ID": "A1",
        "AWS_SECRET_ACCESS_KEY": "S1",
    }


def test_wizard_bedrock_paste_stores_encrypted(monkeypatch, tmp_path):
    pytest.importorskip("boto3")
    monkeypatch.setattr(
        setup_wizard,
        "ask_block",
        lambda *a, **k: "AWS_ACCESS_KEY_ID=AKIA1\nAWS_SECRET_ACCESS_KEY=s\n"
        "AWS_REGION=us-gov-west-1",
    )
    monkeypatch.setattr(
        "kubrick_cli.providers.bedrock_provider.BedrockProvider.list_models",
        lambda self: ["openai.gpt-oss-120b-1:0", "us-gov.openai.gpt-oss-20b-1:0"],
    )
    _script(
        monkeypatch,
        [_value_of("Amazon Bedrock"), "paste", "openai.gpt-oss-120b-1:0"],
        ["us-gov-west-1"],
    )
    config = KubrickConfig(skip_wizard=True, kubrick_dir=tmp_path / "k")
    settings = setup_wizard.SetupWizard.run(config)
    assert settings["bedrock_model"] == "openai.gpt-oss-120b-1:0"
    assert settings["bedrock_region"] == "us-gov-west-1"
    assert settings["bedrock_credentials_file"] == ""
    stored = config.credentials.get("bedrock_aws_credentials")
    assert "AKIA1" in stored
    assert "AKIA1" not in (tmp_path / "k" / "credentials.json").read_text()


def test_wizard_bedrock_env_file(monkeypatch, tmp_path):
    env = tmp_path / ".env.work"
    env.write_text("AWS_ACCESS_KEY_ID=AKIA2\nAWS_SECRET_ACCESS_KEY=s\n")
    monkeypatch.setattr(
        "kubrick_cli.providers.bedrock_provider.BedrockProvider.list_models",
        lambda self: [],
    )
    _script(
        monkeypatch,
        [_value_of("Amazon Bedrock"), "file"],
        [str(env), "us-east-1", "amazon.nova-pro-v1:0"],
    )
    config = KubrickConfig(skip_wizard=True, kubrick_dir=tmp_path / "k")
    settings = setup_wizard.SetupWizard.run(config)
    assert settings["bedrock_credentials_file"] == str(env)
    assert settings["bedrock_model"] == "amazon.nova-pro-v1:0"
