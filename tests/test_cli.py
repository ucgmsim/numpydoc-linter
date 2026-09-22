"""End-to-end command-line behaviour."""

from __future__ import annotations

import json

import pytest

from npdlint.cli import main

PROPERTY_SAMPLE = '''"""M."""


class C:
    """C."""

    @property
    def a(self):
        """float: A."""
        return 1
'''

METHOD_SAMPLE = '''"""M."""


class C:
    """C."""

    def m(self):
        """M."""
        x = 1
        return x
'''

SAMPLE = '''"""Module."""


def undocumented():
    pass
'''


@pytest.fixture
def project(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.npdlint]\nselect = ["GL08"]\n', encoding="utf-8"
    )
    (tmp_path / "sample.py").write_text(SAMPLE, encoding="utf-8")
    return tmp_path


def run(project, *args):
    config = str(project / "pyproject.toml")
    return main(["check", str(project), "--config", config, *args])


def test_exit_code_on_violations(project, capsys):
    assert run(project) == 1
    assert "GL08" in capsys.readouterr().out


def test_exit_code_when_clean(tmp_path, capsys):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.npdlint]\nselect = ["GL08"]\n', encoding="utf-8"
    )
    (tmp_path / "ok.py").write_text('"""Module."""\n', encoding="utf-8")
    config = str(tmp_path / "pyproject.toml")
    assert main(["check", str(tmp_path), "--config", config]) == 0
    assert "All checks passed" in capsys.readouterr().out


def test_exit_zero_flag(project):
    assert run(project, "--exit-zero") == 0


def test_concise_format(project, capsys):
    run(project, "--quiet")
    out = capsys.readouterr().out.strip()
    assert out == "sample.py:4:1: GL08 The object does not have a docstring"


def test_json_format(project, capsys):
    run(project, "--output-format", "json")
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["code"] == "GL08"
    assert payload[0]["path"] == "sample.py"
    assert payload[0]["kind"] == "function"
    assert payload[0]["qualname"] == "sample.undocumented"


def test_github_format(project, capsys):
    run(project, "--output-format", "github")
    out = capsys.readouterr().out
    assert out.startswith("::error file=sample.py,line=4,col=1,title=GL08::")


def test_full_format_quotes_the_source(project, capsys):
    run(project, "--output-format", "full", "--quiet")
    out = capsys.readouterr().out
    assert "def undocumented():" in out
    assert "^" in out


def test_statistics(project, capsys):
    run(project, "--statistics", "--quiet")
    out = capsys.readouterr().out
    assert "GL08  missing-docstring" in out


def test_cli_ignore_overrides_config(project):
    assert run(project, "--ignore", "GL08") == 0


def test_cli_select_replaces_config(project, capsys):
    run(project, "--select", "ES01", "--quiet")
    out = capsys.readouterr().out
    assert "GL08" not in out


def test_unknown_selector_is_an_error(project, capsys):
    assert run(project, "--select", "ZZ99") == 2
    assert "unknown rule selector" in capsys.readouterr().err


def test_syntax_error_is_reported_and_exits_two(tmp_path, capsys):
    (tmp_path / "bad.py").write_text("def (\n", encoding="utf-8")
    assert main(["check", str(tmp_path)]) == 2
    assert "E902" in capsys.readouterr().err


def test_show_files(project, capsys):
    assert run(project, "--show-files") == 0
    assert capsys.readouterr().out.strip() == "sample.py"


def test_show_settings(project, capsys):
    assert run(project, "--show-settings") == 0
    assert "enabled by default" in capsys.readouterr().out


def test_check_is_the_default_command(project, capsys):
    config = str(project / "pyproject.toml")
    assert main([str(project / "sample.py"), "--config", config]) == 1


def test_rule_command_lists_everything(capsys):
    assert main(["rule"]) == 0
    out = capsys.readouterr().out
    assert "GL08  missing-docstring" in out
    assert "PT01  property-form-mismatch" in out


def test_rule_command_filters_by_prefix(capsys):
    assert main(["rule", "PT"]) == 0
    out = capsys.readouterr().out
    assert "PT01" in out
    assert "GL08" not in out


def test_rule_command_json(capsys):
    assert main(["rule", "PR04", "--output-format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["code"] == "PR04"
    assert payload[0]["name"] == "parameter-has-no-type"


def test_rule_command_rejects_unknown(capsys):
    assert main(["rule", "ZZ99"]) == 2


def test_explain_shows_the_resolution(tmp_path, capsys):
    (tmp_path / "pyproject.toml").write_text(
        """
[tool.npdlint]
select = ["ALL"]

[[tool.npdlint.scope]]
match = { kind = "property" }
extend-ignore = ["RT"]
property-form = "type-line"
""",
        encoding="utf-8",
    )
    (tmp_path / "s.py").write_text(PROPERTY_SAMPLE, encoding="utf-8")
    config = str(tmp_path / "pyproject.toml")
    code = main(["explain", str(tmp_path / "s.py:8"), "--config", config])
    out = capsys.readouterr().out
    assert code == 0
    assert "kind       property" in out
    assert "scope block 0" in out
    assert "property-form = 'type-line'" in out
    assert "RT01" not in out.split("enabled")[-1]


def test_explain_rejects_a_missing_file(capsys):
    assert main(["explain", "nope.py"]) == 2


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0


def test_explain_resolves_a_decorator_line_to_its_function(tmp_path, capsys):
    (tmp_path / "s.py").write_text(PROPERTY_SAMPLE, encoding="utf-8")
    assert main(["explain", str(tmp_path / "s.py:7")]) == 0
    out = capsys.readouterr().out
    assert "s.C.a" in out
    assert "kind       property" in out


def test_explain_resolves_a_body_line_to_the_innermost_object(tmp_path, capsys):
    (tmp_path / "s.py").write_text(METHOD_SAMPLE, encoding="utf-8")
    assert main(["explain", str(tmp_path / "s.py:9")]) == 0
    assert "s.C.m" in capsys.readouterr().out


def test_explain_without_a_line_covers_the_whole_file(tmp_path, capsys):
    (tmp_path / "s.py").write_text(
        '"""M."""\n\n\ndef a():\n    """A."""\n', encoding="utf-8"
    )
    assert main(["explain", str(tmp_path / "s.py")]) == 0
    out = capsys.readouterr().out
    assert "kind       module" in out
    assert "kind       function" in out


def test_the_old_tool_table_name_warns_on_stderr(tmp_path, capsys):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.numpydoc-linter]\nselect = ["GL08"]\n', encoding="utf-8"
    )
    (tmp_path / "sample.py").write_text(SAMPLE, encoding="utf-8")
    config = str(tmp_path / "pyproject.toml")
    assert main(["check", str(tmp_path), "--config", config]) == 1
    captured = capsys.readouterr()
    assert "GL08" in captured.out
    assert "[tool.numpydoc-linter] is the old name" in captured.err
