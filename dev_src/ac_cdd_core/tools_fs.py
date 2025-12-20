from pathlib import Path


def write_to_file(path: str, content: str) -> str:
    """
    Writes content to a file at the specified path.
    Creates parent directories if they don't exist.
    """
    try:
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return f"Successfully wrote to {path}"
    except Exception as e:
        return f"Failed to write to {path}: {e}"
