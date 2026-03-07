#!/usr/bin/env python3
"""
Edit metadata and code for existing snippets.

This script supports both interactive and programmatic editing:
- Interactive: Select file from menu, edit fields one-by-one
- Programmatic: Update specific fields via JSON or CLI arguments

Features:
- Auto-update last_updated field
- Schema migration (remove 'source', add 'last_updated')
- Edit code in $EDITOR
- Git integration

Usage:
    # Interactive mode - select from menu
    ./edit.py

    # Edit specific file
    ./edit.py sql/my-snippet.md

    # Edit specific field
    ./edit.py sql/snippet.md --field tags

    # Programmatic JSON mode
    ./edit.py sql/snippet.md --json '{"tags": ["new", "tags"]}'

    # Update specific field (programmatic)
    ./edit.py sql/snippet.md --update-field description --value "New description"

    # Tag operations
    ./edit.py sql/snippet.md --add-tags "tag1,tag2"
    ./edit.py sql/snippet.md --remove-tags "old-tag"
"""

import sys
import argparse
import json
import subprocess
import os
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add .scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from common import (
    log_info, log_success, log_warn, log_error,
    get_today, normalize_tag, suggest_tags,
    parse_frontmatter, serialize_frontmatter, update_frontmatter_field,
    get_repo_root, find_snippet_files, git_add, git_commit,
    validate_frontmatter, SUPPORTED_LANGUAGES, Colors, get_menu_choice,
    copy_to_clipboard, delete_snippet, open_in_finder, duplicate_snippet
)


def select_file_interactive() -> Optional[Path]:
    """
    Display menu to select snippet file with search filtering.

    Returns:
        Selected file path or None if cancelled
    """
    repo_root = get_repo_root()
    all_files = find_snippet_files(repo_root, "*.md")

    # Filter out non-snippet files
    excluded_files = ['README.md', 'CLAUDE.md', 'TODO.md']
    all_files = [f for f in all_files if f.name not in excluded_files]

    if not all_files:
        log_error("No snippet files found")
        return None

    # Search/filter prompt
    print(f"\n{Colors.BOLD}Edit Snippet{Colors.NC}")
    print(f"{Colors.CYAN}Total snippets:{Colors.NC} {len(all_files)}")
    search_term = input(f"\nSearch (or Enter to browse all): ").strip().lower()

    # Filter files based on search term
    if search_term:
        files = [f for f in all_files
                 if search_term in str(f.relative_to(repo_root)).lower()]
        if not files:
            log_warn(f"No snippets matching '{search_term}'")
            return select_file_interactive()  # Try again
    else:
        files = all_files

    # Display matching files
    max_display = 20
    print(f"\n{Colors.BOLD}Matching snippets:{Colors.NC}\n")

    for i, file in enumerate(files[:max_display], 1):
        rel_path = file.relative_to(repo_root)
        print(f"  [{i}] {rel_path}")

    if len(files) > max_display:
        print(f"\n  {Colors.YELLOW}... and {len(files) - max_display} more (refine your search){Colors.NC}")

    print(f"\n  [s]      New search")
    print(f"  [b or m] Back to main menu")

    choice = get_menu_choice("\nChoice: ", valid_chars="sbm").strip().lower()

    if choice in ('b', 'm'):
        return None
    elif choice == 's':
        return select_file_interactive()  # Start over

    try:
        index = int(choice) - 1
        if 0 <= index < min(max_display, len(files)):
            return files[index]
        else:
            log_error("Invalid selection")
            return None
    except ValueError:
        log_error("Invalid input")
        return None


def migrate_schema(metadata: Dict[str, Any]) -> tuple[Dict[str, Any], bool]:
    """
    Migrate old schema to new schema.

    Old schema: has 'source' field, missing 'last_updated'
    New schema: no 'source', has 'last_updated'

    Args:
        metadata: Frontmatter metadata

    Returns:
        (updated_metadata, was_migrated)
    """
    migrated = False

    # Remove 'source' field if present
    if 'source' in metadata:
        log_warn("Migrating old schema: removing 'source' field")
        del metadata['source']
        migrated = True

    # Add 'last_updated' if missing
    if 'last_updated' not in metadata:
        log_warn("Migrating old schema: adding 'last_updated' field")
        metadata['last_updated'] = metadata.get('created', get_today())
        migrated = True

    return metadata, migrated


def edit_field_interactive(metadata: Dict[str, Any], field: str) -> Any:
    """
    Edit a specific field interactively.

    Args:
        metadata: Current metadata
        field: Field name to edit

    Returns:
        New value for field
    """
    current = metadata.get(field, '')

    print(f"\n{Colors.CYAN}Editing: {field}{Colors.NC}")
    print(f"Current value: {current}")

    if field == 'tags':
        return edit_tags_interactive(metadata.get('tags', []))
    elif field == 'language':
        new_value = input(f"New value ({', '.join(SUPPORTED_LANGUAGES)}): ").strip()
        return new_value if new_value else current
    else:
        new_value = input("New value: ").strip()
        return new_value if new_value else current


def edit_tags_interactive(current_tags: List[str]) -> List[str]:
    """
    Edit tags interactively.

    Args:
        current_tags: Current tag list

    Returns:
        Updated tag list
    """
    print(f"Current tags: {', '.join(current_tags)}")
    print(f"{Colors.CYAN}[a]dd{Colors.NC}, {Colors.CYAN}[r]emove{Colors.NC}, {Colors.CYAN}[e]dit (replace all){Colors.NC}, or {Colors.CYAN}[Enter]{Colors.NC} to keep")

    choice = input("Choice: ").strip().lower()

    if choice == 'a':
        new_tags = input("Add tags (comma-separated): ").strip()
        additional = [normalize_tag(t) for t in new_tags.split(',') if t.strip()]
        return current_tags + additional
    elif choice == 'r':
        to_remove = input("Remove tags (comma-separated): ").strip()
        remove_set = {normalize_tag(t) for t in to_remove.split(',') if t.strip()}
        return [t for t in current_tags if t not in remove_set]
    elif choice == 'e':
        new_tags = input("Enter all tags (comma-separated): ").strip()
        return [normalize_tag(t) for t in new_tags.split(',') if t.strip()]
    else:
        return current_tags


def edit_code_in_editor(file_path: Path) -> bool:
    """
    Open file in $EDITOR for code editing.

    Args:
        file_path: Path to snippet file

    Returns:
        True if edited, False if cancelled
    """
    editor = os.environ.get('EDITOR', 'nano')
    log_info(f"Opening in {editor}...")

    try:
        subprocess.run([editor, str(file_path)], check=True)
        return True
    except subprocess.CalledProcessError:
        log_error("Editor failed")
        return False
    except FileNotFoundError:
        log_error(f"Editor not found: {editor}")
        log_info("Set $EDITOR environment variable to your preferred editor")
        return False


def interactive_edit(file_path: Path) -> Dict[str, Any]:
    """
    Interactive editing menu.

    Args:
        file_path: Path to snippet file

    Returns:
        Result dictionary
    """
    # Read current content
    try:
        content = file_path.read_text(encoding='utf-8')
        metadata, code_body = parse_frontmatter(content)
    except Exception as e:
        log_error(f"Failed to parse file: {e}")
        return {'status': 'error', 'message': str(e)}

    # Auto-migrate schema if needed
    metadata, was_migrated = migrate_schema(metadata)

    fields_updated = []
    if was_migrated:
        fields_updated.append('schema_migration')

    while True:
        # Display current metadata
        print(f"\n{Colors.BOLD}Editing: {file_path.name}{Colors.NC}\n")
        print(f"  Title: {metadata.get('title', 'N/A')}")
        print(f"  Language: {metadata.get('language', 'N/A')}")
        print(f"  Tags: {', '.join(metadata.get('tags', []))}")
        print(f"  Description: {metadata.get('description', 'N/A')}")
        print(f"  Created: {metadata.get('created', 'N/A')}")
        print(f"  Last Updated: {metadata.get('last_updated', 'N/A')}")

        print(f"\n{Colors.CYAN}What would you like to edit?{Colors.NC}")
        print("  [t] Title")
        print("  [l] Language")
        print("  [g] Tags (add/remove)")
        print("  [n] Description")
        print("  [c] Edit code (open in $EDITOR)")
        print("  [f] Fill missing fields")
        print("  [v] View full content")
        print("  [y] Copy code to clipboard")
        print("  [o] Open in Finder")
        print("  [p] Duplicate snippet")
        print("  [x] Delete snippet")
        print("  [s] Save and quit")
        print("  [q] Quit without saving")
        print("  [b] Back to main menu")

        choice = get_menu_choice("\nChoice: ", valid_chars="tlgncfvyopxsqb").strip().lower()

        if choice in ('q', 'b'):
            return {'status': 'cancelled', 'message': 'User cancelled'}
        elif choice == 's':
            break
        elif choice == 't':
            metadata['title'] = edit_field_interactive(metadata, 'title')
            fields_updated.append('title')
        elif choice == 'l':
            metadata['language'] = edit_field_interactive(metadata, 'language')
            fields_updated.append('language')
        elif choice == 'g':
            metadata['tags'] = edit_field_interactive(metadata, 'tags')
            fields_updated.append('tags')
        elif choice == 'n':
            metadata['description'] = edit_field_interactive(metadata, 'description')
            fields_updated.append('description')
        elif choice == 'c':
            # Write current state first
            updated_content = serialize_frontmatter(metadata) + "\n" + code_body
            file_path.write_text(updated_content, encoding='utf-8')

            if edit_code_in_editor(file_path):
                # Re-read after editing
                content = file_path.read_text(encoding='utf-8')
                metadata, code_body = parse_frontmatter(content)
                fields_updated.append('code')
        elif choice == 'f':
            # Fill missing fields
            errors = validate_frontmatter(metadata)
            if errors:
                log_info("Missing fields detected:")
                for error in errors:
                    print(f"  - {error}")

                for field in ['title', 'language', 'description']:
                    if field not in metadata or not metadata[field]:
                        metadata[field] = edit_field_interactive(metadata, field)
                        fields_updated.append(field)
            else:
                log_success("All required fields present")
        elif choice == 'v':
            # Show full content and copy code to clipboard
            print("\n" + "=" * 60)
            print(serialize_frontmatter(metadata))
            print(code_body)
            print("=" * 60)
            if copy_to_clipboard(code_body.strip()):
                log_success("Code copied to clipboard!")
            else:
                log_warn("Could not copy to clipboard")
        elif choice == 'y':
            # Copy code to clipboard
            if copy_to_clipboard(code_body.strip()):
                log_success("Code copied to clipboard!")
            else:
                log_warn("Could not copy to clipboard")
        elif choice == 'o':
            # Open in Finder
            if open_in_finder(file_path):
                log_success("Opened in Finder")
            else:
                log_warn("Could not open in Finder")
        elif choice == 'p':
            # Duplicate snippet
            new_title = input("\nNew title for duplicate: ").strip()
            if new_title:
                result = duplicate_snippet(file_path, new_title)
                if result['status'] == 'success':
                    log_success(f"Created duplicate: {result['relative_path']}")
                    if result.get('committed'):
                        log_success(f"Committed with hash: {result.get('commit_hash', 'N/A')}")
                    # Ask if user wants to edit the new file
                    edit_new = input("\nEdit the new snippet? [Y/n]: ").strip().lower()
                    if edit_new in ['', 'y', 'yes']:
                        # Return and let caller handle or recursively edit
                        log_info(f"Run: edit.py {result['relative_path']}")
                else:
                    log_error(f"Failed to duplicate: {result.get('message', 'Unknown error')}")
            else:
                log_warn("No title provided, cancelling duplicate")
        elif choice == 'x':
            # Delete snippet
            confirm = input(f"\n{Colors.RED}Delete this snippet? [y/N]:{Colors.NC} ").strip().lower()
            if confirm == 'y':
                result = delete_snippet(file_path, commit=True)
                if result['status'] == 'success':
                    log_success(f"Deleted: {result['relative_path']}")
                    if result.get('committed'):
                        log_success(f"Committed with hash: {result.get('commit_hash', 'N/A')}")
                    return {'status': 'deleted', 'file_path': str(file_path)}
                else:
                    log_error(f"Failed to delete: {result.get('message', 'Unknown error')}")
            else:
                log_info("Deletion cancelled")
        else:
            log_warn("Invalid choice")

    # Update last_updated
    metadata['last_updated'] = get_today()

    # Write updated content
    updated_content = serialize_frontmatter(metadata) + "\n" + code_body

    try:
        file_path.write_text(updated_content, encoding='utf-8')
        log_success(f"Updated: {file_path}")
    except Exception as e:
        log_error(f"Failed to write file: {e}")
        return {'status': 'error', 'message': str(e)}

    # Git commit (prompt in interactive mode)
    committed = False
    commit_choice = input("\nCommit to git? [Y/n]: ").strip().lower()
    if commit_choice in ['', 'y', 'yes']:
        if git_add(file_path):
            commit_msg = f"chore({file_path.parent.name}): update {file_path.stem} metadata"
            if git_commit(commit_msg):
                log_success("Committed to git")
                committed = True
    else:
        log_info("Skipped git commit (changes saved locally)")

    return {
        'status': 'success',
        'file_path': str(file_path),
        'fields_updated': list(set(fields_updated)),
        'last_updated': metadata['last_updated'],
        'committed': committed
    }


def programmatic_edit(file_path: Path, updates: Dict[str, Any]) -> Dict[str, Any]:
    """
    Programmatic editing via updates dictionary.

    Args:
        file_path: Path to snippet file
        updates: Dictionary of fields to update

    Returns:
        Result dictionary
    """
    # Read current content
    try:
        content = file_path.read_text(encoding='utf-8')
        metadata, code_body = parse_frontmatter(content)
    except Exception as e:
        return {
            'status': 'error',
            'error_type': 'parse_error',
            'message': str(e)
        }

    # Auto-migrate schema
    metadata, was_migrated = migrate_schema(metadata)

    # Apply updates
    fields_updated = []
    for field, value in updates.items():
        if field in metadata:
            metadata[field] = value
            fields_updated.append(field)

    if was_migrated:
        fields_updated.append('schema_migration')

    # Update last_updated
    metadata['last_updated'] = get_today()

    # Validate
    errors = validate_frontmatter(metadata)
    if errors:
        return {
            'status': 'error',
            'error_type': 'validation_error',
            'message': 'Validation failed',
            'errors': errors
        }

    # Write updated content
    updated_content = serialize_frontmatter(metadata) + "\n" + code_body

    try:
        file_path.write_text(updated_content, encoding='utf-8')
    except Exception as e:
        return {
            'status': 'error',
            'error_type': 'write_error',
            'message': str(e)
        }

    # Git commit (auto-commit in programmatic mode)
    committed = False
    if git_add(file_path):
        commit_msg = f"chore({file_path.parent.name}): update {file_path.stem} metadata"
        if git_commit(commit_msg):
            committed = True

    return {
        'status': 'success',
        'file_path': str(file_path),
        'fields_updated': fields_updated,
        'last_updated': metadata['last_updated'],
        'committed': committed
    }


def main():
    """
    Main entry point.
    """
    parser = argparse.ArgumentParser(
        description='Edit metadata for existing snippets.',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('file', nargs='?', help='Snippet file to edit (relative to repo root)')

    # Programmatic modes
    parser.add_argument('--json', type=str, help='JSON updates')
    parser.add_argument('--update-field', type=str, help='Field name to update')
    parser.add_argument('--value', type=str, help='New value for field (use with --update-field)')
    parser.add_argument('--add-tags', type=str, help='Comma-separated tags to add')
    parser.add_argument('--remove-tags', type=str, help='Comma-separated tags to remove')

    # Options
    parser.add_argument('--format', choices=['human', 'json'], default='human')

    args = parser.parse_args()

    # Get file path
    if args.file:
        repo_root = get_repo_root()
        file_path = repo_root / args.file
        if not file_path.exists():
            log_error(f"File not found: {file_path}")
            sys.exit(1)
    else:
        # Interactive file selection
        file_path = select_file_interactive()
        if not file_path:
            log_info("Cancelled")
            sys.exit(0)

    # Determine mode
    if args.json:
        # JSON updates
        try:
            updates = json.loads(args.json)
        except json.JSONDecodeError as e:
            log_error(f"Invalid JSON: {e}")
            sys.exit(1)

        result = programmatic_edit(file_path, updates)

    elif args.update_field:
        # Single field update
        if not args.value:
            log_error("--value required with --update-field")
            sys.exit(1)

        result = programmatic_edit(file_path, {args.update_field: args.value})

    elif args.add_tags or args.remove_tags:
        # Tag operations
        try:
            content = file_path.read_text(encoding='utf-8')
            metadata, _ = parse_frontmatter(content)
        except Exception as e:
            log_error(f"Failed to parse: {e}")
            sys.exit(1)

        tags = metadata.get('tags', [])

        if args.add_tags:
            new_tags = [normalize_tag(t) for t in args.add_tags.split(',') if t.strip()]
            tags = tags + new_tags

        if args.remove_tags:
            remove_set = {normalize_tag(t) for t in args.remove_tags.split(',') if t.strip()}
            tags = [t for t in tags if t not in remove_set]

        result = programmatic_edit(file_path, {'tags': tags})

    else:
        # Interactive mode
        result = interactive_edit(file_path)

    # Output result
    if args.format == 'json':
        print(json.dumps(result, indent=2))
        sys.exit(0 if result['status'] == 'success' else 1)
    else:
        sys.exit(0 if result['status'] == 'success' else 1)


if __name__ == '__main__':
    main()
