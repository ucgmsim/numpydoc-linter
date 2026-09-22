"""Render diagnostics."""

from __future__ import annotations

import collections
import json
from collections.abc import Iterable
from pathlib import Path

from npdlint.diagnostics import Diagnostic
from npdlint.rules.base import registry

#: Every format ``--output-format`` accepts.
FORMATS = ("concise", "full", "json", "github", "pylint")


def _display(path: Path, root: Path) -> str:
    """
    Render a path relative to the project root when possible.

    Parameters
    ----------
    path : pathlib.Path
        The path.
    root : pathlib.Path
        Project root.

    Returns
    -------
    str
        The display form.
    """
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return str(path)


def concise(diagnostics: Iterable[Diagnostic], root: Path) -> list[str]:
    """
    Render one line per diagnostic.

    Parameters
    ----------
    diagnostics : iterable of Diagnostic
        The diagnostics.
    root : pathlib.Path
        Project root.

    Returns
    -------
    list of str
        Output lines.
    """
    return [
        f"{_display(d.path, root)}:{d.line}:{d.col}: {d.code} {d.message}"
        for d in diagnostics
    ]


def full(
    diagnostics: Iterable[Diagnostic], root: Path, sources: dict[Path, list[str]]
) -> list[str]:
    """
    Render each diagnostic with the offending source line.

    Parameters
    ----------
    diagnostics : iterable of Diagnostic
        The diagnostics.
    root : pathlib.Path
        Project root.
    sources : dict
        File path to its lines, used to quote the source.

    Returns
    -------
    list of str
        Output lines.
    """
    out: list[str] = []
    for d in diagnostics:
        out.append(f"{_display(d.path, root)}:{d.line}:{d.col}: {d.code} {d.message}")
        lines = sources.get(d.path.resolve()) or sources.get(d.path)
        if lines and 1 <= d.line <= len(lines):
            gutter = str(d.line)
            pad = " " * len(gutter)
            out.append(f"  {pad} |")
            out.append(f"  {gutter} | {lines[d.line - 1]}")
            out.append(f"  {pad} | {' ' * max(d.col - 1, 0)}^")
            out.append(f"  {pad} |")
        if d.qualname:
            out.append(f"  = {d.kind} {d.qualname}")
        out.append("")
    return out


def github(diagnostics: Iterable[Diagnostic], root: Path) -> list[str]:
    """
    Render GitHub Actions workflow commands, so violations annotate the diff.

    Parameters
    ----------
    diagnostics : iterable of Diagnostic
        The diagnostics.
    root : pathlib.Path
        Project root.

    Returns
    -------
    list of str
        Output lines.
    """
    out = []
    for d in diagnostics:
        message = d.message.replace("%", "%25").replace("\r", "%0D").replace(
            "\n", "%0A"
        )
        out.append(
            f"::error file={_display(d.path, root)},line={d.line},col={d.col},"
            f"title={d.code}::{message}"
        )
    return out


def pylint(diagnostics: Iterable[Diagnostic], root: Path) -> list[str]:
    """
    Render in pylint's parseable format, for editors that expect it.

    Parameters
    ----------
    diagnostics : iterable of Diagnostic
        The diagnostics.
    root : pathlib.Path
        Project root.

    Returns
    -------
    list of str
        Output lines.
    """
    return [
        f"{_display(d.path, root)}:{d.line}: [{d.code}] {d.message}"
        for d in diagnostics
    ]


def as_json(diagnostics: Iterable[Diagnostic], root: Path) -> str:
    """
    Render diagnostics as a JSON array.

    Parameters
    ----------
    diagnostics : iterable of Diagnostic
        The diagnostics.
    root : pathlib.Path
        Project root.

    Returns
    -------
    str
        The JSON document.
    """
    payload = [
        {
            "code": d.code,
            "message": d.message,
            "path": _display(d.path, root),
            "line": d.line,
            "column": d.col,
            "qualname": d.qualname,
            "kind": d.kind,
        }
        for d in diagnostics
    ]
    return json.dumps(payload, indent=2)


def statistics(diagnostics: Iterable[Diagnostic]) -> list[str]:
    """
    Summarise diagnostics by code, most frequent first.

    Parameters
    ----------
    diagnostics : iterable of Diagnostic
        The diagnostics.

    Returns
    -------
    list of str
        A table of counts.
    """
    counts = collections.Counter(d.code for d in diagnostics)
    if not counts:
        return []
    width = max(len(str(c)) for c in counts.values())
    out = []
    for code, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        rule = registry.get(code)
        name = rule.name if rule is not None else ""
        out.append(f"{count:>{width}}  {code}  {name}")
    out.append(f"{sum(counts.values()):>{width}}  total")
    return out


def summary_line(count: int, files: int) -> str:
    """
    Render the trailing summary line.

    Parameters
    ----------
    count : int
        Number of diagnostics.
    files : int
        Number of files checked.

    Returns
    -------
    str
        The summary.
    """
    noun = "issue" if count == 1 else "issues"
    file_noun = "file" if files == 1 else "files"
    if count == 0:
        return f"All checks passed ({files} {file_noun})"
    return f"Found {count} {noun} in {files} {file_noun}"
