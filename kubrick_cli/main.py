#!/usr/bin/env python3
"""Main CLI entry point for Kubrick."""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from .agent_loop import AgentLoop
from .classifier import TaskClassifier
from .config import KubrickConfig
from .display import DisplayManager
from .execution_strategy import ExecutionStrategy
from .planning import PlanningPhase
from .providers.factory import ProviderFactory
from .safety import SafetyConfig, SafetyManager
from .scheduler import ToolScheduler
from .tools import TOOL_DEFINITIONS, ToolExecutor, get_tools_prompt

console = Console()


class KubrickCLI:
    """Main CLI application."""

    def __init__(
        self,
        config: KubrickConfig,
        working_dir: str = None,
        conversation_id: str = None,
        provider_override: str = None,
    ):
        """
        Initialize Kubrick CLI.

        Args:
            config: KubrickConfig instance
            working_dir: Working directory for file operations (overrides config)
            conversation_id: Load existing conversation by ID
            provider_override: Override configured provider (for testing)
        """
        self.config = config

        # Override provider if specified
        if provider_override:
            config.set("provider", provider_override)

        # Create provider using factory
        try:
            self.provider = ProviderFactory.create_provider(config.get_all())
            console.print(
                f"[dim]→ Using {self.provider.provider_name} provider "
                f"with model {self.provider.model_name}[/dim]"
            )
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            console.print(
                "[yellow]Please run the setup wizard or check your configuration.[/yellow]"
            )
            raise

        # Alias for backward compatibility
        self.client = self.provider

        # Initialize safety manager
        self.safety_manager = SafetyManager(
            SafetyConfig.from_config(config.get_all())
        )

        # Initialize tool executor with safety manager
        self.tool_executor = ToolExecutor(
            working_dir=working_dir, safety_manager=self.safety_manager
        )

        # Initialize display manager
        self.display_manager = DisplayManager(config.get_all())

        # Initialize tool scheduler
        enable_parallel = config.get("enable_parallel_tools", True)
        max_workers = config.get("max_parallel_workers", 3)
        self.tool_scheduler = ToolScheduler(
            tool_executor=self.tool_executor,
            max_workers=max_workers,
            enable_parallel=enable_parallel,
        )

        # Initialize agent loop with config values
        max_iterations = config.get("max_iterations", 15)
        max_tools_per_turn = config.get("max_tools_per_turn", 5)
        timeout_seconds = config.get("total_timeout_seconds", 600)

        self.agent_loop = AgentLoop(
            llm_client=self.provider,
            tool_executor=self.tool_executor,
            max_iterations=max_iterations,
            max_tools_per_turn=max_tools_per_turn,
            timeout_seconds=timeout_seconds,
            stream_options={},
            display_manager=self.display_manager,
            tool_scheduler=self.tool_scheduler,
        )

        # Initialize task classifier and planning phase
        self.classifier = TaskClassifier(self.provider)
        self.planning_phase = PlanningPhase(
            llm_client=self.provider,
            tool_executor=self.tool_executor,
            agent_loop=self.agent_loop,
        )

        # Interrupt handling state
        self.interrupt_count = 0

        # Generate conversation ID
        self.conversation_id = conversation_id or datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        # Initialize or load conversation
        if conversation_id:
            loaded = self._load_conversation(conversation_id)
            if loaded:
                self.messages = loaded
            else:
                console.print(
                    f"[yellow]Conversation {conversation_id} not found, starting new conversation[/yellow]"
                )
                self.messages = self._get_initial_messages()
        else:
            self.messages = self._get_initial_messages()

    def _get_initial_messages(self) -> list:
        """Get initial system prompt messages."""
        return [
            {
                "role": "system",
                "content": f"""You are Kubrick, an AI coding assistant with agentic capabilities and file system access.

Current working directory: {self.tool_executor.working_dir}

# Agentic Behavior

You can ITERATE through multiple tool calls until a task is complete. You are not limited to a single response.

## Process

1. Call tools to gather information or make changes
2. Analyze the results
3. Continue calling tools as needed
4. Signal completion when done

# Completion Signal

When you've completed the task, say "TASK_COMPLETE" followed by a summary of what you accomplished.

# Tool Call Format (EXACT SYNTAX REQUIRED)

```tool_call
{{
  "tool": "tool_name",
  "parameters": {{
    "param": "value"
  }}
}}
```

# Available Tools

{get_tools_prompt()}

# How to Explore Directories

To explore the full codebase structure:
- Use `list_files` with pattern `**/*.py` to list all Python files recursively
- Use `list_files` with pattern `**/*` to see ALL files and directories
- Use `run_bash` with `find . -type f` to list all files
- Use `run_bash` with `tree` or `ls -R` to see directory structure

Example - list all Python files:
```tool_call
{{
  "tool": "list_files",
  "parameters": {{
    "pattern": "**/*.py"
  }}
}}
```

# Important Rules

1. **ITERATE**: Call tools immediately when needed, then analyze results and continue iterating
2. **MULTIPLE TOOLS**: You can call multiple tools per response
3. **READ BEFORE EDIT**: Always read a file before editing it
4. **EXPLORE THOROUGHLY**: Use `**/*` patterns to see all files in subdirectories
5. **SIGNAL COMPLETION**: Say "TASK_COMPLETE" when the task is done
6. **USE TOOLS IMMEDIATELY**: Don't ask permission - just call the tool

# Examples

User: "Read the config.pbtxt file"
Assistant: I'll read that file for you.

```tool_call
{{
  "tool": "read_file",
  "parameters": {{
    "file_path": "config.pbtxt"
  }}
}}
```

User: "Create a new Python script called test.py with a hello world function"
Assistant: I'll create that file for you.

```tool_call
{{
  "tool": "write_file",
  "parameters": {{
    "file_path": "test.py",
    "content": "def hello_world():\\n    print('Hello, World!')\\n\\nif __name__ == '__main__':\\n    hello_world()\\n"
  }}
}}
```

User: "Read main.py and add logging to all functions"
Assistant: I'll first read the file to understand its structure.

```tool_call
{{
  "tool": "read_file",
  "parameters": {{
    "file_path": "main.py"
  }}
}}
```

[After seeing the results, I'll add logging and continue iterating until done, then say TASK_COMPLETE]
""",
            }
        ]

    def _load_conversation(self, conversation_id: str) -> list:
        """Load a conversation by ID."""
        data = self.config.load_conversation(conversation_id)
        if data:
            return data.get("messages", [])
        return None

    def _save_conversation(self):
        """Save current conversation to disk."""
        if self.config.get("auto_save_conversations", True):
            metadata = {
                "working_dir": str(self.tool_executor.working_dir),
                "provider": self.provider.provider_name,
                "model_name": self.provider.model_name,
                "saved_at": datetime.now().isoformat(),
            }
            self.config.save_conversation(
                self.conversation_id, self.messages, metadata
            )

    def parse_tool_calls(self, text: str) -> list:
        """
        Parse tool calls from LLM response.

        Args:
            text: Response text from LLM

        Returns:
            List of (tool_name, parameters) tuples
        """
        tool_calls = []

        # Primary parser: Find all ```tool_call blocks (correct format)
        pattern = r"```tool_call\s*\n(.*?)\n```"
        matches = re.findall(pattern, text, re.DOTALL)

        for match in matches:
            try:
                tool_data = json.loads(match.strip())
                tool_name = tool_data.get("tool")
                parameters = tool_data.get("parameters", {})
                if tool_name:
                    tool_calls.append((tool_name, parameters))
            except json.JSONDecodeError as e:
                console.print(f"[red]Failed to parse tool call: {e}[/red]")
                continue

        # Fallback parser: Look for standalone JSON objects that look like tool calls
        # This handles cases where the LLM forgot the markdown fence
        if not tool_calls:
            # Look for JSON objects with "tool" and "parameters" keys
            json_pattern = r'\{\s*"tool"\s*:\s*"([^"]+)"\s*,\s*"parameters"\s*:\s*\{[^}]*\}\s*\}'
            json_matches = re.findall(json_pattern, text, re.DOTALL)

            if json_matches:
                console.print(
                    "[yellow]⚠ Warning: Detected tool call without proper markdown fence. "
                    "Parsing anyway, but please use ```tool_call format.[/yellow]"
                )

                # Try to extract the full JSON objects
                # More lenient pattern to capture the whole object
                full_json_pattern = r'(\{\s*"tool"\s*:\s*"[^"]+"\s*,\s*"parameters"\s*:\s*\{.*?\}\s*\})'
                for match in re.finditer(full_json_pattern, text, re.DOTALL):
                    try:
                        tool_data = json.loads(match.group(1))
                        tool_name = tool_data.get("tool")
                        parameters = tool_data.get("parameters", {})
                        if tool_name:
                            tool_calls.append((tool_name, parameters))
                    except json.JSONDecodeError:
                        continue

        return tool_calls

    def display_streaming_response(self, chunks: list) -> str:
        """
        Display streaming response and return full text.

        Args:
            chunks: List of text chunks

        Returns:
            Full response text
        """
        full_text = "".join(chunks)

        # Split response around tool calls for better display
        parts = re.split(r"(```tool_call.*?```)", full_text, flags=re.DOTALL)

        for part in parts:
            if part.startswith("```tool_call"):
                # Display tool call in a panel
                console.print(
                    Panel(part, title="Tool Call", border_style="cyan")
                )
            elif part.strip():
                # Display regular text as markdown
                console.print(Markdown(part))

        return full_text

    def run_conversation_turn(self, user_message: str) -> None:
        """
        Run one turn of the conversation with optimized execution strategy.

        Args:
            user_message: User's message
        """
        # Add user message to conversation
        self.messages.append({"role": "user", "content": user_message})

        try:
            # Step 1: Classify task (if enabled)
            classification = None
            if self.config.get("enable_task_classification", True):
                classification = self.classifier.classify(
                    user_message, self.messages
                )

                # Step 2: Get execution strategy based on classification
                exec_config = ExecutionStrategy.get_execution_config(
                    classification,
                    self.provider.provider_name,
                    self.provider.model_name,
                )

                console.print(
                    f"[dim]→ Execution mode: {exec_config.mode} "
                    f"(model: {exec_config.model_tier}, "
                    f"max_iter: {exec_config.max_iterations})[/dim]"
                )

                # Step 3: Switch model if needed (and provider supports it)
                current_model = self.provider.model_name
                target_model = exec_config.hyperparameters.get("model")

                if target_model and target_model != current_model:
                    try:
                        self.provider.set_model(target_model)
                        console.print(
                            f"[dim]→ Switched model: {current_model} → {target_model}[/dim]"
                        )
                    except Exception:
                        # Provider doesn't support model switching, continue with current
                        pass

            else:
                # Classification disabled, use default complex config
                exec_config = ExecutionStrategy.get_execution_config(
                    None,  # Will trigger fallback
                    self.provider.provider_name,
                    self.provider.model_name,
                )

            # Step 4: Execute based on mode
            if exec_config.mode == "conversational":
                # Conversational mode: single-turn response, no tools
                self._run_conversational_turn(exec_config)

            else:
                # Agentic modes: use agent loop
                self._run_agentic_turn(
                    classification, exec_config, user_message
                )

        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted[/yellow]")
        except Exception as e:
            import traceback

            console.print(f"\n[red]Error: {e}[/red]")
            console.print(f"[dim]{traceback.format_exc()}[/dim]")

    def _run_conversational_turn(self, exec_config):
        """
        Handle conversational turn (no tools, single response).

        Args:
            exec_config: Execution configuration
        """
        console.print("[bold cyan]Assistant:[/bold cyan]")
        chunks = []

        # Pass hyperparameters to provider
        stream_options = exec_config.hyperparameters.copy()

        for chunk in self.provider.generate_streaming(
            self.messages, stream_options=stream_options
        ):
            console.print(chunk, end="")
            chunks.append(chunk)

        console.print("\n")

        # Add response to conversation
        response_text = "".join(chunks)
        self.messages.append({"role": "assistant", "content": response_text})

    def _run_agentic_turn(self, classification, exec_config, user_message):
        """
        Handle agentic turn (with tools and iterations).

        Args:
            classification: Task classification
            exec_config: Execution configuration
            user_message: Original user message
        """
        # Check if planning phase should be offered
        if (
            exec_config.use_planning
            and classification
            and classification.complexity == "COMPLEX"
            and self.config.get("enable_planning_phase", True)
        ):
            response = Prompt.ask(
                "[bold yellow]This looks complex. Create a plan first?[/bold yellow]",
                choices=["yes", "no"],
                default="yes",
            )

            if response == "yes":
                # Execute planning phase
                plan = self.planning_phase.execute_planning(
                    user_message, self.messages
                )

                # Get user approval
                approval = self.planning_phase.get_user_approval(plan)

                if not approval.get("approved", False):
                    console.print("[yellow]Task cancelled by user[/yellow]")
                    return

                # If modifications requested, add them to conversation
                if "modifications" in approval:
                    self.messages.append(
                        {
                            "role": "user",
                            "content": f"Plan modifications: {approval['modifications']}",
                        }
                    )

        # Update agent loop max iterations for this turn
        original_max_iterations = self.agent_loop.max_iterations
        self.agent_loop.max_iterations = exec_config.max_iterations

        # Run agent loop with hyperparameters
        self.agent_loop.stream_options = exec_config.hyperparameters

        result = self.agent_loop.run(
            messages=self.messages,
            tool_parser=self.parse_tool_calls,
            display_callback=None,
        )

        # Restore original max iterations
        self.agent_loop.max_iterations = original_max_iterations

        # Display result summary
        if result["success"]:
            console.print(
                f"\n[dim]Completed in {result['iterations']} iteration(s) "
                f"with {result['tool_calls']} tool call(s)[/dim]"
            )
        else:
            console.print(f"\n[red]Error: {result.get('error')}[/red]")

    def run(self):
        """Run the interactive CLI."""
        console.print(
            Panel.fit(
                "[bold cyan]Kubrick CLI[/bold cyan]\n"
                f"Working directory: {self.tool_executor.working_dir}\n"
                f"Conversation ID: {self.conversation_id}\n"
                "Type your questions or commands. Use 'exit' or 'quit' to exit.\n"
                "Type '/help' to see available commands.",
                border_style="cyan",
            )
        )

        # Check provider health
        if not self.provider.is_healthy():
            console.print(
                f"[red]Warning: Cannot connect to {self.provider.provider_name} provider[/red]"
            )
            console.print(
                "[yellow]Please check your provider configuration and connectivity.[/yellow]"
            )

        while True:
            try:
                user_input = Prompt.ask("\n[bold green]You[/bold green]")

                # Reset interrupt count when user enters a message
                self.interrupt_count = 0

                if not user_input.strip():
                    continue

                if user_input.lower() in ["exit", "quit", "q"]:
                    # Save conversation before exiting
                    self._save_conversation()
                    console.print(
                        f"[cyan]Conversation saved as {self.conversation_id}[/cyan]"
                    )
                    console.print("[cyan]Goodbye![/cyan]")
                    break

                # Handle special commands
                if user_input.startswith("/"):
                    self._handle_command(user_input)
                    continue

                self.run_conversation_turn(user_input)

                # Auto-save after each turn
                self._save_conversation()

            except KeyboardInterrupt:
                self.interrupt_count += 1

                if self.interrupt_count == 1:
                    # First Ctrl+C: Clear prompt
                    console.print("\n[yellow]^C (Press again to start new conversation, once more to exit)[/yellow]")
                    continue

                elif self.interrupt_count == 2:
                    # Second Ctrl+C: Start new conversation
                    console.print("\n[yellow]Starting new conversation...[/yellow]")
                    self._save_conversation()

                    # Reset conversation
                    self.conversation_id = datetime.now().strftime("%Y%m%d_%H%M%S")
                    self.messages = self._get_initial_messages()

                    console.print(f"[cyan]New conversation ID: {self.conversation_id}[/cyan]")
                    console.print("[dim]Press Ctrl+C once more to exit[/dim]")
                    continue

                else:
                    # Third Ctrl+C: Exit
                    self._save_conversation()
                    console.print(
                        f"\n[cyan]Conversation saved as {self.conversation_id}[/cyan]"
                    )
                    console.print("[cyan]Goodbye![/cyan]")
                    break

            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

    def _handle_command(self, command: str):
        """Handle special CLI commands."""
        parts = command.strip().split()
        cmd = parts[0].lower()

        if cmd == "/save":
            self._save_conversation()
            console.print(
                f"[green]Conversation saved as {self.conversation_id}[/green]"
            )

        elif cmd == "/list":
            limit = int(parts[1]) if len(parts) > 1 else 20
            conversations = self.config.list_conversations(limit=limit)

            if not conversations:
                console.print("[yellow]No saved conversations found[/yellow]")
                return

            table = Table(title="Saved Conversations")
            table.add_column("ID", style="cyan")
            table.add_column("Messages", justify="right", style="green")
            table.add_column("Working Dir", style="dim")
            table.add_column("Modified", style="yellow")

            for conv in conversations:
                conv_id = conv["id"]
                msg_count = str(conv["message_count"])
                working_dir = conv["metadata"].get("working_dir", "N/A")
                modified = datetime.fromtimestamp(conv["modified"]).strftime(
                    "%Y-%m-%d %H:%M"
                )

                table.add_row(conv_id, msg_count, working_dir, modified)

            console.print(table)

        elif cmd == "/config":
            if len(parts) == 1:
                # Show current config
                config_data = self.config.get_all()
                table = Table(title="Current Configuration")
                table.add_column("Setting", style="cyan")
                table.add_column("Value", style="green")

                for key, value in config_data.items():
                    table.add_row(key, str(value))

                console.print(table)

            elif len(parts) == 3:
                # Set config value
                key = parts[1]
                value = parts[2]

                # Try to parse as JSON for booleans/numbers
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    pass  # Keep as string

                self.config.set(key, value)
                console.print(f"[green]Set {key} = {value}[/green]")

            else:
                console.print("[yellow]Usage: /config [key value][/yellow]")

        elif cmd == "/delete":
            if len(parts) < 2:
                console.print(
                    "[yellow]Usage: /delete <conversation_id>[/yellow]"
                )
                return

            conv_id = parts[1]
            if self.config.delete_conversation(conv_id):
                console.print(f"[green]Deleted conversation {conv_id}[/green]")
            else:
                console.print(
                    f"[yellow]Conversation {conv_id} not found[/yellow]"
                )

        elif cmd == "/debug":
            # Show debug information
            table = Table(title="Debug Information")
            table.add_column("Item", style="cyan")
            table.add_column("Value", style="green")

            table.add_row("Conversation ID", self.conversation_id)
            table.add_row("Messages Count", str(len(self.messages)))
            table.add_row("Working Dir", str(self.tool_executor.working_dir))
            table.add_row("Provider", self.provider.provider_name)
            table.add_row("Model Name", self.provider.model_name)

            console.print(table)

            # Show system prompt
            if len(parts) > 1 and parts[1] == "prompt":
                console.print("\n[bold cyan]System Prompt:[/bold cyan]")
                system_msg = next(
                    (m for m in self.messages if m["role"] == "system"), None
                )
                if system_msg:
                    console.print(
                        Panel(system_msg["content"], border_style="dim")
                    )
                else:
                    console.print("[yellow]No system message found[/yellow]")

        elif cmd == "/help":
            console.print("""
[bold cyan]Available Commands:[/bold cyan]

[green]/save[/green]              - Save the current conversation
[green]/list [N][/green]          - List saved conversations (default: 20)
[green]/config[/green]            - Show current configuration
[green]/config KEY VALUE[/green]  - Set a configuration value
[green]/delete ID[/green]         - Delete a conversation
[green]/debug[/green]             - Show debug information
[green]/debug prompt[/green]      - Show the system prompt
[green]/help[/green]              - Show this help message
            """)

        else:
            console.print(f"[yellow]Unknown command: {cmd}[/yellow]")
            console.print(
                "[dim]Available commands: /save, /list, /config, /delete, /debug, /help[/dim]"
            )


def main():
    """Main entry point."""
    # Initialize config (creates ~/.kubrick if needed, runs setup wizard on first run)
    config = KubrickConfig()

    parser = argparse.ArgumentParser(
        description="Kubrick - AI-assisted coding CLI with agentic capabilities",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Special Commands:
  /save              Save the current conversation
  /list [N]          List saved conversations (default: 20)
  /config            Show current configuration
  /config KEY VALUE  Set a configuration value
  /delete ID         Delete a conversation

Examples:
  kubrick                           # Start new conversation with configured provider
  kubrick --load 20240118_143022    # Load a previous conversation
  kubrick --working-dir /path/to/project  # Set working directory
  kubrick --provider openai         # Override provider for this session
        """,
    )

    parser.add_argument(
        "--working-dir",
        default=None,
        help="Working directory for file operations (default: current directory)",
    )

    parser.add_argument(
        "--load",
        "--load-conversation",
        dest="conversation_id",
        default=None,
        help="Load a previous conversation by ID",
    )

    parser.add_argument(
        "--provider",
        default=None,
        choices=["triton", "openai", "anthropic"],
        help="Override configured provider for this session",
    )

    args = parser.parse_args()

    # Create and run CLI
    try:
        cli = KubrickCLI(
            config=config,
            working_dir=args.working_dir,
            conversation_id=args.conversation_id,
            provider_override=args.provider,
        )

        cli.run()
    except Exception as e:
        console.print(f"[red]Failed to start Kubrick: {e}[/red]")
        import sys
        sys.exit(1)


if __name__ == "__main__":
    main()
