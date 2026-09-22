"""Backwards compatibility with numpydoc's own configuration.

A project already configured for ``numpydoc lint`` keeps its
``[tool.numpydoc_validation]`` table and runs unchanged. The table is read with
numpydoc's semantics, not this tool's: ``checks`` is an allow-list unless it
contains ``"all"``, ``exclude`` holds regular expressions searched against the
object's numpydoc name, ``exclude_files`` holds regular expressions anchored at
the start of the file path, and ``override_<CODE>`` suppresses one check when a
pattern is found in the docstring itself.

Where a native ``[tool.numpydoc-linter]`` table is present as well, it is
layered on top, so a project can migrate one setting at a time.
"""

from __future__ import annotations

import configparser
import tomllib
from pathlib import Path
from typing import Any

#: The table numpydoc reads in ``pyproject.toml``.
TOML_TABLE = "numpydoc_validation"

#: The section numpydoc reads in ``setup.cfg``.
CFG_SECTION = "tool:numpydoc_validation"

#: Prefix marking a per-check docstring override.
OVERRIDE_PREFIX = "override_"

#: The checks numpydoc itself defines. ``checks = ["all"]`` means these and no
#: more, so a legacy configuration never silently enables this tool's own rules.
NUMPYDOC_CODES = (
    "GL01", "GL02", "GL03", "GL05", "GL06", "GL07", "GL08", "GL09", "GL10",
    "SS01", "SS02", "SS03", "SS04", "SS05", "SS06",
    "ES01",
    "PR01", "PR02", "PR03", "PR04", "PR05", "PR06", "PR07", "PR08", "PR09",
    "PR10",
    "RT01", "RT02", "RT03", "RT04", "RT05",
    "YD01",
    "SA01", "SA02", "SA03", "SA04",
    "EX01",
)


class LegacyConfigError(ValueError):
    """Raised when a ``[tool.numpydoc_validation]`` table cannot be used."""


def _as_list(value: Any) -> list[str]:
    """
    Accept numpydoc's single-string-or-list convention.

    Parameters
    ----------
    value : Any
        The configured value.

    Returns
    -------
    list of str
        The value as a list.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value]


def _split_cfg(raw: str) -> list[str]:
    """
    Split a comma-separated ``setup.cfg`` value the way numpydoc does.

    Parameters
    ----------
    raw : str
        The raw option value.

    Returns
    -------
    list of str
        The individual entries, with blanks dropped.
    """
    return [part.strip() for part in raw.rstrip(",").split(",") if part.strip()]


def resolve_checks(checks: list[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """
    Turn numpydoc's ``checks`` value into select and ignore selectors.

    ``["all", "ES01"]`` means every numpydoc check except ``ES01``; any other
    list means exactly the checks named.

    Parameters
    ----------
    checks : list of str
        The configured value.

    Returns
    -------
    tuple
        The select selectors and the ignore selectors.

    Raises
    ------
    LegacyConfigError
        When a check code is not one this tool knows.
    """
    wanted = set(checks)
    known = set(NUMPYDOC_CODES)
    if "all" in wanted:
        blocked = wanted - {"all"}
        unknown = blocked - known
        if unknown:
            raise LegacyConfigError(
                f"unrecognised check code(s) {sorted(unknown)} in "
                f"[tool.{TOML_TABLE}] checks"
            )
        return tuple(sorted(known - blocked)), ()
    unknown = wanted - known
    if unknown:
        raise LegacyConfigError(
            f"unrecognised check code(s) {sorted(unknown)} in "
            f"[tool.{TOML_TABLE}] checks"
        )
    return tuple(sorted(wanted)), ()


def _from_items(items: dict[str, Any], cfg: bool = False) -> dict[str, Any]:
    """
    Build the shared representation from a parsed table.

    Parameters
    ----------
    items : dict
        The table's keys and values.
    cfg : bool
        Whether the values came from ``setup.cfg`` and need splitting.

    Returns
    -------
    dict
        Keys ``checks``, ``exclude``, ``exclude_files`` and ``overrides``.
    """

    def listed(key: str) -> list[str]:
        if key not in items:
            return []
        value = items[key]
        if cfg and isinstance(value, str):
            return _split_cfg(value)
        return _as_list(value)

    overrides: dict[str, tuple[str, ...]] = {}
    for key, value in items.items():
        if not key.startswith(OVERRIDE_PREFIX):
            continue
        code = key[len(OVERRIDE_PREFIX) :].upper()
        patterns = _split_cfg(value) if cfg and isinstance(value, str) else _as_list(
            value
        )
        if patterns:
            overrides[code] = tuple(patterns)

    return {
        "checks": listed("checks"),
        "exclude": listed("exclude"),
        "exclude_files": listed("exclude_files"),
        "overrides": overrides,
    }


def read_legacy(root: Path, config_path: Path | None = None) -> dict[str, Any] | None:
    """
    Read a numpydoc configuration table, if the project has one.

    ``pyproject.toml`` takes precedence: when it exists, ``setup.cfg`` is not
    consulted, matching numpydoc.

    Parameters
    ----------
    root : pathlib.Path
        Project root to look in.
    config_path : pathlib.Path, optional
        An explicit ``pyproject.toml`` to read instead of searching.

    Returns
    -------
    dict or None
        The parsed table, or None when the project has no numpydoc config.

    Raises
    ------
    LegacyConfigError
        When the file exists but cannot be parsed.
    """
    toml_path = config_path or (root / "pyproject.toml")
    if toml_path.is_file():
        try:
            data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, OSError) as exc:
            raise LegacyConfigError(f"{toml_path}: {exc}") from exc
        table = data.get("tool", {}).get(TOML_TABLE)
        if table is None:
            return None
        return _from_items(dict(table))

    cfg_path = root / "setup.cfg"
    if cfg_path.is_file():
        parser = configparser.ConfigParser()
        try:
            parser.read(cfg_path)
        except configparser.Error as exc:
            raise LegacyConfigError(f"{cfg_path}: {exc}") from exc
        if not parser.has_section(CFG_SECTION):
            return None
        return _from_items(dict(parser.items(CFG_SECTION)), cfg=True)

    return None
