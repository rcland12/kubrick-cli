"""Planning phase for complex tasks with read-only exploration."""

from typing import Dict, List

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

console = Console()


# Read-only tools allowed in planning mode
PLANNING_ALLOWED_TOOLS = {
    "read_file",
    "list_files",
    "search_files",
    # run_bash is allowed but will be restricted to read-only commands
}

# Dangerous bash commands that are never allowed in planning
DANGEROUS_BASH_PATTERNS = [
    "rm ",
    "mv ",
    "cp ",
    "chmod",
    "chown",
    "sudo",
    "> ",
    ">>",
    "|",
    "git push",
    "git commit",
]


class PlanningPhase:
    """
    Handles the planning phase for complex tasks.

    In planning mode:
    - Agent can only use read-only tools
    - Agent explores the codebase to understand structure
    - Agent creates an implementation plan
    - User approves/modifies/rejects the plan
    - After approval, execution proceeds with full tools
    """

    def __init__(self, llm_client, tool_executor, agent_loop):
        """
        Initialize planning phase.

        Args:
            llm_client: LLM client instance
            tool_executor: Tool executor instance
            agent_loop: Agent loop instance for execution
        """
        self.llm_client = llm_client
        self.tool_executor = tool_executor
        self.agent_loop = agent_loop

    def execute_planning(
        self, user_message: str, base_messages: List[Dict]
    ) -> str:
        """
        Execute the planning phase.

        Args:
            user_message: The user's original request
            base_messages: Base conversation messages

        Returns:
            The generated plan text
        """
        console.print(
            "\n[bold yellow]→ Entering PLANNING MODE[/bold yellow]"
        )
        console.print(
            "[dim]Agent will explore the codebase with read-only tools and create a plan.[/dim]\n"
        )

        # Create planning messages with restricted system prompt
        planning_messages = base_messages.copy()

        # Add planning-specific system message
        planning_messages.append(
            {
                "role": "system",
                "content": """# PLANNING MODE

You are now in PLANNING MODE. Your task is to:
1. EXPLORE the codebase using read-only tools
2. DESIGN an implementation approach
3. CREATE a detailed plan

# Available Tools (READ-ONLY)

You can ONLY use these tools:
- read_file: Read file contents
- list_files: List files matching patterns (supports recursive patterns like "**/*.py")
- search_files: Search for text in files
- run_bash: Run ONLY read-only commands (ls, find, cat, grep, tree, etc.)

You CANNOT use:
- write_file
- edit_file
- create_directory
- Any destructive bash commands

# How to Explore the Codebase

**IMPORTANT**: To get a complete understanding, you MUST explore systematically:

1. **Start with directory structure**:
   - Use `list_files` with pattern `**/*` to see ALL files and directories recursively
   - Or use `run_bash` with command `find . -type f` to list all files
   - Or use `run_bash` with command `tree` or `ls -R` to see the full structure

2. **List files by type**:
   - Python: `list_files` with pattern `**/*.py`
   - JavaScript: `list_files` with pattern `**/*.js`
   - All code files: Try multiple patterns to cover all file types

3. **Read key files**:
   - README files
   - Configuration files (package.json, requirements.txt, pyproject.toml, etc.)
   - Main entry points
   - Important modules based on the task

4. **Search for specific patterns**:
   - Use `search_files` to find classes, functions, imports, etc.

**Example exploration workflow**:
```tool_call
{
  "tool": "list_files",
  "parameters": {
    "pattern": "**/*"
  }
}
```

Then read relevant files:
```tool_call
{
  "tool": "read_file",
  "parameters": {
    "file_path": "path/to/important/file.py"
  }
}
```

# Plan Format

When ready, create a plan in this format:

## Implementation Plan

### Overview
[Brief description of what you'll do]

### Steps
1. [First step]
2. [Second step]
3. [etc.]

### Files to Modify
- file1.py: [what changes]
- file2.py: [what changes]

### Risks
- [Potential issues or concerns]

# Completion

Say "PLAN_COMPLETE" when your plan is ready.""",
            }
        )

        # Add user's original request
        planning_messages.append(
            {
                "role": "user",
                "content": f"Task: {user_message}\n\nPlease explore the codebase and create an implementation plan.",
            }
        )

        # Run agent loop with read-only tool executor
        original_executor = self.agent_loop.tool_executor
        restricted_executor = RestrictedToolExecutor(
            self.tool_executor, PLANNING_ALLOWED_TOOLS
        )
        self.agent_loop.tool_executor = restricted_executor

        try:
            # Run planning loop (max 10 iterations)
            old_max = self.agent_loop.max_iterations
            self.agent_loop.max_iterations = 10

            # Create tool parser
            from .main import KubrickCLI

            temp_cli = KubrickCLI.__new__(KubrickCLI)
            tool_parser = temp_cli.parse_tool_calls

            result = self.agent_loop.run(
                messages=planning_messages,
                tool_parser=tool_parser,
                display_callback=None,
            )

            self.agent_loop.max_iterations = old_max

            # Extract the plan from the last assistant message
            plan_text = ""
            for msg in reversed(planning_messages):
                if msg["role"] == "assistant":
                    plan_text = msg["content"]
                    break

            return plan_text

        finally:
            # Restore original executor
            self.agent_loop.tool_executor = original_executor

    def get_user_approval(self, plan: str) -> Dict:
        """
        Present plan to user and get approval.

        Args:
            plan: The generated plan text

        Returns:
            Dict with 'approved' (bool) and optional 'modifications' (str)
        """
        # Display plan
        console.print("\n" + "=" * 70)
        console.print(
            Panel(
                Markdown(plan),
                title="[bold cyan]Implementation Plan[/bold cyan]",
                border_style="cyan",
            )
        )
        console.print("=" * 70 + "\n")

        # Get user decision
        choice = Prompt.ask(
            "[bold yellow]Approve this plan?[/bold yellow]",
            choices=["approve", "modify", "reject"],
            default="approve",
        )

        if choice == "approve":
            console.print("[green]✓ Plan approved, proceeding with implementation[/green]")
            return {"approved": True}

        elif choice == "modify":
            modifications = Prompt.ask(
                "[yellow]What modifications would you like?[/yellow]"
            )
            console.print("[yellow]Plan modifications noted, will adjust[/yellow]")
            return {"approved": True, "modifications": modifications}

        else:  # reject
            console.print("[red]Plan rejected, cancelling task[/red]")
            return {"approved": False}


class RestrictedToolExecutor:
    """
    Wraps ToolExecutor to restrict to read-only tools during planning.
    """

    def __init__(self, base_executor, allowed_tools: set):
        """
        Initialize restricted executor.

        Args:
            base_executor: Base ToolExecutor instance
            allowed_tools: Set of allowed tool names
        """
        self.base_executor = base_executor
        self.allowed_tools = allowed_tools

    def execute(self, tool_name: str, parameters: Dict) -> Dict:
        """
        Execute tool with restrictions.

        Args:
            tool_name: Name of tool to execute
            parameters: Tool parameters

        Returns:
            Result dict
        """
        # Check if tool is allowed
        if tool_name not in self.allowed_tools:
            return {
                "success": False,
                "error": f"Tool '{tool_name}' is not allowed in planning mode (read-only)",
            }

        # Special handling for run_bash - check for dangerous commands
        if tool_name == "run_bash":
            command = parameters.get("command", "")
            if self._is_dangerous_command(command):
                return {
                    "success": False,
                    "error": f"Bash command '{command}' is not allowed in planning mode (read-only)",
                }

        # Execute allowed tool
        return self.base_executor.execute(tool_name, parameters)

    def _is_dangerous_command(self, command: str) -> bool:
        """Check if bash command is dangerous."""
        command_lower = command.lower()
        for pattern in DANGEROUS_BASH_PATTERNS:
            if pattern in command_lower:
                return True
        return False

    @property
    def working_dir(self):
        """Pass through working_dir property."""
        return self.base_executor.working_dir
