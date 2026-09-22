"""Configuration loading and validation."""

from __future__ import annotations

import pytest
from tests.conftest import settings_from

from npdlint.config import ConfigError, Settings, load_settings


def write(tmp_path, body: str):
    (tmp_path / "pyproject.toml").write_text(body, encoding="utf-8")
    return load_settings(tmp_path / "pyproject.toml")


def test_defaults_when_no_config(tmp_path):
    settings = load_settings(root=tmp_path)
    assert settings.select == ("ALL",)
    assert settings.respect_gitignore is True


def test_reads_the_tool_table(tmp_path):
    settings = write(
        tmp_path,
        """
[tool.npdlint]
include = ["src"]
ignore = ["ES01"]
""",
    )
    assert settings.include == ("src",)
    assert settings.ignore == ("ES01",)
    assert settings.config_path == tmp_path / "pyproject.toml"


def test_the_old_tool_table_name_is_still_read(tmp_path):
    """A project configured before the rename keeps working."""
    settings = write(
        tmp_path,
        '[tool.numpydoc-linter]\ninclude = ["src"]\nignore = ["ES01"]\n',
    )
    assert settings.include == ("src",)
    assert settings.ignore == ("ES01",)
    assert len(settings.notices) == 1
    assert "old name" in settings.notices[0]


def test_the_current_tool_table_name_is_quiet(tmp_path):
    settings = write(tmp_path, '[tool.npdlint]\ninclude = ["src"]\n')
    assert settings.notices == ()


def test_the_current_name_wins_over_the_old_one(tmp_path):
    """Merging the two would make the effective settings unreadable."""
    settings = write(
        tmp_path,
        '[tool.npdlint]\ninclude = ["new"]\n'
        '[tool.numpydoc-linter]\ninclude = ["old"]\n',
    )
    assert settings.include == ("new",)
    assert "is ignored" in settings.notices[0]


def test_a_string_is_accepted_where_a_list_is_expected(tmp_path):
    settings = write(tmp_path, '[tool.npdlint]\ninclude = "src"\n')
    assert settings.include == ("src",)


def test_unknown_top_level_key_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="unknown key"):
        write(tmp_path, "[tool.npdlint]\nselct = []\n")


def test_unknown_match_key_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="unknown match key"):
        write(
            tmp_path,
            "[[tool.npdlint.scope]]\nmatch = { kinds = 'property' }\n",
        )


def test_unknown_kind_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="unknown kind"):
        write(
            tmp_path,
            "[[tool.npdlint.scope]]\nmatch = { kind = 'propery' }\n",
        )


def test_unknown_scope_key_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="unknown key"):
        write(
            tmp_path,
            "[[tool.npdlint.scope]]\nmatch = {}\nskp = true\n",
        )


def test_rule_options_are_allowed_in_scopes(tmp_path):
    settings = write(
        tmp_path,
        """
[[tool.npdlint.scope]]
match = { kind = "property" }
property-form = "type-line"
""",
    )
    assert settings.scopes[0].options == (("property-form", "type-line"),)


def test_malformed_toml_is_reported(tmp_path):
    with pytest.raises(ConfigError):
        write(tmp_path, "[tool.npdlint\n")


def test_missing_config_file_is_reported(tmp_path):
    with pytest.raises(ConfigError, match="no such config file"):
        load_settings(tmp_path / "nope.toml")


def test_property_decorators_extend_the_defaults(tmp_path):
    settings = write(
        tmp_path,
        '[tool.npdlint]\nproperty-decorators = ["computed_field"]\n',
    )
    assert "property" in settings.property_decorators
    assert "computed_field" in settings.property_decorators


def test_all_excludes_includes_the_builtins():
    settings = Settings()
    assert ".git" in settings.all_excludes()


def test_config_is_discovered_upwards(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.npdlint]\ninclude = ["src"]\n', encoding="utf-8"
    )
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    settings = load_settings(root=nested)
    assert settings.include == ("src",)
    assert settings.root == tmp_path.resolve()


def test_settings_are_picklable():
    """Parallel linting ships settings to worker processes."""
    import pickle

    settings = settings_from(
        {
            "select": ["ALL"],
            "scope": [{"match": {"kind": "property"}, "property-form": "type-line"}],
        },
        __import__("pathlib").Path("."),
    )
    assert pickle.loads(pickle.dumps(settings)) == settings
