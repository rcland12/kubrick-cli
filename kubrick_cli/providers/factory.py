"""Provider factory with automatic provider discovery."""

import importlib
import inspect
import pkgutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type

from .base import ProviderAdapter, ProviderMetadata


class MissingCredentialError(ValueError):
    """A required secret (API key) is not configured."""

    def __init__(self, provider: str, field: Dict[str, Any]):
        self.provider = provider
        self.field = field
        env = ", ".join(field.get("env", []))
        hint = f" or set {env}" if env else ""
        super().__init__(
            f"No {field['label']} configured. Run `kubrick auth login {provider}`{hint}."
        )


def is_required(field: Dict[str, Any]) -> bool:
    """Whether a config field must have a value."""
    return field.get("required", "default" not in field)


class ProviderFactory:
    """
    Factory for creating provider adapter instances with automatic discovery.

    Any class in this package that inherits from ProviderAdapter and defines
    METADATA is registered under ``METADATA.name``.
    """

    _provider_registry: Dict[str, Type[ProviderAdapter]] = {}
    _discovered = False

    @classmethod
    def _discover_providers(cls):
        """Import every module in the providers package and register adapters."""
        if cls._discovered:
            return

        providers_dir = Path(__file__).parent

        for module_info in pkgutil.iter_modules([str(providers_dir)]):
            module_name = module_info.name

            if module_name in ("base", "factory", "http", "__init__"):
                continue

            try:
                module = importlib.import_module(f"kubrick_cli.providers.{module_name}")
            except Exception as e:
                print(f"Warning: Failed to load provider from {module_name}: {e}")
                continue

            for _, obj in inspect.getmembers(module, inspect.isclass):
                if (
                    issubclass(obj, ProviderAdapter)
                    and obj is not ProviderAdapter
                    and obj.__dict__.get("METADATA") is not None
                ):
                    cls._provider_registry[obj.METADATA.name.lower()] = obj

        cls._discovered = True

    @classmethod
    def resolve_settings(
        cls,
        config,
        provider_name: str,
        prompt_secret: Optional[Callable[[str, Dict[str, Any]], Optional[str]]] = None,
    ) -> Dict[str, Any]:
        """
        Resolve every config field of a provider to a value.

        Args:
            config: KubrickConfig
            provider_name: Provider to resolve
            prompt_secret: Called as ``prompt_secret(provider, field)`` when a
                required secret is missing; a returned value is saved to the
                credential store. If None, a missing secret raises.

        Raises:
            MissingCredentialError: A required secret is missing
            ValueError: Unknown provider or a required setting is missing
        """
        metadata = cls.get_provider_metadata(provider_name)
        values: Dict[str, Any] = {}
        for field in metadata.config_fields:
            key = field["key"]
            if field.get("type") in ("secret", "password"):
                value = config.get_secret(key, field.get("env", []))
                if not value and is_required(field):
                    if prompt_secret is None:
                        raise MissingCredentialError(metadata.name, field)
                    value = prompt_secret(metadata.name, field)
                    if not value:
                        raise MissingCredentialError(metadata.name, field)
                    config.credentials.set(key, value)
            else:
                value = config.get(key)
                if value in (None, ""):
                    value = field.get("default")
                if value in (None, "") and is_required(field):
                    raise ValueError(
                        f"{metadata.display_name} setting '{key}' is not configured. "
                        f"Run `kubrick setup` or `/config {key} <value>`."
                    )
            values[key] = value
        return values

    @classmethod
    def create_provider(
        cls,
        config,
        provider_name: Optional[str] = None,
        prompt_secret: Optional[Callable[[str, Dict[str, Any]], Optional[str]]] = None,
    ) -> ProviderAdapter:
        """
        Create a provider instance from configuration.

        Args:
            config: KubrickConfig
            provider_name: Provider to create (default: the configured provider)
            prompt_secret: See ``resolve_settings``

        Returns:
            ProviderAdapter instance
        """
        cls._discover_providers()
        provider_name = (provider_name or config.get("provider") or "").lower()
        if provider_name not in cls._provider_registry:
            available = ", ".join(sorted(cls._provider_registry))
            raise ValueError(
                f"Unknown provider: {provider_name!r}. Available: {available}"
            )

        settings = cls.resolve_settings(config, provider_name, prompt_secret)
        return cls.instantiate(provider_name, settings)

    @classmethod
    def instantiate(
        cls, provider_name: str, settings: Dict[str, Any]
    ) -> ProviderAdapter:
        """Build a provider from already-resolved field values (keyed like config)."""
        cls._discover_providers()
        provider_class = cls._provider_registry[provider_name.lower()]
        init_params = {}
        for param_name in inspect.signature(provider_class.__init__).parameters:
            if param_name == "self":
                continue
            for key, value in settings.items():
                if key == param_name or key.endswith(f"_{param_name}"):
                    init_params[param_name] = value
                    break

        return provider_class(**init_params)

    @classmethod
    def list_available_providers(cls) -> List[ProviderMetadata]:
        """All discovered providers, local-first."""
        cls._discover_providers()
        order = ["openai_compatible", "anthropic", "openai", "bedrock", "triton"]
        providers = [p.METADATA for p in cls._provider_registry.values()]
        providers.sort(
            key=lambda p: (order.index(p.name) if p.name in order else 99, p.name)
        )
        return providers

    @classmethod
    def provider_names(cls) -> List[str]:
        """Names of all discovered providers."""
        return [p.name for p in cls.list_available_providers()]

    @classmethod
    def get_provider_metadata(cls, provider_name: str) -> ProviderMetadata:
        """
        Get metadata for a specific provider.

        Raises:
            ValueError: If provider not found
        """
        cls._discover_providers()
        provider_name = provider_name.lower()
        if provider_name not in cls._provider_registry:
            raise ValueError(f"Provider not found: {provider_name}")
        return cls._provider_registry[provider_name].METADATA
