import shutil
import subprocess
from pathlib import Path
from typing import List, Optional
from .utils import logger

class ToolNotFoundError(Exception):
    pass

class ToolWrapper:
    def __init__(self, command: str):
        self.command = command
        if not shutil.which(command):
            raise ToolNotFoundError(f"Command '{command}' not found in PATH.")

    def run(self, args: List[str], capture_output: bool = False, check: bool = True, text: bool = True) -> subprocess.CompletedProcess:
        full_cmd = [self.command] + args
        logger.debug(f"Running command: {' '.join(full_cmd)}")
        try:
            return subprocess.run(full_cmd, capture_output=capture_output, check=check, text=text)
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed: {e}")
            raise
