"""
Docket CLI Commands

One handler per subcommand, each turning parsed arguments into core calls and printed output.

No rules live here either. A handler decides what to say, never what is true.
"""

# MARK: Imports

import argparse
from pathlib import Path

from rich.table import Table
from rich.text import Text

from docket.cli.grammar import EXIT_INVALID, EXIT_OK, EXIT_USAGE, OUT_ARGUMENT, parseEditIdList, parseIdList
from docket.cli.output import STATUS_STYLES, Output, buildContextTable, relativeToRoot
from docket.core.config import Config
from docket.core.deploy import DeployReport, deploy, upgrade
from docket.core.graph import ResolvedGraph, dependencyContext, resolveGraph, subgraphForId, subgraphForKey
from docket.core.inputs import requireWritableFile, writeFile
from docket.core.mermaid import renderGraph
from docket.core.store import Store, TicketResult, TicketSet
from docket.core.ticket import Ticket
from docket.core.validate import SEVERITY_ERROR, ValidationReport, validate

# MARK: Functions


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

    # An unregistered key cannot match a ticket, so name it rather than reporting an empty result the user would read as "no work here".
    if args.key is not None:
        store.config.requireKnownKey(args.key)

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
    if args.title is None and args.priority is None and args.requires is None and args.requiresAdd is None and args.requiresRemove is None:
        output.error("Nothing to change. Pass at least one of --title, --priority, --requires, --requires-add, or --requires-remove.")
        return EXIT_USAGE

    result: TicketResult = store.update(
        ticketId=args.id,
        title=args.title,
        priority=args.priority,
        requires=parseIdList(args.requires) if args.requires is not None else None,
        requiresAdd=parseEditIdList(args.requiresAdd, "--requires-add"),
        requiresRemove=parseEditIdList(args.requiresRemove, "--requires-remove"),
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


def commandMeta(args: argparse.Namespace, store: Store, output: Output) -> int:
    """
    Inspect and manage a ticket's metadata map.

    args: The parsed arguments.
    store: The store to read from or write through.
    output: Where to write.

    Returns the process exit code.
    """

    if args.metaCommand == "get":
        ticket: Ticket = store.load(args.id)

        if not ticket.metadata:
            output.print("[dim]No metadata.[/dim]")
            return EXIT_OK

        table: Table = Table(box=None, pad_edge=False)
        table.add_column("KEY", style="bold")
        table.add_column("VALUE")

        for key, value in ticket.metadata.items():
            table.add_row(key, str(value))

        output.print(table)

        return EXIT_OK

    if args.metaCommand == "set":
        if args.clear and args.value is not None:
            output.error("Cannot pass a value together with -c/--clear.")
            return EXIT_USAGE

        if not args.clear and args.value is None:
            output.error("Nothing to set. Pass a value, or -c/--clear to remove the key.")
            return EXIT_USAGE

        result: TicketResult = store.setMetadata(ticketId=args.id, key=args.key, value=None if args.clear else args.value)

        for warning in result.warnings:
            output.warn(warning)

        verb: str = "Cleared" if args.clear else "Set"
        output.print(f"{verb} [bold]{args.key}[/bold] on [bold]{result.ticket.id}[/bold]")

        return EXIT_OK

    output.error("Expected one of: get, set.")
    return EXIT_USAGE


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
        # For the same reason as `list`, an unregistered key here would render an empty graph rather than admitting the key does not exist.
        store.config.requireKnownKey(args.key)
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
