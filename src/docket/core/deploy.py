"""
Docket Deploy

Installing docket's data and configuration into a consumer repository.

The consumer receives ticket directories, a `CLAUDE.md`, a `.docket.toml`, one entry in `.mcp.json`, and one entry in `.gitignore`. It never receives the tool's source.
"""

# MARK: Imports

import json
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Any

from docket.core.atomic import writeTextAtomic
from docket.core.config import CONFIG_FILENAME, Config, loadConfig
from docket.core.errors import DeployError
from docket.core.lock import LOCK_FILENAME

# MARK: Constants

# The template files shipped inside the package.
TEMPLATE_CLAUDE: str = "CLAUDE.md"
TEMPLATE_CONFIG: str = "docket.toml"

# What the consumer repository receives.
CLAUDE_FILENAME: str = "CLAUDE.md"
MCP_FILENAME: str = ".mcp.json"
GITIGNORE_FILENAME: str = ".gitignore"

# The lock file is machine state, so it is ignored rather than committed. The trailing wildcard covers the journal the lock's own storage may write beside it.
LOCK_IGNORE_ENTRY: str = f"{LOCK_FILENAME}*"
LOCK_IGNORE_COMMENT: str = "# Docket's cross-process lock. Machine state, never committed."

# The key docket claims inside `.mcp.json`, and the console script it points at.
MCP_SERVERS_KEY: str = "mcpServers"
MCP_SERVER_NAME: str = "docket"
MCP_COMMAND: str = "docket-mcp"

# MARK: Classes


@dataclass
class DeployReport:
    """
    What a deploy or upgrade actually did.

    Deploy is idempotent, so the caller needs to be told which steps changed something and which were already satisfied.
    """

    # MARK: Properties

    created: list[Path] = field(default_factory=list)
    updated: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)

    # MARK: Functions

    def record(self, path: Path, existed: bool) -> None:
        """
        Note that a path was written.

        path: The path written.
        existed: Whether the file was already there.
        """

        (self.updated if existed else self.created).append(path)

    def toDict(self) -> dict[str, list[str]]:
        """
        Build the serializable form.

        Returns the report as plain data.
        """

        return {
            "created": [str(path) for path in self.created],
            "updated": [str(path) for path in self.updated],
            "skipped": [str(path) for path in self.skipped],
        }


# MARK: Functions


def deploy(target: Path) -> DeployReport:
    """
    Install docket into a consumer repository.

    This is idempotent. Missing pieces are created and templates are refreshed, but an existing `.docket.toml` is never rewritten, because it holds the key registry a human has curated.

    target: The repository root to deploy into.

    Returns what was done.
    """

    root: Path = _requireDirectory(target)
    report: DeployReport = DeployReport()

    # The configuration has to land first, since every other path derives from it.
    configPath: Path = root / CONFIG_FILENAME
    if configPath.exists():
        report.skipped.append(configPath)
    else:
        _write(configPath, readTemplate(TEMPLATE_CONFIG))
        report.created.append(configPath)

    config: Config = loadConfig(configPath)

    # Both status directories, so a freshly deployed repository has somewhere to put a ticket.
    for directory in (config.todoPath, config.donePath):
        if directory.is_dir():
            report.skipped.append(directory)
        else:
            directory.mkdir(parents=True, exist_ok=True)
            report.created.append(directory)

    _writeClaudeTemplate(config, report)
    _mergeMcpConfig(root, report)
    _ignoreLockFile(root, report)

    return report


def upgrade(target: Path) -> DeployReport:
    """
    Refresh the deployed templates in a consumer repository.

    This rewrites what docket owns and nothing else. The configuration is left alone because it holds the key registry, and tickets are left alone because they are the repository's data.
    The `.gitignore` is the one file docket does not own but still appends to, since a repository deployed before the lock existed has no entry for it and would otherwise commit one.

    target: The repository root to upgrade.

    Returns what was done.
    """

    root: Path = _requireDirectory(target)

    configPath: Path = root / CONFIG_FILENAME
    if not configPath.is_file():
        raise DeployError(f"No {CONFIG_FILENAME} in {root}. Run 'docket deploy {root}' first.")

    report: DeployReport = DeployReport()
    config: Config = loadConfig(configPath)

    # The configuration is deliberately untouched, and saying so is more useful than staying silent about it.
    report.skipped.append(configPath)

    _writeClaudeTemplate(config, report)
    _mergeMcpConfig(root, report)
    _ignoreLockFile(root, report)

    return report


def readTemplate(name: str) -> str:
    """
    Read a template shipped inside the package.

    name: The template filename.

    Returns the template text.
    """

    return files("docket").joinpath("templates", name).read_text(encoding="utf-8")


def _writeClaudeTemplate(config: Config, report: DeployReport) -> None:
    """
    Write the agent instructions into the ticket root.

    This lands beside the tickets rather than at the repository root, so an agent opening the ticket directory reads it in place.

    config: The loaded configuration, naming the ticket root.
    report: The report to record the write against.
    """

    path: Path = config.rootPath / CLAUDE_FILENAME
    existed: bool = path.exists()

    _write(path, readTemplate(TEMPLATE_CLAUDE))
    report.record(path, existed)


def _mergeMcpConfig(root: Path, report: DeployReport) -> None:
    """
    Add docket's server entry to the repository's `.mcp.json`.

    This is the step most likely to damage something, so it reads, modifies, and writes rather than overwriting. Docket's own entry is replaced and every other entry is preserved. A file that is not valid JSON is refused rather than clobbered.

    root: The repository root.
    report: The report to record the write against.
    """

    path: Path = root / MCP_FILENAME
    existed: bool = path.exists()

    document: dict[str, Any] = {}
    if existed:
        try:
            loaded: Any = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise DeployError(f"{path} is not valid JSON, so it was left untouched: {error}") from error

        # A top-level array or string is not something an entry can be merged into, and overwriting it would destroy whatever it was.
        if not isinstance(loaded, dict):
            raise DeployError(f"{path} does not hold a JSON object, so it was left untouched.")

        document = loaded

    servers: Any = document.get(MCP_SERVERS_KEY, {})
    if not isinstance(servers, dict):
        raise DeployError(f"'{MCP_SERVERS_KEY}' in {path} is not a JSON object, so it was left untouched.")

    # Replace only docket's entry, leaving every other server exactly as it was.
    servers[MCP_SERVER_NAME] = {"type": "stdio", "command": MCP_COMMAND, "args": []}
    document[MCP_SERVERS_KEY] = servers

    _write(path, json.dumps(document, indent=2) + "\n")
    report.record(path, existed)


def _ignoreLockFile(root: Path, report: DeployReport) -> None:
    """
    Ensure the repository's `.gitignore` covers docket's lock file.

    The lock file is machine state rather than repository content, so committing it would put one developer's lock in another developer's checkout.
    Only the entry is appended. Everything already in the file is preserved, and a file that already covers the lock is left exactly as it is.

    root: The repository root.
    report: The report to record the write against.
    """

    path: Path = root / GITIGNORE_FILENAME
    existed: bool = path.exists()

    lines: list[str] = []
    if existed:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as error:
            raise DeployError(f"Could not read {path}: {error}") from error

    # An entry already present means there is nothing to do, and rewriting the file to say so would only churn it.
    if any(line.strip() == LOCK_IGNORE_ENTRY for line in lines):
        report.skipped.append(path)

        return

    # Separate the entry from whatever came before it, so it does not land on the end of an existing line or crowd an unrelated block.
    if lines and lines[-1].strip():
        lines.append("")

    lines.extend([LOCK_IGNORE_COMMENT, LOCK_IGNORE_ENTRY])

    _write(path, "\n".join(lines) + "\n")
    report.record(path, existed)


def _requireDirectory(target: Path) -> Path:
    """
    Resolve a deploy target, refusing anything that is not an existing directory.

    target: The path given by the caller.

    Returns the resolved directory.
    """

    resolved: Path = target.resolve()

    if not resolved.is_dir():
        raise DeployError(f"{resolved} is not a directory.")

    return resolved


def _write(path: Path, text: str) -> None:
    """
    Write a file, creating its parent directories.

    path: Where to write.
    text: What to write.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    writeTextAtomic(path, text)
