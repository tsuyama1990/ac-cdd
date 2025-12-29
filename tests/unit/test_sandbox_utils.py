import shlex
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ac_cdd_core.sandbox import SandboxRunner


def test_shlex_quoting():
    """Verify that multiline commands are safely quoted using shlex.join."""
    unsafe_cmd = ["aider", "--message", "Line 1\nLine 2 (paren)"]
    safe_str = shlex.join(unsafe_cmd)

    # Verify it looks like: aider --message 'Line 1\nLine 2 (paren)'
    assert "aider" in safe_str
    assert "'Line 1\nLine 2 (paren)'" in safe_str or '"Line 1\nLine 2 (paren)"' in safe_str


@pytest.mark.asyncio
async def test_sync_hash_reset_on_failure():
    """Verify that _last_sync_hash is reset to None when sandbox retry logic hits."""
    runner = SandboxRunner()
    runner._last_sync_hash = "some_hash"
    runner.sandbox = MagicMock()
    # Mock commands.run to raise exception first time, succeed second time
    runner.sandbox.commands.run.side_effect = [
        Exception("Sandbox was not found"),  # Trigger retry
        MagicMock(stdout="ok", stderr="", exit_code=0),
    ]

    with patch("ac_cdd_core.sandbox.Sandbox.create", return_value=MagicMock()):
        with patch.object(runner, "_sync_to_sandbox", new_callable=AsyncMock):
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
