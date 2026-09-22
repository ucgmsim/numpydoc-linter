"""Turn a parsed module into the documentable objects that rules run against."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from npdlint.docstring import ParsedDocstring


class Kind(StrEnum):
    """The kind of object a docstring belongs to."""

    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    PROPERTY = "property"
    SETTER = "setter"
    CLASSMETHOD = "classmethod"
    STATICMETHOD = "staticmethod"


#: Kinds that are callables of some sort.
CALLABLE_KINDS = frozenset(
    {
        Kind.FUNCTION,
        Kind.METHOD,
        Kind.PROPERTY,
        Kind.SETTER,
        Kind.CLASSMETHOD,
        Kind.STATICMETHOD,
    }
)

#: Kinds that live inside a class body.
METHOD_KINDS = frozenset(
    {
        Kind.METHOD,
        Kind.PROPERTY,
        Kind.SETTER,
        Kind.CLASSMETHOD,
        Kind.STATICMETHOD,
    }
)

#: Group names accepted wherever a ``kind`` is matched in configuration.
KIND_GROUPS: dict[str, frozenset[Kind]] = {
    "callable": CALLABLE_KINDS,
    "any-method": METHOD_KINDS,
    "any": frozenset(Kind),
}

#: Decorators recognised as defining a read-only property.
DEFAULT_PROPERTY_DECORATORS = (
    "property",
    "cached_property",
    "functools.cached_property",
)

#: Decorators that synthesise an ``__init__`` from annotated class attributes.
DEFAULT_DATACLASS_DECORATORS = (
    "dataclass",
    "dataclasses.dataclass",
    "attr.s",
    "attr.define",
    "attr.frozen",
    "attrs.define",
    "attrs.frozen",
    "pydantic.dataclasses.dataclass",
)

#: Base classes that never contribute dataclass fields.
_INERT_BASES = frozenset(
    {
        "object",
        "Protocol",
        "typing.Protocol",
        "Generic",
        "typing.Generic",
        "ABC",
        "abc.ABC",
    }
)

_ABSTRACT_DECORATORS = frozenset(
    {
        "abstractmethod",
        "abc.abstractmethod",
        "abstractproperty",
        "abc.abstractproperty",
    }
)
_OVERLOAD_DECORATORS = frozenset({"overload", "typing.overload", "t.overload"})
_OVERRIDE_DECORATORS = frozenset(
    {"override", "typing.override", "typing_extensions.override"}
)


@dataclass(frozen=True, slots=True)
class Parameter:
    """
    One entry of a function signature.

    Parameters
    ----------
    name : str
        The parameter name, starred for ``*args`` and ``**kwargs``.
    annotation : str or None
        Source text of the annotation, when written.
    has_default : bool
        Whether the parameter has a default value.
    default : str or None
        Source text of the default value, when written.
    has_inline_doc : bool
        Whether a bare string literal documents the field just below it, as
        Sphinx and other tools recognise for class attributes.
    """

    name: str
    annotation: str | None = None
    has_default: bool = False
    default: str | None = None
    has_inline_doc: bool = False


@dataclass(slots=True)
class Target:
    """
    A documentable object, with everything a rule or a scope match needs.

    Parameters
    ----------
    kind : Kind
        What sort of object this is.
    name : str
        The bare name.
    qualname : str
        The dotted name from the module root.
    module_name : str
        Dotted name of the module the object lives in.
    path : pathlib.Path
        File the object is defined in.
    lineno : int
        One-based line of the ``def``, ``class``, or 1 for a module.
    col : int
        One-based column of the definition.
    node : ast.AST
        The AST node itself.
    raw_docstring : str or None
        The docstring exactly as written, or None when absent.
    _parsed : ParsedDocstring or None
        Cache backing the ``docstring`` property; not set directly.
    parent : Target or None
        The enclosing class or module.
    decorators : tuple of str
        Decorator names, resolved to dotted form.
    parameters : tuple of Parameter
        The signature, or the fields a dataclass decorator will synthesise.
    return_annotation : str or None
        Source text of the return annotation.
    docstring_end_line : int or None
        Line the docstring's closing quotes sit on.
    is_private : bool
        Whether the name starts with a single underscore.
    is_dunder : bool
        Whether the name is of the form ``__name__``.
    is_async : bool
        Whether the object is declared with ``async def``.
    is_abstract : bool
        Whether the object is decorated ``@abstractmethod``.
    is_stub : bool
        Whether the body is only a placeholder.
    is_overload : bool
        Whether the object is decorated ``@overload``.
    is_override : bool
        Whether the object is decorated ``@override``.
    is_generator : bool
        Whether the body yields.
    returns_value : bool
        Whether the body returns something other than None.
    in_all : bool or None
        Membership of the module's ``__all__``, or None when it is dynamic.
    is_dataclass : bool
        Whether a decorator synthesises the constructor.
    is_nested : bool
        Whether the object is defined inside a function body.
    bases : tuple of str
        Base class names, in dotted form.
    has_unresolved_bases : bool
        Whether a base class could not be found in this file.
    is_nested : bool
        Whether the object is defined inside a function body.
    children : list of Target
        Targets defined directly inside this one.
    """

    kind: Kind
    name: str
    qualname: str
    module_name: str
    path: Path
    lineno: int
    col: int
    node: ast.AST

    raw_docstring: str | None = None
    _parsed: ParsedDocstring | None = None
    parent: Target | None = None
    decorators: tuple[str, ...] = ()
    parameters: tuple[Parameter, ...] = ()
    return_annotation: str | None = None
    docstring_end_line: int | None = None

    is_private: bool = False
    is_dunder: bool = False
    is_async: bool = False
    is_abstract: bool = False
    is_stub: bool = False
    is_overload: bool = False
    is_override: bool = False
    is_generator: bool = False
    returns_value: bool = False
    in_all: bool | None = None
    is_dataclass: bool = False
    is_nested: bool = False
    bases: tuple[str, ...] = ()
    has_unresolved_bases: bool = False

    #: Populated lazily by the runner so class-level checks can see children.
    children: list[Target] = field(default_factory=list)

    @property
    def docstring(self) -> ParsedDocstring | None:
        """
        Get the parsed docstring, parsing it on first use.

        Parsing is the most expensive work done per object, so a target that
        every rule skips never pays for it.

        Returns
        -------
        ParsedDocstring or None
            The parsed docstring, or None when there is none.
        """
        if self._parsed is None and self.raw_docstring is not None:
            self._parsed = ParsedDocstring(self.raw_docstring)
        return self._parsed

    @property
    def has_docstring(self) -> bool:
        """
        Report whether a non-empty docstring is present.

        Returns
        -------
        bool
            True when the object has a docstring.
        """
        return bool(self.raw_docstring)

    @property
    def is_placeholder(self) -> bool:
        """
        Report whether the body is abstract or a bare placeholder.

        Returns
        -------
        bool
            True when the object has no real implementation to describe.
        """
        return self.is_abstract or self.is_stub

    @property
    def is_callable(self) -> bool:
        """
        Report whether this target is a callable of some sort.

        Returns
        -------
        bool
            True for functions, methods, properties and their variants.
        """
        return self.kind in CALLABLE_KINDS

    @property
    def signature_parameters(self) -> tuple[str, ...]:
        """
        List parameter names as numpydoc would, for comparison with the docstring.

        Returns
        -------
        tuple of str
            Parameter names, starred for variadic parameters.
        """
        return tuple(p.name for p in self.parameters)

    @property
    def numpydoc_name(self) -> str:
        """
        Get the name numpydoc would address this object by.

        numpydoc roots its names at the file stem rather than the importable
        module path, so ``exclude`` patterns written for it match here too.

        Returns
        -------
        str
            The stem-rooted dotted name.
        """
        stem = self.path.stem
        if self.qualname == self.module_name:
            return stem
        if self.qualname.startswith(f"{self.module_name}."):
            return stem + self.qualname[len(self.module_name) :]
        return self.qualname

    @property
    def span(self) -> tuple[int, int]:
        """
        Get the line range the definition occupies, decorators included.

        Returns
        -------
        tuple of int
            The first and last line, inclusive.
        """
        start = self.lineno
        for decorator in getattr(self.node, "decorator_list", ()):
            start = min(start, decorator.lineno)
        end = getattr(self.node, "end_lineno", None) or start
        return start, end

    @property
    def noqa_lines(self) -> tuple[int, ...]:
        """
        List the lines on which an inline suppression applies to this target.

        A signature often spans several lines, and the natural place to write
        the comment is the line carrying the return annotation rather than the
        ``def``. Everything from the first decorator through to the first
        statement of the body counts, as does the docstring's closing line.

        Returns
        -------
        tuple of int
            Every line an inline suppression may be written on.
        """
        lines = {self.lineno, self.span[0]}
        if self.docstring_end_line is not None:
            lines.add(self.docstring_end_line)
        return tuple(sorted(lines))

    @property
    def body_start(self) -> tuple[int, int] | None:
        """
        Get the position of the first statement in the body.

        Returns
        -------
        tuple of int or None
            The line and column, or None when there is no body.
        """
        body = getattr(self.node, "body", None)
        if not body:
            return None
        return body[0].lineno, body[0].col_offset


def _decorator_name(node: ast.expr) -> str:
    """
    Render a decorator expression as a dotted name.

    Parameters
    ----------
    node : ast.expr
        The decorator expression.

    Returns
    -------
    str
        Dotted name, empty when the expression is not a name.
    """
    if isinstance(node, ast.Call):
        node = node.func
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    else:
        return ""
    return ".".join(reversed(parts))


def _unparse(node: ast.expr | None) -> str | None:
    """
    Render an AST expression back to source text.

    Parameters
    ----------
    node : ast.expr or None
        The expression to render.

    Returns
    -------
    str or None
        Source text, or None when the input was None.
    """
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - defensive
        return None


#: Node types that open a new scope, and so end the enclosing function's body.
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


def _scan_body(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[bool, bool]:
    """
    Find out in one pass whether a function yields and whether it returns a value.

    Nested functions, classes and lambdas are not descended into, so their
    returns and yields belong to them rather than to this function. Bare
    returns and ``return None`` do not count as returning a value, matching
    numpydoc.

    Parameters
    ----------
    node : ast.FunctionDef or ast.AsyncFunctionDef
        The function to inspect.

    Returns
    -------
    tuple of bool
        Whether the body yields, and whether it returns a value.
    """
    is_generator = False
    returns_value = False
    stack: list[ast.AST] = list(node.body)
    while stack:
        current = stack.pop()
        if isinstance(current, _SCOPES):
            continue
        if isinstance(current, ast.Return):
            value = current.value
            if value is not None and not (
                isinstance(value, ast.Constant) and value.value is None
            ):
                returns_value = True
                if is_generator:
                    return True, True
        elif isinstance(current, ast.Yield | ast.YieldFrom):
            is_generator = True
            if returns_value:
                return True, True
        stack.extend(ast.iter_child_nodes(current))
    return is_generator, returns_value


def _is_string_expr(stmt: ast.stmt) -> bool:
    """
    Report whether a statement is a bare string literal.

    Parameters
    ----------
    stmt : ast.stmt
        The statement to test.

    Returns
    -------
    bool
        True when the statement is a string expression, as a docstring is.
    """
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def _is_stub(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """
    Report whether a function body is only a placeholder.

    Parameters
    ----------
    node : ast.FunctionDef or ast.AsyncFunctionDef
        The function to inspect.

    Returns
    -------
    bool
        True when the body is ``pass``, ``...``, or ``raise NotImplementedError``.
    """
    body = list(node.body)
    if body and _is_string_expr(body[0]):
        body = body[1:]
    if not body:
        return True
    for stmt in body:
        if isinstance(stmt, ast.Pass):
            continue
        if (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Constant)
            and stmt.value.value is Ellipsis
        ):
            continue
        if isinstance(stmt, ast.Raise):
            exc = stmt.exc
            if isinstance(exc, ast.Call):
                exc = exc.func
            if isinstance(exc, ast.Name) and exc.id == "NotImplementedError":
                continue
        return False
    return True


def _docstring_node(node: ast.AST) -> ast.Constant | None:
    """
    Find the AST node holding an object's docstring.

    Parameters
    ----------
    node : ast.AST
        Module, class, or function node.

    Returns
    -------
    ast.Constant or None
        The string constant, when present.
    """
    body = getattr(node, "body", None)
    if not body:
        return None
    first = body[0]
    if _is_string_expr(first):
        return first.value
    return None


def _module_all(node: ast.Module) -> frozenset[str] | None:
    """
    Read a module's ``__all__`` when it is a literal sequence of strings.

    Parameters
    ----------
    node : ast.Module
        The module node.

    Returns
    -------
    frozenset of str or None
        The exported names, or None when ``__all__`` is absent or dynamic.
    """
    for stmt in node.body:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(stmt, ast.Assign):
            targets, value = stmt.targets, stmt.value
        elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
            targets, value = [stmt.target], stmt.value
        if not any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
            continue
        if isinstance(value, ast.List | ast.Tuple | ast.Set):
            names = {
                e.value
                for e in value.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            }
            return frozenset(names)
    return None


def _strip_wrapper(annotation: str | None, wrapper: str) -> str | None:
    """
    Unwrap a single-argument typing construct such as ``InitVar[int]``.

    Parameters
    ----------
    annotation : str or None
        The annotation source text.
    wrapper : str
        The construct to strip.

    Returns
    -------
    str or None
        The inner annotation, or the input unchanged.
    """
    if annotation is None:
        return None
    match = re.match(rf"^(?:\w+\.)*{wrapper}\[(.+)\]$", annotation.strip())
    return match.group(1) if match else annotation


def _is_wrapped(annotation: str | None, wrapper: str) -> bool:
    """
    Report whether an annotation is a given typing construct.

    Parameters
    ----------
    annotation : str or None
        The annotation source text.
    wrapper : str
        The construct to look for, such as ``ClassVar``.

    Returns
    -------
    bool
        True when the annotation is that construct.
    """
    if annotation is None:
        return False
    return bool(re.match(rf"^(?:\w+\.)*{wrapper}\b", annotation.strip()))


def _field_is_init_false(value: ast.expr | None) -> bool:
    """
    Report whether a default is ``field(init=False)``.

    Parameters
    ----------
    value : ast.expr or None
        The default-value expression.

    Returns
    -------
    bool
        True when the field is excluded from the constructor.
    """
    if not isinstance(value, ast.Call):
        return False
    name = _decorator_name(value.func)
    if name.rsplit(".", 1)[-1] not in ("field", "attrib", "ib"):
        return False
    for keyword in value.keywords:
        if keyword.arg == "init" and isinstance(keyword.value, ast.Constant):
            return keyword.value.value is False
    return False


def _dataclass_fields(node: ast.ClassDef) -> tuple[Parameter, ...]:
    """
    Derive the constructor parameters a dataclass decorator will synthesise.

    Annotated class attributes become parameters, in order. ``ClassVar``
    attributes and ``field(init=False)`` are excluded; ``InitVar`` is included
    and unwrapped. A bare string literal directly below a field is recorded as
    documenting it, which is how Sphinx and friends read attribute docstrings.

    Parameters
    ----------
    node : ast.ClassDef
        The decorated class.

    Returns
    -------
    tuple of Parameter
        The synthesised parameters.
    """
    params: list[Parameter] = []
    body = node.body
    for index, stmt in enumerate(body):
        if not isinstance(stmt, ast.AnnAssign) or not isinstance(stmt.target, ast.Name):
            continue
        annotation = _unparse(stmt.annotation)
        if _is_wrapped(annotation, "ClassVar"):
            continue
        if _field_is_init_false(stmt.value):
            continue
        following = body[index + 1] if index + 1 < len(body) else None
        params.append(
            Parameter(
                stmt.target.id,
                _strip_wrapper(annotation, "InitVar"),
                stmt.value is not None,
                _unparse(stmt.value),
                following is not None and _is_string_expr(following),
            )
        )
    return tuple(params)


def _signature(
    node: ast.FunctionDef | ast.AsyncFunctionDef, *, drop_first: bool
) -> tuple[Parameter, ...]:
    """
    Build the parameter list for a function.

    Parameters
    ----------
    node : ast.FunctionDef or ast.AsyncFunctionDef
        The function to inspect.
    drop_first : bool
        Whether to drop a leading ``self`` or ``cls``.

    Returns
    -------
    tuple of Parameter
        Parameters in signature order.
    """
    a = node.args
    positional = list(a.posonlyargs) + list(a.args)
    pos_defaults: list[ast.expr | None] = [None] * (
        len(positional) - len(a.defaults)
    ) + list(a.defaults)

    params: list[Parameter] = []
    for arg, default in zip(positional, pos_defaults, strict=True):
        params.append(
            Parameter(
                arg.arg,
                _unparse(arg.annotation),
                default is not None,
                _unparse(default),
            )
        )
    if a.vararg is not None:
        params.append(Parameter(f"*{a.vararg.arg}", _unparse(a.vararg.annotation)))
    for arg, default in zip(a.kwonlyargs, a.kw_defaults, strict=True):
        params.append(
            Parameter(
                arg.arg,
                _unparse(arg.annotation),
                default is not None,
                _unparse(default),
            )
        )
    if a.kwarg is not None:
        params.append(Parameter(f"**{a.kwarg.arg}", _unparse(a.kwarg.annotation)))

    if drop_first and params and params[0].name in ("self", "cls"):
        params = params[1:]
    return tuple(params)


def _child_statements(node: ast.AST):
    """
    Yield the statements nested directly inside a statement.

    Definitions can only appear in statement position, so walking statements
    alone finds every one of them without descending into expressions.

    Parameters
    ----------
    node : ast.AST
        The statement to look inside.

    Yields
    ------
    ast.stmt
        Each nested statement, including those in except and match clauses.
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.stmt):
            yield child
        elif isinstance(child, ast.ExceptHandler | ast.match_case):
            yield from child.body


class TargetCollector:
    """
    Walk a module and collect every documentable object.

    Parameters
    ----------
    path : pathlib.Path
        The file being walked.
    module_name : str
        Name to use as the root of every qualified name.
    property_decorators : tuple of str
        Decorator names that mark a read-only property.
    dataclass_decorators : tuple of str
        Decorator names that synthesise a constructor from class attributes.
    """

    def __init__(
        self,
        path: Path,
        module_name: str,
        property_decorators: tuple[str, ...] = DEFAULT_PROPERTY_DECORATORS,
        dataclass_decorators: tuple[str, ...] = DEFAULT_DATACLASS_DECORATORS,
    ) -> None:
        self.path = path
        self.module_name = module_name
        self.property_decorators = frozenset(property_decorators)
        self.dataclass_decorators = frozenset(dataclass_decorators)
        self.targets: list[Target] = []
        self._stack: list[Target] = []
        self._all: frozenset[str] | None = None

    def collect(self, tree: ast.Module) -> list[Target]:
        """
        Collect every target in a parsed module.

        Parameters
        ----------
        tree : ast.Module
            The parsed module.

        Returns
        -------
        list of Target
            Targets in source order, module first.
        """
        self._all = _module_all(tree)
        module = self._make_module(tree)
        self.targets.append(module)
        self._stack.append(module)
        self._visit_body(tree.body)
        self._stack.pop()
        self._resolve_dataclass_bases()
        return self.targets

    def _resolve_dataclass_bases(self) -> None:
        """
        Merge inherited fields into each dataclass in the file.

        Fields declared by a base class come first, matching the order the
        decorator itself uses. A base that is not defined in this file cannot
        be resolved, which is recorded so that rules can stay conservative.
        """
        classes = {t.name: t for t in self.targets if t.kind is Kind.CLASS}

        def resolve(target: Target, seen: frozenset[str]) -> tuple[
            tuple[Parameter, ...], bool
        ]:
            if target.name in seen:
                return target.parameters, target.has_unresolved_bases
            seen = seen | {target.name}
            inherited: list[Parameter] = []
            unresolved = False
            for base in target.bases:
                simple = base.rsplit(".", 1)[-1]
                if base in _INERT_BASES or simple in _INERT_BASES:
                    continue
                parent = classes.get(simple)
                if parent is None:
                    unresolved = True
                    continue
                parent_params, parent_unresolved = resolve(parent, seen)
                unresolved = unresolved or parent_unresolved
                inherited.extend(parent_params)
            own = {p.name for p in target.parameters}
            merged = [p for p in inherited if p.name not in own] + list(
                target.parameters
            )
            return tuple(merged), unresolved

        for target in self.targets:
            if target.kind is Kind.CLASS and target.is_dataclass:
                target.parameters, target.has_unresolved_bases = resolve(
                    target, frozenset()
                )

    # -- construction ---------------------------------------------------------

    def _visit_body(self, body: list[ast.stmt]) -> None:
        """
        Walk a list of statements, recording every definition found.

        Parameters
        ----------
        body : list of ast.stmt
            Statements to walk.
        """
        for stmt in body:
            if isinstance(stmt, ast.ClassDef):
                self.visit_ClassDef(stmt)
            elif isinstance(stmt, ast.FunctionDef):
                self._visit_function(stmt, is_async=False)
            elif isinstance(stmt, ast.AsyncFunctionDef):
                self._visit_function(stmt, is_async=True)
            else:
                self._visit_body(list(_child_statements(stmt)))

    def _inside_function(self) -> bool:
        """
        Report whether the collector is currently inside a function body.

        Returns
        -------
        bool
            True when any enclosing target is a callable.
        """
        return any(t.kind in CALLABLE_KINDS for t in self._stack)

    def _attach(self, target: Target) -> None:
        if self._stack:
            parent = self._stack[-1]
            target.parent = parent
            parent.children.append(target)
        self.targets.append(target)

    def _docstring_fields(self, node: ast.AST) -> tuple[str | None, int | None]:
        """
        Find a node's docstring text and the line its quotes close on.

        Parameters
        ----------
        node : ast.AST
            Module, class, or function node.

        Returns
        -------
        tuple
            The raw docstring and its closing line, both None when absent.
        """
        const = _docstring_node(node)
        if const is None:
            return None, None
        raw = ast.get_docstring(node, clean=False)
        if raw is None:
            return None, None
        return raw, const.end_lineno

    def _make_module(self, node: ast.Module) -> Target:
        raw, end = self._docstring_fields(node)
        return Target(
            kind=Kind.MODULE,
            name=self.module_name,
            qualname=self.module_name,
            module_name=self.module_name,
            path=self.path,
            lineno=1,
            col=1,
            node=node,
            raw_docstring=raw,
            docstring_end_line=end,
            is_private=self.module_name.startswith("_")
            and not self.module_name.startswith("__"),
        )

    def _classify(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, decorators: tuple[str, ...]
    ) -> Kind:
        in_class = bool(self._stack) and self._stack[-1].kind is Kind.CLASS
        if not in_class:
            return Kind.FUNCTION
        for dec in decorators:
            if dec in self.property_decorators:
                return Kind.PROPERTY
            if dec.endswith(".setter") or dec.endswith(".deleter"):
                return Kind.SETTER
            if dec == "classmethod":
                return Kind.CLASSMETHOD
            if dec == "staticmethod":
                return Kind.STATICMETHOD
        return Kind.METHOD

    # -- visitors -------------------------------------------------------------

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        """
        Record a class and descend into its body.

        Parameters
        ----------
        node : ast.ClassDef
            The class node.
        """
        raw, end = self._docstring_fields(node)
        qual = (
            f"{self._stack[-1].qualname}.{node.name}" if self._stack else node.name
        )
        init = next(
            (
                c
                for c in node.body
                if isinstance(c, ast.FunctionDef | ast.AsyncFunctionDef)
                and c.name == "__init__"
            ),
            None,
        )
        decorators = tuple(_decorator_name(d) for d in node.decorator_list)
        bases = tuple(_decorator_name(b) for b in node.bases)
        is_dataclass = bool(self.dataclass_decorators & set(decorators))
        if init is not None:
            parameters = _signature(init, drop_first=True)
        elif is_dataclass:
            parameters = _dataclass_fields(node)
        else:
            parameters = ()
        target = Target(
            kind=Kind.CLASS,
            name=node.name,
            qualname=qual,
            module_name=self.module_name,
            path=self.path,
            lineno=node.lineno,
            col=node.col_offset + 1,
            node=node,
            raw_docstring=raw,
            docstring_end_line=end,
            decorators=decorators,
            parameters=parameters,
            is_private=node.name.startswith("_") and not node.name.startswith("__"),
            in_all=None if self._all is None else node.name in self._all,
            is_dataclass=is_dataclass,
            bases=bases,
            is_nested=self._inside_function(),
        )
        self._attach(target)
        self._stack.append(target)
        self._visit_body(node.body)
        self._stack.pop()

    def _visit_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, *, is_async: bool
    ) -> None:
        decorators = tuple(_decorator_name(d) for d in node.decorator_list)
        kind = self._classify(node, decorators)
        is_generator, returns_value = _scan_body(node)
        raw, end = self._docstring_fields(node)
        qual = (
            f"{self._stack[-1].qualname}.{node.name}" if self._stack else node.name
        )
        in_class = kind in METHOD_KINDS
        target = Target(
            kind=kind,
            name=node.name,
            qualname=qual,
            module_name=self.module_name,
            path=self.path,
            lineno=node.lineno,
            col=node.col_offset + 1,
            node=node,
            raw_docstring=raw,
            docstring_end_line=end,
            decorators=decorators,
            parameters=_signature(
                node, drop_first=in_class and kind is not Kind.STATICMETHOD
            ),
            return_annotation=_unparse(node.returns),
            is_private=node.name.startswith("_") and not node.name.startswith("__"),
            is_dunder=node.name.startswith("__") and node.name.endswith("__"),
            is_async=is_async,
            is_abstract=bool(_ABSTRACT_DECORATORS & set(decorators)),
            is_stub=_is_stub(node),
            is_overload=bool(_OVERLOAD_DECORATORS & set(decorators)),
            is_override=bool(_OVERRIDE_DECORATORS & set(decorators)),
            is_generator=is_generator,
            returns_value=returns_value,
            in_all=None if self._all is None else node.name in self._all,
            is_nested=self._inside_function(),
        )
        self._attach(target)
        self._stack.append(target)
        self._visit_body(node.body)
        self._stack.pop()



def collect_targets(
    tree: ast.Module,
    path: Path,
    module_name: str,
    property_decorators: tuple[str, ...] = DEFAULT_PROPERTY_DECORATORS,
    dataclass_decorators: tuple[str, ...] = DEFAULT_DATACLASS_DECORATORS,
) -> list[Target]:
    """
    Collect every documentable object in a parsed module.

    Parameters
    ----------
    tree : ast.Module
        The parsed module.
    path : pathlib.Path
        The file the module came from.
    module_name : str
        Name to use as the root of every qualified name.
    property_decorators : tuple of str
        Decorator names that mark a read-only property.
    dataclass_decorators : tuple of str
        Decorator names that synthesise a constructor from class attributes.

    Returns
    -------
    list of Target
        Targets in source order.
    """
    return TargetCollector(
        path, module_name, property_decorators, dataclass_decorators
    ).collect(tree)
