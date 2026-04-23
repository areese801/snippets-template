# Snippets Repository - Claude Code Integration Guide

## Overview

This repository is designed for dual-mode operation:
- **Human use**: Interactive TUI and menu-driven scripts
- **AI use (Claude Code)**: Programmatic JSON/CLI interfaces

## Getting Started

1. Clone this template repository
2. Install dependencies: `pip install -r requirements.txt` (or use `uv`)
3. Make scripts executable: `chmod +x .scripts/*.py get search snippets`
4. Add your first snippet: `.scripts/add.py`

## Architecture

### Script-Driven CRUD System

**Core Scripts:**
- `.scripts/add.py` - Create snippets
- `.scripts/search.py` - Find snippets
- `.scripts/edit.py` - Update metadata
- `.scripts/audit.py` - Check metadata completeness
- `.scripts/get.py` - Retrieve snippet by UUID
- `.scripts/gist.py` - Publish snippets as GitHub Gists
- `.scripts/snippets_tui.py` - Unified interface

**Wrapper Scripts:**
- `get` - Quick clipboard access by UUID
- `search` - Search snippets
- `gist` - Publish/manage GitHub Gists
- `snippets` - Launch TUI

**Common Module:**
- `.scripts/common.py` - Shared utilities (logging, frontmatter, git, tags, etc.)

### Frontmatter Schema

```yaml
---
id: 550e8400-e29b-41d4-a716-446655440000  # UUID4 (auto-generated)
title: "Descriptive title"
language: "sql"
tags: [tag1, tag2]
vars: [SCHEMA, TABLE_NAME]  # Optional: variable names for interpolation
runnable: true               # Optional: allow execution via --run (shell only)
gist: true                    # Optional: opt-in for GitHub Gist publishing
gist_id: 5b0e0062eb8e...     # Auto-written after first publish
gist_url: https://gist.github.com/user/5b0e...  # Auto-written after first publish
description: "One-sentence AI-searchable description"
created: "2026-03-05"
last_updated: "2026-03-05"  # Auto-updated by edit.py
reviewed: true               # Optional
---
```

## Shell Aliases (Recommended)

Add to your `~/.zshrc` or shell config:

```bash
# Quick access to snippets
alias snippets='cd ~/path/to/snippets && ./snippets'
alias snip='cd ~/path/to/snippets && ./snippets'

# Search snippets (supports positional args)
alias s='~/path/to/snippets/search'
# Usage: s select join dbt

# Get snippet by UUID and copy to clipboard
alias g='~/path/to/snippets/get'
# Usage: g 550e8400-e29b-41d4-a716-446655440000

# Create aliases for frequently used snippets
alias mysnippet='g 550e8400-e29b-41d4-a716-446655440000'
```

## Python Execution

**IMPORTANT**: When a `venv/` directory exists in the repository root, always use the fully qualified path to the Python interpreter inside the virtual environment rather than relying on `python` or `python3` being on `PATH`:

```bash
# Correct - use venv python directly
./venv/bin/python .scripts/search.py --tag dbt --format json

# Incorrect - may resolve to wrong interpreter or fail
python .scripts/search.py --tag dbt --format json
```

The bash wrapper scripts (`get`, `search`, `snippets`) already handle venv activation, so this only applies when calling `.scripts/*.py` files directly.

## Claude Code Usage Patterns

### Adding Snippets Programmatically

```bash
.scripts/add.py \
  --title "Postgres Connection Check" \
  --language sql \
  --tags "postgresql,diagnostic" \
  --description "Quick query to verify Postgres connection" \
  --code "SELECT version();" \
  --format json
```

### Searching Snippets

```bash
# By tags
.scripts/search.py --tag dbt --tag incremental --format json

# By language
.scripts/search.py --language python --format json

# Multi-term search (all terms must match)
.scripts/search.py --terms "select join" --format json

# Positional args work too
.scripts/search.py select join dbt
```

### Getting Snippets by UUID

```bash
# Copy to clipboard
./get 550e8400-e29b-41d4-a716-446655440000

# Print to stdout
./get 550e8400-e29b-41d4-a716-446655440000 --print

# Run a shell snippet (requires language: shell and runnable: true)
./get 550e8400-e29b-41d4-a716-446655440000 --run

# With variable overrides (for snippets with vars field)
./get 550e8400-e29b-41d4-a716-446655440000 --var SCHEMA=staging --var TABLE_NAME=users

# Skip interpolation
./get 550e8400-e29b-41d4-a716-446655440000 --raw

# List all snippet IDs
./get --list
```

### Espanso Integration (Private Snippets via Public Shortcuts)

If you use [espanso](https://espanso.org/) for text expansion and keep your
dotfiles in a public repo, you can bind a short trigger (e.g. `~!cust`) to a
proprietary snippet without exposing its contents. The public espanso config
carries only the trigger and the snippet UUID; at expansion time espanso
shells out to `get <uuid> --print`, which emits the snippet body from this
private repo.

```yaml
# In your (public) espanso config
- trigger: "~!cust"
  replace: "{{snippet}}"
  vars:
    - name: snippet
      type: shell
      params:
        cmd: "$HOME/path/to/snippets/get <uuid-here> --print"
```

The UUID is an opaque identifier that reveals nothing about the snippet,
and the shell command expands to an empty string for anyone who lacks the
private repo — so the pattern is safe to commit to a public dotfiles repo.

### Editing Snippets

```bash
# Add tags
.scripts/edit.py sql/snippet.md --add-tags "production,reviewed"

# Update field
.scripts/edit.py sql/snippet.md --update-field description --value "New description"
```

### Publishing as GitHub Gists

```bash
# Publish or update a single snippet
./gist sql/my-query.md
./gist 550e8400-e29b-41d4-a716-446655440000

# Create as secret (unlisted) gist
./gist sql/my-query.md --secret

# Sync all gist-marked snippets
./gist --all

# Show publish status
./gist --status

# Dry run
./gist --all --dry-run --format json
```

### Auditing Metadata

```bash
# Scan for issues
.scripts/audit.py --scan --format json

# Add UUIDs to existing snippets
.scripts/audit.py --add-uuids
```

## Best Practices

1. **Always use `--format json`** for programmatic operations
2. **Use `search.py` before adding** to avoid duplicates
3. **Run `audit.py --scan`** periodically to check metadata health
4. **Use meaningful tags** for better searchability
5. **Write clear descriptions** optimized for AI semantic search

## Directory Structure

```
~/snippets/
├── sql/         # SQL queries, DDL, dbt models
├── python/      # Python functions, classes, utilities
├── shell/       # Bash/zsh scripts and one-liners
├── prompts/     # AI prompts and templates
├── config/      # Config file snippets (YAML, TOML, JSON)
└── .scripts/    # Automation scripts
```

## MCP Server

The snippets repository includes a purpose-built MCP server that exposes
snippet operations as structured tools for Claude Desktop and Claude Code.

**Server:** `.scripts/mcp_server.py` (FastMCP, stdio transport)
**Wrapper:** `mcp_server.sh` (activates venv, launches server)

### Available Tools (Read-Only)

| Tool | Description |
|------|-------------|
| `search_snippets` | Find snippets by tags, language, terms, regex, or recency |
| `get_snippet` | Retrieve full code + metadata by UUID |
| `list_snippet_ids` | Browse all snippets with UUIDs, titles, languages |
| `list_tags` | Discover all tags with usage counts |
| `audit_snippets` | Health check for metadata issues |

### Configuration

**Claude Desktop** (`~/Library/Application Support/Claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "snippets": {
      "command": "/path/to/your/snippets/mcp_server.sh"
    }
  }
}
```

**Claude Code** (`.mcp.json` in repo root):
```json
{
  "mcpServers": {
    "snippets": {
      "command": "./mcp_server.sh"
    }
  }
}
```

### Restarting

- **Claude Desktop**: Restart the app
- **Claude Code**: Use `/mcp` to manage MCP servers
