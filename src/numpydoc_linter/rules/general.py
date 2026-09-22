"""General docstring layout checks: the GL family."""

from __future__ import annotations

import re
from collections.abc import Iterable

from numpydoc_linter.diagnostics import Diagnostic
from numpydoc_linter.docstring import ALLOWED_SECTIONS
from numpydoc_linter.rules.base import BaseRule, Context, registry
from numpydoc_linter.rules.messages import render
from numpydoc_linter.rules.parameters import (
    fields_section,
    ignoring_private,
    parameter_mismatches,
)
from numpydoc_linter.targets import Kind, Target


@registry.register
class UnparseableDocstring(BaseRule):
    """DS01: the docstring is malformed enough that the parser gave up."""

    code = "DS01"
    name = "unparseable-docstring"
    summary = "A docstring should be parseable as numpydoc."

    def check(self, target: Target, ctx: Context) -> Iterable[Diagnostic]:
        """
        Report a docstring the parser could not read.

        Parameters
        ----------
        target : Target
            The object being checked.
        ctx : Context
            Shared state for the file.

        Yields
        ------
        Diagnostic
            One when parsing failed.
        """
        doc = target.docstring
        assert doc is not None
        if doc.error is not None:
            yield self.diagnostic(target, render(self.code, reason=doc.error))


@registry.register
class LeadingNewlines(BaseRule):
    """GL01: text should start right after, or on the line following, the quotes."""

    code = "GL01"
    name = "docstring-start-position"
    summary = "Docstring text should start on or just after the opening quotes."

    def check(self, target: Target, ctx: Context) -> Iterable[Diagnostic]:
        """
        Check the blank lines before the summary.

        Parameters
        ----------
        target : Target
            The object being checked.
        ctx : Context
            Shared state for the file.

        Yields
        ------
        Diagnostic
            One when the summary starts too far down.
        """
        doc = target.docstring
        assert doc is not None
        if doc.start_blank_lines not in (0, 1) and "\n" in doc.raw:
            yield self.diagnostic(target, render(self.code))


@registry.register
class TrailingNewlines(BaseRule):
    """GL02: closing quotes belong on the line after the last text."""

    code = "GL02"
    name = "docstring-end-position"
    summary = "Closing quotes should sit on the line after the last text."

    def check(self, target: Target, ctx: Context) -> Iterable[Diagnostic]:
        """
        Check the blank lines after the last text.

        Parameters
        ----------
        target : Target
            The object being checked.
        ctx : Context
            Shared state for the file.

        Yields
        ------
        Diagnostic
            One when the closing quotes are misplaced.
        """
        doc = target.docstring
        assert doc is not None
        if doc.end_blank_lines != 1 and "\n" in doc.raw:
            yield self.diagnostic(target, render(self.code))


@registry.register
class DoubleLineBreak(BaseRule):
    """GL03: only one blank line should separate paragraphs."""

    code = "GL03"
    name = "double-line-break"
    summary = "Use a single blank line between paragraphs and sections."

    def check(self, target: Target, ctx: Context) -> Iterable[Diagnostic]:
        """
        Check for consecutive blank lines.

        Parameters
        ----------
        target : Target
            The object being checked.
        ctx : Context
            Shared state for the file.

        Yields
        ------
        Diagnostic
            One when a double line break is present.
        """
        doc = target.docstring
        assert doc is not None
        if doc.double_blank_lines:
            yield self.diagnostic(target, render(self.code))


@registry.register
class TabsInDocstring(BaseRule):
    """GL05: indent with spaces, never tabs."""

    code = "GL05"
    name = "tabs-in-docstring"
    summary = "Docstrings should be indented with whitespace, not tabs."

    def check(self, target: Target, ctx: Context) -> Iterable[Diagnostic]:
        """
        Check for leading tabs.

        Parameters
        ----------
        target : Target
            The object being checked.
        ctx : Context
            Shared state for the file.

        Yields
        ------
        Diagnostic
            One per line starting with a tab.
        """
        doc = target.docstring
        assert doc is not None
        for line in doc.raw.splitlines():
            if re.match("^ *\t", line):
                yield self.diagnostic(
                    target, render(self.code, line_with_tabs=line.lstrip())
                )


@registry.register
class UnknownSection(BaseRule):
    """GL06: only numpydoc's section names are allowed."""

    code = "GL06"
    name = "unknown-section"
    summary = "Section headings must be ones numpydoc recognises."

    def check(self, target: Target, ctx: Context) -> Iterable[Diagnostic]:
        """
        Check every section heading against the allowed list.

        Parameters
        ----------
        target : Target
            The object being checked.
        ctx : Context
            Shared state for the file.

        Yields
        ------
        Diagnostic
            One per unrecognised section.
        """
        doc = target.docstring
        assert doc is not None
        for section in doc.section_titles:
            if section not in ALLOWED_SECTIONS:
                yield self.diagnostic(
                    target,
                    render(
                        self.code,
                        section=section,
                        allowed_sections=", ".join(ALLOWED_SECTIONS),
                    ),
                )


@registry.register
class SectionOrder(BaseRule):
    """GL07: sections must appear in numpydoc's canonical order."""

    code = "GL07"
    name = "section-order"
    summary = "Sections should follow numpydoc's canonical order."

    def check(self, target: Target, ctx: Context) -> Iterable[Diagnostic]:
        """
        Compare written section order with the canonical order.

        Parameters
        ----------
        target : Target
            The object being checked.
        ctx : Context
            Shared state for the file.

        Yields
        ------
        Diagnostic
            One when the order differs.
        """
        doc = target.docstring
        assert doc is not None
        titles = doc.section_titles
        correct = [s for s in ALLOWED_SECTIONS if s in titles]
        if correct != titles:
            yield self.diagnostic(
                target, render(self.code, correct_sections=", ".join(correct))
            )


@registry.register
class MissingDocstring(BaseRule):
    """GL08: the object has no docstring at all."""

    code = "GL08"
    name = "missing-docstring"
    summary = "Every documented object should have a docstring."
    requires_docstring = False

    def check(self, target: Target, ctx: Context) -> Iterable[Diagnostic]:
        """
        Report a missing docstring, allowing for a documented constructor.

        A class whose own docstring documents the constructor's parameters
        silences this rule for ``__init__``, matching numpydoc.

        Parameters
        ----------
        target : Target
            The object being checked.
        ctx : Context
            Shared state for the file.

        Yields
        ------
        Diagnostic
            One when the docstring is missing.
        """
        if target.has_docstring:
            return
        if (
            target.name == "__init__"
            and target.parent is not None
            and target.parent.kind is Kind.CLASS
        ):
            parent = target.parent
            if parent.docstring is not None and not parameter_mismatches(
                parent, ignoring_private(ctx), fields_section(ctx)
            ):
                return
        yield self.diagnostic(target, render(self.code))


@registry.register
class DeprecationOrder(BaseRule):
    """GL09: the deprecation directive precedes the extended summary."""

    code = "GL09"
    name = "deprecation-order"
    summary = "A deprecation warning should come before the extended summary."

    def check(self, target: Target, ctx: Context) -> Iterable[Diagnostic]:
        """
        Check where the deprecation directive sits.

        Parameters
        ----------
        target : Target
            The object being checked.
        ctx : Context
            Shared state for the file.

        Yields
        ------
        Diagnostic
            One when the directive is misplaced.
        """
        doc = target.docstring
        assert doc is not None
        if doc.deprecated and not doc.extended_summary.startswith(".. deprecated:: "):
            yield self.diagnostic(target, render(self.code))


@registry.register
class DirectiveColons(BaseRule):
    """GL10: reST directives need two colons."""

    code = "GL10"
    name = "directive-colons"
    summary = "reST directives must be followed by two colons."

    def check(self, target: Target, ctx: Context) -> Iterable[Diagnostic]:
        """
        Find directives written with one colon.

        Parameters
        ----------
        target : Target
            The object being checked.
        ctx : Context
            Shared state for the file.

        Yields
        ------
        Diagnostic
            One when such a directive is present.
        """
        doc = target.docstring
        assert doc is not None
        directives = doc.directives_without_two_colons
        if directives:
            yield self.diagnostic(target, render(self.code, directives=directives))
