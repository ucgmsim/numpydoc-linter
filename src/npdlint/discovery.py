"""Find the Python files to lint."""

from __future__ import annotations

import os
from collections.abc import Iterable, Sequence
from pathlib import Path

import pathspec

from npdlint.config import Settings, _regex, _spec

#: Extensions treated as Python source.
PYTHON_SUFFIXES = (".py", ".pyi")

#: The stub extension, linted only when ``include-stubs`` is set.
STUB_SUFFIX = ".pyi"


def _gitignore_patterns(directory: Path) -> tuple[str, ...]:
    """
    Read the ignore patterns declared in one directory.

    Parameters
    ----------
    directory : pathlib.Path
        The directory to look in.

    Returns
    -------
    tuple of str
        Patterns from ``.gitignore``, empty when absent or unreadable.
    """
    path = directory / ".gitignore"
    try:
        if not path.is_file():
            return ()
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ()
    return tuple(
        line for line in lines if line.strip() and not line.lstrip().startswith("#")
    )


def _root_ignore_patterns(root: Path) -> tuple[str, ...]:
    """
    Read repository-level ignore patterns.

    Parameters
    ----------
    root : pathlib.Path
        Project root.

    Returns
    -------
    tuple of str
        Patterns from the root ``.gitignore`` and ``.git/info/exclude``.
    """
    patterns = list(_gitignore_patterns(root))
    info_exclude = root / ".git" / "info" / "exclude"
    try:
        if info_exclude.is_file():
            patterns.extend(
                line
                for line in info_exclude.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            )
    except OSError:
        pass
    return tuple(patterns)


class _Ignores:
    """
    A stack of gitignore rules, one layer per directory descended into.

    Parameters
    ----------
    root : pathlib.Path
        Project root.
    excludes : tuple of str
        Configured exclude patterns, always in force.
    respect_gitignore : bool
        Whether to read ``.gitignore`` files at all.
    """

    def __init__(
        self, root: Path, excludes: tuple[str, ...], respect_gitignore: bool
    ) -> None:
        self.root = root
        self.excludes = _spec(excludes)
        self.respect_gitignore = respect_gitignore
        self._layers: list[tuple[Path, pathspec.PathSpec]] = []
        if respect_gitignore:
            patterns = _root_ignore_patterns(root)
            if patterns:
                self._layers.append((root, _spec(patterns)))

    def push(self, directory: Path) -> bool:
        """
        Add the ignore rules declared in a directory.

        Parameters
        ----------
        directory : pathlib.Path
            The directory being entered.

        Returns
        -------
        bool
            True when a layer was pushed and must later be popped.
        """
        if not self.respect_gitignore or directory == self.root:
            return False
        patterns = _gitignore_patterns(directory)
        if not patterns:
            return False
        self._layers.append((directory, _spec(patterns)))
        return True

    def pop(self) -> None:
        """Drop the most recently pushed layer."""
        self._layers.pop()

    def is_ignored(self, path: Path, *, is_dir: bool) -> bool:
        """
        Test a path against the excludes and the gitignore stack.

        Parameters
        ----------
        path : pathlib.Path
            The path to test.
        is_dir : bool
            Whether the path is a directory.

        Returns
        -------
        bool
            True when the path should be skipped.
        """
        name = path.name
        rel_root = _relative(path, self.root)
        candidates = [name, rel_root]
        if is_dir:
            candidates += [f"{name}/", f"{rel_root}/"]
        if any(self.excludes.match_file(c) for c in candidates if c):
            return True
        for base, spec in self._layers:
            rel = _relative(path, base)
            if not rel:
                continue
            probes = [rel, name]
            if is_dir:
                probes += [f"{rel}/", f"{name}/"]
            if any(spec.match_file(p) for p in probes):
                return True
        return False


def _relative(path: Path, base: Path) -> str:
    """
    Express a path relative to a base directory, in posix form.

    Parameters
    ----------
    path : pathlib.Path
        The path.
    base : pathlib.Path
        The base directory.

    Returns
    -------
    str
        The relative path, or an empty string when unrelated.
    """
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return ""


def _wanted(path: Path, include_stubs: bool) -> bool:
    """
    Report whether a file should be linted, by extension.

    Parameters
    ----------
    path : pathlib.Path
        The file.
    include_stubs : bool
        Whether ``.pyi`` files are wanted.

    Returns
    -------
    bool
        True when the file is Python source this run should read.
    """
    if path.suffix == STUB_SUFFIX:
        return include_stubs
    return path.suffix in PYTHON_SUFFIXES


def _walk(
    start: Path, ignores: _Ignores, out: list[Path], include_stubs: bool
) -> None:
    """
    Recursively collect Python files under a directory.

    Parameters
    ----------
    start : pathlib.Path
        Directory to walk.
    ignores : _Ignores
        The ignore stack.
    out : list of pathlib.Path
        Accumulator for discovered files.
    include_stubs : bool
        Whether ``.pyi`` files are wanted.
    """
    pushed = ignores.push(start)
    try:
        try:
            entries = sorted(os.scandir(start), key=lambda e: e.name)
        except OSError:
            return
        for entry in entries:
            path = Path(entry.path)
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                continue
            if ignores.is_ignored(path, is_dir=is_dir):
                continue
            if is_dir:
                _walk(path, ignores, out, include_stubs)
            elif _wanted(path, include_stubs):
                out.append(path)
    finally:
        if pushed:
            ignores.pop()


def discover(paths: Sequence[Path], settings: Settings) -> list[Path]:
    """
    Expand the command-line paths into the list of files to lint.

    Directories are walked; named files are taken as given. Configured
    excludes apply to both, so a directory walk and a pre-commit file list
    lint the same set.

    Parameters
    ----------
    paths : sequence of pathlib.Path
        Paths given on the command line, or the configured ``include``.
    settings : Settings
        The settings in force.

    Returns
    -------
    list of pathlib.Path
        Python files to lint, sorted and de-duplicated.
    """
    ignores = _Ignores(
        settings.root, settings.all_excludes(), settings.respect_gitignore
    )
    out: list[Path] = []
    for raw in paths:
        path = raw if raw.is_absolute() else (settings.root / raw)
        if path.is_dir():
            if ignores.is_ignored(path, is_dir=True):
                continue
            _walk(path, ignores, out, settings.include_stubs)
        elif path.is_file():
            if ignores.is_ignored(path, is_dir=False):
                continue
            if not _wanted(path, settings.include_stubs):
                continue
            out.append(path)
    if settings.exclude_file_patterns:
        # numpydoc anchors these at the start of the path, unlike its object
        # patterns, which it searches anywhere.
        patterns = [_regex(p) for p in settings.exclude_file_patterns]
        out = [
            path
            for path in out
            if not any(p.match(_relative(path, settings.root)) for p in patterns)
        ]

    seen: set[Path] = set()
    unique: list[Path] = []
    for path in out:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return sorted(unique)


def default_paths(settings: Settings) -> list[Path]:
    """
    Choose what to lint when the command line names nothing.

    Parameters
    ----------
    settings : Settings
        The settings in force.

    Returns
    -------
    list of pathlib.Path
        The configured ``include``, or the project root.
    """
    if settings.include:
        return [settings.root / p for p in settings.include]
    return [settings.root]


def iter_python_files(paths: Iterable[Path], settings: Settings) -> list[Path]:
    """
    Discover files, falling back to the configured defaults.

    Parameters
    ----------
    paths : iterable of pathlib.Path
        Paths given on the command line.
    settings : Settings
        The settings in force.

    Returns
    -------
    list of pathlib.Path
        Python files to lint.
    """
    given = list(paths)
    return discover(given or default_paths(settings), settings)
