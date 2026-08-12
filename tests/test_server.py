"""
MCP Server Tests

Drive tools through the real MCP dispatch path, covering the wire surface, payload shapes, and error propagation.
"""

# MARK: Imports

import asyncio
import inspect
import json
import os
from pathlib import Path
from typing import Any, Callable, Iterator

import pytest
from mcp.types import CallToolResult

from docket import server

# MARK: Fixtures


@pytest.fixture
def inRepo(repoDir: Path) -> Iterator[Path]:
    """
    Run inside a throwaway repository, since the server resolves its configuration from the working directory.

    repoDir: The repository root fixture.

    Returns the repository root, restoring the previous working directory afterwards.
    """

    previous: str = os.getcwd()
    os.chdir(repoDir)
    try:
        yield repoDir
    finally:
        os.chdir(previous)


# MARK: Functions


def callTool(name: str, arguments: dict[str, Any] | None = None) -> Any:
    """
    Invoke a tool through the server's real dispatch and decode its payload.

    Going through `call_tool` rather than the handler directly exercises schema validation and the error path exactly as a client would.

    name: The snake_case tool name.
    arguments: The arguments to pass.

    Returns the decoded JSON payload.
    """

    result: CallToolResult = asyncio.run(server.mcp.call_tool(name, arguments or {}))

    return json.loads(result.content[0].text)


def toolNames() -> list[str]:
    """
    List every registered tool name.

    Returns the names.
    """

    return [tool.name for tool in asyncio.run(server.mcp.list_tools())]


def toolHandlers() -> list[Callable[..., Any]]:
    """
    Collect the handler functions the tools are registered from.

    `mcp.tool` hands back the function it decorated, so every handler is a plain attribute of the module. Imported names are excluded by the module they were defined in, and `main` is the entry point rather than a tool.

    Returns the handler functions.
    """

    return [
        value
        for name, value in vars(server).items()
        if inspect.isfunction(value) and value.__module__ == server.__name__ and not name.startswith("_") and name != "main"
    ]


def testEveryHandlerIsAsync() -> None:
    """
    `MCPServer` runs a synchronous handler on a worker thread, which would let two calls into the core at once, and every write there reads the ticket set and then writes it back with nothing guarding the gap.

    Two creates would allocate one id twice, two edits would lose one of them, and a read landing mid-write would see a half-written file. Staying on the event loop is what prevents all three, so it is asserted rather than left to whoever adds the twelfth tool.
    """

    handlers: list[Callable[..., Any]] = toolHandlers()

    # Counting against the registered tools is what makes this catch a new handler instead of only the ones present today.
    assert len(handlers) == len(toolNames())

    for handler in handlers:
        assert inspect.iscoroutinefunction(handler), f"{handler.__name__} must be async, or it runs on a worker thread"


def testEveryDocumentedToolIsRegistered() -> None:
    """
    The surface is exactly the eleven tools the design specifies, no more and no fewer.
    """

    assert sorted(toolNames()) == sorted(
        ["list_tickets", "read_ticket", "check_ready", "create_ticket", "update_ticket", "set_metadata", "set_status", "graph", "list_keys", "add_key", "validate"]
    )


def testToolNamesAndParametersAreSnakeCase() -> None:
    """
    The wire surface follows the MCP ecosystem convention, so no camelCase name or parameter may leak out of the core.
    """

    for tool in asyncio.run(server.mcp.list_tools()):
        assert tool.name.islower()
        assert "_" in tool.name or tool.name.isalpha()

        for parameter in tool.input_schema.get("properties", {}):
            assert parameter == parameter.lower()
            assert not any(character.isupper() for character in parameter)


def testPriorityMaxIsSpelledForTheWire() -> None:
    """
    The core calls this `priorityMax`, and the mapping to the wire spelling happens in the server and nowhere else.
    """

    listTickets = [tool for tool in asyncio.run(server.mcp.list_tools()) if tool.name == "list_tickets"][0]

    assert "priority_max" in listTickets.input_schema["properties"]
    assert "priorityMax" not in listTickets.input_schema["properties"]


def testCreateTicketDescriptionDirectsTheAgentToListKeys() -> None:
    """
    An agent must not guess a key, so the description names the tool that shows the valid ones.
    """

    createTicket = [tool for tool in asyncio.run(server.mcp.list_tools()) if tool.name == "create_ticket"][0]

    assert "list_keys" in createTicket.description
    assert "add_key" in createTicket.description

    # The user decides whether a new key exists, so the tool that asks them is named too.
    assert "AskUserQuestion" in createTicket.description


def testServerInstructionsCoverTheLoadBearingRules() -> None:
    """
    The instructions are what an agent reads before calling anything, so the rules it could otherwise violate are stated there.
    """

    instructions: str = server.SERVER_INSTRUCTIONS

    assert "never move a file" in instructions.lower()
    assert "requires" in instructions
    assert "list_keys" in instructions
    assert "AskUserQuestion" in instructions

    # The body is editable by hand, and saying otherwise would forbid the only way to revise prose.
    assert "edit directly and freely" in instructions


def testCreateTicketReturnsTheNewId(inRepo: Path) -> None:
    """
    Creation allocates the id and reports it, since the caller cannot know it in advance.
    """

    payload = callTool("create_ticket", {"key": "CORE", "title": "Skirmish Setup", "body": "Goal: one battle."})

    assert payload["id"] == "CORE-1"
    assert payload["warnings"] == []
    assert (inRepo / "docs" / "tickets" / "todo" / "CORE-1_skirmishSetup.md").is_file()


def testCreateTicketWarnsOnADanglingDependency(inRepo: Path) -> None:
    """
    A batch written out of order still completes, with the warning carried in the payload rather than raised.
    """

    payload = callTool("create_ticket", {"key": "CORE", "title": "Second", "requires": ["CORE-99"]})

    assert payload["id"] == "CORE-1"
    assert len(payload["warnings"]) == 1
    assert "CORE-99" in payload["warnings"][0]


def testCreateTicketUnderAnUnknownKeyErrors(inRepo: Path) -> None:
    """
    An unknown key is refused, and the error names the recovery path an agent has.
    """

    with pytest.raises(Exception) as excInfo:
        callTool("create_ticket", {"key": "NOPE", "title": "Orphan"})

    assert "add_key" in str(excInfo.value)


@pytest.mark.parametrize(
    "tool,arguments",
    [
        ("create_ticket", {"key": "CORE", "title": ""}),
        ("update_ticket", {"id": "CORE-1", "title": "   "}),
        ("set_metadata", {"id": "CORE-1", "key": "   ", "value": "x"}),
        ("add_key", {"key": "NEW", "description": "", "rationale": "why"}),
    ],
)
def testEmptyTextIsRefused(inRepo: Path, tool: str, arguments: dict[str, Any]) -> None:
    """
    A model can send an empty string as easily as a shell can, so the rule lives in the core where both surfaces meet it.

    tool: The tool under test.
    arguments: The call arguments carrying the empty value.
    """

    callTool("create_ticket", {"key": "CORE", "title": "Original"})

    with pytest.raises(Exception) as excInfo:
        callTool(tool, arguments)

    assert "cannot be empty" in str(excInfo.value)


def testListTicketsNeverReturnsBodies(inRepo: Path) -> None:
    """
    An agent listing forty tickets must not pay for forty bodies.
    """

    callTool("create_ticket", {"key": "CORE", "title": "App Shell", "body": "A very long body that must not appear in a listing."})

    payload = callTool("list_tickets")

    assert payload["count"] == 1
    assert set(payload["tickets"][0]) == {"id", "title", "status", "priority", "key"}
    assert "very long body" not in json.dumps(payload)


def testListTicketsFiltersCombine(inRepo: Path) -> None:
    """
    Each supplied filter narrows the result, using the wire spelling of the priority filter.
    """

    callTool("create_ticket", {"key": "CORE", "title": "Urgent", "priority": 0})
    callTool("create_ticket", {"key": "GEN", "title": "Later", "priority": 4})

    assert [ticket["id"] for ticket in callTool("list_tickets", {"key": "CORE"})["tickets"]] == ["CORE-1"]
    assert [ticket["id"] for ticket in callTool("list_tickets", {"priority_max": 0})["tickets"]] == ["CORE-1"]
    assert callTool("list_tickets", {"status": "done"})["count"] == 0


def testReadTicketResolvesBothDirections(inRepo: Path) -> None:
    """
    The raw file carries bare ids one way, so the tool supplies the titles, the statuses, and the whole reverse side.
    """

    callTool("create_ticket", {"key": "CORE", "title": "App Shell"})
    callTool("create_ticket", {"key": "CORE", "title": "Skirmish Setup", "requires": ["CORE-1"]})

    payload = callTool("read_ticket", {"id": "CORE-1"})

    assert payload["requires"] == []
    assert payload["requiredBy"] == [{"id": "CORE-2", "title": "Skirmish Setup", "status": "todo", "priority": 2, "exists": True}]
    assert "# App Shell" in payload["body"]


def testReadTicketFlagsAMissingDependency(inRepo: Path) -> None:
    """
    A broken link is returned and marked rather than hidden, so the agent can see and fix it.
    """

    callTool("create_ticket", {"key": "CORE", "title": "Dangling", "requires": ["CORE-99"]})

    payload = callTool("read_ticket", {"id": "CORE-1"})

    assert payload["requires"][0]["exists"] is False
    assert payload["requires"][0]["id"] == "CORE-99"


def testReadTicketCarriesReadiness(inRepo: Path) -> None:
    """
    An agent already reading a ticket must not have to make a second call to find out whether it can act on it.
    """

    callTool("create_ticket", {"key": "CORE", "title": "App Shell"})
    callTool("create_ticket", {"key": "CORE", "title": "Skirmish Setup", "requires": ["CORE-1"]})

    assert callTool("read_ticket", {"id": "CORE-1"})["ready"] is True
    assert callTool("read_ticket", {"id": "CORE-2"})["ready"] is False


def testCheckReadyNamesWhatIsBlocking(inRepo: Path) -> None:
    """
    Refusing without naming the blocker would leave the agent to work out the reason, which is the inference this tool exists to replace.
    """

    callTool("create_ticket", {"key": "CORE", "title": "App Shell"})
    callTool("create_ticket", {"key": "CORE", "title": "Skirmish Setup", "requires": ["CORE-1"]})

    payload = callTool("check_ready", {"id": "CORE-2"})

    assert payload == {
        "id": "CORE-2",
        "ready": False,
        "blocked_by": [{"id": "CORE-1", "title": "App Shell", "status": "todo", "priority": 2, "exists": True}],
    }


def testCheckReadyClearsOnceTheDependencyIsDone(inRepo: Path) -> None:
    """
    Readiness is derived on every read rather than stored, so closing a dependency flips the answer with nothing else written.
    """

    callTool("create_ticket", {"key": "CORE", "title": "App Shell"})
    callTool("create_ticket", {"key": "CORE", "title": "Skirmish Setup", "requires": ["CORE-1"]})
    callTool("set_status", {"id": "CORE-1", "status": "done"})

    payload = callTool("check_ready", {"id": "CORE-2"})

    assert payload["ready"] is True
    assert payload["blocked_by"] == []


def testCheckReadyFlagsAMissingDependency(inRepo: Path) -> None:
    """
    A link the agent cannot follow blocks, and it is returned marked rather than reported as a plain refusal.
    """

    callTool("create_ticket", {"key": "CORE", "title": "Dangling", "requires": ["CORE-99"]})

    payload = callTool("check_ready", {"id": "CORE-1"})

    assert payload["ready"] is False
    assert payload["blocked_by"] == [{"id": "CORE-99", "title": None, "status": None, "priority": None, "exists": False}]


def testCheckReadyOnADoneTicketReturnsNoBlockers(inRepo: Path) -> None:
    """
    A finished ticket is not ready and nothing is blocking it, which is the one case where an empty blocker list means finished rather than unblocked.
    """

    callTool("create_ticket", {"key": "CORE", "title": "Shipped"})
    callTool("set_status", {"id": "CORE-1", "status": "done"})

    payload = callTool("check_ready", {"id": "CORE-1"})

    assert payload["ready"] is False
    assert payload["blocked_by"] == []


def testReadTicketCarriesUnknownFields(inRepo: Path) -> None:
    """
    A consumer repository's own frontmatter fields are visible to the agent rather than silently dropped.
    """

    path: Path = inRepo / "docs" / "tickets" / "todo" / "CORE-1_a.md"
    path.write_text(
        "---\nid: CORE-1\ntitle: T\nstatus: todo\npriority: 2\nrequires: []\nowner: brody\n---\n\n# T\n",
        encoding="utf-8",
        newline="\n",
    )

    assert callTool("read_ticket", {"id": "CORE-1"})["extra"] == {"owner": "brody"}


def testReadTicketCarriesMetadata(inRepo: Path) -> None:
    """
    Metadata is a recognized field, so it is returned in its own payload key rather than folded into `extra`.
    """

    callTool("create_ticket", {"key": "CORE", "title": "App Shell"})
    callTool("set_metadata", {"id": "CORE-1", "key": "video", "value": "2026-01-devlog"})

    payload = callTool("read_ticket", {"id": "CORE-1"})

    assert payload["metadata"] == {"video": "2026-01-devlog"}
    assert "video" not in payload["extra"]


def testSetMetadataOnlyTouchesTheNamedKey(inRepo: Path) -> None:
    """
    Two consumers writing different keys to the same ticket do not clobber each other.
    """

    callTool("create_ticket", {"key": "CORE", "title": "App Shell"})
    callTool("set_metadata", {"id": "CORE-1", "key": "video", "value": "2026-01-devlog"})

    payload = callTool("set_metadata", {"id": "CORE-1", "key": "reviewed", "value": True})

    assert payload["metadata"] == {"video": "2026-01-devlog", "reviewed": True}


def testSetMetadataWithNullValueRemovesTheKey(inRepo: Path) -> None:
    """
    A null value clears the entry rather than storing it as a null.
    """

    callTool("create_ticket", {"key": "CORE", "title": "App Shell"})
    callTool("set_metadata", {"id": "CORE-1", "key": "video", "value": "2026-01-devlog"})

    payload = callTool("set_metadata", {"id": "CORE-1", "key": "video", "value": None})

    assert payload["metadata"] == {}


def testSetMetadataRejectsAnUnknownId(inRepo: Path) -> None:
    """
    Setting metadata on a ticket that does not exist is an error rather than silently creating one.
    """

    with pytest.raises(Exception) as excInfo:
        callTool("set_metadata", {"id": "CORE-99", "key": "video", "value": "x"})

    assert "CORE-99" in str(excInfo.value)


def testReadTicketOnAnUnknownIdErrors(inRepo: Path) -> None:
    """
    Reading a ticket that does not exist is an error rather than an empty payload.
    """

    with pytest.raises(Exception) as excInfo:
        callTool("read_ticket", {"id": "CORE-99"})

    assert "CORE-99" in str(excInfo.value)


def testUpdateTicketChangesFieldsWithoutRenaming(inRepo: Path) -> None:
    """
    Retitling through the tool leaves the filename alone, so prose cross-references elsewhere survive.
    """

    callTool("create_ticket", {"key": "CORE", "title": "Original Title"})

    payload = callTool("update_ticket", {"id": "CORE-1", "title": "Renamed", "priority": 0})

    assert payload["ticket"]["title"] == "Renamed"
    assert payload["ticket"]["priority"] == 0
    assert (inRepo / "docs" / "tickets" / "todo" / "CORE-1_originalTitle.md").is_file()


def testUpdateTicketEditsRequiresInPlace(inRepo: Path) -> None:
    """
    The snake_case edit parameters reach the core's camelCase ones, so an agent can change one edge without restating the list.
    """

    callTool("create_ticket", {"key": "CORE", "title": "First"})
    callTool("create_ticket", {"key": "CORE", "title": "Second"})
    callTool("create_ticket", {"key": "CORE", "title": "Third", "requires": ["CORE-1"]})

    assert callTool("update_ticket", {"id": "CORE-3", "requires_add": ["CORE-2"]})["requires"] == ["CORE-1", "CORE-2"]
    assert callTool("update_ticket", {"id": "CORE-3", "requires_remove": ["CORE-1"]})["requires"] == ["CORE-2"]


def testUpdateTicketRefusesReplacingAndEditingAtOnce(inRepo: Path) -> None:
    """
    A replacement alongside an edit is a tool error rather than a silently resolved contradiction.
    """

    callTool("create_ticket", {"key": "CORE", "title": "First"})

    with pytest.raises(Exception) as excInfo:
        callTool("update_ticket", {"id": "CORE-1", "requires": ["GEN-1"], "requires_add": ["GEN-2"]})

    assert "cannot be combined" in str(excInfo.value)


def testUpdateTicketCannotChangeStatus(inRepo: Path) -> None:
    """
    Status is absent from this tool's schema, because changing it moves the file and that belongs to `set_status`.
    """

    updateTicket = [tool for tool in asyncio.run(server.mcp.list_tools()) if tool.name == "update_ticket"][0]

    assert "status" not in updateTicket.input_schema["properties"]


def testSetStatusMovesTheFile(inRepo: Path) -> None:
    """
    The frontmatter and the directory are written together, which is why an agent never needs to move a file itself.
    """

    callTool("create_ticket", {"key": "CORE", "title": "Skirmish Setup"})

    payload = callTool("set_status", {"id": "CORE-1", "status": "done"})

    assert payload["status"] == "done"
    assert not (inRepo / "docs" / "tickets" / "todo" / "CORE-1_skirmishSetup.md").exists()
    assert (inRepo / "docs" / "tickets" / "done" / "CORE-1_skirmishSetup.md").is_file()


def testSetStatusRejectsAnUnknownStatus(inRepo: Path) -> None:
    """
    The vocabulary is fixed, so an unrecognized status is refused rather than written.
    """

    callTool("create_ticket", {"key": "CORE", "title": "Skirmish Setup"})

    with pytest.raises(Exception) as excInfo:
        callTool("set_status", {"id": "CORE-1", "status": "blocked"})

    assert "blocked" in str(excInfo.value)


def testGraphReturnsMermaidAsAField(inRepo: Path) -> None:
    """
    The source is a field in a JSON payload rather than the whole body, so scope and size travel with it.
    """

    callTool("create_ticket", {"key": "CORE", "title": "App Shell"})

    payload = callTool("graph")

    assert payload["nodeCount"] == 1
    assert payload["scope"] is None
    assert payload["mermaid"].startswith("graph TD\n")
    assert "```" not in payload["mermaid"]


def testGraphScopesToATicket(inRepo: Path) -> None:
    """
    Scoping to an id narrows the graph and records what it was scoped to.
    """

    callTool("create_ticket", {"key": "CORE", "title": "App Shell"})
    callTool("create_ticket", {"key": "GEN", "title": "Unrelated"})

    payload = callTool("graph", {"id": "CORE-1"})

    assert payload["scope"] == "CORE-1"
    assert payload["nodeCount"] == 1


def testGraphScopesToAKeyAndMarksNeighbors(inRepo: Path) -> None:
    """
    A key-scoped graph shows where the key ends.
    """

    callTool("create_ticket", {"key": "CORE", "title": "App Shell"})
    callTool("create_ticket", {"key": "GEN", "title": "Battlescape", "requires": ["CORE-1"]})

    payload = callTool("graph", {"key": "GEN"})

    assert payload["scope"] == "GEN"
    assert "external" in payload["mermaid"]


def testListKeysReturnsEveryRegisteredKey(inRepo: Path) -> None:
    """
    An agent needs the full set of keys it may create under, with the descriptions that say which one fits.
    """

    payload = callTool("list_keys")

    assert [entry["key"] for entry in payload["registered"]] == ["CORE", "GEN", "HEAD", "META"]
    assert payload["registered"][0]["description"] == "tactical-sim core"


def testAddKeyMustTellTheAgentToAskFirst(inRepo: Path) -> None:
    """
    Adding a key is the user's decision, so the description is what stops an agent doing it unprompted.
    """

    addKey = [tool for tool in asyncio.run(server.mcp.list_tools()) if tool.name == "add_key"][0]

    assert "AskUserQuestion" in addKey.description


def testAddKeyWritesToConfiguration(inRepo: Path) -> None:
    """
    A new key lands in the configuration file, where it shows up in the git diff for a human to see.
    """

    payload = callTool("add_key", {"key": "SIM", "description": "simulation layer", "rationale": "the tick loop is its own area"})

    assert payload["key"] == "SIM"

    text: str = (inRepo / ".docket.toml").read_text(encoding="utf-8")

    assert "SIM" in text
    assert "the tick loop is its own area" in text


def testAddKeyThenCreateUnderItSucceeds(inRepo: Path) -> None:
    """
    A key is usable the moment it is added, so the round trip is asserted directly.
    """

    callTool("add_key", {"key": "SIM", "description": "simulation layer", "rationale": "needed"})

    assert callTool("create_ticket", {"key": "SIM", "title": "Tick loop"})["id"] == "SIM-1"


def testAddKeyRejectsAMalformedKey(inRepo: Path) -> None:
    """
    The key format is enforced, so a lowercase or hyphenated key is refused.
    """

    with pytest.raises(Exception):
        callTool("add_key", {"key": "sim", "description": "d", "rationale": "r"})


def testValidateReturnsStructuredFindings(inRepo: Path) -> None:
    """
    Findings cross the boundary as data rather than as prose the agent would have to parse.
    """

    callTool("create_ticket", {"key": "CORE", "title": "Dangling", "requires": ["CORE-99"]})

    payload = callTool("validate")

    assert payload["valid"] is False
    assert payload["errorCount"] == 1
    assert payload["findings"][0]["rule"] == "missingDependency"
    assert payload["findings"][0]["id"] == "CORE-1"


def testValidateOnAFreshRepositoryIsClean(inRepo: Path) -> None:
    """
    A repository with no tickets has nothing to report, in either severity.
    """

    payload = callTool("validate")

    assert payload["valid"] is True
    assert payload["errorCount"] == 0
    assert payload["warningCount"] == 0


def testTheBatchWorkflowRoundTrips(inRepo: Path) -> None:
    """
    The intended agent flow end to end: add a key the user agreed to, write a batch out of order, then validate it clean.
    """

    callTool("add_key", {"key": "SIM", "description": "simulation layer", "rationale": "needed"})

    # Written before its dependency exists, which warns rather than failing.
    first = callTool("create_ticket", {"key": "SIM", "title": "Tick loop", "requires": ["SIM-2"]})
    assert first["warnings"]

    callTool("create_ticket", {"key": "SIM", "title": "Clock"})

    findings = [finding for finding in callTool("validate")["findings"] if finding["severity"] == "error"]

    assert findings == []


def testPayloadsAreCompactJson(inRepo: Path) -> None:
    """
    An agent pays for every token, so payloads carry no indentation padding.
    """

    callTool("create_ticket", {"key": "CORE", "title": "App Shell"})

    result: CallToolResult = asyncio.run(server.mcp.call_tool("list_tickets", {}))
    text: str = result.content[0].text

    assert text.startswith('{"count":1')
    assert "\n" not in text


def testTheServerNeverWritesToStdout(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    The MCP stdio transport owns stdout, so a single stray byte from a handler would corrupt the protocol.
    """

    callTool("create_ticket", {"key": "CORE", "title": "App Shell"})
    callTool("list_tickets")
    callTool("validate")

    assert capsys.readouterr().out == ""


def testRichIsNotImportedByTheServerModule() -> None:
    """
    `rich` emits escape sequences, so importing it anywhere in this module risks corrupting the transport.
    """

    source: str = Path(server.__file__).read_text(encoding="utf-8")

    assert "import rich" not in source
    assert "from rich" not in source
