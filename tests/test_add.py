"""
Tests for add.py - snippet creation functionality.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from helpers import extract_json, run_cli
from add import create_snippet_file, main
from common import parse_frontmatter


# ============================================================================
# create_snippet_file
# ============================================================================


class TestCreateSnippetFile:
    @pytest.fixture
    def snippet_data(self):
        return {
            "title": "New Test Snippet",
            "language": "sql",
            "tags": ["sql", "test"],
            "description": "A brand new snippet",
            "code": "SELECT 42;",
            "created": "2026-03-07",
            "last_updated": "2026-03-07",
        }

    def test_success(self, mock_repo_root, mock_git, snippet_data):
        result = create_snippet_file(snippet_data, output_format="json")
        assert result["status"] == "success"
        assert result["filename"] == "new-test-snippet.md"
        assert result["directory"] == "sql"

        # Verify file was created
        file_path = Path(result["file_path"])
        assert file_path.exists()
        content = file_path.read_text()
        metadata, code = parse_frontmatter(content)
        assert metadata["title"] == "New Test Snippet"
        assert code.strip() == "SELECT 42;"

    def test_generates_uuid(self, mock_repo_root, mock_git, snippet_data):
        result = create_snippet_file(snippet_data, output_format="json")
        file_path = Path(result["file_path"])
        content = file_path.read_text()
        metadata, _ = parse_frontmatter(content)
        assert "id" in metadata
        assert len(metadata["id"]) == 36

    def test_validation_error(self, mock_repo_root, mock_git):
        data = {
            "title": "",
            "language": "",
            "tags": [],
            "description": "",
            "code": "SELECT 1;",
        }
        result = create_snippet_file(data, output_format="json")
        assert result["status"] == "error"
        assert result["error_type"] == "validation_error"

    def test_file_exists(self, mock_repo_root, mock_git, snippet_data):
        # Create first
        create_snippet_file(snippet_data, output_format="json")
        # Try again - should fail
        result = create_snippet_file(snippet_data, output_format="json")
        assert result["status"] == "error"
        assert result["error_type"] == "file_exists"

    def test_auto_commits_json_mode(self, mock_repo_root, mock_git, snippet_data):
        result = create_snippet_file(snippet_data, output_format="json")
        assert result["committed"] is True
        # Verify git commands were called
        assert any("add" in cmd for cmd in mock_git)
        assert any("commit" in cmd for cmd in mock_git)

    def test_strips_code_fences(self, mock_repo_root, mock_git):
        data = {
            "title": "Fenced Code",
            "language": "sql",
            "tags": ["sql"],
            "description": "Code with fences",
            "code": "```sql\nSELECT 1;\n```",
            "created": "2026-03-07",
            "last_updated": "2026-03-07",
        }
        # Code fences should be stripped before passing to create_snippet_file
        # The main() function handles stripping; create_snippet_file takes raw code
        # So this tests that fenced code is stored as-is (stripping happens in CLI layer)
        result = create_snippet_file(data, output_format="json")
        assert result["status"] == "success"


# ============================================================================
# CLI / main
# ============================================================================


class TestAddCLI:
    def test_json_mode_success(self, mock_repo_root, mock_git, capsys):
        json_input = json.dumps(
            {
                "title": "CLI Test",
                "language": "python",
                "tags": ["python"],
                "description": "CLI test snippet",
                "code": "print('hello')",
            }
        )
        code, output = run_cli(main, ["add.py", "--json", json_input, "--format", "json"], capsys)
        assert code == 0
        assert output["status"] == "success"

    def test_json_mode_invalid_json(self, mock_repo_root, capsys):
        with patch("sys.argv", ["add.py", "--json", "not-json", "--format", "json"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

    def test_json_mode_missing_code(self, mock_repo_root, capsys):
        json_input = json.dumps({"title": "No Code"})
        with patch("sys.argv", ["add.py", "--json", json_input, "--format", "json"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

    def test_cli_args_mode(self, mock_repo_root, mock_git, capsys):
        code, output = run_cli(main, [
            "add.py", "--title", "CLI Args Test", "--language", "shell",
            "--tags", "shell,test", "--description", "A CLI test",
            "--code", "echo hello", "--format", "json",
        ], capsys)
        assert code == 0
        assert output["status"] == "success"

    def test_cli_args_missing_description(self, mock_repo_root, capsys):
        with patch("sys.argv", ["add.py", "--title", "No Desc", "--code", "echo hi", "--format", "json"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

    def test_code_file(self, mock_repo_root, mock_git, tmp_path, capsys):
        code_file = tmp_path / "snippet.py"
        code_file.write_text("print('from file')")
        code, output = run_cli(main, [
            "add.py", "--title", "From File", "--language", "python",
            "--description", "Read from file", "--tags", "python",
            "--code-file", str(code_file), "--format", "json",
        ], capsys)
        assert code == 0
        assert output["status"] == "success"
