"""
Tests for get.py - snippet retrieval by UUID.
"""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from constants import VALID_UUID, SECOND_UUID
from helpers import extract_json, run_cli
from get import get_snippet_by_id, list_all_ids, main


# UUID for the vars-enabled test snippet
VARS_UUID = "770a0600-a41d-63f6-c938-668877662222"

# UUID for the undeclared placeholder test snippet
UNDECLARED_UUID = "880b1711-b52e-74g7-d049-779988773333"

# UUID for the dbt/Jinja test snippet
DBT_UUID = "990c2822-c63f-85h8-e150-880099884444"


@pytest.fixture
def vars_snippet(snippet_repo):
    """
    Create a snippet with vars field for interpolation testing.
    """
    content = f"""\
---
id: {VARS_UUID}
title: "Parameterized Query"
language: sql
tags:
- sql
- template
vars:
- SCHEMA
- TABLE_NAME
- START_DATE
description: "Query with variable placeholders"
created: "2026-03-12"
last_updated: "2026-03-12"
---

SELECT * FROM {{{{SCHEMA}}}}.{{{{TABLE_NAME}}}}
WHERE created_at > '{{{{START_DATE}}}}'
"""
    sql_dir = snippet_repo / "sql"
    (sql_dir / "parameterized-query.md").write_text(content, encoding="utf-8")
    return snippet_repo


@pytest.fixture
def undeclared_snippet(snippet_repo):
    """
    Create a snippet WITHOUT vars field but with placeholder-like {{VAR}} syntax.
    """
    content = f"""\
---
id: {UNDECLARED_UUID}
title: "Undeclared Vars Query"
language: sql
tags:
- sql
description: "Query with undeclared placeholders"
created: "2026-03-12"
last_updated: "2026-03-12"
---

SELECT * FROM {{{{SCHEMA}}}}.{{{{TABLE_NAME}}}}
"""
    sql_dir = snippet_repo / "sql"
    (sql_dir / "undeclared-vars-query.md").write_text(content, encoding="utf-8")
    return snippet_repo


@pytest.fixture
def dbt_snippet(snippet_repo):
    """
    Create a snippet with Jinja/dbt syntax that should NOT trigger hints.
    """
    content = f"""\
---
id: {DBT_UUID}
title: "dbt Model"
language: sql
tags:
- sql
- dbt
description: "dbt model with Jinja syntax"
created: "2026-03-12"
last_updated: "2026-03-12"
---

SELECT *
FROM {{{{ ref('stg_users') }}}}
WHERE is_active = true
"""
    sql_dir = snippet_repo / "sql"
    (sql_dir / "dbt-model.md").write_text(content, encoding="utf-8")
    return snippet_repo


# ============================================================================
# get_snippet_by_id
# ============================================================================


class TestGetSnippetById:
    def test_copy_success(self, mock_repo_root, mock_clipboard):
        result = get_snippet_by_id(VALID_UUID)
        assert result["status"] == "success"
        assert result["action"] == "copied"
        assert result["title"] == "Test Query"
        assert mock_clipboard["text"] is not None

    def test_print_mode(self, mock_repo_root, capsys):
        result = get_snippet_by_id(VALID_UUID, print_only=True)
        assert result["status"] == "success"
        assert result["action"] == "printed"
        out = capsys.readouterr().out
        assert "SELECT 1;" in out

    def test_not_found(self, mock_repo_root):
        result = get_snippet_by_id("00000000-0000-0000-0000-000000000000")
        assert result["status"] == "error"
        assert result["error_type"] == "not_found"

    def test_clipboard_failure(self, mock_repo_root, monkeypatch):
        import subprocess as sp

        def fail_popen(*args, **kwargs):
            raise OSError("no clipboard")

        monkeypatch.setattr(sp, "Popen", fail_popen)
        with patch("platform.system", return_value="Darwin"):
            result = get_snippet_by_id(VALID_UUID)
        assert result["status"] == "error"
        assert result["error_type"] == "clipboard_error"


# ============================================================================
# list_all_ids
# ============================================================================


class TestListAllIds:
    def test_returns_count_and_snippets(self, mock_repo_root):
        result = list_all_ids()
        assert result["status"] == "success"
        assert result["count"] >= 2
        ids = [s["id"] for s in result["snippets"]]
        assert VALID_UUID in ids
        assert SECOND_UUID in ids


# ============================================================================
# Variable Interpolation
# ============================================================================


class TestVariableInterpolation:
    def test_all_vars_resolved_via_cli_flags(self, mock_repo_root, vars_snippet, capsys):
        """All vars resolved via --var flags."""
        result = get_snippet_by_id(
            VARS_UUID,
            print_only=True,
            cli_vars={"SCHEMA": "public", "TABLE_NAME": "users", "START_DATE": "2026-01-01"}
        )
        assert result["status"] == "success"
        out = capsys.readouterr().out
        assert "public.users" in out
        assert "'2026-01-01'" in out
        assert "{{SCHEMA}}" not in out
        assert "{{TABLE_NAME}}" not in out
        assert "{{START_DATE}}" not in out

    def test_vars_resolved_via_env(self, mock_repo_root, vars_snippet, capsys, monkeypatch):
        """Vars resolved via environment variables."""
        monkeypatch.setenv("SCHEMA", "staging")
        monkeypatch.setenv("TABLE_NAME", "orders")
        result = get_snippet_by_id(VARS_UUID, print_only=True)
        assert result["status"] == "success"
        out = capsys.readouterr().out
        assert "staging.orders" in out
        # START_DATE not set — should remain unresolved
        assert "{{START_DATE}}" in out

    def test_mixed_resolution(self, mock_repo_root, vars_snippet, capsys, monkeypatch):
        """Some vars from env, some from CLI, some unresolved."""
        monkeypatch.setenv("SCHEMA", "dev")
        result = get_snippet_by_id(
            VARS_UUID,
            print_only=True,
            cli_vars={"TABLE_NAME": "products"}
        )
        assert result["status"] == "success"
        out = capsys.readouterr().out
        assert "dev.products" in out
        assert "{{START_DATE}}" in out

    def test_cli_flag_overrides_env(self, mock_repo_root, vars_snippet, capsys, monkeypatch):
        """CLI --var flag takes priority over env var."""
        monkeypatch.setenv("SCHEMA", "from_env")
        result = get_snippet_by_id(
            VARS_UUID,
            print_only=True,
            cli_vars={"SCHEMA": "from_flag", "TABLE_NAME": "t", "START_DATE": "2026-01-01"}
        )
        assert result["status"] == "success"
        out = capsys.readouterr().out
        assert "from_flag.t" in out
        assert "from_env" not in out

    def test_raw_flag_skips_interpolation(self, mock_repo_root, vars_snippet, capsys, monkeypatch):
        """--raw flag returns code without interpolation."""
        monkeypatch.setenv("SCHEMA", "public")
        result = get_snippet_by_id(
            VARS_UUID,
            print_only=True,
            cli_vars={"TABLE_NAME": "users"},
            raw=True
        )
        assert result["status"] == "success"
        out = capsys.readouterr().out
        assert "{{SCHEMA}}" in out
        assert "{{TABLE_NAME}}" in out
        assert "{{START_DATE}}" in out

    def test_no_vars_field_unchanged(self, mock_repo_root, capsys):
        """Snippet without vars field outputs code unchanged."""
        result = get_snippet_by_id(VALID_UUID, print_only=True)
        assert result["status"] == "success"
        out = capsys.readouterr().out
        assert "SELECT 1;" in out

    def test_jinja_syntax_not_interpolated(self, mock_repo_root, vars_snippet, capsys, monkeypatch):
        """Jinja expressions like {{ ref('stg_users') }} are not touched when not in vars."""
        # The VALID_SNIPPET doesn't have Jinja, but vars_snippet only has SCHEMA, TABLE_NAME, START_DATE
        # Create a snippet with both vars and Jinja-like content
        sql_dir = mock_repo_root / "sql"
        mixed_uuid = "aa0d3933-d74g-96i9-f261-991100995555"
        content = f"""\
---
id: {mixed_uuid}
title: "Mixed Template"
language: sql
tags:
- sql
vars:
- SCHEMA
description: "Has both vars and Jinja"
created: "2026-03-12"
last_updated: "2026-03-12"
---

SELECT * FROM {{{{SCHEMA}}}}.users
WHERE id IN (SELECT id FROM {{{{ ref('stg_users') }}}})
"""
        (sql_dir / "mixed-template.md").write_text(content, encoding="utf-8")

        result = get_snippet_by_id(
            mixed_uuid,
            print_only=True,
            cli_vars={"SCHEMA": "public"}
        )
        assert result["status"] == "success"
        out = capsys.readouterr().out
        assert "public.users" in out
        assert "{{ ref('stg_users') }}" in out

    def test_stderr_resolution_summary(self, mock_repo_root, vars_snippet, capsys, monkeypatch):
        """Resolution summary printed to stderr."""
        monkeypatch.setenv("SCHEMA", "public")
        get_snippet_by_id(
            VARS_UUID,
            print_only=True,
            cli_vars={"TABLE_NAME": "users"}
        )
        err = capsys.readouterr().err
        assert "SCHEMA (env)" in err
        assert "TABLE_NAME (flag)" in err
        assert "START_DATE" in err


class TestUndeclaredPlaceholderHint:
    def test_undeclared_hint_shown(self, mock_repo_root, undeclared_snippet, capsys):
        """Stderr hint when {{UPPER_VAR}} found but no vars field."""
        get_snippet_by_id(UNDECLARED_UUID, print_only=True)
        err = capsys.readouterr().err
        assert "Hint:" in err
        assert "{{SCHEMA}}" in err
        assert "{{TABLE_NAME}}" in err
        assert "vars:" in err

    def test_no_hint_for_jinja(self, mock_repo_root, dbt_snippet, capsys):
        """No hint for Jinja expressions like {{ ref('stg_users') }}."""
        get_snippet_by_id(DBT_UUID, print_only=True)
        err = capsys.readouterr().err
        assert "Hint:" not in err

    def test_no_hint_when_raw(self, mock_repo_root, undeclared_snippet, capsys):
        """--raw flag suppresses undeclared placeholder hints."""
        get_snippet_by_id(UNDECLARED_UUID, print_only=True, raw=True)
        err = capsys.readouterr().err
        assert "Hint:" not in err


# ============================================================================
# CLI / main
# ============================================================================


class TestGetCLI:
    def test_list_json(self, mock_repo_root, capsys):
        code, output = run_cli(main, ["get.py", "--list", "--format", "json"], capsys)
        assert code == 0
        assert output["status"] == "success"
        assert output["count"] >= 2

    def test_uuid_json(self, mock_repo_root, mock_clipboard, capsys):
        code, output = run_cli(main, ["get.py", VALID_UUID, "--format", "json"], capsys)
        assert code == 0
        assert output["status"] == "success"
        assert output["action"] == "copied"

    def test_print_flag(self, mock_repo_root, capsys):
        with patch("sys.argv", ["get.py", VALID_UUID, "--print", "--format", "json"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
        out = capsys.readouterr().out
        # stdout has both the printed code and the JSON
        assert "SELECT 1;" in out

    def test_var_flag_cli(self, mock_repo_root, vars_snippet, capsys):
        """Test --var flag through CLI."""
        with patch("sys.argv", [
            "get.py", VARS_UUID, "--print",
            "--var", "SCHEMA=public",
            "--var", "TABLE_NAME=users",
            "--var", "START_DATE=2026-01-01"
        ]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "public.users" in out
        assert "{{SCHEMA}}" not in out

    def test_raw_flag_cli(self, mock_repo_root, vars_snippet, capsys, monkeypatch):
        """Test --raw flag through CLI."""
        monkeypatch.setenv("SCHEMA", "public")
        with patch("sys.argv", ["get.py", VARS_UUID, "--print", "--raw"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "{{SCHEMA}}" in out
