"""Tests for `kubrick update`."""

import io
import json
import sys

import pytest
from rich.console import Console

from kubrick_cli import updater
from kubrick_cli.updater import InstallInfo, is_newer


@pytest.mark.parametrize(
    "candidate, current, newer",
    [
        ("0.2.1", "0.2.0", True),
        ("0.10.0", "0.9.9", True),
        ("0.2.0", "0.2.0", False),
        ("0.2.0rc1", "0.2.0", False),
        ("0.2.0", "0.2.0rc1", True),
        ("0.2.0.post1", "0.2.0", True),
        ("1.0", "0.99.99", True),
        (None, "0.2.0", False),
    ],
)
def test_is_newer(candidate, current, newer):
    assert is_newer(candidate, current) is newer


def _console():
    out = io.StringIO()
    return Console(file=out, width=200), out


def _install(monkeypatch, command=("upgrade-it",), method="pip_venv"):
    info = InstallInfo(
        method, "for the test", list(command) if command else None, "do X"
    )
    monkeypatch.setattr(updater, "detect_install", lambda: info)


def test_up_to_date(monkeypatch):
    _install(monkeypatch)
    console, out = _console()
    ran = []
    code = updater.run_update(
        "0.2.0", console, fetch=lambda: "0.2.0", runner=ran.append
    )
    assert code == 0 and not ran
    assert "up to date" in out.getvalue()


def test_upgrades_after_confirmation(monkeypatch):
    _install(monkeypatch)
    console, out = _console()
    ran = []
    code = updater.run_update(
        "0.2.0",
        console,
        confirm=lambda q: True,
        fetch=lambda: "0.3.0",
        runner=lambda cmd: ran.append(cmd) or 0,
        installed=lambda: "0.3.0",
    )
    assert code == 0 and ran == [["upgrade-it"]]
    assert "Updated to 0.3.0" in out.getvalue()


def test_reports_when_installer_changed_nothing(monkeypatch):
    _install(monkeypatch)
    console, out = _console()
    updater.run_update(
        "0.2.0",
        console,
        fetch=lambda: "0.3.0",
        runner=lambda cmd: 0,
        installed=lambda: "0.2.0",
    )
    assert "still 0.2.0" in out.getvalue()


def test_declined_or_check_only_does_nothing(monkeypatch):
    _install(monkeypatch)
    ran = []
    for kwargs in ({"confirm": lambda q: False}, {"check_only": True}):
        console, _ = _console()
        updater.run_update(
            "0.2.0", console, fetch=lambda: "0.3.0", runner=ran.append, **kwargs
        )
    assert not ran


def test_manual_install_methods_print_the_command(monkeypatch):
    _install(monkeypatch, command=None, method="docker")
    console, out = _console()
    ran = []
    updater.run_update("0.2.0", console, fetch=lambda: "0.3.0", runner=ran.append)
    assert not ran and "do X" in out.getvalue()


def test_offline(monkeypatch):
    _install(monkeypatch)
    console, out = _console()
    assert updater.run_update("0.2.0", console, fetch=lambda: None) == 1
    assert "Couldn't reach PyPI" in out.getvalue()


def test_detects_source_checkout():
    # The test suite runs from the repo with an editable install.
    assert updater.detect_install().method == "source"


def test_detects_uv_tool_and_venv(monkeypatch):
    monkeypatch.setattr(updater, "_editable_source", lambda: None)
    monkeypatch.delenv("KUBRICK_IN_DOCKER", raising=False)
    monkeypatch.setattr(updater.os.path, "exists", lambda p: False)
    monkeypatch.setattr(updater.shutil, "which", lambda name: f"/usr/bin/{name}")

    monkeypatch.setattr(sys, "prefix", "/home/u/.local/share/uv/tools/kubrick-cli")
    info = updater.detect_install()
    assert info.method == "uv_tool"
    assert info.command == ["/usr/bin/uv", "tool", "upgrade", "kubrick-cli"]

    monkeypatch.setattr(sys, "prefix", "/home/u/.local/share/pipx/venvs/kubrick-cli")
    assert updater.detect_install().method == "pipx"

    monkeypatch.setattr(sys, "prefix", "/home/u/proj/.venv")
    monkeypatch.setattr(sys, "base_prefix", "/usr")
    info = updater.detect_install()
    assert info.method == "pip_venv" and info.command[-1].startswith("kubrick-cli")

    monkeypatch.setattr(sys, "prefix", "/usr")
    info = updater.detect_install()
    assert info.method == "pip_system" and info.command is None


def test_background_check_and_notice(monkeypatch, tmp_path):
    monkeypatch.setattr(
        updater, "detect_install", lambda: InstallInfo("pipx", "", [], "")
    )
    thread = updater.refresh_in_background(tmp_path, fetch=lambda: "9.9.9")
    thread.join()
    assert json.loads((tmp_path / "update_check.json").read_text())["latest"] == "9.9.9"
    assert "9.9.9 is available" in updater.update_notice(tmp_path, "0.2.0")
    # Checked recently: no second request.
    assert updater.refresh_in_background(tmp_path, fetch=lambda: "1/0") is None
    assert updater.update_notice(tmp_path, "9.9.9") is None


def test_no_notice_for_source_checkouts(tmp_path):
    (tmp_path / "update_check.json").write_text(json.dumps({"latest": "9.9.9"}))
    assert updater.update_notice(tmp_path, "0.2.0") is None


def test_update_subcommand_without_terminal_only_checks(monkeypatch, capsys):
    from kubrick_cli import main

    calls = {}

    def fake_run_update(current, console, confirm=None, check_only=False):
        calls.update(confirm=confirm, check_only=check_only)
        return 0

    monkeypatch.setattr(updater, "run_update", fake_run_update)
    assert main.main(["update"]) == 0
    assert calls == {"confirm": None, "check_only": True}
    assert main.main(["update", "--yes"]) == 0
    assert calls == {"confirm": None, "check_only": False}
    assert main.main(["update", "--bogus"]) == 2
