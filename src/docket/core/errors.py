"""
Docket Errors

The exception hierarchy raised by the core and translated by each shell.
"""

# MARK: Classes


class DocketError(Exception):
    """
    Base class for every error the core raises.

    A shell catches this to turn a core failure into a CLI message or an MCP tool error.
    """


class ConfigNotFoundError(DocketError):
    """
    Raised when no `.docket.toml` was found between the starting directory and the repository root.
    """


class ConfigError(DocketError):
    """
    Raised when a `.docket.toml` exists but is malformed or missing a required field.
    """


class InvalidKeyError(DocketError):
    """
    Raised when a key does not match the required `[A-Z][A-Z0-9]*` form.
    """


class UnknownKeyError(DocketError):
    """
    Raised when a key is not registered.
    """


class InvalidIdError(DocketError):
    """
    Raised when a ticket id does not match the required `<KEY>-<NUM>` form.
    """


class DeployError(DocketError):
    """
    Raised when docket cannot be installed into a consumer repository.

    This covers a target that is not a directory, and an existing `.mcp.json` that cannot be safely merged into.
    """


class TicketNotFoundError(DocketError):
    """
    Raised when no ticket carries the requested id.
    """


class InvalidStatusError(DocketError):
    """
    Raised when a status outside `todo`, `wip`, `done` is written through the tool.

    A status that arrived by hand-editing is reported by `validate` instead, since refusing to load it would hide the problem.
    """


class InvalidPriorityError(DocketError):
    """
    Raised when a priority outside `0` through `maxPriority` is written through the tool.
    """


class EmptyValueError(DocketError):
    """
    Raised when a value that must carry text arrived empty or as only whitespace.

    A shell that drops an empty argument before the process starts turns this into its own usage error instead, which is why this exists for the shells that pass one through.
    """


class ConflictingArgumentsError(DocketError):
    """
    Raised when two arguments in one call ask for contradictory things.

    Replacing a dependency list and editing that same list in place is the case this exists for, since honoring both would mean picking an order the caller never stated.
    """


class OutputPathError(DocketError):
    """
    Raised when a path supplied as a destination cannot be written to.

    This covers an empty path, a path naming an existing directory, and a location the filesystem refuses.
    """


class TicketParseError(DocketError):
    """
    Raised when a file under the ticket root is not a readable ticket.

    This covers a missing frontmatter block, unparseable YAML, and a required field that is absent or of the wrong type.
    It does not cover a field whose value breaks a rule, such as an out-of-range priority, because those are reported by `validate` instead.
    """
