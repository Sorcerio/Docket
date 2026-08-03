"""
Concurrency Tests

Cover the guarantees that only hold across separate processes.

Every test here spawns real processes. Threads would pass against an unlocked store without proving anything, because the server already serializes its own handlers and the failure being guarded against is the one that spans processes.
"""

# MARK: Imports

import subprocess
import sys
import time
from pathlib import Path

import pytest

from docket.core.config import Config, loadConfig
from docket.core.errors import LockTimeoutError
from docket.core.store import Store, TicketSet

# MARK: Constants

# The worker script, resolved beside this file so the tests run from any working directory.
WORKER_PATH: Path = Path(__file__).parent / "concurrencyWorker.py"

# How many processes contend at once. Enough to lose an update reliably when nothing guards the gap, small enough to stay quick.
WORKERS: int = 8

# How long a worker is given to finish once released.
WORKER_TIMEOUT: float = 60.0

# MARK: Fixtures


@pytest.fixture
def barrier(repoDir: Path) -> Path:
    """
    Name the file that releases every spawned worker at once.

    repoDir: The repository root fixture.

    Returns the path, which does not exist yet.
    """

    return repoDir / "barrier.start"


# MARK: Functions


def spawn(configPath: Path, barrierPath: Path, operation: str, *arguments: str) -> subprocess.Popen:
    """
    Start one worker process, which blocks until the barrier is released.

    configPath: The configuration the worker loads.
    barrierPath: The file the worker waits for.
    operation: The operation to run.
    arguments: That operation's own arguments.

    Returns the running process.
    """

    return subprocess.Popen(
        [sys.executable, str(WORKER_PATH), str(configPath), str(barrierPath), operation, *arguments],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def release(barrierPath: Path) -> None:
    """
    Release every waiting worker.

    barrierPath: The barrier file to create.
    """

    barrierPath.write_text("go", encoding="utf-8")


def collect(processes: list[subprocess.Popen]) -> list[str]:
    """
    Wait for every worker and return what each printed, failing the test on the first one that did not succeed.

    A worker's stderr is surfaced in the failure, since a traceback inside another process is otherwise invisible to pytest.

    processes: The running workers.

    Returns each worker's stripped standard output.
    """

    output: list[str] = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=WORKER_TIMEOUT)

        assert process.returncode == 0, f"A worker failed:\n{stderr}"

        output.append(stdout.strip())

    return output


def runAll(configPath: Path, barrierPath: Path, operation: str, argumentsPerWorker: list[list[str]]) -> list[str]:
    """
    Spawn one worker per argument set, release them together, and collect their output.

    configPath: The configuration every worker loads.
    barrierPath: The barrier releasing them.
    operation: The operation each worker runs.
    argumentsPerWorker: One argument list per worker.

    Returns each worker's stripped standard output.
    """

    processes: list[subprocess.Popen] = [spawn(configPath, barrierPath, operation, *arguments) for arguments in argumentsPerWorker]

    # Every process is running before any is released, so they contend rather than queue.
    release(barrierPath)

    return collect(processes)


def useLockTimeout(configPath: Path, timeout: float) -> Path:
    """
    Rewrite a throwaway repository's configuration with a shorter lock timeout.

    The field is inserted above `[keys]` rather than appended, because a top-level key written after a table header belongs to that table and would be read as a key named `lockTimeout` instead of as the setting.

    configPath: The configuration to rewrite.
    timeout: The timeout to set, in seconds.

    Returns the same path.
    """

    text: str = configPath.read_text(encoding="utf-8")
    configPath.write_text(text.replace("[keys]", f"lockTimeout = {timeout}\n\n[keys]", 1), encoding="utf-8", newline="\n")

    return configPath


def testConcurrentCreatesAllocateDistinctIds(config: Config, barrier: Path) -> None:
    """
    Two processes minting under one key must not derive the same number.

    Without the lock this fails loudly: the id comes from scanning what exists, the filename slug comes from the title, so overlapping creates write several files all claiming the same id and only `validate` notices afterwards.
    """

    ids: list[str] = runAll(config.path, barrier, "create", [["CORE", f"Worker {index}"] for index in range(WORKERS)])

    assert len(set(ids)) == WORKERS

    # The files have to agree with what the workers reported, since a lost write would leave a returned id with nothing on disk.
    loaded: TicketSet = Store(loadConfig(config.path)).loadAll()

    assert sorted(loaded.ids()) == sorted(ids)
    assert loaded.duplicates == []


def testConcurrentMetadataWritesDoNotOverwriteEachOther(config: Config, store: Store, barrier: Path) -> None:
    """
    Each process sets its own namespaced key, and every one of them has to survive.

    Setting one entry rewrites the whole file, so without the lock the last writer reverts every entry written since it loaded.
    """

    ticketId: str = store.create(key="CORE", title="Shared").ticket.id

    runAll(config.path, barrier, "setMetadata", [[ticketId, f"worker{index}", str(index)] for index in range(WORKERS)])

    metadata: dict = Store(loadConfig(config.path)).load(ticketId).metadata

    assert {f"worker{index}": str(index) for index in range(WORKERS)} == metadata


def testStatusMovesAreNeverSeenAsDuplicates(config: Config, store: Store, barrier: Path) -> None:
    """
    A reader must never catch a status move between the new file being written and the old one being removed.

    The move is two steps whatever else is done, so this is the case atomic writes alone cannot fix and the reader's share of the lock is what closes.
    """

    ticketId: str = store.create(key="CORE", title="Moving").ticket.id

    # One process flips the ticket into done, which crosses directories and so performs the write and the delete.
    process: subprocess.Popen = spawn(config.path, barrier, "setStatus", ticketId, "done")
    release(barrier)

    reader: Store = Store(loadConfig(config.path))

    # Read continuously for as long as the move is in flight, since the window being guarded is short and has to be hit rather than waited for.
    while process.poll() is None:
        loaded: TicketSet = reader.loadAll()

        assert loaded.duplicates == []
        assert loaded.failures == []

    assert collect([process]) == ["done"]


def testLockTimeoutIsRaisedWhileAnotherProcessHolds(repoDir: Path, barrier: Path) -> None:
    """
    A writer that cannot get in within `lockTimeout` fails rather than proceeding unguarded, and says so through a docket error rather than the locking library's own.
    """

    # A short timeout, so the test spends a fraction of a second proving this rather than the default five.
    configPath: Path = useLockTimeout(repoDir / ".docket.toml", 0.2)


    holder: subprocess.Popen = spawn(configPath, barrier, "hold", "3")
    release(barrier)

    # Wait for the holder to confirm it actually has the lock, rather than racing its startup.
    assert holder.stdout is not None
    assert holder.stdout.readline().strip() == "held"

    store: Store = Store(loadConfig(configPath))

    started: float = time.monotonic()
    with pytest.raises(LockTimeoutError):
        store.create(key="CORE", title="Blocked")

    # The call has to have waited for the configured window rather than failing the moment it found the lock taken.
    assert time.monotonic() - started >= 0.2

    holder.communicate(timeout=WORKER_TIMEOUT)


def testLockTimeoutLeavesTheRepositoryUnchanged(repoDir: Path, barrier: Path) -> None:
    """
    The error promises nothing was written, and a retry is only safe if that promise holds.
    """

    configPath: Path = useLockTimeout(repoDir / ".docket.toml", 0.2)

    store: Store = Store(loadConfig(configPath))
    existing: str = store.create(key="CORE", title="Untouched").ticket.id

    holder: subprocess.Popen = spawn(configPath, barrier, "hold", "3")
    release(barrier)

    assert holder.stdout is not None
    assert holder.stdout.readline().strip() == "held"

    with pytest.raises(LockTimeoutError):
        store.update(existing, title="Changed")

    holder.communicate(timeout=WORKER_TIMEOUT)

    # The ticket kept its title, and no half-written file was left anywhere.
    reloaded: TicketSet = store.loadAll()

    assert reloaded.get(existing).title == "Untouched"
    assert reloaded.failures == []
