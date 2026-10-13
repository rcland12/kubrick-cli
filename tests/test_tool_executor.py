"""Unit tests for ToolExecutor."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kubrick_cli.tools import ToolExecutor


class TestToolExecutor:
    """Test suite for ToolExecutor class."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def executor(self, temp_dir):
        """Create a ToolExecutor instance for testing."""
        return ToolExecutor(working_dir=str(temp_dir))

    def test_read_file_success(self, executor, temp_dir):
        """Test reading a file successfully."""
        test_file = temp_dir / "test.txt"
        test_content = "Hello, World!"
        test_file.write_text(test_content)

        result = executor.execute("read_file", {"file_path": "test.txt"})

        assert result["success"] is True
        assert test_content in result["result"]

    def test_read_file_not_found(self, executor):
        """Test reading a non-existent file."""
        result = executor.execute("read_file", {"file_path": "nonexistent.txt"})

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_write_file_success(self, executor, temp_dir):
        """Test writing a file successfully."""
        content = "Test content\nLine 2"
        result = executor.execute(
            "write_file", {"file_path": "output.txt", "content": content}
        )

        assert result["success"] is True

        output_file = temp_dir / "output.txt"
        assert output_file.exists()
        assert output_file.read_text() == content

    def test_write_file_creates_parent_dirs(self, executor, temp_dir):
        """Test that write_file creates parent directories."""
        result = executor.execute(
            "write_file",
            {"file_path": "subdir/nested/file.txt", "content": "test"},
        )

        assert result["success"] is True

        nested_file = temp_dir / "subdir" / "nested" / "file.txt"
        assert nested_file.exists()

    def test_edit_file_success(self, executor, temp_dir):
        """Test editing a file successfully."""
        test_file = temp_dir / "edit.txt"
        original_content = "Hello World\nGoodbye World"
        test_file.write_text(original_content)

        result = executor.execute(
            "edit_file",
            {
                "file_path": "edit.txt",
                "old_string": "Hello World",
                "new_string": "Hi Universe",
            },
        )

        assert result["success"] is True

        new_content = test_file.read_text()
        assert "Hi Universe" in new_content
        assert "Hello World" not in new_content
        assert "Goodbye World" in new_content

    def test_edit_file_string_not_found(self, executor, temp_dir):
        """Test editing when string is not found."""
        test_file = temp_dir / "edit.txt"
        test_file.write_text("Original content")

        result = executor.execute(
            "edit_file",
            {
                "file_path": "edit.txt",
                "old_string": "Nonexistent string",
                "new_string": "Replacement",
            },
        )

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_list_files_success(self, executor, temp_dir):
        """Test listing files with glob pattern."""
        (temp_dir / "test1.py").write_text("# test1")
        (temp_dir / "test2.py").write_text("# test2")
        (temp_dir / "test.txt").write_text("text")

        result = executor.execute("list_files", {"pattern": "*.py"})

        assert result["success"] is True
        assert "test1.py" in result["result"]
        assert "test2.py" in result["result"]
        assert "test.txt" not in result["result"]

    def test_list_files_no_matches(self, executor, temp_dir):
        """Test listing files when no matches found."""
        result = executor.execute("list_files", {"pattern": "*.xyz"})

        assert result["success"] is True
        assert "No files" in result["result"]

    def test_list_files_with_directories(self, executor, temp_dir):
        """Test listing files and directories."""
        (temp_dir / "file.txt").write_text("content")
        (temp_dir / "subdir").mkdir()

        result = executor.execute("list_files", {"pattern": "*"})

        assert result["success"] is True
        assert "file.txt" in result["result"]
        assert "subdir/" in result["result"]

    def test_search_files_success(self, executor, temp_dir):
        """Test searching for text in files."""
        (temp_dir / "file1.txt").write_text("Hello World\nFoo Bar")
        (temp_dir / "file2.txt").write_text("Goodbye World\nBaz Qux")

        result = executor.execute("search_files", {"pattern": "World"})

        assert result["success"] is True
        assert "file1.txt" in result["result"]
        assert "file2.txt" in result["result"]

    def test_search_files_with_file_pattern(self, executor, temp_dir):
        """Test searching with file pattern filter."""
        (temp_dir / "test.py").write_text("import os")
        (temp_dir / "test.txt").write_text("import os")

        result = executor.execute(
            "search_files", {"pattern": "import", "file_pattern": "*.py"}
        )

        assert result["success"] is True
        assert "test.py" in result["result"]

    def test_search_files_no_matches(self, executor, temp_dir):
        """Test searching when no matches found."""
        (temp_dir / "file.txt").write_text("No match here")

        result = executor.execute("search_files", {"pattern": "NonexistentPattern"})

        assert result["success"] is True
        assert "No matches" in result["result"]

    @patch("subprocess.run")
    def test_run_bash_success(self, mock_run, executor):
        """Test running bash command successfully."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="command output", stderr=""
        )

        result = executor.execute("run_bash", {"command": "echo hello"})

        assert result["success"] is True
        assert "command output" in result["result"]
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_run_bash_with_stderr(self, mock_run, executor):
        """Test bash command with stderr output."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="output", stderr="warning message"
        )

        result = executor.execute("run_bash", {"command": "ls"})

        assert result["success"] is True
        assert "output" in result["result"]
        assert "warning message" in result["result"]

    @patch("subprocess.run")
    def test_run_bash_timeout(self, mock_run, executor):
        """Test bash command timeout."""
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 30)

        result = executor.execute("run_bash", {"command": "sleep 100"})

        assert result["success"] is False
        assert "timed out" in result["error"].lower()

    def test_create_directory_success(self, executor, temp_dir):
        """Test creating a directory."""
        result = executor.execute("create_directory", {"path": "new_dir"})

        assert result["success"] is True
        assert (temp_dir / "new_dir").exists()
        assert (temp_dir / "new_dir").is_dir()

    def test_create_directory_nested(self, executor, temp_dir):
        """Test creating nested directories."""
        result = executor.execute(
            "create_directory", {"path": "parent/child/grandchild"}
        )

        assert result["success"] is True
        nested_dir = temp_dir / "parent" / "child" / "grandchild"
        assert nested_dir.exists()
        assert nested_dir.is_dir()

    def test_create_directory_already_exists(self, executor, temp_dir):
        """Test creating directory that already exists."""
        (temp_dir / "existing").mkdir()

        result = executor.execute("create_directory", {"path": "existing"})

        assert result["success"] is True

    def test_unknown_tool(self, executor):
        """Test executing an unknown tool."""
        result = executor.execute("nonexistent_tool", {})

        assert result["success"] is False
        assert "Unknown tool" in result["error"]

    def test_resolve_path_absolute(self, executor, temp_dir):
        """Test resolving absolute paths."""
        abs_path = temp_dir / "absolute.txt"
        abs_path.write_text("content")

        result = executor.execute("read_file", {"file_path": str(abs_path)})

        assert result["success"] is True

    def test_resolve_path_relative(self, executor, temp_dir):
        """Test resolving relative paths."""
        (temp_dir / "relative.txt").write_text("content")

        result = executor.execute("read_file", {"file_path": "relative.txt"})

        assert result["success"] is True

    def test_exception_handling(self, executor):
        """Test that exceptions are caught and returned as errors."""
        result = executor.execute("read_file", {})

        assert result["success"] is False
        assert "error" in result


class TestNewToolBehaviour:
    """Line numbers, unique edits, regex search, argument validation."""

    def test_read_numbers_lines_and_pages(self, temp_workspace):
        from kubrick_cli.tools import ToolExecutor

        (temp_workspace / "f.txt").write_text(
            "\n".join(f"line{i}" for i in range(1, 11))
        )
        ex = ToolExecutor(working_dir=str(temp_workspace))
        out = ex.execute("read_file", {"file_path": "f.txt", "offset": 3, "limit": 2})
        assert out["success"]
        assert "     3\tline3" in out["result"] and "line5" not in out["result"]
        assert "lines 3-4 of 10" in out["result"]

    def test_edit_requires_unique_match(self, temp_workspace):
        from kubrick_cli.tools import ToolExecutor

        (temp_workspace / "f.py").write_text("x = 1\nx = 1\n")
        ex = ToolExecutor(working_dir=str(temp_workspace))
        out = ex.execute(
            "edit_file",
            {"file_path": "f.py", "old_string": "x = 1", "new_string": "x = 2"},
        )
        assert not out["success"] and "2 places" in out["error"]
        out = ex.execute(
            "edit_file",
            {
                "file_path": "f.py",
                "old_string": "x = 1",
                "new_string": "x = 2",
                "replace_all": True,
            },
        )
        assert out["success"]
        assert (temp_workspace / "f.py").read_text() == "x = 2\nx = 2\n"

    def test_search_is_regex(self, temp_workspace):
        from kubrick_cli.tools import ToolExecutor

        (temp_workspace / "a.py").write_text("def foo():\n    pass\ndef bar():\n")
        ex = ToolExecutor(working_dir=str(temp_workspace))
        out = ex.execute(
            "search_files", {"pattern": r"def \w+\(", "file_pattern": "*.py"}
        )
        assert out["success"] and "2 match" in out["result"]
        assert not ex.execute("search_files", {"pattern": "("})["success"]

    def test_bash_reports_exit_code(self, temp_workspace):
        from kubrick_cli.tools import ToolExecutor

        ex = ToolExecutor(working_dir=str(temp_workspace))
        out = ex.execute("run_bash", {"command": "echo hi; exit 3"})
        assert (
            out["success"]
            and out["result"].startswith("Exit code: 3")
            and "hi" in out["result"]
        )

    def test_validation_coerces_and_rejects(self, temp_workspace):
        from kubrick_cli.tools import validate_arguments

        args = {"file_path": "a", "offset": "5"}
        assert validate_arguments("read_file", args) is None and args["offset"] == 5
        assert "must be of type string" in validate_arguments(
            "read_file", {"file_path": 3}
        )
        assert "Unknown tool" in validate_arguments("nope", {})
