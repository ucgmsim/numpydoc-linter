"""File discovery."""

from __future__ import annotations

from pathlib import Path

from tests.conftest import settings_from

from numpydoc_linter.discovery import discover, iter_python_files


def build(root: Path, files: dict[str, str]) -> None:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def names(root: Path, paths: list[Path]) -> set[str]:
    return {p.relative_to(root).as_posix() for p in paths}


def test_walks_a_directory(tmp_path):
    build(tmp_path, {"a.py": "", "pkg/b.py": "", "pkg/sub/c.py": "", "d.txt": ""})
    found = discover([tmp_path], settings_from({}, tmp_path))
    assert names(tmp_path, found) == {"a.py", "pkg/b.py", "pkg/sub/c.py"}


def test_stub_files_are_skipped_by_default(tmp_path):
    """A stub carries no docstrings; the implementation it describes does."""
    build(tmp_path, {"a.py": "", "a.pyi": ""})
    found = discover([tmp_path], settings_from({}, tmp_path))
    assert names(tmp_path, found) == {"a.py"}


def test_stub_files_can_be_opted_in(tmp_path):
    build(tmp_path, {"a.py": "", "a.pyi": ""})
    settings = settings_from({"include-stubs": True}, tmp_path)
    found = discover([tmp_path], settings)
    assert names(tmp_path, found) == {"a.py", "a.pyi"}


def test_a_named_stub_is_still_skipped(tmp_path):
    build(tmp_path, {"a.pyi": ""})
    assert discover([tmp_path / "a.pyi"], settings_from({}, tmp_path)) == []


def test_default_excludes_are_skipped(tmp_path):
    build(
        tmp_path,
        {"a.py": "", ".venv/lib/b.py": "", "build/c.py": "", "__pycache__/d.py": ""},
    )
    found = discover([tmp_path], settings_from({}, tmp_path))
    assert names(tmp_path, found) == {"a.py"}


def test_configured_exclude(tmp_path):
    build(tmp_path, {"a.py": "", "tests/b.py": ""})
    settings = settings_from({"exclude": ["tests"]}, tmp_path)
    found = discover([tmp_path], settings)
    assert names(tmp_path, found) == {"a.py"}


def test_glob_exclude(tmp_path):
    build(tmp_path, {"src/a.py": "", "src/tests/b.py": "", "src/tests/deep/c.py": ""})
    settings = settings_from({"exclude": ["**/tests/**"]}, tmp_path)
    found = discover([tmp_path], settings)
    assert names(tmp_path, found) == {"src/a.py"}


def test_gitignore_is_respected(tmp_path):
    build(tmp_path, {".gitignore": "generated/\n", "a.py": "", "generated/b.py": ""})
    found = discover([tmp_path], settings_from({}, tmp_path))
    assert names(tmp_path, found) == {"a.py"}


def test_nested_gitignore_is_respected(tmp_path):
    build(
        tmp_path,
        {
            "a.py": "",
            "pkg/.gitignore": "skip.py\n",
            "pkg/skip.py": "",
            "pkg/keep.py": "",
        },
    )
    found = discover([tmp_path], settings_from({}, tmp_path))
    assert names(tmp_path, found) == {"a.py", "pkg/keep.py"}


def test_gitignore_can_be_disabled(tmp_path):
    build(tmp_path, {".gitignore": "generated/\n", "a.py": "", "generated/b.py": ""})
    settings = settings_from({"respect-gitignore": False}, tmp_path)
    found = discover([tmp_path], settings)
    assert names(tmp_path, found) == {"a.py", "generated/b.py"}


def test_named_files_are_taken_as_given(tmp_path):
    build(tmp_path, {"a.py": "", "b.py": ""})
    found = discover([tmp_path / "b.py"], settings_from({}, tmp_path))
    assert names(tmp_path, found) == {"b.py"}


def test_excludes_apply_to_named_files_too(tmp_path):
    """A pre-commit file list and a directory walk should lint the same set."""
    build(tmp_path, {"tests/b.py": ""})
    settings = settings_from({"exclude": ["tests"]}, tmp_path)
    assert discover([tmp_path / "tests" / "b.py"], settings) == []


def test_include_is_the_default(tmp_path):
    build(tmp_path, {"src/a.py": "", "other/b.py": ""})
    settings = settings_from({"include": ["src"]}, tmp_path)
    found = iter_python_files([], settings)
    assert names(tmp_path, found) == {"src/a.py"}


def test_command_line_paths_beat_include(tmp_path):
    build(tmp_path, {"src/a.py": "", "other/b.py": ""})
    settings = settings_from({"include": ["src"]}, tmp_path)
    found = iter_python_files([tmp_path / "other"], settings)
    assert names(tmp_path, found) == {"other/b.py"}


def test_results_are_sorted_and_deduplicated(tmp_path):
    build(tmp_path, {"a.py": "", "b.py": ""})
    settings = settings_from({}, tmp_path)
    found = discover([tmp_path, tmp_path / "a.py", tmp_path], settings)
    assert names(tmp_path, found) == {"a.py", "b.py"}
    assert found == sorted(found)


def test_exclude_replaces_the_defaults(tmp_path):
    """Following ruff: exclude overrides the built-ins, extend-exclude adds."""
    build(tmp_path, {"a.py": "", ".venv/b.py": ""})
    settings = settings_from({"exclude": ["nothing"]}, tmp_path)
    found = discover([tmp_path], settings)
    assert names(tmp_path, found) == {"a.py", ".venv/b.py"}


def test_extend_exclude_keeps_the_defaults(tmp_path):
    build(tmp_path, {"a.py": "", ".venv/b.py": "", "gen/c.py": ""})
    settings = settings_from({"extend-exclude": ["gen"]}, tmp_path)
    found = discover([tmp_path], settings)
    assert names(tmp_path, found) == {"a.py"}
