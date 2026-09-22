"""A fast, modular, structurally-aware linter for numpydoc-style docstrings."""

from importlib.metadata import PackageNotFoundError, version

from numpydoc_linter.diagnostics import Diagnostic

try:
    __version__ = version("numpydoc-linter")
except PackageNotFoundError:  # pragma: no cover - running from a source tree
    __version__ = "0.0.0+unknown"

__all__ = ["Diagnostic", "__version__"]
