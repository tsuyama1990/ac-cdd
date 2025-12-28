import logging
import subprocess

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


def run_command(command: list[str], cwd=None, env=None):
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

        for line in process.stdout:
            print(line, end="")  # RichHandler経由でなく直接出力して生ログを見せる

        process.wait()

        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, command)

    except Exception as e:
        logger.error(f"Command failed: {e}")
        raise


def check_api_key() -> None:
    """
    Checks if the necessary API keys are set in the environment.
    Raises ValueError if neither GOOGLE_API_KEY nor OPENROUTER_API_KEY is found.
    """
    import os

    from dotenv import load_dotenv
    
    # Load .env explicitly
    load_dotenv()

    # Check for common API keys
    google_key = os.getenv("GOOGLE_API_KEY")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")

    # You might also want to check settings if keys are loaded there, 
    # but Environment Variables are the most reliable source for these libs.
    
    if not google_key and not openrouter_key:
        raise ValueError(
            "API Key not found! Please set GOOGLE_API_KEY (or OPENROUTER_API_KEY) in your .env file."
        )
