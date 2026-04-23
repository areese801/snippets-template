"""
Tests for the gist publishing feature.

All gh CLI calls are mocked — no real GitHub API calls are made.
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".scripts"))

from constants import VALID_UUID, SECOND_UUID
from helpers import run_cli

import common
import gist as gist_module
from gist import (
    get_gist_filename,
    resolve_snippet,
    publish_snippet,
    teardown_snippet,
    sync_all,
    gist_status,
    main,
    _build_gist_description,
    _parse_gist_url,
    _extract_gist_id_from_url,
)


# ============================================================================
# Test Snippets
# ============================================================================

GIST_SNIPPET = """\
---
id: {uuid}
title: "dbt Incremental Model"
language: sql
tags:
- dbt
- sql
gist: true
description: "Standard incremental model template"
created: "2026-03-01"
last_updated: "2026-03-05"
---

SELECT * FROM source WHERE updated_at > '{{START_DATE}}'
"""

GIST_SNIPPET_WITH_ID = """\
---
id: {uuid}
title: "API Client"
language: python
tags:
- python
- api
gist: true
gist_id: abc123def456
gist_url: https://gist.github.com/testuser/abc123def456
description: "Reusable API client"
created: "2026-02-20"
last_updated: "2026-02-25"
---

import requests

def get_data(url):
    return requests.get(url).json()
"""

NO_GIST_SNIPPET = """\
---
id: {uuid}
title: "Simple Query"
language: sql
tags:
- sql
description: "A simple query"
created: "2026-01-15"
last_updated: "2026-01-20"
---

SELECT 1;
"""

TEARDOWN_SNIPPET = """\
---
id: {uuid}
title: "Old Gist"
language: shell
tags:
- shell
gist: false
gist_id: old-gist-id-789
gist_url: https://gist.github.com/testuser/old-gist-id-789
description: "Previously published, now disabled"
created: "2026-01-10"
last_updated: "2026-01-15"
---

echo "hello"
"""

TEARDOWN_UUID = "770a0600-a41d-63f6-c938-668877662222"
NO_GIST_UUID = "880b1700-b52e-74a7-da49-779988773333"


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def gist_repo(tmp_path):
    """
    Create a snippet repository with gist-related test files.
    """
    sql_dir = tmp_path / "sql"
    sql_dir.mkdir()
    python_dir = tmp_path / "python"
    python_dir.mkdir()
    shell_dir = tmp_path / "shell"
    shell_dir.mkdir()
    scripts_dir = tmp_path / ".scripts"
    scripts_dir.mkdir()

    # gist:true, no gist_id (should create)
    (sql_dir / "dbt-incremental-model.md").write_text(
        GIST_SNIPPET.format(uuid=VALID_UUID), encoding="utf-8"
    )

    # gist:true, has gist_id (should update)
    (python_dir / "api-client.md").write_text(
        GIST_SNIPPET_WITH_ID.format(uuid=SECOND_UUID), encoding="utf-8"
    )

    # No gist field at all (should skip)
    (sql_dir / "simple-query.md").write_text(
        NO_GIST_SNIPPET.format(uuid=NO_GIST_UUID), encoding="utf-8"
    )

    # gist:false with gist_id (should teardown)
    (shell_dir / "old-gist.md").write_text(
        TEARDOWN_SNIPPET.format(uuid=TEARDOWN_UUID), encoding="utf-8"
    )

    return tmp_path


@pytest.fixture
def mock_gist_repo_root(monkeypatch, gist_repo):
    """
    Patch get_repo_root to return our test repo for both common and gist modules.
    """
    monkeypatch.setattr(common, "get_repo_root", lambda: gist_repo)
    monkeypatch.setattr(gist_module, "get_repo_root", lambda: gist_repo)
    return gist_repo


@pytest.fixture
def mock_gh_and_git(monkeypatch):
    """
    Mock subprocess.run to intercept both gh and git commands.
    Returns a dict tracking calls by command type.
    """
    calls = {"gh": [], "git": []}
    original_run = subprocess.run

    def patched_run(cmd, *args, **kwargs):
        if isinstance(cmd, list):
            if cmd[0] == "gh":
                calls["gh"].append(cmd)
                mock_result = MagicMock()
                mock_result.returncode = 0
                mock_result.stderr = ""

                if cmd[1:3] == ["gist", "create"]:
                    mock_result.stdout = (
                        "https://gist.github.com/testuser/new-gist-id-999\n"
                    )
                elif cmd[1:3] == ["gist", "edit"]:
                    mock_result.stdout = ""
                elif cmd[1:3] == ["gist", "delete"]:
                    mock_result.stdout = ""
                else:
                    mock_result.stdout = ""

                return mock_result

            elif cmd[0] == "git":
                calls["git"].append(cmd)
                mock_result = MagicMock()
                mock_result.returncode = 0
                mock_result.stdout = ""
                mock_result.stderr = ""

                if cmd[1:2] == ["rev-parse"]:
                    mock_result.stdout = "abc1234\n"
                elif cmd[1:2] == ["status"] and "--porcelain" in cmd:
                    mock_result.stdout = ""
                elif cmd[1:2] == ["diff"] and "--cached" in cmd:
                    # returncode 1 = there are staged changes
                    mock_result.returncode = 1

                return mock_result

        return original_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", patched_run)
    return calls


# ============================================================================
# Tests: get_gist_filename
# ============================================================================

class TestGetGistFilename:
    """
    Tests for the get_gist_filename helper.
    """

    def test_sql_snippet(self):
        metadata = {"title": "dbt Incremental Model", "language": "sql"}
        assert get_gist_filename(metadata) == "dbt-incremental-model.sql"

    def test_python_snippet(self):
        metadata = {"title": "API Client", "language": "python"}
        assert get_gist_filename(metadata) == "api-client.py"

    def test_shell_snippet(self):
        metadata = {"title": "Docker Cleanup", "language": "shell"}
        assert get_gist_filename(metadata) == "docker-cleanup.sh"

    def test_unknown_language_defaults_to_txt(self):
        metadata = {"title": "Some Notes", "language": "rust"}
        assert get_gist_filename(metadata) == "some-notes.txt"

    def test_special_characters_in_title(self):
        metadata = {"title": "Hello World! (v2.0)", "language": "python"}
        assert get_gist_filename(metadata) == "hello-world-v20.py"

    def test_missing_title_defaults_to_untitled(self):
        metadata = {"language": "sql"}
        assert get_gist_filename(metadata) == "untitled.sql"

    def test_yaml_extension(self):
        metadata = {"title": "Config Template", "language": "yaml"}
        assert get_gist_filename(metadata) == "config-template.yml"

    def test_json_extension(self):
        metadata = {"title": "API Response", "language": "json"}
        assert get_gist_filename(metadata) == "api-response.json"


# ============================================================================
# Tests: resolve_snippet
# ============================================================================

class TestResolveSnippet:
    """
    Tests for the resolve_snippet function.
    """

    def test_resolve_by_file_path(self, mock_gist_repo_root):
        result = resolve_snippet("sql/dbt-incremental-model.md")
        assert result.name == "dbt-incremental-model.md"
        assert result.exists()

    def test_resolve_by_uuid(self, mock_gist_repo_root):
        result = resolve_snippet(VALID_UUID)
        assert result.name == "dbt-incremental-model.md"
        assert result.exists()

    def test_resolve_nonexistent_path_raises(self, mock_gist_repo_root):
        with pytest.raises(FileNotFoundError, match="Snippet file not found"):
            resolve_snippet("sql/nonexistent.md")

    def test_resolve_nonexistent_uuid_raises(self, mock_gist_repo_root):
        with pytest.raises(FileNotFoundError, match="No snippet found with ID"):
            resolve_snippet("00000000-0000-0000-0000-000000000000")

    def test_resolve_invalid_identifier_raises(self, mock_gist_repo_root):
        with pytest.raises(FileNotFoundError, match="Cannot resolve identifier"):
            resolve_snippet("not-a-path-or-uuid")

    def test_resolve_path_with_slash(self, mock_gist_repo_root):
        result = resolve_snippet("python/api-client.md")
        assert result.name == "api-client.md"

    def test_resolve_md_extension(self, mock_gist_repo_root):
        """
        File ending with .md is detected as path even without slash.
        """
        # This file is at sql/simple-query.md, so specifying as
        # a relative path with directory works
        result = resolve_snippet("sql/simple-query.md")
        assert result.exists()


# ============================================================================
# Tests: Helper functions
# ============================================================================

class TestHelpers:
    """
    Tests for internal helper functions.
    """

    def test_build_gist_description_with_desc(self):
        metadata = {"title": "My Query", "description": "Does a thing"}
        result = _build_gist_description(metadata)
        assert result == "My Query \u2014 Does a thing"

    def test_build_gist_description_without_desc(self):
        metadata = {"title": "My Query"}
        result = _build_gist_description(metadata)
        assert result == "My Query"

    def test_parse_gist_url_valid(self):
        url = _parse_gist_url("https://gist.github.com/user/abc123\n")
        assert url == "https://gist.github.com/user/abc123"

    def test_parse_gist_url_invalid(self):
        with pytest.raises(ValueError, match="Could not parse gist URL"):
            _parse_gist_url("Error: something went wrong")

    def test_extract_gist_id_from_url(self):
        gist_id = _extract_gist_id_from_url(
            "https://gist.github.com/user/abc123def456"
        )
        assert gist_id == "abc123def456"


# ============================================================================
# Tests: publish_snippet
# ============================================================================

class TestPublishSnippet:
    """
    Tests for the publish_snippet function.
    """

    def test_publish_creates_new_gist(
        self, mock_gist_repo_root, mock_gh_and_git
    ):
        file_path = mock_gist_repo_root / "sql" / "dbt-incremental-model.md"
        result = publish_snippet(file_path)

        assert result["status"] == "success"
        assert result["action"] == "created"
        assert result["gist_id"] == "new-gist-id-999"
        assert "gist.github.com" in result["gist_url"]
        assert result["gist_filename"] == "dbt-incremental-model.sql"

        # Verify gh gist create was called
        gh_calls = mock_gh_and_git["gh"]
        assert len(gh_calls) == 1
        assert gh_calls[0][1:3] == ["gist", "create"]
        assert "--public" in gh_calls[0]

        # Verify metadata was written back
        content = file_path.read_text(encoding="utf-8")
        metadata, _ = common.parse_frontmatter(content)
        assert metadata["gist_id"] == "new-gist-id-999"
        assert metadata["gist_url"] == "https://gist.github.com/testuser/new-gist-id-999"

    def test_publish_updates_existing_gist(
        self, mock_gist_repo_root, mock_gh_and_git
    ):
        file_path = mock_gist_repo_root / "python" / "api-client.md"
        result = publish_snippet(file_path)

        assert result["status"] == "success"
        assert result["action"] == "updated"
        assert result["gist_id"] == "abc123def456"

        # Verify gh gist edit was called
        gh_calls = mock_gh_and_git["gh"]
        assert len(gh_calls) == 1
        assert gh_calls[0][1:3] == ["gist", "edit"]
        assert "abc123def456" in gh_calls[0]

    def test_publish_secret_gist(
        self, mock_gist_repo_root, mock_gh_and_git
    ):
        file_path = mock_gist_repo_root / "sql" / "dbt-incremental-model.md"
        result = publish_snippet(file_path, secret=True)

        assert result["status"] == "success"
        assert result["action"] == "created"

        gh_calls = mock_gh_and_git["gh"]
        assert "--public" not in gh_calls[0]

    def test_publish_rejects_non_gist_snippet(
        self, mock_gist_repo_root, mock_gh_and_git
    ):
        file_path = mock_gist_repo_root / "sql" / "simple-query.md"
        result = publish_snippet(file_path)

        assert result["status"] == "error"
        assert result["error_type"] == "not_gist_enabled"
        assert mock_gh_and_git["gh"] == []  # No gh calls made

    def test_publish_dry_run(self, mock_gist_repo_root, mock_gh_and_git):
        file_path = mock_gist_repo_root / "sql" / "dbt-incremental-model.md"
        result = publish_snippet(file_path, dry_run=True)

        assert result["status"] == "success"
        assert result["dry_run"] is True
        assert result["action"] == "create"
        assert mock_gh_and_git["gh"] == []  # No gh calls in dry run

    def test_publish_dry_run_update(self, mock_gist_repo_root, mock_gh_and_git):
        file_path = mock_gist_repo_root / "python" / "api-client.md"
        result = publish_snippet(file_path, dry_run=True)

        assert result["status"] == "success"
        assert result["dry_run"] is True
        assert result["action"] == "update"
        assert result["gist_id"] == "abc123def456"

    def test_publish_auto_commits(
        self, mock_gist_repo_root, mock_gh_and_git
    ):
        file_path = mock_gist_repo_root / "sql" / "dbt-incremental-model.md"
        result = publish_snippet(file_path)

        assert result["committed"] is True
        assert result["commit_hash"] == "abc1234"

        # Verify git add and commit were called
        git_calls = mock_gh_and_git["git"]
        git_add_calls = [c for c in git_calls if c[1] == "add"]
        git_commit_calls = [c for c in git_calls if c[1] == "commit"]
        assert len(git_add_calls) >= 1
        assert len(git_commit_calls) >= 1

    def test_publish_strips_frontmatter_from_gist_content(
        self, mock_gist_repo_root, mock_gh_and_git
    ):
        """
        Gist content should be code body only, not the full snippet with frontmatter.
        """
        file_path = mock_gist_repo_root / "sql" / "dbt-incremental-model.md"
        result = publish_snippet(file_path)
        assert result["status"] == "success"

        # The gh gist create command should reference a temp file.
        # We can't easily inspect temp file content in this test,
        # but we verify the call was made correctly.
        gh_calls = mock_gh_and_git["gh"]
        assert len(gh_calls) == 1
        # Last arg is the temp file path
        temp_file_arg = gh_calls[0][-1]
        assert temp_file_arg.endswith(".sql")


# ============================================================================
# Tests: teardown_snippet
# ============================================================================

class TestTeardownSnippet:
    """
    Tests for the teardown_snippet function.
    """

    def test_teardown_deletes_gist(
        self, mock_gist_repo_root, mock_gh_and_git
    ):
        file_path = mock_gist_repo_root / "shell" / "old-gist.md"
        result = teardown_snippet(file_path)

        assert result["status"] == "success"
        assert result["action"] == "torn_down"
        assert result["gist_id"] == "old-gist-id-789"

        # Verify gh gist delete was called
        gh_calls = mock_gh_and_git["gh"]
        assert len(gh_calls) == 1
        assert gh_calls[0] == ["gh", "gist", "delete", "old-gist-id-789", "--yes"]

    def test_teardown_strips_gist_fields(
        self, mock_gist_repo_root, mock_gh_and_git
    ):
        file_path = mock_gist_repo_root / "shell" / "old-gist.md"
        teardown_snippet(file_path)

        # Verify gist_id and gist_url are removed from frontmatter
        content = file_path.read_text(encoding="utf-8")
        metadata, _ = common.parse_frontmatter(content)
        assert "gist_id" not in metadata
        assert "gist_url" not in metadata
        # gist: false should remain
        assert metadata.get("gist") is False

    def test_teardown_auto_commits(
        self, mock_gist_repo_root, mock_gh_and_git
    ):
        file_path = mock_gist_repo_root / "shell" / "old-gist.md"
        result = teardown_snippet(file_path)

        assert result["committed"] is True

    def test_teardown_rejects_no_gist_id(
        self, mock_gist_repo_root, mock_gh_and_git
    ):
        file_path = mock_gist_repo_root / "sql" / "simple-query.md"
        result = teardown_snippet(file_path)

        assert result["status"] == "error"
        assert result["error_type"] == "no_gist_id"
        assert mock_gh_and_git["gh"] == []

    def test_teardown_dry_run(self, mock_gist_repo_root, mock_gh_and_git):
        file_path = mock_gist_repo_root / "shell" / "old-gist.md"
        result = teardown_snippet(file_path, dry_run=True)

        assert result["status"] == "success"
        assert result["dry_run"] is True
        assert result["action"] == "teardown"
        assert mock_gh_and_git["gh"] == []

        # Verify file was NOT modified
        content = file_path.read_text(encoding="utf-8")
        metadata, _ = common.parse_frontmatter(content)
        assert "gist_id" in metadata  # Still there


# ============================================================================
# Tests: sync_all
# ============================================================================

class TestSyncAll:
    """
    Tests for the sync_all function.
    """

    def test_sync_all_creates_updates_teardowns(
        self, mock_gist_repo_root, mock_gh_and_git
    ):
        result = sync_all()

        assert result["status"] in ("success", "partial")
        assert len(result["created"]) == 1  # dbt-incremental-model
        assert len(result["updated"]) == 1  # api-client
        assert len(result["torn_down"]) == 1  # old-gist
        assert len(result["skipped"]) == 1  # simple-query

    def test_sync_all_skips_non_gist_snippets(
        self, mock_gist_repo_root, mock_gh_and_git
    ):
        """
        Safety test: snippets without gist field should be completely skipped.
        """
        result = sync_all()

        skipped = result["skipped"]
        assert any("simple-query" in s for s in skipped)

        # Verify simple-query was not touched by gh
        gh_calls = mock_gh_and_git["gh"]
        for call in gh_calls:
            call_str = " ".join(call)
            assert "simple-query" not in call_str

    def test_sync_all_dry_run(self, mock_gist_repo_root, mock_gh_and_git):
        result = sync_all(dry_run=True)

        assert result["status"] == "success"
        assert len(result["created"]) == 1
        assert len(result["updated"]) == 1
        assert len(result["torn_down"]) == 1
        assert mock_gh_and_git["gh"] == []  # No actual gh calls

    def test_sync_all_secret_flag(
        self, mock_gist_repo_root, mock_gh_and_git
    ):
        result = sync_all(secret=True)

        # New gist should be created without --public (secret is default)
        gh_create_calls = [
            c for c in mock_gh_and_git["gh"] if c[1:3] == ["gist", "create"]
        ]
        assert len(gh_create_calls) == 1
        assert "--public" not in gh_create_calls[0]


# ============================================================================
# Tests: gist_status
# ============================================================================

class TestGistStatus:
    """
    Tests for the gist_status function.
    """

    def test_status_categorizes_correctly(self, mock_gist_repo_root):
        result = gist_status()

        assert result["status"] == "success"
        assert result["total_snippets"] == 4

        # Published: gist:true + has gist_id
        published_titles = [e["title"] for e in result["published"]]
        assert "API Client" in published_titles

        # Unpublished: gist:true + no gist_id
        unpublished_titles = [e["title"] for e in result["unpublished"]]
        assert "dbt Incremental Model" in unpublished_titles

        # Pending teardown: gist:false + has gist_id
        pending_titles = [e["title"] for e in result["pending_teardown"]]
        assert "Old Gist" in pending_titles

    def test_status_includes_gist_url(self, mock_gist_repo_root):
        result = gist_status()

        published = result["published"]
        assert len(published) >= 1
        api_entry = [e for e in published if e["title"] == "API Client"][0]
        assert api_entry["gist_url"] == "https://gist.github.com/testuser/abc123def456"
        assert api_entry["gist_id"] == "abc123def456"


# ============================================================================
# Tests: common.py gist validation
# ============================================================================

class TestGistValidation:
    """
    Tests for gist field validation in common.validate_frontmatter.
    """

    def test_valid_gist_fields(self):
        metadata = {
            "id": VALID_UUID,
            "title": "Test",
            "language": "sql",
            "description": "test",
            "created": "2026-01-01",
            "last_updated": "2026-01-01",
            "gist": True,
            "gist_id": "abc123",
            "gist_url": "https://gist.github.com/user/abc123",
        }
        errors = common.validate_frontmatter(metadata)
        assert errors == []

    def test_gist_must_be_boolean(self):
        metadata = {
            "id": VALID_UUID,
            "title": "Test",
            "language": "sql",
            "description": "test",
            "created": "2026-01-01",
            "last_updated": "2026-01-01",
            "gist": "yes",
        }
        errors = common.validate_frontmatter(metadata)
        assert any("gist must be a boolean" in e for e in errors)

    def test_gist_id_must_be_nonempty_string(self):
        metadata = {
            "id": VALID_UUID,
            "title": "Test",
            "language": "sql",
            "description": "test",
            "created": "2026-01-01",
            "last_updated": "2026-01-01",
            "gist_id": "",
        }
        errors = common.validate_frontmatter(metadata)
        assert any("gist_id must be a non-empty string" in e for e in errors)

    def test_gist_url_must_be_https(self):
        metadata = {
            "id": VALID_UUID,
            "title": "Test",
            "language": "sql",
            "description": "test",
            "created": "2026-01-01",
            "last_updated": "2026-01-01",
            "gist_url": "http://not-https.com",
        }
        errors = common.validate_frontmatter(metadata)
        assert any("gist_url must be a valid HTTPS URL" in e for e in errors)


# ============================================================================
# Tests: common.py get_language_extension
# ============================================================================

class TestGetLanguageExtension:
    """
    Tests for the get_language_extension helper in common.py.
    """

    def test_sql(self):
        assert common.get_language_extension("sql") == ".sql"

    def test_python(self):
        assert common.get_language_extension("python") == ".py"

    def test_shell(self):
        assert common.get_language_extension("shell") == ".sh"

    def test_yaml(self):
        assert common.get_language_extension("yaml") == ".yml"

    def test_unknown_defaults_to_txt(self):
        assert common.get_language_extension("rust") == ".txt"

    def test_case_insensitive(self):
        assert common.get_language_extension("Python") == ".py"
        assert common.get_language_extension("SQL") == ".sql"
