"""Ruff-style selection of rule codes.

A selector is ``ALL``, a family prefix such as ``PR``, a partial code such as
``PR0``, or a full code such as ``PR04``. Where two selectors both match a code,
the more specific one wins; at equal specificity an ignore beats a select.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

#: The selector that matches every rule.
ALL = "ALL"


class SelectorError(ValueError):
    """Raised when a selector matches no known rule code."""


def specificity(selector: str) -> int:
    """
    Score how specific a selector is.

    Parameters
    ----------
    selector : str
        The selector to score.

    Returns
    -------
    int
        Zero for ``ALL``, otherwise the length of the prefix.
    """
    if selector == ALL:
        return 0
    return len(selector)


def matches(selector: str, code: str) -> bool:
    """
    Report whether a selector covers a rule code.

    Parameters
    ----------
    selector : str
        The selector.
    code : str
        The rule code.

    Returns
    -------
    bool
        True when the selector covers the code.
    """
    if selector == ALL:
        return True
    return code.startswith(selector)


def validate(selectors: Iterable[str], known: Sequence[str]) -> None:
    """
    Check that every selector matches at least one known code.

    Parameters
    ----------
    selectors : iterable of str
        Selectors to validate.
    known : sequence of str
        Every registered rule code.

    Raises
    ------
    SelectorError
        When a selector matches nothing.
    """
    for sel in selectors:
        if not any(matches(sel, code) for code in known):
            raise SelectorError(f"unknown rule selector {sel!r}")


def expand(selectors: Iterable[str], known: Sequence[str]) -> frozenset[str]:
    """
    Expand selectors into the set of codes they cover.

    Parameters
    ----------
    selectors : iterable of str
        Selectors to expand.
    known : sequence of str
        Every registered rule code.

    Returns
    -------
    frozenset of str
        The covered codes.
    """
    out: set[str] = set()
    for sel in selectors:
        out.update(code for code in known if matches(sel, code))
    return frozenset(out)


def apply_level(
    base: frozenset[str],
    known: Sequence[str],
    *,
    select: Sequence[str] | None = None,
    ignore: Sequence[str] | None = None,
    extend_select: Sequence[str] = (),
    extend_ignore: Sequence[str] = (),
    skip: bool = False,
) -> frozenset[str]:
    """
    Layer one level of selection on top of an existing set of codes.

    ``select`` replaces the incoming set; ``extend_select`` adds to it. Codes
    touched by neither a select nor an ignore selector keep their incoming
    membership.

    Parameters
    ----------
    base : frozenset of str
        Codes enabled before this level.
    known : sequence of str
        Every registered rule code.
    select : sequence of str, optional
        Selectors that replace the incoming set.
    ignore : sequence of str, optional
        Selectors that disable codes.
    extend_select : sequence of str
        Selectors that add codes to the incoming set.
    extend_ignore : sequence of str
        Further selectors that disable codes.
    skip : bool
        When true, start from an empty set.

    Returns
    -------
    frozenset of str
        Codes enabled after this level.
    """
    if skip:
        base = frozenset()

    selectors = list(select or []) + list(extend_select)
    ignores = list(ignore or []) + list(extend_ignore)

    result = set() if select is not None else set(base)

    for code in known:
        best_select = max(
            (specificity(s) for s in selectors if matches(s, code)), default=-1
        )
        best_ignore = max(
            (specificity(s) for s in ignores if matches(s, code)), default=-1
        )
        if best_select < 0 and best_ignore < 0:
            continue
        if best_ignore >= best_select:
            result.discard(code)
        else:
            result.add(code)

    return frozenset(result)
