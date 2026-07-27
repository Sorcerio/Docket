"""
Docket MCP Server

A stdio MCP server, a thin shell over `docket.core`.

Nothing in this module may write to stdout, because the MCP stdio transport owns it.
Diagnostics go to stderr. `rich` must never be imported here, since a stray escape sequence corrupts the protocol.
"""

# MARK: Imports

import sys
from typing import Optional

# MARK: Functions


def main(argv: Optional[list[str]] = None) -> int:
    """
    Entry point for the `docket-mcp` console script.

    argv: Argument list, accepted for symmetry with the CLI and currently unused.

    Returns the process exit code.
    """

    # The server itself lands in a later phase, so report the gap on stderr and fail.
    print("docket-mcp is not implemented yet.", file=sys.stderr)
    return 1


# MARK: Main

if __name__ == "__main__":
    sys.exit(main())
