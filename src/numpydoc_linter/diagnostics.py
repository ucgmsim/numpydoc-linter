"""The diagnostic record produced by every rule."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """
    A single rule violation at a single source location.

    Parameters
    ----------
    code : str
        The rule code, for example ``"PR04"``.
    message : str
        Human-readable description of the violation.
    path : pathlib.Path
        File the violation was found in.
    line : int
        One-based line number.
    col : int
        One-based column number.
    qualname : str
        Dotted name of the object the violation belongs to.
    kind : str
        Kind of the object, for example ``"property"``.
    """

    code: str
    message: str
    path: Path
    line: int
    col: int
    qualname: str = ""
    kind: str = ""

    @property
    def sort_key(self) -> tuple[str, int, int, str]:
        """
        Order diagnostics by file, then position, then code.

        Returns
        -------
        tuple
            Key suitable for passing to :func:`sorted`.
        """
        return (str(self.path), self.line, self.col, self.code)
