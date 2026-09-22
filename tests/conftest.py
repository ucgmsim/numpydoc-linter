"""Shared test helpers."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from npdlint.config import Settings, _settings_from_table
from npdlint.diagnostics import Diagnostic
from npdlint.runner import lint_source
from npdlint.source import read_source
from npdlint.targets import collect_targets

FIXTURES = Path(__file__).parent / "fixtures"


def settings_from(table: dict, root: Path) -> Settings:
    """Build settings from a literal table, as if read from pyproject.toml."""
    return _settings_from_table(table, root, None)


def lint_text(text: str, tmp_path: Path, table: dict | None = None) -> list[Diagnostic]:
    """Write a snippet to disk, lint it, and return the diagnostics."""
    path = tmp_path / "sample.py"
    path.write_text(text, encoding="utf-8")
    settings = settings_from(table or {}, tmp_path)
    return lint_source(read_source(path, tmp_path), settings)


def codes_at(diagnostics: list[Diagnostic]) -> set[tuple[int, str]]:
    """Reduce diagnostics to the set of (line, code) pairs."""
    return {(d.line, d.code) for d in diagnostics}


def targets_of(text: str, path: Path | None = None):
    """Collect targets from a snippet."""
    return collect_targets(ast.parse(text), path or Path("sample.py"), "sample")


@pytest.fixture
def lint(tmp_path):
    """Return a callable that lints a snippet with optional settings."""

    def _lint(text: str, table: dict | None = None) -> list[Diagnostic]:
        return lint_text(text, tmp_path, table)

    return _lint


def pytest_addoption(parser):
    """Register the flag that enables the performance budget tests."""
    parser.addoption(
        "--run-performance",
        action="store_true",
        default=False,
        help="run the performance budget tests",
    )
