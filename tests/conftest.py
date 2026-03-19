"""
Shared fixtures for snippet repository tests.
"""

import sys
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure .scripts is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".scripts"))

from constants import VALID_UUID, SECOND_UUID

VALID_SNIPPET = """\
---
id: {uuid}
title: "Test Query"
language: sql
tags:
- sql
- test
description: "A test SQL query"
created: "2026-03-01"
last_updated: "2026-03-05"
---

SELECT 1;
"""

OLD_SCHEMA_SNIPPET = """\
---
title: "Old Schema Snippet"
language: python
tags:
- python
source: "manual"
description: "Has source, missing last_updated and id"
created: "2026-01-15"
---

print("hello")
"""

PYTHON_SNIPPET = """\
---
id: {uuid}
title: "API Client"
language: python
tags:
- python
- api
description: "A test Python snippet"
created: "2026-02-20"
last_updated: "2026-02-25"
---

import requests

def get_data(url):
    return requests.get(url).json()
"""


@pytest.fixture
def snippet_repo(tmp_path):
    """
    Create a mini snippet repository structure for testing.
    """
    # Create directories
    sql_dir = tmp_path / "sql"
    sql_dir.mkdir()
    python_dir = tmp_path / "python"
    python_dir.mkdir()
    shell_dir = tmp_path / "shell"
    shell_dir.mkdir()
    scripts_dir = tmp_path / ".scripts"
    scripts_dir.mkdir()

    # Create valid v3 snippet
    (sql_dir / "test-query.md").write_text(
        VALID_SNIPPET.format(uuid=VALID_UUID), encoding="utf-8"
    )

    # Create old schema snippet (has source, missing last_updated and id)
    (python_dir / "old-schema.md").write_text(OLD_SCHEMA_SNIPPET, encoding="utf-8")

    # Create valid python snippet
    (python_dir / "api-client.md").write_text(
        PYTHON_SNIPPET.format(uuid=SECOND_UUID), encoding="utf-8"
    )

    return tmp_path


@pytest.fixture
def mock_repo_root(monkeypatch, snippet_repo):
    """
    Patch common.get_repo_root to return the tmp_path snippet repo.
    Also patches all modules that import get_repo_root from common.
    """
    import common

    monkeypatch.setattr(common, "get_repo_root", lambda: snippet_repo)

    # Patch in every script module that imports get_repo_root
    for mod_name in ["add", "edit", "get", "search", "audit", "snippets_tui", "browse"]:
        try:
            mod = __import__(mod_name)
            if hasattr(mod, "get_repo_root"):
                monkeypatch.setattr(mod, "get_repo_root", lambda: snippet_repo)
        except ImportError:
            pass

    return snippet_repo


@pytest.fixture
def mock_git(monkeypatch):
    """
    Patch subprocess.run to intercept git commands and return success.
    Tracks calls for assertions.
    """
    calls = []
    original_run = subprocess.run

    def patched_run(cmd, *args, **kwargs):
        if isinstance(cmd, list) and cmd[0] == "git":
            calls.append(cmd)
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_result.stderr = ""

            if cmd[1:2] == ["status"] and "--porcelain" in cmd:
                mock_result.stdout = ""
            elif cmd[1:2] == ["rev-parse"]:
                mock_result.stdout = "abc1234\n"

            return mock_result
        return original_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", patched_run)
    return calls


@pytest.fixture
def mock_clipboard(monkeypatch):
    """
    Capture clipboard text by patching subprocess.Popen for pbcopy/xclip.
    """
    captured = {"text": None}

    class FakePopen:
        def __init__(self, cmd, **kwargs):
            self.cmd = cmd
            self.returncode = 0
            self._stdin = kwargs.get("stdin")

        def communicate(self, input_data=None):
            if input_data:
                captured["text"] = input_data.decode("utf-8")
            return (b"", b"")

    monkeypatch.setattr(subprocess, "Popen", FakePopen)
    return captured


@pytest.fixture
def valid_metadata():
    """
    Return a complete v3 metadata dictionary.
    """
    return {
        "id": VALID_UUID,
        "title": "Test Snippet",
        "language": "sql",
        "tags": ["sql", "test"],
        "description": "A test snippet",
        "created": "2026-03-01",
        "last_updated": "2026-03-05",
    }
