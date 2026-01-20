"""Provider factory with automatic provider discovery."""

import importlib
import inspect
import pkgutil
from pathlib import Path
from typing import Dict, List, Type

from .base import ProviderAdapter, ProviderMetadata


class ProviderFactory:
    """
    Factory for creating provider adapter instances with automatic discovery.

    This factory automatically discovers all provider classes in the providers
    directory that inherit from ProviderAdapter and have METADATA defined.
    """

    _provider_registry: Dict[str, Type[ProviderAdapter]] = {}
    _discovered = False

    @classmethod
    def _discover_providers(cls):
        """
        Discover all provider classes in the providers directory.

        This method scans the providers package for classes that:
        1. Inherit from ProviderAdapter
        2. Are not the base ProviderAdapter class itself
        3. Have a METADATA attribute defined
        """
        if cls._discovered:
            return

        providers_dir = Path(__file__).parent

        for module_info in pkgutil.iter_modules([str(providers_dir)]):
            module_name = module_info.name

            if module_name in ("base", "factory", "__init__"):
                continue

            try:
                module = importlib.import_module(f"kubrick_cli.providers.{module_name}")

                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if (
                        issubclass(obj, ProviderAdapter)
                        and obj is not ProviderAdapter
                        and hasattr(obj, "METADATA")
                        and obj.METADATA is not None
                    ):
                        provider_name = obj.METADATA.name.lower()
                        cls._provider_registry[provider_name] = obj

            except Exception as e:
                print(f"Warning: Failed to load provider from {module_name}: {e}")
                continue

        cls._discovered = True

    @classmethod
    def create_provider(cls, config: Dict) -> ProviderAdapter:
        """
        Create a provider instance based on configuration.

        Args:
            config: Configuration dictionary containing provider settings

        Returns:
            ProviderAdapter instance

        Raises:
            ValueError: If provider is invalid or required credentials are missing
        """
        cls._discover_providers()

        provider_name = config.get("provider", "triton").lower()

        if provider_name not in cls._provider_registry:
            available = ", ".join(cls._provider_registry.keys())
            raise ValueError(
                f"Unknown provider: {provider_name}. "
                f"Available providers: {available}"
            )

        provider_class = cls._provider_registry[provider_name]
        metadata = provider_class.METADATA

        provider_config = {}
        for field in metadata.config_fields:
            key = field["key"]
            value = config.get(key)

            if value is None and "default" not in field:
                raise ValueError(
                    f"{metadata.display_name} configuration missing required field: '{key}'. "
                    f"Please run setup wizard or add '{key}' to config."
                )

            provider_config[key] = value if value is not None else field.get("default")

        init_signature = inspect.signature(provider_class.__init__)
        init_params = {}

        for param_name, param in init_signature.parameters.items():
            if param_name == "self":
                continue

            for field in metadata.config_fields:
                if field["key"] == param_name or field["key"].endswith(
                    f"_{param_name}"
                ):
                    init_params[param_name] = provider_config[field["key"]]
                    break

        return provider_class(**init_params)

    @classmethod
    def list_available_providers(cls) -> List[ProviderMetadata]:
        """
        Get list of available providers with their metadata.

        Returns:
            List of ProviderMetadata objects
        """
        cls._discover_providers()

        providers = []
        for provider_class in cls._provider_registry.values():
            if provider_class.METADATA:
                providers.append(provider_class.METADATA)

        def sort_key(p):
            return (0, "") if p.name == "triton" else (1, p.name)

        providers.sort(key=sort_key)
        return providers

    @classmethod
    def get_provider_metadata(cls, provider_name: str) -> ProviderMetadata:
        """
        Get metadata for a specific provider.

        Args:
            provider_name: Name of the provider

        Returns:
            ProviderMetadata object

        Raises:
            ValueError: If provider not found
        """
        cls._discover_providers()

        provider_name = provider_name.lower()
        if provider_name not in cls._provider_registry:
            raise ValueError(f"Provider not found: {provider_name}")

        return cls._provider_registry[provider_name].METADATA
