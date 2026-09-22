"""Inline suppression comments."""

from __future__ import annotations

import pytest
from tests.conftest import codes_at

from numpydoc_linter.source import ALL_CODES, extract_noqa


@pytest.mark.parametrize(
    ("comment", "expected"),
    [
        ("# noqa: PR04", {"PR04"}),
        ("# noqa: PR04,RT01", {"PR04", "RT01"}),
        ("# noqa: PR04, RT01", {"PR04", "RT01"}),
        ("# noqa", {ALL_CODES}),
        ("# numpydoc ignore=GL08", {"GL08"}),
        ("# numpydoc ignore: GL08 ES01", {"GL08", "ES01"}),
        ("# NOQA: pr04", {"PR04"}),
    ],
)
def test_parsing(comment, expected):
    assert extract_noqa(f"x = 1  {comment}\n")[1].codes == expected


@pytest.mark.parametrize(
    ("comment", "numpydoc_style"),
    [("# noqa: PR04", False), ("# numpydoc ignore=PR04", True)],
)
def test_the_spelling_is_remembered(comment, numpydoc_style):
    """Only numpydoc's spelling is unambiguously addressed to this tool."""
    assert extract_noqa(f"x = 1  {comment}\n")[1].numpydoc_style is numpydoc_style


def test_the_column_points_at_the_comment():
    assert extract_noqa("x = 1  # noqa: PR04\n")[1].col == 8


def test_unrelated_comments_are_ignored():
    assert extract_noqa("x = 1  # todo: fix\n") == {}


def test_hash_inside_a_string_is_not_a_comment():
    assert extract_noqa('x = "# noqa: PR04"\n') == {}


def test_suppression_on_the_def_line(lint):
    text = '"""M."""\n\n\ndef f():  # noqa: GL08\n    pass\n'
    assert lint(text, {"select": ["GL08"]}) == []


def test_suppression_on_the_docstring_closing_line(lint):
    text = '''"""M."""


def f(x):
    """
    Summary.
    """  # noqa: PR01
'''
    assert lint(text, {"select": ["PR01"]}) == []


def test_bare_noqa_suppresses_everything(lint):
    found = lint('"""M."""\n\n\ndef f():  # noqa\n    pass\n', EVERYTHING)
    assert found == []


def test_suppression_is_specific(lint):
    text = '"""M."""\n\n\ndef f():  # noqa: RT01\n    pass\n'
    found = lint(text, {"select": ["GL08"]})
    assert codes_at(found) == {(4, "GL08")}


def test_suppression_does_not_leak_to_other_objects(lint):
    text = '"""M."""\n\n\ndef f():  # noqa: GL08\n    pass\n\n\ndef g():\n    pass\n'
    found = lint(text, {"select": ["GL08"]})
    assert codes_at(found) == {(8, "GL08")}


def test_suppression_on_a_multi_line_signature(lint):
    """The natural place for the comment is the return-annotation line."""
    text = '''"""M."""

from typing import overload


@overload
def f(
    x: int,
) -> int:  # numpydoc ignore=GL08
    ...
'''
    assert lint(text, {"select": ["GL08"]}) == []


def test_suppression_on_a_closing_paren_line(lint):
    text = '''"""M."""


def f(
    x,
) -> int:  # noqa: GL08
    return x
'''
    assert lint(text, {"select": ["GL08"]}) == []


def test_suppression_in_the_body_does_not_apply_to_the_function(lint):
    """Unlike numpydoc, a comment deep in the body is not a signature comment."""
    text = '''"""M."""


def f(x):
    y = x + 1  # noqa: GL08
    return y
'''
    assert [d.code for d in lint(text, {"select": ["GL08"]})] == ["GL08"]


def test_suppression_on_a_decorator_line(lint):
    text = '''"""M."""


@property  # noqa: GL08
def f(x):
    return x
'''
    assert lint(text, {"select": ["GL08"]}) == []


DOCUMENTED = '''"""M."""


def f(x):  # {comment}
    """
    Summarise.

    Parameters
    ----------
    x : int
        The value.

    Returns
    -------
    int
        The value.
    """
    return x
'''


#: Every rule except the three that a short docstring can never satisfy.
EVERYTHING = {"select": ["ALL"], "ignore": ["ES01", "SA01", "EX01"]}


def documented(comment: str) -> str:
    """Build a file whose only fault, if any, is the suppression comment."""
    return DOCUMENTED.format(comment=comment)


def test_a_suppression_that_works_is_not_reported(lint):
    text = '"""M."""\n\n\ndef f():  # numpydoc ignore=GL08\n    pass\n'
    assert lint(text, {"select": ["GL08", "NQ"]}) == []


def test_a_suppression_that_suppresses_nothing_is_reported(lint):
    found = lint(documented("numpydoc ignore=SS03"), {"select": ["SS03", "NQ"]})
    assert codes_at(found) == {(4, "NQ01")}
    assert "SS03 was not reported" in found[0].message


def test_only_the_wasted_codes_are_named(lint):
    text = '"""M."""\n\n\ndef f():  # numpydoc ignore=GL08,RT01\n    pass\n'
    found = lint(text, {"select": ["GL08", "RT01", "NQ"]})
    assert codes_at(found) == {(4, "NQ01")}
    assert "RT01 was not reported" in found[0].message
    assert "GL08" not in found[0].message


def test_the_diagnostic_points_at_the_comment(lint):
    found = lint(documented("numpydoc ignore=SS03"), {"select": ["SS03", "NQ"]})
    assert (found[0].line, found[0].col) == (4, 12)


def test_a_rule_disabled_by_configuration_is_not_judged(lint):
    """Narrowing the selection must not condemn the comments left behind."""
    assert lint(documented("numpydoc ignore=SS03"), {"select": ["GL08", "NQ"]}) == []


def test_a_comment_attached_to_nothing_is_reported(lint):
    text = '''"""M."""


def f():
    """Summarise."""
    y = 1  # numpydoc ignore=GL08
    return y
'''
    found = lint(text, {"select": ["GL08", "NQ"]})
    assert codes_at(found) == {(6, "NQ01")}
    assert "no documented object" in found[0].message


def test_a_bare_numpydoc_ignore_that_does_nothing_is_reported(lint):
    found = lint(documented("numpydoc ignore"), EVERYTHING)
    assert codes_at(found) == {(4, "NQ01")}
    assert "no rule was reported" in found[0].message


def test_a_bare_noqa_is_left_alone(lint):
    """It may well be there for another linter."""
    assert lint(documented("noqa"), EVERYTHING) == []


def test_another_linters_code_is_left_alone(lint):
    assert lint(documented("noqa: F401"), EVERYTHING) == []


def test_our_code_in_a_noqa_comment_is_judged(lint):
    found = lint(documented("noqa: SS03"), {"select": ["SS03", "NQ"]})
    assert codes_at(found) == {(4, "NQ01")}


def test_an_unknown_code_is_reported(lint):
    found = lint(documented("numpydoc ignore=GL99"), EVERYTHING)
    assert codes_at(found) == {(4, "NQ02")}
    assert "unknown rule code GL99" in found[0].message


def test_an_unknown_code_in_a_noqa_comment_is_left_alone(lint):
    assert lint(documented("noqa: GL99"), EVERYTHING) == []


def test_a_comment_may_exempt_itself(lint):
    found = lint(documented("numpydoc ignore=SS03,NQ01"), EVERYTHING)
    assert found == []


def test_the_rule_can_be_turned_off(lint):
    assert lint(documented("numpydoc ignore=SS03"), {"select": ["SS03"]}) == []


def test_per_file_ignores_turn_it_off(lint):
    table = {"select": ["SS03", "NQ"], "per-file-ignores": {"sample.py": ["NQ"]}}
    assert lint(documented("numpydoc ignore=SS03"), table) == []


def test_an_excluded_object_is_not_judged(lint):
    table = {**EVERYTHING, "exclude-object-patterns": ["^sample.f$"]}
    assert lint(documented("numpydoc ignore=SS03"), table) == []


def test_a_docstring_override_is_not_judged(lint):
    """Configuration already suppresses the rule, so the comment is moot."""
    table = {"select": ["SS03", "NQ"], "overrides": {"SS03": ["Summarise"]}}
    assert lint(documented("numpydoc ignore=SS03"), table) == []


def test_a_scope_block_that_disables_a_rule_is_not_judged(lint):
    table = {
        "select": ["SS03", "NQ"],
        "scope": [{"match": {"kind": "function"}, "extend-ignore": ["SS03"]}],
    }
    assert lint(documented("numpydoc ignore=SS03"), table) == []
