"""Property docstring forms."""

from __future__ import annotations

import pytest

from numpydoc_linter.rules.properties import (
    PropertyFormError,
    _normalise_type,
    resolve_form,
)

TEMPLATE = '''"""M."""


class C:
    """C."""

    @property
    def a(self){annotation}:
        """{doc}"""
        return 1
'''


def build(doc: str, annotation: str = " -> float") -> str:
    return TEMPLATE.format(doc=doc, annotation=annotation)


def scoped(form) -> dict:
    return {
        "select": ["PT"],
        "scope": [{"match": {"kind": "property"}, "property-form": form}],
    }


def test_type_line_accepts_the_convention(lint):
    assert lint(build("float: The area."), scoped("type-line")) == []


def test_type_line_rejects_a_bare_summary(lint):
    found = lint(build("The area."), scoped("type-line"))
    assert [d.code for d in found] == ["PT01"]


def test_type_line_reports_a_mismatched_annotation(lint):
    found = lint(build("int: The area."), scoped("type-line"))
    assert [d.code for d in found] == ["PT02"]
    assert 'documents type "int"' in found[0].message


def test_no_annotation_means_no_type_check(lint):
    assert lint(build("int: The area.", annotation=""), scoped("type-line")) == []


@pytest.mark.parametrize(
    ("documented", "annotation"),
    [
        ("int | None", " -> Optional[int]"),
        ("int or None", " -> int | None"),
        ("dict[str, int]", " -> dict[str,int]"),
        ("Circle", ' -> "Circle"'),
        ("int", " -> typing.int"),
    ],
)
def test_type_comparison_is_tolerant_of_spelling(lint, documented, annotation):
    found = lint(build(f"{documented}: The thing.", annotation), scoped("type-line"))
    assert found == []


def test_returns_section_is_forbidden_under_type_line(lint):
    doc = """float: The area.

        Returns
        -------
        float
            The area.
        """
    found = lint(build(doc), scoped("type-line"))
    assert "PT03" in {d.code for d in found}


def test_summary_only_form(lint):
    assert lint(build("The area."), scoped("summary-only")) == []
    found = lint(build("float: The area."), scoped("summary-only"))
    assert found == []  # a summary starting with a type is still a summary


def test_returns_section_form_imposes_no_shape(lint):
    assert lint(build("Anything at all"), scoped("returns-section")) == []


def test_custom_regex_form(lint):
    form = {
        "regex": r"^(?P<type>[A-Z]\w*) -- (?P<summary>.+)$",
        "description": "T -- s",
    }
    assert lint(build("Float -- The area.", " -> Float"), scoped(form)) == []
    found = lint(build("float: The area."), scoped(form))
    assert "PT01" in {d.code for d in found}


def test_custom_form_description_appears_in_the_message(lint):
    form = {"regex": r"^\d+$", "description": "digits only"}
    found = lint(build("float: The area."), scoped(form))
    assert "digits only" in found[0].message


def test_unknown_form_is_rejected():
    with pytest.raises(PropertyFormError, match="unknown property-form"):
        resolve_form("type_line")


def test_invalid_regex_is_rejected():
    with pytest.raises(PropertyFormError, match="invalid property-form regex"):
        resolve_form({"regex": "([unclosed"})


def test_default_form_is_plain_numpydoc():
    assert resolve_form(None).name == "returns-section"


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Optional[int]", "int | None"),
        ("Union[int, str]", "int|str"),
        ("  float  ", "float"),
        ("'Circle'", "Circle"),
        ("typing.Sequence[int]", "Sequence[int]"),
    ],
)
def test_normalise_type(a, b):
    assert _normalise_type(a) == _normalise_type(b)


def test_summary_rules_look_past_the_type(lint):
    """Under a type-line form, SS02 judges the summary, not the type."""
    table = {
        "select": ["SS02", "SS03"],
        "scope": [{"match": {"kind": "property"}, "property-form": "type-line"}],
    }
    assert lint(build("float: The area."), table) == []
    assert {d.code for d in lint(build("float: the area."), table)} == {"SS02"}
    assert {d.code for d in lint(build("float: The area"), table)} == {"SS03"}


def test_summary_rules_are_unaffected_without_a_form(lint):
    """Plain numpydoc still judges the whole first line."""
    table = {"select": ["SS02"]}
    assert {d.code for d in lint(build("float: The area."), table)} == {"SS02"}


def test_property_rules_do_not_touch_regular_methods(lint):
    text = '''"""M."""


class C:
    """C."""

    def a(self) -> float:
        """Compute a."""
        return 1
'''
    assert lint(text, scoped("type-line")) == []


@pytest.mark.parametrize(
    ("documented", "annotation"),
    [
        ("np.ndarray of shape (4n x 3)", " -> np.ndarray"),
        ("float, optional", " -> float"),
        ("list of int", " -> list"),
        ("np.ndarray with dtype float64", " -> np.ndarray"),
    ],
)
def test_a_documented_type_may_say_more_than_the_annotation(
    lint, documented, annotation
):
    """numpydoc encourages shape and dtype detail the annotation cannot carry."""
    found = lint(build(f"{documented}: The thing.", annotation), scoped("type-line"))
    assert found == []


@pytest.mark.parametrize(
    ("documented", "annotation"),
    [
        ("int", " -> float"),
        ("int", " -> dict[str, int]"),
        ("str", " -> bytes"),
    ],
)
def test_a_different_type_is_still_reported(lint, documented, annotation):
    found = lint(build(f"{documented}: The thing.", annotation), scoped("type-line"))
    assert [d.code for d in found] == ["PT02"]
