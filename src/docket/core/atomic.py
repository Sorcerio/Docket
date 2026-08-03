"""
Docket Atomic

Replacing a file's contents in one indivisible step, so no reader ever sees a partial write.
"""

# MARK: Imports

import os
import tempfile
from pathlib import Path
from typing import IO, Any

# MARK: Constants

# Marks a temporary file as this module's, so a leftover from a killed process is recognizable rather than mysterious.
TEMP_PREFIX: str = ".docket-"
TEMP_SUFFIX: str = ".tmp"

# MARK: Functions


def writeTextAtomic(path: Path, text: str) -> None:
    """
    Replace a file's contents in one step, leaving no window where the file is half written.

    The text goes to a temporary file in the destination's own directory and is then moved into place with `os.replace`, which is atomic on both POSIX and Windows.
    Writing the temporary file beside the destination rather than in the system temporary directory is what keeps the move on one filesystem, since a cross-device move is a copy and a copy is not atomic.

    Newlines are written as LF explicitly, matching what every direct write in this repository already did, so a checkout on Windows does not churn the file.

    path: The file to replace. Its parent directory must already exist.
    text: The full contents to write.
    """

    # Hold the temporary path outside the try, so cleanup can find it even when the write itself is what failed.
    temporaryPath: Path

    handle: IO[Any] = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        dir=path.parent,
        prefix=TEMP_PREFIX,
        suffix=TEMP_SUFFIX,
        delete=False,
    )
    temporaryPath = Path(handle.name)

    try:
        # Flush through the library buffer and then through the operating system's, so the move promotes fully written bytes rather than a queued write.
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporaryPath, path)
    except BaseException:
        # A failed write must not leave its temporary file behind, since the destination is untouched and the leftover would only confuse the next reader of the directory.
        temporaryPath.unlink(missing_ok=True)

        raise
