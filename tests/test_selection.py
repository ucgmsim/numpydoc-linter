"""Selector expansion and specificity."""

from __future__ import annotations

import pytest

from numpydoc_linter import selection
from numpydoc_linter.rules.base import registry

KNOWN = ("ES01", "GL08", "PR01", "PR04", "PT01", "RT01", "SA01")


@pytest.mark.parametrize(
    ("selector", "expected"),
    [
        ("ALL", 0),
        ("PR", 2),
        ("PR0", 3),
        ("PR04", 4),
    ],
)
def test_specificity(selector, expected):
    assert selection.specificity(selector) == expected


def test_all_matches_everything():
    assert selection.expand(["ALL"], KNOWN) == frozenset(KNOWN)


def test_family_prefix():
    assert selection.expand(["PR"], KNOWN) == {"PR01", "PR04"}


def test_select_then_ignore():
    got = selection.apply_level(frozenset(), KNOWN, select=["ALL"], ignore=["PR"])
    assert got == {"ES01", "GL08", "PT01", "RT01", "SA01"}


def test_more_specific_select_beats_broader_ignore():
    got = selection.apply_level(
        frozenset(), KNOWN, select=["ALL", "PR04"], ignore=["PR"]
    )
    assert "PR04" in got
    assert "PR01" not in got


def test_ignore_wins_at_equal_specificity():
    got = selection.apply_level(frozenset(), KNOWN, select=["PR04"], ignore=["PR04"])
    assert got == frozenset()


def test_extend_select_adds_to_base():
    base = selection.apply_level(frozenset(), KNOWN, select=["GL08"])
    got = selection.apply_level(base, KNOWN, extend_select=["PT"])
    assert got == {"GL08", "PT01"}


def test_select_replaces_base_but_extend_does_not():
    base = frozenset({"GL08", "RT01"})
    assert selection.apply_level(base, KNOWN, select=["PT"]) == {"PT01"}
    assert selection.apply_level(base, KNOWN, extend_select=["PT"]) == {
        "GL08",
        "RT01",
        "PT01",
    }


def test_skip_empties_the_set():
    base = frozenset(KNOWN)
    assert selection.apply_level(base, KNOWN, skip=True) == frozenset()


def test_untouched_codes_keep_membership():
    base = frozenset({"GL08"})
    got = selection.apply_level(base, KNOWN, extend_ignore=["PR"])
    assert got == {"GL08"}


def test_validate_rejects_unknown_selector():
    with pytest.raises(selection.SelectorError):
        selection.validate(["ZZ99"], registry.codes())


def test_validate_accepts_every_registered_code():
    selection.validate(registry.codes(), registry.codes())
