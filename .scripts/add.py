#!/usr/bin/env python3
"""
Add a new code snippet to the repository.

This script supports both interactive (human) and programmatic (AI) usage:
- Interactive: Prompts for code and metadata with auto-suggestions
- Programmatic: JSON or CLI arguments for automated snippet creation

Usage:
    # Interactive mode
    ./add.py

    # Pre-fill some fields
    ./add.py --language sql --tags dbt,incremental

    # Programmatic JSON mode
    ./add.py --json '{"title": "...", "code": "...", "language": "sql"}'

    # Programmatic CLI mode
    ./add.py --title "My Snippet" --language python --code "..."
    ./add.py --title "My Snippet" --language python --code-file snippet.py
"""

import sys
import argparse
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add .scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from common import (
    log_info, log_success, log_warn, log_error,
    get_today, slugify, normalize_tag, suggest_tags,
    detect_language, get_language_directory, serialize_frontmatter,
    get_repo_root, git_add, git_commit, validate_frontmatter,
    SUPPORTED_LANGUAGES, Colors, strip_code_fences, generate_uuid
)


def read_multiline_input(prompt: str = "Paste your code snippet (press Ctrl+D when done):") -> str:
    """
    Read multiline input from stdin until EOF (Ctrl+D).

    Args:
        prompt: Prompt message to display

    Returns:
        Multiline input as string
    """
    print(f"\n{Colors.CYAN}{prompt}{Colors.NC}")
    lines = []
    try:
        while True:
            line = input()
            lines.append(line)
    except EOFError:
        pass
    return '\n'.join(lines)


def prompt_with_default(prompt: str, default: Optional[str] = None, required: bool = True) -> str:
    """
    Prompt user for input with optional default value.

    Args:
        prompt: Prompt message
        default: Default value to show
        required: Whether input is required

    Returns:
        User input or default value
    """
    if default:
        display_prompt = f"{prompt} [{default}]: "
    else:
        display_prompt = f"{prompt}: "

    while True:
        value = input(display_prompt).strip()

        if value:
            return value
        elif default:
            return default
        elif not required:
            return ""
        else:
            log_warn("This field is required. Please enter a value.")


def prompt_tags(suggested: List[str]) -> List[str]:
    """
    Prompt user to accept, edit, or add tags.

    Args:
        suggested: Auto-suggested tags

    Returns:
        Final list of tags
    """
    print(f"\n{Colors.CYAN}Suggested tags:{Colors.NC} {', '.join(suggested)}")
    print(f"{Colors.CYAN}[Enter]{Colors.NC} to accept, {Colors.CYAN}[e]dit{Colors.NC}, {Colors.CYAN}[a]dd{Colors.NC}, or {Colors.CYAN}[r]emove{Colors.NC}")

    choice = input("Choice: ").strip().lower()

    if choice == '' or choice == 'y':
        return suggested
    elif choice == 'e':
        tags_str = input("Enter tags (comma-separated): ").strip()
        return [normalize_tag(tag) for tag in tags_str.split(',') if tag.strip()]
    elif choice == 'a':
        additional = input("Add tags (comma-separated): ").strip()
        new_tags = [normalize_tag(tag) for tag in additional.split(',') if tag.strip()]
        return suggested + new_tags
    elif choice == 'r':
        to_remove = input("Remove tags (comma-separated): ").strip()
        remove_set = {normalize_tag(tag) for tag in to_remove.split(',') if tag.strip()}
        return [tag for tag in suggested if tag not in remove_set]
    else:
        return suggested


def interactive_add() -> Dict[str, Any]:
    """
    Interactive mode: prompt user for code and metadata.

    Returns:
        Dictionary with snippet data
    """
    log_info("Interactive snippet creation mode")

    # Get code first (strip markdown fences if present)
    code = strip_code_fences(read_multiline_input())
    if not code.strip():
        log_error("No code provided. Exiting.")
        sys.exit(1)

    # Auto-detect language
    detected_lang = detect_language(code)
    log_info(f"Detected language: {detected_lang}")

    # Prompt for metadata
    title = prompt_with_default("\nTitle", required=True)
    language = prompt_with_default("Language", default=detected_lang, required=True)

    if language not in SUPPORTED_LANGUAGES:
        log_warn(f"Language '{language}' not in supported list: {SUPPORTED_LANGUAGES}")
        language = prompt_with_default("Choose supported language", default='text', required=True)

    # Auto-suggest tags
    suggested_tags = suggest_tags(code, language)
    tags = prompt_tags(suggested_tags)

    description = prompt_with_default("\nDescription (one sentence)", required=True)

    return {
        'id': generate_uuid(),
        'title': title,
        'language': language,
        'tags': tags,
        'description': description,
        'code': code,
        'created': get_today(),
        'last_updated': get_today(),
        'reviewed': True  # Manually added snippets are reviewed by default
    }


def create_snippet_file(data: Dict[str, Any], output_format: str = 'human') -> Dict[str, Any]:
    """
    Create snippet file from data.

    Args:
        data: Snippet data dictionary
        output_format: 'human' or 'json'

    Returns:
        Result dictionary with file info
    """
    # Generate filename from title
    filename = slugify(data['title']) + '.md'

    # Get target directory
    try:
        directory = get_language_directory(data['language'])
    except ValueError as e:
        log_error(str(e))
        return {
            'status': 'error',
            'error_type': 'validation_error',
            'message': str(e)
        }

    # Create full path
    repo_root = get_repo_root()
    target_dir = repo_root / directory
    target_dir.mkdir(parents=True, exist_ok=True)
    file_path = target_dir / filename

    # Check if file already exists
    if file_path.exists():
        log_warn(f"File already exists: {file_path}")
        if output_format == 'human' and sys.stdin.isatty():
            overwrite = input("Overwrite? [y/N]: ").strip().lower()
            if overwrite != 'y':
                log_info("Cancelled.")
                return {
                    'status': 'cancelled',
                    'message': 'User cancelled overwrite'
                }
        else:
            return {
                'status': 'error',
                'error_type': 'file_exists',
                'message': f'File already exists: {file_path}'
            }

    # Build frontmatter metadata (id first for visibility)
    metadata = {
        'id': data.get('id', generate_uuid()),
        'title': data['title'],
        'language': data['language'],
        'tags': data['tags'],
        'description': data['description'],
        'created': data.get('created', get_today()),
        'last_updated': data.get('last_updated', get_today()),
    }

    if data.get('reviewed') is not None:
        metadata['reviewed'] = data['reviewed']

    # Validate frontmatter
    errors = validate_frontmatter(metadata)
    if errors:
        log_error("Validation errors:")
        for error in errors:
            log_error(f"  - {error}")
        return {
            'status': 'error',
            'error_type': 'validation_error',
            'message': 'Frontmatter validation failed',
            'errors': errors
        }

    # Create file content
    frontmatter = serialize_frontmatter(metadata)
    content = frontmatter + "\n" + data['code'] + "\n"

    # Preview in human mode (only for truly interactive sessions)
    # Skip preview if running in non-interactive context (no stdin)
    if output_format == 'human' and sys.stdin.isatty():
        print(f"\n{Colors.BOLD}Preview:{Colors.NC}")
        print("─" * 60)
        print(content)
        print("─" * 60)

        confirm = input("\n[s]ave, [e]dit metadata, [c]ancel: ").strip().lower()
        if confirm == 'c':
            log_info("Cancelled.")
            return {'status': 'cancelled', 'message': 'User cancelled'}
        elif confirm == 'e':
            # TODO: Allow editing - for now just cancel
            log_info("Editing not yet implemented. Cancelled.")
            return {'status': 'cancelled', 'message': 'User requested edit'}

    # Write file
    try:
        file_path.write_text(content, encoding='utf-8')
        log_success(f"Created: {file_path}")
    except Exception as e:
        log_error(f"Failed to write file: {e}")
        return {
            'status': 'error',
            'error_type': 'write_error',
            'message': str(e)
        }

    # Git add and commit
    committed = False
    commit_hash = None

    # Prompt for commit in interactive mode
    should_commit = False
    if output_format == 'human' and sys.stdin.isatty():
        commit_choice = input("\nCommit to git? [Y/n]: ").strip().lower()
        should_commit = commit_choice in ['', 'y', 'yes']
    elif output_format == 'json':
        # Auto-commit in programmatic mode for backward compatibility
        should_commit = True

    if should_commit:
        if git_add(file_path):
            commit_msg = f"feat({directory}): add {data['title']}"
            if git_commit(commit_msg):
                log_success("Committed to git")
                committed = True
                # Get commit hash
                import subprocess
                try:
                    result = subprocess.run(
                        ['git', 'rev-parse', '--short', 'HEAD'],
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    commit_hash = result.stdout.strip()
                except:
                    pass
            else:
                log_warn("Failed to commit (file staged)")
        else:
            log_warn("Failed to stage file")
    else:
        log_info("Skipped git commit (file saved locally)")

    # Return result
    return {
        'status': 'success',
        'id': metadata['id'],
        'file_path': str(file_path),
        'filename': filename,
        'directory': directory,
        'committed': committed,
        'commit_hash': commit_hash
    }


def main():
    """
    Main entry point.
    """
    parser = argparse.ArgumentParser(
        description='Add a new code snippet to the repository.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode
  ./add.py

  # Pre-fill language and tags
  ./add.py --language sql --tags dbt,incremental

  # Programmatic JSON mode
  ./add.py --json '{"title": "My Snippet", "code": "...", "language": "sql"}'

  # Programmatic CLI mode
  ./add.py --title "My Snippet" --language python --code "import sys"
  ./add.py --title "My Snippet" --language python --code-file snippet.py
        """
    )

    # Mode selection
    parser.add_argument('--json', type=str, help='JSON input with all fields')
    parser.add_argument('--interactive', action='store_true', help='Force interactive mode')

    # CLI arguments for programmatic mode
    parser.add_argument('--title', type=str, help='Snippet title')
    parser.add_argument('--language', type=str, help='Programming language')
    parser.add_argument('--tags', type=str, help='Comma-separated tags')
    parser.add_argument('--description', type=str, help='One-sentence description')
    parser.add_argument('--code', type=str, help='Code content')
    parser.add_argument('--code-file', type=str, help='Read code from file')

    # Options
    parser.add_argument('--no-commit', action='store_true', help='Skip git commit')
    parser.add_argument('--format', choices=['human', 'json'], default='human',
                        help='Output format (default: human)')

    args = parser.parse_args()

    # Determine mode
    if args.json:
        # JSON mode
        try:
            data = json.loads(args.json)
        except json.JSONDecodeError as e:
            log_error(f"Invalid JSON: {e}")
            sys.exit(1)

        # Ensure required fields
        if 'code' not in data or not data['code']:
            log_error("JSON must include 'code' field")
            sys.exit(1)

        # Fill in defaults
        if 'created' not in data:
            data['created'] = get_today()
        if 'last_updated' not in data:
            data['last_updated'] = get_today()

    elif args.title or args.code or args.code_file:
        # CLI arguments mode
        data = {}

        # Get code
        if args.code_file:
            try:
                code_path = Path(args.code_file)
                data['code'] = strip_code_fences(code_path.read_text(encoding='utf-8'))
            except Exception as e:
                log_error(f"Failed to read code file: {e}")
                sys.exit(1)
        elif args.code:
            data['code'] = strip_code_fences(args.code)
        else:
            log_error("Must provide --code or --code-file")
            sys.exit(1)

        # Get metadata
        data['title'] = args.title or "Untitled Snippet"
        data['language'] = args.language or detect_language(data['code'])
        data['tags'] = [normalize_tag(t) for t in args.tags.split(',')] if args.tags else []
        data['description'] = args.description or ""

        if not data['description']:
            log_error("Description is required in programmatic mode (--description)")
            sys.exit(1)

        data['id'] = generate_uuid()
        data['created'] = get_today()
        data['last_updated'] = get_today()
        data['reviewed'] = True

    else:
        # Interactive mode (default)
        data = interactive_add()

    # Create snippet file
    result = create_snippet_file(data, output_format=args.format)

    # Output result
    if args.format == 'json':
        print(json.dumps(result, indent=2))
        sys.exit(0 if result['status'] == 'success' else 1)
    else:
        if result['status'] == 'success':
            sys.exit(0)
        else:
            sys.exit(1)


if __name__ == '__main__':
    main()
