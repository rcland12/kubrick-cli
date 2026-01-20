"""Unit tests for CompletionDetector."""

from kubrick_cli.agent_loop import CompletionDetector


class TestCompletionDetector:
    """Test suite for CompletionDetector class."""

    def test_explicit_marker_task_complete(self):
        """Test detection of TASK_COMPLETE marker."""
        response = "I've finished the task. TASK_COMPLETE"

        is_complete, reason = CompletionDetector.is_complete(
            response_text=response,
            has_tool_calls=False,
            iteration=1,
            max_iterations=10,
        )

        assert is_complete is True
        assert "TASK_COMPLETE" in reason

    def test_explicit_marker_plan_complete(self):
        """Test detection of PLAN_COMPLETE marker."""
        response = "The plan is ready. PLAN_COMPLETE"

        is_complete, reason = CompletionDetector.is_complete(
            response_text=response,
            has_tool_calls=False,
            iteration=1,
            max_iterations=10,
        )

        assert is_complete is True
        assert "PLAN_COMPLETE" in reason

    def test_explicit_marker_complete_brackets(self):
        """Test detection of [COMPLETE] marker."""
        response = "All done! [COMPLETE]"

        is_complete, reason = CompletionDetector.is_complete(
            response_text=response,
            has_tool_calls=False,
            iteration=1,
            max_iterations=10,
        )

        assert is_complete is True
        assert "COMPLETE" in reason

    def test_explicit_marker_done_brackets(self):
        """Test detection of [DONE] marker."""
        response = "Finished processing [DONE]"

        is_complete, reason = CompletionDetector.is_complete(
            response_text=response,
            has_tool_calls=False,
            iteration=1,
            max_iterations=10,
        )

        assert is_complete is True
        assert "DONE" in reason

    def test_max_iterations_reached(self):
        """Test completion when max iterations reached."""
        response = "Still working on it..."

        is_complete, reason = CompletionDetector.is_complete(
            response_text=response,
            has_tool_calls=True,
            iteration=10,
            max_iterations=10,
        )

        assert is_complete is True
        assert reason == "max_iterations_reached"

    def test_max_iterations_exceeded(self):
        """Test completion when iterations exceeded."""
        response = "Still working..."

        is_complete, reason = CompletionDetector.is_complete(
            response_text=response,
            has_tool_calls=True,
            iteration=15,
            max_iterations=10,
        )

        assert is_complete is True
        assert reason == "max_iterations_reached"

    def test_conclusive_response_done(self):
        """Test detection of conclusive response with 'done'."""
        response = "I'm done with the task. Everything looks good!"

        is_complete, reason = CompletionDetector.is_complete(
            response_text=response,
            has_tool_calls=False,
            iteration=3,
            max_iterations=10,
        )

        assert is_complete is True
        assert reason == "conclusive_response"

    def test_conclusive_response_completed(self):
        """Test detection of conclusive response with 'completed'."""
        response = "The task has been completed successfully."

        is_complete, reason = CompletionDetector.is_complete(
            response_text=response,
            has_tool_calls=False,
            iteration=2,
            max_iterations=10,
        )

        assert is_complete is True
        assert reason == "conclusive_response"

    def test_conclusive_response_finished(self):
        """Test detection of conclusive response with 'finished'."""
        response = "I've finished all the work you requested."

        is_complete, reason = CompletionDetector.is_complete(
            response_text=response,
            has_tool_calls=False,
            iteration=5,
            max_iterations=10,
        )

        assert is_complete is True
        assert reason == "conclusive_response"

    def test_conclusive_response_successfully(self):
        """Test detection of conclusive response with 'successfully'."""
        response = "Successfully completed all the updates."

        is_complete, reason = CompletionDetector.is_complete(
            response_text=response,
            has_tool_calls=False,
            iteration=4,
            max_iterations=10,
        )

        assert is_complete is True
        assert reason == "conclusive_response"

    def test_conclusive_response_here_is_summary(self):
        """Test detection of conclusive response with 'here is summary'."""
        response = "Here is the summary of changes made to the codebase."

        is_complete, reason = CompletionDetector.is_complete(
            response_text=response,
            has_tool_calls=False,
            iteration=3,
            max_iterations=10,
        )

        assert is_complete is True
        assert reason == "conclusive_response"

    def test_conclusive_response_let_me_know(self):
        """Test detection of conclusive response with 'let me know'."""
        response = "The changes are complete. Let me know if you need anything else."

        is_complete, reason = CompletionDetector.is_complete(
            response_text=response,
            has_tool_calls=False,
            iteration=2,
            max_iterations=10,
        )

        assert is_complete is True
        assert reason == "conclusive_response"

    def test_conclusive_response_thats_it(self):
        """Test detection of conclusive response with 'that's it'."""
        response = "That's it! The task is complete."

        is_complete, reason = CompletionDetector.is_complete(
            response_text=response,
            has_tool_calls=False,
            iteration=3,
            max_iterations=10,
        )

        assert is_complete is True
        assert reason == "conclusive_response"

    def test_conclusive_response_everything_set(self):
        """Test detection of conclusive response with 'everything set'."""
        response = "Everything is set and ready to go!"

        is_complete, reason = CompletionDetector.is_complete(
            response_text=response,
            has_tool_calls=False,
            iteration=2,
            max_iterations=10,
        )

        assert is_complete is True
        assert reason == "conclusive_response"

    def test_not_complete_with_tool_calls(self):
        """Test that task continues when there are tool calls."""
        response = "Let me read the file first."

        is_complete, reason = CompletionDetector.is_complete(
            response_text=response,
            has_tool_calls=True,
            iteration=3,
            max_iterations=10,
        )

        assert is_complete is False
        assert reason == "continuing"

    def test_not_complete_inconclusive_response(self):
        """Test that task continues with inconclusive response."""
        response = "I'll need to check the configuration next."

        is_complete, reason = CompletionDetector.is_complete(
            response_text=response,
            has_tool_calls=False,
            iteration=3,
            max_iterations=10,
        )

        assert is_complete is False
        assert reason == "continuing"

    def test_not_complete_work_in_progress(self):
        """Test that task continues with work-in-progress response."""
        response = "I'm currently analyzing the code structure."

        is_complete, reason = CompletionDetector.is_complete(
            response_text=response,
            has_tool_calls=False,
            iteration=2,
            max_iterations=10,
        )

        assert is_complete is False
        assert reason == "continuing"

    def test_explicit_marker_priority_over_tool_calls(self):
        """Test that explicit markers override tool call presence."""
        response = "Task is complete. TASK_COMPLETE"

        is_complete, reason = CompletionDetector.is_complete(
            response_text=response,
            has_tool_calls=True,
            iteration=1,
            max_iterations=10,
        )

        assert is_complete is True
        assert "TASK_COMPLETE" in reason

    def test_explicit_marker_priority_over_conclusive(self):
        """Test that explicit markers take priority."""
        response = "I'm done and completed! PLAN_COMPLETE"

        is_complete, reason = CompletionDetector.is_complete(
            response_text=response,
            has_tool_calls=False,
            iteration=1,
            max_iterations=10,
        )

        assert is_complete is True
        assert "PLAN_COMPLETE" in reason
        assert reason != "conclusive_response"

    def test_case_sensitivity_markers(self):
        """Test that completion markers are case-sensitive."""
        response = "task_complete"

        is_complete, reason = CompletionDetector.is_complete(
            response_text=response,
            has_tool_calls=False,
            iteration=1,
            max_iterations=10,
        )

        assert "task_complete" not in reason

    def test_looks_conclusive_helper(self):
        """Test the _looks_conclusive helper method directly."""
        assert CompletionDetector._looks_conclusive("Task is done") is True
        assert CompletionDetector._looks_conclusive("All changes completed") is True
        assert CompletionDetector._looks_conclusive("Successfully finished") is True
        assert CompletionDetector._looks_conclusive("Everything is ready") is True

        assert CompletionDetector._looks_conclusive("I'm working on it") is False
        assert CompletionDetector._looks_conclusive("Let me check the file") is False
        assert CompletionDetector._looks_conclusive("Processing data") is False

    def test_empty_response(self):
        """Test handling of empty response."""
        response = ""

        is_complete, reason = CompletionDetector.is_complete(
            response_text=response,
            has_tool_calls=False,
            iteration=1,
            max_iterations=10,
        )

        assert is_complete is False
        assert reason == "continuing"

    def test_multiple_conclusive_patterns(self):
        """Test response with multiple conclusive patterns."""
        response = "Task is done and completed. Everything is ready!"

        is_complete, reason = CompletionDetector.is_complete(
            response_text=response,
            has_tool_calls=False,
            iteration=1,
            max_iterations=10,
        )

        assert is_complete is True
        assert reason == "conclusive_response"

    def test_iteration_boundary(self):
        """Test iteration at boundary conditions."""
        is_complete, reason = CompletionDetector.is_complete(
            response_text="Still working",
            has_tool_calls=True,
            iteration=9,
            max_iterations=10,
        )
        assert is_complete is False

        is_complete, reason = CompletionDetector.is_complete(
            response_text="Still working",
            has_tool_calls=True,
            iteration=10,
            max_iterations=10,
        )
        assert is_complete is True
        assert reason == "max_iterations_reached"
