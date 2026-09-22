"""Parameter documentation checks: the PR family."""

from __future__ import annotations

import re
from collections.abc import Iterable

from npdlint.diagnostics import Diagnostic
from npdlint.docstring import check_description
from npdlint.rules.base import BaseRule, Context, registry
from npdlint.rules.messages import render
from npdlint.targets import Target

#: Configuration key controlling whether private parameters need documenting.
PRIVATE_OPTION = "private-parameters"

#: The default, which is numpydoc's behaviour.
DEFAULT_PRIVATE = "document"


def _is_private_param(name: str) -> bool:
    """
    Report whether a parameter name marks it as private.

    Parameters
    ----------
    name : str
        The parameter name, possibly starred.

    Returns
    -------
    bool
        True when the name starts with an underscore.
    """
    return name.lstrip("*").startswith("_")


def fields_section(ctx: Context) -> str:
    """
    Read where a dataclass is allowed to document its fields.

    Parameters
    ----------
    ctx : Context
        Shared state for the file.

    Returns
    -------
    str
        The configured section policy.
    """
    return ctx.option(FIELDS_SECTION_OPTION, DEFAULT_FIELDS_SECTION)


def ignoring_private(ctx: Context) -> bool:
    """
    Read whether private parameters are exempt for this target.

    Parameters
    ----------
    ctx : Context
        Shared state for the file.

    Returns
    -------
    bool
        True when private parameters should be skipped entirely.
    """
    return ctx.option(PRIVATE_OPTION, DEFAULT_PRIVATE) == "ignore"


#: Configuration key for where a dataclass may document its fields.
FIELDS_SECTION_OPTION = "dataclass-fields-section"

#: The default: a field counts as documented in either section.
DEFAULT_FIELDS_SECTION = "either"


#: Prose type names that should be spelled as the Python type.
COMMON_TYPE_ERRORS = (("integer", "int"), ("boolean", "bool"), ("string", "str"))


def _fmt(names: Iterable[str]) -> str:
    """
    Render a collection of parameter names deterministically.

    numpydoc interpolates a raw ``set`` here, so its message ordering varies
    between runs. Sorting makes output stable and diffable.

    Parameters
    ----------
    names : iterable of str
        Parameter names.

    Returns
    -------
    str
        A brace-wrapped, sorted, quoted list.
    """
    return "{" + ", ".join(repr(n) for n in sorted(names)) + "}"


def parameter_mismatches(
    target: Target,
    ignore_private: bool = False,
    fields_section: str = DEFAULT_FIELDS_SECTION,
) -> list[tuple[str, dict[str, object]]]:
    """
    Compare the signature with the documented parameters.

    Parameters
    ----------
    target : Target
        The object being checked.
    ignore_private : bool
        Whether to drop underscore-prefixed names from both sides first.
    fields_section : str
        Where a dataclass may document its fields. ``"either"``, the default,
        accepts the Parameters section, the Attributes section, or an inline
        attribute docstring. ``"parameters"`` accepts only the Parameters
        section, as numpydoc does.

    Returns
    -------
    list
        Pairs of code and message-formatting arguments for PR01, PR02 and PR03.
    """
    doc = target.docstring
    if doc is None:
        return []
    errs: list[tuple[str, dict[str, object]]] = []
    signature_params = target.signature_parameters
    all_params = tuple(p.replace("\\", "") for p in doc.doc_all_parameters)
    if ignore_private:
        signature_params = tuple(
            p for p in signature_params if not _is_private_param(p)
        )
        all_params = tuple(p for p in all_params if not _is_private_param(p))

    # A dataclass field is an attribute as much as it is a constructor
    # parameter, and documenting it under Attributes is the usual convention.
    # Such a name counts as documented, but it is not treated as a declared
    # parameter, so it cannot make the parameter list unknown or out of order.
    documented = set(all_params)
    if target.is_dataclass and fields_section != "parameters":
        documented |= set(doc.doc_attributes)
        documented |= {p.name for p in target.parameters if p.has_inline_doc}

    missing = set(signature_params) - documented
    if missing:
        errs.append(("PR01", {"missing_params": _fmt(missing)}))
    extra = set(all_params) - set(signature_params)
    # A dataclass base defined outside this file may contribute fields we
    # cannot see, so documented-but-unknown names are not provably wrong, and
    # neither is the order they appear in.
    forgiven = bool(extra) and target.has_unresolved_bases
    if forgiven:
        extra = set()
    if extra:
        errs.append(("PR02", {"unknown_params": _fmt(extra)}))
    # Order is only meaningful for names written in the Parameters section.
    # Fields documented as attributes have no position to be wrong about.
    ordered = tuple(p for p in signature_params if p in set(all_params))
    if (
        not missing
        and not extra
        and not forgiven
        and ordered != all_params
        and not (not ordered and not all_params)
    ):
        errs.append(
            (
                "PR03",
                {"actual_params": ordered, "documented_params": all_params},
            )
        )
    return errs


class _MismatchRule(BaseRule):
    """Shared base for the three signature-versus-docstring checks."""

    options = (PRIVATE_OPTION, FIELDS_SECTION_OPTION)

    def check(self, target: Target, ctx: Context) -> Iterable[Diagnostic]:
        """
        Emit this rule's share of the signature comparison.

        Parameters
        ----------
        target : Target
            The object being checked.
        ctx : Context
            Shared state for the file.

        Yields
        ------
        Diagnostic
            One per mismatch of this rule's code.
        """
        for code, kwargs in parameter_mismatches(
            target, ignoring_private(ctx), fields_section(ctx)
        ):
            if code == self.code:
                yield self.diagnostic(target, render(code, **kwargs))


@registry.register
class UndocumentedParameters(_MismatchRule):
    """PR01: a signature parameter is missing from the docstring."""

    code = "PR01"
    name = "undocumented-parameters"
    summary = "Every signature parameter should be documented."


@registry.register
class UnknownParameters(_MismatchRule):
    """PR02: the docstring documents something not in the signature."""

    code = "PR02"
    name = "unknown-parameters"
    summary = "Documented parameters should exist in the signature."


@registry.register
class ParameterOrder(_MismatchRule):
    """PR03: documented parameters are in a different order to the signature."""

    code = "PR03"
    name = "parameter-order"
    summary = "Documented parameters should follow signature order."


class _PerParameterRule(BaseRule):
    """Shared base for checks that visit each documented parameter."""

    options = (PRIVATE_OPTION, FIELDS_SECTION_OPTION)

    def _check_one(
        self, name: str, type_: str, desc: list[str], target: Target
    ) -> Iterable[Diagnostic]:  # pragma: no cover - overridden
        raise NotImplementedError

    def check(self, target: Target, ctx: Context) -> Iterable[Diagnostic]:
        """
        Visit each documented parameter.

        Parameters
        ----------
        target : Target
            The object being checked.
        ctx : Context
            Shared state for the file.

        Yields
        ------
        Diagnostic
            One per offending parameter.
        """
        doc = target.docstring
        assert doc is not None
        skip_private = ignoring_private(ctx)
        for name, (type_, desc) in doc.doc_all_parameters.items():
            if skip_private and _is_private_param(name):
                continue
            yield from self._check_one(name, type_, desc, target)


@registry.register
class ParameterHasNoType(_PerParameterRule):
    """PR04: a documented parameter has no type."""

    code = "PR04"
    name = "parameter-has-no-type"
    summary = "Documented parameters should declare a type."

    def _check_one(self, name, type_, desc, target):
        if name.startswith("*") or ":" in name:
            return
        if not type_:
            yield self.diagnostic(target, render(self.code, param_name=name))


@registry.register
class ParameterTypeTrailingPeriod(_PerParameterRule):
    """PR05: a parameter type ends with a period."""

    code = "PR05"
    name = "parameter-type-trailing-period"
    summary = "Parameter types should not end with a period."

    def _check_one(self, name, type_, desc, target):
        if name.startswith("*") or not type_:
            return
        if type_[-1] == ".":
            yield self.diagnostic(target, render(self.code, param_name=name))


@registry.register
class ParameterTypeSpelling(_PerParameterRule):
    """PR06: a parameter type uses prose instead of the Python type name."""

    code = "PR06"
    name = "parameter-type-spelling"
    summary = 'Use "int", "bool" and "str" rather than prose type names.'

    def _check_one(self, name, type_, desc, target):
        if name.startswith("*") or not type_ or "{" in type_:
            return
        words = set(re.split(r"\W", type_))
        for wrong_type, right_type in COMMON_TYPE_ERRORS:
            if wrong_type in words:
                yield self.diagnostic(
                    target,
                    render(
                        self.code,
                        param_name=name,
                        right_type=right_type,
                        wrong_type=wrong_type,
                    ),
                )


@registry.register
class ParameterMissingColonSpace(_PerParameterRule):
    """PR10: the colon separating name and type needs a leading space."""

    code = "PR10"
    name = "parameter-missing-colon-space"
    summary = "Put a space before the colon separating name and type."

    def _check_one(self, name, type_, desc, target):
        if name.startswith("*") or type_:
            return
        if ":" in name:
            yield self.diagnostic(
                target, render(self.code, param_name=name.split(":")[0])
            )


class _ParameterDescRule(_PerParameterRule):
    """Shared base for the parameter description checks."""

    def _check_one(self, name, type_, desc, target):
        for code, kwargs in check_description(
            desc, "PR07", "PR08", "PR09", param_name=name
        ):
            if code == self.code:
                yield self.diagnostic(target, render(code, **kwargs))


@registry.register
class ParameterHasNoDescription(_ParameterDescRule):
    """PR07: a documented parameter has no description."""

    code = "PR07"
    name = "parameter-has-no-description"
    summary = "Every documented parameter should have a description."


@registry.register
class ParameterDescriptionCapitalised(_ParameterDescRule):
    """PR08: a parameter description is not capitalised."""

    code = "PR08"
    name = "parameter-description-capitalised"
    summary = "Parameter descriptions should start with a capital letter."


@registry.register
class ParameterDescriptionPeriod(_ParameterDescRule):
    """PR09: a parameter description does not end with a period."""

    code = "PR09"
    name = "parameter-description-period"
    summary = "Parameter descriptions should end with a period."
