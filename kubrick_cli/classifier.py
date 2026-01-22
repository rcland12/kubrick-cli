"""Task complexity classification for intelligent routing."""

import json
from dataclasses import dataclass
from typing import Dict, List

from rich.console import Console

console = Console()


@dataclass
class TaskClassification:
    """Result of task classification."""

    complexity: str  # CONVERSATIONAL, SIMPLE, COMPLEX
    reasoning: str
    estimated_tool_calls: int
    requires_tools: bool


class TaskClassifier:
    """
    Classifies tasks into three tiers to determine execution strategy.

    CONVERSATIONAL:
    - Greetings, questions, general chat
    - No tool calls needed
    - Single-turn response sufficient

    SIMPLE:
    - Single file operations
    - Clear, specific scope
    - Estimated 1-5 tool calls
    - Low iteration count (3-5)

    COMPLEX:
    - Multi-file operations
    - Architectural changes
    - Uncertain scope
    - Estimated >5 tool calls
    - Full iteration count (15)
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
    ) -> TaskClassification:
        """
        Classify a task into CONVERSATIONAL, SIMPLE, or COMPLEX.

        Args:
            user_message: The user's task request
            conversation_history: Optional conversation context

        Returns:
            TaskClassification object with detailed classification
        """
        classification_messages = [
            {
                "role": "system",
                "content": """You are a task complexity classifier for a coding assistant.

Your job is to classify tasks into three tiers: CONVERSATIONAL, SIMPLE, or COMPLEX.

# Classification Criteria

**CONVERSATIONAL:**
- Greetings, questions, general chat
- Creative requests (poems, stories, jokes)
- Explanations or teaching
- No file operations or code changes needed
- No tools required
- Estimated 0 tool calls
- Examples:
  - "Hi", "Hello", "How are you?"
  - "What can you do?"
  - "Explain what async/await means"
  - "Tell me about this project"
  - "Write me a poem about X"
  - "Tell me a joke"
  - "Explain how X works"

**SIMPLE:**
- Single file operations (read, write, edit one file)
- Clear, specific scope with well-defined requirements
- Estimated 1-5 tool calls
- Examples:
  - "Read config.py"
  - "Create a hello world script"
  - "Fix the typo in line 42 of main.py"
  - "List all Python files"

**COMPLEX:**
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
  "complexity": "CONVERSATIONAL",
  "reasoning": "Brief explanation why",
  "estimated_tool_calls": 0,
  "requires_tools": false
}
```

OR

```json
{
  "complexity": "SIMPLE",
  "reasoning": "Brief explanation why",
  "estimated_tool_calls": 2,
  "requires_tools": true
}
```

OR

```json
{
  "complexity": "COMPLEX",
  "reasoning": "Brief explanation why",
  "estimated_tool_calls": 10,
  "requires_tools": true
}
```

Respond with ONLY the JSON object, no other text.""",
            },
            {"role": "user", "content": user_message},
        ]

        try:
            response = self.llm_client.generate(
                classification_messages, stream_options={}
            )

            json_start = response.find("{")
            json_end = response.rfind("}") + 1

            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                result = json.loads(json_str)

                complexity = result.get("complexity", "SIMPLE").upper()
                reasoning = result.get("reasoning", "No reasoning provided")
                estimated_tool_calls = result.get("estimated_tool_calls", 0)
                requires_tools = result.get("requires_tools", False)

                console.print(
                    f"[dim]→ Task classified as {complexity}: {reasoning}[/dim]"
                )

                return TaskClassification(
                    complexity=complexity,
                    reasoning=reasoning,
                    estimated_tool_calls=estimated_tool_calls,
                    requires_tools=requires_tools,
                )

            console.print(
                "[yellow]⚠ Classification parsing failed, defaulting to SIMPLE[/yellow]"
            )
            return TaskClassification(
                complexity="SIMPLE",
                reasoning="Parsing failed",
                estimated_tool_calls=3,
                requires_tools=True,
            )

        except Exception as e:
            console.print(
                f"[yellow]⚠ Classification error ({e}), defaulting to SIMPLE[/yellow]"
            )
            return TaskClassification(
                complexity="SIMPLE",
                reasoning=f"Error: {e}",
                estimated_tool_calls=3,
                requires_tools=True,
            )
