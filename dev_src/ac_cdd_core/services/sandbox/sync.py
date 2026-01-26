import io
import tarfile
from pathlib import Path

from ac_cdd_core.config import settings
from ac_cdd_core.hash_utils import calculate_directory_hash


class SandboxSyncManager:
    """Manages file synchronization for the Sandbox."""

    @staticmethod
    def compute_sync_hash() -> str:
        """Computes hash of directories to sync."""
        root = Path.cwd()
        return str(
            calculate_directory_hash(
                root, settings.sandbox.files_to_sync, settings.sandbox.dirs_to_sync
            )
        )

    @staticmethod
    def create_sync_tarball() -> io.BytesIO:
        """Creates a tarball of files to sync."""
        root = Path.cwd()
        tar_buffer = io.BytesIO()

        with tarfile.open(fileobj=tar_buffer, mode="w:gz") as tar:
            for filename in settings.sandbox.files_to_sync:
                file_path = root / filename
                if file_path.exists():
                    tar.add(file_path, arcname=filename)

            for folder in settings.sandbox.dirs_to_sync:
                local_folder = root / folder
                if not local_folder.exists():
                    continue

                for file_path in local_folder.rglob("*"):
                    if file_path.is_file():
                        if "__pycache__" in str(file_path) or ".git" in str(file_path):
                            continue

                        rel_path = file_path.relative_to(root)
                        tar.add(file_path, arcname=str(rel_path))

        tar_buffer.seek(0)
        return tar_buffer
