"""Execution strategy configuration based on task complexity."""

from dataclasses import dataclass
from typing import Dict, Optional

from .classifier import TaskClassification


@dataclass
class ExecutionConfig:
    """Configuration for task execution."""

    mode: str  # "conversational", "agentic_simple", "agentic_complex"
    max_iterations: int
    use_agent_loop: bool
    use_planning: bool
    model_tier: str  # "fast", "balanced", "best"
    temperature: float
    max_tokens: Optional[int]
    hyperparameters: Dict


class ExecutionStrategy:
    """
    Determines execution strategy based on task classification.

    Optimizes for:
    - Cost (use smaller models for simple tasks)
    - Speed (fewer iterations for simple tasks)
    - Quality (best models for complex tasks)
    """

    # Model tiers by provider
    MODEL_TIERS = {
        "openai": {
            "fast": "gpt-3.5-turbo",
            "balanced": "gpt-4",
            "best": "gpt-4",
        },
        "anthropic": {
            "fast": "claude-3-haiku-20240307",
            "balanced": "claude-3-5-sonnet-20240620",
            "best": "claude-3-opus-20240229",
        },
        "triton": {
            # Triton uses same model for all tiers
            "fast": None,  # Use configured model
            "balanced": None,
            "best": None,
        },
    }

    @staticmethod
    def get_execution_config(
        classification: Optional[TaskClassification],
        provider_name: str,
        default_model: str,
    ) -> ExecutionConfig:
        """
        Get execution configuration based on task classification.

        Args:
            classification: Task classification result (None for fallback)
            provider_name: Provider name (triton, openai, anthropic)
            default_model: Default model name from config

        Returns:
            ExecutionConfig with optimized settings
        """
        # Handle None classification (fallback to simple)
        if classification is None:
            return ExecutionStrategy._simple_config(
                provider_name, default_model
            )

        complexity = classification.complexity

        if complexity == "CONVERSATIONAL":
            return ExecutionStrategy._conversational_config(
                provider_name, default_model
            )
        elif complexity == "SIMPLE":
            return ExecutionStrategy._simple_config(
                provider_name, default_model
            )
        elif complexity == "COMPLEX":
            return ExecutionStrategy._complex_config(
                provider_name, default_model
            )
        else:
            # Fallback to simple
            return ExecutionStrategy._simple_config(
                provider_name, default_model
            )

    @staticmethod
    def _conversational_config(
        provider_name: str, default_model: str
    ) -> ExecutionConfig:
        """
        Configuration for conversational tasks.

        - Single-turn response
        - No agent loop
        - Fast/cheap model
        - Higher temperature for creativity
        """
        # Get fast model for provider
        model_tier = ExecutionStrategy.MODEL_TIERS.get(
            provider_name, ExecutionStrategy.MODEL_TIERS["triton"]
        )
        fast_model = model_tier.get("fast") or default_model

        return ExecutionConfig(
            mode="conversational",
            max_iterations=1,
            use_agent_loop=False,
            use_planning=False,
            model_tier="fast",
            temperature=0.7,  # Higher for natural conversation
            max_tokens=1000,  # Shorter responses
            hyperparameters={
                "model": fast_model,
                "temperature": 0.7,
                "max_tokens": 1000,
            },
        )

    @staticmethod
    def _simple_config(
        provider_name: str, default_model: str
    ) -> ExecutionConfig:
        """
        Configuration for simple tasks.

        - Agent loop with low iterations
        - No planning phase
        - Balanced model
        - Medium temperature
        """
        model_tier = ExecutionStrategy.MODEL_TIERS.get(
            provider_name, ExecutionStrategy.MODEL_TIERS["triton"]
        )
        balanced_model = model_tier.get("balanced") or default_model

        return ExecutionConfig(
            mode="agentic_simple",
            max_iterations=5,  # Lower for simple tasks
            use_agent_loop=True,
            use_planning=False,  # Skip planning for simple tasks
            model_tier="balanced",
            temperature=0.4,  # Lower for accuracy
            max_tokens=2000,
            hyperparameters={
                "model": balanced_model,
                "temperature": 0.4,
                "max_tokens": 2000,
            },
        )

    @staticmethod
    def _complex_config(
        provider_name: str, default_model: str
    ) -> ExecutionConfig:
        """
        Configuration for complex tasks.

        - Full agent loop
        - Planning phase available
        - Best model
        - Low temperature for consistency
        """
        model_tier = ExecutionStrategy.MODEL_TIERS.get(
            provider_name, ExecutionStrategy.MODEL_TIERS["triton"]
        )
        best_model = model_tier.get("best") or default_model

        return ExecutionConfig(
            mode="agentic_complex",
            max_iterations=15,  # Full iterations
            use_agent_loop=True,
            use_planning=True,  # Enable planning for complex tasks
            model_tier="best",
            temperature=0.3,  # Lower for consistency
            max_tokens=4000,
            hyperparameters={
                "model": best_model,
                "temperature": 0.3,
                "max_tokens": 4000,
            },
        )

    @staticmethod
    def get_model_for_tier(
        provider_name: str, tier: str, default_model: str
    ) -> str:
        """
        Get model name for a specific tier.

        Args:
            provider_name: Provider name
            tier: Model tier (fast, balanced, best)
            default_model: Fallback model

        Returns:
            Model name
        """
        model_tier = ExecutionStrategy.MODEL_TIERS.get(
            provider_name, ExecutionStrategy.MODEL_TIERS["triton"]
        )
        return model_tier.get(tier) or default_model
