"""
Docket Resources

Reading the non-Python files shipped inside the package.

Templates a repository receives and documents a person is handed both live in the package rather than the working tree, so both are read through here.
"""

# MARK: Imports

from importlib.resources import files

# MARK: Constants

# The package the shipped files live inside.
PACKAGE_NAME: str = "docket"

# MARK: Functions


def readPackageText(directory: str, name: str) -> str:
    """
    Read a text file shipped inside the package.

    This goes through `importlib.resources` rather than a path derived from `__file__`, so it reads the same whether docket is installed as a wheel, run from a source checkout, or imported from a zip.

    Args:
        directory: The directory inside the package holding the file.
        name: The filename.

    Returns:
        The file text.
    """

    return files(PACKAGE_NAME).joinpath(directory, name).read_text(encoding="utf-8")
