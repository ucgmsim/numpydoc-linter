"""Read a file once and derive everything the rules need from it."""

from __future__ import annotations

import ast
import io
import re
import tokenize
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

#: Matches suppression comments, both the ruff-style and numpydoc spellings.
NOQA_RE = re.compile(
    r"#\s*(?P<keyword>noqa|numpydoc\s+ignore)"
    r"\s*(?:[:=]\s*(?P<codes>[A-Z0-9,\s]+))?",
    re.IGNORECASE,
)

#: Sentinel meaning "suppress every rule on this line".
ALL_CODES = "*"


@dataclass(frozen=True, slots=True)
class Suppression:
    """
    One inline suppression comment.

    Parameters
    ----------
    line : int
        One-based line the comment sits on.
    col : int
        One-based column the ``#`` sits at.
    codes : frozenset of str
        Codes named in the comment, or ``{ALL_CODES}`` when it names none.
    numpydoc_style : bool
        Whether it was written as ``# numpydoc ignore`` rather than
        ``# noqa``. Only the former is unambiguously addressed to this tool;
        the latter shares its spelling with ruff and flake8.
    """

    line: int
    col: int
    codes: frozenset[str]
    numpydoc_style: bool

    def covers(self, code: str) -> bool:
        """
        Report whether this comment suppresses a rule code.

        Parameters
        ----------
        code : str
            The rule code.

        Returns
        -------
        bool
            True when the code is named, or the comment names none at all.
        """
        return ALL_CODES in self.codes or code in self.codes

    def key_for(self, code: str) -> str:
        """
        Get the ledger key a code is recorded under for this comment.

        A comment naming no codes is tracked as a whole, because any rule it
        covers justifies it.

        Parameters
        ----------
        code : str
            The rule code the comment was consulted for.

        Returns
        -------
        str
            The code itself, or :data:`ALL_CODES`.
        """
        return code if code in self.codes else ALL_CODES


@dataclass(slots=True)
class SourceFile:
    """
    A file that has been read, decoded, and parsed.

    Parameters
    ----------
    path : pathlib.Path
        Absolute path to the file.
    relative_path : str
        Path relative to the project root, in posix form.
    text : str
        Decoded contents.
    tree : ast.Module
        The parsed module.
    module_name : str
        Name used as the root of qualified names.
    noqa : dict
        Line number to the suppression comment written on that line.
    lines : tuple of str
        The decoded contents split into lines, for quoting in output.
    """

    path: Path
    relative_path: str
    text: str
    tree: ast.Module
    module_name: str
    noqa: dict[int, Suppression] = field(default_factory=dict)
    lines: tuple[str, ...] = ()

    def suppression_lines(self, target) -> tuple[int, ...]:
        """
        List every line an inline suppression for a target may be written on.

        A signature often spans several lines, and the natural place for the
        comment is the line carrying the return annotation or the closing
        parenthesis rather than the ``def``. The signature is taken to run from
        the first decorator to the start of the body, with the body's own first
        line counted only when it shares that line with the signature, as in
        ``def f() -> int: ...``.

        Parameters
        ----------
        target : Target
            The object being checked.

        Returns
        -------
        tuple of int
            Lines to look for a suppression comment on.
        """
        lines = set(target.noqa_lines)
        start = target.span[0]
        end = target.lineno
        body = target.body_start
        if body is not None:
            body_line, body_col = body
            prefix = self.line(body_line)[:body_col]
            end = max(end, body_line if prefix.strip() else body_line - 1)
        lines.update(range(start, end + 1))
        return tuple(sorted(lines))

    def suppressions_on(
        self, lines: Sequence[int], code: str
    ) -> tuple[Suppression, ...]:
        """
        Find the comments among some lines that suppress a code.

        Parameters
        ----------
        lines : sequence of int
            Lines to look at, as returned by :meth:`suppression_lines`.
        code : str
            The rule code.

        Returns
        -------
        tuple of Suppression
            The comments that cover the code.
        """
        if not self.noqa:
            return ()
        out = []
        for line in lines:
            suppression = self.noqa.get(line)
            if suppression is not None and suppression.covers(code):
                out.append(suppression)
        return tuple(out)

    def is_suppressed(self, code: str, target) -> bool:
        """
        Report whether an inline comment suppresses a code for a target.

        Parameters
        ----------
        code : str
            The rule code.
        target : Target
            The object being checked.

        Returns
        -------
        bool
            True when suppressed.
        """
        if not self.noqa:
            return False
        return bool(self.suppressions_on(self.suppression_lines(target), code))

    def line(self, number: int) -> str:
        """
        Get one source line.

        Parameters
        ----------
        number : int
            One-based line number.

        Returns
        -------
        str
            The line, without its terminator, empty when out of range.
        """
        if 1 <= number <= len(self.lines):
            return self.lines[number - 1]
        return ""


@dataclass(slots=True)
class SuppressionUsage:
    """
    A record of what each inline suppression actually did.

    The runner fills this in while linting a file, so that a rule can
    afterwards point at the comments that turned out to be doing nothing. A
    code is only judged once it has been *evaluated*: if configuration had
    already disabled it, or the object was excluded, nothing is recorded and
    the comment escapes judgement.

    Parameters
    ----------
    used : set of tuple
        Line and code pairs where the comment suppressed a real violation.
    evaluated : set of tuple
        Line and code pairs where the rule was actually consulted.
    attached : set of int
        Lines that belong to the signature of at least one documentable
        object, and so could suppress something at all.
    """

    used: set[tuple[int, str]] = field(default_factory=set)
    evaluated: set[tuple[int, str]] = field(default_factory=set)
    attached: set[int] = field(default_factory=set)

    def attach(self, lines: Iterable[int]) -> None:
        """
        Note the lines an object's suppressions may be written on.

        Parameters
        ----------
        lines : iterable of int
            Lines belonging to one target.
        """
        self.attached.update(lines)

    def record(
        self, suppressions: Iterable[Suppression], code: str, *, fired: bool
    ) -> None:
        """
        Note that a code was consulted for some comments.

        Parameters
        ----------
        suppressions : iterable of Suppression
            The comments that covered the code.
        code : str
            The rule code.
        fired : bool
            Whether the rule would have reported something.
        """
        for suppression in suppressions:
            key = (suppression.line, suppression.key_for(code))
            self.evaluated.add(key)
            if fired:
                self.used.add(key)

    def is_wasted(self, suppression: Suppression, code: str) -> bool:
        """
        Report whether one code of one comment suppressed nothing.

        Parameters
        ----------
        suppression : Suppression
            The comment.
        code : str
            One of the codes it names, or :data:`ALL_CODES`.

        Returns
        -------
        bool
            True when the code was evaluated and never suppressed anything.
        """
        key = (suppression.line, code)
        return key in self.evaluated and key not in self.used


class SourceError(Exception):
    """Raised when a file cannot be read or parsed.

    Parameters
    ----------
    path : pathlib.Path
        The file that failed.
    message : str
        What went wrong.
    line : int
        Line the failure was reported at.
    col : int
        Column the failure was reported at.
    """

    def __init__(self, path: Path, message: str, line: int = 1, col: int = 1) -> None:
        super().__init__(message)
        self.path = path
        self.message = message
        self.line = line
        self.col = col


def extract_noqa(text: str) -> dict[int, Suppression]:
    """
    Collect inline suppressions from a file's comments.

    Both ``# noqa: PR04`` and numpydoc's ``# numpydoc ignore=PR04`` are
    recognised. A bare ``# noqa`` suppresses everything on its line. Python
    allows only one comment per line, so a line carries at most one.

    Parameters
    ----------
    text : str
        The decoded file contents.

    Returns
    -------
    dict
        Line number to the suppression written on that line.
    """
    out: dict[int, Suppression] = {}
    lowered = text.lower()
    if "noqa" not in lowered and "numpydoc ignore" not in lowered:
        # Tokenising a whole file to find comments is expensive, and almost no
        # file has a suppression in it.
        return out

    for lineno, col, comment in _comments(text):
        match = NOQA_RE.search(comment)
        if match is None:
            continue
        raw = match.group("codes")
        if raw is None:
            codes = frozenset({ALL_CODES})
        else:
            codes = frozenset(
                part.strip().upper()
                for part in re.split(r"[,\s]+", raw)
                if part.strip()
            )
        out[lineno] = Suppression(
            line=lineno,
            col=col + match.start() + 1,
            codes=codes or frozenset({ALL_CODES}),
            numpydoc_style="noqa" not in match.group("keyword").lower(),
        )
    return out


def _comments(text: str) -> Iterable[tuple[int, int, str]]:
    """
    Yield every comment in a file, with where it starts.

    Parameters
    ----------
    text : str
        The decoded file contents.

    Yields
    ------
    tuple
        Line number, zero-based start column, and the comment text.
    """
    try:
        return [
            (tok.start[0], tok.start[1], tok.string)
            for tok in tokenize.generate_tokens(io.StringIO(text).readline)
            if tok.type == tokenize.COMMENT
        ]
    except (tokenize.TokenError, IndentationError, SyntaxError):
        # The file does not tokenise, so fall back to scanning lines. A "#"
        # inside a string may be mistaken for a comment, which is acceptable
        # for a file that is already being reported as unparseable.
        return [
            (i, 0, line) for i, line in enumerate(text.splitlines(), 1) if "#" in line
        ]


def module_name_for(path: Path, root: Path) -> str:
    """
    Derive a module name from a file path.

    Package directories contribute their names, so a nested module gets a
    dotted name that matches how numpydoc would address it.

    Parameters
    ----------
    path : pathlib.Path
        The file.
    root : pathlib.Path
        Project root.

    Returns
    -------
    str
        The dotted module name.
    """
    parts = [path.stem]
    directory = path.parent
    while (directory / "__init__.py").is_file():
        parts.append(directory.name)
        if directory == root or directory.parent == directory:
            break
        directory = directory.parent
    return ".".join(reversed(parts))


def read_source(path: Path, root: Path) -> SourceFile:
    """
    Read, decode, and parse one file.

    Parameters
    ----------
    path : pathlib.Path
        The file to read.
    root : pathlib.Path
        Project root, used for the relative path and module name.

    Returns
    -------
    SourceFile
        The parsed file.

    Raises
    ------
    SourceError
        When the file cannot be read or does not parse.
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise SourceError(path, f"could not read file: {exc}") from exc

    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
    except SyntaxError:
        encoding = "utf-8"
    try:
        text = raw.decode(encoding)
    except (UnicodeDecodeError, LookupError) as exc:
        raise SourceError(path, f"could not decode file: {exc}") from exc

    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        raise SourceError(
            path,
            f"syntax error: {exc.msg}",
            line=exc.lineno or 1,
            col=exc.offset or 1,
        ) from exc

    try:
        relative = path.resolve().relative_to(root).as_posix()
    except ValueError:
        relative = path.as_posix()

    return SourceFile(
        path=path,
        relative_path=relative,
        text=text,
        tree=tree,
        module_name=module_name_for(path, root),
        noqa=extract_noqa(text),
        lines=tuple(text.splitlines()),
    )
