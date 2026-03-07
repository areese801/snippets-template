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

import sys
import argparse
import json
from pathlib import Path

# Add .scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from common import (
    log_info, log_success, log_warn, log_error,
    find_snippet_by_id, get_all_snippet_ids, parse_frontmatter,
    copy_to_clipboard, Colors, get_repo_root
)


def get_snippet_by_id(snippet_id: str, output_format: str = 'human', print_only: bool = False) -> dict:
    """
    Retrieve snippet by UUID and optionally copy to clipboard.

    Args:
        snippet_id: UUID of the snippet
        output_format: 'human' or 'json'
        print_only: If True, print to stdout instead of clipboard

    Returns:
        Result dictionary
    """
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

  # List all snippet IDs
  ./get.py --list

  # JSON output
  ./get.py --list --format json
        """
    )

    # Positional argument for UUID (optional if using --list)
    parser.add_argument('uuid', nargs='?', help='UUID of the snippet to retrieve')

    # Options
    parser.add_argument('--print', '-p', action='store_true', dest='print_only',
                        help='Print code to stdout instead of copying to clipboard')
    parser.add_argument('--list', '-l', action='store_true',
                        help='List all snippet IDs')
    parser.add_argument('--format', choices=['human', 'json'], default='human',
                        help='Output format (default: human)')

    args = parser.parse_args()

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

    result = get_snippet_by_id(args.uuid, args.format, args.print_only)

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
