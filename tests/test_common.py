"""
Tests for common.py shared utilities.
"""

import re
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from constants import VALID_UUID, SECOND_UUID

import common
from common import (
    Colors,
    EXCLUDED_FILES,
    LANGUAGE_DIRECTORY_MAP,
    SUPPORTED_LANGUAGES,
    copy_to_clipboard,
    delete_snippet,
    detect_language,
    duplicate_snippet,
    find_snippet_by_id,
    find_snippet_files,
    generate_uuid,
    get_all_snippet_ids,
    get_all_tags,
    get_language_directory,
    get_recent_snippets,
    get_today,
    merge_tags,
    normalize_tag,
    parse_frontmatter,
    remove_tag,
    rename_tag,
    serialize_frontmatter,
    slugify,
    strip_code_fences,
    suggest_tags,
    update_frontmatter_field,
    validate_date,
    validate_frontmatter,
    git_add,
    git_commit,
    git_status_clean,
    log_info,
    log_success,
    log_warn,
    log_error,
)


# ============================================================================
# Logging
# ============================================================================


class TestLogging:
    def test_log_info(self, capsys):
        log_info("test message")
        out = capsys.readouterr().out
        assert "test message" in out
        assert Colors.BLUE in out

    def test_log_success(self, capsys):
        log_success("ok")
        out = capsys.readouterr().out
        assert "ok" in out
        assert Colors.GREEN in out

    def test_log_warn(self, capsys):
        log_warn("warning")
        out = capsys.readouterr().out
        assert "warning" in out
        assert Colors.YELLOW in out

    def test_log_error(self, capsys):
        log_error("error")
        err = capsys.readouterr().err
        assert "error" in err
        assert Colors.RED in err


# ============================================================================
# Clipboard
# ============================================================================


class TestClipboard:
    def test_copy_to_clipboard_macos(self, mock_clipboard):
        with patch("platform.system", return_value="Darwin"):
            result = copy_to_clipboard("hello world")
        assert result is True
        assert mock_clipboard["text"] == "hello world"

    def test_copy_to_clipboard_unsupported(self, monkeypatch):
        with patch("platform.system", return_value="Windows"):
            result = copy_to_clipboard("text")
        assert result is False

    def test_copy_to_clipboard_exception(self, monkeypatch):
        def raise_exc(*args, **kwargs):
            raise OSError("fail")

        monkeypatch.setattr(subprocess, "Popen", raise_exc)
        with patch("platform.system", return_value="Darwin"):
            result = copy_to_clipboard("text")
        assert result is False


# ============================================================================
# strip_code_fences
# ============================================================================


class TestStripCodeFences:
    def test_with_language(self):
        code = "```python\nprint('hi')\n```"
        assert strip_code_fences(code) == "print('hi')"

    def test_without_language(self):
        code = "```\nSELECT 1;\n```"
        assert strip_code_fences(code) == "SELECT 1;"

    def test_no_fences(self):
        code = "SELECT 1;"
        assert strip_code_fences(code) == "SELECT 1;"

    def test_single_line(self):
        code = "SELECT 1;"
        assert strip_code_fences(code) == "SELECT 1;"


# ============================================================================
# Frontmatter
# ============================================================================


class TestParseFrontmatter:
    def test_valid(self, valid_metadata):
        content = serialize_frontmatter(valid_metadata) + "\nSELECT 1;"
        metadata, body = parse_frontmatter(content)
        assert metadata["title"] == "Test Snippet"
        assert body == "SELECT 1;"

    def test_empty_body(self, valid_metadata):
        content = serialize_frontmatter(valid_metadata)
        metadata, body = parse_frontmatter(content)
        assert metadata["title"] == "Test Snippet"
        assert body == ""

    def test_no_delimiter(self):
        with pytest.raises(ValueError, match="does not start with frontmatter"):
            parse_frontmatter("no frontmatter here")

    def test_missing_closing(self):
        with pytest.raises(ValueError, match="missing closing delimiter"):
            parse_frontmatter("---\ntitle: test\n")

    def test_invalid_yaml(self):
        with pytest.raises(ValueError, match="Invalid YAML"):
            parse_frontmatter("---\n: :\n  bad: [yaml\n---\n")


class TestSerializeFrontmatter:
    def test_round_trip(self, valid_metadata):
        serialized = serialize_frontmatter(valid_metadata)
        metadata, _ = parse_frontmatter(serialized + "\ncode")
        assert metadata["title"] == valid_metadata["title"]
        assert metadata["language"] == valid_metadata["language"]

    def test_starts_and_ends_with_delimiters(self, valid_metadata):
        result = serialize_frontmatter(valid_metadata)
        assert result.startswith("---\n")
        assert result.endswith("---\n")


class TestUpdateFrontmatterField:
    def test_existing_field(self, valid_metadata):
        content = serialize_frontmatter(valid_metadata) + "\nSELECT 1;"
        updated = update_frontmatter_field(content, "title", "New Title")
        metadata, _ = parse_frontmatter(updated)
        assert metadata["title"] == "New Title"

    def test_new_field(self, valid_metadata):
        content = serialize_frontmatter(valid_metadata) + "\nSELECT 1;"
        updated = update_frontmatter_field(content, "reviewed", True)
        metadata, _ = parse_frontmatter(updated)
        assert metadata["reviewed"] is True


class TestValidateFrontmatter:
    def test_valid(self, valid_metadata):
        errors = validate_frontmatter(valid_metadata)
        assert errors == []

    def test_missing_fields(self):
        errors = validate_frontmatter({})
        assert len(errors) >= 5  # title, language, description, created, last_updated

    def test_invalid_date(self, valid_metadata):
        valid_metadata["created"] = "not-a-date"
        errors = validate_frontmatter(valid_metadata)
        assert any("Invalid date" in e for e in errors)

    def test_tags_not_list(self, valid_metadata):
        valid_metadata["tags"] = "not-a-list"
        errors = validate_frontmatter(valid_metadata)
        assert any("Tags must be a list" in e for e in errors)

    def test_empty_language(self, valid_metadata):
        valid_metadata["language"] = ""
        errors = validate_frontmatter(valid_metadata)
        assert any("non-empty string" in e for e in errors)


# ============================================================================
# Language
# ============================================================================


class TestLanguageDirectory:
    @pytest.mark.parametrize(
        "lang,expected",
        [
            ("sql", "sql"),
            ("python", "python"),
            ("shell", "shell"),
            ("bash", "shell"),
            ("yaml", "config"),
            ("json", "config"),
            ("markdown", "prompts"),
            ("text", "prompts"),
        ],
    )
    def test_known_mappings(self, lang, expected):
        assert get_language_directory(lang, auto_create=False) == expected

    def test_unknown_without_auto_create(self):
        result = get_language_directory("rust", auto_create=False)
        assert result == "rust"

    def test_unknown_with_auto_create(self, mock_repo_root):
        result = get_language_directory("go", auto_create=True)
        assert result == "go"
        assert (mock_repo_root / "go").exists()


class TestDetectLanguage:
    def test_sql(self):
        assert detect_language("SELECT * FROM users WHERE id = 1") == "sql"

    def test_python(self):
        assert detect_language("import os\ndef main():") == "python"

    def test_shell(self):
        assert detect_language("#!/bin/bash\necho hi") == "shell"

    def test_json(self):
        assert detect_language('{"key": "value"}') == "json"

    def test_with_hint(self):
        assert detect_language("some code", hint="python") == "python"

    def test_default_text(self):
        assert detect_language("random stuff here 12345") == "text"

    def test_supported_languages_constant(self):
        assert "sql" in SUPPORTED_LANGUAGES
        assert "python" in SUPPORTED_LANGUAGES
        assert "shell" in SUPPORTED_LANGUAGES


# ============================================================================
# File Operations
# ============================================================================


class TestSlugify:
    def test_basic(self):
        assert slugify("Hello World") == "hello-world"

    def test_special_chars(self):
        assert slugify("Hello! @World#") == "hello-world"

    def test_underscores(self):
        assert slugify("my_snippet_name") == "my-snippet-name"

    def test_multiple_hyphens(self):
        assert slugify("hello---world") == "hello-world"

    def test_leading_trailing(self):
        assert slugify("--hello--") == "hello"


class TestFindSnippetFiles:
    def test_finds_md_files(self, snippet_repo):
        files = find_snippet_files(snippet_repo, "*.md")
        filenames = {f.name for f in files}
        assert "test-query.md" in filenames
        assert "api-client.md" in filenames
        assert "old-schema.md" in filenames

    def test_sorted_by_mtime(self, snippet_repo):
        files = find_snippet_files(snippet_repo, "*.md")
        # Most recently modified first
        for i in range(len(files) - 1):
            assert files[i].stat().st_mtime >= files[i + 1].stat().st_mtime


# ============================================================================
# Git Operations
# ============================================================================


class TestGitOps:
    def test_git_add_success(self, mock_git, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("test")
        assert git_add(f) is True
        assert any("add" in cmd for cmd in mock_git)

    def test_git_add_failure(self, monkeypatch):
        def fail(*args, **kwargs):
            raise subprocess.CalledProcessError(1, "git", stderr="error")

        monkeypatch.setattr(subprocess, "run", fail)
        assert git_add(Path("/fake")) is False

    def test_git_commit_success(self, mock_git):
        assert git_commit("test commit") is True
        assert any("commit" in cmd for cmd in mock_git)

    def test_git_commit_failure(self, monkeypatch):
        def fail(*args, **kwargs):
            raise subprocess.CalledProcessError(1, "git", stderr="error")

        monkeypatch.setattr(subprocess, "run", fail)
        assert git_commit("msg") is False

    def test_git_status_clean_true(self, mock_git):
        assert git_status_clean() is True

    def test_git_status_clean_false(self, monkeypatch):
        mock_result = MagicMock()
        mock_result.stdout = " M file.txt\n"
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: mock_result)
        assert git_status_clean() is False


# ============================================================================
# Date Operations
# ============================================================================


class TestDateOps:
    def test_get_today_format(self):
        today = get_today()
        assert re.match(r"\d{4}-\d{2}-\d{2}", today)

    def test_validate_date_valid(self):
        assert validate_date("2026-03-01") is True

    def test_validate_date_invalid(self):
        assert validate_date("2026-13-01") is False

    def test_validate_date_nonsense(self):
        assert validate_date("not-a-date") is False


# ============================================================================
# UUID Operations
# ============================================================================


class TestUUIDOps:
    def test_generate_uuid_format(self):
        uid = generate_uuid()
        assert re.match(
            r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
            uid,
        )

    def test_find_snippet_by_id_found(self, mock_repo_root):
        result = find_snippet_by_id(VALID_UUID)
        assert result is not None
        assert result.name == "test-query.md"

    def test_find_snippet_by_id_not_found(self, mock_repo_root):
        result = find_snippet_by_id("00000000-0000-0000-0000-000000000000")
        assert result is None

    def test_get_all_snippet_ids(self, mock_repo_root):
        ids = get_all_snippet_ids()
        id_values = [s["id"] for s in ids]
        assert VALID_UUID in id_values
        assert SECOND_UUID in id_values


# ============================================================================
# Tag Operations
# ============================================================================


class TestNormalizeTag:
    def test_basic(self):
        assert normalize_tag("Hello World") == "hello-world"

    def test_already_normalized(self):
        assert normalize_tag("dbt") == "dbt"


class TestSuggestTags:
    def test_python_imports(self):
        tags = suggest_tags("import requests\ndef fetch():", "python")
        assert "python" in tags
        assert "requests" in tags

    def test_sql_patterns(self):
        tags = suggest_tags("SELECT * FROM users JOIN orders ON", "sql")
        assert "sql" in tags
        assert "query" in tags
        assert "join" in tags

    def test_shell_patterns(self):
        tags = suggest_tags("docker build -t myapp .", "shell")
        assert "shell" in tags
        assert "docker" in tags

    def test_always_includes_language(self):
        tags = suggest_tags("random code", "text")
        assert "text" in tags


class TestGetAllTags:
    def test_returns_counts(self, mock_repo_root):
        tags = get_all_tags()
        assert isinstance(tags, dict)
        assert "sql" in tags
        assert "python" in tags


class TestRenameTag:
    def test_rename(self, mock_repo_root, mock_git):
        result = rename_tag("sql", "structured-query-language")
        assert result["status"] == "success"
        assert result["count"] >= 1


class TestMergeTags:
    def test_merge(self, mock_repo_root, mock_git):
        result = merge_tags(["sql", "test"], "database")
        assert result["status"] == "success"


class TestRemoveTag:
    def test_remove(self, mock_repo_root, mock_git):
        result = remove_tag("test")
        assert result["status"] == "success"
        assert result["count"] >= 1


# ============================================================================
# Snippet File Operations
# ============================================================================


class TestGetRecentSnippets:
    def test_returns_snippets(self, mock_repo_root):
        results = get_recent_snippets(limit=10)
        assert len(results) >= 2
        assert "metadata" in results[0]
        assert "preview" in results[0]

    def test_respects_limit(self, mock_repo_root):
        results = get_recent_snippets(limit=1)
        assert len(results) == 1


class TestDeleteSnippet:
    def test_not_found(self, mock_repo_root):
        result = delete_snippet(mock_repo_root / "nonexistent.md")
        assert result["status"] == "error"
        assert result["error_type"] == "file_not_found"

    def test_success(self, mock_repo_root, mock_git):
        file_path = mock_repo_root / "sql" / "test-query.md"
        result = delete_snippet(file_path, commit=True)
        assert result["status"] == "success"


class TestDuplicateSnippet:
    def test_success(self, mock_repo_root, mock_git):
        source = mock_repo_root / "sql" / "test-query.md"
        result = duplicate_snippet(source, "Duplicated Query")
        assert result["status"] == "success"
        assert "duplicated-query.md" in result["filename"]

    def test_source_not_found(self, mock_repo_root):
        result = duplicate_snippet(mock_repo_root / "nope.md", "New Title")
        assert result["status"] == "error"
        assert result["error_type"] == "file_not_found"

    def test_file_already_exists(self, mock_repo_root, mock_git):
        source = mock_repo_root / "sql" / "test-query.md"
        # First duplicate succeeds
        duplicate_snippet(source, "Test Query Copy")
        # Create a file at the expected path to trigger conflict
        copy_path = mock_repo_root / "sql" / "test-query-copy.md"
        copy_path.write_text("exists")
        result = duplicate_snippet(source, "Test Query Copy")
        assert result["status"] == "error"
        assert result["error_type"] == "file_exists"
