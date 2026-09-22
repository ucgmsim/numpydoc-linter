"""Constructors synthesised by decorators."""

from __future__ import annotations

from tests.conftest import codes_at


def test_fields_become_parameters(lint):
    found = lint(
        '''"""M."""

from dataclasses import dataclass


@dataclass
class Point:
    """
    A point.

    Parameters
    ----------
    x : int
        The x.
    y : int
        The y.
    """

    x: int
    y: int
''',
        {"select": ["PR"]},
    )
    assert found == []


def test_undocumented_field_is_reported(lint):
    found = lint(
        '''"""M."""

from dataclasses import dataclass


@dataclass
class Point:
    """
    A point.

    Parameters
    ----------
    x : int
        The x.
    """

    x: int
    y: int
''',
        {"select": ["PR"]},
    )
    assert [d.code for d in found] == ["PR01"]
    assert "'y'" in found[0].message


def test_classvar_and_init_false_are_excluded(lint):
    found = lint(
        '''"""M."""

from dataclasses import dataclass, field
from typing import ClassVar


@dataclass
class Point:
    """
    A point.

    Parameters
    ----------
    x : int
        The x.
    """

    x: int
    registry: ClassVar[dict] = {}
    cached: int = field(init=False, default=0)
''',
        {"select": ["PR"]},
    )
    assert found == []


def test_initvar_is_included_and_unwrapped(lint):
    found = lint(
        '''"""M."""

from dataclasses import dataclass, InitVar


@dataclass
class Point:
    """
    A point.

    Parameters
    ----------
    x : int
        The x.
    seed : int
        The seed.
    """

    x: int
    seed: InitVar[int] = 0
''',
        {"select": ["PR"]},
    )
    assert found == []


def test_inherited_fields_come_first(lint):
    found = lint(
        '''"""M."""

from dataclasses import dataclass


@dataclass
class Base:
    """
    A base.

    Parameters
    ----------
    a : int
        The a.
    """

    a: int


@dataclass
class Child(Base):
    """
    A child.

    Parameters
    ----------
    a : int
        The a.
    b : int
        The b.
    """

    b: int
''',
        {"select": ["PR"]},
    )
    assert found == []


def test_unknown_parameters_are_forgiven_when_a_base_is_unresolvable(lint):
    """A base defined elsewhere may contribute fields we cannot see."""
    found = lint(
        '''"""M."""

from dataclasses import dataclass

from elsewhere import Base


@dataclass
class Child(Base):
    """
    A child.

    Parameters
    ----------
    inherited : int
        Defined on the base, in another module.
    b : int
        The b.
    """

    b: int
''',
        {"select": ["PR"]},
    )
    assert [d.code for d in found] == []


def test_explicit_init_wins_over_derivation(lint):
    found = lint(
        '''"""M."""

from dataclasses import dataclass


@dataclass
class Point:
    """
    A point.

    Parameters
    ----------
    z : int
        The z.
    """

    x: int

    def __init__(self, z):
        self.x = z
''',
        {"select": ["PR"]},
    )
    assert found == []


def test_dataclass_predicate_is_matchable(lint):
    found = lint(
        '''"""M."""

from dataclasses import dataclass


@dataclass
class Point:
    """A point."""

    x: int
''',
        {
            "select": ["PR"],
            "scope": [{"match": {"dataclass": True}, "skip": True}],
        },
    )
    assert found == []


def test_attrs_decorators_are_recognised(lint):
    found = lint(
        '''"""M."""

import attrs


@attrs.define
class Point:
    """A point."""

    x: int
''',
        {"select": ["PR01"]},
    )
    assert codes_at(found) == {(7, "PR01")}


def test_private_parameters_can_be_exempted(lint):
    """Underscore-prefixed fields are implementation detail, not API."""
    text = '''"""M."""

from dataclasses import dataclass


@dataclass
class Holder:
    """
    A holder.

    Parameters
    ----------
    value : int
        The value.
    """

    value: int
    _cache: dict | None = None
'''
    assert [d.code for d in lint(text, {"select": ["PR"]})] == ["PR01"]
    assert lint(text, {"select": ["PR"], "private-parameters": "ignore"}) == []


def test_documenting_an_exempt_private_parameter_is_not_an_error(lint):
    text = '''"""M."""

from dataclasses import dataclass


@dataclass
class Holder:
    """
    A holder.

    Parameters
    ----------
    value : int
        The value.
    _cache : dict or None
        The cache.
    """

    value: int
    _cache: dict | None = None
'''
    assert lint(text, {"select": ["PR"], "private-parameters": "ignore"}) == []


def test_fields_may_be_documented_as_attributes(lint):
    """A dataclass field is an attribute as much as a constructor parameter."""
    text = '''"""M."""

from dataclasses import dataclass


@dataclass
class Point:
    """
    A point.

    Attributes
    ----------
    x : int
        The x.
    y : int
        The y.
    """

    x: int
    y: int
'''
    assert lint(text, {"select": ["PR"]}) == []
    strict = {"select": ["PR"], "dataclass-fields-section": "parameters"}
    assert [d.code for d in lint(text, strict)] == ["PR01"]


def test_an_attribute_that_is_not_a_field_is_not_an_unknown_parameter(lint):
    """Attributes may describe properties and ClassVars, which take no argument."""
    text = '''"""M."""

from dataclasses import dataclass


@dataclass
class Point:
    """
    A point.

    Attributes
    ----------
    x : int
        The x.
    magnitude : float
        A derived property, not a field.
    """

    x: int

    @property
    def magnitude(self) -> float:
        """float: The magnitude."""
        return float(self.x)
'''
    assert [d.code for d in lint(text, {"select": ["PR01", "PR02", "PR03"]})] == []


def test_a_non_field_in_parameters_is_still_unknown(lint):
    text = '''"""M."""

from dataclasses import dataclass


@dataclass
class Point:
    """
    A point.

    Parameters
    ----------
    x : int
        The x.
    nonsense : int
        Not a field.
    """

    x: int
'''
    assert [d.code for d in lint(text, {"select": ["PR"]})] == ["PR02"]


def test_a_plain_class_still_needs_parameters(lint):
    """Only dataclasses get the Attributes leniency."""
    text = '''"""M."""


class Point:
    """
    A point.

    Attributes
    ----------
    x : int
        The x.
    """

    def __init__(self, x):
        self.x = x
'''
    assert [d.code for d in lint(text, {"select": ["PR01"]})] == ["PR01"]


def test_inline_attribute_docstrings_count_as_documentation(lint):
    """A bare string below a field is how Sphinx documents class attributes."""
    text = '''"""M."""

from dataclasses import dataclass


@dataclass
class Point:
    """A point."""

    x: int
    """The x."""
    y: int
    """The y."""
'''
    assert lint(text, {"select": ["PR"]}) == []
    strict = {"select": ["PR"], "dataclass-fields-section": "parameters"}
    assert [d.code for d in lint(text, strict)] == ["PR01"]


def test_a_field_without_an_inline_docstring_is_still_reported(lint):
    text = '''"""M."""

from dataclasses import dataclass


@dataclass
class Point:
    """A point."""

    x: int
    """The x."""
    y: int
'''
    found = lint(text, {"select": ["PR01"]})
    assert [d.code for d in found] == ["PR01"]
    assert "'y'" in found[0].message
    assert "'x'" not in found[0].message


def test_a_string_further_down_does_not_document_a_field(lint):
    text = '''"""M."""

from dataclasses import dataclass


@dataclass
class Point:
    """A point."""

    x: int
    y: int
    """This documents y, not x."""
'''
    found = lint(text, {"select": ["PR01"]})
    assert "'x'" in found[0].message
    assert "'y'" not in found[0].message
