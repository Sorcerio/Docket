"""
Concurrency Worker

A standalone process driving one `docket.core` operation, spawned by the concurrency tests.

Threads would prove nothing here, because the guarantee under test is the one that spans processes. This file is therefore executed with the interpreter running the tests rather than imported by them.
It is not named `test_` on purpose, so pytest collects the tests that spawn it and never this.
"""

# MARK: Imports

import sys
import time
from pathlib import Path

from docket.core.config import Config, loadConfig
from docket.core.store import Store

# MARK: Constants

# How long a worker waits for the parent to release the start barrier before giving up on it.
BARRIER_TIMEOUT: float = 30.0

# How often the barrier is checked while waiting.
BARRIER_POLL: float = 0.005

# MARK: Functions


def awaitBarrier(barrierPath: Path) -> None:
    """
    Block until the parent creates the start file.

    Every worker is spawned before any of them is released, so the operations genuinely overlap rather than merely following each other closely.

    barrierPath: The file the parent creates once every worker is running.
    """

    deadline: float = time.monotonic() + BARRIER_TIMEOUT

    while not barrierPath.exists():
        # A parent that died before releasing the barrier must not leave a worker spinning forever.
        if time.monotonic() > deadline:
            raise TimeoutError(f"The start barrier {barrierPath} never appeared.")

        time.sleep(BARRIER_POLL)


def main(argv: list[str]) -> int:
    """
    Run one operation and print whatever the test needs to assert on.

    argv: The arguments after the script name, being the configuration path, the barrier path, the operation, and that operation's own arguments.

    Returns the process exit code.
    """

    configPath: Path = Path(argv[0])
    barrierPath: Path = Path(argv[1])
    operation: str = argv[2]
    rest: list[str] = argv[3:]

    # Load before waiting, so the barrier releases into the operation itself rather than into a cold start.
    config: Config = loadConfig(configPath)
    store: Store = Store(config)

    awaitBarrier(barrierPath)

    if operation == "create":
        print(store.create(key=rest[0], title=rest[1]).ticket.id)

        return 0

    if operation == "setMetadata":
        store.setMetadata(rest[0], rest[1], rest[2])

        return 0

    if operation == "setStatus":
        print(store.setStatus(rest[0], rest[1]).status)

        return 0

    if operation == "hold":
        # Hold the write lock without changing anything, which is what lets a test observe another process waiting on it.
        with config.exclusiveLock():
            print("held", flush=True)
            time.sleep(float(rest[0]))

        return 0

    raise ValueError(f"Unknown operation '{operation}'.")


# MARK: Main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
