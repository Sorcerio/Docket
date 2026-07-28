"""
Input Tests

Cover the checks applied to values a caller supplied, which neither shell may be trusted to have made.
"""

# MARK: Imports

from pathlib import Path

import pytest

from docket.core.errors import EmptyValueError, OutputPathError
from docket.core.inputs import requireText, requireWritableFile, writeFile

# MARK: Tests


@pytest.mark.parametrize("value", ["Skirmish setup", " padded ", "0"])
def testTextPasses(value: str) -> None:
    """
    Anything carrying a character survives unchanged, including surrounding whitespace, since trimming is not this check's job.

    value: The value under test.
    """

    assert requireText(value, "title") == value


@pytest.mark.parametrize("value", ["", " ", "\t", "\n"])
def testEmptyTextIsRefused(value: str) -> None:
    """
    Whitespace is as unusable as nothing, so both are refused rather than written and left to render as a blank cell.

    value: The value under test.
    """

    with pytest.raises(EmptyValueError) as raised:
        requireText(value, "title")

    # The message names the field, since a caller passing several values needs to know which one was empty.
    assert "title" in str(raised.value)


def testWritableFileAcceptsANewPath(tmp_path: Path) -> None:
    """
    A destination whose parent does not exist yet is accepted, because writing it creates the tree.
    """

    target: Path = tmp_path / "nested" / "graph.mmd"

    assert requireWritableFile(str(target), "--out path") == target


def testWritableFileRefusesAnEmptyPath() -> None:
    """
    An empty path resolves to the working directory, which is how this reached the filesystem as a directory write before.
    """

    with pytest.raises(EmptyValueError):
        requireWritableFile("", "--out path")


def testWritableFileRefusesADirectory(tmp_path: Path) -> None:
    """
    A directory can never be opened as a file, and saying so beats the operating system's own message for it.
    """

    with pytest.raises(OutputPathError) as raised:
        requireWritableFile(str(tmp_path), "--out path")

    assert "is a directory" in str(raised.value)


def testWriteFileWritesTheTree(tmp_path: Path) -> None:
    """
    The parent tree is created on the way, so a destination nested under nothing still lands.
    """

    target: Path = tmp_path / "nested" / "deeper" / "graph.mmd"

    assert writeFile(target, "graph TD\n", "--out path") == target
    assert target.read_text(encoding="utf-8") == "graph TD\n"


def testWriteFileTranslatesARefusal(tmp_path: Path) -> None:
    """
    A refusal the checks could not predict still has to arrive as a docket error, since a traceback is not a message.
    """

    # A path whose parent is an existing file cannot be created, and no prior check rejects it.
    blocker: Path = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")

    with pytest.raises(OutputPathError):
        writeFile(blocker / "graph.mmd", "graph TD\n", "--out path")
