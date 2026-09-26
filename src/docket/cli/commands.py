"""
Docket CLI Commands

One handler per subcommand, each turning parsed arguments into core calls and printed output.

No rules live here either. A handler decides what to say, never what is true.
"""

# MARK: Imports

import argparse
from pathlib import Path
from typing import Callable, Optional

from rich.table import Table
from rich.text import Text

from docket.cli.grammar import ACCESSORS, EXIT_INVALID, EXIT_OK, EXIT_USAGE, OUTPUT_ARGUMENT, parseEditIdList, parseIdList, resolveGraphScope, resolveListFilters
from docket.cli.output import STATUS_STYLES, Output, buildContextTable, buildTicketBody, buildTicketPanel, plainTicket, relativeToRoot
from docket.core.config import Config, discoverConfig
from docket.core.deploy import DeployReport, deploy, upgrade
from docket.core.handoff import HANDOFF_FILENAME, renderHandoff
from docket.core.graph import ResolvedGraph, dependencyContext, readyTickets, resolveGraph, scopeGraph, ticketReadiness
from docket.core.inputs import requireWritableFile, writeFile
from docket.core.mermaid import renderGraph
from docket.core.roadmap import ROADMAP_FILENAME, Roadmap, buildRoadmap
from docket.core.store import Store, TicketResult, TicketSet
from docket.core.ticket import STATUSES, Ticket
from docket.core.validate import SEVERITY_ERROR, ValidationReport, validate

# MARK: Constants

# How each accessor in the grammar reads its answer off a ticket. The store is passed alongside the ticket because a derived answer, such as the reverse dependencies or readiness, cannot be read from one ticket alone. A list comes back for a list of ids, which `commandField` prints one per line.
FIELD_READERS: dict[str, Callable[[Store, Ticket], object]] = {
    "title": lambda store, ticket: ticket.title,
    "status": lambda store, ticket: ticket.status,
    "priority": lambda store, ticket: ticket.priority,
    "requires": lambda store, ticket: list(ticket.requires),
    "required-by": lambda store, ticket: [entry["id"] for entry in dependencyContext(store.loadAll(), ticket.id)["requiredBy"]],
    "key": lambda store, ticket: ticket.key,
    "ready": lambda store, ticket: ticketReadiness(store.loadAll(), ticket.id).isReady,
}

# MARK: Functions


def commandTicket(args: argparse.Namespace, store: Store, output: Output) -> int:
    """
    Route one ticket's command to the handler for it.

    A bare id shows the ticket, since showing it is what naming one almost always means.

    Args:
        args: The parsed arguments.
        store: The store to read from or write through.
        output: Where to write.

    Returns:
        The process exit code.
    """

    # A status word is not a command carrying a value, it is the whole instruction.
    if args.ticketCommand in STATUSES:
        return commandStatus(args, store, output)

    # Every read shares one handler, since what differs between them is only which value is read.
    if args.ticketCommand in ACCESSORS:
        return commandField(args, store, output)

    handlers = {
        None: commandShow,
        "show": commandShow,
        "set": commandSet,
        "meta": commandMeta,
    }

    return handlers[args.ticketCommand](args, store, output)


def commandNew(args: argparse.Namespace, store: Store, output: Output) -> int:
    """
    Create a ticket.

    Args:
        args: The parsed arguments.
        store: The store to write through.
        output: Where to write.

    Returns:
        The process exit code.
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

    The raw file carries bare ids in one direction only, so this resolves the titles and statuses the file deliberately does not duplicate. The body is rendered as Markdown unless `--plain` asks for the same content as bare text. Use `cat` for the raw file.

    Args:
        args: The parsed arguments.
        store: The store to read from.
        output: Where to write.

    Returns:
        The process exit code.
    """

    loaded: TicketSet = store.loadAll()
    ticket: Ticket = loaded.get(args.id)
    context: dict[str, list[dict[str, object]]] = dependencyContext(loaded, args.id)
    root: Path = store.config.repoRoot

    # Plain carries everything the styled form does, only without the styling or the rendering.
    if args.plain:
        output.raw(plainTicket(ticket, context, root))

        return EXIT_OK

    output.print(buildTicketPanel(ticket, root))

    # Show both directions, since the reverse one is the whole reason the file can afford to store only forward edges.
    output.print("")
    output.print(buildContextTable("Requires", context["requires"]))
    output.print("")
    output.print(buildContextTable("Required by", context["requiredBy"]))

    output.print("")
    output.print(buildTicketBody(ticket))

    return EXIT_OK


def commandList(args: argparse.Namespace, store: Store, output: Output) -> int:
    """
    List ticket summaries.

    Args:
        args: The parsed arguments.
        store: The store to read from.
        output: Where to write.

    Returns:
        The process exit code.
    """

    status, key, priorityMax = resolveListFilters(args.filters, args.status, args.key, args.priorityMax)

    # An unregistered key cannot match a ticket, so name it rather than reporting an empty result the user would read as "no work here".
    if key is not None:
        store.config.requireKnownKey(key)

    loaded: TicketSet = store.loadAll()
    tickets: list[Ticket] = loaded.filtered(status=status, key=key, priorityMax=priorityMax)

    # Readiness is judged against the whole set rather than the narrowed one, since a dependency may well have been filtered out of the listing.
    if args.ready:
        tickets = readyTickets(loaded, tickets)

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

    Args:
        args: The parsed arguments.
        store: The store to write through.
        output: Where to write.

    Returns:
        The process exit code.
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

    Args:
        args: The parsed arguments.
        store: The store to write through.
        output: Where to write.

    Returns:
        The process exit code.
    """

    # The command that was typed is the status, since each status is its own command rather than a value handed to a shared one.
    ticket: Ticket = store.setStatus(args.id, args.ticketCommand)

    output.print(f"[bold]{ticket.id}[/bold] is now [{STATUS_STYLES.get(ticket.status, 'white')}]{ticket.status}[/] at {relativeToRoot(ticket.path, store.config.repoRoot)}")

    return EXIT_OK


def commandField(args: argparse.Namespace, store: Store, output: Output) -> int:
    """
    Print one thing about a ticket and nothing else.

    This goes out raw, with no styling and no surrounding words, so a shell can read the answer as easily as a person can. A list of ids is written one per line and anything else through `Output.value`. What is blocking a ticket that is not ready is deliberately left to `show`, which already tables both dependency directions with their statuses.

    Args:
        args: The parsed arguments.
        store: The store to read from.
        output: Where to write.

    Returns:
        The process exit code, which reports whether the question could be answered rather than what the answer was.
    """

    value: object = FIELD_READERS[args.ticketCommand](store, store.load(args.id))

    if isinstance(value, list):
        output.lines(value)
    else:
        output.value(value)

    return EXIT_OK


def commandMeta(args: argparse.Namespace, store: Store, output: Output) -> int:
    """
    Inspect and manage a ticket's metadata map.

    How much of the call was typed is what it means. No key reads the whole map, a key alone reads that one entry, and a key with a value writes it, which is the same shape a status has.

    Args:
        args: The parsed arguments.
        store: The store to read from or write through.
        output: Where to write.

    Returns:
        The process exit code.
    """

    if args.key is None:
        # Clearing needs to know what to clear, and the whole map is not it.
        if args.clear:
            output.error("Nothing to clear. Name the metadata key to remove.")
            return EXIT_USAGE

        # The whole map goes out as JSON, including an empty one, so a pipe into `jq` never meets a sentence where the object should be.
        output.json(store.load(args.id).metadata)

        return EXIT_OK

    if args.clear and args.value is not None:
        output.error("Cannot pass a value together with -c/--clear.")
        return EXIT_USAGE

    # A key with no value reads that entry, raw, for the same reason `status` does. A structured value goes out as JSON rather than in Python's own spelling.
    if not args.clear and args.value is None:
        ticket: Ticket = store.load(args.id)

        if args.key not in ticket.metadata:
            output.error(f"'{args.key}' is not set on {ticket.id}.")
            return EXIT_USAGE

        output.value(ticket.metadata[args.key])

        return EXIT_OK

    result: TicketResult = store.setMetadata(ticketId=args.id, key=args.key, value=None if args.clear else args.value)

    for warning in result.warnings:
        output.warn(warning)

    verb: str = "Cleared" if args.clear else "Set"
    output.print(f"{verb} [bold]{args.key}[/bold] on [bold]{result.ticket.id}[/bold]")

    return EXIT_OK


def commandGraph(args: argparse.Namespace, store: Store, output: Output) -> int:
    """
    Render the dependency graph as mermaid source.

    Args:
        args: The parsed arguments.
        store: The store to read from.
        output: Where to write.

    Returns:
        The process exit code.
    """

    ticketId, key, status = resolveGraphScope(args.scope, args.id, args.key, args.status)

    requireScopeKey(store, key)

    graph: ResolvedGraph = scopeGraph(resolveGraph(store.loadAll()), ticketId, key, status)

    source: str = renderGraph(graph)

    return emitDocument(source, args.output, OUTPUT_ARGUMENT, output)


def commandKey(args: argparse.Namespace, store: Store, output: Output) -> int:
    """
    Inspect and manage the key registry.

    Args:
        args: The parsed arguments.
        store: The store, which also reports which keys are in use.
        output: Where to write.

    Returns:
        The process exit code.
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

    Args:
        args: The parsed arguments.
        store: The store to validate.
        output: Where to write.

    Returns:
        The process exit code, non-zero when errors were found.
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


def requireScopeKey(store: Store, key: Optional[str]) -> None:
    """
    Refuse a scope naming a key the repository has not registered.

    Scoping to an unknown key would draw an empty graph, which reads as an answer rather than as the typo it is. `list` refuses one for the same reason. A status needs no equivalent check, since the vocabulary is fixed and both spellings are checked against it before they arrive here, so an empty result there is a true answer.

    Args:
        store: The store holding the registry.
        key: The key the scope named, or `None` when it named something else.
    """

    if key is not None:
        store.config.requireKnownKey(key)


def documentPath(config: Optional[Config], filename: str) -> Path:
    """
    Place a shipped document's prescribed destination.

    A document belongs to the repository it describes, so it lands beside the configuration that governs it. Run outside a repository there is no such place, and the working directory is the only honest fallback, which is the same reasoning that lets the brief render without a configuration at all.

    Args:
        config: The configuration governing the document, or `None` when none was found.
        filename: What the document is called.

    Returns:
        The path to write to unless the caller names another.
    """

    return (config.repoRoot if config is not None else Path.cwd()) / filename


def emitDocument(text: str, destination: Optional[str], name: str, output: Output, defaultPath: Optional[Path] = None, toPrint: bool = False, note: str = "") -> int:
    """
    Send rendered text to the file it belongs in, to stdout, or to both.

    Every command that renders text leaves through here rather than each growing its own copy of the rule. What differs between them is only whether they have a file to fall back on: a document does and so writes one unasked, while `graph` does not and so stays a pipe.

    A named destination always wins. Without one, the prescribed path is written unless printing was asked for instead, and asking for both does both.

    Args:
        text: The rendered text to emit.
        destination: The path the caller named, or `None` when none was named.
        name: What to name the destination in an error message, for example `--output path`.
        output: Where to write.
        defaultPath: The path to write when none was named, or `None` to leave stdout as the only destination.
        toPrint: Whether to print the text to stdout.
        note: Anything to append to the confirmation line, already spaced and parenthesized.

    Returns:
        The process exit code.
    """

    chosen: Optional[str] = destination

    # Fall back to the prescribed path, which printing replaces rather than adds to, so a bare print stays clean enough to pipe.
    if chosen is None and defaultPath is not None and not toPrint:
        chosen = str(defaultPath)

    if chosen is not None:
        # Check the destination before the filesystem is touched, and translate whatever it still refuses, so no write failure reaches the user as a traceback.
        outPath: Path = writeFile(requireWritableFile(chosen, name), text, name)
        output.print(f"Wrote {outPath}{note}")

    # Straight to stdout with no styling, so a redirect captures exactly what was rendered and nothing else. With nothing written this is the whole of the command's output.
    if toPrint or chosen is None:
        output.raw(text)

    return EXIT_OK


def commandDocs(args: argparse.Namespace, config: Optional[Config], output: Output) -> int:
    """
    Write a document docket ships, rendered for this repository.

    Args:
        args: The parsed arguments.
        config: The configuration governing the current directory, or `None` when none was found.
        output: Where to write.

    Returns:
        The process exit code.
    """

    if args.docsCommand == "handoff":
        # A configuration is what lets the brief name real keys and real numbering, but its absence is a state the document handles rather than an error, since a person may be anywhere when they go to fetch it.
        store: Optional[Store] = Store(config) if config is not None else None

        return emitDocument(renderHandoff(store), args.output, OUTPUT_ARGUMENT, output, documentPath(config, HANDOFF_FILENAME), args.toPrint)

    if args.docsCommand == "roadmap":
        # The roadmap is nothing but this repository's own tickets, so unlike the brief it cannot be rendered without one. Discovery is repeated here so the reason a configuration could not be found is reported by the code that knows it.
        return commandRoadmap(args, Store(config if config is not None else discoverConfig()), output)

    output.error("Expected one of: handoff, roadmap.")

    return EXIT_USAGE


def commandRoadmap(args: argparse.Namespace, store: Store, output: Output) -> int:
    """
    Write the dependency graph as a markdown document with an embedded mermaid diagram.

    Args:
        args: The parsed arguments.
        store: The store to read from.
        output: Where to write.

    Returns:
        The process exit code.
    """

    ticketId, key, status = resolveGraphScope(args.scope, args.id, args.key, args.status)

    requireScopeKey(store, key)

    # The flag overrides the configured ceiling for one run, which is what lets a repository render a bigger diagram once without editing its configuration.
    maxNodes: int = store.config.maxRoadmapNodes if args.maxNodes is None else args.maxNodes

    roadmap: Roadmap = buildRoadmap(store, ticketId=ticketId, key=key, status=status, maxNodes=maxNodes)

    # The document says nothing about what the ceiling dropped, so the person who ran the command is told here instead. Otherwise a diagram that quietly stopped showing its history gives no hint of why.
    note: str = f" ({roadmap.dropped} completed ticket(s) omitted)" if roadmap.dropped else ""

    return emitDocument(roadmap.document, args.output, OUTPUT_ARGUMENT, output, documentPath(store.config, ROADMAP_FILENAME), args.toPrint, note)


def commandDeploy(args: argparse.Namespace, output: Output) -> int:
    """
    Install docket into a repository, or refresh what is already deployed there.

    Args:
        args: The parsed arguments.
        output: Where to write.

    Returns:
        The process exit code.
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
