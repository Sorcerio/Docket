"""
Docket CLI

Argument parsing and command dispatch, a thin shell over `docket.core`.

This holds no rules of its own. Every decision belongs to the core, so the CLI and the MCP server can never disagree about one.
"""

# MARK: Imports

import argparse
import sys
from typing import Optional

from docket.cli.commands import (
    commandDeploy,
    commandGraph,
    commandKey,
    commandList,
    commandMeta,
    commandNew,
    commandSet,
    commandShow,
    commandStatus,
    commandValidate,
)
from docket.cli.grammar import (
    CLEAR_SENTINEL,
    EXIT_INVALID,
    EXIT_OK,
    EXIT_USAGE,
    OUT_ARGUMENT,
    PROGRAM_NAME,
    buildParser,
    describeKeys,
    describePriorities,
    parseEditIdList,
    parseIdList,
    tryDiscoverConfig,
)
from docket.cli.output import STATUS_STYLES, Output, buildContextTable, relativeToRoot
from docket.core.config import Config, discoverConfig
from docket.core.errors import DocketError
from docket.core.store import Store

# MARK: Constants

# `docket.cli` was one module before it was a package, and it is what `pyproject.toml` names as the console script. Everything the outside world reached for then is still reachable by the same path.
__all__: list[str] = [
    "CLEAR_SENTINEL",
    "EXIT_INVALID",
    "EXIT_OK",
    "EXIT_USAGE",
    "OUT_ARGUMENT",
    "PROGRAM_NAME",
    "STATUS_STYLES",
    "Output",
    "buildContextTable",
    "buildParser",
    "commandDeploy",
    "commandGraph",
    "commandKey",
    "commandList",
    "commandMeta",
    "commandNew",
    "commandSet",
    "commandShow",
    "commandStatus",
    "commandValidate",
    "describeKeys",
    "describePriorities",
    "dispatch",
    "main",
    "parseEditIdList",
    "parseIdList",
    "relativeToRoot",
    "tryDiscoverConfig",
]

# MARK: Functions


def main(argv: Optional[list[str]] = None) -> int:
    """
    Entry point for the `docket` console script.

    argv: Argument list to parse, defaulting to `sys.argv[1:]`.

    Returns the process exit code.
    """

    # Read the configuration before the parser is built, so the help text can name the keys and priorities this repository actually allows. A missing one is not fatal here, since the commands that need it say so themselves.
    config: Optional[Config] = tryDiscoverConfig()

    parser: argparse.ArgumentParser = buildParser(config)
    args: argparse.Namespace = parser.parse_args(argv)
    output: Output = Output()

    # With no subcommand there is nothing to dispatch, so show help and report a usage error.
    if args.command is None:
        parser.print_help()
        return EXIT_USAGE

    # Every core failure surfaces here as a message and an exit code, which is the whole of the CLI's error handling.
    try:
        return dispatch(args, config, output)
    except DocketError as error:
        output.error(str(error))
        return EXIT_USAGE


def dispatch(args: argparse.Namespace, config: Optional[Config], output: Output) -> int:
    """
    Route parsed arguments to the command that handles them.

    args: The parsed arguments.
    config: The configuration already discovered for the help text, or `None` when none was found.
    output: Where to write.

    Returns the process exit code.
    """

    # Deploy and upgrade run before a configuration exists, or in order to repair one, so they must not require discovering it first.
    if args.command in ("deploy", "upgrade"):
        return commandDeploy(args, output)

    # Every other command works against the configuration governing the current directory. Discovery is repeated when the parser was built without one, so the reason it could not be found is reported by the code that knows it.
    store: Store = Store(config if config is not None else discoverConfig())

    handlers = {
        "new": commandNew,
        "show": commandShow,
        "list": commandList,
        "set": commandSet,
        "status": commandStatus,
        "meta": commandMeta,
        "graph": commandGraph,
        "key": commandKey,
        "validate": commandValidate,
    }

    return handlers[args.command](args, store, output)


# MARK: Main

if __name__ == "__main__":
    sys.exit(main())
