"""
Docket CLI

Argument parsing and command dispatch, a thin shell over `docket.core`.
"""

# MARK: Imports

import argparse
import sys
from typing import Optional

from rich_argparse import RichHelpFormatter

from docket import __version__

# MARK: Constants

# The program name used in help output and error messages.
PROGRAM_NAME: str = "docket"

# MARK: Functions


def buildParser() -> argparse.ArgumentParser:
    """
    Build the top-level argument parser and every subcommand parser.

    Returns the configured `argparse.ArgumentParser`.
    """

    # Build the root parser with the rich formatter so help output is styled.
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog=PROGRAM_NAME,
        description="A per-repo ticketing system that is plain markdown for humans and structured MCP for agents.",
        formatter_class=RichHelpFormatter,
    )

    # Expose the version, which is the only flag wired up before the commands land.
    parser.add_argument("--version", action="version", version=f"{PROGRAM_NAME} {__version__}")

    # Reserve the subcommand slot so later phases attach commands to a stable parser.
    parser.add_subparsers(dest="command", metavar="COMMAND")

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """
    Entry point for the `docket` console script.

    argv: Argument list to parse, defaulting to `sys.argv[1:]`.

    Returns the process exit code.
    """

    # Parse the arguments against the assembled parser.
    parser: argparse.ArgumentParser = buildParser()
    args: argparse.Namespace = parser.parse_args(argv)

    # With no subcommand there is nothing to dispatch, so show help and report a usage error.
    if args.command is None:
        parser.print_help()
        return 2

    return 0


# MARK: Main

if __name__ == "__main__":
    sys.exit(main())
