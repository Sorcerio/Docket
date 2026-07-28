"""
Deploy Tests

Cover the four deploy steps, idempotency, the `.mcp.json` merge, and what upgrade refuses to touch.
"""

# MARK: Imports

import json
from pathlib import Path
from typing import Any

import pytest

from docket.core.config import Config, loadConfig
from docket.core.deploy import DeployReport, deploy, readTemplate, upgrade
from docket.core.errors import DeployError

# MARK: Functions


def readMcp(root: Path) -> dict[str, Any]:
    """
    Read a repository's `.mcp.json`.

    root: The repository root.

    Returns the parsed document.
    """

    return json.loads((root / ".mcp.json").read_text(encoding="utf-8"))


def testDeployPerformsAllFourSteps(tmp_path: Path) -> None:
    """
    A fresh repository receives the ticket directories, the instructions, the configuration, and the server entry.
    """

    deploy(tmp_path)

    assert (tmp_path / ".docket.toml").is_file()
    assert (tmp_path / "docs" / "tickets" / "todo").is_dir()
    assert (tmp_path / "docs" / "tickets" / "done").is_dir()
    assert (tmp_path / "docs" / "tickets" / "CLAUDE.md").is_file()
    assert (tmp_path / ".mcp.json").is_file()


def testDeployedConfigurationHasAnEmptyKeyRegistry(tmp_path: Path) -> None:
    """
    The user populates the registry themselves, so nothing is invented for them.
    """

    deploy(tmp_path)

    config: Config = loadConfig(tmp_path / ".docket.toml")

    assert config.registeredKeys == {}


def testDeployedConfigurationCarriesNoStatusesKey(tmp_path: Path) -> None:
    """
    The status vocabulary is fixed in the tool, so the configuration must not suggest otherwise.
    """

    deploy(tmp_path)

    assert "statuses" not in (tmp_path / ".docket.toml").read_text(encoding="utf-8")
    assert "statuses" not in readTemplate("docket.toml")


def testTheServerEntryPointsAtTheConsoleScript(tmp_path: Path) -> None:
    """
    The consumer never receives the tool's source, so the entry relies on the globally installed script.
    """

    deploy(tmp_path)

    assert readMcp(tmp_path)["mcpServers"]["docket"] == {"type": "stdio", "command": "docket-mcp", "args": []}


def testDeployIsIdempotent(tmp_path: Path) -> None:
    """
    Running deploy twice changes nothing that matters and reports what it kept.
    """

    deploy(tmp_path)
    (tmp_path / ".docket.toml").write_text('root = "docs/tickets"\n\n[keys]\nCORE = "core"\n', encoding="utf-8", newline="\n")

    report: DeployReport = deploy(tmp_path)

    # The curated registry survives, which is the whole point of not rewriting the configuration.
    assert loadConfig(tmp_path / ".docket.toml").registeredKeys == {"CORE": "core"}
    assert tmp_path / ".docket.toml" in report.skipped


def testDeployReportsWhatItCreatedAndKept(tmp_path: Path) -> None:
    """
    Deploy is idempotent, so the useful information is which steps actually changed something.
    """

    first: DeployReport = deploy(tmp_path)

    assert tmp_path / ".docket.toml" in first.created
    assert tmp_path / ".mcp.json" in first.created

    second: DeployReport = deploy(tmp_path)

    assert second.created == []
    assert tmp_path / ".mcp.json" in second.updated


def testDeployPreservesOtherMcpServers(tmp_path: Path) -> None:
    """
    The merge is the step most likely to cause damage, so every other entry survives it untouched.
    """

    (tmp_path / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"other": {"command": "other-server", "args": ["--flag"]}}}, indent=2),
        encoding="utf-8",
        newline="\n",
    )

    deploy(tmp_path)

    servers = readMcp(tmp_path)["mcpServers"]

    assert servers["other"] == {"command": "other-server", "args": ["--flag"]}
    assert "docket" in servers


def testDeployPreservesUnrelatedTopLevelKeys(tmp_path: Path) -> None:
    """
    Anything else in the file is data the repository owns, so it is carried across.
    """

    (tmp_path / ".mcp.json").write_text(json.dumps({"someOtherSetting": True, "mcpServers": {}}), encoding="utf-8", newline="\n")

    deploy(tmp_path)

    assert readMcp(tmp_path)["someOtherSetting"] is True


def testDeployReplacesAnExistingDocketEntry(tmp_path: Path) -> None:
    """
    A stale docket entry is corrected rather than duplicated.
    """

    (tmp_path / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"docket": {"command": "old-command", "args": ["--stale"]}}}),
        encoding="utf-8",
        newline="\n",
    )

    deploy(tmp_path)

    assert readMcp(tmp_path)["mcpServers"]["docket"]["command"] == "docket-mcp"
    assert readMcp(tmp_path)["mcpServers"]["docket"]["args"] == []


def testDeployCreatesMcpConfigWhenAbsent(tmp_path: Path) -> None:
    """
    A repository with no `.mcp.json` gets one rather than an error.
    """

    deploy(tmp_path)

    assert readMcp(tmp_path)["mcpServers"]["docket"]["command"] == "docket-mcp"


def testMalformedMcpConfigIsRefusedNotClobbered(tmp_path: Path) -> None:
    """
    Overwriting an unparseable file would destroy whatever was in it, so the deploy fails instead.
    """

    original: str = "{ this is not json"
    (tmp_path / ".mcp.json").write_text(original, encoding="utf-8", newline="\n")

    with pytest.raises(DeployError) as excInfo:
        deploy(tmp_path)

    assert "left untouched" in str(excInfo.value)
    assert (tmp_path / ".mcp.json").read_text(encoding="utf-8") == original


def testAnMcpConfigHoldingAnArrayIsRefused(tmp_path: Path) -> None:
    """
    An entry cannot be merged into a top-level array, and replacing it would destroy the contents.
    """

    (tmp_path / ".mcp.json").write_text("[1, 2, 3]", encoding="utf-8", newline="\n")

    with pytest.raises(DeployError):
        deploy(tmp_path)


def testAWronglyTypedServersKeyIsRefused(tmp_path: Path) -> None:
    """
    The same protection applies one level down.
    """

    (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": "not an object"}), encoding="utf-8", newline="\n")

    with pytest.raises(DeployError):
        deploy(tmp_path)


def testDeployRefusesANonDirectory(tmp_path: Path) -> None:
    """
    A target that is not a directory is refused before anything is written.
    """

    target: Path = tmp_path / "afile.txt"
    target.write_text("hello", encoding="utf-8", newline="\n")

    with pytest.raises(DeployError):
        deploy(target)

    with pytest.raises(DeployError):
        deploy(tmp_path / "does-not-exist")


def testDeployHonoursACustomRootFromAnExistingConfiguration(tmp_path: Path) -> None:
    """
    A repository that already chose its own layout keeps it, since the configuration is read rather than assumed.
    """

    (tmp_path / ".docket.toml").write_text('root = "planning"\ntodoDir = "open"\ndoneDir = "closed"\n', encoding="utf-8", newline="\n")

    deploy(tmp_path)

    assert (tmp_path / "planning" / "open").is_dir()
    assert (tmp_path / "planning" / "closed").is_dir()
    assert (tmp_path / "planning" / "CLAUDE.md").is_file()


def testUpgradeRefreshesTheInstructions(tmp_path: Path) -> None:
    """
    Upgrade exists to bring a consumer's templates back in line with the tool.
    """

    deploy(tmp_path)

    claudePath: Path = tmp_path / "docs" / "tickets" / "CLAUDE.md"
    claudePath.write_text("stale content\n", encoding="utf-8", newline="\n")

    upgrade(tmp_path)

    assert claudePath.read_text(encoding="utf-8") == readTemplate("CLAUDE.md")


def testUpgradeNeverTouchesTheKeyRegistry(tmp_path: Path) -> None:
    """
    The registry is curated by a human, so upgrade leaves the configuration completely alone.
    """

    deploy(tmp_path)

    configText: str = '# My own comment.\nroot = "docs/tickets"\n\n[keys]\nCORE = "core"\n'
    (tmp_path / ".docket.toml").write_text(configText, encoding="utf-8", newline="\n")

    report: DeployReport = upgrade(tmp_path)

    assert (tmp_path / ".docket.toml").read_text(encoding="utf-8") == configText
    assert tmp_path / ".docket.toml" in report.skipped


def testUpgradeNeverTouchesTickets(tmp_path: Path) -> None:
    """
    Tickets are the repository's data, not docket's, so an upgrade must not rewrite them.
    """

    deploy(tmp_path)

    ticketPath: Path = tmp_path / "docs" / "tickets" / "todo" / "CORE-1_a.md"
    original: str = "---\nid: CORE-1\ntitle: T\nstatus: todo\npriority: 2\nrequires: []\n---\n\n# T\n"
    ticketPath.write_text(original, encoding="utf-8", newline="\n")

    upgrade(tmp_path)

    assert ticketPath.read_text(encoding="utf-8") == original


def testUpgradeRepairsTheServerEntry(tmp_path: Path) -> None:
    """
    A consumer whose entry drifted gets it put back, which is half the reason upgrade exists.
    """

    deploy(tmp_path)
    (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": {}}), encoding="utf-8", newline="\n")

    upgrade(tmp_path)

    assert readMcp(tmp_path)["mcpServers"]["docket"]["command"] == "docket-mcp"


def testUpgradeOnAnUndeployedRepositoryFails(tmp_path: Path) -> None:
    """
    There is nothing to upgrade without a configuration, and the message names the command that fixes it.
    """

    with pytest.raises(DeployError) as excInfo:
        upgrade(tmp_path)

    assert "docket deploy" in str(excInfo.value)


def testTemplatesShipWithThePackage(tmp_path: Path) -> None:
    """
    The templates are package data, so they must be readable from the installed package rather than from the source tree.
    """

    assert "# Tickets" in readTemplate("CLAUDE.md")
    assert "[keys]" in readTemplate("docket.toml")


def testTheDeployedInstructionsCoverTheLoadBearingRules(tmp_path: Path) -> None:
    """
    This template is the single most important deliverable for agent behavior, so its required content is asserted directly.
    """

    text: str = readTemplate("CLAUDE.md")

    # Every frontmatter field is explained.
    for fieldName in ("`id`", "`title`", "`status`", "`priority`", "`requires`"):
        assert fieldName in text

    # Moving and renaming are forbidden, and the frontmatter is named as the tool's.
    assert "never move a file" in text.lower()
    assert "by hand" in text
    assert "frontmatter block, and where the file lives, belong to the tool" in text

    # One-way edges, with the reverse direction named.
    assert "requiredBy" in text
    assert "never declares what it blocks" in text

    # Keys are closed, with the listing tool, the adding tool, and the requirement to ask the user first all named.
    assert "list_keys" in text
    assert "add_key" in text
    assert "AskUserQuestion" in text

    # The instruction carried over from the source repository, which is load-bearing.
    assert "assumptions" in text
    assert "questions" in text


def testTheDeployedInstructionsPermitEditingTheBody() -> None:
    """
    There is deliberately no tool for editing a body, so hand-editing prose is the intended path and the template must say so.

    Wording that forbids touching ticket files outright would forbid the only way to revise the prose the design says the writer owns.
    """

    text: str = readTemplate("CLAUDE.md")

    assert "The body is yours" in text
    assert "yours to edit directly" in text
    assert "There is no MCP tool for editing a body" in text


def testTheDeployedInstructionsUseNoEmDashes() -> None:
    """
    The repository's style forbids them, including in shipped output.
    """

    assert "—" not in readTemplate("CLAUDE.md")
    assert "—" not in readTemplate("docket.toml")
