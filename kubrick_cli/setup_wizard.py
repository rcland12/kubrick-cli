"""Setup wizard for first-time Kubrick configuration."""

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from .providers.factory import ProviderFactory

console = Console()


class SetupWizard:
    """
    Interactive setup wizard for Kubrick configuration.

    This wizard automatically discovers all available providers and
    generates the configuration UI based on provider metadata.
    """

    @staticmethod
    def run() -> dict:
        """
        Run the setup wizard.

        Returns:
            Dictionary with provider configuration
        """
        console.print(
            Panel.fit(
                "[bold cyan]Welcome to Kubrick![/bold cyan]\n\n"
                "Let's set up your AI provider.\n"
                "You can change these settings later in ~/.kubrick/config.json",
                border_style="cyan",
            )
        )

        # Step 1: Select provider (dynamically discovered)
        provider_metadata = SetupWizard._select_provider()

        # Step 2: Get provider-specific configuration (dynamic)
        config = SetupWizard._configure_provider(provider_metadata)
        config["provider"] = provider_metadata.name

        # Step 3: Show summary
        SetupWizard._show_summary(provider_metadata, config)

        console.print("\n[green]✓ Setup complete![/green]")
        console.print(
            "[dim]Your configuration has been saved to ~/.kubrick/config.json[/dim]\n"
        )

        return config

    @staticmethod
    def _select_provider():
        """
        Prompt user to select a provider from all discovered providers.

        Returns:
            ProviderMetadata object for selected provider
        """
        console.print("\n[bold]Step 1: Select Your AI Provider[/bold]\n")

        # Get all available providers
        providers = ProviderFactory.list_available_providers()

        if not providers:
            raise RuntimeError(
                "No providers found! Please ensure provider files are in kubrick_cli/providers/"
            )

        # Build provider table
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Option", style="cyan")
        table.add_column("Provider", style="green")
        table.add_column("Description")

        # Create mapping of choices to providers
        choice_map = {}
        for idx, provider in enumerate(providers, start=1):
            choice_map[str(idx)] = provider
            table.add_row(
                str(idx),
                provider.display_name,
                provider.description,
            )

        console.print(table)
        console.print()

        # Get user choice
        choices = list(choice_map.keys())
        choice = Prompt.ask(
            "[bold yellow]Choose your provider[/bold yellow]",
            choices=choices,
            default="1",
        )

        return choice_map[choice]

    @staticmethod
    def _configure_provider(metadata) -> dict:
        """
        Get provider-specific configuration based on metadata.

        Args:
            metadata: ProviderMetadata object

        Returns:
            Configuration dictionary
        """
        console.print(f"\n[bold]Step 2: Configure {metadata.display_name}[/bold]\n")

        config = {}

        for field in metadata.config_fields:
            key = field["key"]
            label = field["label"]
            field_type = field.get("type", "text")
            default = field.get("default")
            help_text = field.get("help_text")

            # Show help text if provided
            if help_text:
                console.print(f"[dim]{help_text}[/dim]\n")

            # Prompt for the value
            if field_type == "password":
                value = Prompt.ask(
                    f"[cyan]{label}[/cyan]",
                    password=True,
                )
            elif default is not None:
                value = Prompt.ask(
                    f"[cyan]{label}[/cyan]",
                    default=str(default),
                )
            else:
                value = Prompt.ask(f"[cyan]{label}[/cyan]")

            config[key] = value

        return config

    @staticmethod
    def _show_summary(metadata, config: dict):
        """
        Show configuration summary.

        Args:
            metadata: ProviderMetadata object
            config: Configuration dict
        """
        console.print("\n[bold]Configuration Summary[/bold]\n")

        console.print(f"[cyan]Provider:[/cyan] {metadata.display_name}")

        # Show each configured field
        for field in metadata.config_fields:
            key = field["key"]
            label = field["label"]
            field_type = field.get("type", "text")
            value = config.get(key)

            # Mask passwords
            if field_type == "password" and value:
                display_value = f"{'*' * 20}{value[-4:]}"
            else:
                display_value = value

            console.print(f"[cyan]{label}:[/cyan] {display_value}")
