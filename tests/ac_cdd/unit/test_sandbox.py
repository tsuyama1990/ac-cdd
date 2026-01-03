import shlex
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ac_cdd_core.sandbox import SandboxRunner


def test_shlex_quoting() -> None:
    """Verify that multiline commands are safely quoted using shlex.join."""
    unsafe_cmd = ["aider", "--message", "Line 1\nLine 2 (paren)"]
    safe_str = shlex.join(unsafe_cmd)

    # Verify it looks like: aider --message 'Line 1\nLine 2 (paren)'
    assert "aider" in safe_str
    assert "'Line 1\nLine 2 (paren)'" in safe_str or '"Line 1\nLine 2 (paren)"' in safe_str


@pytest.mark.asyncio
async def test_sync_hash_reset_on_failure() -> None:
    """Verify that _last_sync_hash is reset to None when sandbox retry logic hits."""
    runner = SandboxRunner()
    runner._last_sync_hash = "some_hash"
    runner.sandbox = MagicMock()
    # Mock commands.run to raise exception first time, succeed second time
    runner.sandbox.commands.run.side_effect = [
        Exception("Sandbox was not found"),  # Trigger retry
        MagicMock(stdout="ok", stderr="", exit_code=0),
    ]

    with (
        patch("ac_cdd_core.sandbox.Sandbox.create", return_value=MagicMock()),
        patch.object(runner, "_sync_to_sandbox", new_callable=AsyncMock),
    ):
        # We also need to mock _get_sandbox to return a new sandbox
        # But the logic is internal. Let's patch _get_sandbox actually?
        # No, we want to test run_command's loop.
        # We need _get_sandbox to return a sandbox.

        # Since _get_sandbox calls Sandbox.create if self.sandbox is None,
        # the retry loop sets self.sandbox=None.

        await runner.run_command(["ls"])

        # Check if reset happened
        assert runner._last_sync_hash is None
        # Sync should be called twice (once for initial (mocked out context), once after retry)
        # Actually, in this test setup:
        # 1. run_command calls _get_sandbox -> returns self.sandbox (already set)
        # 2. calls _sync_to_sandbox
        # 3. runs command -> Fails
        # 4. sets self.sandbox = None, self._last_sync_hash = None
        # 5. loop continues
        # 6. run_command calls _get_sandbox -> creates new sandbox
        assert runner._last_sync_hash is None


@pytest.mark.asyncio
async def test_get_sandbox_creates_new() -> None:
    """Test that _get_sandbox creates new sandbox when none exists."""
    runner = SandboxRunner()

    with patch("ac_cdd_core.sandbox.Sandbox.create", return_value=MagicMock()) as mock_create:
        sandbox = await runner._get_sandbox()

        assert sandbox is not None
        mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_get_sandbox_reuses_existing() -> None:
    """Test that _get_sandbox reuses existing sandbox."""
    runner = SandboxRunner()
    runner.sandbox = MagicMock()

    with patch("ac_cdd_core.sandbox.Sandbox.create") as mock_create:
        sandbox = await runner._get_sandbox()

        assert sandbox == runner.sandbox
        mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_sync_to_sandbox_success() -> None:
    """Test successful sync to sandbox."""
    runner = SandboxRunner()
    runner.sandbox = MagicMock()

    with (
        patch.object(runner, "_create_sync_tarball", return_value=b"tarball_data"),
        patch.object(runner, "_compute_sync_hash", return_value="hash123"),
    ):
        await runner._sync_to_sandbox()

        assert runner._last_sync_hash == "hash123"


@pytest.mark.asyncio
async def test_sync_to_sandbox_hash_unchanged() -> None:
    """Test that sync is skipped when hash unchanged."""
    runner = SandboxRunner()
    runner.sandbox = MagicMock()
    runner._last_sync_hash = "hash123"

    with (
        patch.object(runner, "_compute_sync_hash", return_value="hash123"),
        patch.object(runner, "_create_sync_tarball") as mock_tarball,
    ):
        await runner._sync_to_sandbox()

        # Should not create tarball if hash unchanged
        mock_tarball.assert_not_called()


@pytest.mark.asyncio
async def test_run_command_success() -> None:
    """Test successful command execution."""
    runner = SandboxRunner()
    runner.sandbox = MagicMock()
    # commands.run is synchronous in e2b
    runner.sandbox.commands.run.return_value = MagicMock(stdout="output", stderr="", exit_code=0)

    with (
        patch.object(runner, "_get_sandbox", new_callable=AsyncMock) as mock_get,
        patch.object(runner, "_sync_to_sandbox", new_callable=AsyncMock),
    ):
        mock_get.return_value = runner.sandbox
        stdout, _stderr, code = await runner.run_command(["echo", "hello"])

        assert code == 0
        assert stdout == "output"


@pytest.mark.asyncio
async def test_run_command_retry_on_failure() -> None:
    """Test command retry logic on sandbox failure."""
    runner = SandboxRunner()
    runner.sandbox = MagicMock()

    # First call fails (Exception) on the INITIAL sandbox
    runner.sandbox.commands.run.side_effect = Exception("Sandbox error")

    # Second call (retry) will be on a NEW sandbox created via Sandbox.create
    # So we must configure that new mock to succeed
    new_sandbox_mock = MagicMock()
    new_sandbox_mock.commands.run.return_value = MagicMock(stdout="ok", stderr="", exit_code=0)

    with (
        patch("ac_cdd_core.sandbox.Sandbox.create", return_value=new_sandbox_mock) as mock_create,
        patch.object(runner, "_sync_to_sandbox", new_callable=AsyncMock),
    ):
        _stdout, _stderr, code = await runner.run_command(["test"])

        # Should retry and succeed
        assert code == 0
        # Should create new sandbox after failure
        # (via _get_sandbox logic which calls create if sandbox fails/is None)
        # Note: logic inside run_command calls _get_sandbox again on retry.
        # But wait, run_command calls _get_sandbox at start of loop.
        # We need to ensure _get_sandbox creates new one on stored state change?
        # Actually logic is: catch exception -> kill sandbox -> continue loop
        assert mock_create.called


@pytest.mark.asyncio
async def test_cleanup_sandbox() -> None:
    """Test sandbox cleanup."""
    runner = SandboxRunner()
    mock_sandbox = MagicMock()
    runner.sandbox = mock_sandbox

    await runner.cleanup()

    # Should call kill on sandbox
    mock_sandbox.kill.assert_called_once()
    assert runner.sandbox is None
