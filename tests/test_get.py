"""
Tests for get.py - snippet retrieval by UUID.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from constants import VALID_UUID, SECOND_UUID
from helpers import extract_json, run_cli
from get import get_snippet_by_id, list_all_ids, main


# ============================================================================
# get_snippet_by_id
# ============================================================================


class TestGetSnippetById:
    def test_copy_success(self, mock_repo_root, mock_clipboard):
        result = get_snippet_by_id(VALID_UUID)
        assert result["status"] == "success"
        assert result["action"] == "copied"
        assert result["title"] == "Test Query"
        assert mock_clipboard["text"] is not None

    def test_print_mode(self, mock_repo_root, capsys):
        result = get_snippet_by_id(VALID_UUID, print_only=True)
        assert result["status"] == "success"
        assert result["action"] == "printed"
        out = capsys.readouterr().out
        assert "SELECT 1;" in out

    def test_not_found(self, mock_repo_root):
        result = get_snippet_by_id("00000000-0000-0000-0000-000000000000")
        assert result["status"] == "error"
        assert result["error_type"] == "not_found"

    def test_clipboard_failure(self, mock_repo_root, monkeypatch):
        import subprocess as sp

        def fail_popen(*args, **kwargs):
            raise OSError("no clipboard")

        monkeypatch.setattr(sp, "Popen", fail_popen)
        with patch("platform.system", return_value="Darwin"):
            result = get_snippet_by_id(VALID_UUID)
        assert result["status"] == "error"
        assert result["error_type"] == "clipboard_error"


# ============================================================================
# list_all_ids
# ============================================================================


class TestListAllIds:
    def test_returns_count_and_snippets(self, mock_repo_root):
        result = list_all_ids()
        assert result["status"] == "success"
        assert result["count"] >= 2
        ids = [s["id"] for s in result["snippets"]]
        assert VALID_UUID in ids
        assert SECOND_UUID in ids


# ============================================================================
# CLI / main
# ============================================================================


class TestGetCLI:
    def test_list_json(self, mock_repo_root, capsys):
        code, output = run_cli(main, ["get.py", "--list", "--format", "json"], capsys)
        assert code == 0
        assert output["status"] == "success"
        assert output["count"] >= 2

    def test_uuid_json(self, mock_repo_root, mock_clipboard, capsys):
        code, output = run_cli(main, ["get.py", VALID_UUID, "--format", "json"], capsys)
        assert code == 0
        assert output["status"] == "success"
        assert output["action"] == "copied"

    def test_print_flag(self, mock_repo_root, capsys):
        with patch("sys.argv", ["get.py", VALID_UUID, "--print", "--format", "json"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
        out = capsys.readouterr().out
        # stdout has both the printed code and the JSON
        assert "SELECT 1;" in out
