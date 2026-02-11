import difflib
import fnmatch
from dataclasses import dataclass
from pathlib import Path

from ac_cdd_core.domain_models import FileCreate, FileOperation, FilePatch
from ac_cdd_core.utils import logger


@dataclass
class PatchResult:
    success: bool
    file_path: str
    diff_text: str
    message: str
    operation: str


class FilePatcher:
    """
    Handles file operations including reading, writing, and patching files.
    """

    def apply_changes(
        self, changes: list[FileOperation], dry_run: bool = False
    ) -> list[PatchResult]:
        """Applies a list of FileOperation objects to the file system."""
        results = []

        for op in changes:
            p = Path(op.path)
            new_content = ""
            diff_text = ""
            message = ""
            success = False

            if isinstance(op, FileCreate):
                success, new_content, diff_text, message = self._prepare_create(p, op, dry_run)
            elif isinstance(op, FilePatch):
                success, new_content, diff_text, message = self._prepare_patch(p, op, dry_run)

            if success and not dry_run:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(new_content, encoding="utf-8")
                logger.info(f"Applied {op.operation} to {p}")
            elif success and dry_run:
                logger.info(f"[DRY-RUN] Would apply {op.operation} to {p}")

            results.append(
                PatchResult(
                    success=success,
                    file_path=str(p),
                    diff_text=diff_text,
                    message=message,
                    operation=op.operation,
                )
            )

        return results

    def _prepare_create(self, p: Path, op: FileCreate, dry_run: bool) -> tuple[bool, str, str, str]:
        old_lines = p.read_text(encoding="utf-8").splitlines(keepends=True) if p.exists() else []
        new_content = op.content

        # Strip markdown code blocks if present (common LLM artifact)
        if new_content.strip().startswith("```"):
            lines = new_content.strip().splitlines()
            # Remove first line (```python)
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            # Remove last line (```)
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            new_content = "\n".join(lines) + "\n"

        new_lines = new_content.splitlines(keepends=True)
        diff = list(
            difflib.unified_diff(old_lines, new_lines, fromfile=str(p), tofile=str(p), lineterm="")
        )
        return (
            True,
            new_content,
            "".join(diff),
            "File created (prepared)" if dry_run else "File created",
        )

    def _prepare_patch(self, p: Path, op: FilePatch, dry_run: bool) -> tuple[bool, str, str, str]:
        if not p.exists():
            return False, "", "", "Cannot patch non-existent file"

        original_content = p.read_text(encoding="utf-8")
        start_idx, end_idx = self._fuzzy_find(original_content, op.search_block)

        if start_idx == -1:
            return False, "", "", "Patch failed: search_block not found"

        new_content = original_content[:start_idx] + op.replace_block + original_content[end_idx:]
        old_lines = original_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        diff = list(
            difflib.unified_diff(old_lines, new_lines, fromfile=str(p), tofile=str(p), lineterm="")
        )
        return (
            True,
            new_content,
            "".join(diff),
            "File patched (prepared)" if dry_run else "File patched",
        )

    def read_src_files(self, src_dir: str) -> str:
        """Reads python files in source directory, respecting .auditignore."""
        ignored_patterns = self._load_ignored_patterns()
        content_str = ""
        path = Path(src_dir)
        for p in path.rglob("*"):
            if not p.is_file() or self._is_path_ignored(p, ignored_patterns):
                continue
            try:
                file_content = p.read_text(encoding="utf-8")
                content_str += f"\n=== {p} ===\n{file_content}"
            except Exception as e:
                logger.warning(f"Skipping {p}: {e}")
        return content_str

    def _load_ignored_patterns(self) -> set[str]:
        ignored = {"__pycache__", ".git", ".env", ".DS_Store", "*.pyc"}
        auditignore_path = Path(".auditignore")
        if auditignore_path.exists():
            try:
                lines = auditignore_path.read_text(encoding="utf-8").splitlines()
                for raw_line in lines:
                    line = raw_line.strip()
                    if line and not line.startswith("#"):
                        ignored.add(line)
            except Exception as e:
                logger.warning(f"Failed to read .auditignore: {e}")
        return ignored

    def _is_path_ignored(self, p: Path, patterns: set[str]) -> bool:
        for pattern in patterns:
            if fnmatch.fnmatch(p.name, pattern) or fnmatch.fnmatch(str(p), pattern):
                return True
            if pattern in str(p):
                return True
        return False

    def _fuzzy_find(self, content: str, block: str) -> tuple[int, int]:
        """Finds the block in content with fuzzy matching."""
        idx = content.find(block)
        if idx != -1:
            return idx, idx + len(block)

        content_lines = content.splitlines(keepends=True)
        block_lines = block.splitlines(keepends=True)

        norm_content = [line.strip() for line in content_lines]
        norm_block = [line.strip() for line in block_lines]

        n_block = len(norm_block)
        n_content = len(norm_content)

        if n_block == 0:
            return -1, -1

        for i in range(n_content - n_block + 1):
            if norm_content[i : i + n_block] == norm_block:
                start_char = sum(len(line) for line in content_lines[:i])
                end_char = sum(len(line) for line in content_lines[: i + n_block])
                return start_char, end_char

        return -1, -1
