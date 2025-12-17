from unittest.mock import patch

import pytest

from ac_cdd.domain_models import FileCreate, FilePatch
from ac_cdd.services.file_ops import FilePatcher


@pytest.fixture
def patcher():
    return FilePatcher()

def test_apply_changes_create(patcher):
    """Test creating a new file."""
    ops = [FileCreate(path="new_file.py", content="print('hello')")]

    with patch("pathlib.Path.write_text") as mock_write:
        results = patcher.apply_changes(ops, dry_run=False)

        assert len(results) == 1
        assert results[0].success
        assert results[0].operation == "create"
        mock_write.assert_called_with("print('hello')", encoding="utf-8")

def test_apply_changes_patch_success(patcher):
    """Test patching an existing file."""
    ops = [
        FilePatch(
            path="existing.py",
            search_block="old_code",
            replace_block="new_code"
        )
    ]

    with patch("pathlib.Path.read_text", return_value="start\nold_code\nend"), \
         patch("pathlib.Path.write_text") as mock_write, \
         patch("pathlib.Path.exists", return_value=True):

        results = patcher.apply_changes(ops, dry_run=False)

        assert len(results) == 1
        assert results[0].success
        mock_write.assert_called_with("start\nnew_code\nend", encoding="utf-8")

def test_apply_changes_dry_run(patcher):
    """Test dry run does not write."""
    ops = [FileCreate(path="new_file.py", content="print('hello')")]

    with patch("pathlib.Path.write_text") as mock_write:
        results = patcher.apply_changes(ops, dry_run=True)

        assert len(results) == 1
        assert results[0].success
        mock_write.assert_not_called()
