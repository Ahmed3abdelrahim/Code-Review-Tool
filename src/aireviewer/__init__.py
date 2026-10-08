"""AI Code Reviewer: a GitHub App that reviews pull requests."""

from importlib.metadata import version

__version__: str = version("aireviewer")

__all__ = ["__version__"]
