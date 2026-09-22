"""Built-in rules.

Importing this package populates :data:`numpydoc_linter.rules.base.registry`.
"""

from __future__ import annotations

from numpydoc_linter.rules import (  # noqa: F401
    general,
    parameters,
    properties,
    returns,
    see_also,
    summary,
    suppressions,
)
from numpydoc_linter.rules.base import (
    BaseFileRule,
    BaseRule,
    Context,
    Registry,
    Rule,
    registry,
)

__all__ = [
    "BaseFileRule",
    "BaseRule",
    "Context",
    "Registry",
    "Rule",
    "registry",
]
