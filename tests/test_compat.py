"""Backwards compatibility with numpydoc's own configuration."""

from __future__ import annotations

import pytest

from numpydoc_linter import compat
from numpydoc_linter.config import ConfigError, load_settings
from numpydoc_linter.runner import lint_paths

SAMPLE = '''"""Module."""


def documented(x):
    """
    Summary.

    Parameters
    ----------
    x : int
        The x.
    """
    return x


def undocumented(x):
    pass


class Widget:
    """A widget."""

    def undocumented_method(self):
        pass

    def __repr__(self):
        pass
'''


def project(tmp_path, pyproject: str, files: dict[str, str] | None = None):
    """Lay out a project and return its settings."""
    (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    for name, body in (files or {"sample.py": SAMPLE}).items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return load_settings(tmp_path / "pyproject.toml")


def run(tmp_path, settings):
    """Lint every Python file in the project."""
    from numpydoc_linter.discovery import iter_python_files

    files = iter_python_files([], settings)
    return lint_paths(files, settings, jobs=1)


# -- checks ---------------------------------------------------------------


def test_checks_as_an_allow_list(tmp_path):
    settings = project(
        tmp_path,
        "[tool.numpydoc_validation]\nchecks = ['GL08', 'PR01']\n",
    )
    assert settings.select == ("GL08", "PR01")
    assert settings.legacy_config is True


def test_checks_with_all_means_every_numpydoc_check(tmp_path):
    settings = project(tmp_path, "[tool.numpydoc_validation]\nchecks = ['all']\n")
    assert set(settings.select) == set(compat.NUMPYDOC_CODES)


def test_checks_with_all_and_exclusions(tmp_path):
    settings = project(
        tmp_path,
        "[tool.numpydoc_validation]\nchecks = ['all', 'ES01', 'SA01', 'EX01']\n",
    )
    assert set(settings.select) == set(compat.NUMPYDOC_CODES) - {
        "ES01",
        "SA01",
        "EX01",
    }


def test_all_does_not_enable_this_tools_own_rules(tmp_path):
    """A legacy configuration should not silently gain new checks."""
    settings = project(tmp_path, "[tool.numpydoc_validation]\nchecks = ['all']\n")
    assert not [code for code in settings.select if code.startswith(("PT", "DS"))]


def test_a_legacy_table_without_checks_defaults_to_all_numpydoc_checks(tmp_path):
    settings = project(
        tmp_path, "[tool.numpydoc_validation]\nexclude = ['nothing']\n"
    )
    assert set(settings.select) == set(compat.NUMPYDOC_CODES)


def test_unknown_check_code_is_reported(tmp_path):
    with pytest.raises(ConfigError, match="unrecognised check code"):
        project(tmp_path, "[tool.numpydoc_validation]\nchecks = ['ZZ99']\n")


def test_unknown_check_code_is_reported_with_all(tmp_path):
    with pytest.raises(ConfigError, match="unrecognised check code"):
        project(tmp_path, "[tool.numpydoc_validation]\nchecks = ['all', 'ZZ99']\n")


# -- exclude --------------------------------------------------------------


def test_exclude_matches_the_numpydoc_object_name(tmp_path):
    settings = project(
        tmp_path,
        "[tool.numpydoc_validation]\n"
        "checks = ['GL08']\n"
        "exclude = ['\\.undocumented_method$', '\\.__repr__$']\n",
    )
    result = run(tmp_path, settings)
    names = {d.qualname for d in result.diagnostics}
    assert names == {"sample.undocumented"}


def test_exclude_is_rooted_at_the_file_stem_like_numpydoc(tmp_path):
    """numpydoc names objects from the file stem, not the package path."""
    settings = project(
        tmp_path,
        "[tool.numpydoc_validation]\nchecks = ['GL08']\nexclude = ['^sample\\.']\n",
    )
    assert run(tmp_path, settings).diagnostics == []


def test_exclude_accepts_a_bare_string(tmp_path):
    settings = project(
        tmp_path,
        "[tool.numpydoc_validation]\nchecks = ['GL08']\nexclude = '^sample\\.'\n",
    )
    assert settings.exclude_object_patterns == ("^sample\\.",)


# -- exclude_files --------------------------------------------------------


def test_exclude_files_skips_matching_paths(tmp_path):
    settings = project(
        tmp_path,
        "[tool.numpydoc_validation]\n"
        "checks = ['GL08']\n"
        "exclude_files = ['^skipme/.*']\n",
        files={"keep.py": SAMPLE, "skipme/drop.py": SAMPLE},
    )
    result = run(tmp_path, settings)
    assert {d.path.name for d in result.diagnostics} == {"keep.py"}


def test_exclude_files_is_anchored_at_the_start(tmp_path):
    """numpydoc uses re.match here, unlike the object patterns."""
    settings = project(
        tmp_path,
        "[tool.numpydoc_validation]\nchecks = ['GL08']\nexclude_files = ['drop']\n",
        files={"keep.py": SAMPLE, "sub/drop.py": SAMPLE},
    )
    result = run(tmp_path, settings)
    assert {d.path.name for d in result.diagnostics} == {"keep.py", "drop.py"}


# -- override_<CODE> ------------------------------------------------------


OVERRIDE_SAMPLE = '''"""Module."""


def processes_things():
    """Processes the things."""


def generates_things():
    """Generates the things."""
'''


def test_override_suppresses_a_check_when_the_pattern_matches(tmp_path):
    settings = project(
        tmp_path,
        "[tool.numpydoc_validation]\n"
        "checks = ['SS05']\n"
        "override_SS05 = ['^Processes ']\n",
        files={"sample.py": OVERRIDE_SAMPLE},
    )
    result = run(tmp_path, settings)
    assert {d.qualname for d in result.diagnostics} == {"sample.generates_things"}


def test_override_without_a_match_changes_nothing(tmp_path):
    settings = project(
        tmp_path,
        "[tool.numpydoc_validation]\nchecks = ['SS05']\noverride_SS05 = ['^Nope ']\n",
        files={"sample.py": OVERRIDE_SAMPLE},
    )
    assert len(run(tmp_path, settings).diagnostics) == 2


def test_override_does_not_crash_on_a_missing_docstring(tmp_path):
    settings = project(
        tmp_path,
        "[tool.numpydoc_validation]\nchecks = ['GL08']\noverride_GL08 = ['anything']\n",
    )
    assert run(tmp_path, settings).diagnostics != []


# -- setup.cfg ------------------------------------------------------------


def test_setup_cfg_is_read_when_there_is_no_pyproject(tmp_path):
    (tmp_path / "setup.cfg").write_text(
        "[tool:numpydoc_validation]\nchecks = GL08,PR01\nexclude = \\.__repr__$\n",
        encoding="utf-8",
    )
    (tmp_path / "sample.py").write_text(SAMPLE, encoding="utf-8")
    settings = load_settings(root=tmp_path)
    assert settings.select == ("GL08", "PR01")
    assert settings.exclude_object_patterns == ("\\.__repr__$",)


def test_pyproject_wins_over_setup_cfg(tmp_path):
    """numpydoc does not consult setup.cfg once pyproject.toml exists."""
    (tmp_path / "setup.cfg").write_text(
        "[tool:numpydoc_validation]\nchecks = GL08\n", encoding="utf-8"
    )
    settings = project(
        tmp_path, "[tool.numpydoc_validation]\nchecks = ['PR01']\n"
    )
    assert settings.select == ("PR01",)


# -- layering -------------------------------------------------------------


def test_native_settings_win_over_legacy_ones(tmp_path):
    settings = project(
        tmp_path,
        "[tool.numpydoc_validation]\nchecks = ['GL08']\n\n"
        "[tool.numpydoc-linter]\nselect = ['PR01']\n",
    )
    assert settings.select == ("PR01",)


def test_legacy_fills_in_what_the_native_table_omits(tmp_path):
    settings = project(
        tmp_path,
        "[tool.numpydoc_validation]\n"
        "checks = ['GL08']\n"
        "exclude = ['\\.__repr__$']\n\n"
        "[tool.numpydoc-linter]\ninclude = ['src']\n",
    )
    assert settings.select == ("GL08",)
    assert settings.exclude_object_patterns == ("\\.__repr__$",)
    assert settings.include == ("src",)


def test_compat_can_be_turned_off(tmp_path):
    settings = project(
        tmp_path,
        "[tool.numpydoc_validation]\nchecks = ['GL08']\n\n"
        "[tool.numpydoc-linter]\nnumpydoc-compat = false\n",
    )
    assert settings.select == ("ALL",)
    assert settings.legacy_config is False


def test_no_legacy_table_means_no_compat(tmp_path):
    settings = project(tmp_path, "[tool.numpydoc-linter]\nselect = ['GL08']\n")
    assert settings.legacy_config is False


# -- native equivalents ---------------------------------------------------


def test_the_same_features_are_available_natively(tmp_path):
    settings = project(
        tmp_path,
        "[tool.numpydoc-linter]\n"
        "select = ['SS05']\n"
        "exclude-object-patterns = ['\\.__repr__$']\n"
        "exclude-file-patterns = ['^skip/']\n\n"
        "[tool.numpydoc-linter.overrides]\n"
        "SS05 = ['^Processes ']\n",
        files={"sample.py": OVERRIDE_SAMPLE},
    )
    assert settings.exclude_object_patterns == ("\\.__repr__$",)
    assert settings.exclude_file_patterns == ("^skip/",)
    assert settings.overrides == (("SS05", ("^Processes ",)),)
    result = run(tmp_path, settings)
    assert {d.qualname for d in result.diagnostics} == {"sample.generates_things"}
