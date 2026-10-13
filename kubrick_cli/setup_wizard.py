"""First-run setup wizard and `kubrick auth` commands."""

import os
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from . import aws_credentials as awscreds
from .glyphs import glyph
from .providers.factory import ProviderFactory, is_required
from .providers.http import HttpEndpoint, HttpStatusError
from .providers.openai_provider import normalize_server_url
from .widgets import Choice, ask_block, ask_text, select

console = Console()

# Local servers the "Local model server" provider is usually pointed at:
# (id, name, default port, how to make it reachable from another machine).
LOCAL_SERVERS = [
    (
        "ollama",
        "Ollama",
        11434,
        "On the Ollama machine set OLLAMA_HOST=0.0.0.0 (and a large "
        "OLLAMA_CONTEXT_LENGTH, e.g. 32768), then restart Ollama.",
    ),
    (
        "vllm",
        "vLLM",
        8000,
        "Start it with: vllm serve <model> --host 0.0.0.0 "
        "--enable-auto-tool-choice --tool-call-parser <parser>",
    ),
    (
        "llamacpp",
        "llama.cpp (llama-server)",
        8080,
        "Start it with: llama-server -m <model.gguf> --jinja --host 0.0.0.0",
    ),
    (
        "lmstudio",
        "LM Studio",
        1234,
        "In LM Studio: Developer > Start Server, and enable serving on the network.",
    ),
    ("other", "Something else", None, ""),
]

_OTHER = object()


class SetupCancelled(KeyboardInterrupt):
    """The user backed out of the wizard (Esc)."""


def prompt_secret(provider: str, field: Dict[str, Any]) -> Optional[str]:
    """Ask for a secret on the terminal (input hidden)."""
    return (
        ask_text(field["label"], example=field.get("help_text", ""), password=True)
        or None
    )


def _need(value):
    """Esc in a wizard menu cancels the wizard."""
    if value is None:
        raise SetupCancelled()
    return value


def choose_provider(
    current: Optional[str] = None, title: str = "Which model provider?"
):
    """Arrow-key provider menu; returns the chosen ProviderMetadata or None (Esc)."""
    providers = ProviderFactory.list_available_providers()
    choices = [
        Choice(p, p.display_name, p.description, current=p.name == current)
        for p in providers
    ]
    return select(title, choices, summary="Provider")


def _probe_models(
    base_url: str, api_key: Optional[str]
) -> Tuple[List[str], Optional[str], bool]:
    """GET /models. Returns (model ids, error message, whether a key is needed)."""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        data = HttpEndpoint(base_url).get_json("/models", headers=headers, timeout=5)
    except HttpStatusError as e:
        return [], str(e), e.status in (401, 403)
    except Exception as e:
        return [], str(e), False
    models = data.get("data", []) if isinstance(data, dict) else []
    return (
        sorted(m["id"] for m in models if isinstance(m, dict) and m.get("id")),
        None,
        False,
    )


def _choose_model(
    field: Dict[str, Any], models: List[str], current: Optional[str]
) -> str:
    """Pick from ``models`` (or type a name); falls back to typing when there are none."""
    if models:
        choices = [Choice(m, m, current=m == current) for m in models]
        choices.append(Choice(_OTHER, "Other...", "Type a model name"))
        picked = _need(
            select(
                "Which model?",
                choices,
                default=current if current in models else models[0],
                filterable=len(models) > 9,
                summary="Model",
            )
        )
        if picked is not _OTHER:
            return picked
    value = ""
    while not value:
        value = ask_text(
            field["label"], default=current or "", example=field.get("help_text", "")
        )
    return value


class SetupWizard:
    """Interactive provider setup, generated from provider metadata."""

    @staticmethod
    def run(config) -> Dict[str, Any]:
        """
        Run the wizard.

        Secrets go straight to the credential store; the returned dict holds the
        non-secret settings to merge into config.json.

        Raises:
            KeyboardInterrupt: The user cancelled (Ctrl+C or Esc)
        """
        console.print(
            Panel.fit(
                "[bold cyan]Welcome to Kubrick![/bold cyan]\n\n"
                "Let's connect a model. Use the arrow keys and Enter to choose.\n"
                "[dim]Rerun this any time with `kubrick setup` (or /setup in a session).[/dim]",
                border_style="cyan",
            )
        )
        current = None if config.first_run else config.get("provider")
        metadata = _need(choose_provider(current))
        settings = SetupWizard.configure_provider(config, metadata)
        settings["provider"] = metadata.name
        console.print(
            f"\n[green]{glyph('check')} {escape(metadata.display_name)} is set up.[/green] "
            f"[dim]API keys are kept in the {config.credentials.backend_name} "
            "credential store, never in config.json.[/dim]\n"
        )
        return settings

    @staticmethod
    def configure_provider(config, metadata) -> Dict[str, Any]:
        """Ask for a provider's settings; returns the non-secret values.

        Raises:
            KeyboardInterrupt: The user cancelled
        """
        if metadata.name == "openai_compatible":
            return _configure_local_server(config, metadata)
        if metadata.name == "bedrock":
            return _configure_bedrock(config, metadata)

        settings: Dict[str, Any] = {}
        secrets: Dict[str, str] = {}
        fields = [f for f in metadata.config_fields if not f.get("advanced")]
        # Everything else first, so the model list can be fetched with it.
        for field in sorted(fields, key=lambda f: f.get("type") == "model"):
            key = field["key"]
            current = config.get(key)
            if current in (None, ""):
                current = field.get("default")
            field_type = field.get("type", "text")

            if field_type in ("secret", "password"):
                value = _ask_secret(config, field)
                if value:
                    secrets[key] = value
            elif field.get("choices"):
                if field.get("help_text"):
                    console.print(f"[dim]{escape(field['help_text'])}[/dim]")
                settings[key] = _need(
                    select(
                        f"{field['label']}?",
                        [Choice(v, v, d) for v, d in field["choices"]],
                        default=current,
                        summary=field["label"],
                    )
                )
            elif field_type == "model":
                settings[key] = _ask_model(
                    config, metadata, field, settings, secrets, current
                )
            else:
                settings[key] = ask_text(
                    field["label"],
                    default=str(current or ""),
                    example=field.get("help_text", ""),
                )
        return settings


def _ask_secret(config, field: Dict[str, Any]) -> Optional[str]:
    """Ask for (or keep) an API key; stores it and returns it."""
    key = field["key"]
    env = next((e for e in field.get("env", []) if os.environ.get(e)), None)
    if env:
        console.print(
            f"[dim]{escape(field['label'])}: using ${env} from the environment[/dim]"
        )
        return os.environ[env]
    stored = config.credentials.get(key)
    if stored:
        keep = _need(
            select(
                f"A {field['label']} is already saved.",
                [Choice(True, "Keep it"), Choice(False, "Replace it")],
                summary=field["label"],
            )
        )
        if keep:
            return stored
    value = prompt_secret("", field)
    if value:
        config.credentials.set(key, value)
        console.print(f"[green]{glyph('check')} Saved {escape(field['label'])}[/green]")
    elif is_required(field):
        console.print(
            "[yellow]Skipped; add it later with `kubrick auth login`.[/yellow]"
        )
    return value


def _ask_model(config, metadata, field, settings, secrets, current) -> str:
    """Offer the provider's model list, checking the credentials on the way."""
    while True:
        values = {f["key"]: config.get(f["key"]) for f in metadata.config_fields}
        values.update(
            {
                f["key"]: f.get("default")
                for f in metadata.config_fields
                if values.get(f["key"]) in (None, "")
            }
        )
        values.update(settings)
        values.update(secrets)
        models: List[str] = []
        with console.status(
            f"Fetching models from {metadata.display_name}{glyph('ellipsis')}"
        ):
            try:
                models = ProviderFactory.instantiate(
                    metadata.name, values
                ).list_models()
            except Exception:
                models = []
        if models or not metadata.secret_fields:
            return _choose_model(field, models, current)
        console.print(
            "[yellow]Couldn't list models: the API key may be wrong, or the network "
            "blocks the API.[/yellow]"
        )
        retry = _need(
            select(
                "What now?",
                [
                    Choice("key", "Re-enter the API key"),
                    Choice("type", "Type a model name and continue"),
                ],
            )
        )
        if retry == "type":
            return _choose_model(field, [], current)
        for secret_field in metadata.secret_fields:
            value = prompt_secret("", secret_field)
            if value:
                config.credentials.set(secret_field["key"], value)
                secrets[secret_field["key"]] = value


AWS_PASTE_EXAMPLE = (
    "Paste the lines your credentials page gives you, e.g. AWS_ACCESS_KEY_ID=... "
    "AWS_SECRET_ACCESS_KEY=... AWS_SESSION_TOKEN=... (with or without `export`). "
    "Input is hidden."
)


def ask_aws_credentials() -> Dict[str, str]:
    """Ask for a pasted block of AWS credentials until it parses (empty = give up)."""
    while True:
        text = ask_block("AWS credentials", example=AWS_PASTE_EXAMPLE)
        if not text.strip():
            return {}
        values = awscreds.parse_env_text(text)
        if awscreds.is_usable(values):
            found = ", ".join(k for k in awscreds.KNOWN_KEYS if k in values)
            expiry = awscreds.describe_expiry(values)
            console.print(
                f"[green]{glyph('check')} Got {escape(found)}[/green]"
                + (f" [dim]({expiry})[/dim]" if expiry else "")
            )
            return values
        console.print(
            "[yellow]Couldn't find AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY (or "
            "AWS_BEARER_TOKEN_BEDROCK) in that. Try again, or press Enter to "
            "cancel.[/yellow]"
        )


def store_aws_credentials(config, values: Dict[str, str], credentials_file=None):
    """Save pasted credentials: back into the .env file in use, else the encrypted store."""
    if credentials_file:
        awscreds.write_env_file(credentials_file, values)
        console.print(f"[dim]Updated {escape(credentials_file)}[/dim]")
    else:
        config.credentials.set("bedrock_aws_credentials", awscreds.to_json(values))
        console.print(
            f"[dim]Saved to the {config.credentials.backend_name} credential store "
            "(encrypted).[/dim]"
        )


def _configure_bedrock(config, metadata) -> Dict[str, Any]:
    """Credential source -> region -> model."""
    current = (
        lambda key: (None if config.first_run else config.get(key)) or ""
    )  # noqa: E731
    source = _need(
        select(
            "How do you get AWS credentials?",
            [
                Choice(
                    "paste",
                    "Paste them",
                    "KEY=VALUE or export lines from a credentials page; stored encrypted",
                ),
                Choice(
                    "file",
                    "A .env file",
                    "AWS_ACCESS_KEY_ID=... lines in a file you keep updated",
                    current=bool(current("bedrock_credentials_file")),
                ),
                Choice(
                    "profile",
                    "An AWS profile",
                    "~/.aws/credentials or SSO (aws sso login)",
                    current=bool(current("bedrock_profile")),
                ),
                Choice(
                    "chain",
                    "Environment / default AWS setup",
                    "AWS_* environment variables, instance role, AWS_BEARER_TOKEN_BEDROCK",
                ),
            ],
            summary="AWS credentials",
        )
    )
    settings: Dict[str, Any] = {
        "bedrock_profile": "",
        "bedrock_credentials_file": "",
    }
    values: Dict[str, str] = {}
    if source == "paste":
        values = ask_aws_credentials()
        if not values:
            raise SetupCancelled()
        store_aws_credentials(config, values)
    elif source == "file":
        while True:
            path = ask_text(
                "Credentials file",
                default=current("bedrock_credentials_file") or "~/.aws/kubrick.env",
                example="Lines like AWS_ACCESS_KEY_ID=...; Kubrick re-reads it when "
                "the keys expire, so just update the file.",
            )
            values = awscreds.load_env_file(path)
            if awscreds.is_usable(values):
                break
            console.print(
                f"[yellow]No AWS keys found in {escape(path)}.[/yellow] "
                "[dim]Create it first (chmod 600), or pick another file.[/dim]"
            )
        settings["bedrock_credentials_file"] = path
        expiry = awscreds.describe_expiry(values)
        if expiry:
            console.print(f"[dim]Credentials {expiry}.[/dim]")
    elif source == "profile":
        settings["bedrock_profile"] = ask_text(
            "AWS profile name", default=current("bedrock_profile") or "default"
        )

    region = ask_text(
        "AWS region",
        default=awscreds.region_of(values) or current("bedrock_region") or "us-east-1",
        example="e.g. us-east-1, us-west-2, us-gov-west-1",
    )
    settings["bedrock_region"] = region

    values_for_listing = {
        "bedrock_region": region,
        "bedrock_profile": settings["bedrock_profile"],
        "bedrock_credentials_file": settings["bedrock_credentials_file"],
        "bedrock_aws_credentials": (
            awscreds.to_json(values) if source == "paste" else None
        ),
    }
    with console.status(f"Fetching models from Bedrock{glyph('ellipsis')}"):
        try:
            models = ProviderFactory.instantiate(
                "bedrock", values_for_listing
            ).list_models()
        except Exception:
            models = []
    if not models:
        console.print(
            "[yellow]Couldn't list models (check the credentials, region, and "
            "bedrock:ListFoundationModels permission). Type a model ID instead.[/yellow]"
        )
    fields = {f["key"]: f for f in metadata.config_fields}
    settings["bedrock_model"] = _choose_model(
        fields["bedrock_model"], models, current("bedrock_model") or None
    )
    return settings


def _report_context_window(url: str, model: str, api_key: Optional[str]):
    """Warn when the server runs the model with too little context for an agent."""
    from .providers.openai_provider import OpenAICompatibleProvider

    try:
        window = OpenAICompatibleProvider(model, url, api_key).context_window()
    except Exception:
        window = None
    if window and window >= 16000:
        console.print(f"[dim]Context window: {window:,} tokens[/dim]")
        return
    size = f"only {window:,} tokens" if window else "unknown until the model loads"
    console.print(
        f"[yellow]Context window is {size}.[/yellow] [dim]Kubrick needs 16k+ "
        "(32k+ is better). Ollama: set OLLAMA_CONTEXT_LENGTH=32768 on the server. "
        "vLLM: --max-model-len. llama.cpp: -c.[/dim]"
    )


def _configure_local_server(config, metadata) -> Dict[str, Any]:
    """Server type -> host:port (checked live) -> model."""
    url_key, model_key, key_key = (
        "openai_compatible_base_url",
        "openai_compatible_model",
        "openai_compatible_api_key",
    )
    fields = {f["key"]: f for f in metadata.config_fields}
    current_url = None if config.first_run else config.get(url_key)
    current_port = (
        urlparse(normalize_server_url(current_url)).port if current_url else None
    )

    server = _need(
        select(
            "Which server are you running?",
            [
                Choice(
                    s,
                    s[1],
                    f"usually port {s[2]}" if s[2] else "any OpenAI-compatible /v1 API",
                    current=current_port is not None and s[2] == current_port,
                )
                for s in LOCAL_SERVERS
            ],
            summary="Server",
        )
    )
    _, _, port, remote_tip = server
    if current_url and (port is None or current_port == port):
        parsed = urlparse(normalize_server_url(current_url))
        default = f"{parsed.hostname}:{parsed.port}" if parsed.port else parsed.hostname
        if parsed.path not in ("", "/v1") or parsed.scheme == "https":
            default = current_url
    else:
        default = f"localhost:{port or 8000}"

    api_key = config.get_secret(key_key, fields[key_key].get("env", []))
    while True:
        address = ask_text(
            "Server address",
            default=default,
            example=(
                f"host:port, e.g. {default} or 192.168.1.50:{port or 8000} for another "
                "machine. http:// and /v1 are added for you."
            ),
        )
        url = normalize_server_url(address)
        with console.status(f"Connecting to {url}{glyph('ellipsis')}"):
            models, error, needs_key = _probe_models(url, api_key)
        if needs_key:
            console.print("[yellow]The server wants an API key.[/yellow]")
            api_key = prompt_secret("", fields[key_key])
            if api_key:
                config.credentials.set(key_key, api_key)
            default = address
            continue
        if error is None:
            count = f"{len(models)} model{'s' if len(models) != 1 else ''}"
            console.print(
                f"[green]{glyph('check')} Connected to {escape(url)} ({count})[/green]"
            )
            break
        console.print(
            f"[yellow]Couldn't connect to {escape(url)}: {escape(error)}[/yellow]"
        )
        host = urlparse(url).hostname or ""
        if remote_tip and host not in ("localhost", "127.0.0.1", "::1"):
            console.print(f"[dim]{escape(remote_tip)}[/dim]")
        action = _need(
            select(
                "What now?",
                [
                    Choice("retry", "Try a different address"),
                    Choice(
                        "keep",
                        "Use this address anyway",
                        "e.g. the server isn't running yet",
                    ),
                ],
            )
        )
        default = address
        if action == "keep":
            break

    current_model = None if config.first_run else config.get(model_key)
    model = _choose_model(fields[model_key], models, current_model)
    _report_context_window(url, model, api_key)
    return {url_key: url, model_key: model}


# --- `kubrick auth` ----------------------------------------------------------


def _secret_fields(provider: Optional[str]):
    providers = ProviderFactory.list_available_providers()
    if provider:
        providers = [ProviderFactory.get_provider_metadata(provider)]
    for metadata in providers:
        for field in metadata.secret_fields:
            yield metadata, field


def _bedrock_status(config) -> str:
    """Where Bedrock credentials come from, with expiry when known."""
    if config.get("bedrock_profile"):
        return f"AWS profile {config.get('bedrock_profile')}"
    values, where = {}, ""
    if config.get("bedrock_credentials_file"):
        where = f"file {config.get('bedrock_credentials_file')}"
        values = awscreds.load_env_file(config.get("bedrock_credentials_file"))
    else:
        values = awscreds.from_json(config.credentials.get("bedrock_aws_credentials"))
        where = "pasted (encrypted store)" if values else "default AWS chain"
    expiry = awscreds.describe_expiry(values)
    return where + (f", {expiry}" if expiry else "")


def auth_login(config, provider: Optional[str]) -> int:
    """Prompt for and store the API key(s) of a provider."""
    provider = provider or config.get("provider")
    metadata = ProviderFactory.get_provider_metadata(provider)
    if metadata.name == "bedrock":
        values = ask_aws_credentials()
        if values:
            store_aws_credentials(
                config, values, config.get("bedrock_credentials_file")
            )
        return 0
    if not metadata.secret_fields:
        console.print(f"{metadata.display_name} has no API keys to store.")
        return 0
    for field in metadata.secret_fields:
        value = prompt_secret(metadata.name, field)
        if value:
            config.credentials.set(field["key"], value)
            console.print(
                f"[green]✓ Stored {field['label']} in the "
                f"{config.credentials.backend_name} credential store.[/green]"
            )
    return 0


def auth_logout(config, provider: Optional[str]) -> int:
    """Delete stored API key(s) (all providers if none given)."""
    removed = 0
    for metadata, field in _secret_fields(provider):
        if config.credentials.delete(field["key"]):
            removed += 1
            console.print(f"Removed {metadata.display_name} {field['label']}")
    if not removed:
        console.print("Nothing stored to remove.")
    return 0


def auth_status(config) -> int:
    """Show where each provider's credentials come from (never the values)."""
    store = config.credentials
    stored = {row["key"]: row for row in store.status()}
    table = Table(title=f"Credentials (store: {store.backend_name})")
    table.add_column("Provider", style="cyan")
    table.add_column("Credential")
    table.add_column("Source")
    table.add_column("Stored at")
    for metadata, field in _secret_fields(None):
        if field["key"] == "bedrock_aws_credentials":
            table.add_row(
                metadata.display_name, "AWS credentials", _bedrock_status(config), ""
            )
            continue
        env = next((e for e in field.get("env", []) if os.environ.get(e)), None)
        row = stored.get(field["key"])
        if env:
            source = f"[green]env ${env}[/green]"
        elif row and row["readable"] and not row["expired"]:
            source = f"[green]{store.backend_name}[/green]"
        elif row and row["expired"]:
            source = "[yellow]expired — run kubrick auth login[/yellow]"
        elif row:
            source = "[yellow]unreadable (machine key changed) — re-login[/yellow]"
        else:
            source = "[dim]not set[/dim]"
        table.add_row(
            metadata.display_name,
            field["label"],
            source,
            (row or {}).get("created_at") or "",
        )
    console.print(table)
    console.print(
        "[dim]Bedrock: paste keys with `kubrick auth login bedrock`, or use a .env "
        "file, an AWS profile/SSO, or the default AWS chain (`kubrick setup`).[/dim]"
    )
    return 0
