"""Short and extended summary checks: the SS and ES families."""

from __future__ import annotations

from collections.abc import Iterable

from numpydoc_linter.diagnostics import Diagnostic
from numpydoc_linter.rules.base import BaseRule, Context, registry
from numpydoc_linter.rules.messages import render
from numpydoc_linter.rules.properties import effective_summary
from numpydoc_linter.targets import CALLABLE_KINDS, Kind, Target

_NON_MODULE = frozenset(Kind) - {Kind.MODULE}


@registry.register
class NoSummary(BaseRule):
    """SS01: the docstring has no short summary."""

    code = "SS01"
    name = "no-summary"
    summary = "A docstring should open with a one-line summary."

    def check(self, target: Target, ctx: Context) -> Iterable[Diagnostic]:
        """
        Check that a summary is present.

        Parameters
        ----------
        target : Target
            The object being checked.
        ctx : Context
            Shared state for the file.

        Yields
        ------
        Diagnostic
            One when the summary is missing.
        """
        doc = target.docstring
        assert doc is not None
        if not doc.summary:
            yield self.diagnostic(target, render(self.code))


@registry.register
class SummaryCapitalised(BaseRule):
    """SS02: the summary does not start with a capital letter."""

    code = "SS02"
    name = "summary-capitalised"
    summary = "The summary should start with a capital letter."

    def check(self, target: Target, ctx: Context) -> Iterable[Diagnostic]:
        """
        Check the first character of the summary.

        Parameters
        ----------
        target : Target
            The object being checked.
        ctx : Context
            Shared state for the file.

        Yields
        ------
        Diagnostic
            One when the summary is lower case.
        """
        s = effective_summary(target, ctx)
        if s and s[0].isalpha() and not s[0].isupper():
            yield self.diagnostic(target, render(self.code))


@registry.register
class SummaryPeriod(BaseRule):
    """SS03: the summary does not end with a period."""

    code = "SS03"
    name = "summary-period"
    summary = "The summary should end with a period."

    def check(self, target: Target, ctx: Context) -> Iterable[Diagnostic]:
        """
        Check the last character of the summary.

        Parameters
        ----------
        target : Target
            The object being checked.
        ctx : Context
            Shared state for the file.

        Yields
        ------
        Diagnostic
            One when the period is missing.
        """
        s = effective_summary(target, ctx)
        if s and s[-1] != ".":
            yield self.diagnostic(target, render(self.code))


@registry.register
class SummaryLeadingWhitespace(BaseRule):
    """SS04: the summary is indented."""

    code = "SS04"
    name = "summary-leading-whitespace"
    summary = "The summary should not be indented."

    def check(self, target: Target, ctx: Context) -> Iterable[Diagnostic]:
        """
        Check for leading whitespace on the summary.

        Parameters
        ----------
        target : Target
            The object being checked.
        ctx : Context
            Shared state for the file.

        Yields
        ------
        Diagnostic
            One when the summary is indented.
        """
        doc = target.docstring
        assert doc is not None
        s = doc.summary
        if s and s != s.lstrip():
            yield self.diagnostic(target, render(self.code))


@registry.register
class SummaryInfinitiveVerb(BaseRule):
    """SS05: the summary uses third person instead of the infinitive."""

    code = "SS05"
    name = "summary-infinitive-verb"
    summary = 'Start the summary with an infinitive verb, "Generate" not "Generates".'
    kinds = CALLABLE_KINDS

    def check(self, target: Target, ctx: Context) -> Iterable[Diagnostic]:
        """
        Apply numpydoc's third-person heuristic to the first word.

        This does not fire when the summary is indented, matching numpydoc,
        where the two checks share an if-else chain.

        Parameters
        ----------
        target : Target
            The object being checked.
        ctx : Context
            Shared state for the file.

        Yields
        ------
        Diagnostic
            One when the first word looks like third person.
        """
        doc = target.docstring
        assert doc is not None
        if doc.summary != doc.summary.lstrip():
            return
        s = effective_summary(target, ctx)
        if not s:
            return
        first = s.split(" ")[0]
        if len(first) > 1 and first[-1] == "s" and first[-2] != "s":
            yield self.diagnostic(target, render(self.code))


@registry.register
class SummarySingleLine(BaseRule):
    """SS06: the summary spills onto more than one line."""

    code = "SS06"
    name = "summary-single-line"
    summary = "The summary should fit on one line."

    def check(self, target: Target, ctx: Context) -> Iterable[Diagnostic]:
        """
        Count the lines of the summary.

        Parameters
        ----------
        target : Target
            The object being checked.
        ctx : Context
            Shared state for the file.

        Yields
        ------
        Diagnostic
            One when the summary is multi-line.
        """
        doc = target.docstring
        assert doc is not None
        if doc.summary and doc.num_summary_lines > 1:
            yield self.diagnostic(target, render(self.code))


@registry.register
class NoExtendedSummary(BaseRule):
    """ES01: the docstring has no extended summary."""

    code = "ES01"
    name = "no-extended-summary"
    summary = "A docstring should have an extended summary."
    kinds = _NON_MODULE

    def check(self, target: Target, ctx: Context) -> Iterable[Diagnostic]:
        """
        Check that an extended summary is present.

        Parameters
        ----------
        target : Target
            The object being checked.
        ctx : Context
            Shared state for the file.

        Yields
        ------
        Diagnostic
            One when the extended summary is missing.
        """
        doc = target.docstring
        assert doc is not None
        if not doc.extended_summary:
            yield self.diagnostic(target, render(self.code))
