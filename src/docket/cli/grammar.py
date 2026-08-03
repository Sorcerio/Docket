"""
Docket CLI Grammar

The vocabulary the CLI accepts, and the exit codes it answers with.

This is the shape of the interface and nothing behind it. The parser lives here, along with the small parsers for the values individual arguments carry.
"""

# MARK: Imports

import argparse
from typing import Optional

from rich_argparse import RichHelpFormatter

from docket import __version__
from docket.core.config import Config, discoverConfig
from docket.core.errors import DocketError, InvalidIdError
from docket.core.ticket import STATUSES

# MARK: Constants

# The program name used in help output and error messages.
PROGRAM_NAME: str = "docket"

# Exit codes, distinguishing a set that failed validation from a command that could not run at all.
EXIT_OK: int = 0
EXIT_INVALID: int = 1
EXIT_USAGE: int = 2

# The word that clears a comma-separated list argument. An id can never collide with it, since every id is an uppercase key followed by a hyphen and a number.
CLEAR_SENTINEL: str = "none"

# How the graph destination is named when a message has to talk about it.
OUT_ARGUMENT: str = "--out path"

# MARK: Functions


def describeKeys(config: Optional[Config]) -> str:
    """
    Describe the keys an argument accepts, for appending to its help text.

    The registry is per-repository, so the options can only be named once a configuration has been found. Without one the description stays general rather than guessing.

    config: The configuration holding the registry, or `None` when none was found.

    Returns the sentence to append.
    """

    if config is None:
        return "Must be registered."

    registered: str = ", ".join(sorted(config.registeredKeys))

    # A registry with nothing in it is a real state after a fresh deploy, so name it rather than printing an empty list.
    return f"One of: {registered}." if registered else "None are registered yet. Add one with 'docket key add'."


def describePriorities(config: Optional[Config]) -> str:
    """
    Describe the priorities an argument accepts, for appending to its help text.

    The band runs from 0 through the configured `maxPriority`, so like the key registry it can only be listed once a configuration has been found.

    config: The configuration holding the band, or `None` when none was found.

    Returns the sentence to append.
    """

    if config is None:
        return "0 is most urgent."

    return f"One of: {', '.join(str(priority) for priority in range(config.maxPriority + 1))}. 0 is most urgent."


def tryDiscoverConfig() -> Optional[Config]:
    """
    Load the configuration governing the current directory, without insisting that one exists.

    Only the help text depends on this, and every command that truly needs a configuration discovers it again through `dispatch`, so a missing one must not stop the parser from being built. That is what keeps `--help`, `--version`, and `deploy` working outside a repository.

    Returns the loaded `Config`, or `None` when none could be loaded.
    """

    try:
        return discoverConfig()
    except DocketError:
        return None


def buildParser(config: Optional[Config] = None) -> argparse.ArgumentParser:
    """
    Build the top-level argument parser and every subcommand parser.

    config: The configuration whose keys and priority band the help text names, or `None` to describe both in general terms.

    Returns the configured `argparse.ArgumentParser`.
    """

    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog=PROGRAM_NAME,
        description="A per-repo ticketing system that is plain markdown for humans and structured MCP for agents.",
        formatter_class=RichHelpFormatter,
    )
    parser.add_argument("-V", "--version", action="version", version=f"{PROGRAM_NAME} {__version__}")

    commands = parser.add_subparsers(dest="command", metavar="COMMAND")

    # Name the discrete options once, since every argument that takes a key or a priority describes the same set.
    keyOptions: str = describeKeys(config)
    priorityOptions: str = describePriorities(config)

    # Creating a ticket, which allocates the id and freezes the filename.
    newParser: argparse.ArgumentParser = commands.add_parser("new", help="Create a ticket.", formatter_class=RichHelpFormatter)
    newParser.add_argument("-k", "--key", required=True, help=f"The key to mint under. {keyOptions}")
    newParser.add_argument("-t", "--title", required=True, help="The ticket title. The filename slug derives from this once, here.")
    newParser.add_argument("-r", "--requires", help="Comma-separated ids this ticket depends on.")
    newParser.add_argument("-p", "--priority", type=int, help=f"Priority, defaulting to the configured defaultPriority. {priorityOptions}")
    newParser.add_argument("-b", "--body", help="Prose for the body, placed under a heading built from the title.")

    showParser: argparse.ArgumentParser = commands.add_parser("show", help="Show a ticket with its resolved dependency context.", formatter_class=RichHelpFormatter)
    showParser.add_argument("id", help="The ticket id.")

    listParser: argparse.ArgumentParser = commands.add_parser("list", help="List ticket summaries.", formatter_class=RichHelpFormatter)
    listParser.add_argument("-s", "--status", choices=STATUSES, help="Keep only tickets with this status.")
    listParser.add_argument("-k", "--key", help=f"Keep only tickets carrying this key. {keyOptions}")
    listParser.add_argument("-m", "--priority-max", type=int, dest="priorityMax", help=f"Keep only tickets at or below this priority number. {priorityOptions}")

    setParser: argparse.ArgumentParser = commands.add_parser("set", help="Change a ticket's title, priority, or dependencies.", formatter_class=RichHelpFormatter)
    setParser.add_argument("id", help="The ticket id.")
    setParser.add_argument("-t", "--title", help="A new title. The filename does not follow it, since filenames are frozen at creation.")
    setParser.add_argument("-p", "--priority", type=int, help=f"A new priority. {priorityOptions}")
    setParser.add_argument("-r", "--requires", help=f"A replacement comma-separated dependency list. Pass '{CLEAR_SENTINEL}' to clear it.")
    setParser.add_argument("-ra", "--requires-add", dest="requiresAdd", help="Comma-separated ids to append to the existing dependency list, leaving the rest of it alone.")
    setParser.add_argument("-rr", "--requires-remove", dest="requiresRemove", help="Comma-separated ids to drop from the existing dependency list, leaving the rest of it alone.")

    statusParser: argparse.ArgumentParser = commands.add_parser("status", help="Change a ticket's status, moving its file to match.", formatter_class=RichHelpFormatter)
    statusParser.add_argument("id", help="The ticket id.")
    statusParser.add_argument("status", choices=STATUSES, help="The new status.")

    metaParser: argparse.ArgumentParser = commands.add_parser("meta", help="Inspect and manage a ticket's metadata map.", formatter_class=RichHelpFormatter)
    metaCommands = metaParser.add_subparsers(dest="metaCommand", metavar="SUBCOMMAND")

    metaGetParser: argparse.ArgumentParser = metaCommands.add_parser("get", help="Show a ticket's metadata.", formatter_class=RichHelpFormatter)
    metaGetParser.add_argument("id", help="The ticket id.")

    metaSetParser: argparse.ArgumentParser = metaCommands.add_parser("set", help="Set or clear one metadata key.", formatter_class=RichHelpFormatter)
    metaSetParser.add_argument("id", help="The ticket id.")
    metaSetParser.add_argument("key", help="The metadata key. Namespace it, for example 'video', so it cannot collide with another tool's key.")
    metaSetParser.add_argument("value", nargs="?", help="The value to store. Omit with -c/--clear to remove the key instead.")
    metaSetParser.add_argument("-c", "--clear", action="store_true", help="Remove the key instead of setting it.")

    graphParser: argparse.ArgumentParser = commands.add_parser("graph", help="Render the dependency graph as mermaid source.", formatter_class=RichHelpFormatter)
    graphScope = graphParser.add_mutually_exclusive_group()
    graphScope.add_argument("-i", "--id", help="Scope to one ticket's ancestors and descendants.")
    graphScope.add_argument("-k", "--key", help=f"Scope to one key, plus its immediate cross-key neighbors. {keyOptions}")
    graphParser.add_argument("-o", "--out", help="Write to a file rather than to stdout.")

    keyParser: argparse.ArgumentParser = commands.add_parser("key", help="Inspect and manage the key registry.", formatter_class=RichHelpFormatter)
    keyCommands = keyParser.add_subparsers(dest="keyCommand", metavar="SUBCOMMAND")

    keyCommands.add_parser("list", help="List the registered keys.", formatter_class=RichHelpFormatter)

    keyAddParser: argparse.ArgumentParser = keyCommands.add_parser("add", help="Register a new key.", formatter_class=RichHelpFormatter)
    keyAddParser.add_argument("key", help="The key to add.")
    keyAddParser.add_argument("description", help="What the key groups.")
    keyAddParser.add_argument("-r", "--rationale", help="Why the key was added, written as a comment above it.")

    keyRemoveParser: argparse.ArgumentParser = keyCommands.add_parser("remove", help="Remove a key no ticket uses.", formatter_class=RichHelpFormatter)
    keyRemoveParser.add_argument("key", help=f"The key to remove. {keyOptions}")

    commands.add_parser("validate", help="Run every integrity rule.", formatter_class=RichHelpFormatter)

    deployParser: argparse.ArgumentParser = commands.add_parser("deploy", help="Install docket into a repository.", formatter_class=RichHelpFormatter)
    deployParser.add_argument("path", help="The repository root to deploy into.")

    upgradeParser: argparse.ArgumentParser = commands.add_parser("upgrade", help="Refresh the deployed templates in a repository.", formatter_class=RichHelpFormatter)
    upgradeParser.add_argument("path", help="The repository root to upgrade.")

    return parser


def parseIdList(value: Optional[str]) -> Optional[list[str]]:
    """
    Split a comma-separated id list.

    Both `none` and an empty string yield an empty list rather than `None`, which is how `set --requires` clears a ticket's dependencies. The sentinel exists because PowerShell discards an empty-string argument before the process ever sees it, leaving the documented empty-string form unreachable on Windows.

    value: The raw argument value.

    Returns the ids, or `None` when the argument was absent.
    """

    if value is None:
        return None

    entries: list[str] = [entry.strip() for entry in value.split(",") if entry.strip()]

    # The sentinel clears the whole list, so mixing it with real ids asks for two contradictory things at once.
    if any(entry.lower() == CLEAR_SENTINEL for entry in entries):
        if len(entries) > 1:
            raise InvalidIdError(f"'{CLEAR_SENTINEL}' clears the whole list, so it cannot be combined with an id. Pass either '{CLEAR_SENTINEL}' alone or only ids.")

        return []

    return entries


def parseEditIdList(value: Optional[str], flag: str) -> Optional[list[str]]:
    """
    Split a comma-separated id list for an argument that edits a list rather than replacing one.

    Clearing is what `--requires` is for, so an empty result here means the caller named an edit and then named nothing to do, which is a usage error rather than a silent no-op.

    value: The raw argument value.
    flag: The flag the value came from, named in the error.

    Returns the ids, or `None` when the argument was absent.
    """

    entries: Optional[list[str]] = parseIdList(value)

    if entries is not None and not entries:
        raise InvalidIdError(f"'{flag}' needs at least one id. Use '--requires {CLEAR_SENTINEL}' to clear the list instead.")

    return entries
