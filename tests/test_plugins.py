"""Third-party rules."""

from __future__ import annotations

import pytest

from npdlint import plugins
from npdlint.config import _settings_from_table
from npdlint.rules.base import Registry, registry
from npdlint.runner import lint_source
from npdlint.source import read_source

PLUGIN = '''
"""A project-local rule."""

from npdlint.rules import BaseRule, registry
from npdlint.targets import Kind


@registry.register
class UnitsInSummary(BaseRule):
    """X001: physical quantities should state their units."""

    code = "X001"
    name = "units-in-summary"
    summary = "Summaries of measured properties should state units."
    kinds = frozenset({Kind.PROPERTY})

    def check(self, target, ctx):
        doc = target.docstring
        if target.name.endswith("_m") and "metres" not in doc.summary:
            yield self.diagnostic(target, "summary should state the units")
'''

SAMPLE = '''"""M."""


class C:
    """C."""

    @property
    def length_m(self):
        """float: The length."""
        return 1

    @property
    def width_m(self):
        """float: The width in metres."""
        return 1
'''


@pytest.fixture
def clean_registry():
    """Remove the plugin rule afterwards so other tests are unaffected."""
    yield
    registry._rules.pop("X001", None)
    plugins._loaded.discard("path:rules_plugin.py")


def test_local_plugin_registers_and_runs(tmp_path, clean_registry):
    (tmp_path / "rules_plugin.py").write_text(PLUGIN, encoding="utf-8")
    (tmp_path / "sample.py").write_text(SAMPLE, encoding="utf-8")

    plugins.load_path("rules_plugin.py", tmp_path)
    assert "X001" in registry

    settings = _settings_from_table({"select": ["X001"]}, tmp_path, None)
    found = lint_source(read_source(tmp_path / "sample.py", tmp_path), settings)
    assert [(d.line, d.code) for d in found] == [(8, "X001")]


def test_plugin_rule_participates_in_selection(tmp_path, clean_registry):
    (tmp_path / "rules_plugin.py").write_text(PLUGIN, encoding="utf-8")
    (tmp_path / "sample.py").write_text(SAMPLE, encoding="utf-8")
    plugins.load_path("rules_plugin.py", tmp_path)

    settings = _settings_from_table(
        {
            "select": ["X001"],
            "scope": [{"match": {"name": "length"}, "skip": True}],
        },
        tmp_path,
        None,
    )
    found = lint_source(read_source(tmp_path / "sample.py", tmp_path), settings)
    assert found == []


def test_missing_plugin_file_is_reported(tmp_path):
    with pytest.raises(plugins.PluginError, match="plugin file not found"):
        plugins.load_path("nope.py", tmp_path)


def test_broken_plugin_is_reported(tmp_path):
    (tmp_path / "bad_plugin.py").write_text(
        "raise RuntimeError('boom')\n", encoding="utf-8"
    )
    with pytest.raises(plugins.PluginError, match="error importing plugin"):
        plugins.load_path("bad_plugin.py", tmp_path)


def test_duplicate_code_is_rejected():
    local = Registry()

    class A:
        code = "Q001"
        name = "a"
        summary = ""
        kinds = frozenset()
        requires_docstring = True

    local.register(A)
    with pytest.raises(ValueError, match="duplicate rule code"):
        local.register(A)


def test_rule_without_a_code_is_rejected():
    local = Registry()

    class A:
        code = ""
        name = "a"
        summary = ""
        kinds = frozenset()
        requires_docstring = True

    with pytest.raises(ValueError, match="has no code"):
        local.register(A)


def test_register_hook_is_called(tmp_path):
    module = tmp_path / "hook_plugin.py"
    module.write_text(
        "CALLED = []\n\n\ndef register(registry):\n    CALLED.append(registry)\n",
        encoding="utf-8",
    )
    local = Registry()
    plugins.load_path("hook_plugin.py", tmp_path, local)
    import sys

    assert [local] == sys.modules["_npdlint_plugin_hook_plugin"].CALLED
