"""Parallel tool execution scheduler for improved performance."""

import concurrent.futures
from typing import Dict, List, Tuple

from rich.console import Console

console = Console()


# Read-only tools that can be executed in parallel
READ_ONLY_TOOLS = {
    "read_file",
    "list_files",
    "search_files",
}

# Write tools that must be executed sequentially
WRITE_TOOLS = {
    "write_file",
    "edit_file",
    "create_directory",
    "run_bash",
}


class ToolScheduler:
    """
    Schedules and executes tools with intelligent parallelization.

    Strategy: Conservative parallelization
    - Read-only tools (read_file, list_files, search_files) run in parallel
    - Write tools (write_file, edit_file, run_bash, etc.) run sequentially
    - Graceful error handling per tool
    """

    def __init__(
        self, tool_executor, max_workers: int = 3, enable_parallel: bool = True
    ):
        """
        Initialize tool scheduler.

        Args:
            tool_executor: ToolExecutor instance
            max_workers: Maximum parallel workers (default: 3)
            enable_parallel: Whether to enable parallel execution
        """
        self.tool_executor = tool_executor
        self.max_workers = max_workers
        self.enable_parallel = enable_parallel

    def execute_tools(self, tool_calls: List[Tuple[str, Dict]]) -> List[Dict]:
        """
        Execute a list of tool calls with intelligent scheduling.

        Args:
            tool_calls: List of (tool_name, parameters) tuples

        Returns:
            List of result dictionaries in the same order as input
        """
        if not self.enable_parallel or len(tool_calls) <= 1:
            return self._execute_sequential(tool_calls)

        read_only_calls = []
        write_calls = []
        call_order = []

        for i, (tool_name, params) in enumerate(tool_calls):
            if tool_name in READ_ONLY_TOOLS:
                read_only_calls.append((i, tool_name, params))
                call_order.append(("read", len(read_only_calls) - 1))
            else:
                write_calls.append((i, tool_name, params))
                call_order.append(("write", len(write_calls) - 1))

        read_results = {}
        if read_only_calls:
            console.print(
                f"[dim]→ Executing {len(read_only_calls)} read-only tool(s) in parallel[/dim]"
            )
            read_results = self._execute_parallel(read_only_calls)

        write_results = {}
        if write_calls:
            write_results = self._execute_sequential_indexed(write_calls)

        results = []
        for call_type, index in call_order:
            if call_type == "read":
                results.append(read_results[index])
            else:
                results.append(write_results[index])

        return results

    def _execute_parallel(
        self, indexed_calls: List[Tuple[int, str, Dict]]
    ) -> Dict[int, Dict]:
        """
        Execute tools in parallel using ThreadPoolExecutor.

        Args:
            indexed_calls: List of (index, tool_name, parameters) tuples

        Returns:
            Dict mapping index to result
        """
        results = {}

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.max_workers
        ) as executor:
            future_to_index = {}
            for index, tool_name, params in indexed_calls:
                future = executor.submit(self._execute_single, tool_name, params)
                future_to_index[future] = index

            for future in concurrent.futures.as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    result = future.result()
                    results[index] = result
                except Exception as e:
                    results[index] = {
                        "success": False,
                        "error": f"Parallel execution error: {str(e)}",
                    }

        return results

    def _execute_sequential(self, tool_calls: List[Tuple[str, Dict]]) -> List[Dict]:
        """
        Execute tools sequentially.

        Args:
            tool_calls: List of (tool_name, parameters) tuples

        Returns:
            List of result dictionaries
        """
        results = []
        for tool_name, params in tool_calls:
            result = self._execute_single(tool_name, params)
            results.append(result)
        return results

    def _execute_sequential_indexed(
        self, indexed_calls: List[Tuple[int, str, Dict]]
    ) -> Dict[int, Dict]:
        """
        Execute tools sequentially with index mapping.

        Args:
            indexed_calls: List of (index, tool_name, parameters) tuples

        Returns:
            Dict mapping index to result
        """
        results = {}
        for index, tool_name, params in indexed_calls:
            result = self._execute_single(tool_name, params)
            results[index] = result
        return results

    def _execute_single(self, tool_name: str, params: Dict) -> Dict:
        """
        Execute a single tool.

        Args:
            tool_name: Name of tool
            params: Tool parameters

        Returns:
            Result dictionary
        """
        try:
            return self.tool_executor.execute(tool_name, params)
        except Exception as e:
            return {
                "success": False,
                "error": f"Tool execution error: {str(e)}",
            }
