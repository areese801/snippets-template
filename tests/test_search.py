"""
Tests for search.py - snippet search functionality.
"""

import json
from unittest.mock import patch

import pytest

from constants import VALID_UUID
from helpers import extract_json, run_cli
from search import matches_filters, search_snippets, list_all_tags, main


# ============================================================================
# matches_filters - pure function, highest-value tests
# ============================================================================


class TestMatchesFilters:
    @pytest.fixture
    def sample_metadata(self):
        return {
            "title": "dbt Incremental Model",
            "language": "sql",
            "tags": ["dbt", "incremental", "sql"],
            "description": "Standard incremental pattern",
            "created": "2026-02-01",
            "last_updated": "2026-03-01",
        }

    @pytest.fixture
    def sample_code(self):
        return "SELECT * FROM {{ ref('stg_orders') }} WHERE updated_at > '2026-01-01'"

    def test_no_filters(self, sample_metadata, sample_code):
        assert matches_filters(sample_metadata, sample_code, {}) is True

    def test_tag_match(self, sample_metadata, sample_code):
        assert matches_filters(sample_metadata, sample_code, {"tags": ["dbt"]}) is True

    def test_tag_no_match(self, sample_metadata, sample_code):
        assert (
            matches_filters(sample_metadata, sample_code, {"tags": ["python"]})
            is False
        )

    def test_multiple_tags_and(self, sample_metadata, sample_code):
        assert (
            matches_filters(
                sample_metadata, sample_code, {"tags": ["dbt", "incremental"]}
            )
            is True
        )
        assert (
            matches_filters(
                sample_metadata, sample_code, {"tags": ["dbt", "python"]}
            )
            is False
        )

    def test_language_match(self, sample_metadata, sample_code):
        assert (
            matches_filters(sample_metadata, sample_code, {"language": "sql"}) is True
        )

    def test_language_no_match(self, sample_metadata, sample_code):
        assert (
            matches_filters(sample_metadata, sample_code, {"language": "python"})
            is False
        )

    def test_terms_all_match(self, sample_metadata, sample_code):
        assert (
            matches_filters(
                sample_metadata, sample_code, {"terms": "dbt incremental"}
            )
            is True
        )

    def test_terms_partial_no_match(self, sample_metadata, sample_code):
        assert (
            matches_filters(
                sample_metadata, sample_code, {"terms": "dbt nonexistent"}
            )
            is False
        )

    def test_title_contains(self, sample_metadata, sample_code):
        assert (
            matches_filters(
                sample_metadata, sample_code, {"title_contains": "incremental"}
            )
            is True
        )
        assert (
            matches_filters(
                sample_metadata, sample_code, {"title_contains": "python"}
            )
            is False
        )

    def test_description_contains(self, sample_metadata, sample_code):
        assert (
            matches_filters(
                sample_metadata,
                sample_code,
                {"description_contains": "incremental pattern"},
            )
            is True
        )

    def test_code_regex_match(self, sample_metadata, sample_code):
        assert (
            matches_filters(
                sample_metadata, sample_code, {"query": r"SELECT.*FROM"}
            )
            is True
        )

    def test_code_regex_no_match(self, sample_metadata, sample_code):
        assert (
            matches_filters(
                sample_metadata, sample_code, {"query": r"DELETE FROM"}
            )
            is False
        )

    def test_invalid_regex(self, sample_metadata, sample_code):
        # Invalid regex should return False (not crash)
        assert (
            matches_filters(sample_metadata, sample_code, {"query": "[invalid"})
            is False
        )

    def test_created_after(self, sample_metadata, sample_code):
        assert (
            matches_filters(
                sample_metadata, sample_code, {"created_after": "2026-01-01"}
            )
            is True
        )
        assert (
            matches_filters(
                sample_metadata, sample_code, {"created_after": "2026-12-01"}
            )
            is False
        )

    def test_recently_updated(self, sample_metadata, sample_code):
        # With a very large window, should match
        assert (
            matches_filters(
                sample_metadata, sample_code, {"recently_updated_days": 99999}
            )
            is True
        )
        # With 1 day window on an old date, should not match
        old_metadata = dict(sample_metadata, last_updated="2020-01-01")
        assert (
            matches_filters(
                old_metadata, sample_code, {"recently_updated_days": 1}
            )
            is False
        )


# ============================================================================
# search_snippets
# ============================================================================


class TestSearchSnippets:
    def test_returns_results(self, mock_repo_root):
        results = search_snippets({"language": "sql"})
        assert len(results) >= 1
        assert "metadata" in results[0]
        assert "preview" in results[0]
        assert "relative_path" in results[0]

    def test_excludes_non_snippet_files(self, mock_repo_root):
        # Create a README that should be excluded
        (mock_repo_root / "README.md").write_text("# README")
        results = search_snippets({})
        paths = [r["relative_path"] for r in results]
        assert not any("README.md" in p for p in paths)

    def test_preview_format(self, mock_repo_root):
        results = search_snippets({})
        for r in results:
            assert isinstance(r["preview"], str)
            assert isinstance(r["line_count"], int)


# ============================================================================
# list_all_tags
# ============================================================================


class TestListAllTags:
    def test_returns_tag_counts(self, mock_repo_root):
        tags = list_all_tags()
        assert isinstance(tags, dict)
        assert "sql" in tags
        assert tags["sql"] >= 1


# ============================================================================
# CLI / main
# ============================================================================


class TestSearchCLI:
    def test_tag_json(self, mock_repo_root, capsys):
        code, output = run_cli(main, ["search.py", "--tag", "sql", "--format", "json"], capsys)
        assert code == 0
        assert output["status"] == "success"
        assert output["count"] >= 1

    def test_list_tags(self, mock_repo_root, capsys):
        code, output = run_cli(main, ["search.py", "--list-tags", "--format", "json"], capsys)
        assert code == 0
        assert "sql" in output

    def test_positional_terms(self, mock_repo_root, capsys):
        code, output = run_cli(main, ["search.py", "SELECT", "--format", "json"], capsys)
        assert code == 0
        assert output["status"] == "success"

    def test_combined_filters(self, mock_repo_root, capsys):
        code, output = run_cli(main, [
            "search.py", "--tag", "sql", "--language", "sql", "--format", "json",
        ], capsys)
        assert code == 0
        assert output["status"] == "success"
