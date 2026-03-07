"""
Tests for edit.py - snippet editing functionality.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from helpers import extract_json, run_cli
from edit import migrate_schema, programmatic_edit, main
from common import parse_frontmatter, get_today


# ============================================================================
# migrate_schema
# ============================================================================


class TestMigrateSchema:
    def test_removes_source(self):
        metadata = {"title": "Test", "source": "manual", "last_updated": "2026-03-01"}
        result, migrated = migrate_schema(metadata)
        assert "source" not in result
        assert migrated is True

    def test_adds_last_updated(self):
        metadata = {"title": "Test", "created": "2026-01-15"}
        result, migrated = migrate_schema(metadata)
        assert result["last_updated"] == "2026-01-15"
        assert migrated is True

    def test_both_migrations(self):
        metadata = {"title": "Test", "source": "manual", "created": "2026-01-15"}
        result, migrated = migrate_schema(metadata)
        assert "source" not in result
        assert "last_updated" in result
        assert migrated is True

    def test_no_change_needed(self):
        metadata = {"title": "Test", "last_updated": "2026-03-01"}
        result, migrated = migrate_schema(metadata)
        assert migrated is False


# ============================================================================
# programmatic_edit
# ============================================================================


class TestProgrammaticEdit:
    def test_success(self, mock_repo_root, mock_git):
        file_path = mock_repo_root / "sql" / "test-query.md"
        result = programmatic_edit(file_path, {"description": "Updated description"})
        assert result["status"] == "success"
        assert "description" in result["fields_updated"]
        assert result["last_updated"] == get_today()

        # Verify file was updated
        content = file_path.read_text()
        metadata, _ = parse_frontmatter(content)
        assert metadata["description"] == "Updated description"

    def test_parse_error(self, mock_repo_root):
        bad_file = mock_repo_root / "sql" / "bad.md"
        bad_file.write_text("no frontmatter here")
        result = programmatic_edit(bad_file, {"title": "New"})
        assert result["status"] == "error"
        assert result["error_type"] == "parse_error"

    def test_auto_migrates_old_schema(self, mock_repo_root, mock_git):
        file_path = mock_repo_root / "python" / "old-schema.md"
        result = programmatic_edit(file_path, {"description": "Updated"})
        assert result["status"] == "success"
        assert "schema_migration" in result["fields_updated"]

        # Verify source was removed
        content = file_path.read_text()
        metadata, _ = parse_frontmatter(content)
        assert "source" not in metadata
        assert "last_updated" in metadata


# ============================================================================
# CLI / main
# ============================================================================


class TestEditCLI:
    def test_json_updates(self, mock_repo_root, mock_git, capsys):
        updates = json.dumps({"description": "CLI updated"})
        code, output = run_cli(main, [
            "edit.py", "sql/test-query.md", "--json", updates, "--format", "json",
        ], capsys)
        assert code == 0
        assert output["status"] == "success"

    def test_update_field(self, mock_repo_root, mock_git, capsys):
        code, output = run_cli(main, [
            "edit.py", "sql/test-query.md", "--update-field", "description",
            "--value", "New desc", "--format", "json",
        ], capsys)
        assert code == 0
        assert output["status"] == "success"

    def test_add_tags(self, mock_repo_root, mock_git, capsys):
        code, output = run_cli(main, [
            "edit.py", "sql/test-query.md", "--add-tags", "new-tag,another",
            "--format", "json",
        ], capsys)
        assert code == 0
        assert output["status"] == "success"

        # Verify tags were added
        content = (mock_repo_root / "sql" / "test-query.md").read_text()
        metadata, _ = parse_frontmatter(content)
        assert "new-tag" in metadata["tags"]
        assert "another" in metadata["tags"]
