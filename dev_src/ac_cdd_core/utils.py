import logging
import os
import shutil
import subprocess
from types import TracebackType

from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler

console = Console()

# ロガー設定
logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=console, rich_tracebacks=True)],
)

logger = logging.getLogger("AC-CDD")


def run_command(
    command: list[str], cwd: str | None = None, env: dict[str, str] | None = None
) -> None:
    """
    コマンドを実行し、出力をリアルタイムで表示する。
    エラー時は CalledProcessError を送出する。
    """
    cmd_str = " ".join(command)
    logger.info(f"Running: {cmd_str}")

    try:
        process = subprocess.Popen(  # noqa: S603
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        if process.stdout:
            for _line in process.stdout:
                pass  # RichHandler経由でなく直接出力して生ログを見せる

        process.wait()

    except Exception:
        logger.exception("Command failed")
        raise

    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, command)


def check_api_key() -> bool:
    """
    Checks if the necessary API keys are set in the environment.
    Returns True if keys are found, False otherwise.
    """

    load_dotenv()

    # Check for common API keys
    google_key = os.getenv("GOOGLE_API_KEY")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")

    if not google_key and not openrouter_key:
        logger.warning(
            "API Key not found! (GOOGLE_API_KEY or OPENROUTER_API_KEY). "
            "Proceeding assuming this is a test or dry-run. "
            "Real operations will fail."
        )
        return False
    return True


class KeepAwake:
    """
    Context manager to prevent system sleep/suspension during long operations.
    Uses 'systemd-inhibit' on Linux.
    """

    def __init__(self, reason: str = "AC-CDD Long Running Task") -> None:
        self.reason = reason
        self.process: subprocess.Popen[bytes] | None = None

    def __enter__(self) -> "KeepAwake":
        """Start the inhibitor process."""
        # Check if systemd-inhibit exists
        if not shutil.which("systemd-inhibit"):
            logger.warning("systemd-inhibit not found. Sleep inhibition disabled.")
            return self

        try:
            # We start a subprocess that holds the lock forever (sleep infinity)
            # When this python process exits or we kill the subprocess, the lock is released.
            # --what=idle:sleep:handle-suspend-key:handle-hibernate-key:handle-lid-switch
            # We strictly want to prevent sleep/suspend.
            cmd = [
                "systemd-inhibit",
                "--what=idle:sleep",
                "--who=AC-CDD",
                f"--why={self.reason}",
                "--mode=block",
                "sleep",
                "infinity",
            ]
            self.process = subprocess.Popen(  # noqa: S603
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            logger.info("💤 System sleep inhibited (AC-CDD is running).")
        except Exception:
            logger.exception("Failed to start sleep inhibitor")
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_val: BaseException | None,
        _exc_tb: TracebackType | None,
    ) -> None:
        """Stop the inhibitor process."""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=1)
            except Exception:
                # If it refuses to die, kill it
                logger.debug("Force killing sleep inhibitor")
                if self.process.poll() is None:
                    self.process.kill()
            logger.info("💤 System sleep inhibition released.")
