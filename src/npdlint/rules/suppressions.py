"""Checks on the suppression comments themselves: the NQ family.

A suppression that suppresses nothing is worse than no suppression at all: it
survives the fix that made it redundant, and the next reader takes it as
evidence that the rule still fires. These rules run once per file, after every
other rule has had its say, and report the comments that did no work.

Only comments this tool can fairly claim are judged. ``# numpydoc ignore`` is
addressed to it alone, so everything in one counts. ``# noqa`` shares its
spelling with ruff and flake8, so only codes that are registered rules here
count, and a bare ``# noqa`` is left alone entirely.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from npdlint.diagnostics import Diagnostic
from npdlint.rules.base import BaseFileRule, Context, registry
from npdlint.rules.messages import render
from npdlint.source import ALL_CODES, Suppression


def judgeable_codes(suppression: Suppression) -> tuple[str, ...]:
    """
    List the codes of one comment whose usefulness can be judged.

    Codes belonging to another tool are left out, as are unknown ones, which
    are ``NQ02``'s business, and file-level rules, which no comment can
    suppress in the first place.

    Parameters
    ----------
    suppression : Suppression
        The comment.

    Returns
    -------
    tuple of str
        Codes to judge, possibly including :data:`~npdlint.source.ALL_CODES`.
    """
    out: list[str] = []
    for code in sorted(suppression.codes):
        if code == ALL_CODES:
            if suppression.numpydoc_style:
                out.append(code)
            continue
        rule = registry.get(code)
        if rule is None or getattr(rule, "per_file", False):
            continue
        out.append(code)
    return tuple(out)


def _join(codes: Sequence[str]) -> str:
    """
    Render a list of codes as English.

    Parameters
    ----------
    codes : sequence of str
        The codes.

    Returns
    -------
    str
        For example ``"GL08, PR01 and RT01"``.
    """
    if len(codes) == 1:
        return codes[0]
    return f"{', '.join(codes[:-1])} and {codes[-1]}"


@registry.register
class UnnecessarySuppression(BaseFileRule):
    """NQ01: an inline suppression comment that had nothing to suppress."""

    code = "NQ01"
    name = "unnecessary-suppression"
    summary = "An inline suppression should suppress something."

    def check_file(self, ctx: Context) -> Iterable[Diagnostic]:
        """
        Report every suppression comment that did no work.

        A code is only reported once it has been evaluated, meaning the rule
        was enabled for the object the comment sits on and was consulted. A
        code that configuration had already disabled is left alone, so running
        with a narrowed ``--select`` does not condemn the comments belonging
        to the rules it left out.

        Parameters
        ----------
        ctx : Context
            Shared state for the file.

        Yields
        ------
        Diagnostic
            One per comment, naming the codes that suppressed nothing.
        """
        usage = ctx.usage
        if usage is None:  # pragma: no cover - the runner always provides one
            return
        for suppression in ctx.source.noqa.values():
            if self.code in suppression.codes:
                # The comment opts itself out of this very rule.
                continue
            codes = judgeable_codes(suppression)
            if not codes:
                continue
            if suppression.line not in usage.attached:
                yield self.at(
                    ctx,
                    suppression.line,
                    suppression.col,
                    render("NQ01", detail="it applies to no documented object"),
                )
                continue
            wasted = [code for code in codes if usage.is_wasted(suppression, code)]
            if not wasted:
                continue
            if wasted == [ALL_CODES]:
                detail = "no rule was reported for this object"
            else:
                verb = "was" if len(wasted) == 1 else "were"
                detail = f"{_join(wasted)} {verb} not reported for this object"
            yield self.at(
                ctx,
                suppression.line,
                suppression.col,
                render("NQ01", detail=detail),
            )


@registry.register
class UnknownSuppressionCode(BaseFileRule):
    """NQ02: a suppression comment naming a rule code that does not exist."""

    code = "NQ02"
    name = "unknown-suppression-code"
    summary = "An inline suppression should name rules that exist."

    def check_file(self, ctx: Context) -> Iterable[Diagnostic]:
        """
        Report codes that no registered rule answers to.

        Only the ``# numpydoc ignore`` spelling is checked, because a code in
        a ``# noqa`` comment is as likely to belong to another linter as to be
        a typo.

        Parameters
        ----------
        ctx : Context
            Shared state for the file.

        Yields
        ------
        Diagnostic
            One per comment, naming the unknown codes.
        """
        for suppression in ctx.source.noqa.values():
            if not suppression.numpydoc_style or self.code in suppression.codes:
                continue
            unknown = sorted(
                code
                for code in suppression.codes
                if code != ALL_CODES and registry.get(code) is None
            )
            if not unknown:
                continue
            noun = "code" if len(unknown) == 1 else "codes"
            yield self.at(
                ctx,
                suppression.line,
                suppression.col,
                render("NQ02", detail=f"unknown rule {noun} {_join(unknown)}"),
            )
