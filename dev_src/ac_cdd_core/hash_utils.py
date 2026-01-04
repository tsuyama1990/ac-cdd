import hashlib
from pathlib import Path


def calculate_directory_hash(root: Path, files: list[str], dirs: list[str]) -> str:
    """Calculate a hash of the project state."""
    hasher = hashlib.sha256()

    for filename in sorted(files):
        p = root / filename
        if p.exists():
            hasher.update(str(p).encode())
            try:
                hasher.update(p.read_bytes())
            except Exception:  # noqa: BLE001, S112
                continue

    for folder in sorted(dirs):
        p = root / folder
        if p.exists():
            for file_path in sorted(p.rglob("*")):
                if file_path.is_file():
                    if "__pycache__" in str(file_path) or ".git" in str(file_path):
                        continue
                    hasher.update(str(file_path.relative_to(root)).encode())
                    try:
                        hasher.update(file_path.read_bytes())
                    except Exception:  # noqa: BLE001, S112
                        continue
    return hasher.hexdigest()
