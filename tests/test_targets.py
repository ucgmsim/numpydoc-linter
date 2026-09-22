"""Classification of documentable objects."""

from __future__ import annotations

import pytest
from tests.conftest import targets_of


def by_name(text: str) -> dict[str, object]:
    return {t.name: t for t in targets_of(text)}


def test_module_is_the_first_target():
    targets = targets_of('"""Doc."""\n')
    assert targets[0].kind == "module"
    assert targets[0].lineno == 1


def test_property_variants_are_distinguished():
    targets = by_name(
        """
import functools


class C:
    @property
    def a(self): ...

    @functools.cached_property
    def b(self): ...

    @a.setter
    def a(self, v): ...

    @classmethod
    def c(cls): ...

    @staticmethod
    def d(): ...

    def e(self): ...
"""
    )
    assert targets["b"].kind == "property"
    assert targets["c"].kind == "classmethod"
    assert targets["d"].kind == "staticmethod"
    assert targets["e"].kind == "method"


def test_custom_property_decorator_is_configurable():
    import ast
    from pathlib import Path

    from npdlint.targets import collect_targets

    text = """
class C:
    @computed_field
    def a(self): ...
"""
    default = collect_targets(ast.parse(text), Path("x.py"), "x")
    assert default[-1].kind == "method"
    custom = collect_targets(
        ast.parse(text), Path("x.py"), "x", ("property", "computed_field")
    )
    assert custom[-1].kind == "property"


def test_self_and_cls_are_dropped_but_not_from_staticmethods():
    targets = by_name(
        """
class C:
    def m(self, x): ...

    @classmethod
    def c(cls, x): ...

    @staticmethod
    def s(self, x): ...
"""
    )
    assert targets["m"].signature_parameters == ("x",)
    assert targets["c"].signature_parameters == ("x",)
    assert targets["s"].signature_parameters == ("self", "x")


def test_variadic_parameters_are_starred():
    targets = by_name("def f(a, /, b, *args, c, **kwargs): ...")
    assert targets["f"].signature_parameters == ("a", "b", "*args", "c", "**kwargs")


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("return 1", True),
        ("return None", False),
        ("return", False),
        ("pass", False),
        ("def inner():\n        return 1", False),
        ("x = lambda: 1", False),
        ("if a:\n        return 1", True),
    ],
)
def test_returns_value(body, expected):
    targets = by_name(f"def f(a):\n    {body}\n")
    assert targets["f"].returns_value is expected


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("yield 1", True),
        ("yield from range(3)", True),
        ("if a:\n        yield 1", True),
        ("x = yield 1", True),
        ("return 1", False),
        ("def inner():\n        yield 1", False),
    ],
)
def test_generator_detection(body, expected):
    targets = by_name(f"def f(a):\n    {body}\n")
    assert targets["f"].is_generator is expected


def test_abstract_and_stub_are_separate():
    targets = by_name(
        """
import abc


class C:
    @abc.abstractmethod
    def a(self): ...

    def b(self): pass

    def c(self): return 1
"""
    )
    assert (targets["a"].is_abstract, targets["a"].is_stub) == (True, True)
    assert (targets["b"].is_abstract, targets["b"].is_stub) == (False, True)
    assert (targets["c"].is_abstract, targets["c"].is_stub) == (False, False)


def test_private_and_dunder():
    targets = by_name(
        """
class C:
    def _p(self): ...

    def __d__(self): ...

    def pub(self): ...
"""
    )
    assert targets["_p"].is_private and not targets["_p"].is_dunder
    assert targets["__d__"].is_dunder and not targets["__d__"].is_private
    assert not targets["pub"].is_private


def test_dunder_init_is_dunder_not_private():
    targets = by_name("class C:\n    def __init__(self): ...")
    assert targets["__init__"].is_dunder
    assert not targets["__init__"].is_private


def test_in_all_membership():
    targets = by_name('__all__ = ["a"]\n\n\ndef a(): ...\n\n\ndef b(): ...')
    assert targets["a"].in_all is True
    assert targets["b"].in_all is False


def test_in_all_is_none_when_dynamic():
    targets = by_name("__all__ = compute()\n\n\ndef a(): ...")
    assert targets["a"].in_all is None


def test_nested_objects_are_marked():
    targets = targets_of(
        """
def outer():
    def inner(): ...

    if True:
        def deeper(): ...


class C:
    def m(self): ...
"""
    )
    nested = {t.name for t in targets if t.is_nested}
    assert nested == {"inner", "deeper"}


def test_qualified_names():
    targets = targets_of("class A:\n    class B:\n        def c(self): ...")
    assert [t.qualname for t in targets] == [
        "sample",
        "sample.A",
        "sample.A.B",
        "sample.A.B.c",
    ]


def test_decorators_are_dotted():
    targets = by_name("import a.b\n\n\n@a.b.deco(1)\ndef f(): ...")
    assert targets["f"].decorators == ("a.b.deco",)


def test_overload_and_override():
    targets = by_name(
        """
from typing import overload, override


class C:
    @overload
    def f(self) -> int: ...

    @override
    def g(self): ...
"""
    )
    assert targets["f"].is_overload
    assert targets["g"].is_override


def test_return_annotation_is_captured():
    targets = by_name("def f() -> dict[str, int]: ...")
    assert targets["f"].return_annotation == "dict[str, int]"
