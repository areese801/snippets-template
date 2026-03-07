"""
Tests for audit.py - metadata auditing functionality.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from constants import VALID_UUID
from helpers import extract_json, run_cli
from audit import detect_issues, scan_all_snippets, migrate_schema_all, add_uuids_all, main
from common import parse_frontmatter, SUPPORTED_LANGUAGES


# ============================================================================
# detect_issues
# ============================================================================


class TestDetectIssues:
    def test_clean(self, valid_metadata):
        issues = detect_issues(valid_metadata, Path("test.md"))
        assert issues == []

    def test_missing_id(self, valid_metadata):
        del valid_metadata["id"]
        issues = detect_issues(valid_metadata, Path("test.md"))
        assert "missing_id" in issues

    def test_old_schema_has_source(self, valid_metadata):
        valid_metadata["source"] = "manual"
        issues = detect_issues(valid_metadata, Path("test.md"))
        assert "old_schema_has_source" in issues

    def test_missing_last_updated(self, valid_metadata):
        del valid_metadata["last_updated"]
        issues = detect_issues(valid_metadata, Path("test.md"))
        assert "old_schema_missing_last_updated" in issues
        assert "missing_last_updated" in issues

    def test_missing_title(self, valid_metadata):
        del valid_metadata["title"]
        issues = detect_issues(valid_metadata, Path("test.md"))
        assert "missing_title" in issues

    def test_invalid_language(self, valid_metadata):
        valid_metadata["language"] = "brainfuck"
        issues = detect_issues(valid_metadata, Path("test.md"))
        assert "invalid_language" in issues

    def test_invalid_date(self, valid_metadata):
        valid_metadata["created"] = "not-a-date"
        issues = detect_issues(valid_metadata, Path("test.md"))
        assert "invalid_date_created" in issues

    def test_malformed_tags(self, valid_metadata):
        valid_metadata["tags"] = "not-a-list"
        issues = detect_issues(valid_metadata, Path("test.md"))
        assert "malformed_tags" in issues

    def test_empty_tags(self, valid_metadata):
        valid_metadata["tags"] = []
        issues = detect_issues(valid_metadata, Path("test.md"))
        assert "missing_tags" in issues

    def test_multiple_issues(self):
        metadata = {"source": "old"}
        issues = detect_issues(metadata, Path("test.md"))
        assert "missing_id" in issues
        assert "old_schema_has_source" in issues
        assert "missing_title" in issues
        assert len(issues) >= 3


# ============================================================================
# scan_all_snippets
# ============================================================================


class TestScanAllSnippets:
    def test_returns_totals(self, mock_repo_root):
        result = scan_all_snippets()
        assert result["status"] == "success"
        assert result["total_snippets"] >= 2
        assert isinstance(result["breakdown"], dict)

    def test_directory_filter(self, mock_repo_root):
        result = scan_all_snippets(directory="sql")
        assert result["status"] == "success"
        # Only sql snippets
        assert result["total_snippets"] >= 1

    def test_excludes_readme(self, mock_repo_root):
        (mock_repo_root / "README.md").write_text("# README\n")
        result = scan_all_snippets()
        paths = [s["file_path"] for s in result["snippets_with_issues"]]
        assert not any("README.md" in p for p in paths)


# ============================================================================
# migrate_schema_all
# ============================================================================


class TestMigrateSchemaAll:
    def test_migrates_old_files(self, mock_repo_root):
        result = migrate_schema_all()
        assert result["status"] == "success"
        assert result["migrated_count"] >= 1
        # The old-schema.md should have been migrated
        assert any("old-schema.md" in f for f in result["migrated_files"])

        # Verify the file was actually updated
        content = (mock_repo_root / "python" / "old-schema.md").read_text()
        metadata, _ = parse_frontmatter(content)
        assert "source" not in metadata
        assert "last_updated" in metadata
        assert "id" in metadata

    def test_idempotent(self, mock_repo_root):
        migrate_schema_all()
        result = migrate_schema_all()
        assert result["migrated_count"] == 0


# ============================================================================
# add_uuids_all
# ============================================================================


class TestAddUuidsAll:
    def test_adds_uuids(self, mock_repo_root):
        result = add_uuids_all()
        assert result["status"] == "success"
        # old-schema.md is missing an id
        assert result["updated_count"] >= 1

        # Verify UUID was added
        content = (mock_repo_root / "python" / "old-schema.md").read_text()
        metadata, _ = parse_frontmatter(content)
        assert "id" in metadata
        assert len(metadata["id"]) == 36  # UUID4 format


# ============================================================================
# CLI / main
# ============================================================================


class TestAuditCLI:
    def test_scan_json(self, mock_repo_root, capsys):
        code, output = run_cli(main, ["audit.py", "--scan", "--format", "json"], capsys)
        assert code == 0
        assert output["status"] == "success"
        assert "total_snippets" in output

    def test_add_uuids_json(self, mock_repo_root, capsys):
        code, output = run_cli(main, ["audit.py", "--add-uuids", "--format", "json"], capsys)
        assert code == 0
        assert output["status"] == "success"
