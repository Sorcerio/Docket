"""
Test Fixtures

Shared fixtures building throwaway consumer repositories on disk.
"""

# MARK: Imports

from pathlib import Path

import pytest

from docket.core.config import Config, loadConfig

# MARK: Constants

# A configuration carrying comments and a deliberately non-alphabetical key order, so round-trip tests have something to lose.
SAMPLE_CONFIG: str = """\
# Docket configuration for the test repository.
root = "docs/tickets"
todoDir = "todo"
doneDir = "done"
defaultPriority = 2
maxPriority = 4

[keys]
# The engine itself.
CORE = "tactical-sim core"
GEN = "map generation"
HEAD = "Godot frontend and seam"
# The strategic layer is a distinct area.
META = "campaign and progression"
"""

# MARK: Fixtures


@pytest.fixture
def repoDir(tmp_path: Path) -> Path:
    """
    Build a directory that looks like a deployed consumer repository.

    tmp_path: The pytest-provided temporary directory.

    Returns the repository root.
    """

    # A `.git` entry marks the boundary the configuration walk must stop at.
    (tmp_path / ".git").mkdir()

    # Lay out the ticket directories the store expects.
    (tmp_path / "docs" / "tickets" / "todo").mkdir(parents=True)
    (tmp_path / "docs" / "tickets" / "done").mkdir(parents=True)

    # Write the configuration with its comments intact.
    (tmp_path / ".docket.toml").write_text(SAMPLE_CONFIG, encoding="utf-8", newline="\n")

    return tmp_path


@pytest.fixture
def config(repoDir: Path) -> Config:
    """
    Load the configuration from a throwaway repository.

    repoDir: The repository root fixture.

    Returns the loaded `Config`.
    """

    return loadConfig(repoDir / ".docket.toml")
