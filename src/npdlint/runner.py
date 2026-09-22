"""Run the enabled rules over a set of files."""

from __future__ import annotations

import os
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from npdlint import plugins
from npdlint.config import Settings
from npdlint.diagnostics import Diagnostic
from npdlint.rules.base import Context, registry
from npdlint.scope import Resolver
from npdlint.source import (
    SourceError,
    SourceFile,
    SuppressionUsage,
    read_source,
)
from npdlint.targets import Target, collect_targets

#: Code reported for a file that could not be read or parsed.
SYNTAX_ERROR_CODE = "E902"

#: Below this many files, the pool costs more than it saves.
PARALLEL_THRESHOLD = 24


def _is_file_rule(rule) -> bool:
    """
    Report whether a rule runs once per file rather than once per target.

    Parameters
    ----------
    rule : Rule
        The rule.

    Returns
    -------
    bool
        True for a file-level rule. Plugins predating the attribute are
        treated as ordinary per-target rules.
    """
    return bool(getattr(rule, "per_file", False))


@dataclass(slots=True)
class FileResult:
    """
    What linting one file produced.

    Parameters
    ----------
    path : pathlib.Path
        The file.
    diagnostics : list of Diagnostic
        Violations found.
    error : str or None
        Message when the file could not be processed.
    """

    path: Path
    diagnostics: list[Diagnostic] = field(default_factory=list)
    error: str | None = None


@dataclass(slots=True)
class LintResult:
    """
    The outcome of a whole run.

    Parameters
    ----------
    diagnostics : list of Diagnostic
        Every violation, sorted.
    errors : list of str
        Messages for files that could not be processed.
    files_checked : int
        How many files were read successfully.
    """

    diagnostics: list[Diagnostic] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    files_checked: int = 0

    @property
    def ok(self) -> bool:
        """
        Report whether the run found nothing to complain about.

        Returns
        -------
        bool
            True when there were no diagnostics and no errors.
        """
        return not self.diagnostics and not self.errors


def lint_source(
    source: SourceFile, settings: Settings, resolver: Resolver | None = None
) -> list[Diagnostic]:
    """
    Run the enabled rules over one already-parsed file.

    Parameters
    ----------
    source : SourceFile
        The parsed file.
    settings : Settings
        The settings in force.
    resolver : Resolver, optional
        A resolver to reuse; one is built when omitted.

    Returns
    -------
    list of Diagnostic
        Violations found, in source order.
    """
    resolver = resolver or Resolver(settings, registry.codes())
    targets = collect_targets(
        source.tree,
        source.path,
        source.module_name,
        settings.property_decorators,
        settings.dataclass_decorators,
    )
    by_qualname = {t.qualname: t for t in targets}

    file_rules = tuple(
        rule
        for code in sorted(resolver.file_codes(source.relative_path))
        if (rule := registry.get(code)) is not None and _is_file_rule(rule)
    )
    # Tracking what each suppression comment did means running rules whose
    # output is about to be thrown away, so only do it when a file-level rule
    # is going to ask, and only for a file that has comments to judge.
    usage = SuppressionUsage() if file_rules and source.noqa else None

    out: list[Diagnostic] = []
    seen: set[tuple[str, int, int, str]] = set()

    def add(diagnostic: Diagnostic) -> None:
        """
        Collect one diagnostic, dropping exact duplicates.

        Parameters
        ----------
        diagnostic : Diagnostic
            The diagnostic to keep.
        """
        key = (
            diagnostic.code,
            diagnostic.line,
            diagnostic.col,
            diagnostic.message,
        )
        if key in seen:
            return
        seen.add(key)
        out.append(diagnostic)

    for target in targets:
        lines = source.suppression_lines(target) if source.noqa else ()
        if usage is not None:
            usage.attach(lines)
        if resolver.is_excluded_object(target):
            continue
        resolution = resolver.resolve(target, source.relative_path)
        if not resolution.enabled:
            continue
        ctx = Context(
            source=source,
            options=resolution.options,
            targets_by_qualname=by_qualname,
            usage=usage,
        )
        for code in sorted(resolution.enabled):
            rule = registry.get(code)
            if rule is None or _is_file_rule(rule):
                continue
            hits = source.suppressions_on(lines, code) if lines else ()
            if hits and usage is None:
                continue
            # numpydoc stops after reporting a missing docstring; so do we.
            missing = rule.requires_docstring and not target.has_docstring
            if target.kind not in rule.kinds or missing:
                # The rule cannot fire here, which is all that a suppression
                # for it needs to know.
                if hits:
                    usage.record(hits, code, fired=False)
                continue
            if resolver.is_overridden(code, target):
                # Configuration suppresses this already, so a comment for it
                # is not judged either way.
                continue
            found = list(rule.check(target, ctx))
            if hits:
                usage.record(hits, code, fired=bool(found))
                continue
            for diagnostic in found:
                add(diagnostic)

    if file_rules:
        file_ctx = Context(
            source=source,
            options=resolver.settings.base_options,
            targets_by_qualname=by_qualname,
            usage=usage,
        )
        for rule in file_rules:
            for diagnostic in rule.check_file(file_ctx):
                add(diagnostic)

    out.sort(key=lambda d: d.sort_key)
    return out


def lint_file(
    path: Path, settings: Settings, resolver: Resolver | None = None
) -> FileResult:
    """
    Read and lint one file.

    Parameters
    ----------
    path : pathlib.Path
        The file to lint.
    settings : Settings
        The settings in force.
    resolver : Resolver, optional
        A resolver to reuse.

    Returns
    -------
    FileResult
        Diagnostics, or an error message when the file could not be processed.
    """
    try:
        source = read_source(path, settings.root)
    except SourceError as exc:
        rel = _display(path, settings.root)
        return FileResult(
            path=path,
            error=f"{rel}:{exc.line}:{exc.col}: {SYNTAX_ERROR_CODE} {exc.message}",
        )
    return FileResult(path=path, diagnostics=lint_source(source, settings, resolver))


def _display(path: Path, root: Path) -> str:
    """
    Render a path for display, relative to the project root when possible.

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


_WORKER_SETTINGS: Settings | None = None
_WORKER_RESOLVER: Resolver | None = None


def _init_worker(settings: Settings) -> None:
    """
    Prepare a worker process.

    Plugins are re-loaded here because the registry does not survive pickling.

    Parameters
    ----------
    settings : Settings
        The settings in force.
    """
    global _WORKER_SETTINGS, _WORKER_RESOLVER
    plugins.load_all(settings.plugins, settings.root)
    _WORKER_SETTINGS = settings
    _WORKER_RESOLVER = Resolver(settings, registry.codes())


def _worker(path: Path) -> FileResult:
    """
    Lint one file inside a worker process.

    Parameters
    ----------
    path : pathlib.Path
        The file to lint.

    Returns
    -------
    FileResult
        The result.
    """
    assert _WORKER_SETTINGS is not None
    return lint_file(path, _WORKER_SETTINGS, _WORKER_RESOLVER)


def lint_paths(
    paths: Sequence[Path], settings: Settings, *, jobs: int | None = None
) -> LintResult:
    """
    Lint a list of files, in parallel when there are enough of them.

    Parameters
    ----------
    paths : sequence of pathlib.Path
        Files to lint.
    settings : Settings
        The settings in force.
    jobs : int, optional
        Worker count. One means run in this process; None picks a default.

    Returns
    -------
    LintResult
        Every diagnostic, sorted, plus any per-file errors.
    """
    files = list(paths)
    result = LintResult()
    if not files:
        return result

    if jobs is None:
        jobs = min(len(files) // PARALLEL_THRESHOLD + 1, os.cpu_count() or 1)
    jobs = max(1, jobs)

    if jobs == 1 or len(files) < PARALLEL_THRESHOLD:
        resolver = Resolver(settings, registry.codes())
        results = [lint_file(path, settings, resolver) for path in files]
    else:
        chunk = max(1, len(files) // (jobs * 4))
        with ProcessPoolExecutor(
            max_workers=jobs, initializer=_init_worker, initargs=(settings,)
        ) as pool:
            results = list(pool.map(_worker, files, chunksize=chunk))

    for file_result in results:
        if file_result.error is not None:
            result.errors.append(file_result.error)
        else:
            result.files_checked += 1
            result.diagnostics.extend(file_result.diagnostics)

    result.diagnostics.sort(key=lambda d: d.sort_key)
    result.errors.sort()
    return result


#: How many codes to name before summarising the rest.
_MAX_LISTED_CODES = 6


def _codes(codes: frozenset[str]) -> str:
    """
    Render a set of codes compactly, summarising a long list.

    Parameters
    ----------
    codes : frozenset of str
        The codes to render.

    Returns
    -------
    str
        A comma-separated list, truncated when long.
    """
    ordered = sorted(codes)
    if len(ordered) <= _MAX_LISTED_CODES:
        return ",".join(ordered)
    shown = ",".join(ordered[:_MAX_LISTED_CODES])
    return f"{shown} and {len(ordered) - _MAX_LISTED_CODES} more"


def explain_target(
    target: Target, source: SourceFile, settings: Settings
) -> list[str]:
    """
    Describe how the rule set for one target was arrived at.

    Parameters
    ----------
    target : Target
        The object to explain.
    source : SourceFile
        The file it came from.
    settings : Settings
        The settings in force.

    Returns
    -------
    list of str
        Lines of explanation.
    """
    resolver = Resolver(settings, registry.codes())
    resolution = resolver.resolve(target, source.relative_path, trace=True)

    lines = [
        f"{_display(target.path, settings.root)}:{target.lineno}:{target.col}",
        f"  object     {target.qualname}",
        f"  kind       {target.kind}",
    ]
    flags = [
        name
        for name, value in (
            ("private", target.is_private),
            ("dunder", target.is_dunder),
            ("async", target.is_async),
            ("abstract", target.is_abstract),
            ("stub", target.is_stub),
            ("overload", target.is_overload),
            ("override", target.is_override),
            ("generator", target.is_generator),
            ("returns-value", target.returns_value),
            ("has-docstring", target.has_docstring),
            ("dataclass", target.is_dataclass),
            ("nested", target.is_nested),
        )
        if value
    ]
    lines.append(f"  flags      {', '.join(flags) or 'none'}")
    if target.decorators:
        lines.append(f"  decorators {', '.join(target.decorators)}")
    lines.append("")
    lines.append("  resolution")
    for step in resolution.steps:
        detail = []
        if step.added:
            detail.append(f"+{_codes(step.added)}")
        if step.removed:
            detail.append(f"-{_codes(step.removed)}")
        suffix = f"  ({'; '.join(detail)})" if detail else ""
        lines.append(f"    {step.label:<24}{len(step.enabled):>3} enabled{suffix}")
    if resolution.options:
        lines.append("")
        lines.append("  options")
        for key, value in sorted(resolution.options.items()):
            lines.append(f"    {key} = {value!r}")
    lines.append("")
    enabled = sorted(
        code
        for code in resolution.enabled
        if not _is_file_rule(registry.get(code))
    )
    lines.append(f"  enabled    {', '.join(enabled) if enabled else 'none'}")
    suppressed = sorted(
        code for code in enabled if source.is_suppressed(code, target)
    )
    if suppressed:
        lines.append(f"  suppressed {', '.join(suppressed)}  (inline comment)")
    overridden = sorted(
        code for code in enabled if resolver.is_overridden(code, target)
    )
    if overridden:
        lines.append(f"  overridden {', '.join(overridden)}  (docstring pattern)")
    if resolver.is_excluded_object(target):
        lines.append("  excluded   by exclude-object-patterns")
    file_level = sorted(
        code
        for code in resolver.file_codes(source.relative_path)
        if _is_file_rule(registry.get(code))
    )
    if file_level:
        joined = ", ".join(file_level)
        lines.append(f"  file rules {joined}  (whole file, not this object)")
    return lines
