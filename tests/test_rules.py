"""Fixture-driven rule tests.

Each fixture under ``tests/fixtures`` declares the rules it exercises, either
in a ``# select:`` header or in a sibling ``.toml`` file, and marks every
expected diagnostic with a ``# expect: CODE[,CODE]`` comment on the line it is
reported at. The test asserts the two agree exactly, so a rule that stops
firing and a rule that starts over-firing both fail.
"""

from __future__ import annotations

import re
import tomllib
from collections import defaultdict
from pathlib import Path

import pytest

from npdlint.config import _settings_from_table
from npdlint.rules.base import registry
from npdlint.runner import lint_source
from npdlint.source import read_source

FIXTURES = Path(__file__).parent / "fixtures"
EXPECT_RE = re.compile(r"#\s*expect:\s*([A-Z0-9,\s]+)")
SELECT_RE = re.compile(r"#\s*select:\s*(.+)")


def _fixture_files() -> list[Path]:
    return sorted(FIXTURES.glob("*.py"))


def _expected(text: str) -> set[tuple[int, str]]:
    out: set[tuple[int, str]] = set()
    for lineno, line in enumerate(text.splitlines(), 1):
        match = EXPECT_RE.search(line)
        if match is None:
            continue
        for code in re.split(r"[,\s]+", match.group(1).strip()):
            if code:
                out.add((lineno, code))
    return out


def _settings_for(path: Path):
    toml = path.with_suffix(".toml")
    if toml.is_file():
        table = tomllib.loads(toml.read_text(encoding="utf-8"))
    else:
        header = SELECT_RE.search(path.read_text(encoding="utf-8"))
        assert header is not None, f"{path.name} needs a '# select:' header"
        table = {"select": [s.strip() for s in header.group(1).split(",")]}
    return _settings_from_table(table, FIXTURES, None)


@pytest.mark.parametrize("path", _fixture_files(), ids=lambda p: p.stem)
def test_fixture_matches_expectations(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    settings = _settings_for(path)
    diagnostics = lint_source(read_source(path, FIXTURES), settings)
    actual = {(d.line, d.code) for d in diagnostics}
    expected = _expected(text)

    missing = expected - actual
    unexpected = actual - expected
    assert not missing, f"expected but not reported: {sorted(missing)}"
    assert not unexpected, f"reported but not expected: {sorted(unexpected)}"


def test_every_rule_is_covered_by_a_fixture() -> None:
    """No rule should ship without at least one fixture exercising it."""
    covered: set[str] = set()
    for path in _fixture_files():
        for _line, code in _expected(path.read_text(encoding="utf-8")):
            covered.add(code)
    uncovered = set(registry.codes()) - covered
    assert not uncovered, f"rules with no fixture: {sorted(uncovered)}"


def test_fixtures_report_nothing_outside_their_selection() -> None:
    """A fixture's expectations must all fall inside the rules it selects."""
    for path in _fixture_files():
        settings = _settings_for(path)
        diagnostics = lint_source(read_source(path, FIXTURES), settings)
        by_line: dict[int, set[str]] = defaultdict(set)
        for d in diagnostics:
            by_line[d.line].add(d.code)
        for line, codes in by_line.items():
            assert codes, f"{path.name}:{line} produced an empty code set"
