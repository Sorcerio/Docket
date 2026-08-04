"""
Packaging Tests

Verify the package imports, that both console script entry points are callable, that every surface reports one version, and that the built artifacts carry what they should.
"""

# MARK: Imports

import asyncio
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import InitializeResult

import docket
from docket import cli, server

# MARK: Constants

# A handshake that has not answered by now is hung, and a hung test is worse than a failing one.
HANDSHAKE_TIMEOUT: float = 30.0

# The repository root, two levels up from this file.
REPO_ROOT: Path = Path(__file__).resolve().parent.parent

# Files the package ships that are not Python, so no import failure would ever reveal them missing.
PACKAGE_DATA_FILES: tuple[str, ...] = (
    "py.typed",
    "templates/CLAUDE.md",
    "templates/docket.toml",
)

# Directories that must never reach the source distribution, because they are development state rather than source.
SDIST_FORBIDDEN: tuple[str, ...] = (
    "docs",
    ".claude",
    ".videos",
    "uv.lock",
    "main.py",
)

# MARK: Functions


def testVersionIsExposed(capsys: pytest.CaptureFixture[str]) -> None:
    """
    The package exposes a version string that the CLI reports back.
    """

    assert docket.__version__

    # `--version` exits zero through `SystemExit`, which is argparse's contract.
    with pytest.raises(SystemExit) as excInfo:
        cli.main(["--version"])

    assert excInfo.value.code == 0
    assert docket.__version__ in capsys.readouterr().out


def testServerReportsTheSameVersion() -> None:
    """
    The MCP server advertises the package version rather than an empty one.

    `MCPServer` defaults `version` to the empty string and reports that to a client, so this asserts the constructor is still handed the real one.
    """

    assert server.mcp.version == docket.__version__


def testCliWithNoCommandIsAUsageError() -> None:
    """
    Invoking the CLI with no subcommand prints help and reports a usage error.
    """

    assert cli.main([]) == 2


def testServerEntryPointResolves() -> None:
    """
    The `docket-mcp` entry point exists and is callable.

    It is not invoked here, because calling it hands this process to the stdio transport and blocks on stdin. `testHandshakeAdvertisesThePackageVersion` runs it for real in a subprocess instead.
    """

    assert callable(server.main)


def testHandshakeAdvertisesThePackageVersion() -> None:
    """
    A real client connecting over stdio is told the package version.

    Asserting the attribute in this process proves the constructor was handed the right string, and nothing more. This spawns the server, speaks the protocol to it, and reads the version back off the wire, which is the only place the mistake this test exists to catch could actually show up.
    """

    result: InitializeResult = asyncio.run(_initializeOverStdio())

    assert result.server_info.name == server.SERVER_NAME
    assert result.server_info.version == docket.__version__

    # The instructions are what an agent reads before its first call, so a handshake that drops them is a broken one.
    assert result.instructions == server.SERVER_INSTRUCTIONS


@pytest.mark.parametrize("relativePath", PACKAGE_DATA_FILES)
def testPackageDataFilesAreShipped(relativePath: str) -> None:
    """
    Every non-Python file the package depends on sits inside the package directory.

    Anything outside `src/docket` is left behind by the wheel build, and `deploy` would then fail only once installed rather than in the test suite.

    relativePath: A path inside the package directory, relative to it.
    """

    assert (REPO_ROOT / "src" / "docket" / relativePath).is_file()


def testSdistShipsSourceAndItsVerification() -> None:
    """
    The source distribution carries the source, the tests, and the scripts the tests reach for.

    `tests/test_bumpVersion.py` loads `scripts/bumpVersion.py` by path, so dropping the scripts would leave an unpacked sdist unable to run its own suite.
    """

    include: list[str] = _readSdistInclude()

    for required in ("src", "tests", "scripts", "README.md", "LICENSE", "pyproject.toml"):
        assert required in include


@pytest.mark.parametrize("entry", SDIST_FORBIDDEN)
def testSdistExcludesDevelopmentState(entry: str) -> None:
    """
    Development state stays out of the source distribution.

    Hatchling ships every tracked file unless told otherwise, which would publish the demo recording, the ticket board, and the agent configuration to an index that never forgets a release.

    entry: A path that must not appear in the include list.
    """

    assert entry not in _readSdistInclude()


def _readSdistInclude() -> list[str]:
    """
    Read the source distribution include list out of `pyproject.toml`.

    Returns the configured include entries.
    """

    with (REPO_ROOT / "pyproject.toml").open("rb") as file:
        configuration: dict[str, Any] = tomllib.load(file)

    return configuration["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]


async def _initializeOverStdio() -> InitializeResult:
    """
    Start the server in a subprocess and complete one MCP handshake against it.

    The module is run rather than the `docket-mcp` script, so the test does not depend on console scripts having been installed, and `main` is still the entry point either way.

    Returns the initialize result the server sent back.
    """

    parameters: StdioServerParameters = StdioServerParameters(command=sys.executable, args=["-m", "docket.server"])

    async with stdio_client(parameters) as (readStream, writeStream):
        async with ClientSession(readStream, writeStream, read_timeout_seconds=HANDSHAKE_TIMEOUT) as session:
            return await session.initialize()
