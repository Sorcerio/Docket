"""
Lock Tests

Cover where the lock file lives and how the locks nest within one process.

The guarantees that only hold across processes are covered by the concurrency tests, since nothing observable here would prove them.
"""

# MARK: Imports

from pathlib import Path

import pytest

from docket.core.config import Config
from docket.core.lock import LOCK_FILENAME, exclusiveLock, lockPath, sharedLock
from docket.core.store import Store, TicketSet

# MARK: Functions


def testLockPathSitsBesideTheConfiguration(repoDir: Path) -> None:
    """
    One lock covers the tickets and the configuration, so it lives at the repository root rather than under the ticket directories.
    """

    assert lockPath(repoDir) == (repoDir / LOCK_FILENAME).resolve()


def testLockPathIsTheSameForEverySpellingOfOneDirectory(repoDir: Path) -> None:
    """
    Two paths naming one directory must not produce two locks, because two locks would guard nothing.
    """

    assert lockPath(repoDir) == lockPath(repoDir / "docs" / "..")


def testTakingTheSharedLockCreatesTheLockFile(repoDir: Path) -> None:
    """
    The lock file is created on demand, since a freshly deployed repository has never taken one.
    """

    with sharedLock(repoDir, 5.0):
        pass

    assert lockPath(repoDir).exists()


def testSharedLocksNestWithinOneProcess(repoDir: Path) -> None:
    """
    A read inside a read is allowed, so a caller never has to track whether it already holds the shared side.
    """

    with sharedLock(repoDir, 5.0):
        with sharedLock(repoDir, 5.0):
            pass


def testExclusiveLocksNestWithinOneProcess(repoDir: Path) -> None:
    """
    A write inside a write is allowed on one thread, which is what lets a mutator call another without either knowing.
    """

    with exclusiveLock(repoDir, 5.0):
        with exclusiveLock(repoDir, 5.0):
            pass


def testReadingInsideAWriteIsRefused(repoDir: Path) -> None:
    """
    Downgrading from the write side to the read side raises rather than nesting.

    This is why `Store` keeps an unlocked load at all. A mutator holding the write lock cannot call `loadAll`, so it calls the unlocked form instead, and this test is what stops that arrangement being quietly undone.
    """

    with pytest.raises(RuntimeError):
        with exclusiveLock(repoDir, 5.0):
            with sharedLock(repoDir, 5.0):
                pass


def testMutatorsDoNotReadThroughTheLockedLoad(config: Config, store: Store) -> None:
    """
    Every mutator runs inside the write lock, so none of them may reach `loadAll`.

    Were one to do so it would raise the refusal above rather than returning, which makes this a direct test of the arrangement rather than of the lock.
    """

    created: str = store.create(key="CORE", title="Written").ticket.id

    store.update(created, title="Retitled")
    store.setMetadata(created, "video", "covered")
    store.setStatus(created, "done")

    loaded: TicketSet = store.loadAll()

    assert loaded.get(created).title == "Retitled"
    assert loaded.get(created).status == "done"
    assert config.donePath in loaded.get(created).path.parents
