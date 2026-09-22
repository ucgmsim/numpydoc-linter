"""Settings, scope blocks, and loading them from ``pyproject.toml``."""

from __future__ import annotations

import dataclasses
import re
import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import pathspec

from numpydoc_linter import compat, selection
from numpydoc_linter.rules import registry
from numpydoc_linter.targets import (
    DEFAULT_DATACLASS_DECORATORS,
    DEFAULT_PROPERTY_DECORATORS,
    KIND_GROUPS,
    Kind,
    Target,
)

#: Section of ``pyproject.toml`` this tool reads.
TOOL_TABLE = "numpydoc-linter"

#: Directories never walked, regardless of configuration.
DEFAULT_EXCLUDES = (
    ".bzr",
    ".direnv",
    ".eggs",
    ".git",
    ".hg",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".tox",
    ".venv",
    "__pycache__",
    "__pypackages__",
    "build",
    "dist",
    "node_modules",
    "site-packages",
    "venv",
)


class ConfigError(ValueError):
    """Raised when configuration cannot be understood."""


def _pattern_factory() -> str:
    """
    Pick the gitignore pattern factory this pathspec version prefers.

    Returns
    -------
    str
        The factory name to pass to ``PathSpec.from_lines``.
    """
    try:
        pathspec.PathSpec.from_lines("gitignore", [])
    except Exception:
        return "gitwildmatch"
    return "gitignore"


_FACTORY = _pattern_factory()


@lru_cache(maxsize=256)
def _spec(patterns: tuple[str, ...]) -> pathspec.PathSpec:
    """
    Compile gitignore-style patterns, caching the result.

    Parameters
    ----------
    patterns : tuple of str
        Patterns to compile.

    Returns
    -------
    pathspec.PathSpec
        The compiled specification.
    """
    return pathspec.PathSpec.from_lines(_FACTORY, patterns)


@lru_cache(maxsize=512)
def _regex(pattern: str) -> re.Pattern[str]:
    """
    Compile a regular expression, caching the result.

    Parameters
    ----------
    pattern : str
        The pattern.

    Returns
    -------
    re.Pattern
        The compiled pattern.
    """
    return re.compile(pattern)


def _as_tuple(value: Any, key: str) -> tuple[str, ...]:
    """
    Accept either a single string or a list of strings.

    Parameters
    ----------
    value : Any
        The configured value.
    key : str
        Key name, used in the error message.

    Returns
    -------
    tuple of str
        The normalised value.

    Raises
    ------
    ConfigError
        When the value is neither a string nor a list of strings.
    """
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list | tuple) and all(isinstance(v, str) for v in value):
        return tuple(value)
    raise ConfigError(f"{key} must be a string or a list of strings, got {value!r}")


#: Boolean predicates a scope may match on, mapped to the Target attribute.
BOOL_PREDICATES = {
    "private": "is_private",
    "dunder": "is_dunder",
    "abstract": "is_abstract",
    "stub": "is_stub",
    "overload": "is_overload",
    "override": "is_override",
    "async": "is_async",
    "generator": "is_generator",
    "returns-value": "returns_value",
    "has-docstring": "has_docstring",
    "dataclass": "is_dataclass",
    "nested": "is_nested",
}

#: Every key a ``match`` table may contain.
MATCH_KEYS = frozenset(
    {"kind", "name", "qualname", "path", "decorator", "parent-kind", "in-all"}
    | set(BOOL_PREDICATES)
)


@dataclass(frozen=True, slots=True)
class Matcher:
    """
    A predicate over targets, built from a scope block's ``match`` table.

    All populated fields must hold for the matcher to apply.

    Parameters
    ----------
    kinds : frozenset of Kind or None
        Kinds to match, or None to match any.
    name : str or None
        Regular expression searched against the bare name.
    qualname : str or None
        Regular expression searched against the dotted name.
    paths : tuple of str
        Gitignore-style patterns matched against the file path.
    decorators : tuple of str
        Decorator names, any one of which is enough to match.
    parent_kinds : frozenset of Kind or None
        Kinds the enclosing object may have.
    in_all : bool or None
        Required membership of the module's ``__all__``.
    booleans : tuple
        Pairs of Target attribute name and the value it must take.
    """

    kinds: frozenset[Kind] | None = None
    name: str | None = None
    qualname: str | None = None
    paths: tuple[str, ...] = ()
    decorators: tuple[str, ...] = ()
    parent_kinds: frozenset[Kind] | None = None
    in_all: bool | None = None
    booleans: tuple[tuple[str, bool], ...] = ()

    @classmethod
    def from_table(cls, table: dict[str, Any]) -> Matcher:
        """
        Build a matcher from a configuration table.

        Parameters
        ----------
        table : dict
            The ``match`` table.

        Returns
        -------
        Matcher
            The compiled predicate.

        Raises
        ------
        ConfigError
            When the table contains an unknown key or an unknown kind.
        """
        unknown = set(table) - MATCH_KEYS
        if unknown:
            raise ConfigError(
                f"unknown match key(s) {sorted(unknown)}; "
                f"valid keys are {sorted(MATCH_KEYS)}"
            )

        def kinds(key: str) -> frozenset[Kind] | None:
            if key not in table:
                return None
            out: set[Kind] = set()
            for raw in _as_tuple(table[key], key):
                if raw in KIND_GROUPS:
                    out.update(KIND_GROUPS[raw])
                    continue
                try:
                    out.add(Kind(raw))
                except ValueError:
                    raise ConfigError(
                        f"unknown kind {raw!r}; valid kinds are "
                        f"{sorted(k.value for k in Kind)} "
                        f"or groups {sorted(KIND_GROUPS)}"
                    ) from None
            return frozenset(out)

        booleans = tuple(
            (BOOL_PREDICATES[key], bool(table[key]))
            for key in sorted(BOOL_PREDICATES)
            if key in table
        )
        return cls(
            kinds=kinds("kind"),
            name=table.get("name"),
            qualname=table.get("qualname"),
            paths=_as_tuple(table["path"], "path") if "path" in table else (),
            decorators=(
                _as_tuple(table["decorator"], "decorator")
                if "decorator" in table
                else ()
            ),
            parent_kinds=kinds("parent-kind"),
            in_all=table.get("in-all"),
            booleans=booleans,
        )

    def matches(self, target: Target, relative_path: str) -> bool:
        """
        Test the predicate against one target.

        Parameters
        ----------
        target : Target
            The object being considered.
        relative_path : str
            The target's file, relative to the project root, in posix form.

        Returns
        -------
        bool
            True when every populated field holds.
        """
        if self.kinds is not None and target.kind not in self.kinds:
            return False
        if self.name is not None and not _regex(self.name).search(target.name):
            return False
        if self.qualname is not None and not _regex(self.qualname).search(
            target.qualname
        ):
            return False
        if self.paths and not _spec(self.paths).match_file(relative_path):
            return False
        if self.decorators and not (set(self.decorators) & set(target.decorators)):
            return False
        if self.parent_kinds is not None:
            parent = target.parent
            if parent is None or parent.kind not in self.parent_kinds:
                return False
        if self.in_all is not None and target.in_all is not self.in_all:
            return False
        for attr, expected in self.booleans:
            if bool(getattr(target, attr)) is not expected:
                return False
        return True


@dataclass(frozen=True, slots=True)
class ScopeBlock:
    """
    One conditional override of the rule set.

    Parameters
    ----------
    matcher : Matcher
        Which targets this block applies to.
    index : int
        Position in the configuration, used when explaining resolution.
    select : tuple of str or None
        Selectors that replace the incoming rule set.
    ignore : tuple of str or None
        Selectors that disable rules.
    extend_select : tuple of str
        Selectors that add to the incoming rule set.
    extend_ignore : tuple of str
        Further selectors that disable rules.
    skip : bool
        Whether to disable every rule for matching targets.
    options : tuple
        Pairs of rule-option name and value.
    """

    matcher: Matcher
    index: int
    select: tuple[str, ...] | None = None
    ignore: tuple[str, ...] | None = None
    extend_select: tuple[str, ...] = ()
    extend_ignore: tuple[str, ...] = ()
    skip: bool = False
    options: tuple[tuple[str, Any], ...] = ()

    @classmethod
    def from_table(cls, table: dict[str, Any], index: int) -> ScopeBlock:
        """
        Build a scope block from a configuration table.

        Parameters
        ----------
        table : dict
            One entry of the ``scope`` array.
        index : int
            Position in the array.

        Returns
        -------
        ScopeBlock
            The parsed block.

        Raises
        ------
        ConfigError
            When the block contains an unknown key.
        """
        structural = {
            "match",
            "select",
            "ignore",
            "extend-select",
            "extend-ignore",
            "skip",
        }
        legal_options = registry.option_keys()
        unknown = set(table) - structural - legal_options
        if unknown:
            raise ConfigError(
                f"unknown key(s) {sorted(unknown)} in scope block {index}; "
                f"valid keys are {sorted(structural | legal_options)}"
            )
        match_table = table.get("match", {})
        if not isinstance(match_table, dict):
            raise ConfigError(f"scope block {index}: 'match' must be a table")
        options = tuple(
            (key, table[key]) for key in sorted(legal_options) if key in table
        )
        return cls(
            matcher=Matcher.from_table(match_table),
            index=index,
            select=(
                _as_tuple(table["select"], "select") if "select" in table else None
            ),
            ignore=(
                _as_tuple(table["ignore"], "ignore") if "ignore" in table else None
            ),
            extend_select=(
                _as_tuple(table["extend-select"], "extend-select")
                if "extend-select" in table
                else ()
            ),
            extend_ignore=(
                _as_tuple(table["extend-ignore"], "extend-ignore")
                if "extend-ignore" in table
                else ()
            ),
            skip=bool(table.get("skip", False)),
            options=options,
        )


@dataclass(frozen=True, slots=True)
class Settings:
    """
    Everything the linter needs to run, after merging config and CLI flags.

    Parameters
    ----------
    root : pathlib.Path
        Project root, which paths are reported relative to.
    include : tuple of str
        Paths to lint when the command line names none.
    exclude : tuple of str
        Gitignore-style patterns never linted.
    extend_exclude : tuple of str
        Further exclude patterns, added rather than replacing.
    respect_gitignore : bool
        Whether to honour ``.gitignore`` files.
    include_stubs : bool
        Whether to lint ``.pyi`` stub files, which normally carry no
        docstrings because the implementation holds them.
    select : tuple of str
        Selectors choosing the base rule set.
    ignore : tuple of str
        Selectors disabling rules from the base set.
    extend_select : tuple of str
        Selectors adding to the base set.
    extend_ignore : tuple of str
        Further selectors disabling rules.
    per_file_ignores : tuple
        Pairs of path pattern and the selectors to disable for it.
    exclude_object_patterns : tuple of str
        Regular expressions searched against an object's numpydoc name; a
        match exempts it from every rule.
    exclude_file_patterns : tuple of str
        Regular expressions anchored at the start of a file's path; a match
        skips the file.
    overrides : tuple
        Pairs of rule code and the regular expressions that, when found in a
        docstring, suppress that rule for it.
    numpydoc_compat : bool
        Whether to read a ``[tool.numpydoc_validation]`` table as defaults.
    legacy_config : bool
        Whether such a table was actually found and used.
    scopes : tuple of ScopeBlock
        Conditional overrides, applied in order.
    options : tuple
        Pairs of rule-option name and value, before any scope override.
    property_decorators : tuple of str
        Decorator names that mark a read-only property.
    dataclass_decorators : tuple of str
        Decorator names that synthesise a constructor from class attributes.
    plugins : tuple of str
        Local plugin paths or dotted module names providing extra rules.
    config_path : pathlib.Path or None
        The file these settings were read from.
    """

    root: Path = field(default_factory=Path.cwd)
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    extend_exclude: tuple[str, ...] = ()
    respect_gitignore: bool = True
    include_stubs: bool = False
    select: tuple[str, ...] = (selection.ALL,)
    ignore: tuple[str, ...] = ()
    extend_select: tuple[str, ...] = ()
    extend_ignore: tuple[str, ...] = ()
    per_file_ignores: tuple[tuple[str, tuple[str, ...]], ...] = ()
    exclude_object_patterns: tuple[str, ...] = ()
    exclude_file_patterns: tuple[str, ...] = ()
    overrides: tuple[tuple[str, tuple[str, ...]], ...] = ()
    numpydoc_compat: bool = True
    legacy_config: bool = False
    scopes: tuple[ScopeBlock, ...] = ()
    options: tuple[tuple[str, Any], ...] = ()
    property_decorators: tuple[str, ...] = DEFAULT_PROPERTY_DECORATORS
    dataclass_decorators: tuple[str, ...] = DEFAULT_DATACLASS_DECORATORS
    plugins: tuple[str, ...] = ()
    config_path: Path | None = None

    @property
    def base_options(self) -> dict[str, Any]:
        """
        Get the rule options that apply before any scope block.

        Returns
        -------
        dict
            Option name to value.
        """
        return dict(self.options)

    def all_excludes(self) -> tuple[str, ...]:
        """
        Build the effective exclude list.

        Following ruff, ``exclude`` replaces the built-in defaults while
        ``extend-exclude`` adds to them, so the common case of adding one more
        directory does not silently start walking ``.venv``.

        Returns
        -------
        tuple of str
            Patterns in gitignore syntax.
        """
        base = self.exclude if self.exclude else tuple(DEFAULT_EXCLUDES)
        return base + self.extend_exclude


def find_pyproject(start: Path) -> Path | None:
    """
    Walk upwards looking for the nearest ``pyproject.toml``.

    Parameters
    ----------
    start : pathlib.Path
        Directory to start from.

    Returns
    -------
    pathlib.Path or None
        The file, when found.
    """
    start = start.resolve()
    for directory in (start, *start.parents):
        candidate = directory / "pyproject.toml"
        if candidate.is_file():
            return candidate
    return None


def load_settings(
    config_path: Path | None = None, root: Path | None = None
) -> Settings:
    """
    Read settings from ``pyproject.toml``.

    Parameters
    ----------
    config_path : pathlib.Path, optional
        Explicit path to a ``pyproject.toml``. Discovered when omitted.
    root : pathlib.Path, optional
        Directory to search from, defaulting to the working directory.

    Returns
    -------
    Settings
        The parsed settings, with defaults where the file is silent.

    Raises
    ------
    ConfigError
        When the file cannot be parsed or contains unknown keys.
    """
    if config_path is None:
        config_path = find_pyproject(root or Path.cwd())
    if config_path is not None and config_path.is_dir():
        config_path = config_path / "pyproject.toml"

    if config_path is None:
        # No pyproject.toml, but the project may still carry a numpydoc
        # section in setup.cfg, which is where numpydoc looks next.
        base_root = (root or Path.cwd()).resolve()
        table, legacy_used = _merge_legacy({}, base_root, None)
        settings = _settings_from_table(table, base_root, None)
        return dataclasses.replace(settings, legacy_config=legacy_used)

    if not config_path.is_file():
        raise ConfigError(f"no such config file: {config_path}")

    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{config_path}: {exc}") from exc

    table = data.get("tool", {}).get(TOOL_TABLE, {})
    project_root = config_path.parent.resolve()
    table, legacy_used = _merge_legacy(table, project_root, config_path)
    settings = _settings_from_table(table, project_root, config_path)
    return dataclasses.replace(settings, legacy_config=legacy_used)


def _merge_legacy(
    table: dict[str, Any], root: Path, config_path: Path | None
) -> tuple[dict[str, Any], bool]:
    """
    Use a numpydoc configuration table as defaults beneath the native one.

    A project already set up for ``numpydoc lint`` therefore runs unchanged,
    and can move one setting at a time: anything written natively wins.

    Parameters
    ----------
    table : dict
        The native ``[tool.numpydoc-linter]`` table.
    root : pathlib.Path
        Project root.
    config_path : pathlib.Path or None
        The file the native table came from.

    Returns
    -------
    tuple
        The merged table, and whether a legacy table was used.

    Raises
    ------
    ConfigError
        When the legacy table cannot be understood.
    """
    if not bool(table.get("numpydoc-compat", True)):
        return table, False
    try:
        legacy = compat.read_legacy(root, config_path)
    except compat.LegacyConfigError as exc:
        raise ConfigError(str(exc)) from exc
    if legacy is None:
        return table, False

    try:
        select, _ = (
            compat.resolve_checks(legacy["checks"])
            if legacy["checks"]
            else (compat.NUMPYDOC_CODES, ())
        )
    except compat.LegacyConfigError as exc:
        raise ConfigError(str(exc)) from exc

    base: dict[str, Any] = {"select": list(select)}
    if legacy["exclude"]:
        base["exclude-object-patterns"] = legacy["exclude"]
    if legacy["exclude_files"]:
        base["exclude-file-patterns"] = legacy["exclude_files"]
    if legacy["overrides"]:
        base["overrides"] = legacy["overrides"]

    merged = {**base, **table}
    return merged, True


def _settings_from_table(
    table: dict[str, Any], root: Path, config_path: Path | None
) -> Settings:
    """
    Build settings from an already-parsed table.

    Parameters
    ----------
    table : dict
        The ``[tool.numpydoc-linter]`` table.
    root : pathlib.Path
        Project root.
    config_path : pathlib.Path or None
        Where the table came from.

    Returns
    -------
    Settings
        The parsed settings.

    Raises
    ------
    ConfigError
        When the table contains an unknown key.
    """
    known = {
        "include",
        "exclude",
        "extend-exclude",
        "respect-gitignore",
        "include-stubs",
        "select",
        "ignore",
        "extend-select",
        "extend-ignore",
        "per-file-ignores",
        "exclude-object-patterns",
        "exclude-file-patterns",
        "overrides",
        "numpydoc-compat",
        "scope",
        "property-decorators",
        "dataclass-decorators",
        "plugins",
    }
    legal_options = registry.option_keys()
    unknown = set(table) - known - legal_options
    if unknown:
        raise ConfigError(
            f"unknown key(s) {sorted(unknown)} in [tool.{TOOL_TABLE}]; "
            f"valid keys are {sorted(known | legal_options)}"
        )

    per_file: list[tuple[str, tuple[str, ...]]] = []
    for pattern, codes in (table.get("per-file-ignores") or {}).items():
        per_file.append((pattern, _as_tuple(codes, f"per-file-ignores[{pattern}]")))

    scopes = tuple(
        ScopeBlock.from_table(block, i)
        for i, block in enumerate(table.get("scope") or [])
    )

    return Settings(
        root=root,
        include=_as_tuple(table["include"], "include") if "include" in table else (),
        exclude=_as_tuple(table["exclude"], "exclude") if "exclude" in table else (),
        extend_exclude=(
            _as_tuple(table["extend-exclude"], "extend-exclude")
            if "extend-exclude" in table
            else ()
        ),
        respect_gitignore=bool(table.get("respect-gitignore", True)),
        include_stubs=bool(table.get("include-stubs", False)),
        select=(
            _as_tuple(table["select"], "select")
            if "select" in table
            else (selection.ALL,)
        ),
        ignore=_as_tuple(table["ignore"], "ignore") if "ignore" in table else (),
        extend_select=(
            _as_tuple(table["extend-select"], "extend-select")
            if "extend-select" in table
            else ()
        ),
        extend_ignore=(
            _as_tuple(table["extend-ignore"], "extend-ignore")
            if "extend-ignore" in table
            else ()
        ),
        per_file_ignores=tuple(per_file),
        exclude_object_patterns=(
            _as_tuple(table["exclude-object-patterns"], "exclude-object-patterns")
            if "exclude-object-patterns" in table
            else ()
        ),
        exclude_file_patterns=(
            _as_tuple(table["exclude-file-patterns"], "exclude-file-patterns")
            if "exclude-file-patterns" in table
            else ()
        ),
        overrides=tuple(
            (code.upper(), _as_tuple(patterns, f"overrides[{code}]"))
            for code, patterns in (table.get("overrides") or {}).items()
        ),
        numpydoc_compat=bool(table.get("numpydoc-compat", True)),
        scopes=scopes,
        options=tuple(
            (key, table[key]) for key in sorted(legal_options) if key in table
        ),
        property_decorators=(
            tuple(DEFAULT_PROPERTY_DECORATORS)
            + _as_tuple(table["property-decorators"], "property-decorators")
            if "property-decorators" in table
            else DEFAULT_PROPERTY_DECORATORS
        ),
        dataclass_decorators=(
            tuple(DEFAULT_DATACLASS_DECORATORS)
            + _as_tuple(table["dataclass-decorators"], "dataclass-decorators")
            if "dataclass-decorators" in table
            else DEFAULT_DATACLASS_DECORATORS
        ),
        plugins=_as_tuple(table["plugins"], "plugins") if "plugins" in table else (),
        config_path=config_path,
    )
