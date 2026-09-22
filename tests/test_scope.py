"""Scope-block resolution."""

from __future__ import annotations

import pytest
from tests.conftest import codes_at

SAMPLE = '''"""M."""


def public():
    pass


def _private():
    pass


class Widget:
    """A widget."""

    def method(self):
        pass

    def __repr__(self):
        pass

    @property
    def size(self):
        pass
'''


def test_no_scopes_reports_everything(lint):
    found = lint(SAMPLE, {"select": ["GL08"]})
    assert codes_at(found) == {
        (4, "GL08"),
        (8, "GL08"),
        (15, "GL08"),
        (18, "GL08"),
        (22, "GL08"),
    }


def test_skip_private(lint):
    found = lint(
        SAMPLE,
        {"select": ["GL08"], "scope": [{"match": {"private": True}, "skip": True}]},
    )
    assert (8, "GL08") not in codes_at(found)


def test_skip_by_kind(lint):
    found = lint(
        SAMPLE,
        {
            "select": ["GL08"],
            "scope": [{"match": {"kind": "property"}, "skip": True}],
        },
    )
    assert (22, "GL08") not in codes_at(found)


def test_kind_group_any_method(lint):
    found = lint(
        SAMPLE,
        {
            "select": ["GL08"],
            "scope": [{"match": {"kind": "any-method"}, "skip": True}],
        },
    )
    assert codes_at(found) == {(4, "GL08"), (8, "GL08")}


def test_blocks_layer_in_order(lint):
    """A later block can put back what an earlier one took away."""
    found = lint(
        SAMPLE,
        {
            "select": ["GL08"],
            "scope": [
                {"match": {}, "skip": True},
                {"match": {"kind": "property"}, "extend-select": ["GL08"]},
            ],
        },
    )
    assert codes_at(found) == {(22, "GL08")}


def test_select_in_a_block_replaces_the_set(lint):
    found = lint(
        SAMPLE,
        {
            "select": ["ALL"],
            "scope": [{"match": {"dunder": True}, "select": ["GL08"]}],
        },
    )
    dunder = {c for line, c in codes_at(found) if line == 18}
    assert dunder == {"GL08"}


def test_qualname_regex(lint):
    found = lint(
        SAMPLE,
        {
            "select": ["GL08"],
            "scope": [{"match": {"qualname": r"^sample\.Widget\."}, "skip": True}],
        },
    )
    assert codes_at(found) == {(4, "GL08"), (8, "GL08")}


def test_name_regex(lint):
    found = lint(
        SAMPLE,
        {"select": ["GL08"], "scope": [{"match": {"name": "^public$"}, "skip": True}]},
    )
    assert (4, "GL08") not in codes_at(found)


def test_decorator_match(lint):
    found = lint(
        SAMPLE,
        {
            "select": ["GL08"],
            "scope": [{"match": {"decorator": "property"}, "skip": True}],
        },
    )
    assert (22, "GL08") not in codes_at(found)


def test_parent_kind_match(lint):
    found = lint(
        SAMPLE,
        {
            "select": ["GL08"],
            "scope": [{"match": {"parent-kind": "class"}, "skip": True}],
        },
    )
    assert codes_at(found) == {(4, "GL08"), (8, "GL08")}


def test_predicates_are_anded(lint):
    """Both conditions must hold, so a private non-method is untouched."""
    found = lint(
        SAMPLE,
        {
            "select": ["GL08"],
            "scope": [
                {"match": {"private": True, "kind": "method"}, "skip": True}
            ],
        },
    )
    assert (8, "GL08") in codes_at(found)


def test_per_file_ignores(lint):
    table = {"select": ["GL08"], "per-file-ignores": {"sample.py": ["GL08"]}}
    found = lint(SAMPLE, table)
    assert found == []


def test_per_file_ignores_do_not_match_other_files(lint):
    table = {"select": ["GL08"], "per-file-ignores": {"other.py": ["GL08"]}}
    found = lint(SAMPLE, table)
    assert found != []


def test_path_match_in_scope(lint):
    found = lint(
        SAMPLE,
        {
            "select": ["GL08"],
            "scope": [{"match": {"path": "sample.py"}, "skip": True}],
        },
    )
    assert found == []


@pytest.mark.parametrize("value", [True, False])
def test_in_all_predicate(lint, value):
    text = (
        '"""M."""\n\n__all__ = ["a"]\n\n\n'
        "def a():\n    pass\n\n\ndef b():\n    pass\n"
    )
    found = lint(
        text,
        {"select": ["GL08"], "scope": [{"match": {"in-all": value}, "skip": True}]},
    )
    kept = {line for line, _ in codes_at(found)}
    assert kept == ({10} if value else {6})
