"""
Docket Shim

Runs the CLI from the repository root, for a debugger or an IDE run configuration.
"""

# MARK: Imports

import sys

from docket.cli import main

# MARK: Main

# Import through the installed package rather than through `src.docket`, so this shares one module object with the `docket` console script instead of loading a second copy of every module.
if __name__ == "__main__":
    sys.exit(main())
