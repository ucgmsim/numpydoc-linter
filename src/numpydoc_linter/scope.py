"""Work out which rules apply to a given target."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from numpydoc_linter import selection
from numpydoc_linter.config import ScopeBlock, Settings, _regex, _spec
from numpydoc_linter.targets import Target


@dataclass(slots=True)
class ResolutionStep:
    """
    One layer of the resolution, kept so ``explain`` can show its working.

    Parameters
    ----------
    label : str
        Human-readable name of the layer.
    enabled : frozenset of str
        Codes enabled after this layer.
    added : frozenset of str
        Codes this layer turned on.
    removed : frozenset of str
        Codes this layer turned off.
    """

    label: str
    enabled: frozenset[str]
    added: frozenset[str] = frozenset()
    removed: frozenset[str] = frozenset()


@dataclass(slots=True)
class Resolution:
    """
    The rules and options in force for one target.

    Parameters
    ----------
    enabled : frozenset of str
        Rule codes to run.
    options : dict
        Rule options, after scope overrides.
    steps : list of ResolutionStep
        How the set was arrived at.
    """

    enabled: frozenset[str]
    options: dict[str, Any] = field(default_factory=dict)
    steps: list[ResolutionStep] = field(default_factory=list)


class Resolver:
    """
    Resolve rule sets for targets, caching the parts that do not vary.

    Parameters
    ----------
    settings : Settings
        The settings in force.
    known_codes : tuple of str
        Every registered rule code.
    """

    def __init__(self, settings: Settings, known_codes: tuple[str, ...]) -> None:
        self.settings = settings
        self.known = known_codes
        self._base = selection.apply_level(
            frozenset(),
            known_codes,
            select=list(settings.select),
            ignore=list(settings.ignore),
            extend_select=list(settings.extend_select),
            extend_ignore=list(settings.extend_ignore),
        )
        self._base_options = settings.base_options
        self._excluded_objects = tuple(
            _regex(pattern) for pattern in settings.exclude_object_patterns
        )
        self._overrides = {
            code: tuple(_regex(pattern) for pattern in patterns)
            for code, patterns in settings.overrides
        }

    @property
    def base(self) -> frozenset[str]:
        """
        Get the rule set before any scope block or per-file ignore.

        Returns
        -------
        frozenset of str
            The globally enabled codes.
        """
        return self._base

    def is_excluded_object(self, target: Target) -> bool:
        """
        Report whether an object is exempt from every rule by name.

        The patterns are searched against the object's numpydoc name, so
        expressions written for ``[tool.numpydoc_validation]`` behave as they
        did there.

        Parameters
        ----------
        target : Target
            The object being considered.

        Returns
        -------
        bool
            True when the object should be skipped entirely.
        """
        if not self._excluded_objects:
            return False
        name = target.numpydoc_name
        return any(pattern.search(name) for pattern in self._excluded_objects)

    def is_overridden(self, code: str, target: Target) -> bool:
        """
        Report whether a docstring opts itself out of one rule.

        This is numpydoc's ``override_<CODE>`` mechanism: a rule is suppressed
        for an object when one of its patterns is found in the docstring.

        Parameters
        ----------
        code : str
            The rule code.
        target : Target
            The object being checked.

        Returns
        -------
        bool
            True when the rule is overridden for this object.
        """
        patterns = self._overrides.get(code)
        if not patterns:
            return False
        raw = target.raw_docstring
        if raw is None:
            return False
        return any(pattern.search(raw) for pattern in patterns)

    def per_file_ignores(self, relative_path: str) -> tuple[str, ...]:
        """
        Collect the ignore selectors that apply to one file.

        Parameters
        ----------
        relative_path : str
            Path relative to the project root, in posix form.

        Returns
        -------
        tuple of str
            Selectors to disable for this file.
        """
        out: list[str] = []
        for pattern, codes in self.settings.per_file_ignores:
            if _spec((pattern,)).match_file(relative_path):
                out.extend(codes)
        return tuple(out)

    def file_codes(self, relative_path: str) -> frozenset[str]:
        """
        Compute the rules in force for a file as a whole.

        Scope blocks match objects, and a file is not one, so only the global
        selection and the file's ``per-file-ignores`` apply. This is the rule
        set a file-level rule runs under.

        Parameters
        ----------
        relative_path : str
            Path relative to the project root, in posix form.

        Returns
        -------
        frozenset of str
            The enabled codes.
        """
        ignores = self.per_file_ignores(relative_path)
        if not ignores:
            return self._base
        return selection.apply_level(
            self._base, self.known, extend_ignore=list(ignores)
        )

    def matching_scopes(
        self, target: Target, relative_path: str
    ) -> tuple[ScopeBlock, ...]:
        """
        Find the scope blocks that apply to a target, in configuration order.

        Parameters
        ----------
        target : Target
            The object being considered.
        relative_path : str
            Path relative to the project root, in posix form.

        Returns
        -------
        tuple of ScopeBlock
            Matching blocks.
        """
        return tuple(
            block
            for block in self.settings.scopes
            if block.matcher.matches(target, relative_path)
        )

    def resolve(
        self, target: Target, relative_path: str, *, trace: bool = False
    ) -> Resolution:
        """
        Compute the rules and options in force for one target.

        Layers apply in this order: global selection, then each matching scope
        block in configuration order, then per-file ignores. Inline
        suppressions are applied later, by the runner.

        Parameters
        ----------
        target : Target
            The object being considered.
        relative_path : str
            Path relative to the project root, in posix form.
        trace : bool
            Whether to record each layer for ``explain``.

        Returns
        -------
        Resolution
            The enabled codes, options, and optionally the trace.
        """
        enabled = self._base
        options = dict(self._base_options)
        steps: list[ResolutionStep] = []
        if trace:
            steps.append(ResolutionStep("global select/ignore", enabled))

        for block in self.matching_scopes(target, relative_path):
            before = enabled
            enabled = selection.apply_level(
                enabled,
                self.known,
                select=list(block.select) if block.select is not None else None,
                ignore=list(block.ignore) if block.ignore is not None else None,
                extend_select=list(block.extend_select),
                extend_ignore=list(block.extend_ignore),
                skip=block.skip,
            )
            options.update(dict(block.options))
            if trace:
                steps.append(
                    ResolutionStep(
                        f"scope block {block.index}",
                        enabled,
                        added=enabled - before,
                        removed=before - enabled,
                    )
                )

        file_ignores = self.per_file_ignores(relative_path)
        if file_ignores:
            before = enabled
            enabled = selection.apply_level(
                enabled, self.known, extend_ignore=list(file_ignores)
            )
            if trace:
                steps.append(
                    ResolutionStep(
                        "per-file-ignores", enabled, removed=before - enabled
                    )
                )

        return Resolution(enabled=enabled, options=options, steps=steps)
