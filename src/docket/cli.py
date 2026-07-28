"""
Docket CLI

Argument parsing and command dispatch, a thin shell over `docket.core`.

This holds no rules of its own. Every decision belongs to the core, so the CLI and the MCP server can never disagree about one.
"""

# MARK: Imports

import argparse
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich_argparse import RichHelpFormatter

from docket import __version__
from docket.core.config import Config, discoverConfig
from docket.core.deploy import DeployReport, deploy, upgrade
from docket.core.errors import DocketError, InvalidIdError
from docket.core.graph import ResolvedGraph, dependencyContext, resolveGraph, subgraphForId, subgraphForKey
from docket.core.inputs import requireWritableFile, writeFile
from docket.core.mermaid import renderGraph
from docket.core.store import Store, TicketResult, TicketSet
from docket.core.ticket import STATUSES, Ticket
from docket.core.validate import SEVERITY_ERROR, ValidationReport, validate

# MARK: Constants

# The program name used in help output and error messages.
PROGRAM_NAME: str = "docket"

# Exit codes, distinguishing a set that failed validation from a command that could not run at all.
EXIT_OK: int = 0
EXIT_INVALID: int = 1
EXIT_USAGE: int = 2

# Styles for the status column, matching the intent of the mermaid classes without depending on them.
STATUS_STYLES: dict[str, str] = {"todo": "dim", "wip": "yellow", "done": "green"}

# The word that clears a comma-separated list argument. An id can never collide with it, since every id is an uppercase key followed by a hyphen and a number.
CLEAR_SENTINEL: str = "none"

# How the graph destination is named when a message has to talk about it.
OUT_ARGUMENT: str = "--out path"

# MARK: Classes


class Output:
    """
    Everything the CLI prints.

    Human-facing output goes through `rich`. Machine-readable output does not, because a pipe must receive bare text with no wrapping, highlighting, or escape sequences in it.
    """

    # MARK: Initializer

    def __init__(self) -> None:
        """
        Build the consoles.
        """

        self.console: Console = Console()
        self.errorConsole: Console = Console(stderr=True)

    # MARK: Functions

    def print(self, renderable: object) -> None:
        """
        Print human-facing output.

        renderable: Anything `rich` can render.
        """

        self.console.print(renderable)

    def raw(self, text: str) -> None:
        """
        Write machine-readable output with no styling applied.

        Mermaid source goes through here, so redirecting it to a file or a pipe yields exactly the source and nothing else.

        text: The text to write.
        """

        sys.stdout.write(text)

    def warn(self, message: str) -> None:
        """
        Report a non-fatal warning.

        message: The warning text.
        """

        self.errorConsole.print(Text(f"warning: {message}", style="yellow"))

    def error(self, message: str) -> None:
        """
        Report a failure.

        message: The error text.
        """

        self.errorConsole.print(Text(f"error: {message}", style="bold red"))


# MARK: Functions


def buildParser() -> argparse.ArgumentParser:
    """
    Build the top-level argument parser and every subcommand parser.

    Returns the configured `argparse.ArgumentParser`.
    """

    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog=PROGRAM_NAME,
        description="A per-repo ticketing system that is plain markdown for humans and structured MCP for agents.",
        formatter_class=RichHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"{PROGRAM_NAME} {__version__}")

    commands = parser.add_subparsers(dest="command", metavar="COMMAND")

    # Creating a ticket, which allocates the id and freezes the filename.
    newParser: argparse.ArgumentParser = commands.add_parser("new", help="Create a ticket.", formatter_class=RichHelpFormatter)
    newParser.add_argument("--key", required=True, help="The key to mint under. Must be registered.")
    newParser.add_argument("--title", required=True, help="The ticket title. The filename slug derives from this once, here.")
    newParser.add_argument("--requires", help="Comma-separated ids this ticket depends on.")
    newParser.add_argument("--priority", type=int, help="Priority, 0 most urgent. Defaults to the configured defaultPriority.")
    newParser.add_argument("--body", help="Prose for the body, placed under a heading built from the title.")

    showParser: argparse.ArgumentParser = commands.add_parser("show", help="Show a ticket with its resolved dependency context.", formatter_class=RichHelpFormatter)
    showParser.add_argument("id", help="The ticket id.")

    listParser: argparse.ArgumentParser = commands.add_parser("list", help="List ticket summaries.", formatter_class=RichHelpFormatter)
    listParser.add_argument("--status", choices=STATUSES, help="Keep only tickets with this status.")
    listParser.add_argument("--key", help="Keep only tickets carrying this key.")
    listParser.add_argument("--priority-max", type=int, dest="priorityMax", help="Keep only tickets at or below this priority number.")

    setParser: argparse.ArgumentParser = commands.add_parser("set", help="Change a ticket's title, priority, or dependencies.", formatter_class=RichHelpFormatter)
    setParser.add_argument("id", help="The ticket id.")
    setParser.add_argument("--title", help="A new title. The filename does not follow it, since filenames are frozen at creation.")
    setParser.add_argument("--priority", type=int, help="A new priority.")
    setParser.add_argument("--requires", help=f"A replacement comma-separated dependency list. Pass '{CLEAR_SENTINEL}' to clear it.")

    statusParser: argparse.ArgumentParser = commands.add_parser("status", help="Change a ticket's status, moving its file to match.", formatter_class=RichHelpFormatter)
    statusParser.add_argument("id", help="The ticket id.")
    statusParser.add_argument("status", choices=STATUSES, help="The new status.")

    graphParser: argparse.ArgumentParser = commands.add_parser("graph", help="Render the dependency graph as mermaid source.", formatter_class=RichHelpFormatter)
    graphScope = graphParser.add_mutually_exclusive_group()
    graphScope.add_argument("--id", help="Scope to one ticket's ancestors and descendants.")
    graphScope.add_argument("--key", help="Scope to one key, plus its immediate cross-key neighbors.")
    graphParser.add_argument("--out", help="Write to a file rather than to stdout.")

    keyParser: argparse.ArgumentParser = commands.add_parser("key", help="Inspect and manage the key registry.", formatter_class=RichHelpFormatter)
    keyCommands = keyParser.add_subparsers(dest="keyCommand", metavar="SUBCOMMAND")

    keyCommands.add_parser("list", help="List the registered keys.", formatter_class=RichHelpFormatter)

    keyAddParser: argparse.ArgumentParser = keyCommands.add_parser("add", help="Register a new key.", formatter_class=RichHelpFormatter)
    keyAddParser.add_argument("key", help="The key to add.")
    keyAddParser.add_argument("description", help="What the key groups.")
    keyAddParser.add_argument("--rationale", help="Why the key was added, written as a comment above it.")

    keyRemoveParser: argparse.ArgumentParser = keyCommands.add_parser("remove", help="Remove a key no ticket uses.", formatter_class=RichHelpFormatter)
    keyRemoveParser.add_argument("key", help="The key to remove.")

    commands.add_parser("validate", help="Run every integrity rule.", formatter_class=RichHelpFormatter)

    deployParser: argparse.ArgumentParser = commands.add_parser("deploy", help="Install docket into a repository.", formatter_class=RichHelpFormatter)
    deployParser.add_argument("path", help="The repository root to deploy into.")

    upgradeParser: argparse.ArgumentParser = commands.add_parser("upgrade", help="Refresh the deployed templates in a repository.", formatter_class=RichHelpFormatter)
    upgradeParser.add_argument("path", help="The repository root to upgrade.")

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """
    Entry point for the `docket` console script.

    argv: Argument list to parse, defaulting to `sys.argv[1:]`.

    Returns the process exit code.
    """

    parser: argparse.ArgumentParser = buildParser()
    args: argparse.Namespace = parser.parse_args(argv)
    output: Output = Output()

    # With no subcommand there is nothing to dispatch, so show help and report a usage error.
    if args.command is None:
        parser.print_help()
        return EXIT_USAGE

    # Every core failure surfaces here as a message and an exit code, which is the whole of the CLI's error handling.
    try:
        return dispatch(args, output)
    except DocketError as error:
        output.error(str(error))
        return EXIT_USAGE


def dispatch(args: argparse.Namespace, output: Output) -> int:
    """
    Route parsed arguments to the command that handles them.

    args: The parsed arguments.
    output: Where to write.

    Returns the process exit code.
    """

    # Deploy and upgrade run before a configuration exists, or in order to repair one, so they must not require discovering it first.
    if args.command in ("deploy", "upgrade"):
        return commandDeploy(args, output)

    # Every other command works against the configuration governing the current directory.
    store: Store = Store(discoverConfig())

    handlers = {
        "new": commandNew,
        "show": commandShow,
        "list": commandList,
        "set": commandSet,
        "status": commandStatus,
        "graph": commandGraph,
        "key": commandKey,
        "validate": commandValidate,
    }

    return handlers[args.command](args, store, output)


def commandNew(args: argparse.Namespace, store: Store, output: Output) -> int:
    """
    Create a ticket.

    args: The parsed arguments.
    store: The store to write through.
    output: Where to write.

    Returns the process exit code.
    """

    result: TicketResult = store.create(
        key=args.key,
        title=args.title,
        body=args.body,
        requires=parseIdList(args.requires),
        priority=args.priority,
    )

    # A dangling dependency is a warning here, so a batch written out of order still completes.
    for warning in result.warnings:
        output.warn(warning)

    output.print(f"Created [bold]{result.ticket.id}[/bold] at {relativeToRoot(result.ticket.path, store.config.repoRoot)}")

    return EXIT_OK


def commandShow(args: argparse.Namespace, store: Store, output: Output) -> int:
    """
    Show a ticket with its resolved dependency context.

    The raw file carries bare ids in one direction only, so this resolves the titles and statuses the file deliberately does not duplicate. Use `cat` for the raw file.

    args: The parsed arguments.
    store: The store to read from.
    output: Where to write.

    Returns the process exit code.
    """

    loaded: TicketSet = store.loadAll()
    ticket: Ticket = loaded.get(args.id)
    context = dependencyContext(loaded, args.id)

    output.print(Text(f"{ticket.id}  {ticket.title}", style="bold"))
    output.print(f"status [{STATUS_STYLES.get(ticket.status, 'white')}]{ticket.status}[/]  priority {ticket.priority}  key {ticket.key}")

    # Show both directions, since the reverse one is the whole reason the file can afford to store only forward edges.
    output.print("")
    output.print(buildContextTable("Requires", context["requires"]))
    output.print("")
    output.print(buildContextTable("Required by", context["requiredBy"]))

    output.print("")
    output.print(ticket.body.strip("\n"))

    return EXIT_OK


def commandList(args: argparse.Namespace, store: Store, output: Output) -> int:
    """
    List ticket summaries.

    args: The parsed arguments.
    store: The store to read from.
    output: Where to write.

    Returns the process exit code.
    """

    tickets: list[Ticket] = store.loadAll().filtered(status=args.status, key=args.key, priorityMax=args.priorityMax)

    if not tickets:
        output.print("[dim]No tickets matched.[/dim]")
        return EXIT_OK

    table: Table = Table(box=None, pad_edge=False)
    table.add_column("ID", style="bold")
    table.add_column("P", justify="right")
    table.add_column("STATUS")
    table.add_column("TITLE")

    for ticket in tickets:
        table.add_row(ticket.id, str(ticket.priority), Text(ticket.status, style=STATUS_STYLES.get(ticket.status, "white")), ticket.title)

    output.print(table)

    return EXIT_OK


def commandSet(args: argparse.Namespace, store: Store, output: Output) -> int:
    """
    Change a ticket's title, priority, or dependencies.

    args: The parsed arguments.
    store: The store to write through.
    output: Where to write.

    Returns the process exit code.
    """

    # Nothing to do is a usage error rather than a silent success, since the caller clearly meant to change something.
    if args.title is None and args.priority is None and args.requires is None:
        output.error("Nothing to change. Pass at least one of --title, --priority, or --requires.")
        return EXIT_USAGE

    result: TicketResult = store.update(
        ticketId=args.id,
        title=args.title,
        priority=args.priority,
        requires=parseIdList(args.requires) if args.requires is not None else None,
    )

    for warning in result.warnings:
        output.warn(warning)

    output.print(f"Updated [bold]{result.ticket.id}[/bold]")

    return EXIT_OK


def commandStatus(args: argparse.Namespace, store: Store, output: Output) -> int:
    """
    Change a ticket's status, moving its file in the same operation.

    args: The parsed arguments.
    store: The store to write through.
    output: Where to write.

    Returns the process exit code.
    """

    ticket: Ticket = store.setStatus(args.id, args.status)

    output.print(f"[bold]{ticket.id}[/bold] is now [{STATUS_STYLES.get(ticket.status, 'white')}]{ticket.status}[/] at {relativeToRoot(ticket.path, store.config.repoRoot)}")

    return EXIT_OK


def commandGraph(args: argparse.Namespace, store: Store, output: Output) -> int:
    """
    Render the dependency graph as mermaid source.

    args: The parsed arguments.
    store: The store to read from.
    output: Where to write.

    Returns the process exit code.
    """

    graph: ResolvedGraph = resolveGraph(store.loadAll())

    # Scope the graph when asked. The two scopes are mutually exclusive at the parser.
    if args.id is not None:
        graph = subgraphForId(graph, args.id)
    elif args.key is not None:
        graph = subgraphForKey(graph, args.key)

    source: str = renderGraph(graph)

    if args.out is not None:
        # Check the destination before rendering work is spent on it, and translate whatever the filesystem still refuses, so no write failure reaches the user as a traceback.
        outPath: Path = writeFile(requireWritableFile(args.out, OUT_ARGUMENT), source, OUT_ARGUMENT)
        output.print(f"Wrote {outPath}")

        return EXIT_OK

    # Straight to stdout with no styling, so a redirect captures exactly the mermaid source.
    output.raw(source)

    return EXIT_OK


def commandKey(args: argparse.Namespace, store: Store, output: Output) -> int:
    """
    Inspect and manage the key registry.

    args: The parsed arguments.
    store: The store, which also reports which keys are in use.
    output: Where to write.

    Returns the process exit code.
    """

    config: Config = store.config

    if args.keyCommand == "add":
        config.addKey(args.key, args.description, rationale=args.rationale)
        output.print(f"Added [bold]{args.key}[/bold]")

        return EXIT_OK

    if args.keyCommand == "remove":
        # Hand the store's view of usage in, so a key with tickets behind it fails loudly and names them.
        config.removeKey(args.key, usedBy=store.usedKeys().get(args.key))
        output.print(f"Removed [bold]{args.key}[/bold]")

        return EXIT_OK

    if args.keyCommand != "list":
        output.error("Expected one of: list, add, remove.")
        return EXIT_USAGE

    table: Table = Table(box=None, pad_edge=False)
    table.add_column("KEY", style="bold")
    table.add_column("DESCRIPTION")

    for key, description in sorted(config.registeredKeys.items()):
        table.add_row(key, description)

    if not table.rows:
        output.print("[dim]No keys.[/dim]")
        return EXIT_OK

    output.print(table)

    return EXIT_OK


def commandValidate(args: argparse.Namespace, store: Store, output: Output) -> int:
    """
    Run every integrity rule.

    args: The parsed arguments.
    store: The store to validate.
    output: Where to write.

    Returns the process exit code, non-zero when errors were found.
    """

    report: ValidationReport = validate(store)

    if not report.findings:
        output.print("[green]No findings.[/green]")
        return EXIT_OK

    for finding in report.findings:
        style: str = "bold red" if finding.severity == SEVERITY_ERROR else "yellow"
        location: str = f" [dim]{finding.path.name}[/dim]" if finding.path is not None else ""
        output.print(Text.from_markup(f"[{style}]{finding.severity}[/] [dim]{finding.rule}[/dim] {finding.message}{location}"))

    output.print(f"\n{len(report.errors)} error(s), {len(report.warnings)} warning(s)")

    # Warnings alone must not fail a pre-commit hook, so only errors change the exit code.
    return EXIT_INVALID if report.errors else EXIT_OK


def commandDeploy(args: argparse.Namespace, output: Output) -> int:
    """
    Install docket into a repository, or refresh what is already deployed there.

    args: The parsed arguments.
    output: Where to write.

    Returns the process exit code.
    """

    target: Path = Path(args.path)
    report: DeployReport = deploy(target) if args.command == "deploy" else upgrade(target)

    # Report every step, since deploy is idempotent and the useful information is which steps actually changed something.
    root: Path = target.resolve()
    for path in report.created:
        output.print(f"[green]created[/green] {relativeToRoot(path, root)}")
    for path in report.updated:
        output.print(f"[yellow]updated[/yellow] {relativeToRoot(path, root)}")
    for path in report.skipped:
        output.print(f"[dim]kept    {relativeToRoot(path, root)}[/dim]")

    if args.command == "deploy":
        output.print("\nAdd your keys to [bold].docket.toml[/bold] before creating tickets.")

    return EXIT_OK


def buildContextTable(heading: str, entries: list[dict[str, object]]) -> Table:
    """
    Build the table showing one direction of a ticket's resolved dependencies.

    heading: What to title the table.
    entries: The resolved records.

    Returns the table.
    """

    table: Table = Table(title=heading, title_justify="left", box=None, pad_edge=False, title_style="bold")
    table.add_column("ID")
    table.add_column("STATUS")
    table.add_column("TITLE")

    if not entries:
        table.add_row("[dim]none[/dim]", "", "")

        return table

    for entry in entries:
        # A dependency naming a missing id is shown rather than hidden, since a broken link the reader cannot see is worse than one they can.
        if not entry["exists"]:
            table.add_row(str(entry["id"]), Text("missing", style="bold red"), "[dim]no such ticket[/dim]")
            continue

        status: str = str(entry["status"])
        table.add_row(str(entry["id"]), Text(status, style=STATUS_STYLES.get(status, "white")), str(entry["title"]))

    return table


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


def relativeToRoot(path: Optional[Path], root: Path) -> str:
    """
    Describe a path relative to a repository root, so output stays readable in a narrow terminal.

    path: The path to describe.
    root: The directory to describe it against.

    Returns the relative path, falling back to the absolute one when it lies outside the root.
    """

    if path is None:
        return "an unwritten file"

    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


# MARK: Main

if __name__ == "__main__":
    sys.exit(main())
