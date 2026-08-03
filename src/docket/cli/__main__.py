"""
Docket CLI Module Entry

Runs the CLI as `python -m docket.cli`, which is what the single-module layout gave for free.
"""

# MARK: Imports

import sys

from docket.cli import main

# MARK: Main

if __name__ == "__main__":
    sys.exit(main())
