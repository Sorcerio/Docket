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
from docket.core.errors import ConflictingArgumentsError, DocketError, InvalidArgumentError, InvalidIdError
from docket.core.handoff import HANDOFF_FILENAME
from docket.core.ids import isValidId, isValidKey
from docket.core.roadmap import ROADMAP_FILENAME
from docket.core.ticket import STATUSES

# MARK: Constants

# The program name used in help output and error messages.
PROGRAM_NAME: str = "docket"

# Exit codes, distinguishing a set that failed validation from a command that could not run at all.
EXIT_OK: int = 0
EXIT_INVALID: int = 1
EXIT_USAGE: int = 2

# The name the one-ticket branch is registered under. It is a placeholder rather than a word, because what reaches it is a ticket id and never this string. Registering it anyway is what lets `argparse` describe the branch in help and name it in an error, instead of it being an undocumented trick.
TICKET_COMMAND: str = "<ID>"

# What a bare positional token can be read as. Every class is decided by the token's own shape, and no token can fall into two, since an id carries a hyphen and a number, a key is uppercase, a status is one of a fixed lowercase set, and a priority is digits.
TOKEN_ID: str = "id"
TOKEN_KEY: str = "key"
TOKEN_STATUS: str = "status"
TOKEN_PRIORITY: str = "priority"

# The word that clears a comma-separated list argument. An id can never collide with it, since every id is an uppercase key followed by a hyphen and a number.
CLEAR_SENTINEL: str = "none"

# The commands that print one thing about a ticket and nothing else, for a pipe to read, each with its help text. The name is the subcommand that reaches it and the key `commands` looks its reader up by, so this one table is the whole vocabulary of reads.
ACCESSORS: dict[str, str] = {
    "title": "Print the ticket's title.",
    "status": "Print the ticket's status.",
    "priority": "Print the ticket's priority.",
    "requires": "Print the ids this ticket depends on, one per line. Prints nothing when there are none.",
    "required-by": "Print the ids of the tickets depending on this one, one per line. Prints nothing when there are none.",
    "key": "Print the key portion of the ticket's id and nothing else.",
    "ready": "Print whether every dependency is done, as a bare true or false.",
    "body": "Print the ticket's body as raw Markdown, with no frontmatter. Prints nothing when it is empty.",
}

# The command that reads each frontmatter field. `id` has none, since it is what was typed to reach the ticket, and `metadata` is read through `meta` because that command also writes it. A field missing from here fails the suite, which is what keeps a new field from arriving without a way to read it.
FIELD_ACCESSORS: dict[str, Optional[str]] = {
    "id": None,
    "title": "title",
    "status": "status",
    "priority": "priority",
    "requires": "requires",
    "metadata": "meta",
}

# How a destination is named when a message has to talk about it. The graph and the shipped documents share the flag, so they share its name too.
OUTPUT_ARGUMENT: str = "--output path"

# MARK: Functions


def describeKeys(config: Optional[Config]) -> str:
    """
    Describe the keys an argument accepts, for appending to its help text.

    The registry is per-repository, so the options can only be named once a configuration has been found. Without one the description stays general rather than guessing.

    Args:
        config: The configuration holding the registry, or `None` when none was found.

    Returns:
        The sentence to append.
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

    Args:
        config: The configuration holding the band, or `None` when none was found.

    Returns:
        The sentence to append.
    """

    if config is None:
        return "0 is most urgent."

    return f"One of: {', '.join(str(priority) for priority in range(config.maxPriority + 1))}. 0 is most urgent."


def tryDiscoverConfig() -> Optional[Config]:
    """
    Load the configuration governing the current directory, without insisting that one exists.

    Only the help text depends on this, and every command that truly needs a configuration discovers it again through `dispatch`, so a missing one must not stop the parser from being built. That is what keeps `--help`, `--version`, and `deploy` working outside a repository.

    Returns:
        The loaded `Config`, or `None` when none could be loaded.
    """

    try:
        return discoverConfig()
    except DocketError:
        return None


def classifyToken(token: str) -> Optional[str]:
    """
    Decide what a bare positional token names, from its shape alone.

    This is the whole of the rule that lets `docket list todo CORE 1` and `docket graph CORE-14` be written without a flag between them. The four classes cannot overlap, so no token is ever ambiguous and no ordering between the checks changes an answer.

    Args:
        token: The token to read.

    Returns:
        One of the `TOKEN_` names, or `None` when the token is none of them.
    """

    if isValidId(token):
        return TOKEN_ID

    if isValidKey(token):
        return TOKEN_KEY

    if token in STATUSES:
        return TOKEN_STATUS

    # A priority is a plain number, so a signed or decimal one is deliberately not a priority.
    if token.isdigit():
        return TOKEN_PRIORITY

    return None


def rewriteIdFirst(argv: list[str]) -> list[str]:
    """
    Rewrite an invocation that opens with a ticket id into the branch that handles one.

    `docket CORE-14 done` is the shape a person types, and `argparse` cannot express "a subcommand, or else an id". It does not have to, because the two are distinguishable before parsing begins: every command name is lowercase and every id is an uppercase key followed by a hyphen and a number. So naming the branch is all this does, and the parser is left to do the rest, including the help and every error.

    Args:
        argv: The raw argument list.

    Returns:
        The list to parse, unchanged when it does not open with an id.
    """

    if not argv or not isValidId(argv[0]):
        return argv

    return [TICKET_COMMAND, *argv]


def resolveListFilters(tokens: list[str], status: Optional[str], key: Optional[str], priorityMax: Optional[int]) -> tuple[Optional[str], Optional[str], Optional[int]]:
    """
    Resolve `list`'s filters from its bare tokens and its flags together.

    A token says which filter it is by its own shape, so `docket list todo CORE 1` needs no flags at all. The flags remain for scripts and for anyone who would rather be explicit, and naming one filter twice is refused rather than quietly resolved in whichever direction the code happens to read.

    Args:
        tokens: The bare filter tokens, in any order.
        status: The status named by `--status`, or `None`.
        key: The key named by `--key`, or `None`.
        priorityMax: The ceiling named by `--priority-max`, or `None`.

    Returns:
        The resolved `(status, key, priorityMax)` triple.

    Raises:
        InvalidArgumentError: '{token}' is a ticket id, which does not filter a list. Show it with '{PROGRAM_NAME} {token}'.
        ConflictingArgumentsError: The {kind} filter was given twice, the second time as '{token}'. Pass it once.
    """

    # Held as text so one loop can fill any of the three, then converted back on the way out.
    resolved: dict[str, Optional[str]] = {
        TOKEN_STATUS: status,
        TOKEN_KEY: key,
        TOKEN_PRIORITY: None if priorityMax is None else str(priorityMax),
    }

    for token in tokens:
        kind: Optional[str] = classifyToken(token)

        # An id is a whole other command rather than a filter, so name that command instead of calling the token unreadable.
        if kind == TOKEN_ID:
            raise InvalidArgumentError(f"'{token}' is a ticket id, which does not filter a list. Show it with '{PROGRAM_NAME} {token}'.")

        if kind is None:
            raise InvalidArgumentError(f"Cannot read '{token}' as a filter. Expected a status ({', '.join(STATUSES)}), a key, or a priority number.")

        if resolved[kind] is not None:
            raise ConflictingArgumentsError(f"The {kind} filter was given twice, the second time as '{token}'. Pass it once.")

        resolved[kind] = token

    ceiling: Optional[str] = resolved[TOKEN_PRIORITY]

    return resolved[TOKEN_STATUS], resolved[TOKEN_KEY], None if ceiling is None else int(ceiling)


def resolveGraphScope(scope: Optional[str], ticketId: Optional[str], key: Optional[str], status: Optional[str]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Resolve the graph's scope from its bare token and its flags together.

    An id, a key, and a status are told apart by shape, which is what makes `docket graph CORE-14`, `docket graph GEN`, and `docket graph todo` all unambiguous. The flags stay for the explicit form, and combining the two spellings is refused, since `argparse` can enforce that the flags exclude each other but cannot reach across to a positional.

    The three scopes remain exclusive rather than composing. A graph is scoped to one thing, and narrowing an already narrowed graph is what `list`'s filters are for.

    Args:
        scope: The bare scope token, or `None`.
        ticketId: The id named by `--id`, or `None`.
        key: The key named by `--key`, or `None`.
        status: The status named by `--status`, or `None`.

    Returns:
        The resolved `(id, key, status)` triple, at most one of which is set.

    Raises:
        ConflictingArgumentsError: '{scope}' already scopes the graph, so it cannot be combined with -i/--id, -k/--key, or -s/--status.
        InvalidArgumentError: Cannot read '{scope}' as a scope. Expected a ticket id, for example 'CORE-14', a key, or a status ({', '.join(STATUSES)}).
    """

    if scope is None:
        return ticketId, key, status

    if ticketId is not None or key is not None or status is not None:
        raise ConflictingArgumentsError(f"'{scope}' already scopes the graph, so it cannot be combined with -i/--id, -k/--key, or -s/--status.")

    kind: Optional[str] = classifyToken(scope)

    if kind == TOKEN_ID:
        return scope, None, None

    if kind == TOKEN_KEY:
        return None, scope, None

    if kind == TOKEN_STATUS:
        return None, None, scope

    raise InvalidArgumentError(f"Cannot read '{scope}' as a scope. Expected a ticket id, for example 'CORE-14', a key, or a status ({', '.join(STATUSES)}).")


def buildParser(config: Optional[Config] = None) -> argparse.ArgumentParser:
    """
    Build the top-level argument parser and every subcommand parser.

    Args:
        config: The configuration whose keys and priority band the help text names, or `None` to describe both in general terms.

    Returns:
        The configured `argparse.ArgumentParser`.
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

    buildTicketParser(commands, priorityOptions)

    # Creating a ticket, which allocates the id and freezes the filename. The key and the title are positional because both are required, and a required flag is a flag that should have been an argument.
    newParser: argparse.ArgumentParser = commands.add_parser("new", help="Create a ticket.", formatter_class=RichHelpFormatter)
    newParser.add_argument("key", metavar="KEY", help=f"The key to mint under. {keyOptions}")
    newParser.add_argument("title", metavar="TITLE", help="The ticket title. The filename slug derives from this once, here.")
    newParser.add_argument("-r", "--requires", help="Comma-separated ids this ticket depends on.")
    newParser.add_argument("-p", "--priority", type=int, help=f"Priority, defaulting to the configured defaultPriority. {priorityOptions}")
    newParser.add_argument("-b", "--body", help="Prose for the body, placed under a heading built from the title.")

    listParser: argparse.ArgumentParser = commands.add_parser("list", help="List ticket summaries.", formatter_class=RichHelpFormatter)
    listParser.add_argument("filters", nargs="*", metavar="FILTER", help=f"Filters in any order, each read from its own shape: a status ({', '.join(STATUSES)}), a key, or a priority ceiling. The flags below are the same three, named explicitly.")
    listParser.add_argument("-s", "--status", choices=STATUSES, help="Keep only tickets with this status.")
    listParser.add_argument("-k", "--key", help=f"Keep only tickets carrying this key. {keyOptions}")
    listParser.add_argument("-m", "--priority-max", type=int, dest="priorityMax", help=f"Keep only tickets at or below this priority number. {priorityOptions}")
    listParser.add_argument("-r", "--ready", action="store_true", help="Keep only tickets whose dependencies are all done. A done ticket is never ready, so this never shows one.")

    graphParser: argparse.ArgumentParser = commands.add_parser("graph", help="Render the dependency graph as mermaid source.", formatter_class=RichHelpFormatter)
    addScopeArguments(graphParser, keyOptions)
    graphParser.add_argument("-o", "--output", help="Write to a file rather than to stdout.")

    keyParser: argparse.ArgumentParser = commands.add_parser("key", help="Inspect and manage the key registry.", formatter_class=RichHelpFormatter)
    keyCommands = keyParser.add_subparsers(dest="keyCommand", metavar="SUBCOMMAND")

    keyCommands.add_parser("list", help="List the registered keys.", formatter_class=RichHelpFormatter)

    keyAddParser: argparse.ArgumentParser = keyCommands.add_parser("add", help="Register a new key.", formatter_class=RichHelpFormatter)
    keyAddParser.add_argument("key", help="The key to add.")
    keyAddParser.add_argument("description", help="What the key groups.")
    keyAddParser.add_argument("-r", "--rationale", help="Why the key was added, written as a comment above it.")

    keyRemoveParser: argparse.ArgumentParser = keyCommands.add_parser("remove", help="Remove a key no ticket uses.", formatter_class=RichHelpFormatter)
    keyRemoveParser.add_argument("key", help=f"The key to remove. {keyOptions}")

    # Documents docket ships, rendered against this repository. This is a group rather than a bare command because each one is read somewhere else, and more than one such document was always plausible.
    docsParser: argparse.ArgumentParser = commands.add_parser("docs", help="Write a document docket ships, rendered for this repository.", formatter_class=RichHelpFormatter)
    docsCommands = docsParser.add_subparsers(dest="docsCommand", metavar="SUBCOMMAND")

    # Every document reaches its reader the same way, so the destination is declared once here and inherited by each one rather than repeated per document. A document is a file by default, unlike `graph`, because it is written to be kept and read later rather than piped into something else.
    docsOutput: argparse.ArgumentParser = argparse.ArgumentParser(add_help=False)
    docsOutput.add_argument("-o", "--output", help="Write to this file instead of the one the document is named for.")
    docsOutput.add_argument("-p", "--print", dest="toPrint", action="store_true", help="Print to stdout instead of writing the file. Combined with -o/--output it does both, writing the file and printing it.")

    docsCommands.add_parser(
        "handoff",
        help=f"Write the brief that teaches a chat system with no access to this repository how to write tickets for it by hand. Lands in {HANDOFF_FILENAME}.",
        parents=[docsOutput],
        formatter_class=RichHelpFormatter,
    )

    roadmapParser: argparse.ArgumentParser = docsCommands.add_parser(
        "roadmap",
        help=f"Write the dependency graph as a markdown document with an embedded mermaid diagram, for committing alongside the tickets. Lands in {ROADMAP_FILENAME}.",
        parents=[docsOutput],
        formatter_class=RichHelpFormatter,
    )
    addScopeArguments(roadmapParser, keyOptions)
    roadmapParser.add_argument(
        "-m",
        "--max-nodes",
        type=int,
        dest="maxNodes",
        help="How many nodes to aim for, overriding the configured maxRoadmapNodes. Past it the completed tickets furthest from the work still open are dropped, and open tickets are never dropped. Pass 0 for no ceiling.",
    )

    commands.add_parser("validate", help="Run every integrity rule.", formatter_class=RichHelpFormatter)

    deployParser: argparse.ArgumentParser = commands.add_parser("deploy", help="Install docket into a repository.", formatter_class=RichHelpFormatter)
    deployParser.add_argument("path", help="The repository root to deploy into.")

    upgradeParser: argparse.ArgumentParser = commands.add_parser("upgrade", help="Refresh the deployed templates in a repository.", formatter_class=RichHelpFormatter)
    upgradeParser.add_argument("path", help="The repository root to upgrade.")

    return parser


def addScopeArguments(parser: argparse.ArgumentParser, keyOptions: str) -> None:
    """
    Add the three ways of scoping a graph to a parser, in both their bare and their explicit spelling.

    Both commands that draw a graph offer the same scopes, read by the same rules, and resolved by the same `resolveGraphScope`. Declaring them once is what keeps the two from drifting into disagreeing about what a bare token means.

    Args:
        parser: The parser to add the arguments to.
        keyOptions: The sentence describing the registered keys, already built.
    """

    parser.add_argument("scope", nargs="?", metavar="SCOPE", help=f"What to scope to, read from its own shape: a ticket id, a key, or a status ({', '.join(STATUSES)}). The flags below are the same three, named explicitly.")

    scopeGroup = parser.add_mutually_exclusive_group()
    scopeGroup.add_argument("-i", "--id", help="Scope to one ticket's ancestors and descendants.")
    scopeGroup.add_argument("-k", "--key", help=f"Scope to one key, plus its immediate cross-key neighbors. {keyOptions}")
    scopeGroup.add_argument("-s", "--status", choices=STATUSES, help="Scope to the tickets with this status alone. Nothing outside it is borrowed, so an edge survives only when both of its ends carry the status.")


def buildTicketParser(commands: argparse._SubParsersAction, priorityOptions: str) -> argparse.ArgumentParser:
    """
    Build the branch that works with one ticket, named by its id.

    `prog` is set to the program name alone, and the id is added before the subcommands, so `argparse` derives every child's usage line as `docket ID <command>`. That is exactly what was typed, rather than the placeholder the branch is registered under.

    Args:
        commands: The top-level subparser action to register into.
        priorityOptions: The sentence describing the priority band, already built.

    Returns:
        The branch parser.
    """

    ticketParser: argparse.ArgumentParser = commands.add_parser(
        TICKET_COMMAND,
        prog=PROGRAM_NAME,
        help="Work with one ticket. A bare id shows it, a status word sets it.",
        description="Work with the ticket named by ID. Status is the truth and the directory follows it, so setting a status may move the file.",
        formatter_class=RichHelpFormatter,
    )
    ticketParser.add_argument("id", metavar="ID", help="The ticket id, for example CORE-14.")

    # Not required, so a bare id parses and falls through to showing the ticket.
    ticketCommands = ticketParser.add_subparsers(dest="ticketCommand", metavar="COMMAND")

    # A bare id never reaches the show parser, so the ticket parser carries the default it would otherwise leave unset.
    ticketParser.set_defaults(plain=False)

    showParser: argparse.ArgumentParser = ticketCommands.add_parser("show", help="Show the ticket with its resolved dependency context. This is what a bare id does.", formatter_class=RichHelpFormatter)
    showParser.add_argument("--plain", action="store_true", help="Write the same content as bare text, with no styling and the body left as raw Markdown. Use `cat` for the raw file.")

    # Every read is registered from the one table, so a new one needs no parser code of its own.
    for accessor, accessorHelp in ACCESSORS.items():
        ticketCommands.add_parser(accessor, help=accessorHelp, formatter_class=RichHelpFormatter)

    # One parser per status is what makes 'docket CORE-14 done' work. It also puts the whole vocabulary into the error when a command is misspelled, which a single `choices` list on a value argument could not do.
    for status in STATUSES:
        ticketCommands.add_parser(status, help=f"Set the status to {status}.", formatter_class=RichHelpFormatter)

    setParser: argparse.ArgumentParser = ticketCommands.add_parser("set", help="Change the ticket's title, priority, or dependencies.", formatter_class=RichHelpFormatter)
    setParser.add_argument("-t", "--title", help="A new title. The filename does not follow it, since filenames are frozen at creation.")
    setParser.add_argument("-p", "--priority", type=int, help=f"A new priority. {priorityOptions}")
    setParser.add_argument("-r", "--requires", help=f"A replacement comma-separated dependency list. Pass '{CLEAR_SENTINEL}' to clear it.")
    setParser.add_argument("-ra", "--requires-add", dest="requiresAdd", help="Comma-separated ids to append to the existing dependency list, leaving the rest of it alone.")
    setParser.add_argument("-rr", "--requires-remove", dest="requiresRemove", help="Comma-separated ids to drop from the existing dependency list, leaving the rest of it alone.")

    # How much of the call was typed is what it means, the same way a status reads with no value and writes with one.
    metaParser: argparse.ArgumentParser = ticketCommands.add_parser("meta", help="Inspect and manage the ticket's metadata map.", formatter_class=RichHelpFormatter)
    metaParser.add_argument("key", nargs="?", metavar="KEY", help="The metadata key. Namespace it, for example 'video', so it cannot collide with another tool's key. Omit it to print the whole map as JSON.")
    metaParser.add_argument("value", nargs="?", metavar="VALUE", help="The value to store. Omit it to print the key's value and nothing else.")
    metaParser.add_argument("-c", "--clear", action="store_true", help="Remove the key instead of setting it.")

    return ticketParser


def parseIdList(value: Optional[str]) -> Optional[list[str]]:
    """
    Split a comma-separated id list.

    Both `none` and an empty string yield an empty list rather than `None`, which is how `set --requires` clears a ticket's dependencies. The sentinel exists because PowerShell discards an empty-string argument before the process ever sees it, leaving the documented empty-string form unreachable on Windows.

    Args:
        value: The raw argument value.

    Returns:
        The ids, or `None` when the argument was absent.

    Raises:
        InvalidIdError: '{CLEAR_SENTINEL}' clears the whole list, so it cannot be combined with an id. Pass either '{CLEAR_SENTINEL}' alone or only ids.
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

    Args:
        value: The raw argument value.
        flag: The flag the value came from, named in the error.

    Returns:
        The ids, or `None` when the argument was absent.

    Raises:
        InvalidIdError: '{flag}' needs at least one id. Use '--requires {CLEAR_SENTINEL}' to clear the list instead.
    """

    entries: Optional[list[str]] = parseIdList(value)

    if entries is not None and not entries:
        raise InvalidIdError(f"'{flag}' needs at least one id. Use '--requires {CLEAR_SENTINEL}' to clear the list instead.")

    return entries
