"""
Tests for notes.py — Obsidian notes search functionality.
"""

import json
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from helpers import run_cli
from notes import (
    check_obsidian_available,
    run_obsidian_cmd,
    KNOWN_STDERR_PATTERNS,
    discover_vaults,
    get_vault_ignore_filters,
    build_obsidian_uri,
    filter_ignored_paths,
    cmd_search,
    cmd_read,
    cmd_tags,
    main,
)


# ============================================================================
# check_obsidian_available
# ============================================================================


class TestCheckObsidianAvailable:
    def test_available(self):
        with patch("shutil.which", return_value="/usr/local/bin/obsidian"):
            available, msg = check_obsidian_available()
            assert available is True
            assert msg == ""

    def test_not_available(self):
        with patch("shutil.which", return_value=None):
            available, msg = check_obsidian_available()
            assert available is False
            assert "not found" in msg.lower()
            assert "https://help.obsidian.md/cli" in msg


# ============================================================================
# run_obsidian_cmd
# ============================================================================


class TestRunObsidianCmd:
    def test_returns_stdout(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "line1\nline2\n"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            output = run_obsidian_cmd(["vault"])
            assert output == "line1\nline2"

    def test_filters_known_stderr_noise(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "result\n"
        mock_result.stderr = (
            "2026-03-15 Loading updated app package /some/path\n"
            "Your Obsidian installer is out of date. "
            "Please download the latest installer\n"
        )

        with patch("subprocess.run", return_value=mock_result):
            output = run_obsidian_cmd(["search", 'query="test"'])
            assert output == "result"

    def test_raises_on_real_stderr(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Error: vault not found\n"

        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="vault not found"):
                run_obsidian_cmd(["search", 'query="test"'])

    def test_timeout(self):
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="obsidian", timeout=5),
        ):
            with pytest.raises(subprocess.TimeoutExpired):
                run_obsidian_cmd(["search", 'query="test"'], timeout=5)


# ============================================================================
# discover_vaults
# ============================================================================


class TestDiscoverVaults:
    def test_parses_tsv_output(self):
        tsv = "My Vault\t/Users/areese/Obsidian/My Vault\nRemote Vault\t/path/to/remote"
        with patch("notes.run_obsidian_cmd", return_value=tsv):
            vaults = discover_vaults()
            assert len(vaults) == 2
            assert vaults[0] == {
                "name": "My Vault",
                "path": "/Users/areese/Obsidian/My Vault",
            }
            assert vaults[1] == {"name": "Remote Vault", "path": "/path/to/remote"}

    def test_empty_output(self):
        with patch("notes.run_obsidian_cmd", return_value=""):
            vaults = discover_vaults()
            assert vaults == []


# ============================================================================
# get_vault_ignore_filters
# ============================================================================


class TestGetVaultIgnoreFilters:
    def test_reads_filters(self, tmp_path):
        obsidian_dir = tmp_path / ".obsidian"
        obsidian_dir.mkdir()
        app_json = obsidian_dir / "app.json"
        app_json.write_text(
            json.dumps(
                {
                    "userIgnoreFilters": ["_ARCHIVE/", "_PERSONAL/EVERNOTE/"],
                    "otherSetting": True,
                }
            )
        )
        filters = get_vault_ignore_filters(str(tmp_path))
        assert filters == ["_ARCHIVE/", "_PERSONAL/EVERNOTE/"]

    def test_no_filters_key(self, tmp_path):
        obsidian_dir = tmp_path / ".obsidian"
        obsidian_dir.mkdir()
        app_json = obsidian_dir / "app.json"
        app_json.write_text(json.dumps({"otherSetting": True}))
        filters = get_vault_ignore_filters(str(tmp_path))
        assert filters == []

    def test_no_app_json(self, tmp_path):
        filters = get_vault_ignore_filters(str(tmp_path))
        assert filters == []


# ============================================================================
# build_obsidian_uri
# ============================================================================


class TestBuildObsidianUri:
    def test_basic(self):
        uri = build_obsidian_uri("My Vault", "folder/note.md")
        assert uri == "obsidian://open?vault=My%20Vault&file=folder/note"

    def test_strips_md_extension(self):
        uri = build_obsidian_uri("Vault", "note.md")
        assert "note.md" not in uri
        assert "note" in uri

    def test_url_encodes_special_chars(self):
        uri = build_obsidian_uri("My Vault", "WORK/Cinch/Postgres CDC & S3.md")
        assert "%26" in uri or "&" not in uri.split("?", 1)[1].split("file=")[1]


# ============================================================================
# filter_ignored_paths
# ============================================================================


class TestFilterIgnoredPaths:
    def test_filters_matching_prefixes(self):
        paths = ["_ARCHIVE/old.md", "notes/keep.md", "_PERSONAL/EVERNOTE/note.md"]
        filters = ["_ARCHIVE/", "_PERSONAL/EVERNOTE/"]
        assert filter_ignored_paths(paths, filters) == ["notes/keep.md"]

    def test_no_filters(self):
        paths = ["a.md", "b.md"]
        assert filter_ignored_paths(paths, []) == ["a.md", "b.md"]

    def test_empty_paths(self):
        assert filter_ignored_paths([], ["_ARCHIVE/"]) == []


# ============================================================================
# cmd_search
# ============================================================================


class TestCmdSearch:
    @pytest.fixture
    def mock_vaults(self):
        return [
            {"name": "My Vault", "path": "/tmp/vault1"},
            {"name": "Remote Vault", "path": "/tmp/vault2"},
        ]

    def test_basic_search_single_vault(self, mock_vaults):
        search_output = "folder/note-one.md\nfolder/note-two.md"

        with patch("notes.discover_vaults", return_value=mock_vaults):
            with patch("notes.get_vault_ignore_filters", return_value=[]):
                with patch("notes.run_obsidian_cmd", return_value=search_output):
                    result = cmd_search("postgres", vault_filter="My Vault")
                    assert result["status"] == "success"
                    assert result["count"] == 2
                    assert result["results"][0]["vault"] == "My Vault"
                    assert result["results"][0]["file"] == "folder/note-one.md"
                    assert result["results"][0]["title"] == "note-one"
                    assert "obsidian://" in result["results"][0]["uri"]

    def test_search_all_vaults(self, mock_vaults):
        def fake_cmd(args, **kwargs):
            if "vault=My Vault" in " ".join(args):
                return "note-a.md"
            return "note-b.md"

        with patch("notes.discover_vaults", return_value=mock_vaults):
            with patch("notes.get_vault_ignore_filters", return_value=[]):
                with patch("notes.run_obsidian_cmd", side_effect=fake_cmd):
                    result = cmd_search("test")
                    assert result["count"] == 2
                    vaults = {r["vault"] for r in result["results"]}
                    assert "My Vault" in vaults
                    assert "Remote Vault" in vaults

    def test_search_no_results(self, mock_vaults):
        with patch("notes.discover_vaults", return_value=mock_vaults):
            with patch("notes.get_vault_ignore_filters", return_value=[]):
                with patch("notes.run_obsidian_cmd", return_value=""):
                    result = cmd_search("nonexistent")
                    assert result["status"] == "success"
                    assert result["count"] == 0

    def test_search_respects_ignore_filters(self, mock_vaults):
        search_output = "_ARCHIVE/old.md\nnotes/keep.md"

        with patch("notes.discover_vaults", return_value=[mock_vaults[0]]):
            with patch("notes.get_vault_ignore_filters", return_value=["_ARCHIVE/"]):
                with patch("notes.run_obsidian_cmd", return_value=search_output):
                    result = cmd_search("test", vault_filter="My Vault")
                    assert result["count"] == 1
                    assert result["results"][0]["file"] == "notes/keep.md"

    def test_search_with_limit(self, mock_vaults):
        search_output = "a.md\nb.md\nc.md"

        with patch("notes.discover_vaults", return_value=[mock_vaults[0]]):
            with patch("notes.get_vault_ignore_filters", return_value=[]):
                with patch("notes.run_obsidian_cmd", return_value=search_output):
                    result = cmd_search("test", vault_filter="My Vault", limit=2)
                    assert result["status"] == "success"

    def test_vault_not_found(self, mock_vaults):
        with patch("notes.discover_vaults", return_value=mock_vaults):
            result = cmd_search("test", vault_filter="Nonexistent")
            assert result["status"] == "error"
            assert "not found" in result["message"].lower()

    def test_search_with_context(self, mock_vaults):
        context_json = json.dumps(
            [
                {
                    "file": "folder/note.md",
                    "matches": [
                        {"line": 5, "text": "# Postgres Setup"},
                        {"line": 12, "text": "Connect to postgres on port 5432"},
                    ],
                }
            ]
        )

        with patch("notes.discover_vaults", return_value=[mock_vaults[0]]):
            with patch("notes.get_vault_ignore_filters", return_value=[]):
                with patch("notes.run_obsidian_cmd", return_value=context_json):
                    result = cmd_search(
                        "postgres", vault_filter="My Vault", context=True
                    )
                    assert result["count"] == 1
                    assert result["results"][0]["matches"][0]["line"] == 5
                    assert (
                        "Postgres Setup"
                        in result["results"][0]["matches"][0]["text"]
                    )


# ============================================================================
# cmd_read
# ============================================================================


class TestCmdRead:
    @pytest.fixture
    def mock_vaults(self):
        return [{"name": "My Vault", "path": "/tmp/vault1"}]

    def test_read_by_name(self, mock_vaults):
        with patch("notes.discover_vaults", return_value=mock_vaults):
            with patch(
                "notes.run_obsidian_cmd", return_value="# My Note\n\nContent here"
            ):
                result = cmd_read("My Note", vault_filter="My Vault")
                assert result["status"] == "success"
                assert "Content here" in result["content"]
                assert "obsidian://" in result["uri"]

    def test_read_by_path(self, mock_vaults):
        with patch("notes.discover_vaults", return_value=mock_vaults):
            with patch("notes.run_obsidian_cmd", return_value="# Note\n\nBody"):
                result = cmd_read(None, path="folder/note.md", vault_filter="My Vault")
                assert result["status"] == "success"
                assert result["file"] == "folder/note.md"

    def test_read_not_found(self, mock_vaults):
        with patch("notes.discover_vaults", return_value=mock_vaults):
            with patch("notes.run_obsidian_cmd", return_value=""):
                result = cmd_read("Nonexistent Note", vault_filter="My Vault")
                assert result["status"] == "error"

    def test_read_fallback_across_vaults(self):
        two_vaults = [
            {"name": "Vault A", "path": "/tmp/a"},
            {"name": "Vault B", "path": "/tmp/b"},
        ]

        def fake_cmd(args, **kwargs):
            if "vault=Vault A" in " ".join(args):
                return ""  # not found
            return "# Found It\n\nContent"

        with patch("notes.discover_vaults", return_value=two_vaults):
            with patch("notes.run_obsidian_cmd", side_effect=fake_cmd):
                result = cmd_read("Found It")
                assert result["status"] == "success"
                assert result["vault"] == "Vault B"

    def test_read_returns_content(self, mock_vaults):
        with patch("notes.discover_vaults", return_value=mock_vaults):
            with patch("notes.run_obsidian_cmd", return_value="# Note\n\nBody"):
                result = cmd_read("Note", vault_filter="My Vault")
                assert result["status"] == "success"
                assert "content" in result


# ============================================================================
# cmd_tags
# ============================================================================


class TestCmdTags:
    @pytest.fixture
    def mock_vaults(self):
        return [
            {"name": "Vault A", "path": "/tmp/a"},
            {"name": "Vault B", "path": "/tmp/b"},
        ]

    def test_tags_single_vault(self, mock_vaults):
        tags_json = json.dumps(
            [
                {"tag": "#api", "count": "5"},
                {"tag": "#database", "count": "3"},
            ]
        )

        with patch("notes.discover_vaults", return_value=[mock_vaults[0]]):
            with patch("notes.run_obsidian_cmd", return_value=tags_json):
                result = cmd_tags(vault_filter="Vault A")
                assert result["status"] == "success"
                assert result["count"] == 2
                # Verify # prefix stripped
                assert result["tags"][0]["name"] == "api"
                # Verify count is int
                assert result["tags"][0]["count"] == 5

    def test_tags_merged_across_vaults(self, mock_vaults):
        def fake_cmd(args, **kwargs):
            if "vault=Vault A" in " ".join(args):
                return json.dumps(
                    [{"tag": "#api", "count": "5"}, {"tag": "#sql", "count": "2"}]
                )
            return json.dumps(
                [{"tag": "#api", "count": "3"}, {"tag": "#python", "count": "7"}]
            )

        with patch("notes.discover_vaults", return_value=mock_vaults):
            with patch("notes.run_obsidian_cmd", side_effect=fake_cmd):
                result = cmd_tags()
                assert result["status"] == "success"
                # api should be merged: 5 + 3 = 8
                api_tag = next(t for t in result["tags"] if t["name"] == "api")
                assert api_tag["count"] == 8
                assert set(api_tag["vaults"]) == {"Vault A", "Vault B"}
                # Total unique tags
                assert result["count"] == 3

    def test_tags_sorted_by_name(self, mock_vaults):
        tags_json = json.dumps(
            [
                {"tag": "#zebra", "count": "1"},
                {"tag": "#alpha", "count": "5"},
            ]
        )

        with patch("notes.discover_vaults", return_value=[mock_vaults[0]]):
            with patch("notes.run_obsidian_cmd", return_value=tags_json):
                result = cmd_tags(vault_filter="Vault A", sort_by="name")
                assert result["tags"][0]["name"] == "alpha"
                assert result["tags"][1]["name"] == "zebra"

    def test_tags_sorted_by_count(self, mock_vaults):
        tags_json = json.dumps(
            [
                {"tag": "#alpha", "count": "1"},
                {"tag": "#beta", "count": "10"},
            ]
        )

        with patch("notes.discover_vaults", return_value=[mock_vaults[0]]):
            with patch("notes.run_obsidian_cmd", return_value=tags_json):
                result = cmd_tags(vault_filter="Vault A", sort_by="count")
                assert result["tags"][0]["name"] == "beta"
                assert result["tags"][1]["name"] == "alpha"


# ============================================================================
# CLI Integration
# ============================================================================


class TestCLIIntegration:
    def test_no_obsidian_human(self, capsys):
        with patch("shutil.which", return_value=None):
            with patch("sys.argv", ["notes", "search", "test"]):
                with pytest.raises(SystemExit) as exc:
                    main()
                assert exc.value.code == 1
                output = capsys.readouterr()
                assert "not found" in output.err.lower()

    def test_no_obsidian_json(self, capsys):
        with patch("shutil.which", return_value=None):
            exit_code, result = run_cli(
                main, ["notes", "search", "test", "--format", "json"], capsys
            )
            assert exit_code == 1
            assert result["status"] == "error"
            assert result["error_type"] == "not_installed"

    def test_no_subcommand_shows_help(self, capsys):
        with patch("sys.argv", ["notes"]):
            with pytest.raises(SystemExit) as exc:
                main()
            # argparse exits 2 for missing subcommand
            assert exc.value.code in (0, 2)

    def test_search_multiword_query(self, capsys):
        with patch("shutil.which", return_value="/usr/bin/obsidian"):
            with patch(
                "notes.discover_vaults",
                return_value=[{"name": "V", "path": "/tmp"}],
            ):
                with patch("notes.get_vault_ignore_filters", return_value=[]):
                    with patch("notes.run_obsidian_cmd", return_value="note.md"):
                        exit_code, result = run_cli(
                            main,
                            [
                                "notes",
                                "search",
                                "API",
                                "rate",
                                "limiting",
                                "--format",
                                "json",
                            ],
                            capsys,
                        )
                        assert result["query"] == "API rate limiting"

    def test_read_no_prompt_json(self, capsys):
        with patch("shutil.which", return_value="/usr/bin/obsidian"):
            with patch(
                "notes.discover_vaults",
                return_value=[{"name": "V", "path": "/tmp"}],
            ):
                with patch(
                    "notes.run_obsidian_cmd", return_value="# Note\n\nContent"
                ):
                    exit_code, result = run_cli(
                        main,
                        ["notes", "read", "Note", "--format", "json"],
                        capsys,
                    )
                    assert result["status"] == "success"
                    assert "content" in result
