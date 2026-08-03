"""
Packaging Tests

Verify the package imports, that both console script entry points are callable, and that every surface reports one version.
"""

# MARK: Imports

import asyncio
import sys

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import InitializeResult

import docket
from docket import cli, server

# MARK: Constants

# A handshake that has not answered by now is hung, and a hung test is worse than a failing one.
HANDSHAKE_TIMEOUT: float = 30.0

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
