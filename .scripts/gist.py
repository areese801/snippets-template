"""
Publish snippets as GitHub Gists.

Create, update, and teardown GitHub Gists from snippet files using the gh CLI.

Usage:
    # Publish or update a single snippet
    ./gist <file-or-uuid>

    # Publish as secret (unlisted) gist
    ./gist <file-or-uuid> --secret

    # Publish/update all gist:true, teardown gist:false with gist_id
    ./gist --all

    # Show publish status for all gist-marked snippets
    ./gist --status

    # JSON output
    ./gist --format json

    # Dry run (show what would happen)
    ./gist --dry-run
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add .scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from common import (
    Colors,
    get_language_extension,
    get_repo_root,
    get_today,
    find_all_snippets,
    find_snippet_by_id,
    git_add,
    git_commit,
    git_get_short_hash,
    log_error,
    log_info,
    log_success,
    log_warn,
    parse_frontmatter,
    serialize_frontmatter,
    slugify,
)


# ============================================================================
# Helpers
# ============================================================================

UUID_PATTERN = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE,
)


def get_gist_filename(metadata: Dict[str, Any]) -> str:
    """
    Build deterministic gist filename from snippet metadata.

    Format: slugify(title) + language_extension

    Args:
        metadata: Snippet frontmatter metadata

    Returns:
        Filename string (e.g., 'dbt-incremental-model.sql')
    """
    title = metadata.get('title', 'untitled')
    language = metadata.get('language', 'text')
    extension = get_language_extension(language)
    return slugify(title) + extension


def resolve_snippet(identifier: str) -> Path:
    """
    Resolve a positional argument to a snippet file path.

    Auto-detects whether the identifier is a file path or UUID:
    - Contains '/' or ends with '.md' -> treat as file path (relative to repo root)
    - Matches UUID pattern -> resolve via find_snippet_by_id()

    Args:
        identifier: File path or UUID string

    Returns:
        Resolved Path to snippet file

    Raises:
        FileNotFoundError: If the snippet cannot be found
    """
    # File path detection
    if '/' in identifier or identifier.endswith('.md'):
        repo_root = get_repo_root()
        file_path = repo_root / identifier
        if not file_path.exists():
            raise FileNotFoundError(f"Snippet file not found: {identifier}")
        return file_path

    # UUID detection
    if UUID_PATTERN.match(identifier):
        file_path = find_snippet_by_id(identifier)
        if file_path is None:
            raise FileNotFoundError(f"No snippet found with ID: {identifier}")
        return file_path

    raise FileNotFoundError(
        f"Cannot resolve identifier: {identifier} "
        f"(not a file path or valid UUID)"
    )


def _build_gist_description(metadata: Dict[str, Any]) -> str:
    """
    Build gist description from snippet metadata.

    Args:
        metadata: Snippet frontmatter metadata

    Returns:
        Description string in 'title - description' format
    """
    title = metadata.get('title', 'Untitled')
    description = metadata.get('description', '')
    if description:
        return f"{title} \u2014 {description}"
    return title


def _parse_gist_url(gh_output: str) -> str:
    """
    Extract gist URL from gh CLI output.

    Args:
        gh_output: stdout from gh gist create

    Returns:
        Gist URL string
    """
    # gh gist create outputs the URL on stdout
    url = gh_output.strip()
    if url.startswith('https://'):
        return url
    raise ValueError(f"Could not parse gist URL from gh output: {gh_output!r}")


def _extract_gist_id_from_url(url: str) -> str:
    """
    Extract gist ID from a gist URL.

    Args:
        url: Gist URL (e.g., 'https://gist.github.com/user/abc123')

    Returns:
        Gist ID string
    """
    # URL format: https://gist.github.com/<user>/<gist_id>
    parts = url.rstrip('/').split('/')
    return parts[-1]


def _has_staged_changes() -> bool:
    """
    Check if there are any staged changes to commit.

    Returns:
        True if there are staged changes, False otherwise
    """
    result = subprocess.run(
        ['git', 'diff', '--cached', '--quiet'],
        capture_output=True,
    )
    return result.returncode != 0


def _write_metadata_back(
    file_path: Path,
    metadata: Dict[str, Any],
    code_body: str,
) -> None:
    """
    Write updated metadata back to snippet file.

    Args:
        file_path: Path to snippet file
        metadata: Updated metadata dictionary
        code_body: Original code body
    """
    metadata['last_updated'] = get_today()
    updated_content = serialize_frontmatter(metadata) + "\n" + code_body
    file_path.write_text(updated_content, encoding='utf-8')


# ============================================================================
# Core Operations
# ============================================================================

def publish_snippet(
    file_path: Path,
    secret: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Publish or update a single snippet as a GitHub Gist.

    Creates a new gist if no gist_id exists, updates the existing gist otherwise.
    Writes gist_id and gist_url back to frontmatter and auto-commits.

    Args:
        file_path: Path to snippet file
        secret: If True, create as secret (unlisted) gist
        dry_run: If True, show what would happen without doing it

    Returns:
        Result dictionary with status and gist details
    """
    repo_root = get_repo_root()
    relative_path = str(file_path.relative_to(repo_root))

    # Parse snippet
    try:
        content = file_path.read_text(encoding='utf-8')
        metadata, code_body = parse_frontmatter(content)
    except Exception as e:
        return {
            'status': 'error',
            'error_type': 'parse_error',
            'message': f'Failed to parse snippet: {e}',
        }

    # Verify gist: true
    if not metadata.get('gist'):
        return {
            'status': 'error',
            'error_type': 'not_gist_enabled',
            'message': f'Snippet does not have gist: true ({relative_path})',
        }

    gist_filename = get_gist_filename(metadata)
    gist_description = _build_gist_description(metadata)
    has_gist_id = bool(metadata.get('gist_id'))

    if has_gist_id:
        action = 'update'
    else:
        action = 'create'

    if dry_run:
        return {
            'status': 'success',
            'action': action,
            'dry_run': True,
            'file_path': relative_path,
            'gist_filename': gist_filename,
            'gist_description': gist_description,
            'gist_id': metadata.get('gist_id'),
            'secret': secret,
        }

    # Write code to temp file with the gist filename
    tmp_dir = tempfile.mkdtemp()
    tmp_file = Path(tmp_dir) / gist_filename
    tmp_file.write_text(code_body.strip() + '\n', encoding='utf-8')

    try:
        if action == 'create':
            # gh gist create [--public] --desc "..." <file>
            # gh defaults to secret; --public opts into public
            cmd = [
                'gh', 'gist', 'create',
                '--desc', gist_description,
                str(tmp_file),
            ]
            if not secret:
                cmd.insert(3, '--public')
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
            )

            gist_url = _parse_gist_url(result.stdout)
            gist_id = _extract_gist_id_from_url(gist_url)

            # Write back to frontmatter
            metadata['gist_id'] = gist_id
            metadata['gist_url'] = gist_url
            _write_metadata_back(file_path, metadata, code_body)

            # Auto-commit
            committed = False
            commit_hash = None
            git_add(file_path)
            if _has_staged_changes():
                commit_msg = f"feat(gist): publish {file_path.stem} as gist"
                if git_commit(commit_msg):
                    committed = True
                    commit_hash = git_get_short_hash()

            return {
                'status': 'success',
                'action': 'created',
                'file_path': relative_path,
                'gist_id': gist_id,
                'gist_url': gist_url,
                'gist_filename': gist_filename,
                'committed': committed,
                'commit_hash': commit_hash,
            }

        else:
            # gh gist edit <gist_id> --filename <name> <localfile>
            # Replaces the content of the named file in the gist
            gist_id = metadata['gist_id']
            cmd = [
                'gh', 'gist', 'edit',
                gist_id,
                '--filename', gist_filename,
                str(tmp_file),
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
            )

            # Update last_updated in frontmatter
            _write_metadata_back(file_path, metadata, code_body)

            # Auto-commit
            committed = False
            commit_hash = None
            git_add(file_path)
            if _has_staged_changes():
                commit_msg = f"chore(gist): update {file_path.stem} gist"
                if git_commit(commit_msg):
                    committed = True
                    commit_hash = git_get_short_hash()

            return {
                'status': 'success',
                'action': 'updated',
                'file_path': relative_path,
                'gist_id': gist_id,
                'gist_url': metadata.get('gist_url', ''),
                'gist_filename': gist_filename,
                'committed': committed,
                'commit_hash': commit_hash,
            }

    except subprocess.CalledProcessError as e:
        return {
            'status': 'error',
            'error_type': 'gh_error',
            'message': f'gh command failed: {e.stderr or e.stdout}',
        }
    except Exception as e:
        return {
            'status': 'error',
            'error_type': 'unexpected_error',
            'message': str(e),
        }
    finally:
        # Cleanup temp file
        try:
            tmp_file.unlink(missing_ok=True)
            Path(tmp_dir).rmdir()
        except Exception:
            pass


def teardown_snippet(
    file_path: Path,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Delete a gist and strip gist_id/gist_url from snippet frontmatter.

    Only operates on snippets that have gist_id but gist is falsy/missing.

    Args:
        file_path: Path to snippet file
        dry_run: If True, show what would happen without doing it

    Returns:
        Result dictionary with status
    """
    repo_root = get_repo_root()
    relative_path = str(file_path.relative_to(repo_root))

    try:
        content = file_path.read_text(encoding='utf-8')
        metadata, code_body = parse_frontmatter(content)
    except Exception as e:
        return {
            'status': 'error',
            'error_type': 'parse_error',
            'message': f'Failed to parse snippet: {e}',
        }

    gist_id = metadata.get('gist_id')
    if not gist_id:
        return {
            'status': 'error',
            'error_type': 'no_gist_id',
            'message': f'Snippet has no gist_id to teardown ({relative_path})',
        }

    if dry_run:
        return {
            'status': 'success',
            'action': 'teardown',
            'dry_run': True,
            'file_path': relative_path,
            'gist_id': gist_id,
        }

    try:
        # gh gist delete <gist_id>
        cmd = ['gh', 'gist', 'delete', gist_id, '--yes']
        subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        return {
            'status': 'error',
            'error_type': 'gh_error',
            'message': f'gh gist delete failed: {e.stderr or e.stdout}',
        }

    # Strip gist_id and gist_url from frontmatter
    metadata.pop('gist_id', None)
    metadata.pop('gist_url', None)
    _write_metadata_back(file_path, metadata, code_body)

    # Auto-commit
    committed = False
    commit_hash = None
    git_add(file_path)
    if _has_staged_changes():
        commit_msg = f"chore(gist): teardown {file_path.stem} gist"
        if git_commit(commit_msg):
            committed = True
            commit_hash = git_get_short_hash()

    return {
        'status': 'success',
        'action': 'torn_down',
        'file_path': relative_path,
        'gist_id': gist_id,
        'committed': committed,
        'commit_hash': commit_hash,
    }


def sync_all(
    secret: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Sync all snippets: create, update, or teardown gists as needed.

    Logic:
    - gist:true + no gist_id -> create
    - gist:true + gist_id -> update
    - gist falsy/missing + gist_id -> teardown
    - no gist + no gist_id -> skip

    Args:
        secret: If True, create new gists as secret
        dry_run: If True, show what would happen without doing it

    Returns:
        Result dictionary with lists of actions taken
    """
    results = {
        'status': 'success',
        'created': [],
        'updated': [],
        'torn_down': [],
        'skipped': [],
        'errors': [],
    }

    for file_path in find_all_snippets():
        try:
            content = file_path.read_text(encoding='utf-8')
            metadata, _ = parse_frontmatter(content)
        except Exception:
            continue

        gist_enabled = metadata.get('gist', False)
        has_gist_id = bool(metadata.get('gist_id'))

        if gist_enabled and not has_gist_id:
            # Create new gist
            result = publish_snippet(file_path, secret=secret, dry_run=dry_run)
            if result['status'] == 'success':
                results['created'].append(result)
            else:
                results['errors'].append(result)

        elif gist_enabled and has_gist_id:
            # Update existing gist
            result = publish_snippet(file_path, secret=secret, dry_run=dry_run)
            if result['status'] == 'success':
                results['updated'].append(result)
            else:
                results['errors'].append(result)

        elif not gist_enabled and has_gist_id:
            # Teardown: gist disabled but has gist_id
            result = teardown_snippet(file_path, dry_run=dry_run)
            if result['status'] == 'success':
                results['torn_down'].append(result)
            else:
                results['errors'].append(result)

        else:
            # No gist involvement, skip
            repo_root = get_repo_root()
            results['skipped'].append(str(file_path.relative_to(repo_root)))

    if results['errors']:
        results['status'] = 'partial'

    return results


def gist_status() -> Dict[str, Any]:
    """
    Show publish status for all snippets with gist involvement.

    Categorizes snippets into:
    - published: gist:true + has gist_id
    - unpublished: gist:true + no gist_id
    - pending_teardown: gist falsy/missing + has gist_id

    Returns:
        Result dictionary with categorized snippet lists
    """
    results = {
        'status': 'success',
        'published': [],
        'unpublished': [],
        'pending_teardown': [],
        'total_snippets': 0,
    }

    repo_root = get_repo_root()

    for file_path in find_all_snippets():
        try:
            content = file_path.read_text(encoding='utf-8')
            metadata, _ = parse_frontmatter(content)
        except Exception:
            continue

        results['total_snippets'] += 1

        gist_enabled = metadata.get('gist', False)
        has_gist_id = bool(metadata.get('gist_id'))
        relative_path = str(file_path.relative_to(repo_root))

        entry = {
            'file_path': relative_path,
            'title': metadata.get('title', 'Untitled'),
            'gist_id': metadata.get('gist_id'),
            'gist_url': metadata.get('gist_url'),
        }

        if gist_enabled and has_gist_id:
            results['published'].append(entry)
        elif gist_enabled and not has_gist_id:
            results['unpublished'].append(entry)
        elif not gist_enabled and has_gist_id:
            results['pending_teardown'].append(entry)

    return results


# ============================================================================
# CLI
# ============================================================================

def main():
    """
    Main entry point for gist CLI.
    """
    parser = argparse.ArgumentParser(
        description='Publish snippets as GitHub Gists.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  ./gist sql/my-query.md              Publish or update a single snippet
  ./gist 550e8400-...-446655440000    Publish by UUID
  ./gist sql/my-query.md --secret     Create as secret (unlisted) gist
  ./gist --all                        Sync all gist-marked snippets
  ./gist --status                     Show publish status
  ./gist --all --dry-run              Preview sync actions
""",
    )

    parser.add_argument(
        'identifier',
        nargs='?',
        help='Snippet file path (relative to repo root) or UUID',
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Publish/update all gist:true snippets, teardown gist:false with gist_id',
    )
    parser.add_argument(
        '--status',
        action='store_true',
        help='Show publish status for all gist-marked snippets',
    )
    parser.add_argument(
        '--secret',
        action='store_true',
        help='Create gist as secret (unlisted)',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would happen without doing it',
    )
    parser.add_argument(
        '--format',
        choices=['human', 'json'],
        default='human',
        help='Output format (default: human)',
    )

    args = parser.parse_args()

    # Validate argument combinations
    if not args.identifier and not args.all and not args.status:
        parser.error('Provide a snippet identifier, --all, or --status')

    if args.identifier and args.all:
        parser.error('Cannot use both identifier and --all')

    if args.identifier and args.status:
        parser.error('Cannot use both identifier and --status')

    # Dispatch
    if args.status:
        result = gist_status()

        if args.format == 'json':
            print(json.dumps(result, indent=2))
        else:
            published = result['published']
            unpublished = result['unpublished']
            pending = result['pending_teardown']

            print(f"\n{Colors.BOLD}Gist Status{Colors.NC}")
            print(f"Total snippets: {result['total_snippets']}\n")

            if published:
                print(f"{Colors.GREEN}Published ({len(published)}):{Colors.NC}")
                for entry in published:
                    print(f"  {entry['title']}")
                    print(f"    {entry['file_path']}")
                    print(f"    {entry['gist_url']}")
                print()

            if unpublished:
                print(f"{Colors.YELLOW}Unpublished ({len(unpublished)}):{Colors.NC}")
                for entry in unpublished:
                    print(f"  {entry['title']}")
                    print(f"    {entry['file_path']}")
                print()

            if pending:
                print(f"{Colors.RED}Pending Teardown ({len(pending)}):{Colors.NC}")
                for entry in pending:
                    print(f"  {entry['title']}")
                    print(f"    {entry['file_path']}")
                    print(f"    gist_id: {entry['gist_id']}")
                print()

            if not published and not unpublished and not pending:
                log_info("No snippets have gist involvement")

        sys.exit(0)

    elif args.all:
        result = sync_all(secret=args.secret, dry_run=args.dry_run)

        if args.format == 'json':
            print(json.dumps(result, indent=2))
        else:
            prefix = "[DRY RUN] " if args.dry_run else ""
            created = result['created']
            updated = result['updated']
            torn_down = result['torn_down']
            errors = result['errors']

            if created:
                log_success(f"{prefix}Created {len(created)} gist(s)")
                for r in created:
                    print(f"  {r['file_path']} -> {r.get('gist_url', 'N/A')}")

            if updated:
                log_success(f"{prefix}Updated {len(updated)} gist(s)")
                for r in updated:
                    print(f"  {r['file_path']}")

            if torn_down:
                log_warn(f"{prefix}Torn down {len(torn_down)} gist(s)")
                for r in torn_down:
                    print(f"  {r['file_path']} (gist_id: {r['gist_id']})")

            if errors:
                log_error(f"{len(errors)} error(s)")
                for r in errors:
                    print(f"  {r.get('message', 'Unknown error')}")

            if not created and not updated and not torn_down and not errors:
                log_info("Nothing to do")

        sys.exit(0 if result['status'] != 'error' else 1)

    else:
        # Single snippet
        try:
            file_path = resolve_snippet(args.identifier)
        except FileNotFoundError as e:
            if args.format == 'json':
                print(json.dumps({
                    'status': 'error',
                    'error_type': 'not_found',
                    'message': str(e),
                }, indent=2))
            else:
                log_error(str(e))
            sys.exit(1)

        result = publish_snippet(
            file_path,
            secret=args.secret,
            dry_run=args.dry_run,
        )

        if args.format == 'json':
            print(json.dumps(result, indent=2))
        else:
            if result['status'] == 'success':
                action = result.get('action', 'published')
                if args.dry_run:
                    log_info(f"[DRY RUN] Would {result.get('action', 'publish')}: {result['file_path']}")
                    log_info(f"  Gist filename: {result['gist_filename']}")
                else:
                    log_success(f"Gist {action}: {result['file_path']}")
                    if result.get('gist_url'):
                        log_info(f"  URL: {result['gist_url']}")
                    if result.get('committed'):
                        log_info(f"  Committed: {result.get('commit_hash', 'N/A')}")
            else:
                log_error(result.get('message', 'Unknown error'))

        sys.exit(0 if result['status'] == 'success' else 1)


if __name__ == '__main__':
    main()
