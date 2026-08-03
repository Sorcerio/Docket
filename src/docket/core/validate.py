"""
Docket Validate

Every integrity rule, returned as structured findings.

This is what makes the system trustworthy under a pre-commit hook or in CI, so it loads once and derives everything else from that single pass.
"""

# MARK: Imports

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from docket.core.config import Config
from docket.core.graph import ResolvedGraph, findCycles, resolveGraph
from docket.core.store import Store, TicketSet
from docket.core.ticket import STATUSES, Ticket

# MARK: Constants

# The two severities a finding can carry. An error blocks, a warning informs.
SEVERITY_ERROR: str = "error"
SEVERITY_WARNING: str = "warning"

# Rule identifiers, so a consumer can filter or suppress by rule rather than by matching message text.
RULE_UNREADABLE: str = "unreadableTicket"
RULE_MISSING_DEPENDENCY: str = "missingDependency"
RULE_CYCLE: str = "dependencyCycle"
RULE_DUPLICATE_ID: str = "duplicateId"
RULE_UNKNOWN_KEY: str = "unknownKey"
RULE_FILENAME_MISMATCH: str = "filenameMismatch"
RULE_STATUS_DIRECTORY: str = "statusDirectoryMismatch"
RULE_PRIORITY_RANGE: str = "priorityOutOfRange"
RULE_UNKNOWN_STATUS: str = "unknownStatus"

# MARK: Classes


@dataclass(frozen=True)
class Finding:
    """
    One validation result.
    """

    # MARK: Properties

    severity: str
    rule: str
    message: str

    # The ticket the finding concerns, absent for a finding about a key or a file that never parsed.
    ticketId: Optional[str] = None

    # The file the finding concerns, absent for a finding about configuration.
    path: Optional[Path] = None

    # MARK: Functions

    def toDict(self) -> dict[str, Optional[str]]:
        """
        Build the serializable form, used by the MCP surface.

        Returns the finding as plain data.
        """

        return {
            "severity": self.severity,
            "rule": self.rule,
            "message": self.message,
            "id": self.ticketId,
            "path": str(self.path) if self.path is not None else None,
        }


@dataclass
class ValidationReport:
    """
    Every finding from one validation pass.
    """

    # MARK: Properties

    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> list[Finding]:
        """
        Findings that block.
        """

        return [finding for finding in self.findings if finding.severity == SEVERITY_ERROR]

    @property
    def warnings(self) -> list[Finding]:
        """
        Findings that inform.
        """

        return [finding for finding in self.findings if finding.severity == SEVERITY_WARNING]

    @property
    def isValid(self) -> bool:
        """
        Whether the set is free of errors. Warnings alone still count as valid.
        """

        return not self.errors

    # MARK: Functions

    def toDict(self) -> dict[str, object]:
        """
        Build the serializable form, used by the MCP surface.

        Returns the report as plain data.
        """

        return {
            "valid": self.isValid,
            "errorCount": len(self.errors),
            "warningCount": len(self.warnings),
            "findings": [finding.toDict() for finding in self.findings],
        }


# MARK: Functions


def validate(store: Store, ticketSet: Optional[TicketSet] = None) -> ValidationReport:
    """
    Run every rule against a ticket set.

    store: The store naming the configuration and the ticket root.
    ticketSet: An already-loaded set, loaded here when omitted.

    Returns the report.
    """

    loaded: TicketSet = ticketSet if ticketSet is not None else store.loadAll()
    config: Config = store.config
    graph: ResolvedGraph = resolveGraph(loaded)

    findings: list[Finding] = []

    # Report what could not be read first, since every later rule is blind to those files.
    findings.extend(_checkLoadFailures(loaded))
    findings.extend(_checkDuplicateIds(loaded))

    # Per-ticket rules, walked once in sorted order so output is stable.
    for ticket in loaded.sorted():
        findings.extend(_checkDependencies(ticket, loaded))
        findings.extend(_checkKey(ticket, config))
        findings.extend(_checkFilename(ticket))
        findings.extend(_checkStatusDirectory(ticket, store))
        findings.extend(_checkPriority(ticket, config))
        findings.extend(_checkStatus(ticket))

    findings.extend(_checkCycles(graph))

    return ValidationReport(findings=findings)


def _checkLoadFailures(ticketSet: TicketSet) -> list[Finding]:
    """
    Report files under a status directory that could not be read as tickets.

    ticketSet: The loaded set.

    Returns the findings.
    """

    return [
        Finding(severity=SEVERITY_ERROR, rule=RULE_UNREADABLE, message=f"{failure.path.name} could not be read as a ticket: {failure.message}", path=failure.path)
        for failure in ticketSet.failures
    ]


def _checkDuplicateIds(ticketSet: TicketSet) -> list[Finding]:
    """
    Report two tickets claiming one id.

    This is the collision two branches minting under the same key produce, and catching it here at merge time is the accepted cost of having no counter file.

    ticketSet: The loaded set.

    Returns the findings.
    """

    return [
        Finding(
            severity=SEVERITY_ERROR,
            rule=RULE_DUPLICATE_ID,
            message=f"Id '{duplicate.id}' is claimed by both {duplicate.existingPath.name} and {duplicate.path.name}.",
            ticketId=duplicate.id,
            path=duplicate.path,
        )
        for duplicate in ticketSet.duplicates
    ]


def _checkDependencies(ticket: Ticket, ticketSet: TicketSet) -> list[Finding]:
    """
    Report a `requires` entry naming an id that does not exist.

    ticket: The ticket to check.
    ticketSet: The loaded set to resolve against.

    Returns the findings.
    """

    return [
        Finding(
            severity=SEVERITY_ERROR,
            rule=RULE_MISSING_DEPENDENCY,
            message=f"Ticket '{ticket.id}' requires '{requiredId}', which does not exist.",
            ticketId=ticket.id,
            path=ticket.path,
        )
        for requiredId in ticket.requires
        if requiredId not in ticketSet
    ]


def _checkKey(ticket: Ticket, config: Config) -> list[Finding]:
    """
    Report a ticket whose key is not registered.

    ticket: The ticket to check.
    config: The configuration holding the key registry.

    Returns the findings.
    """

    if config.isRegisteredKey(ticket.key):
        return []

    return [
        Finding(
            severity=SEVERITY_ERROR,
            rule=RULE_UNKNOWN_KEY,
            message=f"Ticket '{ticket.id}' uses key '{ticket.key}', which is not registered.",
            ticketId=ticket.id,
            path=ticket.path,
        )
    ]


def _checkFilename(ticket: Ticket) -> list[Finding]:
    """
    Report a ticket whose id does not match its filename prefix.

    The slug is deliberately not checked, because filenames are frozen at creation and a retitle is expected to leave the slug stale.

    ticket: The ticket to check.

    Returns the findings.
    """

    if ticket.path is None:
        return []

    # The prefix is everything before the first underscore, which is where the id ends.
    prefix: str = ticket.path.stem.split("_", 1)[0]
    if prefix == ticket.id:
        return []

    return [
        Finding(
            severity=SEVERITY_ERROR,
            rule=RULE_FILENAME_MISMATCH,
            message=f"Ticket '{ticket.id}' sits in {ticket.path.name}, whose filename prefix is '{prefix}'.",
            ticketId=ticket.id,
            path=ticket.path,
        )
    ]


def _checkStatusDirectory(ticket: Ticket, store: Store) -> list[Finding]:
    """
    Report a ticket whose status disagrees with the directory holding it.

    The status field is the truth and the directory is a projection of it, so this catches a file a human moved by hand.

    ticket: The ticket to check.
    store: The store resolving a status to its directory.

    Returns the findings.
    """

    if ticket.path is None:
        return []

    # An unrecognized status has no directory to agree with, and is reported by its own rule instead.
    if ticket.status not in STATUSES:
        return []

    expected: Path = store.directoryFor(ticket.status)
    if ticket.path.parent == expected:
        return []

    return [
        Finding(
            severity=SEVERITY_ERROR,
            rule=RULE_STATUS_DIRECTORY,
            message=f"Ticket '{ticket.id}' has status '{ticket.status}' but sits in '{ticket.path.parent.name}/' rather than '{expected.name}/'. Use 'docket {ticket.id} {ticket.status}' rather than moving files by hand.",
            ticketId=ticket.id,
            path=ticket.path,
        )
    ]


def _checkPriority(ticket: Ticket, config: Config) -> list[Finding]:
    """
    Report a priority outside the configured band.

    ticket: The ticket to check.
    config: The configuration holding the ceiling.

    Returns the findings.
    """

    if 0 <= ticket.priority <= config.maxPriority:
        return []

    return [
        Finding(
            severity=SEVERITY_ERROR,
            rule=RULE_PRIORITY_RANGE,
            message=f"Ticket '{ticket.id}' has priority {ticket.priority}, outside 0 through {config.maxPriority}.",
            ticketId=ticket.id,
            path=ticket.path,
        )
    ]


def _checkStatus(ticket: Ticket) -> list[Finding]:
    """
    Report a status outside the fixed vocabulary.

    ticket: The ticket to check.

    Returns the findings.
    """

    if ticket.status in STATUSES:
        return []

    return [
        Finding(
            severity=SEVERITY_ERROR,
            rule=RULE_UNKNOWN_STATUS,
            message=f"Ticket '{ticket.id}' has status '{ticket.status}', which is not one of {', '.join(STATUSES)}.",
            ticketId=ticket.id,
            path=ticket.path,
        )
    ]


def _checkCycles(graph: ResolvedGraph) -> list[Finding]:
    """
    Report every dependency cycle.

    graph: The resolved graph to search.

    Returns the findings.
    """

    findings: list[Finding] = []
    for cycle in findCycles(graph):
        # A one-member cycle is a ticket requiring itself, which reads better stated plainly.
        if len(cycle) == 1:
            findings.append(Finding(severity=SEVERITY_ERROR, rule=RULE_CYCLE, message=f"Ticket '{cycle[0]}' requires itself.", ticketId=cycle[0]))
            continue

        findings.append(Finding(severity=SEVERITY_ERROR, rule=RULE_CYCLE, message=f"Dependency cycle between {', '.join(cycle)}.", ticketId=cycle[0]))

    return findings
