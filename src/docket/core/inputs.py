"""
Docket Inputs

Checks on values supplied directly by a caller, rather than read back from a file.

A value reaching the core came either from a command line or from an MCP tool call, and neither shell may be trusted to have checked it. POSIX shells pass an empty string through to the process, so an empty title or an empty destination arrives intact and would otherwise be written. PowerShell discards it before the process starts, which produces its own usage error and never reaches here.
"""

# MARK: Imports

import os
from pathlib import Path

from docket.core.errors import EmptyValueError, OutputPathError

# MARK: Functions


def requireText(value: str, name: str) -> str:
    """
    Reject a value that carries no text.

    Whitespace counts as empty, since a title of spaces is as unusable as a title of nothing and would leave the same blank cell in every listing.

    value: The value to check.
    name: What to name in the error message, for example `title`.

    Returns the value unchanged, with its surrounding whitespace intact.
    """

    if not value.strip():
        raise EmptyValueError(f"The {name} cannot be empty.")

    return value


def requireWritableFile(path: str, name: str) -> Path:
    """
    Reject a destination that cannot be written as a file.

    The checks that can be made without touching the disk are made here, so a caller learns the destination is unusable before any work is done for it. A filesystem may still refuse the write afterwards for a reason no check can predict, which is why `writeFile` exists to catch that too.

    path: The destination as the caller supplied it.
    name: What to name in the error message, for example `--out path`.

    Returns the destination as a `Path`.
    """

    requireText(path, name)

    resolved: Path = Path(path)

    # A directory can never be opened as a file, and this is the case an empty path used to reach by resolving to the working directory.
    if resolved.is_dir():
        raise OutputPathError(f"The {name} '{path}' is a directory, not a file.")

    # An existing file the process cannot open for writing fails no matter what its parent allows.
    if resolved.exists() and not os.access(resolved, os.W_OK):
        raise OutputPathError(f"The {name} '{path}' is not writable.")

    # An existing parent that refuses new entries fails before the directory tree is touched. A parent that does not exist yet is not an error, since the write creates it.
    parent: Path = resolved.parent
    if parent.is_dir() and not os.access(parent, os.W_OK):
        raise OutputPathError(f"The {name} '{path}' is inside a directory that is not writable.")

    return resolved


def writeFile(path: Path, text: str, name: str) -> Path:
    """
    Write text to a destination, translating whatever the filesystem refuses into a docket error.

    Every check `requireWritableFile` can make is a prediction, and a prediction can be wrong. A refusal escaping here as a bare `OSError` would reach the user as a traceback rather than as a message, so it is translated instead.

    path: The destination, already checked.
    text: The content to write.
    name: What to name in the error message, for example `--out path`.

    Returns the path written.
    """

    try:
        # Create the tree only once the destination itself has been accepted, so a rejected path leaves no directories behind.
        path.parent.mkdir(parents=True, exist_ok=True)

        # Write LF explicitly so the file does not churn on a Windows checkout.
        path.write_text(text, encoding="utf-8", newline="\n")
    except OSError as error:
        raise OutputPathError(f"Could not write the {name} '{path}': {error.strerror or error}.") from error

    return path
