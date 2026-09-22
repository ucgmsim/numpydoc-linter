"""The rule protocol, the registry, and the context rules receive."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, runtime_checkable

from npdlint.diagnostics import Diagnostic
from npdlint.targets import Kind, Target

if TYPE_CHECKING:  # pragma: no cover
    from npdlint.source import SourceFile, SuppressionUsage


@dataclass(slots=True)
class Context:
    """
    Everything a rule may look at besides its target.

    Parameters
    ----------
    source : SourceFile
        The parsed file the target came from.
    options : dict
        Rule options in force for this target, after scope resolution.
    targets_by_qualname : dict
        Every target in the file, keyed by qualified name.
    usage : SuppressionUsage or None
        What each inline suppression in the file did, filled in by the runner
        and only when a file-level rule asked for it.
    """

    source: SourceFile
    options: dict[str, Any] = field(default_factory=dict)
    targets_by_qualname: dict[str, Target] = field(default_factory=dict)
    usage: SuppressionUsage | None = None

    def option(self, name: str, default: Any = None) -> Any:
        """
        Read one rule option.

        Parameters
        ----------
        name : str
            Option name as written in configuration.
        default : Any
            Value to return when the option is unset.

        Returns
        -------
        Any
            The configured value, or the default.
        """
        return self.options.get(name, default)


@runtime_checkable
class Rule(Protocol):
    """A single check, addressed by its code."""

    code: ClassVar[str]
    name: ClassVar[str]
    summary: ClassVar[str]
    kinds: ClassVar[frozenset[Kind]]
    requires_docstring: ClassVar[bool]
    options: ClassVar[tuple[str, ...]]
    per_file: ClassVar[bool]

    def check(self, target: Target, ctx: Context) -> Iterable[Diagnostic]:
        """
        Run the check against one target.

        Parameters
        ----------
        target : Target
            The object being checked.
        ctx : Context
            Shared state for the file.

        Yields
        ------
        Diagnostic
            One per violation.
        """
        ...


class BaseRule:
    """
    Convenience base implementing the boilerplate of :class:`Rule`.

    Subclasses set ``code``, ``name``, ``summary``, ``kinds``, and implement
    ``check``.
    """

    code: ClassVar[str] = ""
    name: ClassVar[str] = ""
    summary: ClassVar[str] = ""
    kinds: ClassVar[frozenset[Kind]] = frozenset(Kind)
    requires_docstring: ClassVar[bool] = True
    #: Configuration keys this rule reads from its scope.
    options: ClassVar[tuple[str, ...]] = ()
    #: Whether the rule runs once per file instead of once per target.
    per_file: ClassVar[bool] = False

    def check(  # pragma: no cover
        self, target: Target, ctx: Context
    ) -> Iterable[Diagnostic]:
        """
        Run the check against one target.

        Parameters
        ----------
        target : Target
            The object being checked.
        ctx : Context
            Shared state for the file.

        Yields
        ------
        Diagnostic
            One per violation.
        """
        raise NotImplementedError

    def diagnostic(self, target: Target, message: str) -> Diagnostic:
        """
        Build a diagnostic anchored at a target.

        Parameters
        ----------
        target : Target
            The object being reported on.
        message : str
            The rendered message.

        Returns
        -------
        Diagnostic
            The diagnostic record.
        """
        return Diagnostic(
            code=self.code,
            message=message,
            path=target.path,
            line=target.lineno,
            col=target.col,
            qualname=target.qualname,
            kind=str(target.kind),
        )


class BaseFileRule(BaseRule):
    """
    Convenience base for a rule that looks at the file rather than an object.

    A file-level rule runs once, after every target has been checked, so it
    can see what the other rules did. It is selected and ignored by code like
    any other rule, but takes its rule set from the global selection and the
    file's ``per-file-ignores`` only: scope blocks match objects, and a file
    is not one.
    """

    kinds: ClassVar[frozenset[Kind]] = frozenset()
    requires_docstring: ClassVar[bool] = False
    per_file: ClassVar[bool] = True

    def check(self, target: Target, ctx: Context) -> Iterable[Diagnostic]:
        """
        Never run; a file-level rule is dispatched through ``check_file``.

        Parameters
        ----------
        target : Target
            The object being checked.
        ctx : Context
            Shared state for the file.

        Returns
        -------
        tuple
            Always empty.
        """
        return ()

    def check_file(self, ctx: Context) -> Iterable[Diagnostic]:  # pragma: no cover
        """
        Run the check against one file.

        Parameters
        ----------
        ctx : Context
            Shared state for the file.

        Yields
        ------
        Diagnostic
            One per violation.
        """
        raise NotImplementedError

    def at(self, ctx: Context, line: int, col: int, message: str) -> Diagnostic:
        """
        Build a diagnostic anchored at a position in the file.

        Parameters
        ----------
        ctx : Context
            Shared state for the file.
        line : int
            One-based line number.
        col : int
            One-based column number.
        message : str
            The rendered message.

        Returns
        -------
        Diagnostic
            The diagnostic record.
        """
        return Diagnostic(
            code=self.code,
            message=message,
            path=ctx.source.path,
            line=line,
            col=col,
        )


class Registry:
    """A mutable collection of rules, keyed by code."""

    def __init__(self) -> None:
        self._rules: dict[str, Rule] = {}

    def register(self, rule_cls: type) -> type:
        """
        Register a rule class, instantiating it.

        Intended for use as a decorator.

        Parameters
        ----------
        rule_cls : type
            The rule class to register.

        Returns
        -------
        type
            The class, unchanged.

        Raises
        ------
        ValueError
            If the code is missing or already registered.
        """
        rule = rule_cls()
        code = rule.code
        if not code:
            raise ValueError(f"{rule_cls.__name__} has no code")
        if code in self._rules:
            raise ValueError(f"duplicate rule code {code!r}")
        self._rules[code] = rule
        return rule_cls

    def add(self, rule: Rule) -> None:
        """
        Register an already-constructed rule.

        Parameters
        ----------
        rule : Rule
            The rule instance.

        Raises
        ------
        ValueError
            If the code is already registered.
        """
        if rule.code in self._rules:
            raise ValueError(f"duplicate rule code {rule.code!r}")
        self._rules[rule.code] = rule

    def get(self, code: str) -> Rule | None:
        """
        Look up one rule.

        Parameters
        ----------
        code : str
            The rule code.

        Returns
        -------
        Rule or None
            The rule, when registered.
        """
        return self._rules.get(code)

    def option_keys(self) -> frozenset[str]:
        """
        List every option key any registered rule reads.

        Returns
        -------
        frozenset of str
            Legal rule-option names.
        """
        keys: set[str] = set()
        for rule in self._rules.values():
            keys.update(getattr(rule, "options", ()))
        return frozenset(keys)

    def codes(self) -> tuple[str, ...]:
        """
        List every registered code, sorted.

        Returns
        -------
        tuple of str
            All known rule codes.
        """
        return tuple(sorted(self._rules))

    def all(self) -> tuple[Rule, ...]:
        """
        List every registered rule, ordered by code.

        Returns
        -------
        tuple of Rule
            All registered rules.
        """
        return tuple(self._rules[c] for c in self.codes())

    def __contains__(self, code: object) -> bool:
        """
        Report whether a code is registered.

        Parameters
        ----------
        code : object
            The code to look for.

        Returns
        -------
        bool
            True when registered.
        """
        return code in self._rules


#: The registry every built-in rule registers itself with.
registry = Registry()
