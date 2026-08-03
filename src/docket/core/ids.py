"""
Docket Ids

Key parsing, id formatting, next-number allocation, and filename slug generation.
"""

# MARK: Imports

import re
import unicodedata
from typing import Iterable, Optional

from docket.core.errors import InvalidIdError, InvalidKeyError

# MARK: Constants

# A key is uppercase alphanumeric and must start with a letter.
KEY_PATTERN: re.Pattern[str] = re.compile(r"^[A-Z][A-Z0-9]*$")

# A ticket id is a key, a hyphen, and a positive integer with no leading zeros.
ID_PATTERN: re.Pattern[str] = re.compile(r"^([A-Z][A-Z0-9]*)-([1-9][0-9]*)$")

# Every run of characters outside this set separates one slug token from the next.
SLUG_SEPARATOR_PATTERN: re.Pattern[str] = re.compile(r"[^A-Za-z0-9]+")

# The slug is capped so a filename stays comfortably inside every filesystem's limit.
SLUG_MAX_LENGTH: int = 48

# Used when a title contains nothing that survives normalization, for example a title of only emoji.
SLUG_FALLBACK: str = "untitled"

# MARK: Functions


def isValidKey(key: str) -> bool:
    """
    Report whether a key matches the required form.

    key: The key to test.

    Returns `True` when the key is well formed.
    """

    return bool(KEY_PATTERN.match(key))


def requireValidKey(key: str) -> str:
    """
    Return the key unchanged, raising when it is malformed.

    key: The key to check.

    Returns the same key.
    """

    # Reject anything that is not uppercase alphanumeric starting with a letter.
    if not isValidKey(key):
        raise InvalidKeyError(f"Key '{key}' is malformed. A key must be uppercase alphanumeric and start with a letter, for example 'CORE'.")

    return key


def isValidId(ticketId: str) -> bool:
    """
    Report whether a ticket id matches the required form.

    This is the asking half of `parseId`, for a caller deciding what a token is rather than one that already knows.

    ticketId: The id to test.

    Returns `True` when the id is well formed.
    """

    return bool(ID_PATTERN.match(ticketId))


def parseId(ticketId: str) -> tuple[str, int]:
    """
    Split a ticket id into its key and its number.

    ticketId: The id to split, for example `CORE-14`.

    Returns a `(key, number)` pair.
    """

    # Match the whole id so a trailing or leading fragment cannot slip through.
    match: Optional[re.Match[str]] = ID_PATTERN.match(ticketId)
    if match is None:
        raise InvalidIdError(f"Id '{ticketId}' is malformed. An id must be a key, a hyphen, and a positive number, for example 'CORE-14'.")

    return match.group(1), int(match.group(2))


def formatId(key: str, number: int) -> str:
    """
    Build a ticket id from a key and a number.

    key: The key the ticket belongs to.
    number: The sequential number within that key.

    Returns the formatted id.
    """

    # Validate both halves here so a malformed id can never be constructed.
    requireValidKey(key)
    if number < 1:
        raise InvalidIdError(f"Number {number} is invalid. Ticket numbers start at 1.")

    return f"{key}-{number}"


def keyOf(ticketId: str) -> str:
    """
    Extract the key from a ticket id.

    ticketId: The id to read.

    Returns the key portion.
    """

    return parseId(ticketId)[0]


def nextNumber(key: str, existingIds: Iterable[str]) -> int:
    """
    Derive the next available number for a key by scanning existing ids.

    The result is always one past the highest number seen, never the lowest unused gap, so a deleted ticket's number is not reused.

    key: The key to allocate within.
    existingIds: Every ticket id currently in the set, of any key.

    Returns the next number to use.
    """

    requireValidKey(key)

    # Collect the numbers already taken under this key, ignoring ids belonging to other keys.
    highest: int = 0
    for existingId in existingIds:
        match: Optional[re.Match[str]] = ID_PATTERN.match(existingId)
        if match is None or match.group(1) != key:
            continue

        highest = max(highest, int(match.group(2)))

    return highest + 1


def nextId(key: str, existingIds: Iterable[str]) -> str:
    """
    Derive the next available id for a key.

    key: The key to allocate within.
    existingIds: Every ticket id currently in the set.

    Returns the formatted next id.
    """

    return formatId(key, nextNumber(key, existingIds))


def slugify(title: str) -> str:
    """
    Convert a free-text title into a camelCase filename slug.

    A title is untrusted input, so this works from an allowlist of characters rather than a blocklist.
    Path separators, `..`, quotes, and control characters are discarded as a consequence of that rule rather than by explicit rejection.

    title: The ticket title to convert.

    Returns the slug, or `untitled` when nothing survives.
    """

    # Fold accented characters onto their ASCII bases, then drop anything still outside ASCII.
    normalized: str = unicodedata.normalize("NFKD", title)
    asciiOnly: str = normalized.encode("ascii", "ignore").decode("ascii")

    # Split on every run of non-alphanumeric characters, which is what makes traversal impossible by construction.
    tokens: list[str] = [token for token in SLUG_SEPARATOR_PATTERN.split(asciiOnly) if token]
    if not tokens:
        return SLUG_FALLBACK

    # Lowercase the first token whole, then capitalize each later token so an acronym like `HTTP` becomes `Http` rather than shouting.
    parts: list[str] = [tokens[0].lower()]
    parts.extend(token[0].upper() + token[1:].lower() for token in tokens[1:])

    # Append tokens while they fit, so truncation lands on a word boundary wherever possible.
    slug: str = ""
    for part in parts:
        if slug and len(slug) + len(part) > SLUG_MAX_LENGTH:
            break

        slug += part

    # A single opening token longer than the cap has no boundary to break on, so cut it hard.
    return slug[:SLUG_MAX_LENGTH]


def buildFilename(ticketId: str, title: str) -> str:
    """
    Build the on-disk filename for a ticket.

    The id prefix is what makes the filename unique, which is why a slug collision between two titles is harmless and why a slug matching a Windows reserved device name is harmless too.

    ticketId: The ticket's id, which is validated here.
    title: The title the slug derives from.

    Returns the filename, including the `.md` extension.
    """

    # Validate the id rather than trusting it, since this result is used as a path.
    parseId(ticketId)

    return f"{ticketId}_{slugify(title)}.md"
