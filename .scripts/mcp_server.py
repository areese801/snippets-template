"""
MCP (Model Context Protocol) server for the code snippets repository.

Exposes snippet search, retrieval, and audit as tools that MCP-compatible
clients (Claude Desktop, Claude Code, etc.) can call.

Communicates over stdin/stdout using JSON-RPC 2.0 (stdio transport).
The MCP client spawns this as a subprocess.

== Running ==

You don't run this directly — the MCP client launches it via mcp_server.sh.
For manual testing:

    ./venv/bin/python .scripts/mcp_server.py

It will sit waiting for JSON-RPC messages on stdin (Ctrl-C to quit).
"""

import sys
from pathlib import Path

# --------------------------------------------------------------------------- #
# stdout protection
#
# Several functions in common.py (log_info, log_warn, log_success) print to
# stdout.  MCP uses stdout for JSON-RPC messages, so any stray print() would
# corrupt the protocol stream.  We redirect stdout to stderr before importing
# anything, then restore it for mcp.run().
# --------------------------------------------------------------------------- #
_real_stdout = sys.stdout
sys.stdout = sys.stderr

# Add .scripts/ to sys.path (same pattern as all other scripts in this dir)
sys.path.insert(0, str(Path(__file__).parent))

from mcp.server.fastmcp import FastMCP

from common import (
    find_snippet_by_id as _find_by_id,
    get_all_snippet_ids,
    get_repo_root,
    interpolate_variables,
    parse_frontmatter,
)
from search import search_snippets as _search_snippets, list_all_tags as _list_all_tags
from audit import scan_all_snippets as _scan_all_snippets


# --------------------------------------------------------------------------- #
# Initialize the MCP server
# --------------------------------------------------------------------------- #
mcp = FastMCP(
    name="snippets",
    instructions=(
        "This server provides access to the user's personal code snippets "
        "repository. Use search_snippets to find snippets by tag, language, "
        "or keyword. Use get_snippet to retrieve the full code by UUID. "
        "Use list_snippet_ids to browse all available snippets. "
        "Call list_tags to discover what tags exist before searching."
    ),
)


# --------------------------------------------------------------------------- #
# Read-Only Tools
# --------------------------------------------------------------------------- #


@mcp.tool()
def search_snippets(
    tags: list[str] | None = None,
    language: str | None = None,
    terms: str | None = None,
    query: str | None = None,
    recently_updated_days: int | None = None,
) -> dict:
    """
    Search for code snippets matching the given filters. All filters use
    AND logic — a snippet must match every provided filter.

    Use this to find snippets by topic, language, or content. Start with
    list_tags() if you don't know what tags are available.

    Args:
        tags: Only return snippets with ALL of these tags.
              Example: ["dbt", "incremental"]
        language: Only return snippets in this language.
                  Supported: sql, python, shell, yaml, toml, json, markdown, text.
        terms: Space-separated search terms. ALL terms must appear somewhere
               in the snippet's title, description, tags, or code.
               Example: "select transaction"
        query: Regex pattern to search within snippet code.
               Example: "SELECT.*JOIN"
        recently_updated_days: Only return snippets updated within this many days.

    Returns:
        Dict with 'count' and 'results' list. Each result has id, relative_path,
        metadata (title, language, tags, description), preview, and line_count.
    """
    filters = {}
    if tags:
        filters["tags"] = tags
    if language:
        filters["language"] = language
    if terms:
        filters["terms"] = terms.split()
    if query:
        filters["query"] = query
    if recently_updated_days is not None:
        filters["recently_updated_days"] = recently_updated_days

    results = _search_snippets(filters)

    return {
        "status": "success",
        "count": len(results),
        "results": results,
    }


@mcp.tool()
def get_snippet(
    snippet_id: str,
    vars: dict[str, str] | None = None,
) -> dict:
    """
    Retrieve a snippet's full code and metadata by UUID.

    Use this after finding a snippet via search_snippets or list_snippet_ids.
    Returns the complete code body — not just a preview.

    If the snippet has {{VAR}} placeholders (listed in metadata.vars),
    you can pass values via the vars parameter. Variables not provided
    are resolved from environment variables, or left as-is.

    Args:
        snippet_id: The UUID of the snippet to retrieve.
        vars: Optional dict of variable substitutions.
              Example: {"SCHEMA": "public", "TABLE_NAME": "users"}

    Returns:
        Dict with id, file_path, relative_path, metadata, and full code body.
        If variables were interpolated, includes 'variables' with resolved
        and unresolved details.
    """
    file_path = _find_by_id(snippet_id)
    if not file_path:
        return {
            "status": "error",
            "message": f"No snippet found with ID: {snippet_id}. "
            "Use list_snippet_ids() to see all available IDs.",
        }

    content = file_path.read_text(encoding="utf-8")
    metadata, code = parse_frontmatter(content)
    repo_root = get_repo_root()
    code = code.strip()

    result = {
        "status": "success",
        "id": snippet_id,
        "file_path": str(file_path),
        "relative_path": str(file_path.relative_to(repo_root)),
        "metadata": metadata,
        "code": code,
    }

    # Interpolate variables if the snippet declares any
    declared_vars = metadata.get("vars", [])
    if declared_vars:
        interpolated, resolved, unresolved = interpolate_variables(
            code, declared_vars, vars or {}
        )
        result["code"] = interpolated
        result["variables"] = {
            "resolved": {k: {"value": v, "source": s} for k, (v, s) in resolved.items()},
            "unresolved": unresolved,
        }

    return result


@mcp.tool()
def list_snippet_ids() -> dict:
    """
    List all snippets with their UUIDs, titles, and languages.

    Use this to browse the full snippet collection or to find a specific
    snippet's UUID before calling get_snippet().

    Returns:
        Dict with 'count' and 'snippets' list. Each entry has id, title,
        language, and relative file path.
    """
    snippets = get_all_snippet_ids()
    return {
        "status": "success",
        "count": len(snippets),
        "snippets": snippets,
    }


@mcp.tool()
def list_tags() -> dict:
    """
    List all tags used across snippets with their counts.

    Use this to discover what tags exist before calling search_snippets()
    with a tag filter. Tags are lowercase-hyphenated (e.g., "dbt",
    "rate-limiting", "soft-delete").

    Returns:
        Dict with 'count' (number of unique tags) and 'tags' mapping
        each tag name to its usage count.
    """
    tags = _list_all_tags()
    return {
        "status": "success",
        "count": len(tags),
        "tags": tags,
    }


@mcp.tool()
def audit_snippets() -> dict:
    """
    Check all snippets for metadata issues (missing fields, invalid dates,
    unsupported languages, etc.).

    Use this as a health check to find snippets that need attention.

    Returns:
        Dict with total_snippets, issues_found, breakdown by issue type,
        and list of snippets with issues.
    """
    return _scan_all_snippets()


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    # Restore real stdout for FastMCP's JSON-RPC communication
    sys.stdout = _real_stdout
    mcp.run()
