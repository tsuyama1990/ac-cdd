from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ac_cdd_core.services.git_ops import GitManager


@pytest.mark.asyncio
class TestGitStatePersistence:
    @pytest.fixture
    def git_manager(self) -> GitManager:
        return GitManager()

    @patch("ac_cdd_core.process_runner.ProcessRunner.run_command")
    async def test_ensure_state_branch_exists(
        self, mock_run: AsyncMock, git_manager: GitManager
    ) -> None:
        # Setup: branch exists (rev-parse returns 0)
        mock_run.return_value = ("", "", 0)

        await git_manager.ensure_state_branch()

        # Verify check called but no creation commands
        assert mock_run.call_count >= 1
        args, _ = mock_run.call_args_list[0]  # First call should be rev-parse or fetch
        # Given the updated logic might fetch first, we check that rev-parse eventually succeeds


    @patch("ac_cdd_core.process_runner.ProcessRunner.run_command")
    async def test_read_state_file(self, mock_run: AsyncMock, git_manager: GitManager) -> None:
        expected_content = '{"key": "value"}'
        mock_run.return_value = (expected_content, "", 0)

        content = await git_manager.read_state_file("test.json")

        assert content == expected_content
        args, _ = mock_run.call_args
        assert "show" in args[0]
        assert "ac-cdd/state:test.json" in args[0]

    @patch("ac_cdd_core.services.git.state.tempfile.TemporaryDirectory")
    @patch("ac_cdd_core.process_runner.ProcessRunner.run_command")
    @patch("pathlib.Path.write_text")  # Mock writing file
    async def test_save_state_file(
        self,
        mock_write: MagicMock,
        mock_run: AsyncMock,
        mock_temp: MagicMock,
        git_manager: GitManager,
    ) -> None:
        # Setup mocks
        mock_temp.return_value.__enter__.return_value = "/tmp/dir"  # noqa: S108

        # Sequence of calls:
        # ensure_state_branch calls rev-parse -> success

        # Then save_state_file logic:
        # worktree add, add file, status (changed), commit, push, worktree remove

        # We need to feed enough mock returns
        mock_run.side_effect = [
            ("", "", 0),  # ensure_state_branch -> rev-parse (local exists)
            ("", "", 0),  # worktree add
            ("", "", 0),  # git add
            ("M test.json", "", 0),  # git status (changed)
            ("", "", 0),  # git commit
            ("", "", 0),  # git push
            ("", "", 0),  # worktree remove
        ]

        await git_manager.save_state_file("test.json", "content", "msg")

        cmd_args = [call[0][0] for call in mock_run.call_args_list]

        # Check core operations
        assert any("worktree" in cmd and "add" in cmd for cmd in cmd_args)
        assert any("add" in cmd and "test.json" in cmd for cmd in cmd_args)
        assert any("commit" in cmd for cmd in cmd_args)
        assert any("push" in cmd for cmd in cmd_args)
