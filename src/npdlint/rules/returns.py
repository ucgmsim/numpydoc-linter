"""Return and yield documentation checks: the RT and YD families."""

from __future__ import annotations

from collections.abc import Iterable

from npdlint.diagnostics import Diagnostic
from npdlint.docstring import check_description
from npdlint.rules.base import BaseRule, Context, registry
from npdlint.rules.messages import render
from npdlint.targets import CALLABLE_KINDS, Target


@registry.register
class NoReturnsSection(BaseRule):
    """RT01: the function returns a value but documents no Returns section."""

    code = "RT01"
    name = "no-returns-section"
    summary = "A function that returns a value should document it."
    kinds = CALLABLE_KINDS

    def check(self, target: Target, ctx: Context) -> Iterable[Diagnostic]:
        """
        Check for a missing Returns section.

        Parameters
        ----------
        target : Target
            The object being checked.
        ctx : Context
            Shared state for the file.

        Yields
        ------
        Diagnostic
            One when a return value is undocumented.
        """
        doc = target.docstring
        assert doc is not None
        if not doc.returns and target.returns_value:
            yield self.diagnostic(target, render(self.code))


@registry.register
class ReturnsFirstLine(BaseRule):
    """RT02: the first line of Returns should hold only the type."""

    code = "RT02"
    name = "returns-first-line"
    summary = "A single return value should be documented as a bare type."
    kinds = CALLABLE_KINDS

    def check(self, target: Target, ctx: Context) -> Iterable[Diagnostic]:
        """
        Check the shape of a single Returns entry.

        Parameters
        ----------
        target : Target
            The object being checked.
        ctx : Context
            Shared state for the file.

        Yields
        ------
        Diagnostic
            One when a lone entry is named.
        """
        doc = target.docstring
        assert doc is not None
        if len(doc.returns) == 1 and doc.returns[0].name:
            yield self.diagnostic(target, render(self.code))


class _ReturnDescRule(BaseRule):
    """Shared base for the return description checks."""

    kinds = CALLABLE_KINDS

    def check(self, target: Target, ctx: Context) -> Iterable[Diagnostic]:
        """
        Apply the shared description checks to each return value.

        Parameters
        ----------
        target : Target
            The object being checked.
        ctx : Context
            Shared state for the file.

        Yields
        ------
        Diagnostic
            One per offending return value.
        """
        doc = target.docstring
        assert doc is not None
        for _name, _type, desc in doc.returns:
            for code, kwargs in check_description(desc, "RT03", "RT04", "RT05"):
                if code == self.code:
                    yield self.diagnostic(target, render(code, **kwargs))


@registry.register
class ReturnHasNoDescription(_ReturnDescRule):
    """RT03: a return value has no description."""

    code = "RT03"
    name = "return-has-no-description"
    summary = "Every documented return value should have a description."


@registry.register
class ReturnDescriptionCapitalised(_ReturnDescRule):
    """RT04: a return description is not capitalised."""

    code = "RT04"
    name = "return-description-capitalised"
    summary = "Return descriptions should start with a capital letter."


@registry.register
class ReturnDescriptionPeriod(_ReturnDescRule):
    """RT05: a return description does not end with a period."""

    code = "RT05"
    name = "return-description-period"
    summary = "Return descriptions should end with a period."


@registry.register
class NoYieldsSection(BaseRule):
    """YD01: a generator documents no Yields section."""

    code = "YD01"
    name = "no-yields-section"
    summary = "A generator should document what it yields."
    kinds = CALLABLE_KINDS

    def check(self, target: Target, ctx: Context) -> Iterable[Diagnostic]:
        """
        Check for a missing Yields section.

        Parameters
        ----------
        target : Target
            The object being checked.
        ctx : Context
            Shared state for the file.

        Yields
        ------
        Diagnostic
            One when a generator's yields are undocumented.
        """
        doc = target.docstring
        assert doc is not None
        if not doc.yields and target.is_generator:
            yield self.diagnostic(target, render(self.code))
