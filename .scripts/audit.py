#!/usr/bin/env python3
"""
Audit snippet metadata for completeness and correctness.

This script scans all snippets and identifies metadata issues:
- Missing required fields
- Empty values
- Invalid date formats
- Old schema (has 'source', missing 'last_updated')
- Invalid language
- Malformed tags

Supports both dry-run scanning and interactive fixing.

Usage:
    # Scan and report issues (dry-run)
    ./audit.py --scan

    # Interactive fix mode (one-by-one)
    ./audit.py --fix-interactive

    # Batch fix mode (prompt for all at once)
    ./audit.py --fix-batch

    # Auto-migrate old schema
    ./audit.py --migrate-schema

    # Check specific directory only
    ./audit.py --scan --directory sql

    # JSON output for programmatic use
    ./audit.py --scan --format json
"""

import sys
import argparse
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# Add .scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from common import (
    log_info, log_success, log_warn, log_error,
    get_repo_root, find_snippet_files, parse_frontmatter,
    serialize_frontmatter, validate_frontmatter, validate_date,
    suggest_tags, get_today, normalize_tag, generate_uuid,
    SUPPORTED_LANGUAGES, Colors, git_add, git_commit
)


def detect_issues(metadata: Dict[str, Any], file_path: Path) -> List[str]:
    """
    Detect metadata issues in a snippet.

    Args:
        metadata: Frontmatter metadata
        file_path: Path to snippet file

    Returns:
        List of issue descriptions
    """
    issues = []

    # Check for missing UUID
    if 'id' not in metadata or not metadata['id']:
        issues.append('missing_id')

    # Check for old schema
    if 'source' in metadata:
        issues.append('old_schema_has_source')
    if 'last_updated' not in metadata:
        issues.append('old_schema_missing_last_updated')

    # Check required fields
    required_fields = ['title', 'language', 'description', 'created', 'last_updated']
    for field in required_fields:
        if field not in metadata or not metadata[field]:
            issues.append(f'missing_{field}')

    # Validate language
    if 'language' in metadata:
        if metadata['language'] not in SUPPORTED_LANGUAGES:
            issues.append('invalid_language')

    # Validate dates
    for date_field in ['created', 'last_updated']:
        if date_field in metadata and metadata[date_field]:
            if not validate_date(str(metadata[date_field])):
                issues.append(f'invalid_date_{date_field}')

    # Check tags (should be list)
    if 'tags' in metadata:
        if not isinstance(metadata['tags'], list):
            issues.append('malformed_tags')
        elif len(metadata['tags']) == 0:
            issues.append('missing_tags')

    return issues


def scan_all_snippets(directory: Optional[str] = None) -> Dict[str, Any]:
    """
    Scan all snippets for issues.

    Args:
        directory: Optional specific directory to scan

    Returns:
        Dictionary with scan results
    """
    repo_root = get_repo_root()

    if directory:
        search_path = repo_root / directory
        if not search_path.exists():
            return {
                'status': 'error',
                'message': f'Directory not found: {directory}'
            }
    else:
        search_path = repo_root

    all_files = find_snippet_files(search_path, "*.md")

    # Filter out non-snippet files
    excluded_files = ['README.md', 'CLAUDE.md', 'TODO.md']
    all_files = [f for f in all_files if f.name not in excluded_files]

    total_snippets = 0
    snippets_with_issues = []
    issue_breakdown = {}

    for file_path in all_files:
        try:
            content = file_path.read_text(encoding='utf-8')
            metadata, _ = parse_frontmatter(content)
            total_snippets += 1

            issues = detect_issues(metadata, file_path)

            if issues:
                rel_path = str(file_path.relative_to(repo_root))
                snippets_with_issues.append({
                    'file_path': rel_path,
                    'issues': issues
                })

                # Count issue types
                for issue in issues:
                    issue_breakdown[issue] = issue_breakdown.get(issue, 0) + 1

        except Exception as e:
            log_warn(f"Failed to parse {file_path}: {e}")
            continue

    return {
        'status': 'success',
        'total_snippets': total_snippets,
        'issues_found': len(snippets_with_issues),
        'breakdown': issue_breakdown,
        'snippets_with_issues': snippets_with_issues
    }


def fix_snippet_interactive(file_path: Path, issues: List[str]) -> bool:
    """
    Fix issues for a single snippet interactively.

    Args:
        file_path: Path to snippet file
        issues: List of issues to fix

    Returns:
        True if fixed, False if skipped
    """
    try:
        content = file_path.read_text(encoding='utf-8')
        metadata, code = parse_frontmatter(content)
    except Exception as e:
        log_error(f"Failed to parse {file_path}: {e}")
        return False

    print(f"\n{Colors.BOLD}Fixing: {file_path.name}{Colors.NC}")
    print(f"Issues: {', '.join(issues)}\n")

    # Show current metadata
    print(f"{Colors.CYAN}Current metadata:{Colors.NC}")
    for key, value in metadata.items():
        print(f"  {key}: {value}")

    # Show code preview
    code_preview = '\n'.join(code.strip().split('\n')[:3])
    print(f"\n{Colors.CYAN}Code preview:{Colors.NC}")
    print(f"  {code_preview}...")

    updated = False

    # Handle old schema migration
    if 'old_schema_has_source' in issues:
        print(f"\n{Colors.YELLOW}Old schema detected: 'source' field present{Colors.NC}")
        remove = input("Remove 'source' field? [Y/n]: ").strip().lower()
        if remove in ['', 'y', 'yes']:
            del metadata['source']
            updated = True

    if 'old_schema_missing_last_updated' in issues or 'missing_last_updated' in issues:
        print(f"\n{Colors.YELLOW}Missing 'last_updated' field{Colors.NC}")
        metadata['last_updated'] = metadata.get('created', get_today())
        print(f"Set to: {metadata['last_updated']}")
        updated = True

    # Fix missing fields
    if 'missing_title' in issues:
        print(f"\n{Colors.YELLOW}Missing title{Colors.NC}")
        title = input("Enter title: ").strip()
        if title:
            metadata['title'] = title
            updated = True

    if 'missing_language' in issues:
        print(f"\n{Colors.YELLOW}Missing language{Colors.NC}")
        print(f"Supported: {', '.join(SUPPORTED_LANGUAGES)}")
        lang = input("Enter language: ").strip()
        if lang:
            metadata['language'] = lang
            updated = True

    if 'missing_description' in issues:
        print(f"\n{Colors.YELLOW}Missing description{Colors.NC}")
        desc = input("Enter description (one sentence): ").strip()
        if desc:
            metadata['description'] = desc
            updated = True

    if 'missing_tags' in issues:
        print(f"\n{Colors.YELLOW}Missing tags{Colors.NC}")
        # Auto-suggest tags
        suggested = suggest_tags(code, metadata.get('language', 'text'))
        print(f"Suggested: {', '.join(suggested)}")
        accept = input("Accept suggested tags? [Y/n/e(dit)]: ").strip().lower()

        if accept in ['', 'y', 'yes']:
            metadata['tags'] = suggested
            updated = True
        elif accept == 'e':
            tags_input = input("Enter tags (comma-separated): ").strip()
            if tags_input:
                metadata['tags'] = [normalize_tag(t) for t in tags_input.split(',')]
                updated = True

    if 'missing_created' in issues:
        print(f"\n{Colors.YELLOW}Missing 'created' date{Colors.NC}")
        created = input(f"Enter created date (YYYY-MM-DD) [{get_today()}]: ").strip()
        metadata['created'] = created if created else get_today()
        updated = True

    # Validate language
    if 'invalid_language' in issues:
        print(f"\n{Colors.YELLOW}Invalid language: {metadata.get('language')}{Colors.NC}")
        print(f"Supported: {', '.join(SUPPORTED_LANGUAGES)}")
        lang = input("Enter valid language: ").strip()
        if lang:
            metadata['language'] = lang
            updated = True

    if updated:
        # Write updated content
        updated_content = serialize_frontmatter(metadata) + "\n" + code

        try:
            file_path.write_text(updated_content, encoding='utf-8')
            log_success(f"Updated: {file_path}")
            return True
        except Exception as e:
            log_error(f"Failed to write: {e}")
            return False
    else:
        log_info("No changes made")
        return False


def migrate_schema_all(directory: Optional[str] = None) -> Dict[str, Any]:
    """
    Auto-migrate all snippets from old schema to new schema.

    Args:
        directory: Optional specific directory to migrate

    Returns:
        Result dictionary
    """
    repo_root = get_repo_root()

    if directory:
        search_path = repo_root / directory
    else:
        search_path = repo_root

    all_files = find_snippet_files(search_path, "*.md")

    # Filter out non-snippet files
    excluded_files = ['README.md', 'CLAUDE.md', 'TODO.md']
    all_files = [f for f in all_files if f.name not in excluded_files]

    migrated_files = []

    for file_path in all_files:
        try:
            content = file_path.read_text(encoding='utf-8')
            metadata, code = parse_frontmatter(content)

            updated = False

            # Remove 'source' field
            if 'source' in metadata:
                del metadata['source']
                updated = True

            # Add 'last_updated' field
            if 'last_updated' not in metadata:
                metadata['last_updated'] = metadata.get('created', get_today())
                updated = True

            # Add 'id' field (UUID)
            if 'id' not in metadata:
                # Rebuild metadata with id first for visibility
                new_metadata = {'id': generate_uuid()}
                for key, value in metadata.items():
                    if key != 'id':
                        new_metadata[key] = value
                metadata = new_metadata
                updated = True

            if updated:
                updated_content = serialize_frontmatter(metadata) + "\n" + code
                file_path.write_text(updated_content, encoding='utf-8')
                migrated_files.append(str(file_path.relative_to(repo_root)))
                log_success(f"Migrated: {file_path.name}")

        except Exception as e:
            log_warn(f"Failed to migrate {file_path}: {e}")
            continue

    return {
        'status': 'success',
        'migrated_count': len(migrated_files),
        'migrated_files': migrated_files
    }


def add_uuids_all(directory: Optional[str] = None) -> Dict[str, Any]:
    """
    Add UUIDs to all snippets missing them.

    Args:
        directory: Optional specific directory to process

    Returns:
        Result dictionary
    """
    repo_root = get_repo_root()

    if directory:
        search_path = repo_root / directory
    else:
        search_path = repo_root

    all_files = find_snippet_files(search_path, "*.md")

    # Filter out non-snippet files
    excluded_files = ['README.md', 'CLAUDE.md', 'TODO.md']
    all_files = [f for f in all_files if f.name not in excluded_files]

    updated_files = []

    for file_path in all_files:
        try:
            content = file_path.read_text(encoding='utf-8')
            metadata, code = parse_frontmatter(content)

            # Check if UUID is missing
            if 'id' not in metadata or not metadata['id']:
                # Generate and add UUID
                new_uuid = generate_uuid()

                # Rebuild metadata with id first (for visibility)
                new_metadata = {'id': new_uuid}
                for key, value in metadata.items():
                    if key != 'id':
                        new_metadata[key] = value

                # Write updated content
                updated_content = serialize_frontmatter(new_metadata) + "\n" + code
                file_path.write_text(updated_content, encoding='utf-8')
                updated_files.append({
                    'file': str(file_path.relative_to(repo_root)),
                    'id': new_uuid
                })
                log_success(f"Added UUID to: {file_path.name}")

        except Exception as e:
            log_warn(f"Failed to process {file_path}: {e}")
            continue

    return {
        'status': 'success',
        'updated_count': len(updated_files),
        'updated_files': updated_files
    }


def display_scan_results(results: Dict[str, Any], format: str = 'human'):
    """
    Display scan results.

    Args:
        results: Scan results dictionary
        format: Output format ('human' or 'json')
    """
    if format == 'json':
        print(json.dumps(results, indent=2))
        return

    if results['status'] != 'success':
        log_error(results.get('message', 'Scan failed'))
        return

    print(f"\n{Colors.BOLD}Audit Results:{Colors.NC}\n")
    print(f"  Total snippets: {results['total_snippets']}")
    print(f"  Snippets with issues: {results['issues_found']}")

    if results['issues_found'] == 0:
        log_success("\nAll snippets are compliant! ✓")
        return

    print(f"\n{Colors.BOLD}Issue Breakdown:{Colors.NC}")
    for issue, count in sorted(results['breakdown'].items(), key=lambda x: x[1], reverse=True):
        issue_label = issue.replace('_', ' ').title()
        print(f"  {issue_label}: {count}")

    print(f"\n{Colors.BOLD}Snippets with issues:{Colors.NC}")
    for snippet in results['snippets_with_issues'][:10]:  # Show first 10
        print(f"  • {snippet['file_path']}")
        print(f"    Issues: {', '.join(snippet['issues'])}")

    if len(results['snippets_with_issues']) > 10:
        remaining = len(results['snippets_with_issues']) - 10
        print(f"\n  ... and {remaining} more")


def main():
    """
    Main entry point.
    """
    parser = argparse.ArgumentParser(
        description='Audit snippet metadata for completeness.',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Modes
    parser.add_argument('--scan', action='store_true', help='Scan for issues (dry-run)')
    parser.add_argument('--fix-interactive', action='store_true', help='Fix issues interactively')
    parser.add_argument('--fix-batch', action='store_true', help='Batch fix mode')
    parser.add_argument('--migrate-schema', action='store_true', help='Auto-migrate old schema')
    parser.add_argument('--add-uuids', action='store_true', help='Add UUIDs to snippets missing them')

    # Options
    parser.add_argument('--directory', help='Specific directory to audit')
    parser.add_argument('--format', choices=['human', 'json'], default='human')

    args = parser.parse_args()

    # Determine mode
    if args.scan:
        # Scan mode
        log_info("Scanning snippets for metadata issues...")
        results = scan_all_snippets(args.directory)
        display_scan_results(results, args.format)

    elif args.migrate_schema:
        # Schema migration mode
        log_info("Migrating snippets to new schema...")
        results = migrate_schema_all(args.directory)

        if args.format == 'json':
            print(json.dumps(results, indent=2))
        else:
            if results['migrated_count'] > 0:
                log_success(f"\nMigrated {results['migrated_count']} snippets")

                # Prompt for commit
                if sys.stdin.isatty():
                    commit_choice = input("\nCommit changes? [Y/n]: ").strip().lower()
                    if commit_choice in ['', 'y', 'yes']:
                        # Stage all migrated files
                        repo_root = get_repo_root()
                        for file in results['migrated_files']:
                            git_add(repo_root / file)

                        commit_msg = "chore: migrate snippets to new schema (remove source, add last_updated)"
                        if git_commit(commit_msg):
                            log_success("Committed schema migration")
            else:
                log_info("No snippets needed migration")

    elif args.add_uuids:
        # Add UUIDs mode
        log_info("Adding UUIDs to snippets missing them...")
        results = add_uuids_all(args.directory)

        if args.format == 'json':
            print(json.dumps(results, indent=2))
        else:
            if results['updated_count'] > 0:
                log_success(f"\nAdded UUIDs to {results['updated_count']} snippets")

                # Prompt for commit
                if sys.stdin.isatty():
                    commit_choice = input("\nCommit changes? [Y/n]: ").strip().lower()
                    if commit_choice in ['', 'y', 'yes']:
                        # Stage all updated files
                        repo_root = get_repo_root()
                        for item in results['updated_files']:
                            git_add(repo_root / item['file'])

                        commit_msg = f"chore: add UUIDs to {results['updated_count']} snippets"
                        if git_commit(commit_msg):
                            log_success("Committed UUID additions")
            else:
                log_info("All snippets already have UUIDs")

    elif args.fix_interactive:
        # Interactive fix mode
        log_info("Scanning for issues...")
        results = scan_all_snippets(args.directory)

        if results['issues_found'] == 0:
            log_success("No issues found!")
            sys.exit(0)

        print(f"\nFound {results['issues_found']} snippets with issues")
        proceed = input("Fix one-by-one? [Y/n]: ").strip().lower()

        if proceed not in ['', 'y', 'yes']:
            log_info("Cancelled")
            sys.exit(0)

        repo_root = get_repo_root()
        fixed_count = 0
        fixed_files = []

        for i, snippet in enumerate(results['snippets_with_issues'], 1):
            print(f"\n{Colors.BOLD}[{i}/{results['issues_found']}]{Colors.NC}")

            file_path = repo_root / snippet['file_path']
            if fix_snippet_interactive(file_path, snippet['issues']):
                fixed_count += 1
                fixed_files.append(file_path)

            # Ask to continue
            if i < results['issues_found']:
                cont = input("\nContinue to next? [Y/n/q(uit)]: ").strip().lower()
                if cont == 'q':
                    break
                elif cont == 'n':
                    break

        if fixed_count > 0:
            log_success(f"\nFixed {fixed_count} snippets")

            # Prompt for commit
            commit_choice = input("\nCommit all fixes? [Y/n]: ").strip().lower()
            if commit_choice in ['', 'y', 'yes']:
                for file in fixed_files:
                    git_add(file)

                commit_msg = f"chore: fix metadata issues in {fixed_count} snippets"
                if git_commit(commit_msg):
                    log_success("Committed fixes")

    else:
        # Default: scan
        log_info("Scanning snippets for metadata issues...")
        results = scan_all_snippets(args.directory)
        display_scan_results(results, args.format)

        if results['issues_found'] > 0 and args.format == 'human':
            print(f"\n{Colors.CYAN}To fix issues:{Colors.NC}")
            print("  ./audit.py --fix-interactive  # Fix one-by-one")
            print("  ./audit.py --migrate-schema   # Auto-migrate old schema")

    sys.exit(0)


if __name__ == '__main__':
    main()
