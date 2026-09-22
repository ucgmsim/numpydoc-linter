"""Built-in rules.

Importing this package populates :data:`npdlint.rules.base.registry`.
"""

from __future__ import annotations

from npdlint.rules import (  # noqa: F401
    general,
    parameters,
    properties,
    returns,
    see_also,
    summary,
    suppressions,
)
from npdlint.rules.base import (
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
