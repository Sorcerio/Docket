"""
Docket Handoff

Rendering the offsite authoring brief.

The brief is one document handed to a chat system that has no connection to this repository, so everything it could otherwise only guess at is rendered into it.
"""

# MARK: Imports

from dataclasses import dataclass
from typing import Any, Optional

from jinja2 import Environment, StrictUndefined, Template

from docket.core.config import DEFAULT_MAX_PRIORITY, DEFAULT_PRIORITY, DEFAULT_ROOT, DEFAULT_TODO_DIR, Config
from docket.core.ids import nextId
from docket.core.resources import readPackageText
from docket.core.store import Store

# MARK: Constants

# The directory inside the package holding documents written to be read by someone, kept apart from `templates` because those are files a repository receives rather than text a person is handed.
DOCS_DIRECTORY: str = "docs"

# The brief itself.
HANDOFF_TEMPLATE: str = "writingTicketsOffsite.md.jinja"

# MARK: Classes


@dataclass(frozen=True)
class KeyBriefing:
    """
    One registered key, as the brief needs to describe it.

    The next id is carried alongside the key because it is the whole reason the brief is rendered rather than shipped flat. A reader told which number to start at cannot collide with a ticket that already exists.
    """

    # MARK: Properties

    key: str
    description: str
    nextId: str


# MARK: Functions


def readDocument(name: str) -> str:
    """
    Read a document shipped inside the package.

    name: The document filename.

    Returns the document text.
    """

    return readPackageText(DOCS_DIRECTORY, name)


def buildKeyBriefings(store: Store) -> list[KeyBriefing]:
    """
    Describe every registered key, with the next id free under it.

    The whole ticket set is loaded once and every key allocates against that one snapshot, so the numbers cannot disagree with each other.

    store: The store naming the configuration and the ticket root.

    Returns one briefing per registered key, ordered by key.
    """

    existingIds: list[str] = store.loadAll().ids()

    return [
        KeyBriefing(key=key, description=description, nextId=nextId(key, existingIds))
        for key, description in sorted(store.config.registeredKeys.items())
    ]


def buildContext(store: Optional[Store]) -> dict[str, Any]:
    """
    Gather everything the brief names about the repository it is written for.

    Run outside a repository there is nothing to gather, so the defaults stand in and the brief tells its reader to propose keys instead of choosing from them. That is the same document either way rather than a second mode.

    store: The store for the repository the brief is being written for, or `None` when none was found.

    Returns the render context.
    """

    # Without a configuration every value falls back to what a freshly deployed repository would have, since that is what the reader's tickets will eventually meet.
    if store is None:
        return {
            "keys": [],
            "ticketDir": f"{DEFAULT_ROOT}/{DEFAULT_TODO_DIR}",
            "defaultPriority": DEFAULT_PRIORITY,
            "maxPriority": DEFAULT_MAX_PRIORITY,
        }

    config: Config = store.config

    return {
        "keys": buildKeyBriefings(store),
        "ticketDir": f"{config.root}/{config.todoDir}",
        "defaultPriority": config.defaultPriority,
        "maxPriority": config.maxPriority,
    }


def renderHandoff(store: Optional[Store] = None) -> str:
    """
    Render the offsite authoring brief.

    store: The store for the repository the brief is being written for, or `None` when none was found.

    Returns the rendered document.
    """

    template: Template = _buildEnvironment().from_string(readDocument(HANDOFF_TEMPLATE))

    return template.render(buildContext(store))


def _buildEnvironment() -> Environment:
    """
    Build the environment every shipped document renders through.

    Autoescaping is off because the output is markdown a person reads, and escaping it would corrupt the very syntax the brief is teaching. An undefined name raises rather than rendering as nothing, so a template naming something the context does not carry fails here instead of reaching the reader as a hole in a sentence.

    Returns the environment.
    """

    return Environment(undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True, autoescape=False)
