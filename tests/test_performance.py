"""A guard against performance regressions.

Skipped unless ``--run-performance`` is passed, because wall-clock budgets are
unreliable on a loaded machine and would otherwise make the suite flaky.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from npdlint.config import _settings_from_table
from npdlint.runner import lint_paths

pytestmark = pytest.mark.performance

#: Seconds allowed per file, single process. The real figure is far below this;
#: the budget is set loosely so only a real regression trips it.
BUDGET_PER_FILE = 0.05

#: Files needed before a measurement means anything.
MINIMUM_FILES = 200


def _corpus() -> list[Path]:
    import sysconfig

    root = Path(sysconfig.get_paths()["purelib"])
    return sorted(root.rglob("*.py"))[:600]


def test_throughput(request):
    if not request.config.getoption("--run-performance"):
        pytest.skip("needs --run-performance")
    files = _corpus()
    if len(files) < MINIMUM_FILES:
        pytest.skip(f"corpus too small: {len(files)} files")

    root = files[0].parents[1]
    settings = _settings_from_table({"select": ["ALL"]}, root, None)

    start = time.perf_counter()
    result = lint_paths(files, settings, jobs=1)
    elapsed = time.perf_counter() - start

    per_file = elapsed / max(result.files_checked, 1)
    assert per_file < BUDGET_PER_FILE, (
        f"{per_file * 1000:.1f} ms/file over {result.files_checked} files "
        f"exceeds the {BUDGET_PER_FILE * 1000:.0f} ms budget"
    )


def test_parallel_is_not_slower(request):
    if not request.config.getoption("--run-performance"):
        pytest.skip("needs --run-performance")
    files = _corpus()
    if len(files) < MINIMUM_FILES:
        pytest.skip(f"corpus too small: {len(files)} files")

    root = files[0].parents[1]
    settings = _settings_from_table({"select": ["ALL"]}, root, None)

    start = time.perf_counter()
    serial = lint_paths(files, settings, jobs=1)
    serial_time = time.perf_counter() - start

    start = time.perf_counter()
    parallel = lint_paths(files, settings, jobs=4)
    parallel_time = time.perf_counter() - start

    assert len(parallel.diagnostics) == len(serial.diagnostics)
    assert parallel_time < serial_time
