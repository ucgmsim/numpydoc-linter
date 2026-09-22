"""Property docstring conventions: the PT family.

numpydoc has no opinion about properties; its AST hook does not look at
decorators at all, so a ``@property`` is validated as an ordinary function and
is told to grow a Returns section. Many projects instead write the one-line
form ``float: The radius in metres.`` These rules make the convention a
configurable choice rather than a fork.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from numpydoc_linter.diagnostics import Diagnostic
from numpydoc_linter.rules.base import BaseRule, Context, registry
from numpydoc_linter.rules.messages import render
from numpydoc_linter.targets import Kind, Target

#: Configuration key selecting the expected shape of a property docstring.
OPTION = "property-form"

#: The form assumed when nothing is configured: plain numpydoc.
DEFAULT_FORM = "returns-section"

_TYPE_LINE_RE = re.compile(r"^(?P<type>[^:\n]+):[ \t]+(?P<summary>\S.*)$")

_BUILTIN_FORMS: dict[str, PropertyForm] = {}


@dataclass(frozen=True, slots=True)
class PropertyForm:
    """
    An expected shape for a property docstring.

    Parameters
    ----------
    name : str
        The form's name, as written in configuration.
    pattern : re.Pattern or None
        Pattern the first line must match, or None to impose no shape.
    expected : str
        Human-readable description of the shape, used in messages.
    forbidden_sections : tuple of str
        Sections that this form does not use.
    """

    name: str
    pattern: re.Pattern[str] | None
    expected: str
    forbidden_sections: tuple[str, ...] = ()


def _register(form: PropertyForm) -> PropertyForm:
    _BUILTIN_FORMS[form.name] = form
    return form


_register(
    PropertyForm(
        name="returns-section",
        pattern=None,
        expected="an ordinary numpydoc docstring",
    )
)
_register(
    PropertyForm(
        name="type-line",
        pattern=_TYPE_LINE_RE,
        expected="<type>: <summary>",
        forbidden_sections=("Parameters", "Returns", "Yields"),
    )
)
_register(
    PropertyForm(
        name="summary-only",
        pattern=re.compile(r"^(?P<summary>\S.*)$"),
        expected="<summary>, with no type",
        forbidden_sections=("Parameters", "Returns", "Yields"),
    )
)


class PropertyFormError(ValueError):
    """Raised when ``property-form`` is configured with an unusable value."""


def resolve_form(value: object) -> PropertyForm:
    """
    Turn a configured value into a :class:`PropertyForm`.

    Parameters
    ----------
    value : object
        Either the name of a built-in form, or a table with a ``regex`` key.

    Returns
    -------
    PropertyForm
        The resolved form.

    Raises
    ------
    PropertyFormError
        When the value names no built-in form and carries no usable regex.
    """
    if value is None:
        return _BUILTIN_FORMS[DEFAULT_FORM]
    if isinstance(value, PropertyForm):
        return value
    if isinstance(value, str):
        try:
            return _BUILTIN_FORMS[value]
        except KeyError:
            raise PropertyFormError(
                f"unknown property-form {value!r}; expected one of "
                f"{', '.join(sorted(_BUILTIN_FORMS))}, or a table with a 'regex' key"
            ) from None
    if isinstance(value, dict) and "regex" in value:
        try:
            pattern = re.compile(str(value["regex"]))
        except re.error as exc:
            raise PropertyFormError(f"invalid property-form regex: {exc}") from exc
        return PropertyForm(
            name="custom",
            pattern=pattern,
            expected=str(value.get("description", value["regex"])),
            forbidden_sections=tuple(value.get("forbidden-sections", ())),
        )
    raise PropertyFormError(f"could not read property-form from {value!r}")


def _first_line(raw: str) -> str:
    """
    Take the first non-blank line of a docstring.

    Parameters
    ----------
    raw : str
        The raw docstring.

    Returns
    -------
    str
        The first non-blank line, stripped.
    """
    for line in raw.splitlines():
        if line.strip():
            return line.strip()
    return ""


def _normalise_type(text: str) -> str:
    """
    Reduce a type expression to a comparable form.

    Unions written either way, optionals, quoted forward references and
    whitespace all collapse to the same spelling.

    Parameters
    ----------
    text : str
        The type expression.

    Returns
    -------
    str
        A normalised spelling.
    """
    t = text.strip().strip("`").strip()
    t = re.sub(r"^(typing|t)\.", "", t)
    t = re.sub(r"\bOptional\[(.+)\]$", r"\1 | None", t)
    t = re.sub(r"\bUnion\[(.+)\]$", lambda m: m.group(1).replace(",", "|"), t)
    t = t.replace(" or ", "|")
    t = re.sub(r"['\"]", "", t)
    t = re.sub(r"\s+", "", t)
    return t.lower()


def effective_summary(target: Target, ctx: Context) -> str:
    """
    Get the part of a docstring that reads as the summary.

    Under a property form that puts a type before the summary, the summary
    checks should look past the type, so that ``float: The radius.`` is not
    reported as starting with a lower-case letter.

    Parameters
    ----------
    target : Target
        The object being checked.
    ctx : Context
        Shared state for the file.

    Returns
    -------
    str
        The text the summary rules should judge.
    """
    doc = target.docstring
    if doc is None:
        return ""
    if target.kind is not Kind.PROPERTY:
        return doc.summary
    form = resolve_form(ctx.option(OPTION))
    if form.pattern is None:
        return doc.summary
    match = form.pattern.match(_first_line(doc.raw))
    if match is None:
        return doc.summary
    groups = match.groupdict() or {}
    if "summary" not in groups or groups["summary"] is None:
        return doc.summary
    summary = groups["summary"]
    # A summary continued onto later lines is still one summary.
    rest = doc.summary
    first = _first_line(doc.raw)
    if rest.startswith(first) and len(rest) > len(first):
        summary += rest[len(first) :]
    return summary


#: Words that carry no type information in a documented type.
_NOISE_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "default",
        "dtype",
        "of",
        "optional",
        "or",
        "shape",
        "the",
        "with",
    }
)


def _type_tokens(text: str) -> frozenset[str]:
    """
    Reduce a type expression to the identifiers it names.

    Parameters
    ----------
    text : str
        The type expression.

    Returns
    -------
    frozenset of str
        Lower-cased identifiers, with punctuation and filler words removed.
    """
    # Tokenise before the whitespace-collapsing normalisation, which would
    # otherwise run adjacent words together into one identifier.
    cleaned = re.sub(r"['\"`]", "", text)
    cleaned = re.sub(r"^\s*(typing|t)\.", "", cleaned)
    tokens = re.findall(r"[A-Za-z_][\w]*(?:\.[A-Za-z_]\w*)*", cleaned)
    return frozenset(
        token.lower()
        for token in tokens
        if token.lower() not in _NOISE_WORDS
    )


def types_agree(documented: str, annotated: str) -> bool:
    """
    Decide whether a documented type is consistent with an annotation.

    numpydoc encourages types that say more than the annotation does, such as
    ``np.ndarray of shape (n, 3)`` or ``float, optional``. A documented type is
    accepted when it names everything the annotation names; it may add detail
    but it may not describe a different type.

    Parameters
    ----------
    documented : str
        The type written in the docstring.
    annotated : str
        The return annotation.

    Returns
    -------
    bool
        True when the two are consistent.
    """
    if _normalise_type(documented) == _normalise_type(annotated):
        return True
    annotation_tokens = _type_tokens(annotated)
    if not annotation_tokens:
        return True
    return annotation_tokens <= _type_tokens(documented)


class _PropertyRule(BaseRule):
    """Shared base for the property-form rules."""

    kinds = frozenset({Kind.PROPERTY})
    options = (OPTION,)

    @staticmethod
    def form(ctx: Context) -> PropertyForm:
        """
        Read the property form in force for this target.

        Parameters
        ----------
        ctx : Context
            Shared state for the file.

        Returns
        -------
        PropertyForm
            The configured form.
        """
        return resolve_form(ctx.option(OPTION))


@registry.register
class PropertyFormMismatch(_PropertyRule):
    """PT01: the property docstring does not match the configured form."""

    code = "PT01"
    name = "property-form-mismatch"
    summary = "Property docstrings should follow the configured form."

    def check(self, target: Target, ctx: Context) -> Iterable[Diagnostic]:
        """
        Match the first line of the docstring against the form.

        Parameters
        ----------
        target : Target
            The object being checked.
        ctx : Context
            Shared state for the file.

        Yields
        ------
        Diagnostic
            One when the first line does not match.
        """
        form = self.form(ctx)
        if form.pattern is None:
            return
        doc = target.docstring
        assert doc is not None
        if not form.pattern.match(_first_line(doc.raw)):
            yield self.diagnostic(
                target, render(self.code, form=form.name, expected=form.expected)
            )


@registry.register
class PropertyTypeMismatch(_PropertyRule):
    """PT02: the documented type disagrees with the return annotation."""

    code = "PT02"
    name = "property-type-mismatch"
    summary = "A documented property type should match its return annotation."

    def check(self, target: Target, ctx: Context) -> Iterable[Diagnostic]:
        """
        Compare the documented type with the return annotation.

        Only fires when the form captures a type and the property is annotated.

        Parameters
        ----------
        target : Target
            The object being checked.
        ctx : Context
            Shared state for the file.

        Yields
        ------
        Diagnostic
            One when the two disagree.
        """
        form = self.form(ctx)
        if form.pattern is None or target.return_annotation is None:
            return
        doc = target.docstring
        assert doc is not None
        match = form.pattern.match(_first_line(doc.raw))
        if match is None or "type" not in (match.groupdict() or {}):
            return
        documented = match.group("type")
        if documented is None:
            return
        if not types_agree(documented, target.return_annotation):
            yield self.diagnostic(
                target,
                render(
                    self.code,
                    documented=documented.strip(),
                    annotated=target.return_annotation,
                ),
            )


@registry.register
class PropertyForbiddenSection(_PropertyRule):
    """PT03: the property docstring uses a section the form does not."""

    code = "PT03"
    name = "property-forbidden-section"
    summary = "Property docstrings should not carry sections the form omits."

    def check(self, target: Target, ctx: Context) -> Iterable[Diagnostic]:
        """
        Look for sections that the configured form does not use.

        Parameters
        ----------
        target : Target
            The object being checked.
        ctx : Context
            Shared state for the file.

        Yields
        ------
        Diagnostic
            One per forbidden section present.
        """
        form = self.form(ctx)
        if not form.forbidden_sections:
            return
        doc = target.docstring
        assert doc is not None
        present = set(doc.section_titles)
        for section in form.forbidden_sections:
            if section in present:
                yield self.diagnostic(
                    target, render(self.code, section=section, form=form.name)
                )
