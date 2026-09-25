"""
Docket Templating

The environment every document docket renders is built through.

This holds the settings and nothing else. What each document says belongs to the module that renders it, so a second document costs another renderer rather than another environment.
"""

# MARK: Imports

from jinja2 import Environment, StrictUndefined, Template

from docket.core.resources import readPackageText

# MARK: Constants

# The directory inside the package holding documents written to be read by someone, kept apart from `templates` because those are files a repository receives rather than text a person is handed.
DOCS_DIRECTORY: str = "docs"

# MARK: Functions


def buildEnvironment() -> Environment:
    """
    Build the environment every shipped document renders through.

    Autoescaping is off because the output is markdown a person reads, and escaping it would corrupt the very syntax a brief may be teaching. An undefined name raises rather than rendering as nothing, so a template naming something the context does not carry fails here instead of reaching the reader as a hole in a sentence.

    Returns:
        The environment.
    """

    return Environment(undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True, autoescape=False)


def readDocument(name: str) -> str:
    """
    Read a document shipped inside the package.

    Args:
        name: The document filename.

    Returns:
        The document text.
    """

    return readPackageText(DOCS_DIRECTORY, name)


def renderDocument(name: str, context: dict[str, object]) -> str:
    """
    Render one shipped document against a context.

    Reading and rendering are one step here because no caller has ever wanted one without the other, and keeping them together is what leaves each document's module holding only its own context.

    Args:
        name: The document filename.
        context: The names the template renders against.

    Returns:
        The rendered document.
    """

    template: Template = buildEnvironment().from_string(readDocument(name))

    return template.render(context)
