"""Command-line interface."""

from __future__ import annotations

import argparse
import dataclasses
import sys
from collections.abc import Sequence
from pathlib import Path

from npdlint import __version__, output, plugins, selection
from npdlint.config import ConfigError, Settings, load_settings
from npdlint.discovery import iter_python_files
from npdlint.rules.base import registry
from npdlint.runner import explain_target, lint_paths
from npdlint.source import SourceError, read_source
from npdlint.targets import collect_targets

#: Exit code when the run found violations.
EXIT_VIOLATIONS = 1
#: Exit code when the tool could not run.
EXIT_ERROR = 2


def _split_codes(values: Sequence[str] | None) -> tuple[str, ...]:
    """
    Split repeated comma- or space-separated code options.

    Parameters
    ----------
    values : sequence of str or None
        Raw option values.

    Returns
    -------
    tuple of str
        Individual selectors, upper-cased.
    """
    out: list[str] = []
    for value in values or ():
        for part in value.replace(",", " ").split():
            out.append(part.strip().upper())
    return tuple(out)


def build_parser() -> argparse.ArgumentParser:
    """
    Build the argument parser.

    Returns
    -------
    argparse.ArgumentParser
        The configured parser.
    """
    parser = argparse.ArgumentParser(
        prog="npdlint",
        description="Lint numpydoc-style docstrings.",
    )
    parser.add_argument("--version", action="version", version=f"npdlint {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    check = subparsers.add_parser(
        "check", help="lint files or directories (the default command)"
    )
    _add_check_arguments(check)
    check.set_defaults(func=command_check)

    rule = subparsers.add_parser("rule", help="describe rules")
    rule.add_argument(
        "codes", nargs="*", help="rule codes to describe; all of them when omitted"
    )
    rule.add_argument(
        "--output-format", choices=("text", "json"), default="text"
    )
    rule.set_defaults(func=command_rule)

    explain = subparsers.add_parser(
        "explain", help="show which rules apply at a source location"
    )
    explain.add_argument(
        "location", help="FILE, FILE:LINE, or a dotted qualified name"
    )
    explain.add_argument("--config", type=Path, default=None)
    explain.set_defaults(func=command_explain)

    return parser


def _add_check_arguments(parser: argparse.ArgumentParser) -> None:
    """
    Add the options of the ``check`` command.

    Parameters
    ----------
    parser : argparse.ArgumentParser
        The subparser to populate.
    """
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="files or directories; the configured include, or '.', when omitted",
    )
    parser.add_argument(
        "--config", type=Path, default=None, help="path to a pyproject.toml"
    )
    parser.add_argument(
        "--select", action="append", metavar="CODES", help="replace the selected rules"
    )
    parser.add_argument(
        "--extend-select", action="append", metavar="CODES", help="enable more rules"
    )
    parser.add_argument(
        "--ignore", action="append", metavar="CODES", help="disable rules"
    )
    parser.add_argument(
        "--extend-ignore", action="append", metavar="CODES", help="disable more rules"
    )
    parser.add_argument(
        "--exclude", action="append", metavar="PATTERN", help="replace exclude patterns"
    )
    parser.add_argument(
        "--extend-exclude", action="append", metavar="PATTERN", help="exclude more"
    )
    parser.add_argument(
        "--respect-gitignore",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="honour .gitignore files (default: yes)",
    )
    parser.add_argument(
        "--include-stubs",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="lint .pyi stub files (default: no)",
    )
    parser.add_argument(
        "--output-format",
        choices=output.FORMATS,
        default="concise",
        help="how to render diagnostics (default: concise)",
    )
    parser.add_argument(
        "--statistics", action="store_true", help="summarise counts per rule"
    )
    parser.add_argument(
        "--jobs",
        "-j",
        type=int,
        default=None,
        help="worker processes; 1 disables parallelism",
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true", help="suppress the summary line"
    )
    parser.add_argument(
        "--exit-zero", action="store_true", help="always exit 0, even on violations"
    )
    parser.add_argument(
        "--show-files",
        action="store_true",
        help="list the discovered files and exit without linting",
    )
    parser.add_argument(
        "--show-settings",
        action="store_true",
        help="print the resolved settings and exit",
    )


def _print_notices(settings: Settings) -> None:
    """
    Report anything the configuration itself needs saying about.

    Parameters
    ----------
    settings : Settings
        The loaded settings.
    """
    for notice in settings.notices:
        print(f"warning: {notice}", file=sys.stderr)


def _apply_overrides(settings: Settings, args: argparse.Namespace) -> Settings:
    """
    Layer command-line options over the loaded settings.

    Parameters
    ----------
    settings : Settings
        Settings from configuration.
    args : argparse.Namespace
        Parsed command-line options.

    Returns
    -------
    Settings
        The merged settings.
    """
    changes: dict[str, object] = {}
    if select := _split_codes(args.select):
        changes["select"] = select
        changes["extend_select"] = ()
    if extend_select := _split_codes(args.extend_select):
        changes["extend_select"] = settings.extend_select + extend_select
    if ignore := _split_codes(args.ignore):
        changes["ignore"] = ignore
    if extend_ignore := _split_codes(args.extend_ignore):
        changes["extend_ignore"] = settings.extend_ignore + extend_ignore
    if args.exclude:
        changes["exclude"] = tuple(args.exclude)
    if args.extend_exclude:
        changes["extend_exclude"] = settings.extend_exclude + tuple(args.extend_exclude)
    if args.respect_gitignore is not None:
        changes["respect_gitignore"] = args.respect_gitignore
    if args.include_stubs is not None:
        changes["include_stubs"] = args.include_stubs
    return dataclasses.replace(settings, **changes) if changes else settings


def command_check(args: argparse.Namespace) -> int:
    """
    Run the ``check`` command.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed command-line options.

    Returns
    -------
    int
        The process exit code.
    """
    settings = load_settings(args.config)
    _print_notices(settings)
    plugins.load_all(settings.plugins, settings.root)
    settings = _apply_overrides(settings, args)

    known = registry.codes()
    selection.validate(
        settings.select
        + settings.ignore
        + settings.extend_select
        + settings.extend_ignore,
        known,
    )
    for block in settings.scopes:
        selection.validate(
            tuple(block.select or ())
            + tuple(block.ignore or ())
            + block.extend_select
            + block.extend_ignore,
            known,
        )
    for _pattern, codes in settings.per_file_ignores:
        selection.validate(codes, known)

    if args.show_settings:
        _print_settings(settings)
        return 0

    files = iter_python_files(args.paths, settings)

    if args.show_files:
        for path in files:
            print(output._display(path, settings.root))
        return 0

    result = lint_paths(files, settings, jobs=args.jobs)

    if args.output_format == "json":
        print(output.as_json(result.diagnostics, settings.root))
    elif args.output_format == "github":
        for line in output.github(result.diagnostics, settings.root):
            print(line)
    elif args.output_format == "pylint":
        for line in output.pylint(result.diagnostics, settings.root):
            print(line)
    elif args.output_format == "full":
        sources = _read_lines({d.path for d in result.diagnostics})
        for line in output.full(result.diagnostics, settings.root, sources):
            print(line)
    else:
        for line in output.concise(result.diagnostics, settings.root):
            print(line)

    if args.statistics:
        stats = output.statistics(result.diagnostics)
        if stats:
            print()
            for line in stats:
                print(line)

    for error in result.errors:
        print(error, file=sys.stderr)

    if not args.quiet and args.output_format not in ("json", "github"):
        print(output.summary_line(len(result.diagnostics), result.files_checked))

    if args.exit_zero:
        return 0
    if result.errors:
        return EXIT_ERROR
    return EXIT_VIOLATIONS if result.diagnostics else 0


def _read_lines(paths: set[Path]) -> dict[Path, list[str]]:
    """
    Read the lines of each file, for the full output format.

    Parameters
    ----------
    paths : set of pathlib.Path
        Files to read.

    Returns
    -------
    dict
        File path to its lines.
    """
    out: dict[Path, list[str]] = {}
    for path in paths:
        try:
            out[path.resolve()] = path.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()
        except OSError:
            continue
    return out


def _print_settings(settings: Settings) -> None:
    """
    Print the resolved settings.

    Parameters
    ----------
    settings : Settings
        The settings to print.
    """
    enabled = selection.apply_level(
        frozenset(),
        registry.codes(),
        select=list(settings.select),
        ignore=list(settings.ignore),
        extend_select=list(settings.extend_select),
        extend_ignore=list(settings.extend_ignore),
    )
    print(f"root                {settings.root}")
    print(f"config              {settings.config_path or '(defaults)'}")
    print(f"include             {list(settings.include) or ['.']}")
    print(f"exclude             {list(settings.exclude)}")
    print(f"extend-exclude      {list(settings.extend_exclude)}")
    print(f"respect-gitignore   {settings.respect_gitignore}")
    print(f"include-stubs       {settings.include_stubs}")
    print(f"select              {list(settings.select)}")
    print(f"ignore              {list(settings.ignore)}")
    print(f"property-decorators {list(settings.property_decorators)}")
    print(f"plugins             {list(settings.plugins)}")
    print(f"exclude-objects     {list(settings.exclude_object_patterns)}")
    print(f"exclude-file-re     {list(settings.exclude_file_patterns)}")
    print(f"overrides           {[c for c, _ in settings.overrides]}")
    print(
        f"numpydoc-compat     {settings.numpydoc_compat}"
        f"{' (legacy table in use)' if settings.legacy_config else ''}"
    )
    print(f"scope blocks        {len(settings.scopes)}")
    for block in settings.scopes:
        bits = []
        if block.skip:
            bits.append("skip")
        if block.select is not None:
            bits.append(f"select={list(block.select)}")
        if block.ignore is not None:
            bits.append(f"ignore={list(block.ignore)}")
        if block.extend_select:
            bits.append(f"extend-select={list(block.extend_select)}")
        if block.extend_ignore:
            bits.append(f"extend-ignore={list(block.extend_ignore)}")
        for key, value in block.options:
            bits.append(f"{key}={value!r}")
        print(f"  [{block.index}] {block.matcher}")
        print(f"       {', '.join(bits) or '(no overrides)'}")
    print(f"enabled by default  {len(enabled)} rules")


def command_rule(args: argparse.Namespace) -> int:
    """
    Run the ``rule`` command.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed command-line options.

    Returns
    -------
    int
        The process exit code.
    """
    plugins.load_entry_points()
    known = registry.codes()
    codes = [c.upper() for c in args.codes] if args.codes else list(known)
    expanded: list[str] = []
    for code in codes:
        matched = [k for k in known if selection.matches(code, k)]
        if not matched:
            print(f"unknown rule selector {code!r}", file=sys.stderr)
            return EXIT_ERROR
        expanded.extend(matched)
    seen: set[str] = set()
    ordered = [c for c in expanded if not (c in seen or seen.add(c))]

    if args.output_format == "json":
        import json

        payload = []
        for code in ordered:
            rule = registry.get(code)
            assert rule is not None
            payload.append(
                {
                    "code": rule.code,
                    "name": rule.name,
                    "summary": rule.summary,
                    "kinds": sorted(str(k) for k in rule.kinds),
                    "options": list(getattr(rule, "options", ())),
                    "per_file": bool(getattr(rule, "per_file", False)),
                }
            )
        print(json.dumps(payload, indent=2))
        return 0

    for code in ordered:
        rule = registry.get(code)
        assert rule is not None
        print(f"{rule.code}  {rule.name}")
        print(f"    {rule.summary}")
        kinds = sorted(str(k) for k in rule.kinds)
        if getattr(rule, "per_file", False):
            print("    applies to: the file as a whole")
        elif len(kinds) < 8:
            print(f"    applies to: {', '.join(kinds)}")
        if getattr(rule, "options", ()):
            print(f"    options: {', '.join(rule.options)}")
        print()
    return 0


def command_explain(args: argparse.Namespace) -> int:
    """
    Run the ``explain`` command.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed command-line options.

    Returns
    -------
    int
        The process exit code.
    """
    settings = load_settings(args.config)
    _print_notices(settings)
    plugins.load_all(settings.plugins, settings.root)

    location = args.location
    line_no: int | None = None
    if ":" in location:
        head, _, tail = location.rpartition(":")
        if tail.isdigit():
            location, line_no = head, int(tail)

    path = Path(location)
    if not path.is_absolute():
        path = settings.root / path
    if not path.is_file():
        print(f"no such file: {location}", file=sys.stderr)
        return EXIT_ERROR

    try:
        source = read_source(path, settings.root)
    except SourceError as exc:
        print(f"{location}: {exc.message}", file=sys.stderr)
        return EXIT_ERROR

    targets = collect_targets(
        source.tree,
        source.path,
        source.module_name,
        settings.property_decorators,
        settings.dataclass_decorators,
    )
    if line_no is not None:
        chosen = [t for t in targets if t.lineno == line_no]
        if not chosen:
            # A decorator line belongs to the definition it decorates, and a
            # line in a body belongs to the innermost object containing it.
            containing = [
                t
                for t in targets
                if t.span[0] <= line_no <= t.span[1] and t.kind != "module"
            ]
            if containing:
                chosen = [max(containing, key=lambda t: t.span[0])]
        if not chosen:
            print(f"no documentable object at line {line_no}", file=sys.stderr)
            return EXIT_ERROR
    else:
        chosen = targets

    for target in chosen:
        for out_line in explain_target(target, source, settings):
            print(out_line)
        print()
    return 0


#: Subcommands the parser knows about.
COMMANDS = ("check", "rule", "explain")

#: Options that belong to the top-level parser rather than to ``check``.
TOP_LEVEL_FLAGS = ("--version", "-h", "--help")


def _needs_default_command(argv: list[str]) -> bool:
    """
    Decide whether to insert the implicit ``check`` command.

    Bare paths and bare options should behave as ``npdlint check``, while an
    explicit subcommand or a top-level flag should not be rewritten.

    Parameters
    ----------
    argv : list of str
        The arguments as given.

    Returns
    -------
    bool
        True when ``check`` should be prepended.
    """
    if not argv:
        return True
    first = argv[0]
    if first in COMMANDS:
        return False
    return first not in TOP_LEVEL_FLAGS


def main(argv: Sequence[str] | None = None) -> int:
    """
    Entry point.

    Parameters
    ----------
    argv : sequence of str, optional
        Arguments, defaulting to ``sys.argv``.

    Returns
    -------
    int
        The process exit code.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()

    if _needs_default_command(argv):
        argv = ["check", *argv]

    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0

    try:
        return args.func(args)
    except (ConfigError, selection.SelectorError, plugins.PluginError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:  # pragma: no cover
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
