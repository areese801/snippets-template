"""
Integration tests for shell wrapper scripts (get, search, snippets).

These run the actual shell scripts against the real repository.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.integration
class TestShellWrappers:
    def test_get_list_json(self):
        result = subprocess.run(
            [str(REPO_ROOT / "get"), "--list", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["status"] == "success"
        assert isinstance(output["snippets"], list)

    def test_get_help(self):
        result = subprocess.run(
            [str(REPO_ROOT / "get"), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "UUID" in result.stdout or "uuid" in result.stdout

    def test_search_list_tags_json(self):
        result = subprocess.run(
            [str(REPO_ROOT / "search"), "--list-tags", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert isinstance(output, dict)

    def test_search_help(self):
        result = subprocess.run(
            [str(REPO_ROOT / "search"), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0

    def test_snippets_is_executable(self):
        snippets_path = REPO_ROOT / "snippets"
        assert snippets_path.exists()
        assert os.access(str(snippets_path), os.X_OK)
