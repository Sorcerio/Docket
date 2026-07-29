"""
Docket MCP Server

A stdio MCP server, a thin shell over `docket.core`.

Nothing here may write to stdout, because the MCP stdio transport owns it and one stray byte corrupts the protocol.
Diagnostics go to stderr. `rich` must never be imported in this module for the same reason.

Naming across the two surfaces:
MCP tool names and their parameters are snake_case, because that is the MCP ecosystem convention and it is what the model sees.
This repository's Python is camelCase. The two meet here and nowhere else.
Each handler is a camelCase Python function carrying an explicit snake_case `name`, its parameters are snake_case because they are the wire format, and the first thing every body does is hand those values to camelCase core calls.
Neither convention leaks into the other.
"""

# MARK: Imports

import json
import sys
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from docket import __version__
from docket.core.config import Config, discoverConfig
from docket.core.graph import ResolvedGraph, dependencyContext, resolveGraph, subgraphForId, subgraphForKey
from docket.core.mermaid import renderGraph
from docket.core.store import Store, TicketResult, TicketSet
from docket.core.ticket import Ticket
from docket.core.validate import ValidationReport, validate

# MARK: Constants

# The server name the client sees.
SERVER_NAME: str = "docket"

# Shown to the model when the server connects, so an agent knows the shape of the system before calling anything.
SERVER_INSTRUCTIONS: str = """\
Docket is this repository's ticket system. Tickets are markdown files with YAML frontmatter.

A ticket file has two halves with different rules. The body, everything below the closing frontmatter delimiter, is prose you may edit directly and freely. No tool parses it, and there is deliberately no tool for editing it. The frontmatter fields, and where the file lives, belong to these tools.

So: use `update_ticket` for title, priority, and dependencies, `set_metadata` for one metadata entry at a time, and `set_status` for status. Never move a file between the todo and done directories by hand, because `set_status` writes the frontmatter and performs the move together. Never rename a ticket file, because filenames are frozen at creation and other tickets reference them.

`metadata` is a free-form map any tool or skill can attach entries to. Namespace your key so two consumers never collide, for example `video` rather than `covered`. `set_metadata` touches only the key you name, leaving every other consumer's entries alone.

Dependencies are stored in one direction only. A ticket declares `requires`, and never declares what it blocks. `read_ticket` returns both directions, deriving the reverse side for you.

Keys are closed. Call `list_keys` before `create_ticket`. When no existing key fits, ask the user with `AskUserQuestion` whether to add one, and call `add_key` only once they agree.
"""

# MARK: Server

mcp: FastMCP = FastMCP(name=SERVER_NAME, instructions=SERVER_INSTRUCTIONS)

# `FastMCP` accepts no version and forwards none to the lowlevel server it wraps, which then falls back to reporting the `mcp` package's own version as ours.
# Assigning it here is the only way to advertise the real one. `version` is a plain attribute on that server, read when the client initializes, so a late assignment still reaches the handshake.
mcp._mcp_server.version = __version__

# MARK: Functions


@mcp.tool(name="list_tickets")
def listTickets(status: Optional[str] = None, key: Optional[str] = None, priority_max: Optional[int] = None) -> str:
    """
    List ticket summaries, ordered by priority and then by id.

    Returns id, title, status, priority, and key for each match. Never returns bodies, so listing many tickets stays cheap. Call `read_ticket` for the body of one.

    status: Keep only tickets with this status. One of todo, wip, done.
    key: Keep only tickets carrying this key.
    priority_max: Keep only tickets at or below this priority number. 0 is most urgent.
    """

    store: Store = _store()
    tickets: list[Ticket] = store.loadAll().filtered(status=status, key=key, priorityMax=priority_max)

    return _json({"count": len(tickets), "tickets": [ticket.summary() for ticket in tickets]})


@mcp.tool(name="read_ticket")
def readTicket(id: str) -> str:
    """
    Read one ticket in full, with its dependency context resolved.

    The raw file stores bare ids in one direction only, so this adds what the file deliberately does not duplicate: the title and status of everything this ticket requires, and the whole reverse direction of everything that requires it. A dependency naming a ticket that does not exist is returned with `exists` false rather than being hidden.

    id: The ticket id, for example CORE-14.
    """

    store: Store = _store()
    loaded: TicketSet = store.loadAll()
    ticket: Ticket = loaded.get(id)
    context = dependencyContext(loaded, id)

    payload: dict[str, Any] = dict(ticket.summary())
    payload["body"] = ticket.body
    payload["requires"] = context["requires"]
    payload["requiredBy"] = context["requiredBy"]
    payload["metadata"] = ticket.metadata
    payload["extra"] = ticket.extra

    return _json(payload)


@mcp.tool(name="create_ticket")
def createTicket(
    key: str,
    title: str,
    body: Optional[str] = None,
    requires: Optional[list[str]] = None,
    priority: Optional[int] = None,
) -> str:
    """
    Create a ticket, allocating its id and writing the file.

    The key must already be registered. Call `list_keys` first rather than guessing. When nothing fits, ask the user with `AskUserQuestion` and call `add_key` once they agree. An unregistered key is refused.

    Write the body so a reader with no other context can act on it. Include the architecture discussed, the assumptions made, and the questions already answered, stated plainly in the ticket itself.

    A `requires` entry naming a ticket that does not exist yet is a warning rather than a failure, so a batch written out of order still completes. Call `validate` once the batch is done.

    key: The key to mint under, for example CORE.
    title: The ticket title, which cannot be empty. The filename derives from this once, at creation, and never changes afterwards.
    body: Markdown prose for the body, placed under a heading built from the title.
    requires: Ids this ticket depends on.
    priority: 0 is most urgent. Defaults to the repository's configured default.
    """

    result: TicketResult = _store().create(key=key, title=title, body=body, requires=requires, priority=priority)

    return _json({"id": result.ticket.id, "path": str(result.ticket.path), "warnings": result.warnings})


@mcp.tool(name="update_ticket")
def updateTicket(
    id: str,
    title: Optional[str] = None,
    priority: Optional[int] = None,
    requires: Optional[list[str]] = None,
) -> str:
    """
    Change a ticket's title, priority, or dependencies.

    Only the fields supplied are touched. Status is not changeable here, because changing it moves the file, which is `set_status`. The filename never changes, even when the title does, so prose cross-references elsewhere stay intact.

    id: The ticket id.
    title: A new title, which cannot be empty.
    priority: A new priority. 0 is most urgent.
    requires: A replacement dependency list. Pass an empty list to clear it.
    """

    result: TicketResult = _store().update(ticketId=id, title=title, priority=priority, requires=requires)

    return _json({"id": result.ticket.id, "warnings": result.warnings, "ticket": result.ticket.summary()})


@mcp.tool(name="set_metadata")
def setMetadata(id: str, key: str, value: Optional[Any] = None) -> str:
    """
    Set or clear one entry in a ticket's `metadata` map.

    `metadata` is free-form, shared by whatever tools or skills want to attach data to a ticket. Namespace your key, for example `video`, so your entries never collide with another consumer's. Only the named key is touched, every other entry is left as it was.

    id: The ticket id.
    key: The metadata key, which cannot be empty.
    value: The value to store, any JSON-compatible type. Omit or pass null to remove the key instead.
    """

    result: TicketResult = _store().setMetadata(ticketId=id, key=key, value=value)

    return _json({"id": result.ticket.id, "warnings": result.warnings, "metadata": result.ticket.metadata})


@mcp.tool(name="set_status")
def setStatus(id: str, status: str) -> str:
    """
    Change a ticket's status, updating the frontmatter and moving the file in one operation.

    Never move a ticket file by hand. The status field is the truth and the directory is a projection of it, and only this tool keeps the two in step.

    id: The ticket id.
    status: One of todo, wip, done. Only done moves the file into the done directory.
    """

    ticket: Ticket = _store().setStatus(id, status)

    return _json({"id": ticket.id, "status": ticket.status, "path": str(ticket.path)})


@mcp.tool(name="graph")
def graphTool(id: Optional[str] = None, key: Optional[str] = None) -> str:
    """
    Render the dependency graph as mermaid source.

    Arrows point from a dependency to what depends on it, so an arrow reads as "must happen before". With no argument the whole set is rendered.

    id: Scope to one ticket's transitive ancestors and descendants.
    key: Scope to one key, plus its immediate cross-key neighbors, which are marked so the boundary is visible.
    """

    store: Store = _store()
    graph: ResolvedGraph = resolveGraph(store.loadAll())

    # Scope when asked, preferring an id since it is the narrower request.
    if id is not None:
        graph = subgraphForId(graph, id)
    elif key is not None:
        graph = subgraphForKey(graph, key)

    return _json({"scope": graph.scope, "nodeCount": len(graph), "mermaid": renderGraph(graph)})


@mcp.tool(name="list_keys")
def listKeys() -> str:
    """
    List the keys tickets may be created under.

    A key not listed here will be refused by `create_ticket`.
    """

    registered: list[dict[str, str]] = [{"key": key, "description": description} for key, description in sorted(_config().registeredKeys.items())]

    return _json({"registered": registered})


@mcp.tool(name="add_key")
def addKey(key: str, description: str, rationale: str) -> str:
    """
    Register a new key, so tickets can be created under it.

    Adding a key changes how this repository is organized, which is the user's call and not yours. Before calling this, ask the user with `AskUserQuestion` whether they want the new key, naming the key you propose and why the existing ones do not fit. Offer using an existing key as an option. Call this only once they have agreed, and never as a reflex because you cannot remember which key to use. Call `list_keys` first.

    The key is written into the repository's configuration, where it shows up in the git diff.

    key: The new key. Uppercase alphanumeric, starting with a letter, for example META.
    description: What this key groups, shown alongside the other keys. It cannot be empty.
    rationale: Why a new key is needed. This is written as a comment above the key, so a later reader sees the reasoning.
    """

    _config().addKey(key=key, description=description, rationale=rationale)

    return _json({"key": key, "description": description, "rationale": rationale})


@mcp.tool(name="validate")
def validateTool() -> str:
    """
    Run every integrity rule over the ticket set and return structured findings.

    Errors block. Warnings inform. Call this after writing a batch of tickets, since a dependency naming a ticket that did not exist yet is only a warning at creation time and becomes an error here.
    """

    store: Store = _store()
    report: ValidationReport = validate(store)

    return _json(report.toDict())


def main(argv: Optional[list[str]] = None) -> int:
    """
    Entry point for the `docket-mcp` console script.

    argv: Argument list, accepted for symmetry with the CLI and currently unused.

    Returns the process exit code.
    """

    # `FastMCP.run` owns the event loop, so no async runtime is imported here.
    try:
        mcp.run(transport="stdio")
    except KeyboardInterrupt:
        return 0

    return 0


def _config() -> Config:
    """
    Find the configuration governing the working directory.

    This resolves per call rather than once at startup, so a key approved while the server is running is picked up without a restart.

    Returns the loaded `Config`.
    """

    return discoverConfig()


def _store() -> Store:
    """
    Build a store over the configuration governing the working directory.

    Returns the store.
    """

    return Store(_config())


def _json(payload: Any) -> str:
    """
    Encode a payload for return across the MCP boundary.

    Every tool returns JSON as text, which is unambiguous for the model to parse and stable to assert on in tests. It is written compactly, since an agent pays for every token of it.

    payload: The data to encode.

    Returns the encoded text.
    """

    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


# MARK: Main

if __name__ == "__main__":
    sys.exit(main())
