"""Parsed view of a numpydoc docstring.

This wraps the vendored :class:`~numpydoc_linter._vendor.docscrape.NumpyDocString`
and re-exposes the derived quantities that numpydoc's own ``Validator`` computes,
so that ported rules can be written against the same vocabulary.
"""

from __future__ import annotations

import collections
import re
import warnings
from functools import cached_property

from numpydoc_linter._vendor.docscrape import NumpyDocString

#: Sections numpydoc recognises, in their canonical order.
ALLOWED_SECTIONS = (
    "Parameters",
    "Attributes",
    "Methods",
    "Returns",
    "Yields",
    "Other Parameters",
    "Raises",
    "Warns",
    "Warnings",
    "See Also",
    "Notes",
    "References",
    "Examples",
)

#: reST directives that must be written with two colons.
DIRECTIVES = ("versionadded", "versionchanged", "deprecated")

_DIRECTIVE_PATTERN = re.compile(
    r"^\s*\.\. ({})(?!::)".format("|".join(DIRECTIVES)),
    re.IGNORECASE | re.MULTILINE,
)

#: Description prefixes exempt from the "must end in a period" checks.
IGNORE_STARTS = (" ", "* ", "- ")


def _first_content_line(rows: list[str]) -> int | None:
    """
    Find the index of the first row with text on it.

    Parameters
    ----------
    rows : list of str
        The rows to scan.

    Returns
    -------
    int or None
        The index of the first non-blank row, the last index when every row is
        blank, or None when there are no rows.
    """
    for index, row in enumerate(rows):
        if row.strip():
            return index
    return len(rows) - 1 if rows else None


class ParsedDocstring:
    """
    A numpydoc docstring together with the properties rules ask about.

    Parameters
    ----------
    raw : str
        The docstring exactly as written in the source, without the quotes.
    """

    __slots__ = ("raw", "doc", "error", "__dict__")

    def __init__(self, raw: str) -> None:
        self.raw = raw
        self.error: str | None = None
        # docscrape warns about unrecognised sections; GL06 reports them
        # properly, so the warning is only noise on stderr.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                self.doc = NumpyDocString(raw)
            except Exception as exc:
                # A docstring malformed enough to break the parser is a
                # finding, not a reason to abandon the file. DS01 reports it
                # and every other rule sees an empty docstring.
                self.error = str(exc).strip() or exc.__class__.__name__
                self.doc = NumpyDocString("")

    # -- whitespace and layout ------------------------------------------------

    @cached_property
    def start_blank_lines(self) -> int | None:
        """
        Count blank lines before the first text in the docstring.

        Returns
        -------
        int or None
            The index of the first non-blank line, or None when empty.
        """
        return _first_content_line(self.raw.split("\n") if self.raw else [])

    @cached_property
    def end_blank_lines(self) -> int | None:
        """
        Count blank lines after the last text in the docstring.

        Returns
        -------
        int or None
            The index from the end of the last non-blank line, or None.
        """
        rows = list(reversed(self.raw.split("\n"))) if self.raw else []
        return _first_content_line(rows)

    @cached_property
    def double_blank_lines(self) -> bool:
        """
        Report whether two consecutive blank lines appear.

        Returns
        -------
        bool
            True when a double line break is present.
        """
        prev = True
        for row in self.raw.split("\n"):
            if not prev and not row.strip():
                return True
            prev = bool(row.strip())
        return False

    @cached_property
    def section_titles(self) -> list[str]:
        """
        List the underlined section headings, in the order written.

        Returns
        -------
        list of str
            Section titles found in the docstring.
        """
        sections: list[str] = []
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.doc._doc.reset()
            while not self.doc._doc.eof():
                content = self.doc._read_to_next_section()
                if (
                    len(content) > 1
                    and len(content[0]) == len(content[1])
                    and set(content[1]) == {"-"}
                ):
                    sections.append(content[0])
        return sections

    @cached_property
    def directives_without_two_colons(self) -> list[str]:
        """
        Find reST directives written with a single colon.

        Returns
        -------
        list of str
            Names of the offending directives.
        """
        return _DIRECTIVE_PATTERN.findall(self.raw)

    # -- summary --------------------------------------------------------------

    @cached_property
    def summary(self) -> str:
        """
        Join the short summary into one string.

        Returns
        -------
        str
            The short summary.
        """
        return " ".join(self.doc["Summary"])

    @cached_property
    def num_summary_lines(self) -> int:
        """
        Count the lines of the short summary.

        Returns
        -------
        int
            Number of summary lines.
        """
        return len(self.doc["Summary"])

    @cached_property
    def extended_summary(self) -> str:
        """
        Join the extended summary into one string.

        A multi-line short summary is treated as an extended summary, matching
        numpydoc.

        Returns
        -------
        str
            The extended summary.
        """
        if not self.doc["Extended Summary"] and len(self.doc["Summary"]) > 1:
            return " ".join(self.doc["Summary"])
        return " ".join(self.doc["Extended Summary"])

    @cached_property
    def deprecated(self) -> bool:
        """
        Report whether the docstring carries a deprecation directive.

        Returns
        -------
        bool
            True when a deprecation directive is present.
        """
        return ".. deprecated:: " in (self.summary + self.extended_summary)

    # -- parameters -----------------------------------------------------------

    def _params(self, sections: tuple[str, ...]) -> dict[str, tuple[str, list[str]]]:
        parameters: dict[str, tuple[str, list[str]]] = collections.OrderedDict()
        for section in sections:
            for names, type_, desc in self.doc[section]:
                for name in names.split(", "):
                    parameters[name] = (type_, desc)
        return parameters

    @cached_property
    def doc_parameters(self) -> dict[str, tuple[str, list[str]]]:
        """
        Map documented names from the Parameters section to type and description.

        Returns
        -------
        dict
            Mapping of parameter name to a (type, description) pair.
        """
        return self._params(("Parameters",))

    @cached_property
    def doc_attributes(self) -> dict[str, tuple[str, list[str]]]:
        """
        Map documented names from the Attributes section to type and description.

        Returns
        -------
        dict
            Mapping of attribute name to a (type, description) pair.
        """
        return self._params(("Attributes",))

    @cached_property
    def doc_all_parameters(self) -> dict[str, tuple[str, list[str]]]:
        """
        Map documented names from Parameters and Other Parameters.

        Returns
        -------
        dict
            Mapping of parameter name to a (type, description) pair.
        """
        return self._params(("Parameters", "Other Parameters"))

    def parameter_type(self, param: str) -> str:
        """
        Get the documented type of one parameter.

        Parameters
        ----------
        param : str
            The documented parameter name.

        Returns
        -------
        str
            The documented type, empty when none was written.
        """
        return self.doc_all_parameters[param][0]

    # -- other sections -------------------------------------------------------

    @cached_property
    def returns(self) -> list:
        """
        Get the entries of the Returns section.

        Returns
        -------
        list
            Parsed Returns entries.
        """
        return self.doc["Returns"]

    @cached_property
    def yields(self) -> list:
        """
        Get the entries of the Yields section.

        Returns
        -------
        list
            Parsed Yields entries.
        """
        return self.doc["Yields"]

    @cached_property
    def raises(self) -> list:
        """
        Get the entries of the Raises section.

        Returns
        -------
        list
            Parsed Raises entries.
        """
        return self.doc["Raises"]

    @cached_property
    def examples(self) -> list:
        """
        Get the lines of the Examples section.

        Returns
        -------
        list
            Example lines.
        """
        return self.doc["Examples"]

    @cached_property
    def see_also(self) -> dict[str, str]:
        """
        Map each See Also reference to its description.

        Returns
        -------
        dict
            Mapping of reference name to description text.
        """
        result: dict[str, str] = collections.OrderedDict()
        for funcs, desc in self.doc["See Also"]:
            for func, _ in funcs:
                result[func] = "".join(desc)
        return result


def check_description(
    desc: list[str],
    code_no_desc: str,
    code_no_upper: str,
    code_no_period: str,
    **kwargs: object,
) -> list[tuple[str, dict[str, object]]]:
    """
    Apply the shared description checks used for parameters and returns.

    Sphinx directives are stripped before checking, matching numpydoc.

    Parameters
    ----------
    desc : list of str
        Description lines.
    code_no_desc : str
        Code to emit when the description is empty.
    code_no_upper : str
        Code to emit when the description is not capitalised.
    code_no_period : str
        Code to emit when the description does not end in a period.
    **kwargs : object
        Values interpolated into the message templates.

    Returns
    -------
    list
        Pairs of code and message-formatting arguments.
    """
    text = "\n".join(desc)
    for directive in DIRECTIVES:
        full_directive = f".. {directive}"
        if full_directive in text:
            text = text[: text.index(full_directive)].rstrip("\n")
    lines = text.split("\n")

    errs: list[tuple[str, dict[str, object]]] = []
    if not "".join(lines):
        errs.append((code_no_desc, dict(kwargs)))
    else:
        if lines[0][0].isalpha() and not lines[0][0].isupper():
            errs.append((code_no_upper, dict(kwargs)))
        if not lines[-1].endswith(".") and not lines[-1].startswith(IGNORE_STARTS):
            errs.append((code_no_period, dict(kwargs)))
    return errs
