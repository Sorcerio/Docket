"""
Docket Handoff

Rendering the offsite authoring brief.

The brief is one document handed to a chat system that has no connection to this repository, so everything it could otherwise only guess at is rendered into it.
"""

# MARK: Imports

from dataclasses import dataclass
from typing import Any, Optional

from docket.core.config import DEFAULT_MAX_PRIORITY, DEFAULT_PRIORITY, DEFAULT_ROOT, DEFAULT_TODO_DIR, Config
from docket.core.ids import nextId
from docket.core.store import Store
from docket.core.templating import renderDocument

# MARK: Constants

# The brief itself.
HANDOFF_TEMPLATE: str = "writingTicketsOffsite.md.jinja"

# What the brief is called once it has been written into a repository.
HANDOFF_FILENAME: str = "handoff.md"

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

    return renderDocument(HANDOFF_TEMPLATE, buildContext(store))
