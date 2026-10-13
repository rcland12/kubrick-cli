"""`kubrick update` / `/update`: check PyPI and upgrade however Kubrick was installed."""

import importlib.util
import json
import os
import re
import shutil
import subprocess  # nosec B404 - runs fixed upgrade commands, never model input
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

PACKAGE = "kubrick-cli"
DOCKER_IMAGE = "rcland12/kubrick-cli"
CHECK_INTERVAL_SECONDS = 24 * 3600


@dataclass
class InstallInfo:
    """How this copy of Kubrick was installed, and how to upgrade it."""

    method: str  # source | docker | uv_tool | pipx | pip_venv | pip_system
    description: str
    # Upgrade command Kubrick can run itself; None means the user has to (``hint``).
    command: Optional[List[str]]
    hint: str


def _version_key(version: str) -> Tuple[int, ...]:
    """Sortable key for simple PEP 440 versions (1.2.3, 1.2.3rc1, 1.2.3.post1)."""
    match = re.match(r"\s*v?(\d+(?:\.\d+)*)(.*)", version or "")
    if not match:
        return (0,)
    numbers = [int(n) for n in match.group(1).split(".")][:4]
    numbers += [0] * (4 - len(numbers))
    suffix = match.group(2).lower()
    # Pre-releases sort before the release, post-releases after it.
    rank = 0 if re.match(r"[.-]?(a|b|rc|dev)", suffix) else 2 if "post" in suffix else 1
    return tuple(numbers) + (rank,)


def is_newer(candidate: Optional[str], current: str) -> bool:
    """Whether ``candidate`` is a later version than ``current``."""
    return bool(candidate) and _version_key(candidate) > _version_key(current)


def latest_version(timeout: int = 5) -> Optional[str]:
    """Latest release on PyPI, or None if it can't be reached."""
    from .providers.http import HttpEndpoint

    try:
        data = HttpEndpoint("https://pypi.org").get_json(
            f"/pypi/{PACKAGE}/json", timeout=timeout
        )
        return str(data["info"]["version"])
    except Exception:
        return None


def _editable_source() -> Optional[str]:
    """The source directory if Kubrick is installed in editable/development mode."""
    try:
        from importlib.metadata import distribution

        raw = distribution(PACKAGE).read_text("direct_url.json")
    except Exception:
        raw = None
    if raw:
        try:
            info = json.loads(raw)
        except ValueError:
            info = {}
        if info.get("dir_info", {}).get("editable"):
            url = info.get("url", "")
            return url[7:] if url.startswith("file://") else url
    # Not installed at all: running straight from a checkout (python -m kubrick_cli.main).
    package_dir = Path(__file__).resolve().parent
    if (package_dir.parent / "pyproject.toml").exists() and not any(
        part in ("site-packages", "dist-packages") for part in package_dir.parts
    ):
        return str(package_dir.parent)
    return None


def _installed_extras() -> str:
    extras = [
        name
        for name, module in (("bedrock", "boto3"), ("keyring", "keyring"))
        if importlib.util.find_spec(module) is not None
    ]
    return f"[{','.join(extras)}]" if extras else ""


def detect_install() -> InstallInfo:
    """Work out how Kubrick was installed."""
    source = _editable_source()
    if source:
        return InstallInfo(
            "source",
            f"from source ({source})",
            None,
            f"Update the checkout in {source} (e.g. `git pull`), then rerun "
            "`make dev` if dependencies changed.",
        )
    if os.path.exists("/.dockerenv") or os.environ.get("KUBRICK_IN_DOCKER"):
        return InstallInfo(
            "docker",
            "in a Docker container",
            None,
            f"On the host, run: docker pull {DOCKER_IMAGE}:latest",
        )
    parts = Path(sys.prefix).resolve().parts
    joined = "/".join(parts)
    if "uv/tools" in joined:
        uv = shutil.which("uv")
        return InstallInfo(
            "uv_tool",
            "with `uv tool`",
            [uv, "tool", "upgrade", PACKAGE] if uv else None,
            f"uv tool upgrade {PACKAGE}",
        )
    if "pipx" in parts and "venvs" in parts:
        pipx = shutil.which("pipx")
        return InstallInfo(
            "pipx",
            "with pipx",
            [pipx, "upgrade", PACKAGE] if pipx else None,
            f"pipx upgrade {PACKAGE}",
        )
    spec = PACKAGE + _installed_extras()
    if sys.prefix != getattr(sys, "base_prefix", sys.prefix):
        command = [sys.executable, "-m", "pip", "install", "--upgrade", spec]
        uv = shutil.which("uv")
        if importlib.util.find_spec("pip") is None and uv:
            # Virtualenvs made by uv have no pip.
            command = [
                uv,
                "pip",
                "install",
                "--python",
                sys.executable,
                "--upgrade",
                spec,
            ]
        return InstallInfo(
            "pip_venv",
            f"in the virtual environment {sys.prefix}",
            command,
            " ".join(command),
        )
    # System or user site: upgrading it may need sudo or clash with the OS packages.
    return InstallInfo(
        "pip_system",
        "with pip outside a virtual environment",
        None,
        f"pip install --user --upgrade '{spec}'  (or switch to "
        f"`uv tool install {PACKAGE}` / `pipx install {PACKAGE}`)",
    )


def installed_version() -> Optional[str]:
    """The version now installed in this environment (fresh process, after an upgrade)."""
    script = f"import importlib.metadata as m; print(m.version({PACKAGE!r}))"
    try:
        result = subprocess.run(  # nosec B603
            [sys.executable, "-c", script], capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


# --- Background check ----------------------------------------------------------


def _cache_file(kubrick_dir: Path) -> Path:
    return Path(kubrick_dir) / "update_check.json"


def cached_latest(kubrick_dir: Path) -> Optional[str]:
    """The latest version seen by the last background check (no network)."""
    try:
        return json.loads(_cache_file(kubrick_dir).read_text()).get("latest")
    except (OSError, ValueError, AttributeError):
        return None


def refresh_in_background(
    kubrick_dir: Path,
    fetch: Callable[[], Optional[str]] = latest_version,
    max_age: int = CHECK_INTERVAL_SECONDS,
) -> Optional[threading.Thread]:
    """Re-check PyPI at most once per ``max_age`` seconds, without blocking startup."""
    path = _cache_file(kubrick_dir)
    try:
        if time.time() - path.stat().st_mtime < max_age:
            return None
    except OSError:
        pass

    def run():
        latest = fetch()
        try:
            path.write_text(json.dumps({"latest": latest, "checked_at": time.time()}))
        except OSError:
            pass

    thread = threading.Thread(target=run, name="kubrick-update-check", daemon=True)
    thread.start()
    return thread


def update_notice(kubrick_dir: Path, current: str) -> Optional[str]:
    """A one-line "update available" message, from the cached check."""
    latest = cached_latest(kubrick_dir)
    if not is_newer(latest, current):
        return None
    if detect_install().method == "source":
        return None  # a checkout is usually ahead of PyPI anyway
    return (
        f"Kubrick {latest} is available (you have {current}). "
        "Run `kubrick update` or /update."
    )


# --- The update command ------------------------------------------------------------


def run_update(
    current: str,
    console,
    confirm: Optional[Callable[[str], bool]] = None,
    check_only: bool = False,
    fetch: Callable[[], Optional[str]] = latest_version,
    runner: Callable[[List[str]], int] = None,
    installed: Optional[Callable[[], Optional[str]]] = None,
) -> int:
    """
    Check for a newer release and upgrade if the user agrees.

    Args:
        current: Installed version
        console: rich Console for output
        confirm: Asks a yes/no question; None means don't ask (just do it)
        check_only: Only report; never upgrade
        fetch: Returns the latest version (for tests)
        runner: Runs the upgrade command and returns its exit code (for tests)
        installed: Returns the version installed after upgrading (for tests)

    Returns:
        Process exit code
    """
    from rich.markup import escape

    install = detect_install()
    console.print(f"Kubrick {current}, installed {escape(install.description)}")
    with console.status("Checking PyPI for updates..."):
        latest = fetch()
    if latest is None:
        console.print(
            "[yellow]Couldn't reach PyPI to check for updates. If you're offline or "
            f"behind a proxy, upgrade manually: {escape(install.hint)}[/yellow]"
        )
        return 1
    if not is_newer(latest, current):
        console.print(f"[green]You're up to date[/green] (latest release: {latest}).")
        return 0
    console.print(f"[bold]Kubrick {latest} is available.[/bold]")
    if check_only or install.command is None:
        console.print(f"To update: {escape(install.hint)}")
        return 0
    command = " ".join(install.command)
    if confirm is not None and not confirm(f"Run `{command}`?"):
        console.print(f"[dim]Skipped. To update later: {escape(command)}[/dim]")
        return 0
    runner = runner or (lambda cmd: subprocess.call(cmd))  # nosec B603
    code = runner(install.command)
    if code == 0:
        now = (installed or installed_version)()
        if now and not is_newer(now, current) and now != latest:
            console.print(
                f"[yellow]The installer finished, but Kubrick is still {now}.[/yellow]"
            )
        else:
            console.print(
                f"[green]Updated to {now or latest}.[/green] Restart Kubrick to use it."
            )
    else:
        console.print(f"[red]The upgrade command failed (exit {code}).[/red]")
    return code
