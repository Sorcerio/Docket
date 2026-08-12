"""
Docket Titles

Title case for the `title` field, applied on every write and reported on by `validate`.

The rule lives here alone so the CLI, the MCP server, and the validator can never disagree about what a correct title looks like.
"""

# MARK: Imports

from typing import Iterable, Iterator

import textcase

# MARK: Constants

# Words left lowercase when they fall between the first and the last word, following the convention that articles, coordinating conjunctions, and prepositions are minor.
# `up` and `out` are deliberately absent, because a ticket title is far more likely to want the phrasal verb in `Set Up Publishing` than the preposition.
MINOR_WORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "as",
        "at",
        "but",
        "by",
        "for",
        "from",
        "if",
        "in",
        "into",
        "nor",
        "of",
        "off",
        "on",
        "onto",
        "or",
        "over",
        "per",
        "so",
        "than",
        "that",
        "to",
        "upon",
        "via",
        "when",
        "with",
        "yet",
    }
)

# MARK: Functions


def _transformWords(words: Iterable[str]) -> Iterator[str]:
    """
    Case each word of a title according to its position and its existing shape.

    `textcase.title` alone is not usable here, because it capitalizes through `str.capitalize`, which lowercases the rest of the word and would turn `CLI` into `Cli`.
    A word is therefore left exactly as written whenever it carries capitalization or a digit of its own, which is what lets an acronym, a ticket id, and a version number survive a title that is otherwise rewritten.

    words: The words the case split produced, in order.

    Returns each word in the case it should carry.
    """

    ordered: list[str] = list(words)
    last: int = len(ordered) - 1

    for index, word in enumerate(ordered):
        # A minor word is checked first and by its lowercase form, so a wrongly capitalized `For` is corrected rather than mistaken for an acronym.
        # The first and the last word are always major, no matter which word they are.
        if 0 < index < last and word.lower() in MINOR_WORDS:
            yield word.lower()
            continue

        # A word carrying an uppercase letter past its first character, or a digit anywhere, was written that way on purpose.
        if word[1:] != word[1:].lower() or any(character.isdigit() for character in word):
            yield word
            continue

        yield word[:1].upper() + word[1:]


# The boundaries are narrowed to whitespace and punctuation is kept, so `FEAT-5` and `2.x` reach the transform whole rather than being split apart and stripped.
titleCase: textcase.Case = textcase.Case(delimiter=" ", transform=_transformWords)


def toTitleCase(title: str) -> str:
    """
    Convert a title to title case.

    Runs of whitespace collapse to a single space and surrounding whitespace is dropped, since the split that finds the words is what removes them.

    title: The title to convert.

    Returns the title in title case.
    """

    return titleCase(title, boundaries=[textcase.SPACE], strip_punctuation=False)


def isTitleCase(title: str) -> bool:
    """
    Report whether a title is already in title case.

    title: The title to test.

    Returns `True` when converting the title would change nothing.
    """

    return toTitleCase(title) == title
