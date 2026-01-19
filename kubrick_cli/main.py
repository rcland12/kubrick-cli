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
from .planning import PlanningPhase
from .safety import SafetyConfig, SafetyManager
from .scheduler import ToolScheduler
from .tools import TOOL_DEFINITIONS, ToolExecutor, get_tools_prompt
from .triton_client import TritonLLMClient

console = Console()


class KubrickCLI:
    """Main CLI application."""

    def __init__(
        self,
        config: KubrickConfig,
        triton_url: str = None,
        model_name: str = None,
        working_dir: str = None,
        use_openai: bool = None,
        conversation_id: str = None,
    ):
        """
        Initialize Kubrick CLI.

        Args:
            config: KubrickConfig instance
            triton_url: Triton server HTTP URL (overrides config)
            model_name: Triton model name (overrides config)
            working_dir: Working directory for file operations (overrides config)
            use_openai: Whether to route requests to OpenAI (overrides config)
            conversation_id: Load existing conversation by ID
        """
        self.config = config

        # Use provided values or fall back to config
        triton_url = triton_url or config.get("triton_url", "localhost:8000")
        model_name = model_name or config.get("model_name", "llm_decoupled")
        self.use_openai = (
            use_openai
            if use_openai is not None
            else config.get("use_openai", False)
        )

        self.client = TritonLLMClient(url=triton_url, model_name=model_name)

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

        stream_options = {}
        if self.use_openai:
            stream_options["use_openai"] = True

        self.agent_loop = AgentLoop(
            llm_client=self.client,
            tool_executor=self.tool_executor,
            max_iterations=max_iterations,
            max_tools_per_turn=max_tools_per_turn,
            timeout_seconds=timeout_seconds,
            stream_options=stream_options,
            display_manager=self.display_manager,
            tool_scheduler=self.tool_scheduler,
        )

        # Initialize task classifier and planning phase
        self.classifier = TaskClassifier(self.client)
        self.planning_phase = PlanningPhase(
            llm_client=self.client,
            tool_executor=self.tool_executor,
            agent_loop=self.agent_loop,
        )

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

# Important Rules

1. **ITERATE**: Call tools immediately when needed, then analyze results and continue iterating
2. **MULTIPLE TOOLS**: You can call multiple tools per response
3. **READ BEFORE EDIT**: Always read a file before editing it
4. **SIGNAL COMPLETION**: Say "TASK_COMPLETE" when the task is done
5. **USE TOOLS IMMEDIATELY**: Don't ask permission - just call the tool

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
                "triton_url": self.client.url,
                "model_name": self.client.model_name,
                "use_openai": self.use_openai,
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
        Run one turn of the conversation using the agentic loop.

        Args:
            user_message: User's message
        """
        # Add user message to conversation
        self.messages.append({"role": "user", "content": user_message})

        try:
            # Step 1: Classify task complexity (if enabled)
            complexity = "SIMPLE"
            if self.config.get("enable_task_classification", True):
                complexity = self.classifier.classify(
                    user_message, self.messages
                )

            # Step 2: If COMPLEX and planning enabled, ask about planning
            if (
                complexity == "COMPLEX"
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
                        console.print(
                            "[yellow]Task cancelled by user[/yellow]"
                        )
                        return

                    # If modifications requested, add them to conversation
                    if "modifications" in approval:
                        self.messages.append(
                            {
                                "role": "user",
                                "content": f"Plan modifications: {approval['modifications']}",
                            }
                        )

            # Step 3: Run the agentic loop
            result = self.agent_loop.run(
                messages=self.messages,
                tool_parser=self.parse_tool_calls,
                display_callback=None,  # We'll handle display in agent_loop
            )

            # Display result summary
            if result["success"]:
                console.print(
                    f"\n[dim]Completed in {result['iterations']} iteration(s) "
                    f"with {result['tool_calls']} tool call(s)[/dim]"
                )
            else:
                console.print(f"\n[red]Error: {result.get('error')}[/red]")

        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted[/yellow]")
        except Exception as e:
            import traceback

            console.print(f"\n[red]Error: {e}[/red]")
            console.print(f"[dim]{traceback.format_exc()}[/dim]")

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

        # Show Docker mode notice
        if os.environ.get("KUBRICK_IN_DOCKER"):
            console.print(
                "[yellow]ℹ️  Running in Docker mode[/yellow]\n"
                "[dim]→ Files are accessible only within /workspace (mounted from your current directory)[/dim]\n"
                "[dim]→ Config is saved to ~/.kubrick (mounted volume)[/dim]"
            )

        # Check Triton server health
        if not self.client.is_healthy():
            console.print(
                f"[red]Warning: Cannot connect to Triton server at {self.client.url}[/red]"
            )
            console.print(
                "[yellow]Make sure the Triton server is running.[/yellow]"
            )

        while True:
            try:
                user_input = Prompt.ask("\n[bold green]You[/bold green]")

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
                # Save conversation before exiting
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
            table.add_row("Triton URL", self.client.url)
            table.add_row("Model Name", self.client.model_name)
            table.add_row("Use OpenAI", str(self.use_openai))

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
    # Initialize config (creates ~/.kubrick if needed)
    config = KubrickConfig()

    parser = argparse.ArgumentParser(
        description="Kubrick - AI-assisted coding CLI with conversation persistence",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Special Commands:
  /save              Save the current conversation
  /list [N]          List saved conversations (default: 20)
  /config            Show current configuration
  /config KEY VALUE  Set a configuration value
  /delete ID         Delete a conversation

Examples:
  kubrick                           # Start new conversation with defaults
  kubrick --load 20240118_143022    # Load a previous conversation
  kubrick --triton-url myserver:8000 # Use custom Triton server
  kubrick --use-openai              # Use OpenAI instead of local LLM
        """,
    )

    parser.add_argument(
        "--triton-url",
        default=os.environ.get("TRITON_URL", None),
        help=f"Triton server HTTP URL (default from config: {config.get('triton_url')})",
    )

    parser.add_argument(
        "--model-name",
        default=os.environ.get("TRITON_MODEL_NAME", None),
        help=f"Triton model name (default from config: {config.get('model_name')})",
    )

    parser.add_argument(
        "--working-dir",
        default=None,
        help="Working directory for file operations (default: current directory)",
    )

    parser.add_argument(
        "--use-openai",
        action="store_true",
        default=None,
        help="Route requests to OpenAI API instead of local vLLM",
    )

    parser.add_argument(
        "--load",
        "--load-conversation",
        dest="conversation_id",
        default=None,
        help="Load a previous conversation by ID",
    )

    args = parser.parse_args()

    # Create and run CLI
    cli = KubrickCLI(
        config=config,
        triton_url=args.triton_url,
        model_name=args.model_name,
        working_dir=args.working_dir,
        use_openai=args.use_openai if args.use_openai else None,
        conversation_id=args.conversation_id,
    )

    cli.run()


if __name__ == "__main__":
    main()
