"""
Tests for browse.py - interactive snippet browser with fzf.
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from constants import VALID_UUID, SECOND_UUID
from conftest import VALID_SNIPPET, PYTHON_SNIPPET
from browse import build_snippet_lines, check_fzf, browse_snippets, main


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_fzf(monkeypatch):
    """
    Patch subprocess.run to intercept fzf calls and return a configurable
    selection. Non-fzf subprocess calls pass through.
    """
    state = {"selected_line": None, "returncode": 0}
    original_run = subprocess.run

    def patched_run(cmd, *args, **kwargs):
        if isinstance(cmd, list) and cmd[0] == "fzf":
            result = MagicMock()
            result.returncode = state["returncode"]
            result.stdout = state["selected_line"] or ""
            result.stderr = ""
            return result
        return original_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", patched_run)
    return state


# ============================================================================
# check_fzf
# ============================================================================


class TestCheckFzf:
    def test_fzf_installed(self, monkeypatch):
        monkeypatch.setattr("browse.shutil.which", lambda cmd: "/usr/local/bin/fzf")
        assert check_fzf() is True

    def test_fzf_not_installed(self, monkeypatch):
        monkeypatch.setattr("browse.shutil.which", lambda cmd: None)
        assert check_fzf() is False


# ============================================================================
# build_snippet_lines
# ============================================================================


class TestBuildSnippetLines:
    def test_all_snippets_produce_lines(self, mock_repo_root):
        from common import find_all_snippets

        snippets = find_all_snippets()
        lines = build_snippet_lines(snippets)
        # snippet_repo has 3 snippets (test-query, old-schema, api-client)
        # old-schema may be included too
        assert len(lines) >= 2

    def test_lines_contain_tab_separator(self, mock_repo_root):
        from common import find_all_snippets

        snippets = find_all_snippets()
        lines = build_snippet_lines(snippets)
        for line in lines:
            assert "\t" in line

    def test_lines_start_with_absolute_path(self, mock_repo_root):
        from common import find_all_snippets

        snippets = find_all_snippets()
        lines = build_snippet_lines(snippets)
        for line in lines:
            path_part = line.split("\t")[0]
            assert Path(path_part).is_absolute()

    def test_language_filter_sql(self, mock_repo_root):
        from common import find_all_snippets

        snippets = find_all_snippets()
        lines = build_snippet_lines(snippets, language_filter="sql")
        for line in lines:
            assert "[sql]" in line

    def test_language_filter_excludes_other(self, mock_repo_root):
        from common import find_all_snippets

        snippets = find_all_snippets()
        all_lines = build_snippet_lines(snippets)
        sql_lines = build_snippet_lines(snippets, language_filter="sql")
        assert len(sql_lines) < len(all_lines)

    def test_tag_filter(self, mock_repo_root):
        from common import find_all_snippets

        snippets = find_all_snippets()
        lines = build_snippet_lines(snippets, tag_filters=["api"])
        # Only api-client.md has tag "api"
        assert len(lines) == 1
        assert "API Client" in lines[0]

    def test_combined_filters(self, mock_repo_root):
        from common import find_all_snippets

        snippets = find_all_snippets()
        lines = build_snippet_lines(
            snippets, language_filter="python", tag_filters=["api"]
        )
        assert len(lines) == 1
        assert "API Client" in lines[0]

    def test_no_match_returns_empty(self, mock_repo_root):
        from common import find_all_snippets

        snippets = find_all_snippets()
        lines = build_snippet_lines(snippets, tag_filters=["nonexistent-tag-xyz"])
        assert len(lines) == 0

    def test_malformed_snippet_skipped(self, mock_repo_root):
        """Snippets with bad frontmatter are silently skipped."""
        bad_file = mock_repo_root / "sql" / "bad-snippet.md"
        bad_file.write_text("no frontmatter here", encoding="utf-8")

        from common import find_all_snippets

        snippets = find_all_snippets()
        lines = build_snippet_lines(snippets)
        # Should not crash; bad snippet excluded
        paths = [line.split("\t")[0] for line in lines]
        assert str(bad_file) not in paths


# ============================================================================
# fzf subprocess interaction
# ============================================================================


class TestFzfInteraction:
    def test_selected_snippet_copies_to_clipboard(
        self, mock_repo_root, mock_fzf, mock_clipboard, monkeypatch
    ):
        monkeypatch.setattr("browse.shutil.which", lambda cmd: "/usr/local/bin/fzf")
        snippet_path = mock_repo_root / "sql" / "test-query.md"
        mock_fzf["selected_line"] = f"{snippet_path}\t[sql] Test Query  (sql, test)"

        exit_code = browse_snippets()
        assert exit_code == 0
        assert mock_clipboard["text"] is not None
        assert "SELECT 1;" in mock_clipboard["text"]

    def test_cancel_exits_cleanly(self, mock_repo_root, mock_fzf, monkeypatch):
        monkeypatch.setattr("browse.shutil.which", lambda cmd: "/usr/local/bin/fzf")
        mock_fzf["returncode"] = 130  # ESC
        mock_fzf["selected_line"] = ""

        exit_code = browse_snippets()
        assert exit_code == 0

    def test_no_match_exits_cleanly(self, mock_repo_root, mock_fzf, monkeypatch):
        monkeypatch.setattr("browse.shutil.which", lambda cmd: "/usr/local/bin/fzf")
        mock_fzf["returncode"] = 1  # no match
        mock_fzf["selected_line"] = ""

        exit_code = browse_snippets()
        assert exit_code == 0

    def test_print_flag_outputs_to_stdout(
        self, mock_repo_root, mock_fzf, monkeypatch, capsys
    ):
        monkeypatch.setattr("browse.shutil.which", lambda cmd: "/usr/local/bin/fzf")
        snippet_path = mock_repo_root / "sql" / "test-query.md"
        mock_fzf["selected_line"] = f"{snippet_path}\t[sql] Test Query"

        exit_code = browse_snippets(print_only=True)
        assert exit_code == 0
        out = capsys.readouterr().out
        assert "SELECT 1;" in out


# ============================================================================
# CLI / main
# ============================================================================


class TestBrowseCLI:
    def test_fzf_not_installed_error(self, mock_repo_root, monkeypatch, capsys):
        monkeypatch.setattr("browse.shutil.which", lambda cmd: None)

        with pytest.raises(SystemExit) as exc:
            with patch("sys.argv", ["browse.py"]):
                main()
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert "fzf" in err
        assert "brew install fzf" in err

    def test_no_matching_snippets(self, mock_repo_root, monkeypatch, capsys):
        monkeypatch.setattr("browse.shutil.which", lambda cmd: "/usr/local/bin/fzf")

        with pytest.raises(SystemExit) as exc:
            with patch("sys.argv", ["browse.py", "--tag", "nonexistent-xyz"]):
                main()
        assert exc.value.code == 0
        err = capsys.readouterr().err
        assert "No snippets match" in err

    def test_language_flag_passed(self, mock_repo_root, mock_fzf, monkeypatch, capsys):
        monkeypatch.setattr("browse.shutil.which", lambda cmd: "/usr/local/bin/fzf")
        snippet_path = mock_repo_root / "python" / "api-client.md"
        mock_fzf["selected_line"] = f"{snippet_path}\t[python] API Client"

        with pytest.raises(SystemExit) as exc:
            with patch("sys.argv", ["browse.py", "--language", "python", "--print"]):
                main()
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "requests" in out
