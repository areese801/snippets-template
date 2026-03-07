"""
Search snippets by tags, language, description, title, or code content.

This script provides powerful multi-filter search with structured output:
- Filter by tags, language, dates, content
- Multi-term AND search across all fields (title, description, tags, code)
- Full-text regex search in code
- Interactive fuzzy search with preview
- JSON output for programmatic use

Usage:
    # Interactive mode
    ./search.py

    # Multi-term AND search (all terms must match)
    ./search.py --terms "select transaction"

    # Filter by tag
    ./search.py --tag dbt --tag incremental

    # Filter by language
    ./search.py --language sql

    # Full-text search in code
    ./search.py --query "SELECT.*JOIN"

    # Recently updated
    ./search.py --recently-updated 7

    # Multiple filters (AND logic)
    ./search.py --tag dbt --language sql --format json

    # List all tags with counts
    ./search.py --list-tags
"""

import sys
import argparse
import json
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Set
from collections import Counter

# Add .scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from common import (
    log_info, log_success, log_warn, log_error,
    get_repo_root, find_all_snippets, parse_frontmatter,
    Colors, copy_to_clipboard
)


def matches_filters(metadata: Dict[str, Any], code: str, filters: Dict[str, Any]) -> bool:
    """
    Check if snippet matches all filters (AND logic).

    Args:
        metadata: Snippet frontmatter metadata
        code: Snippet code content
        filters: Dictionary of filter criteria

    Returns:
        True if matches all filters
    """
    # Tag filters (AND logic - must have all specified tags)
    if 'tags' in filters and filters['tags']:
        snippet_tags = set(metadata.get('tags', []))
        required_tags = set(filters['tags'])
        if not required_tags.issubset(snippet_tags):
            return False

    # Multi-term AND search across all fields
    if 'terms' in filters and filters['terms']:
        terms = filters['terms'].lower().split()
        searchable = ' '.join([
            metadata.get('title', ''),
            metadata.get('description', ''),
            ' '.join(metadata.get('tags', [])),
            code
        ]).lower()

        if not all(term in searchable for term in terms):
            return False

    # Language filter
    if 'language' in filters and filters['language']:
        if metadata.get('language', '').lower() != filters['language'].lower():
            return False

    # Title contains
    if 'title_contains' in filters and filters['title_contains']:
        title = metadata.get('title', '').lower()
        if filters['title_contains'].lower() not in title:
            return False

    # Description contains
    if 'description_contains' in filters and filters['description_contains']:
        desc = metadata.get('description', '').lower()
        if filters['description_contains'].lower() not in desc:
            return False

    # Code regex search
    if 'query' in filters and filters['query']:
        try:
            pattern = re.compile(filters['query'], re.IGNORECASE | re.MULTILINE)
            if not pattern.search(code):
                return False
        except re.error:
            log_warn(f"Invalid regex pattern: {filters['query']}")
            return False

    # Date filters
    created = metadata.get('created', '')

    if 'created_after' in filters and filters['created_after']:
        if created < filters['created_after']:
            return False

    if 'created_before' in filters and filters['created_before']:
        if created > filters['created_before']:
            return False

    # Recently updated filter
    if 'recently_updated_days' in filters and filters['recently_updated_days']:
        last_updated = metadata.get('last_updated', metadata.get('created', ''))
        if last_updated:
            try:
                updated_date = datetime.strptime(last_updated, '%Y-%m-%d')
                cutoff = datetime.now() - timedelta(days=filters['recently_updated_days'])
                if updated_date < cutoff:
                    return False
            except ValueError:
                return False

    return True


def search_snippets(filters: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Search for snippets matching filters.

    Args:
        filters: Dictionary of filter criteria

    Returns:
        List of matching snippet dictionaries
    """
    repo_root = get_repo_root()
    results = []

    for file_path in find_all_snippets():
        try:
            content = file_path.read_text(encoding='utf-8')
            metadata, code = parse_frontmatter(content)

            if matches_filters(metadata, code, filters):
                # Get preview (first 3 lines of code)
                code_lines = code.strip().split('\n')
                preview = '\n'.join(code_lines[:3])
                if len(code_lines) > 3:
                    preview += '...'

                results.append({
                    'id': metadata.get('id'),
                    'file_path': str(file_path),
                    'relative_path': str(file_path.relative_to(repo_root)),
                    'metadata': metadata,
                    'preview': preview,
                    'line_count': len(code_lines)
                })

        except Exception as e:
            log_warn(f"Failed to parse {file_path}: {e}")
            continue

    return results


def list_all_tags() -> Dict[str, int]:
    """
    List all tags used across snippets with counts.

    Returns:
        Dictionary of tag -> count
    """
    tag_counter = Counter()

    for file_path in find_all_snippets():
        try:
            content = file_path.read_text(encoding='utf-8')
            metadata, _ = parse_frontmatter(content)
            tags = metadata.get('tags', [])
            tag_counter.update(tags)
        except Exception:
            continue

    return dict(tag_counter)


def display_results_interactive(results: List[Dict[str, Any]], filters: Dict[str, Any]):
    """
    Display search results in interactive format.

    Args:
        results: List of matching snippets
        filters: Filter criteria used
    """
    if not results:
        log_warn("No snippets found matching criteria")
        return

    # Show filter summary
    filter_parts = []
    if filters.get('tags'):
        filter_parts.append(f"tags={','.join(filters['tags'])}")
    if filters.get('language'):
        filter_parts.append(f"language={filters['language']}")
    if filters.get('terms'):
        filter_parts.append(f"terms='{filters['terms']}'")
    if filters.get('query'):
        filter_parts.append(f"query='{filters['query']}'")

    filter_summary = ' AND '.join(filter_parts) if filter_parts else 'all snippets'

    print(f"\n{Colors.GREEN}Found {len(results)} snippet(s) matching: {filter_summary}{Colors.NC}\n")

    for i, result in enumerate(results, 1):
        metadata = result['metadata']
        print(f"{Colors.BOLD}[{i}] {result['relative_path']}{Colors.NC} ({metadata.get('language', 'unknown')})")
        print(f"    Title: {metadata.get('title', 'N/A')}")

        # Show ID if present
        snippet_id = result.get('id') or metadata.get('id')
        if snippet_id:
            print(f"    ID: {Colors.CYAN}{snippet_id}{Colors.NC}")

        tags = metadata.get('tags', [])
        if tags:
            print(f"    Tags: [{', '.join(tags)}]")

        print(f"    Desc: {metadata.get('description', 'N/A')}")
        print(f"    Preview: {result['preview'][:80]}...")
        print()

    # Interactive actions (only if TTY)
    if not sys.stdin.isatty():
        return

    print(f"{Colors.CYAN}Actions:{Colors.NC}")
    print("  [number]  View snippet and copy code to clipboard")
    print("  [b or m]  Back to main menu")

    choice = input("\nChoice: ").strip().lower()

    if choice in ('b', 'm', 'q'):
        return

    if choice.isdigit():
        index = int(choice) - 1
        if 0 <= index < len(results):
            file_path = Path(results[index]['file_path'])
            content = file_path.read_text(encoding='utf-8')

            # Extract code body (without frontmatter)
            metadata, code_body = parse_frontmatter(content)

            # Display full content
            print("\n" + "=" * 60)
            print(content)
            print("=" * 60)

            # Copy code to clipboard
            if copy_to_clipboard(code_body.strip()):
                log_success("Code copied to clipboard!")
            else:
                log_warn("Could not copy to clipboard")


def interactive_search():
    """
    Interactive search mode with filter building.
    """
    filters = {}

    print(f"\n{Colors.BOLD}Build Your Search Query{Colors.NC}\n")

    # Multi-term search (most common)
    keyword_input = input("Search terms (space-separated, all must match): ").strip()
    if keyword_input:
        filters['terms'] = keyword_input

    # Tag filter
    tags_input = input("Tags (comma-separated, optional): ").strip()
    if tags_input:
        filters['tags'] = [t.strip() for t in tags_input.split(',')]

    # Language filter
    lang_input = input("Language (sql/python/shell/etc, optional): ").strip()
    if lang_input:
        filters['language'] = lang_input

    # Code search
    code_input = input("Search in code (regex, optional): ").strip()
    if code_input:
        filters['query'] = code_input

    # Execute search
    log_info("Searching...")
    results = search_snippets(filters)

    # Display results
    display_results_interactive(results, filters)


def main():
    """
    Main entry point.
    """
    parser = argparse.ArgumentParser(
        description='Search code snippets with multi-filter support.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode
  ./search.py

  # Multi-term AND search (all terms must match somewhere)
  ./search.py --terms "select transaction"
  ./search.py --terms "api retry" --format json

  # Filter by tags (AND logic)
  ./search.py --tag dbt --tag incremental

  # Filter by language
  ./search.py --language sql

  # Full-text regex search
  ./search.py --query "SELECT.*JOIN"

  # Multiple filters
  ./search.py --tag dbt --language sql --format json

  # Recently updated snippets
  ./search.py --recently-updated 7

  # List all tags
  ./search.py --list-tags
        """
    )

    # Positional arguments for quick search
    parser.add_argument('search_terms', nargs='*', help='Search terms (all must match)')

    # Filter options
    parser.add_argument('--tag', action='append', dest='tags', help='Filter by tag (can specify multiple)')
    parser.add_argument('--language', help='Filter by language')
    parser.add_argument('--terms', help='Space-separated terms - ALL must match somewhere (title, description, tags, or code)')
    parser.add_argument('--title-contains', help='Filter by title substring')
    parser.add_argument('--description-contains', help='Filter by description substring')
    parser.add_argument('--query', help='Full-text regex search in code')
    parser.add_argument('--created-after', help='Filter by created date (YYYY-MM-DD)')
    parser.add_argument('--created-before', help='Filter by created date (YYYY-MM-DD)')
    parser.add_argument('--recently-updated', type=int, metavar='DAYS',
                        help='Show snippets updated in last N days')

    # Special modes
    parser.add_argument('--list-tags', action='store_true', help='List all tags with counts')
    parser.add_argument('--interactive', action='store_true', help='Force interactive mode')

    # Output
    parser.add_argument('--format', choices=['human', 'json'], default='human')

    args = parser.parse_args()

    # List tags mode
    if args.list_tags:
        tags = list_all_tags()
        if args.format == 'json':
            print(json.dumps(tags, indent=2))
        else:
            print(f"\n{Colors.BOLD}All Tags:{Colors.NC}\n")
            for tag, count in sorted(tags.items(), key=lambda x: x[1], reverse=True):
                print(f"  {tag}: {count}")
        sys.exit(0)

    # Combine positional args with --terms if both provided
    if args.search_terms:
        positional_terms = ' '.join(args.search_terms)
        if args.terms:
            args.terms = f"{args.terms} {positional_terms}"
        else:
            args.terms = positional_terms

    # Interactive mode
    if args.interactive or (not any([args.tags, args.language, args.terms,
                                      args.title_contains, args.description_contains,
                                      args.query, args.created_after, args.created_before,
                                      args.recently_updated])):
        interactive_search()
        sys.exit(0)

    # Build filters from args
    filters = {}

    if args.tags:
        filters['tags'] = args.tags
    if args.language:
        filters['language'] = args.language
    if args.terms:
        filters['terms'] = args.terms
    if args.title_contains:
        filters['title_contains'] = args.title_contains
    if args.description_contains:
        filters['description_contains'] = args.description_contains
    if args.query:
        filters['query'] = args.query
    if args.created_after:
        filters['created_after'] = args.created_after
    if args.created_before:
        filters['created_before'] = args.created_before
    if args.recently_updated:
        filters['recently_updated_days'] = args.recently_updated

    # Execute search
    results = search_snippets(filters)

    # Output results
    if args.format == 'json':
        output = {
            'status': 'success',
            'query': filters,
            'count': len(results),
            'results': results
        }
        print(json.dumps(output, indent=2))
    else:
        display_results_interactive(results, filters)

    sys.exit(0)


if __name__ == '__main__':
    main()
