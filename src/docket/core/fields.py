"""
Docket Fields

Typed reading of untrusted mapping fields, shared by frontmatter parsing and configuration parsing.

Both surfaces read a mapping that came from a file a human or an agent may have written badly, and both need the same presence and type checks. Only the exception they raise differs, so it is passed in.
"""

# MARK: Imports

from typing import Any, Mapping, Optional, Type

from docket.core.errors import DocketError

# MARK: Functions


def readString(mapping: Mapping[str, Any], name: str, errorType: Type[DocketError], source: str, fallback: Optional[str] = None) -> str:
    """
    Read a string field.

    mapping: The parsed mapping to read from.
    name: The field name.
    errorType: The exception raised when the field is absent or of the wrong type.
    source: What to name in the error message, for example `Frontmatter`.
    fallback: The value used when the field is absent, or `None` to make the field required.

    Returns the field value.
    """

    value: Any = _readRaw(mapping, name, errorType, source, fallback)

    if not isinstance(value, str):
        raise errorType(f"{source} field '{name}' must be a string, got {type(value).__name__}.")

    # Narrow to exactly `str`, since a parser may hand back a subclass. `tomlkit` does, and `pyyaml` dispatches its representers on exact type, so a subclass leaking this far fails at serialization instead of here.
    return str(value)


def readInt(mapping: Mapping[str, Any], name: str, errorType: Type[DocketError], source: str, fallback: Optional[int] = None) -> int:
    """
    Read an integer field.

    mapping: The parsed mapping to read from.
    name: The field name.
    errorType: The exception raised when the field is absent or of the wrong type.
    source: What to name in the error message, for example `Frontmatter`.
    fallback: The value used when the field is absent, or `None` to make the field required.

    Returns the field value.
    """

    value: Any = _readRaw(mapping, name, errorType, source, fallback)

    # `bool` subclasses `int` in Python, so exclude it explicitly rather than reading `true` as 1.
    if isinstance(value, bool) or not isinstance(value, int):
        raise errorType(f"{source} field '{name}' must be an integer, got {type(value).__name__}.")

    # Narrow to exactly `int`, for the same reason as `readString`.
    return int(value)


def readStringList(mapping: Mapping[str, Any], name: str, errorType: Type[DocketError], source: str) -> list[str]:
    """
    Read a list-of-strings field.

    An absent or null field reads as empty, since an empty list is the common case and refusing to load over it would be hostile.

    mapping: The parsed mapping to read from.
    name: The field name.
    errorType: The exception raised when the field is of the wrong type.
    source: What to name in the error message, for example `Frontmatter`.

    Returns the field value.
    """

    if name not in mapping or mapping[name] is None:
        return []

    value: Any = mapping[name]
    if not isinstance(value, list):
        raise errorType(f"{source} field '{name}' must be a list, got {type(value).__name__}.")

    # Reject a non-string entry here, since every later stage treats these as ids.
    for entry in value:
        if not isinstance(entry, str):
            raise errorType(f"{source} field '{name}' must contain only strings, found {type(entry).__name__}.")

    # Narrow every entry to exactly `str`, for the same reason as `readString`.
    return [str(entry) for entry in value]


def _readRaw(mapping: Mapping[str, Any], name: str, errorType: Type[DocketError], source: str, fallback: Optional[Any]) -> Any:
    """
    Fetch a field, applying its fallback or raising when it is required and absent.

    mapping: The parsed mapping to read from.
    name: The field name.
    errorType: The exception raised when a required field is absent.
    source: What to name in the error message.
    fallback: The value used when the field is absent, or `None` to make the field required.

    Returns the raw value, still untyped.
    """

    if name in mapping:
        return mapping[name]

    if fallback is None:
        raise errorType(f"{source} is missing the required field '{name}'.")

    return fallback
