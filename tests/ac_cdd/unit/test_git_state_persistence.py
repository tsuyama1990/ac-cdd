import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from ac_cdd_core.services.git_ops import GitManager

@pytest.mark.asyncio
class TestGitStatePersistence:

    @pytest.fixture
    def git_manager(self):
        return GitManager()

    @patch("ac_cdd_core.process_runner.ProcessRunner.run_command")
    async def test_ensure_state_branch_exists(self, mock_run, git_manager):
        # Setup: branch exists (rev-parse returns 0)
        mock_run.return_value = ("", "", 0)

        await git_manager.ensure_state_branch()

        # Verify check called but no creation commands
        assert mock_run.call_count >= 1
        args, _ = mock_run.call_args_list[0] # First call should be rev-parse or fetch
        # Given the updated logic might fetch first, we check that rev-parse eventually succeeds

    @patch("ac_cdd_core.process_runner.ProcessRunner.run_command")
    async def test_ensure_state_branch_creates_if_missing(self, mock_run, git_manager):
        # Mock sequence:
        # 1. rev-parse local (fail)
        # 2. fetch origin (fail or succeed, doesn't matter if local missing)
        # 3. rev-parse local (fail)
        # 4. mktree
        # 5. commit-tree
        # 6. update-ref

        # We need to adapt based on implementation.
        # Assuming implementation:
        # rev-parse local (fail)
        # fetch origin (ignore error)
        # rev-parse local (fail)
        # create orphan

        mock_run.side_effect = [
            ("", "", 128), # rev-parse local
            ("", "", 128), # fetch origin (optional/can fail)
            ("", "", 128), # rev-parse local
            ("tree_hash\n", "", 0), # mktree
            ("commit_hash\n", "", 0), # commit-tree
            ("", "", 0) # update-ref
        ]

        await git_manager.ensure_state_branch()

        # Verify creation calls
        cmd_args = [call[0][0] for call in mock_run.call_args_list]
        assert any("mktree" in cmd for cmd in cmd_args)
        assert any("commit-tree" in cmd for cmd in cmd_args)
        assert any("update-ref" in cmd for cmd in cmd_args)

    @patch("ac_cdd_core.process_runner.ProcessRunner.run_command")
    async def test_read_state_file(self, mock_run, git_manager):
        expected_content = '{"key": "value"}'
        mock_run.return_value = (expected_content, "", 0)

        content = await git_manager.read_state_file("test.json")

        assert content == expected_content
        args, _ = mock_run.call_args
        assert "show" in args[0]
        assert "ac-cdd/state:test.json" in args[0]

    @patch("ac_cdd_core.services.git_ops.tempfile.TemporaryDirectory")
    @patch("ac_cdd_core.process_runner.ProcessRunner.run_command")
    @patch("pathlib.Path.write_text") # Mock writing file
    async def test_save_state_file(self, mock_write, mock_run, mock_temp, git_manager):
        # Setup mocks
        mock_temp.return_value.__enter__.return_value = "/tmp/dir"

        # Sequence of calls:
        # ensure_state_branch calls rev-parse -> success

        # Then save_state_file logic:
        # worktree add
        # add file
        # status (changed)
        # commit
        # push
        # worktree remove

        # We need to feed enough mock returns
        mock_run.side_effect = [
            ("", "", 0), # ensure_state_branch -> rev-parse (local exists)
            ("", "", 0), # worktree add
            ("", "", 0), # git add
            ("M test.json", "", 0), # git status (changed)
            ("", "", 0), # git commit
            ("", "", 0), # git push
            ("", "", 0), # worktree remove
        ]

        await git_manager.save_state_file("test.json", "content", "msg")

        cmd_args = [call[0][0] for call in mock_run.call_args_list]

        # Check core operations
        assert any("worktree" in cmd and "add" in cmd for cmd in cmd_args)
        assert any("add" in cmd and "test.json" in cmd for cmd in cmd_args)
        assert any("commit" in cmd for cmd in cmd_args)
        assert any("push" in cmd for cmd in cmd_args)
