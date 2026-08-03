"""
Atomic Tests

Cover replacing a file's contents without leaving a window where it is half written.
"""

# MARK: Imports

import os
from pathlib import Path

import pytest

from docket.core.atomic import TEMP_PREFIX, writeTextAtomic

# MARK: Functions


def strays(directory: Path) -> list[Path]:
    """
    List any temporary files this module left behind.

    directory: The directory to inspect.

    Returns the leftover paths.
    """

    return sorted(path for path in directory.iterdir() if path.name.startswith(TEMP_PREFIX))


def testWriteTextAtomicCreatesAFile(tmp_path: Path) -> None:
    """
    Writing where nothing exists yet produces the file.
    """

    path: Path = tmp_path / "new.txt"

    writeTextAtomic(path, "written")

    assert path.read_text(encoding="utf-8") == "written"


def testWriteTextAtomicReplacesExistingContents(tmp_path: Path) -> None:
    """
    Writing over a file leaves the new contents and nothing of the old, including when the old text was longer.
    """

    path: Path = tmp_path / "existing.txt"
    path.write_text("the previous and rather longer contents", encoding="utf-8")

    writeTextAtomic(path, "short")

    assert path.read_text(encoding="utf-8") == "short"


def testWriteTextAtomicWritesLineFeeds(tmp_path: Path) -> None:
    """
    Newlines are written as LF whatever the platform does by default, so a checkout on Windows does not churn the file.
    """

    path: Path = tmp_path / "lines.txt"

    writeTextAtomic(path, "first\nsecond\n")

    assert path.read_bytes() == b"first\nsecond\n"


def testWriteTextAtomicLeavesNoTemporaryFileBehind(tmp_path: Path) -> None:
    """
    The temporary file is moved into place rather than left beside the destination.
    """

    writeTextAtomic(tmp_path / "clean.txt", "written")

    assert strays(tmp_path) == []


def testWriteTextAtomicCleansUpWhenTheMoveFails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    A failure part way through leaves the destination as it was and takes the temporary file with it.

    This is the whole point of writing elsewhere first. A direct write that failed would leave the destination truncated.
    """

    path: Path = tmp_path / "kept.txt"
    path.write_text("original", encoding="utf-8")

    def failingReplace(source: object, destination: object) -> None:
        """
        Stand in for `os.replace` and refuse.

        source: The path being moved.
        destination: Where it was going.
        """

        raise OSError("the move failed")

    monkeypatch.setattr(os, "replace", failingReplace)

    with pytest.raises(OSError):
        writeTextAtomic(path, "replacement")

    assert path.read_text(encoding="utf-8") == "original"
    assert strays(tmp_path) == []
