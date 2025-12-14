import subprocess
import logging
from rich.logging import RichHandler
from rich.console import Console

console = Console()

# ロガー設定
logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=console, rich_tracebacks=True)]
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
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        for line in process.stdout:
            print(line, end="") # RichHandler経由でなく直接出力して生ログを見せる

        process.wait()

        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, command)

    except Exception as e:
        logger.error(f"Command failed: {e}")
        raise

def check_dependency(cmd: str) -> bool:
    import shutil
    return shutil.which(cmd) is not None
