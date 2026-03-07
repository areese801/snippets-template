"""
Tests for snippets_tui.py - only pure functions, skip interactive menus.
"""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from snippets_tui import get_repository_stats, run_script


# ============================================================================
# get_repository_stats
# ============================================================================


class TestGetRepositoryStats:
    def test_with_snippets(self, mock_repo_root):
        stats = get_repository_stats()
        assert stats["total"] >= 2
        assert "sql" in stats["by_language"]
        assert "python" in stats["by_language"]

    def test_empty_repo(self, monkeypatch, tmp_path):
        import common
        import snippets_tui

        # Create empty repo structure
        (tmp_path / ".scripts").mkdir()
        (tmp_path / "sql").mkdir()
        monkeypatch.setattr(common, "get_repo_root", lambda: tmp_path)
        monkeypatch.setattr(snippets_tui, "get_repo_root", lambda: tmp_path)

        stats = get_repository_stats()
        assert stats["total"] == 0
        assert stats["by_language"] == {}


# ============================================================================
# run_script
# ============================================================================


class TestRunScript:
    def test_success(self, monkeypatch):
        mock_result = MagicMock()
        mock_result.returncode = 0
        monkeypatch.setattr("subprocess.run", lambda cmd, **kw: mock_result)
        assert run_script("search.py", ["--list-tags"]) == 0

    def test_failure(self, monkeypatch):
        mock_result = MagicMock()
        mock_result.returncode = 1
        monkeypatch.setattr("subprocess.run", lambda cmd, **kw: mock_result)
        assert run_script("search.py") == 1
