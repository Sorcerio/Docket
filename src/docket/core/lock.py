"""
Docket Lock

Serializing reads and writes across separate processes sharing one repository.
"""

# MARK: Imports

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from filelock import ReadWriteLock, Timeout

from docket.core.errors import LockTimeoutError

# MARK: Constants

# The lock file, kept beside `.docket.toml` because one lock covers both the tickets and the configuration.
LOCK_FILENAME: str = ".docket.lock"

# MARK: Functions


def lockPath(repoRoot: Path) -> Path:
    """
    Resolve where a repository's lock file belongs.

    repoRoot: The directory holding `.docket.toml`.

    Returns the absolute path of the lock file.
    """

    # Resolve the path, since the lock is shared per resolved path and two spellings of one directory must not produce two locks.
    return (repoRoot / LOCK_FILENAME).resolve()


@contextmanager
def sharedLock(repoRoot: Path, timeout: float) -> Iterator[None]:
    """
    Hold the repository's read lock for the duration of a block.

    Any number of processes may read at once, and none of them may read while a writer holds the lock.
    This is what closes the window where a reader catches `setStatus` between writing the new file and removing the old one, and reports a duplicate id that never really existed.

    repoRoot: The directory holding `.docket.toml`.
    timeout: How long to wait for a writer to finish, in seconds.
    """

    with _held(repoRoot, timeout, writing=False):
        yield


@contextmanager
def exclusiveLock(repoRoot: Path, timeout: float) -> Iterator[None]:
    """
    Hold the repository's write lock for the duration of a block.

    One process writes at a time and no process reads while it does, so a read followed by a write back is indivisible from any other process's point of view.
    The whole read-modify-write span belongs inside the block, not just the write, because holding it for the write alone would still let two processes derive their changes from the same starting state.

    repoRoot: The directory holding `.docket.toml`.
    timeout: How long to wait for the current holder to finish, in seconds.
    """

    with _held(repoRoot, timeout, writing=True):
        yield


# MARK: Private Functions


@contextmanager
def _held(repoRoot: Path, timeout: float, writing: bool) -> Iterator[None]:
    """
    Hold one side of the repository lock, translating a timeout into a docket error.

    `filelock` raises its own `Timeout`, which no caller of `docket.core` should have to know about, so it is converted here into the error every other failure in this package already uses.

    repoRoot: The directory holding `.docket.toml`.
    timeout: How long to wait, in seconds.
    writing: Whether to take the exclusive side rather than the shared one.
    """

    path: Path = lockPath(repoRoot)

    # The lock instance is shared per resolved path, so the timeout is passed at acquisition rather than construction, where a later caller's value would be ignored.
    lock: ReadWriteLock = ReadWriteLock(path)
    acquire = lock.write_lock if writing else lock.read_lock

    try:
        with acquire(timeout=timeout):
            yield
    except Timeout as error:
        raise LockTimeoutError(f"Another docket process has been {'writing to' if writing else 'locking'} {repoRoot} for longer than {timeout} seconds. Nothing was changed. Retry the call.") from error
