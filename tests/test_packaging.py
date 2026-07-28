"""
Packaging Tests

Verify the package imports, that both console script entry points are callable, and that every surface reports one version.
"""

# MARK: Imports

import pytest

import docket
from docket import cli, server

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
    The MCP server advertises the package version rather than the `mcp` library's.

    `FastMCP` forwards no version to the lowlevel server it wraps, which falls back to reporting its own package's version, so this asserts the assignment that corrects it is still in place.
    """

    assert server.mcp._mcp_server.version == docket.__version__


def testCliWithNoCommandIsAUsageError() -> None:
    """
    Invoking the CLI with no subcommand prints help and reports a usage error.
    """

    assert cli.main([]) == 2


def testServerEntryPointResolves() -> None:
    """
    The `docket-mcp` entry point exists and is callable.

    It is not invoked here, because calling it hands the process to the stdio transport and blocks on stdin.
    """

    assert callable(server.main)
