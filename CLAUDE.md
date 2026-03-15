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
- `.scripts/snippets_tui.py` - Unified interface

**Wrapper Scripts:**
- `get` - Quick clipboard access by UUID
- `search` - Search snippets
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

# With variable overrides (for snippets with vars field)
./get 550e8400-e29b-41d4-a716-446655440000 --var SCHEMA=staging --var TABLE_NAME=users

# Skip interpolation
./get 550e8400-e29b-41d4-a716-446655440000 --raw

# List all snippet IDs
./get --list
```

### Editing Snippets

```bash
# Add tags
.scripts/edit.py sql/snippet.md --add-tags "production,reviewed"

# Update field
.scripts/edit.py sql/snippet.md --update-field description --value "New description"
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

## MCP Filesystem Integration

Enable Claude Desktop to read snippets directly:

**~/.config/Claude/claude_desktop_config.json:**
```json
{
  "mcpServers": {
    "snippets": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "/path/to/your/snippets"
      ]
    }
  }
}
```
