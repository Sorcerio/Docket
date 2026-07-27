"""
Packaging Tests

Verify the package imports and that both console script entry points are callable.
"""

# MARK: Imports

import pytest

import docket
from docket import cli, server

# MARK: Functions


def testVersionIsExposed() -> None:
    """
    The package exposes a version string that matches what the CLI reports.
    """

    assert docket.__version__

    # `--version` exits zero through `SystemExit`, which is argparse's contract.
    with pytest.raises(SystemExit) as excInfo:
        cli.main(["--version"])

    assert excInfo.value.code == 0


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
