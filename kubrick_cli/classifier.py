"""Task complexity classification for intelligent routing."""

import json
from typing import Dict, List

from rich.console import Console

console = Console()


class TaskClassifier:
    """
    Classifies tasks as SIMPLE or COMPLEX to determine execution strategy.

    SIMPLE tasks:
    - Single file operations
    - Clear, specific scope
    - Estimated <5 tool calls

    COMPLEX tasks:
    - Multi-file operations
    - Architectural changes
    - Uncertain scope
    - Estimated >5 tool calls
    """

    def __init__(self, llm_client):
        """
        Initialize task classifier.

        Args:
            llm_client: LLM client instance for classification
        """
        self.llm_client = llm_client

    def classify(
        self, user_message: str, conversation_history: List[Dict] = None
    ) -> str:
        """
        Classify a task as SIMPLE or COMPLEX.

        Args:
            user_message: The user's task request
            conversation_history: Optional conversation context

        Returns:
            "SIMPLE" or "COMPLEX"
        """
        # Build classification prompt
        classification_messages = [
            {
                "role": "system",
                "content": """You are a task complexity classifier for a coding assistant.

Your job is to classify tasks as SIMPLE or COMPLEX based on their scope and requirements.

# Classification Criteria

**SIMPLE tasks:**
- Single file operations (read, write, edit one file)
- Clear, specific scope with well-defined requirements
- Estimated <5 tool calls
- Examples:
  - "Read config.py"
  - "Create a hello world script"
  - "Fix the typo in line 42 of main.py"
  - "List all Python files"

**COMPLEX tasks:**
- Multi-file operations affecting multiple files
- Architectural changes or refactoring
- Uncertain scope requiring exploration
- Estimated >5 tool calls
- Examples:
  - "Add logging to all Python files"
  - "Refactor the authentication system"
  - "Implement a new feature"
  - "Debug why the tests are failing"

# Response Format

Respond with ONLY a JSON object:
```json
{
  "complexity": "SIMPLE",
  "reasoning": "Brief explanation why"
}
```

OR

```json
{
  "complexity": "COMPLEX",
  "reasoning": "Brief explanation why"
}
```

Respond with ONLY the JSON object, no other text.""",
            },
            {"role": "user", "content": user_message},
        ]

        try:
            # Get classification from LLM (non-streaming for speed)
            response = self.llm_client.generate(
                classification_messages, stream_options={}
            )

            # Parse JSON response
            # Look for JSON in the response
            json_start = response.find("{")
            json_end = response.rfind("}") + 1

            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                result = json.loads(json_str)

                complexity = result.get("complexity", "SIMPLE").upper()
                reasoning = result.get("reasoning", "No reasoning provided")

                console.print(
                    f"[dim]→ Task classified as {complexity}: {reasoning}[/dim]"
                )

                return complexity

            # Fallback: default to SIMPLE if parsing fails
            console.print(
                "[yellow]⚠ Classification parsing failed, defaulting to SIMPLE[/yellow]"
            )
            return "SIMPLE"

        except Exception as e:
            console.print(
                f"[yellow]⚠ Classification error ({e}), defaulting to SIMPLE[/yellow]"
            )
            return "SIMPLE"
