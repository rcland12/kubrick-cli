# Creating Custom Providers for Kubrick

Kubrick has a truly plug-and-play provider system that allows you to add support for any LLM backend with minimal effort. This guide will walk you through creating a custom provider.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Provider Architecture](#provider-architecture)
- [Step-by-Step Guide](#step-by-step-guide)
- [Complete Example](#complete-example)
- [Testing Your Provider](#testing-your-provider)
- [Advanced Topics](#advanced-topics)

## Overview

The Kubrick provider system uses **automatic discovery**. This means:

1. Drop a new provider file in `kubrick_cli/providers/`
2. That's it! No need to edit any other files.

Your provider will automatically:

- Be discovered and registered
- Appear in the setup wizard
- Be available for use via configuration

## Quick Start

Here's the minimal code to create a custom provider:

```python
"""My custom provider adapter."""

from typing import Dict, Iterator, List
from .base import ProviderAdapter, ProviderMetadata


class MyCustomProvider(ProviderAdapter):
    """Provider adapter for My Custom LLM Service."""

    # Define metadata - this is what makes it auto-discoverable
    METADATA = ProviderMetadata(
        name="mycustom",
        display_name="My Custom LLM",
        description="My custom LLM service",
        config_fields=[
            {
                "key": "mycustom_api_key",
                "label": "API Key",
                "type": "password",
                "help_text": "Get your API key from: https://mycustom.example.com",
            },
            {
                "key": "mycustom_model",
                "label": "Model name",
                "type": "text",
                "default": "default-model",
            },
        ],
    )

    def __init__(self, mycustom_api_key: str, mycustom_model: str = "default-model"):
        """Initialize the provider."""
        self.api_key = mycustom_api_key
        self._model_name = mycustom_model

    def generate_streaming(self, messages: List[Dict[str, str]], stream_options: Dict = None) -> Iterator[str]:
        """Generate streaming response."""
        # Your streaming implementation here
        yield "Hello from custom provider!"

    def generate(self, messages: List[Dict[str, str]], stream_options: Dict = None) -> str:
        """Generate non-streaming response."""
        return "".join(self.generate_streaming(messages, stream_options))

    def is_healthy(self) -> bool:
        """Check if provider is accessible."""
        return True

    @property
    def provider_name(self) -> str:
        """Get provider name."""
        return "mycustom"

    @property
    def model_name(self) -> str:
        """Get model name."""
        return self._model_name
```

Save this as `kubrick_cli/providers/mycustom_provider.py` and you're done!

## Provider Architecture

### Base Class: ProviderAdapter

All providers must inherit from `ProviderAdapter` which defines the interface:

```python
from kubrick_cli.providers import ProviderAdapter, ProviderMetadata

class MyProvider(ProviderAdapter):
    METADATA = ProviderMetadata(...)  # Required for auto-discovery

    def generate_streaming(self, messages, stream_options) -> Iterator[str]:
        """Streaming text generation"""
        pass

    def generate(self, messages, stream_options) -> str:
        """Non-streaming text generation"""
        pass

    def is_healthy(self) -> bool:
        """Health check"""
        pass

    @property
    def provider_name(self) -> str:
        """Provider identifier"""
        pass

    @property
    def model_name(self) -> str:
        """Model identifier"""
        pass
```

### Metadata System

The `METADATA` class attribute is what makes your provider discoverable. It tells Kubrick:

- **name**: Internal identifier (lowercase, no spaces)
- **display_name**: Human-readable name shown in UI
- **description**: Brief description for setup wizard
- **config_fields**: Configuration fields needed by this provider

## Step-by-Step Guide

### Step 1: Create the Provider File

Create a new Python file in `kubrick_cli/providers/` with a descriptive name:

```bash
kubrick_cli/providers/
├── base.py
├── factory.py
├── triton_provider.py
├── openai_provider.py
├── anthropic_provider.py
└── your_provider.py  # Your new file
```

### Step 2: Define Your Provider Class

```python
from typing import Dict, Iterator, List
from .base import ProviderAdapter, ProviderMetadata


class YourProvider(ProviderAdapter):
    """Provider adapter for Your LLM Service."""

    # This is required for auto-discovery
    METADATA = ProviderMetadata(
        name="yourprovider",           # Internal name (used in config)
        display_name="Your Provider",  # Shown in setup wizard
        description="Description of your provider",
        config_fields=[
            # Define configuration fields here
        ],
    )
```

### Step 3: Define Configuration Fields

Configuration fields tell Kubrick what information to collect during setup:

```python
config_fields=[
    {
        "key": "yourprovider_api_key",     # Config key name
        "label": "API Key",                 # Display label
        "type": "password",                 # Field type
        "help_text": "Get your key from: https://example.com",  # Optional
    },
    {
        "key": "yourprovider_endpoint",
        "label": "API Endpoint",
        "type": "url",
        "default": "https://api.example.com",  # Optional default value
    },
    {
        "key": "yourprovider_model",
        "label": "Model Name",
        "type": "text",
        "default": "default-model",
    },
]
```

**Field Types:**

- `text`: Regular text input
- `password`: Hidden password input
- `url`: URL input
- Custom types can be added by extending the setup wizard

**Important:** If a field has no `default`, it's considered required.

### Step 4: Implement the Constructor

The constructor parameters **must match** your config field keys:

```python
def __init__(
    self,
    yourprovider_api_key: str,           # Matches "yourprovider_api_key"
    yourprovider_endpoint: str = "https://api.example.com",
    yourprovider_model: str = "default-model"
):
    """
    Initialize your provider.

    Args:
        yourprovider_api_key: API key for authentication
        yourprovider_endpoint: API endpoint URL
        yourprovider_model: Model identifier
    """
    self.api_key = yourprovider_api_key
    self.endpoint = yourprovider_endpoint
    self._model_name = yourprovider_model
```

**Key Point:** Parameter names should match the config keys exactly, or at least the suffix after the provider name prefix.

### Step 5: Implement Required Methods

#### generate_streaming()

This method yields text chunks as they arrive:

```python
def generate_streaming(
    self,
    messages: List[Dict[str, str]],
    stream_options: Dict = None
) -> Iterator[str]:
    """
    Generate streaming response.

    Args:
        messages: List of message dicts with 'role' and 'content'
        stream_options: Optional parameters (temperature, max_tokens, etc.)

    Yields:
        Text chunks as they arrive from the LLM
    """
    # Your implementation here
    # Example using requests:
    import requests

    payload = {
        "model": self._model_name,
        "messages": messages,
        "stream": True,
    }

    response = requests.post(
        f"{self.endpoint}/chat/completions",
        headers={"Authorization": f"Bearer {self.api_key}"},
        json=payload,
        stream=True
    )

    for line in response.iter_lines():
        if line:
            # Parse and yield text chunk
            yield parse_chunk(line)
```

#### generate()

Non-streaming variant - usually just collects all chunks:

```python
def generate(
    self,
    messages: List[Dict[str, str]],
    stream_options: Dict = None
) -> str:
    """
    Generate complete response.

    Args:
        messages: List of message dicts
        stream_options: Optional parameters

    Returns:
        Complete response text
    """
    chunks = []
    for chunk in self.generate_streaming(messages, stream_options):
        chunks.append(chunk)
    return "".join(chunks)
```

#### is_healthy()

Health check to verify the service is accessible:

```python
def is_healthy(self) -> bool:
    """
    Check if the provider is healthy and accessible.

    Returns:
        True if healthy, False otherwise
    """
    try:
        # Attempt a simple request to verify connectivity
        response = requests.get(
            f"{self.endpoint}/health",
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=10
        )
        return response.status_code == 200
    except Exception:
        return False
```

#### Properties

```python
@property
def provider_name(self) -> str:
    """Get provider name."""
    return "yourprovider"  # Should match METADATA.name

@property
def model_name(self) -> str:
    """Get current model name."""
    return self._model_name
```

## Complete Example

Here's a complete example for a fictional "Cohere" provider:

```python
"""Cohere provider adapter."""

import http.client
import json
import ssl
from typing import Dict, Iterator, List

from .base import ProviderAdapter, ProviderMetadata


class CohereProvider(ProviderAdapter):
    """Provider adapter for Cohere API."""

    METADATA = ProviderMetadata(
        name="cohere",
        display_name="Cohere",
        description="Cohere API (Command, Command-Light, etc.)",
        config_fields=[
            {
                "key": "cohere_api_key",
                "label": "Cohere API key",
                "type": "password",
                "help_text": "Get your API key from: https://dashboard.cohere.ai/api-keys",
            },
            {
                "key": "cohere_model",
                "label": "Model name",
                "type": "text",
                "default": "command",
            },
        ],
    )

    def __init__(self, cohere_api_key: str, cohere_model: str = "command"):
        """
        Initialize Cohere provider.

        Args:
            cohere_api_key: Cohere API key
            cohere_model: Model name (default: command)
        """
        self.api_key = cohere_api_key
        self._model_name = cohere_model
        self.base_url = "api.cohere.ai"
        self.timeout = 600

    def generate_streaming(
        self, messages: List[Dict[str, str]], stream_options: Dict = None
    ) -> Iterator[str]:
        """
        Generate streaming response from Cohere.

        Args:
            messages: List of message dicts with 'role' and 'content'
            stream_options: Optional streaming parameters

        Yields:
            Text chunks as they arrive
        """
        # Convert messages to Cohere format
        # (Cohere uses 'chat_history' and 'message' instead of 'messages')
        chat_history = []
        current_message = ""

        for msg in messages:
            if msg["role"] == "user":
                current_message = msg["content"]
            elif msg["role"] == "assistant":
                chat_history.append({
                    "role": "CHATBOT",
                    "message": msg["content"]
                })

        # Build request payload
        payload = {
            "model": self._model_name,
            "message": current_message,
            "chat_history": chat_history,
            "stream": True,
        }

        # Add optional parameters
        if stream_options:
            if "temperature" in stream_options:
                payload["temperature"] = stream_options["temperature"]
            if "max_tokens" in stream_options:
                payload["max_tokens"] = stream_options["max_tokens"]

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        body = json.dumps(payload).encode("utf-8")

        # Create HTTPS connection
        context = ssl.create_default_context()
        conn = http.client.HTTPSConnection(
            self.base_url, 443, timeout=self.timeout, context=context
        )

        try:
            conn.request("POST", "/v1/chat", body=body, headers=headers)
            response = conn.getresponse()

            if response.status != 200:
                error_body = response.read().decode("utf-8")
                raise Exception(f"Cohere API error {response.status}: {error_body}")

            # Read streaming response
            buffer = ""
            while True:
                chunk = response.read(1024)
                if not chunk:
                    break

                if isinstance(chunk, bytes):
                    chunk = chunk.decode("utf-8")

                buffer += chunk

                # Process complete lines
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()

                    if not line:
                        continue

                    try:
                        data = json.loads(line)

                        # Cohere streaming format
                        if "text" in data:
                            yield data["text"]

                        if data.get("is_finished"):
                            return

                    except json.JSONDecodeError:
                        continue

        finally:
            conn.close()

    def generate(
        self, messages: List[Dict[str, str]], stream_options: Dict = None
    ) -> str:
        """
        Generate non-streaming response from Cohere.

        Args:
            messages: List of message dicts with 'role' and 'content'
            stream_options: Optional parameters

        Returns:
            Complete response text
        """
        chunks = []
        for chunk in self.generate_streaming(messages, stream_options):
            chunks.append(chunk)
        return "".join(chunks)

    def is_healthy(self) -> bool:
        """
        Check if Cohere API is accessible.

        Returns:
            True if healthy, False otherwise
        """
        try:
            context = ssl.create_default_context()
            conn = http.client.HTTPSConnection(
                self.base_url, 443, timeout=10, context=context
            )
            headers = {
                "Authorization": f"Bearer {self.api_key}",
            }
            conn.request("GET", "/v1/check-api-key", headers=headers)
            response = conn.getresponse()
            conn.close()
            return response.status == 200
        except Exception:
            return False

    @property
    def provider_name(self) -> str:
        """Get provider name."""
        return "cohere"

    @property
    def model_name(self) -> str:
        """Get model name."""
        return self._model_name

    def set_model(self, model_name: str):
        """Set model name dynamically."""
        self._model_name = model_name
```

## Testing Your Provider

### 1. Test Discovery

Create a simple test script:

```python
from kubrick_cli.providers.factory import ProviderFactory

# List all discovered providers
providers = ProviderFactory.list_available_providers()
for provider in providers:
    print(f"- {provider.display_name}: {provider.description}")
```

### 2. Test Configuration

Run the setup wizard:

```bash
rm ~/.kubrick/config.json  # Remove existing config
kubrick
```

Your provider should appear in the list!

### 3. Test Provider Creation

```python
from kubrick_cli.config import KubrickConfig
from kubrick_cli.providers.factory import ProviderFactory

config = KubrickConfig()
provider = ProviderFactory.create_provider(config.get_all())

# Test health check
print(f"Health check: {provider.is_healthy()}")

# Test generation
messages = [{"role": "user", "content": "Say hello!"}]
response = provider.generate(messages)
print(f"Response: {response}")
```

### 4. Test Streaming

```python
messages = [{"role": "user", "content": "Count to 5"}]
for chunk in provider.generate_streaming(messages):
    print(chunk, end="", flush=True)
print()
```

## Advanced Topics

### Multiple Configuration Profiles

Users can maintain multiple config files for different providers:

```bash
# Default config
~/.kubrick/config.json

# Custom configs
~/.kubrick/config-openai.json
~/.kubrick/config-anthropic.json
```

### Error Handling

Always handle errors gracefully:

```python
def generate_streaming(self, messages, stream_options=None):
    try:
        # Your implementation
        yield "response"
    except ConnectionError as e:
        raise Exception(f"Failed to connect to {self.provider_name}: {e}")
    except Exception as e:
        raise Exception(f"Error generating response: {e}")
```

### Custom Parameters

You can add provider-specific parameters:

```python
METADATA = ProviderMetadata(
    name="custom",
    display_name="Custom",
    description="Custom provider with special features",
    config_fields=[
        {
            "key": "custom_api_key",
            "label": "API Key",
            "type": "password",
        },
        {
            "key": "custom_region",
            "label": "Region",
            "type": "text",
            "default": "us-east-1",
            "help_text": "AWS region for deployment",
        },
        {
            "key": "custom_use_cache",
            "label": "Enable caching",
            "type": "text",
            "default": "true",
            "help_text": "Enable response caching (true/false)",
        },
    ],
)
```

### Using External Dependencies

If your provider needs external libraries, add them to `pyproject.toml`:

```toml
[project.optional-dependencies]
cohere = [
    "cohere>=4.0.0",
]
```

Then install with:

```bash
pip install -e ".[cohere]"
```

### Model Switching

Support dynamic model switching:

```python
def set_model(self, model_name: str):
    """
    Set model name dynamically.

    Args:
        model_name: New model identifier
    """
    self._model_name = model_name
    # Optionally validate or update other settings
```

## Summary

Creating a custom provider is simple:

1. **Create a file** in `kubrick_cli/providers/your_provider.py`
2. **Inherit from** `ProviderAdapter`
3. **Define METADATA** with provider info and config fields
4. **Implement required methods**: `generate_streaming()`, `generate()`, `is_healthy()`
5. **Test it** - it will automatically appear in the setup wizard!

No need to edit factory.py, setup_wizard.py, or any other files. The system automatically discovers and integrates your provider.

## Need Help?

- Check existing providers (`triton_provider.py`, `openai_provider.py`, `anthropic_provider.py`) for reference
- Review the base class documentation in `base.py`
- Test incrementally - start with a simple provider and add features gradually
- Use the setup wizard to verify your metadata is correct

Happy coding!
