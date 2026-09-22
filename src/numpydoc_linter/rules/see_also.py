"""See Also and Examples checks: the SA and EX families."""

from __future__ import annotations

from collections.abc import Iterable

from numpydoc_linter.diagnostics import Diagnostic
from numpydoc_linter.rules.base import BaseRule, Context, registry
from numpydoc_linter.rules.messages import render
from numpydoc_linter.targets import Kind, Target

_NON_MODULE = frozenset(Kind) - {Kind.MODULE}


@registry.register
class NoSeeAlso(BaseRule):
    """SA01: the docstring has no See Also section."""

    code = "SA01"
    name = "no-see-also"
    summary = "A docstring should point at related objects."
    kinds = _NON_MODULE

    def check(self, target: Target, ctx: Context) -> Iterable[Diagnostic]:
        """
        Check that a See Also section is present.

        Parameters
        ----------
        target : Target
            The object being checked.
        ctx : Context
            Shared state for the file.

        Yields
        ------
        Diagnostic
            One when the section is missing.
        """
        doc = target.docstring
        assert doc is not None
        if not doc.see_also:
            yield self.diagnostic(target, render(self.code))


class _SeeAlsoEntryRule(BaseRule):
    """Shared base for checks that visit each See Also entry."""

    kinds = _NON_MODULE

    def _check_one(  # pragma: no cover
        self, name: str, desc: str, target: Target
    ) -> Iterable[Diagnostic]:
        raise NotImplementedError

    def check(self, target: Target, ctx: Context) -> Iterable[Diagnostic]:
        """
        Visit each See Also reference.

        Parameters
        ----------
        target : Target
            The object being checked.
        ctx : Context
            Shared state for the file.

        Yields
        ------
        Diagnostic
            One per offending reference.
        """
        doc = target.docstring
        assert doc is not None
        for name, desc in doc.see_also.items():
            yield from self._check_one(name, desc, target)


@registry.register
class SeeAlsoPeriod(_SeeAlsoEntryRule):
    """SA02: a See Also description does not end with a period."""

    code = "SA02"
    name = "see-also-period"
    summary = "See Also descriptions should end with a period."

    def _check_one(self, name, desc, target):
        if desc and not desc.endswith("."):
            yield self.diagnostic(target, render(self.code, reference_name=name))


@registry.register
class SeeAlsoCapitalised(_SeeAlsoEntryRule):
    """SA03: a See Also description is not capitalised."""

    code = "SA03"
    name = "see-also-capitalised"
    summary = "See Also descriptions should start with a capital letter."

    def _check_one(self, name, desc, target):
        if desc and desc[0].isalpha() and not desc[0].isupper():
            yield self.diagnostic(target, render(self.code, reference_name=name))


@registry.register
class SeeAlsoNoDescription(_SeeAlsoEntryRule):
    """SA04: a See Also reference has no description."""

    code = "SA04"
    name = "see-also-no-description"
    summary = "Every See Also reference should have a description."

    def _check_one(self, name, desc, target):
        if not desc:
            yield self.diagnostic(target, render(self.code, reference_name=name))


@registry.register
class NoExamples(BaseRule):
    """EX01: the docstring has no Examples section."""

    code = "EX01"
    name = "no-examples"
    summary = "A docstring should carry a worked example."
    kinds = _NON_MODULE

    def check(self, target: Target, ctx: Context) -> Iterable[Diagnostic]:
        """
        Check that an Examples section is present.

        Parameters
        ----------
        target : Target
            The object being checked.
        ctx : Context
            Shared state for the file.

        Yields
        ------
        Diagnostic
            One when the section is missing.
        """
        doc = target.docstring
        assert doc is not None
        if not doc.examples:
            yield self.diagnostic(target, render(self.code))
