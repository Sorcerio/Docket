"""
MCP Server Tests

Drive tools through the real MCP dispatch path, covering the wire surface, payload shapes, and error propagation.
"""

# MARK: Imports

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Iterator

import pytest

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

    content, _ = asyncio.run(server.mcp.call_tool(name, arguments or {}))

    return json.loads(content[0].text)


def toolNames() -> list[str]:
    """
    List every registered tool name.

    Returns the names.
    """

    return [tool.name for tool in asyncio.run(server.mcp.list_tools())]


def testEveryDocumentedToolIsRegistered() -> None:
    """
    The surface is exactly the nine tools the design specifies, no more and no fewer.
    """

    assert sorted(toolNames()) == sorted(
        ["list_tickets", "read_ticket", "create_ticket", "update_ticket", "set_status", "graph", "list_keys", "propose_key", "validate"]
    )


def testToolNamesAndParametersAreSnakeCase() -> None:
    """
    The wire surface follows the MCP ecosystem convention, so no camelCase name or parameter may leak out of the core.
    """

    for tool in asyncio.run(server.mcp.list_tools()):
        assert tool.name.islower()
        assert "_" in tool.name or tool.name.isalpha()

        for parameter in tool.inputSchema.get("properties", {}):
            assert parameter == parameter.lower()
            assert not any(character.isupper() for character in parameter)


def testPriorityMaxIsSpelledForTheWire() -> None:
    """
    The core calls this `priorityMax`, and the mapping to the wire spelling happens in the server and nowhere else.
    """

    listTickets = [tool for tool in asyncio.run(server.mcp.list_tools()) if tool.name == "list_tickets"][0]

    assert "priority_max" in listTickets.inputSchema["properties"]
    assert "priorityMax" not in listTickets.inputSchema["properties"]


def testCreateTicketDescriptionDirectsTheAgentToListKeys() -> None:
    """
    An agent must not guess a key, so the description names the tool that shows the valid ones.
    """

    createTicket = [tool for tool in asyncio.run(server.mcp.list_tools()) if tool.name == "create_ticket"][0]

    assert "list_keys" in createTicket.description
    assert "propose_key" in createTicket.description


def testServerInstructionsCoverTheLoadBearingRules() -> None:
    """
    The instructions are what an agent reads before calling anything, so the rules it could otherwise violate are stated there.
    """

    instructions: str = server.SERVER_INSTRUCTIONS

    assert "never move a file" in instructions.lower()
    assert "requires" in instructions
    assert "list_keys" in instructions

    # The body is editable by hand, and saying otherwise would forbid the only way to revise prose.
    assert "edit directly and freely" in instructions


def testCreateTicketReturnsTheNewId(inRepo: Path) -> None:
    """
    Creation allocates the id and reports it, since the caller cannot know it in advance.
    """

    payload = callTool("create_ticket", {"key": "CORE", "title": "Skirmish setup", "body": "Goal: one battle."})

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

    assert "propose_key" in str(excInfo.value)


def testCreateTicketUnderAProposedKeyWorks(inRepo: Path) -> None:
    """
    A proposed key is usable immediately, which is what stops a batch stranding mid-flight.
    """

    assert callTool("create_ticket", {"key": "META", "title": "Campaign layer"})["id"] == "META-1"


def testListTicketsNeverReturnsBodies(inRepo: Path) -> None:
    """
    An agent listing forty tickets must not pay for forty bodies.
    """

    callTool("create_ticket", {"key": "CORE", "title": "App shell", "body": "A very long body that must not appear in a listing."})

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

    callTool("create_ticket", {"key": "CORE", "title": "App shell"})
    callTool("create_ticket", {"key": "CORE", "title": "Skirmish setup", "requires": ["CORE-1"]})

    payload = callTool("read_ticket", {"id": "CORE-1"})

    assert payload["requires"] == []
    assert payload["requiredBy"] == [{"id": "CORE-2", "title": "Skirmish setup", "status": "todo", "priority": 2, "exists": True}]
    assert "# App shell" in payload["body"]


def testReadTicketFlagsAMissingDependency(inRepo: Path) -> None:
    """
    A broken link is returned and marked rather than hidden, so the agent can see and fix it.
    """

    callTool("create_ticket", {"key": "CORE", "title": "Dangling", "requires": ["CORE-99"]})

    payload = callTool("read_ticket", {"id": "CORE-1"})

    assert payload["requires"][0]["exists"] is False
    assert payload["requires"][0]["id"] == "CORE-99"


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

    callTool("create_ticket", {"key": "CORE", "title": "Original title"})

    payload = callTool("update_ticket", {"id": "CORE-1", "title": "Renamed", "priority": 0})

    assert payload["ticket"]["title"] == "Renamed"
    assert payload["ticket"]["priority"] == 0
    assert (inRepo / "docs" / "tickets" / "todo" / "CORE-1_originalTitle.md").is_file()


def testUpdateTicketCannotChangeStatus(inRepo: Path) -> None:
    """
    Status is absent from this tool's schema, because changing it moves the file and that belongs to `set_status`.
    """

    updateTicket = [tool for tool in asyncio.run(server.mcp.list_tools()) if tool.name == "update_ticket"][0]

    assert "status" not in updateTicket.inputSchema["properties"]


def testSetStatusMovesTheFile(inRepo: Path) -> None:
    """
    The frontmatter and the directory are written together, which is why an agent never needs to move a file itself.
    """

    callTool("create_ticket", {"key": "CORE", "title": "Skirmish setup"})

    payload = callTool("set_status", {"id": "CORE-1", "status": "done"})

    assert payload["status"] == "done"
    assert not (inRepo / "docs" / "tickets" / "todo" / "CORE-1_skirmishSetup.md").exists()
    assert (inRepo / "docs" / "tickets" / "done" / "CORE-1_skirmishSetup.md").is_file()


def testSetStatusRejectsAnUnknownStatus(inRepo: Path) -> None:
    """
    The vocabulary is fixed, so an unrecognized status is refused rather than written.
    """

    callTool("create_ticket", {"key": "CORE", "title": "Skirmish setup"})

    with pytest.raises(Exception) as excInfo:
        callTool("set_status", {"id": "CORE-1", "status": "blocked"})

    assert "blocked" in str(excInfo.value)


def testGraphReturnsMermaidAsAField(inRepo: Path) -> None:
    """
    The source is a field in a JSON payload rather than the whole body, so scope and size travel with it.
    """

    callTool("create_ticket", {"key": "CORE", "title": "App shell"})

    payload = callTool("graph")

    assert payload["nodeCount"] == 1
    assert payload["scope"] is None
    assert payload["mermaid"].startswith("graph TD\n")
    assert "```" not in payload["mermaid"]


def testGraphScopesToATicket(inRepo: Path) -> None:
    """
    Scoping to an id narrows the graph and records what it was scoped to.
    """

    callTool("create_ticket", {"key": "CORE", "title": "App shell"})
    callTool("create_ticket", {"key": "GEN", "title": "Unrelated"})

    payload = callTool("graph", {"id": "CORE-1"})

    assert payload["scope"] == "CORE-1"
    assert payload["nodeCount"] == 1


def testGraphScopesToAKeyAndMarksNeighbors(inRepo: Path) -> None:
    """
    A key-scoped graph shows where the key ends.
    """

    callTool("create_ticket", {"key": "CORE", "title": "App shell"})
    callTool("create_ticket", {"key": "GEN", "title": "Battlescape", "requires": ["CORE-1"]})

    payload = callTool("graph", {"key": "GEN"})

    assert payload["scope"] == "GEN"
    assert "external" in payload["mermaid"]


def testListKeysSeparatesRegisteredFromProposed(inRepo: Path) -> None:
    """
    An agent needs to know which keys are approved and which are still pending, along with the rationale behind a proposal.
    """

    payload = callTool("list_keys")

    assert [entry["key"] for entry in payload["registered"]] == ["CORE", "GEN", "HEAD"]
    assert payload["proposed"][0]["key"] == "META"
    assert payload["proposed"][0]["rationale"] == "the strategic layer is a distinct area"


def testProposeKeyWritesToConfiguration(inRepo: Path) -> None:
    """
    A proposal lands in the configuration file, where it shows up in the git diff for a human to see.
    """

    payload = callTool("propose_key", {"key": "SIM", "description": "simulation layer", "rationale": "the tick loop is its own area"})

    assert payload["key"] == "SIM"
    assert payload["approved"] is False

    text: str = (inRepo / ".docket.toml").read_text(encoding="utf-8")

    assert "SIM" in text
    assert "the tick loop is its own area" in text


def testProposeKeyThenCreateUnderItSucceeds(inRepo: Path) -> None:
    """
    This is the whole point of the soft gate, so the round trip is asserted directly.
    """

    callTool("propose_key", {"key": "SIM", "description": "simulation layer", "rationale": "needed"})

    assert callTool("create_ticket", {"key": "SIM", "title": "Tick loop"})["id"] == "SIM-1"


def testProposeKeyRejectsAMalformedKey(inRepo: Path) -> None:
    """
    The key format is enforced, so a lowercase or hyphenated proposal is refused.
    """

    with pytest.raises(Exception):
        callTool("propose_key", {"key": "sim", "description": "d", "rationale": "r"})


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


def testValidateIsValidWithWarningsAlone(inRepo: Path) -> None:
    """
    A pending proposal informs without invalidating, matching the CLI's exit-code behavior.
    """

    payload = callTool("validate")

    assert payload["valid"] is True
    assert payload["warningCount"] == 2


def testTheBatchWorkflowRoundTrips(inRepo: Path) -> None:
    """
    The intended agent flow end to end: propose a key, write a batch out of order, then validate it clean.
    """

    callTool("propose_key", {"key": "SIM", "description": "simulation layer", "rationale": "needed"})

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

    callTool("create_ticket", {"key": "CORE", "title": "App shell"})

    content, _ = asyncio.run(server.mcp.call_tool("list_tickets", {}))
    text: str = content[0].text

    assert text.startswith('{"count":1')
    assert "\n" not in text


def testTheServerNeverWritesToStdout(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    The MCP stdio transport owns stdout, so a single stray byte from a handler would corrupt the protocol.
    """

    callTool("create_ticket", {"key": "CORE", "title": "App shell"})
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
