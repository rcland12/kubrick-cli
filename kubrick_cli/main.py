#!/usr/bin/env python3
"""Main CLI entry point for Kubrick."""

import argparse
import io
import json
import os
import select
import stat
import sys
from datetime import datetime
from typing import List, Optional, Tuple

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from . import __version__
from .agent_loop import AgentLoop, TurnResult
from .config import KubrickConfig
from .context_manager import ContextManager
from .display import Renderer, is_interactive
from .glyphs import glyph
from .permissions import MODE_DESCRIPTIONS, MODES, PermissionManager
from .prompts import build_system_prompt
from .providers.base import ProviderError
from .providers.factory import MissingCredentialError, ProviderFactory
from .safety import SafetyConfig, SafetyManager
from .setup_wizard import (
    SetupWizard,
    auth_login,
    auth_logout,
    auth_status,
    choose_provider,
    prompt_secret,
)
from .tools import ToolExecutor, get_tool_specs
from .ui import EnhancedPrompt, SessionStats, SlashCommand, make_permission_prompt
from .widgets import Choice, ask_text
from .widgets import select as pick

console = Console()

INIT_PROMPT = """Please analyze this codebase and create a KUBRICK.md file in the \
working directory. It will be loaded into your context in future sessions, so write it \
for an AI coding agent working in this repo. Include:
1. Commands to build, lint, run tests, and run a single test.
2. A concise architecture overview: the big-picture structure that takes reading \
several files to understand, not a file listing.
3. Conventions and gotchas specific to this project.
If a CLAUDE.md, AGENTS.md, README, or contributing guide exists, use it. Don't invent \
information you can't verify from the repo, and keep it concise. If KUBRICK.md already \
exists, suggest improvements to it instead."""

COMMANDS = [
    SlashCommand("/help", "Show commands and keys"),
    SlashCommand("/clear", "Start a new conversation"),
    SlashCommand("/compact", "Summarize the conversation to free context", "[focus]"),
    SlashCommand("/context", "Show context window usage"),
    SlashCommand("/model", "Pick or switch the model", "[name]"),
    SlashCommand("/provider", "Pick or switch the provider", "[name]"),
    SlashCommand("/setup", "Set up a provider (API key, server, model)"),
    SlashCommand("/login", "Enter new credentials for the current provider"),
    SlashCommand("/plan", "Toggle plan mode (read-only investigation)"),
    SlashCommand("/permissions", "Pick the permission mode", "[mode]"),
    SlashCommand("/init", "Generate a KUBRICK.md for this project"),
    SlashCommand("/status", "Session, provider, and token usage"),
    SlashCommand("/save", "Save the conversation"),
    SlashCommand("/list", "List saved conversations", "[N]"),
    SlashCommand("/load", "Resume a saved conversation", "<#|id>", needs_arg=True),
    SlashCommand("/delete", "Delete a saved conversation", "<id>", needs_arg=True),
    SlashCommand("/config", "Show or change settings", "[key [value]]"),
    SlashCommand("/update", "Check for a new Kubrick release and install it"),
    SlashCommand(
        "/debug", "Show the system prompt or recent messages", "<prompt|messages>", True
    ),
    SlashCommand("/exit", "Save and quit"),
]


def help_text() -> str:
    """The /help screen."""
    width = max(len(f"{c.name} {c.args}") for c in COMMANDS) + 2
    rows = "\n".join(
        f"  [green]{escape(f'{c.name} {c.args}'.strip().ljust(width))}[/green]"
        f"{escape(c.description)}"
        for c in COMMANDS
    )
    dot = glyph("dot")
    return (
        f"[bold cyan]Commands[/bold cyan]\n{rows}\n\n"
        f"[bold cyan]Keys[/bold cyan]\n"
        f"  Enter submits {dot} Alt+Enter or Ctrl+J adds a newline\n"
        f"  Type / for the command menu: {glyph('up_down')} to pick, Tab to complete, "
        "Esc to close\n"
        f"  Ctrl+C interrupts the agent {dot} Ctrl+D quits\n\n"
        "[bold cyan]Project instructions[/bold cyan]  KUBRICK.md (or CLAUDE.md / "
        "AGENTS.md) in the project, and ~/.kubrick/KUBRICK.md, are loaded into the "
        "system prompt."
    )


class KubrickCLI:
    """One Kubrick session: provider, tools, conversation, and the agent loop."""

    def __init__(
        self,
        config: KubrickConfig,
        working_dir: Optional[str] = None,
        conversation_id: Optional[str] = None,
        print_mode: bool = False,
        interactive: bool = True,
    ):
        """
        Args:
            config: KubrickConfig (session overrides already applied)
            working_dir: Directory the agent works in (default: cwd)
            conversation_id: Resume a saved conversation (ID or path)
            print_mode: Non-interactive single-prompt mode (``-p``)
            interactive: Whether a human can answer prompts
        """
        self.config = config
        self.interactive = interactive
        self.renderer = Renderer(
            working_dir=working_dir,
            show_thinking=bool(config.get("show_thinking", True)),
            print_mode=print_mode,
        )
        self.safety_manager = SafetyManager(SafetyConfig.from_config(config.get_all()))
        self.tool_executor = ToolExecutor(
            working_dir=working_dir,
            safety_manager=self.safety_manager,
            bash_timeout=int(config.get("tool_timeout_seconds") or 120),
        )
        self.session_stats = SessionStats()
        self.permissions = PermissionManager(
            config.get("permission_mode", "default"),
            self.tool_executor,
            self.safety_manager,
            prompt=make_permission_prompt(self.renderer) if interactive else None,
        )
        self.provider = None
        self._model_cache: Optional[List[str]] = None
        self._connect(config.get("provider"))

        self.conversation_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.messages = [self._system_message()]
        self.last_listed_conversations: List[dict] = []
        if conversation_id:
            self._load(conversation_id)

    # --- Setup ---------------------------------------------------------------

    def _connect(self, provider_name: str):
        """Create (or switch to) a provider and rebuild everything that depends on it."""
        provider = ProviderFactory.create_provider(
            self.config,
            provider_name,
            prompt_secret=prompt_secret if self.interactive else None,
        )
        self.provider = provider
        self._model_cache = None
        if self.interactive and hasattr(provider, "on_credentials_expired"):
            provider.on_credentials_expired = self._refresh_aws_credentials
        self.context_manager = None
        if self.config.get("enable_context_management", True):
            self.context_manager = ContextManager(provider, self.config.get_all())
        self.agent = AgentLoop(
            provider=provider,
            tool_executor=self.tool_executor,
            permissions=self.permissions,
            renderer=self.renderer,
            context_manager=self.context_manager,
            max_iterations=int(self.config.get("max_iterations") or 50),
            tool_calling=self.config.get("tool_calling", "auto"),
            max_tool_result_chars=int(
                self.config.get("max_tool_result_chars") or 30000
            ),
            max_parallel_workers=int(self.config.get("max_parallel_workers") or 4),
            enable_parallel_tools=bool(self.config.get("enable_parallel_tools", True)),
            session_stats=self.session_stats,
            system_prompt_builder=self._build_system_prompt,
        )

    def _build_system_prompt(self, text_protocol: bool) -> str:
        return build_system_prompt(
            self.tool_executor.working_dir,
            tools=get_tool_specs(),
            text_tool_protocol=text_protocol,
            kubrick_dir=self.config.kubrick_dir,
        )

    def _system_message(self) -> dict:
        return {
            "role": "system",
            "content": self._build_system_prompt(self.agent.text_protocol),
        }

    def _update_check(self):
        """Mention a newer release (from the last check), and re-check in the background."""
        if not self.config.get("check_for_updates", True):
            return
        from .updater import refresh_in_background, update_notice

        notice = update_notice(self.config.kubrick_dir, __version__)
        if notice:
            self.renderer.notice(notice)
        refresh_in_background(self.config.kubrick_dir)

    def startup_checks(self):
        """Warn about unreachable servers, expiring keys, and too-small context windows."""
        if hasattr(self.provider, "explicit_credentials"):
            from . import aws_credentials as awscreds

            values = self.provider.explicit_credentials()
            left = awscreds.seconds_left(values)
            if left is not None:
                text = f"AWS credentials {awscreds.describe_expiry(values)}"
                if left < 1800:
                    self.renderer.warning(text + "; /login to paste new ones.")
                else:
                    self.renderer.notice(text + ".")
        if not self.provider.is_healthy():
            self.renderer.warning(
                f"Cannot reach the {self.provider.provider_name} provider. "
                "Check the server/URL and credentials (`kubrick auth status`)."
            )
        cm = self.context_manager
        if cm and cm.context_window < 16000:
            self.renderer.warning(
                f"Context window is only {cm.context_window:,} tokens; the system prompt and "
                "tools alone use several thousand. For Ollama, start the server with "
                "OLLAMA_CONTEXT_LENGTH=32768 (or more); for vLLM raise --max-model-len; "
                "or set the real value with /config context_window <tokens>."
            )

    # --- Conversation --------------------------------------------------------

    def run_turn(self, user_message: str) -> TurnResult:
        """Send one user message and run the agent until it ends its turn."""
        self.messages.append({"role": "user", "content": user_message})
        result = self.agent.run(self.messages)
        self._save()
        return result

    def _save(self) -> bool:
        """Save the conversation; False if there was nothing (or nothing to) save."""
        if not self.config.get("auto_save_conversations", True):
            return False
        if not any(m["role"] == "user" for m in self.messages):
            return False  # nothing said yet; don't litter the conversation list
        metadata = {
            "working_dir": str(self.tool_executor.working_dir),
            "provider": self.provider.provider_name,
            "model_name": self.provider.model_name,
            "saved_at": datetime.now().isoformat(),
        }
        self.config.save_conversation(self.conversation_id, self.messages, metadata)
        return True

    def _load(self, identifier: str) -> bool:
        if identifier.isdigit() and self.last_listed_conversations:
            idx = int(identifier) - 1
            if not 0 <= idx < len(self.last_listed_conversations):
                self.renderer.warning("No such conversation number; use /list.")
                return False
            identifier = self.last_listed_conversations[idx]["id"]
        data = self.config.load_conversation(identifier)
        if not data:
            self.renderer.warning(f"Conversation not found: {identifier}")
            return False
        loaded = [m for m in data.get("messages", []) if m.get("role") != "system"]
        self.messages = [self._system_message()] + loaded
        self.conversation_id = data.get("id", identifier)
        self.renderer.notice(
            f"Loaded conversation {self.conversation_id} ({len(loaded)} messages)"
        )
        return True

    def _new_conversation(self):
        self._save()
        self.conversation_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.messages = [self._system_message()]
        if self.context_manager:
            self.context_manager = ContextManager(self.provider, self.config.get_all())
            self.agent.context_manager = self.context_manager

    # --- Interactive ---------------------------------------------------------

    def _status(self) -> dict:
        cm = self.context_manager
        context = ""
        if cm:
            context = f"ctx {cm.usage_ratio(self.messages):.0%} of {cm.context_window // 1000}k"
        s = self.session_stats
        stats = []
        if s.tool_calls:
            stats.append(f"tools {s.tool_calls}")
        if s.files_created or s.files_modified:
            stats.append(f"files +{s.files_created} ~{s.files_modified}")
        stats.append(s.get_runtime())
        return {
            "model": f"{self.provider.provider_name}:{self.provider.model_name}",
            "mode": self.permissions.mode,
            "context": context,
            "stats": " · ".join(stats),
            "dir": self.tool_executor.working_dir.name,
        }

    def run(self, initial_prompt: Optional[str] = None):
        """Interactive session loop."""
        console.print(
            Panel.fit(
                f"[bold cyan]Kubrick[/bold cyan] {__version__}  ·  "
                f"{escape(self.provider.provider_name)}:{escape(self.provider.model_name)}\n"
                f"[dim]{escape(str(self.tool_executor.working_dir))}[/dim]\n"
                f"[dim]/ for commands {glyph('dot')} Ctrl+C interrupts "
                f"{glyph('dot')} Ctrl+D quits[/dim]",
                border_style="cyan",
            )
        )
        self.startup_checks()
        self._update_check()
        prompt = EnhancedPrompt(
            self._status,
            self.config.kubrick_dir / "history",
            commands=COMMANDS,
            argument_choices=self._argument_choices,
            editing_mode=self.config.get("editing_mode", "emacs"),
        )

        if initial_prompt:
            self.run_turn(initial_prompt)

        interrupts = 0
        while True:
            try:
                console.print()
                user_input = prompt.get_input(">")
                interrupts = 0
            except KeyboardInterrupt:
                interrupts += 1
                if interrupts >= 2:
                    break
                console.print("[dim](Press Ctrl+C again or type exit to quit)[/dim]")
                continue

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "/exit", "/quit"):
                break
            if _is_command(user_input):
                try:
                    self.handle_command(user_input)
                except (ProviderError, ValueError) as e:
                    self.renderer.error(str(e))
                except (KeyboardInterrupt, EOFError):
                    self.renderer.notice("Cancelled.")
                continue
            try:
                self.run_turn(user_input)
            except KeyboardInterrupt:
                self.renderer.warning("Interrupted.")

        if self._save():
            console.print(f"[dim]Conversation saved as {self.conversation_id}[/dim]")

    # --- Slash commands ------------------------------------------------------

    def handle_command(self, command: str):
        parts = command.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""
        handlers = {
            "/help": lambda: console.print(help_text()),
            "/clear": self._cmd_clear,
            "/compact": lambda: self._cmd_compact(arg),
            "/context": self._cmd_context,
            "/model": lambda: self._cmd_model(arg),
            "/provider": lambda: self._cmd_provider(arg),
            "/setup": self._cmd_setup,
            "/login": self._cmd_login,
            "/plan": self._cmd_plan,
            "/permissions": lambda: self._cmd_permissions(arg),
            "/init": lambda: self.run_turn(INIT_PROMPT),
            "/status": self._cmd_status,
            "/save": self._cmd_save,
            "/list": lambda: self._cmd_list(arg),
            "/load": lambda: (
                self._load(arg) if arg else console.print("Usage: /load <#|id>")
            ),
            "/delete": lambda: self._cmd_delete(arg),
            "/config": lambda: self._cmd_config(arg),
            "/debug": lambda: self._cmd_debug(arg),
            "/update": self._cmd_update,
        }
        if cmd not in handlers:
            # Unambiguous prefixes work too: /pro -> /provider.
            matches = [name for name in handlers if name.startswith(cmd)]
            if len(matches) != 1:
                hint = f" Did you mean {', '.join(matches)}?" if matches else ""
                self.renderer.warning(f"Unknown command {cmd}.{hint} Type /help.")
                return
            cmd = matches[0]
        handlers[cmd]()

    def _argument_choices(self, command: str) -> List[Tuple[str, str]]:
        """Completions for a command's argument (runs in a background thread)."""
        if command == "/provider":
            current = self.provider.provider_name
            return [
                (m.name, m.display_name + (" (current)" if m.name == current else ""))
                for m in ProviderFactory.list_available_providers()
            ]
        if command == "/model":
            current = self.provider.model_name
            return [(m, "current" if m == current else "") for m in self._models()]
        if command == "/permissions":
            return [(m, MODE_DESCRIPTIONS[m]) for m in MODES]
        if command == "/config":
            return [
                (k, json.dumps(v)[:40])
                for k, v in sorted(self.config.get_all().items())
            ]
        if command in ("/load", "/delete"):
            return [
                (
                    c["id"],
                    f"{c['metadata'].get('model_name', '')} {glyph('dot')} "
                    f"{c['message_count']} msgs {glyph('dot')} "
                    f"{os.path.basename(c['metadata'].get('working_dir', ''))}",
                )
                for c in self.config.list_conversations(limit=30)
            ]
        if command == "/debug":
            return [("prompt", "System prompt"), ("messages", "Last 10 messages")]
        return []

    def _models(self) -> List[str]:
        """The provider's models, fetched once per provider."""
        if self._model_cache is None:
            self._model_cache = self.provider.list_models()
        return self._model_cache

    def _cmd_clear(self):
        self._new_conversation()
        self.renderer.notice(f"New conversation {self.conversation_id}")

    def _cmd_compact(self, focus: str):
        if not self.context_manager:
            self.context_manager = ContextManager(self.provider, self.config.get_all())
        if len(self.messages) < 4:
            self.renderer.notice("Nothing to compact yet.")
            return
        self.renderer.notice("Summarizing conversation…")
        self.messages, info = self.context_manager.compact(self.messages, focus or None)
        self.renderer.notice(
            f"Compacted ({info['action']}): ~{info['tokens_before']:,} {glyph('arrow')} "
            f"~{info['tokens_after']:,} tokens"
        )

    def _cmd_context(self):
        cm = self.context_manager
        if not cm:
            self.renderer.notice("Context management is disabled.")
            return
        tokens = cm.current_tokens(self.messages)
        table = Table(title="Context")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Estimated tokens in use", f"{tokens:,}")
        table.add_row("Context window", f"{cm.context_window:,}")
        table.add_row("Reserved for output", f"{cm.reserved_output:,}")
        table.add_row("Usage", f"{cm.usage_ratio(self.messages):.1%}")
        table.add_row("Auto-compact at", f"{cm.usage_threshold:.0%}")
        table.add_row("Messages", str(len(self.messages)))
        if cm.last_usage:
            u = cm.last_usage
            table.add_row(
                "Last request (reported)",
                f"in {u.input_tokens:,} · cache read {u.cache_read_tokens:,} · "
                f"out {u.output_tokens:,}",
            )
        console.print(table)

    def _cmd_model(self, name: str):
        if not name:
            current = self.provider.model_name
            with console.status(f"Fetching models{glyph('ellipsis')}"):
                models = self._models()
            if not models:
                console.print(f"Current model: [cyan]{escape(current)}[/cyan]")
                console.print("[dim]Switch with /model <name>[/dim]")
                return
            choices = [Choice(m, m, current=m == current) for m in models]
            choices.append(Choice("", "Other...", "Type a model name"))
            name = pick(
                "Switch model", choices, filterable=len(models) > 9, summary="Model"
            )
            if name == "":
                name = ask_text("Model name")
            if not name or name == current:
                return
        self.provider.set_model(name)
        self.config.override(f"{self.provider.provider_name}_model", name)
        if self.context_manager:
            self.context_manager = ContextManager(self.provider, self.config.get_all())
            self.agent.context_manager = self.context_manager
        self.renderer.notice(
            f"Switched to {name} for this session "
            f"(save with /config {self.provider.provider_name}_model {name})"
        )

    def _cmd_provider(self, name: str):
        if not name:
            metadata = choose_provider(self.provider.provider_name, "Switch provider")
            if metadata is None or metadata.name == self.provider.provider_name:
                return
            name = metadata.name
        try:
            self._connect(name)
        except ValueError as e:
            # Not configured yet (no model, no key): offer to set it up now.
            self.renderer.warning(str(e))
            metadata = ProviderFactory.get_provider_metadata(name)
            if not pick(
                f"Set up {metadata.display_name} now?",
                [Choice(True, "Yes"), Choice(False, "No")],
            ):
                return
            for key, value in SetupWizard.configure_provider(
                self.config, metadata
            ).items():
                self.config.set(key, value)
            self._connect(name)
        self.config.override("provider", name)
        if self.messages and self.messages[0]["role"] == "system":
            self.messages[0] = self._system_message()
        self.renderer.notice(
            f"Switched to {name}:{self.provider.model_name} for this session "
            f"(save with /config provider {name})"
        )

    def _cmd_setup(self):
        settings = SetupWizard.run(self.config)
        for key, value in settings.items():
            self.config.set(key, value)
        self._connect(settings["provider"])
        if self.messages and self.messages[0]["role"] == "system":
            self.messages[0] = self._system_message()
        self.renderer.notice(
            f"Now using {self.provider.provider_name}:{self.provider.model_name}"
        )

    def _refresh_aws_credentials(self, provider) -> bool:
        """Called by the Bedrock provider when its credentials are rejected or expired."""
        from .setup_wizard import ask_aws_credentials

        self.renderer.warning(
            f"Your AWS credentials have expired or were rejected "
            f"({provider.credential_source()})."
        )
        choices = [Choice("paste", "Paste new credentials", "input is hidden")]
        if provider.credentials_file:
            choices.append(
                Choice("file", f"I've updated {provider.credentials_file}; try again")
            )
        elif provider.profile:
            choices.append(Choice("file", f"I've refreshed profile {provider.profile}"))
        choices.append(Choice("cancel", "Cancel this request"))
        answer = pick("What now?", choices)
        if answer == "file":
            return True
        if answer != "paste":
            return False
        values = ask_aws_credentials()
        if not values:
            return False
        self._apply_aws_credentials(provider, values)
        return True

    def _apply_aws_credentials(self, provider, values):
        from . import aws_credentials as awscreds
        from .setup_wizard import store_aws_credentials

        store_aws_credentials(self.config, values, provider.credentials_file)
        if not provider.credentials_file:
            provider.pasted_credentials = values
            provider.profile = None  # pasted keys take over for this session
        if not provider.region and awscreds.region_of(values):
            provider.region = awscreds.region_of(values)

    def _cmd_login(self):
        if self.provider.provider_name == "bedrock":
            from .setup_wizard import ask_aws_credentials

            values = ask_aws_credentials()
            if values:
                self._apply_aws_credentials(self.provider, values)
                self.provider.reload_credentials()
                self.renderer.notice("Using the new AWS credentials.")
            return
        metadata = ProviderFactory.get_provider_metadata(self.provider.provider_name)
        if not metadata.secret_fields:
            self.renderer.notice(
                f"{metadata.display_name} has no credentials to enter."
            )
            return
        for field in metadata.secret_fields:
            value = prompt_secret(metadata.name, field)
            if value:
                self.config.credentials.set(field["key"], value)
        self._connect(self.provider.provider_name)
        self.renderer.notice("Reconnected with the new credentials.")

    def _cmd_plan(self):
        if self.permissions.mode == "plan":
            self.permissions.mode = getattr(self, "_mode_before_plan", "default")
            self.renderer.notice(
                f"Plan mode off (permissions: {self.permissions.mode})."
            )
        else:
            self._mode_before_plan = self.permissions.mode
            self.permissions.mode = "plan"
            self.renderer.notice(
                "Plan mode on: the agent can only read and investigate. "
                "Ask for a plan; run /plan again to let it make changes."
            )

    def _cmd_permissions(self, mode: str):
        if not mode:
            if self.permissions.allowed_command_prefixes:
                console.print(
                    "Always-allowed commands this session: "
                    + escape(
                        ", ".join(sorted(self.permissions.allowed_command_prefixes))
                    )
                )
            mode = pick(
                "Permission mode",
                [
                    Choice(
                        m, m, MODE_DESCRIPTIONS[m], current=m == self.permissions.mode
                    )
                    for m in MODES
                ],
                summary="Permission mode",
            )
            if not mode or mode == self.permissions.mode:
                return
        if mode not in MODES:
            self.renderer.warning(f"Unknown mode {mode}. Choose: {', '.join(MODES)}")
            return
        self.permissions.mode = mode
        self.renderer.notice(f"Permission mode: {mode}")

    def _cmd_status(self):
        s = self.session_stats
        table = Table(title="Session")
        table.add_column("", style="cyan")
        table.add_column("")
        table.add_row(
            "Provider / model",
            f"{self.provider.provider_name} / {self.provider.model_name}",
        )
        table.add_row(
            "Tool calling", "text protocol" if self.agent.text_protocol else "native"
        )
        table.add_row("Permission mode", self.permissions.mode)
        table.add_row("Credential store", self.config.credentials.backend_name)
        if hasattr(self.provider, "credential_source"):
            table.add_row("AWS credentials", self.provider.credential_source())
        table.add_row("Conversation", self.conversation_id)
        table.add_row("Working dir", str(self.tool_executor.working_dir))
        table.add_row(
            "Tokens (session)",
            f"in {s.input_tokens:,} · cache read {s.cache_read_tokens:,} · out {s.output_tokens:,}",
        )
        table.add_row("Tool calls", str(s.tool_calls))
        table.add_row("Runtime", s.get_runtime())
        console.print(table)

    def _cmd_save(self):
        self._save()
        self.renderer.notice(f"Saved as {self.conversation_id}")

    def _cmd_list(self, arg: str):
        conversations = self.config.list_conversations(
            limit=int(arg) if arg.isdigit() else 20
        )
        if not conversations:
            self.renderer.notice("No saved conversations.")
            return
        self.last_listed_conversations = conversations
        table = Table(title="Saved conversations")
        table.add_column("#", style="magenta", justify="right")
        table.add_column("ID", style="cyan")
        table.add_column("Msgs", justify="right")
        table.add_column("Model", style="dim")
        table.add_column("Working dir", style="dim")
        table.add_column("Modified", style="yellow")
        for idx, conv in enumerate(conversations, 1):
            meta = conv["metadata"]
            table.add_row(
                str(idx),
                conv["id"],
                str(conv["message_count"]),
                meta.get("model_name", ""),
                meta.get("working_dir", ""),
                datetime.fromtimestamp(conv["modified"]).strftime("%Y-%m-%d %H:%M"),
            )
        console.print(table)
        console.print("[dim]/load <#> to resume[/dim]")

    def _cmd_delete(self, conv_id: str):
        if not conv_id:
            console.print("Usage: /delete <id>")
        elif self.config.delete_conversation(conv_id):
            self.renderer.notice(f"Deleted {conv_id}")
        else:
            self.renderer.warning(f"Conversation {conv_id} not found")

    def _cmd_config(self, arg: str):
        parts = arg.split(maxsplit=1)
        if not parts:
            table = Table(title=f"Configuration ({self.config.config_file})")
            table.add_column("Setting", style="cyan")
            table.add_column("Value", style="green")
            for key, value in sorted(self.config.get_all().items()):
                table.add_row(key, escape(json.dumps(value)))
            console.print(table)
            console.print(
                "[dim]API keys are not shown; see `kubrick auth status`.[/dim]"
            )
            return
        key = parts[0]
        if len(parts) == 1:
            console.print(f"{key} = {json.dumps(self.config.get(key))}")
            return
        if key.endswith("_api_key"):
            self.renderer.warning(
                "Store API keys with `kubrick auth login`, not /config."
            )
            return
        try:
            value = json.loads(parts[1])
        except json.JSONDecodeError:
            value = parts[1]
        self.config.set(key, value)
        self.renderer.notice(
            f"Set {key} = {json.dumps(value)} (takes effect on restart for "
            "provider settings)"
        )

    def _cmd_update(self):
        from .updater import run_update

        run_update(__version__, console, confirm=_confirm)

    def _cmd_debug(self, arg: str):
        if arg == "prompt":
            console.print(
                Panel(
                    escape(self.messages[0]["content"]),
                    title="System prompt",
                    border_style="dim",
                )
            )
            return
        if arg == "messages":
            console.print_json(json.dumps(self.messages[-10:], default=str))
            return
        console.print("Usage: /debug prompt | /debug messages")


# --- Entry point -------------------------------------------------------------


def _confirm(question: str) -> bool:
    return bool(pick(question, [Choice(True, "Yes"), Choice(False, "No")]))


def _is_command(text: str) -> bool:
    """A /command, as opposed to a message that starts with a path like /etc/hosts."""
    return text.startswith("/") and text.split()[0].count("/") == 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kubrick",
        description="Kubrick: an agentic coding CLI for local and hosted models.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Other commands:
  kubrick setup                       Run the setup wizard
  kubrick auth login [provider]       Store an API key (encrypted / OS keychain)
  kubrick auth logout [provider]      Remove stored API keys
  kubrick auth status                 Show where credentials come from
  kubrick update [--check] [--yes]    Upgrade to the latest release

Examples:
  kubrick                                   Start an interactive session
  kubrick "fix the failing test"            Start with a first message
  kubrick -p "summarize this repo"          Answer once and exit (scriptable)
  git diff | kubrick -p "review this diff"  Pipe input in
  kubrick --provider anthropic --model claude-sonnet-5-5
  kubrick -c                                Continue the most recent conversation
""",
    )
    parser.add_argument("prompt", nargs="?", help="Initial message")
    parser.add_argument(
        "-p",
        "--print",
        dest="print_mode",
        action="store_true",
        help="Run the prompt non-interactively, print the answer, and exit",
    )
    parser.add_argument(
        "-c",
        "--continue",
        dest="continue_last",
        action="store_true",
        help="Continue the most recent conversation",
    )
    parser.add_argument(
        "-r",
        "--resume",
        "--load",
        dest="conversation_id",
        help="Resume a conversation by ID or file path",
    )
    parser.add_argument("--provider", help="Provider for this session")
    parser.add_argument("-m", "--model", help="Model for this session")
    parser.add_argument(
        "--working-dir", "-C", help="Working directory (default: current)"
    )
    parser.add_argument(
        "--permission-mode", choices=MODES, help="Permission mode for this session"
    )
    parser.add_argument(
        "--tool-calling",
        choices=["auto", "native", "text"],
        help="Force native or text-based tool calling",
    )
    parser.add_argument(
        "--max-iterations", type=int, help="Model calls allowed per turn"
    )
    parser.add_argument("--version", action="version", version=f"kubrick {__version__}")
    return parser


def _run_subcommand(argv: List[str]) -> Optional[int]:
    """Handle `kubrick setup` / `kubrick auth ...`; None if argv isn't one."""
    if not argv or argv[0] not in ("setup", "auth", "update"):
        return None
    if argv[0] == "update":
        from .updater import run_update

        flags = set(argv[1:])
        unknown = flags - {"--check", "--yes", "-y"}
        if unknown:
            console.print("Usage: kubrick update [--check] [--yes]")
            return 2
        yes = bool(flags & {"--yes", "-y"})
        interactive = sys.stdin.isatty()
        return run_update(
            __version__,
            console,
            confirm=_confirm if interactive and not yes else None,
            # Without a terminal, only upgrade when explicitly told to.
            check_only="--check" in flags or not (interactive or yes),
        )
    config = KubrickConfig(skip_wizard=True)
    if argv[0] == "setup":
        try:
            settings = SetupWizard.run(config)
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Setup cancelled; nothing was changed.[/dim]")
            return 130
        for key, value in settings.items():
            config.set(key, value)
        return 0
    action = argv[1] if len(argv) > 1 else "status"
    provider = argv[2] if len(argv) > 2 else None
    if action == "login":
        return auth_login(config, provider)
    if action == "logout":
        return auth_logout(config, provider)
    if action == "status":
        return auth_status(config)
    console.print("Usage: kubrick auth [login|logout|status] [provider]")
    return 2


def _read_piped_stdin(wait: bool = False) -> str:
    """Read input piped into kubrick (``git diff | kubrick -p ...``).

    Only reads when stdin is a file, or a pipe/socket with data ready within a
    moment: harnesses, cron and IDE terminals often leave an idle pipe open that
    would otherwise block forever. With ``wait`` (no prompt argument given, so
    stdin is the only possible input) it blocks until the pipe closes.
    """
    if sys.stdin is None or sys.stdin.isatty():
        return ""
    try:
        mode = os.fstat(sys.stdin.fileno()).st_mode
    except (OSError, ValueError, io.UnsupportedOperation):
        return sys.stdin.read()  # not a real file descriptor (e.g. tests)
    if stat.S_ISREG(mode) or wait:
        return sys.stdin.read()
    if os.name == "nt":
        return ""
    ready, _, _ = select.select([sys.stdin], [], [], 0.25)
    return sys.stdin.read() if ready else ""


def main(argv: Optional[List[str]] = None) -> int:
    """Main entry point."""
    argv = list(sys.argv[1:] if argv is None else argv)
    code = _run_subcommand(argv)
    if code is not None:
        return code

    args = _build_parser().parse_args(argv)
    if not is_interactive():
        args.print_mode = True  # no terminal to talk to: answer once and exit
    interactive = not args.print_mode

    prompt = args.prompt
    piped = _read_piped_stdin(wait=prompt is None)
    if piped.strip():
        prompt = f"{prompt}\n\n{piped}" if prompt else piped
    if args.print_mode and not prompt:
        console.print("[red]-p needs a prompt (argument or stdin).[/red]")
        return 2

    try:
        config = KubrickConfig(skip_wizard=not interactive)
    except (KeyboardInterrupt, EOFError):
        console.print(
            "\n[dim]Setup cancelled. Run `kubrick` again to restart it.[/dim]"
        )
        return 130
    for key, value in (
        ("provider", args.provider),
        ("permission_mode", args.permission_mode),
        ("tool_calling", args.tool_calling),
        ("max_iterations", args.max_iterations),
    ):
        if value is not None:
            config.override(key, value)
    if args.model:
        config.override(f"{config.get('provider')}_model", args.model)

    conversation_id = args.conversation_id
    if args.continue_last and not conversation_id:
        recent = config.list_conversations(limit=1)
        conversation_id = recent[0]["id"] if recent else None

    try:
        cli = KubrickCLI(
            config=config,
            working_dir=args.working_dir,
            conversation_id=conversation_id,
            print_mode=args.print_mode,
            interactive=interactive,
        )
    except (MissingCredentialError, ProviderError, ValueError) as e:
        console.print(f"[red]{escape(str(e))}[/red]")
        return 1
    except KeyboardInterrupt:
        return 130

    if args.print_mode:
        result = cli.run_turn(prompt)
        return 0 if result.success else 1

    cli.run(initial_prompt=prompt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
