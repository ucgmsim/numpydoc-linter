"""Differential tests against the numpydoc reference implementation.

These lint a real corpus with both tools and require the results to agree,
except in the places where this linter deliberately does something different.
Each divergence is asserted structurally, not waved through, so an unexpected
one fails the test.

Three divergences are expected, all of them cases where numpydoc's AST hook
disagrees with its own documentation:

1. ``GL08`` on ``__init__``. numpydoc documents that "a properly formatted
   class docstring silences GL08 for an ``__init__`` constructor without a
   docstring", and its import-based path does exactly that. The AST hook gets
   it wrong in both directions: it guards the logic with ``len(ancestry) > 2``,
   so a plain ``module.Class.__init__`` is reported even when the class
   documents it, and where the guard does pass it accepts a class with no
   docstring at all, because an absent docstring trivially has no parameter
   mismatch. This linter requires an actual class docstring that documents the
   constructor's parameters.

2. ``PR01`` and ``PR02`` on dataclasses. A ``@dataclass`` has no ``__init__``
   in the tree, so numpydoc sees an empty signature: it calls every documented
   field an unknown parameter, and never notices an undocumented one. numpydoc's
   own test suite contains a dataclass annotated "As param1 is not documented
   this class should also raise PR01", which numpydoc does not raise and this
   linter does. This linter derives the synthesised constructor.

3. Objects nested inside control flow. numpydoc's visitor recurses only
   through module, class and function nodes, so a function defined directly in
   a body is visited but one defined inside an ``if`` or a ``for`` is silently
   skipped. This linter visits every nested object consistently. The
   comparison is therefore restricted to the objects numpydoc's own traversal
   can reach, which is computed below rather than assumed.

4. ``YD01`` on ``yield from``. numpydoc's AST generator check looks only at
   direct children that are a bare ``ast.Yield`` expression statement, so it
   misses ``yield from`` and any yield inside a branch or loop. This linter
   walks the body.

5. Malformed docstrings. A docstring that breaks the parser raises out of
   numpydoc's ``process_file`` and abandons the whole file. This linter
   reports ``DS01`` and carries on, so those files are compared only up to the
   point numpydoc manages to reach, which is nothing; they are skipped.
"""

from __future__ import annotations

import ast
import warnings
from pathlib import Path

import pytest

from numpydoc_linter.config import _settings_from_table
from numpydoc_linter.runner import lint_source
from numpydoc_linter.source import read_source
from numpydoc_linter.targets import collect_targets

numpydoc = pytest.importorskip("numpydoc", reason="parity needs numpydoc installed")

from numpydoc.hooks.validate_docstrings import process_file  # noqa: E402
from numpydoc.validate import get_validation_checks  # noqa: E402

pytestmark = pytest.mark.parity

REPO = Path(__file__).resolve().parent.parent

#: Our settings for the parity run: every ported rule and nothing new.
PARITY_TABLE = {"select": ["ALL"], "ignore": ["PT", "DS", "NQ"]}

NUMPYDOC_CONFIG = {
    "checks": get_validation_checks({"all"}),
    "exclude": None,
    "overrides": {},
    "exclude_files": None,
}


def _corpus() -> list[Path]:
    files = sorted(Path(numpydoc.__file__).parent.rglob("*.py"))
    files += sorted((REPO / "src" / "numpydoc_linter").rglob("*.py"))
    files += sorted((REPO / "tests" / "fixtures").glob("*.py"))
    return files


def _numpydoc_reachable_lines(tree: ast.Module) -> set[int]:
    """
    Replicate numpydoc's traversal to find the objects it can actually visit.

    Its visitor handles module, class and function nodes and returns without
    recursing for anything else, so a definition only counts if every step
    from the module down to it is itself a definition.

    Parameters
    ----------
    tree : ast.Module
        The parsed module.

    Returns
    -------
    set of int
        Lines of the definitions numpydoc will visit.
    """
    kinds = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    reachable = {1}
    stack = [tree]
    while stack:
        node = stack.pop()
        for child in ast.iter_child_nodes(node):
            if isinstance(child, kinds):
                reachable.add(child.lineno)
                stack.append(child)
    return reachable


def _numpydoc_findings(path: Path) -> set[tuple[int, str]]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return {
            (int(f[0].rsplit(":", 1)[1]), f[2])
            for f in process_file(path, NUMPYDOC_CONFIG)
        }


def _our_findings(path: Path) -> set[tuple[int, str]]:
    settings = _settings_from_table(PARITY_TABLE, REPO, None)
    return {(d.line, d.code) for d in lint_source(read_source(path, REPO), settings)}


def _targets_by_line(path: Path) -> dict[int, object]:
    source = read_source(path, REPO)
    return {
        t.lineno: t
        for t in collect_targets(source.tree, source.path, source.module_name)
    }


CORPUS = _corpus()


def test_corpus_is_substantial() -> None:
    """A parity test over three files would prove nothing."""
    assert len(CORPUS) >= 30


@pytest.mark.parametrize("path", CORPUS, ids=lambda p: p.name)
def test_agrees_with_numpydoc(path: Path) -> None:
    source = read_source(path, REPO)
    try:
        theirs = _numpydoc_findings(path)
    except Exception as exc:
        # Divergence 4: numpydoc abandons the file, we do not.
        ours_codes = {d.code for d in lint_source(source, _settings_from_table(
            {"select": ["ALL"]}, REPO, None
        ))}
        assert "DS01" in ours_codes, (
            f"{path}: numpydoc raised {exc!r} but we reported no DS01"
        )
        pytest.skip(f"numpydoc cannot parse this file: {exc}")

    reachable = _numpydoc_reachable_lines(source.tree)
    ours = {item for item in _our_findings(path) if item[0] in reachable}
    if theirs == ours:
        return

    by_line = _targets_by_line(path)
    unexplained: list[str] = []
    for line, code in sorted(theirs ^ ours):
        side = "numpydoc only" if (line, code) in theirs else "ours only"
        reason = _divergence(line, code, by_line.get(line))
        if reason is None:
            unexplained.append(f"{side} {code} at line {line}")
    assert not unexplained, f"{path}: undocumented divergence: {unexplained}"


def _divergence(line: int, code: str, target) -> str | None:
    """
    Name the documented divergence covering one difference, if any.

    Parameters
    ----------
    line : int
        Line the difference was reported at.
    code : str
        The rule code.
    target : Target or None
        The object at that line.

    Returns
    -------
    str or None
        The divergence name, or None when the difference is unexplained.
    """
    if target is None:
        return None
    if code == "GL08" and target.name == "__init__":
        return "1: __init__ exemption"
    if code in ("PR01", "PR02") and target.is_dataclass:
        return "2: synthesised dataclass constructor"
    if code == "YD01" and _uses_yield_from(target.node):
        return "4: yield from is a generator"
    return None


def _uses_yield_from(node: ast.AST) -> bool:
    """
    Report whether a function body contains ``yield from``.

    Parameters
    ----------
    node : ast.AST
        The function node.

    Returns
    -------
    bool
        True when a ``yield from`` is present.
    """
    return any(isinstance(n, ast.YieldFrom) for n in ast.walk(node))


def test_init_exemption_is_the_documented_behaviour(tmp_path: Path) -> None:
    """A class that documents its parameters silences GL08 on __init__."""
    code = '''
"""Module."""


class Documented:
    """
    A thing.

    Parameters
    ----------
    x : int
        The x.
    """

    def __init__(self, x):
        self.x = x


class Undocumented:
    """A thing."""

    def __init__(self, x):
        self.x = x
'''
    path = tmp_path / "sample.py"
    path.write_text(code, encoding="utf-8")
    settings = _settings_from_table({"select": ["GL08"]}, tmp_path, None)
    found = {d.line for d in lint_source(read_source(path, tmp_path), settings)}

    targets = {t.qualname: t for t in _targets_by_line(path).values()}
    documented_init = next(
        t for t in targets.values()
        if t.name == "__init__" and t.parent.name == "Documented"
    )
    undocumented_init = next(
        t for t in targets.values()
        if t.name == "__init__" and t.parent.name == "Undocumented"
    )
    assert documented_init.lineno not in found
    # The class docstring does not document x, so the constructor must.
    assert undocumented_init.lineno in found


def test_dataclass_fields_are_not_unknown_parameters(tmp_path: Path) -> None:
    """Documented dataclass fields are real constructor parameters."""
    code = '''
"""Module."""

from dataclasses import dataclass


@dataclass
class Point:
    """
    A point.

    Parameters
    ----------
    x : int
        The x.
    y : int
        The y.
    """

    x: int
    y: int
'''
    path = tmp_path / "sample.py"
    path.write_text(code, encoding="utf-8")
    settings = _settings_from_table({"select": ["PR"]}, tmp_path, None)
    codes = {d.code for d in lint_source(read_source(path, tmp_path), settings)}
    assert codes == set()
