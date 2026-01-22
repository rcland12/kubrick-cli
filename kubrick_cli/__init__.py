"""Kubrick CLI - AI-assisted coding tool with agentic capabilities."""

__version__ = "0.2.0"

from .agent_loop import AgentLoop, CompletionDetector
from .classifier import TaskClassification, TaskClassifier
from .config import KubrickConfig
from .display import DisplayManager
from .execution_strategy import ExecutionConfig, ExecutionStrategy
from .main import KubrickCLI
from .planning import PlanningPhase
from .progress import ProgressTracker
from .providers.anthropic_provider import AnthropicProvider
from .providers.base import ProviderAdapter
from .providers.factory import ProviderFactory
from .providers.openai_provider import OpenAIProvider
from .providers.triton_provider import TritonProvider
from .safety import SafetyConfig, SafetyManager
from .scheduler import ToolScheduler
from .setup_wizard import SetupWizard
from .tools import ToolExecutor
from .triton_client import TritonLLMClient

__all__ = [
    "AgentLoop",
    "AnthropicProvider",
    "CompletionDetector",
    "DisplayManager",
    "ExecutionConfig",
    "ExecutionStrategy",
    "KubrickCLI",
    "KubrickConfig",
    "OpenAIProvider",
    "PlanningPhase",
    "ProgressTracker",
    "ProviderAdapter",
    "ProviderFactory",
    "SafetyConfig",
    "SafetyManager",
    "SetupWizard",
    "TaskClassification",
    "TaskClassifier",
    "ToolExecutor",
    "ToolScheduler",
    "TritonLLMClient",
    "TritonProvider",
]
