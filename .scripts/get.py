"""
Retrieve snippets by UUID for quick clipboard access.

This script enables fast snippet retrieval using unique identifiers:
- Copy code to clipboard (default behavior)
- Print to stdout for piping
- List all snippet IDs

Usage:
    # Copy snippet code to clipboard
    ./get.py 550e8400-e29b-41d4-a716-446655440000

    # Print to stdout instead
    ./get.py 550e8400-e29b-41d4-a716-446655440000 --print

    # List all snippet IDs
    ./get.py --list

    # JSON output
    ./get.py 550e8400-e29b-41d4-a716-446655440000 --format json
"""

import re
import subprocess
import sys
import argparse
import json
from pathlib import Path

# Add .scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from common import (
    log_info, log_success, log_warn, log_error,
    find_snippet_by_id, get_all_snippet_ids, parse_frontmatter,
    copy_to_clipboard, Colors, get_repo_root,
    interpolate_variables, find_undeclared_placeholders
)


# ============================================================================
# Destructive Pattern Detection
# ============================================================================

DESTRUCTIVE_PATTERNS = [
    # Shell patterns
    (r'\brm\s+.*-[a-zA-Z]*r[a-zA-Z]*f', 'rm -rf (recursive force delete)'),
    (r'\brm\s+.*-[a-zA-Z]*f[a-zA-Z]*r', 'rm -rf (recursive force delete)'),
    (r'\brm\s+-rf\b', 'rm -rf (recursive force delete)'),
    (r'\brm\s+-f\b', 'rm -f (force delete)'),
    (r'\brm\s+-r\b', 'rm -r (recursive delete)'),
    (r'\brm\s+--force\b', 'rm --force (force delete)'),
    (r'\bmkfs\b', 'mkfs (format filesystem)'),
    (r'\bdd\b.*\bof=', 'dd with of= (raw disk write)'),
    (r'\bkill\s+-9\b', 'kill -9 (force kill)'),
    (r'\bkillall\b', 'killall (kill processes by name)'),
    (r'\bchmod\s+-R\b', 'chmod -R (recursive permission change)'),
    (r'\bchown\s+-R\b', 'chown -R (recursive ownership change)'),
    (r'\bgit\s+push\s+--force\b', 'git push --force'),
    (r'\bgit\s+reset\s+--hard\b', 'git reset --hard'),
    # SQL patterns (inside shell wrappers like psql -c, snowsql -q, etc.)
    (r'\bDROP\s+(TABLE|DATABASE|SCHEMA|VIEW|INDEX)\b', 'DROP statement'),
    (r'\bTRUNCATE\b', 'TRUNCATE statement'),
    (r'\bDELETE\s+FROM\b', 'DELETE FROM statement'),
    (r'\bALTER\s+TABLE\b.*\bDROP\b', 'ALTER TABLE ... DROP'),
]


def is_destructive(code: str) -> tuple:
    """
    Scan code for destructive patterns.

    Args:
        code: Shell code to scan

    Returns:
        Tuple of (is_destructive, matched_description)
    """
    for pattern, description in DESTRUCTIVE_PATTERNS:
        if re.search(pattern, code, re.IGNORECASE):
            return (True, description)
    return (False, '')


def run_snippet(
    snippet_id: str,
    cli_vars: dict = None,
    raw: bool = False
) -> dict:
    """
    Execute a shell snippet after safety checks and confirmation.

    Args:
        snippet_id: UUID of the snippet
        cli_vars: Dictionary of variable overrides from --var flags
        raw: If True, skip variable interpolation

    Returns:
        Result dictionary
    """
    if cli_vars is None:
        cli_vars = {}

    file_path = find_snippet_by_id(snippet_id)

    if not file_path:
        return {
            'status': 'error',
            'error_type': 'not_found',
            'message': f'No snippet found with ID: {snippet_id}'
        }

    try:
        content = file_path.read_text(encoding='utf-8')
        metadata, code = parse_frontmatter(content)
    except Exception as e:
        return {
            'status': 'error',
            'error_type': 'parse_error',
            'message': f'Failed to parse snippet: {e}'
        }

    title = metadata.get('title', 'Untitled')

    # Safety gate 1: Language guard
    if metadata.get('language') != 'shell':
        return {
            'status': 'error',
            'error_type': 'language_error',
            'message': f"--run requires language: shell (got: {metadata.get('language', 'unset')})"
        }

    # Safety gate 2: Runnable check
    if not metadata.get('runnable', False):
        return {
            'status': 'error',
            'error_type': 'not_runnable',
            'message': (
                f"Snippet '{title}' is not marked as runnable. "
                "Add 'runnable: true' to frontmatter to enable execution."
            )
        }

    # Variable interpolation
    declared_vars = metadata.get('vars', [])
    if declared_vars and not raw:
        code, resolved_info, unresolved_info = interpolate_variables(
            code, declared_vars, cli_vars
        )
        parts = []
        if resolved_info:
            parts.append("Resolved: " + ", ".join(
                f"{name} ({source})" for name, (_, source) in resolved_info.items()
            ))
        if unresolved_info:
            parts.append("Unresolved: " + ", ".join(unresolved_info))
        if parts:
            for part in parts:
                print(part, file=sys.stderr)

    code_stripped = code.strip()

    # Safety gate 3: Destructive check
    destructive, matched = is_destructive(code_stripped)
    if destructive:
        return {
            'status': 'error',
            'error_type': 'destructive',
            'message': (
                f"Blocked: destructive pattern detected — {matched}. "
                "Use --print to inspect the code instead."
            )
        }

    # Safety gate 4: Confirmation prompt
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"Snippet: {title}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(code_stripped, file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    if not sys.stdin.isatty():
        return {
            'status': 'error',
            'error_type': 'no_tty',
            'message': '--run requires an interactive terminal for confirmation'
        }

    try:
        answer = input("Execute? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print(file=sys.stderr)
        return {
            'status': 'error',
            'error_type': 'cancelled',
            'message': 'Execution cancelled by user'
        }

    if answer != 'y':
        return {
            'status': 'error',
            'error_type': 'cancelled',
            'message': 'Execution cancelled by user'
        }

    # Safety gate 5: Execute
    print(f"Running: {title}", file=sys.stderr)
    result = subprocess.run(code_stripped, shell=True)

    if result.returncode != 0:
        print(f"Exit code: {result.returncode}", file=sys.stderr)

    return {
        'status': 'success',
        'action': 'executed',
        'id': snippet_id,
        'title': title,
        'exit_code': result.returncode
    }


def get_snippet_by_id(
    snippet_id: str,
    output_format: str = 'human',
    print_only: bool = False,
    cli_vars: dict = None,
    raw: bool = False
) -> dict:
    """
    Retrieve snippet by UUID and optionally copy to clipboard.

    Args:
        snippet_id: UUID of the snippet
        output_format: 'human' or 'json'
        print_only: If True, print to stdout instead of clipboard
        cli_vars: Dictionary of variable overrides from --var flags
        raw: If True, skip variable interpolation

    Returns:
        Result dictionary
    """
    if cli_vars is None:
        cli_vars = {}

    file_path = find_snippet_by_id(snippet_id)

    if not file_path:
        return {
            'status': 'error',
            'error_type': 'not_found',
            'message': f'No snippet found with ID: {snippet_id}'
        }

    try:
        content = file_path.read_text(encoding='utf-8')
        metadata, code = parse_frontmatter(content)
    except Exception as e:
        return {
            'status': 'error',
            'error_type': 'parse_error',
            'message': f'Failed to parse snippet: {e}'
        }

    # Variable interpolation
    declared_vars = metadata.get('vars', [])
    resolved_info = {}
    unresolved_info = []

    if declared_vars and not raw:
        code, resolved_info, unresolved_info = interpolate_variables(
            code, declared_vars, cli_vars
        )

        # Print resolution summary to stderr
        parts = []
        if resolved_info:
            parts.append("Resolved: " + ", ".join(
                f"{name} ({source})" for name, (_, source) in resolved_info.items()
            ))
        if unresolved_info:
            parts.append("Unresolved: " + ", ".join(unresolved_info))
        if parts:
            for part in parts:
                print(part, file=sys.stderr)

    # Check for undeclared placeholders (even if no vars field or --raw)
    if not raw:
        undeclared = find_undeclared_placeholders(code, declared_vars)
        if undeclared:
            placeholder_list = ", ".join("{{" + name + "}}" for name in undeclared)
            var_list = ", ".join(undeclared)
            print(
                f"Hint: Found {placeholder_list} in output but not in vars.\n"
                f"  Add `vars: [{var_list}]` to frontmatter to enable interpolation.",
                file=sys.stderr
            )

    repo_root = get_repo_root()
    relative_path = str(file_path.relative_to(repo_root))

    if print_only:
        # Print code to stdout
        print(code.strip())
        return {
            'status': 'success',
            'action': 'printed',
            'id': snippet_id,
            'title': metadata.get('title', 'Untitled'),
            'file_path': str(file_path),
            'relative_path': relative_path
        }
    else:
        # Copy to clipboard
        if copy_to_clipboard(code.strip()):
            return {
                'status': 'success',
                'action': 'copied',
                'id': snippet_id,
                'title': metadata.get('title', 'Untitled'),
                'file_path': str(file_path),
                'relative_path': relative_path,
                'code_length': len(code.strip())
            }
        else:
            return {
                'status': 'error',
                'error_type': 'clipboard_error',
                'message': 'Failed to copy to clipboard'
            }


def list_all_ids(output_format: str = 'human') -> dict:
    """
    List all snippet IDs with metadata.

    Args:
        output_format: 'human' or 'json'

    Returns:
        Result dictionary
    """
    snippets = get_all_snippet_ids()

    return {
        'status': 'success',
        'count': len(snippets),
        'snippets': snippets
    }


def main():
    """
    Main entry point.
    """
    parser = argparse.ArgumentParser(
        description='Retrieve snippets by UUID for quick access.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Copy snippet to clipboard
  ./get.py 550e8400-e29b-41d4-a716-446655440000

  # Print to stdout
  ./get.py 550e8400-e29b-41d4-a716-446655440000 --print

  # Run a shell snippet
  ./get.py 550e8400-e29b-41d4-a716-446655440000 --run

  # List all snippet IDs
  ./get.py --list

  # JSON output
  ./get.py --list --format json
        """
    )

    # Positional argument for UUID (optional if using --list)
    parser.add_argument('uuid', nargs='?', help='UUID of the snippet to retrieve')

    # Mutually exclusive: --print vs --run
    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument('--print', '-p', action='store_true', dest='print_only',
                              help='Print code to stdout instead of copying to clipboard')
    action_group.add_argument('--run', '-r', action='store_true',
                              help='Execute shell snippet (requires language: shell and runnable: true)')

    # Options
    parser.add_argument('--list', '-l', action='store_true',
                        help='List all snippet IDs')
    parser.add_argument('--var', action='append', metavar='NAME=VALUE',
                        help='Variable override for interpolation (repeatable)')
    parser.add_argument('--raw', action='store_true',
                        help='Skip variable interpolation, output code as-is')
    parser.add_argument('--format', choices=['human', 'json'], default='human',
                        help='Output format (default: human)')

    args = parser.parse_args()

    # --format json + --run is an error
    if args.run and args.format == 'json':
        parser.error("--run cannot be used with --format json")

    # List mode
    if args.list:
        result = list_all_ids(args.format)

        if args.format == 'json':
            print(json.dumps(result, indent=2))
        else:
            if result['count'] == 0:
                log_warn("No snippets with IDs found")
                log_info("Run '.scripts/audit.py --add-uuids' to add UUIDs to existing snippets")
            else:
                print(f"\n{Colors.BOLD}Snippet IDs ({result['count']} total):{Colors.NC}\n")
                for snippet in result['snippets']:
                    print(f"  {Colors.CYAN}{snippet['id']}{Colors.NC}")
                    print(f"    {snippet['title']} ({snippet['language']})")
                    print(f"    {snippet['relative_path']}")
                    print()
        sys.exit(0)

    # Retrieve mode - UUID required
    if not args.uuid:
        parser.error("UUID required. Use --list to see all IDs.")

    # Parse --var flags into dict
    cli_vars = {}
    if args.var:
        for var_str in args.var:
            if '=' not in var_str:
                parser.error(f"Invalid --var format: '{var_str}'. Use NAME=VALUE.")
            name, value = var_str.split('=', 1)
            cli_vars[name] = value

    # Run mode
    if args.run:
        result = run_snippet(args.uuid, cli_vars, args.raw)
        if result['status'] == 'success':
            sys.exit(result.get('exit_code', 0))
        else:
            log_error(result['message'])
            sys.exit(1)

    result = get_snippet_by_id(args.uuid, args.format, args.print_only, cli_vars, args.raw)

    if args.format == 'json':
        print(json.dumps(result, indent=2))
    else:
        if result['status'] == 'success':
            if result['action'] == 'copied':
                log_success(f"Copied '{result['title']}' to clipboard")
                log_info(f"  From: {result['relative_path']}")
            # If print_only, code was already printed
        else:
            log_error(result['message'])

    sys.exit(0 if result['status'] == 'success' else 1)


if __name__ == '__main__':
    main()
