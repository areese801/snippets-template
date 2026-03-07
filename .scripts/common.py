#!/usr/bin/env python3
"""
Shared utilities for snippet management scripts.

This module provides common functionality used across all CRUD scripts:
- Color logging with timestamps
- Frontmatter parsing and serialization
- Language detection and mapping
- File operations (slugify, find files)
- Git operations
- Date validation
- Tag normalization and suggestion
"""

import re
import subprocess
import uuid
import yaml
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ============================================================================
# Color Codes and Logging
# ============================================================================

class Colors:
    """
    ANSI color codes for terminal output.
    """
    BLUE = '\033[0;34m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    RED = '\033[0;31m'
    CYAN = '\033[0;36m'
    BOLD = '\033[1m'
    NC = '\033[0m'  # No Color


def log_info(message: str) -> None:
    """
    Log informational message with blue timestamp.

    Args:
        message: Message to log
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"{Colors.BLUE}[{timestamp}]{Colors.NC} {message}")


def log_success(message: str) -> None:
    """
    Log success message with green timestamp.

    Args:
        message: Message to log
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"{Colors.GREEN}[{timestamp}]{Colors.NC} {message}")


def log_warn(message: str) -> None:
    """
    Log warning message with yellow timestamp.

    Args:
        message: Message to log
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"{Colors.YELLOW}[{timestamp}]{Colors.NC} {message}")


def log_error(message: str) -> None:
    """
    Log error message with red timestamp to stderr.

    Args:
        message: Message to log
    """
    import sys
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"{Colors.RED}[{timestamp}]{Colors.NC} {message}", file=sys.stderr)


# ============================================================================
# Terminal Input Helpers
# ============================================================================

def getch() -> str:
    """
    Read a single character from stdin without requiring Enter.

    Works on Unix/macOS. Falls back to regular input on Windows or
    if terminal is not available.

    Returns:
        Single character string
    """
    import sys

    # Check if stdin is a TTY
    if not sys.stdin.isatty():
        return input()

    try:
        import tty
        import termios

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            # Handle Ctrl+C
            if ch == '\x03':
                raise KeyboardInterrupt
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    except (ImportError, termios.error):
        # Fall back to regular input
        return input()


def get_menu_choice(prompt: str = "Choice: ", valid_chars: str = "") -> str:
    """
    Get menu choice with single-char support for specified characters.

    For characters in valid_chars, returns immediately without Enter.
    For other input (like numbers), requires Enter.

    Args:
        prompt: The prompt to display
        valid_chars: Characters that trigger immediate return (e.g., "qsb")

    Returns:
        User's choice as string
    """
    import sys
    import select

    print(prompt, end='', flush=True)

    if not sys.stdin.isatty():
        return input().strip()

    try:
        import tty
        import termios

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)

        try:
            tty.setraw(fd)

            while True:
                ch = sys.stdin.read(1)

                # Handle Ctrl+C
                if ch == '\x03':
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    print()
                    raise KeyboardInterrupt

                # Handle escape sequences (arrows, function keys, etc.)
                if ch == '\x1b':
                    # Consume the rest of the escape sequence
                    # Check if more chars are available
                    if select.select([sys.stdin], [], [], 0.1)[0]:
                        # Read and discard escape sequence chars
                        while select.select([sys.stdin], [], [], 0.01)[0]:
                            sys.stdin.read(1)
                    continue  # Ignore escape sequences, wait for next input

                # Ignore non-printable characters
                if not ch.isprintable() and ch not in '\r\n':
                    continue

                # If it's a valid single-char option, return immediately
                if ch.lower() in valid_chars.lower():
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    print(ch)  # Echo the character
                    return ch

                # Otherwise, switch back to normal mode and read the rest
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                print(ch, end='', flush=True)

                # Read remaining input until Enter
                rest = input()
                return ch + rest

        except Exception:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            raise

    except (ImportError, termios.error):
        return input().strip()


# ============================================================================
# Clipboard Operations
# ============================================================================

def copy_to_clipboard(text: str) -> bool:
    """
    Copy text to system clipboard.

    Uses pbcopy on macOS, xclip or xsel on Linux.

    Args:
        text: Text to copy to clipboard

    Returns:
        True if successful, False otherwise
    """
    import platform
    import subprocess

    system = platform.system()

    try:
        if system == 'Darwin':  # macOS
            process = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
            process.communicate(text.encode('utf-8'))
            return process.returncode == 0

        elif system == 'Linux':
            # Try xclip first, then xsel
            for cmd in [['xclip', '-selection', 'clipboard'], ['xsel', '--clipboard', '--input']]:
                try:
                    process = subprocess.Popen(cmd, stdin=subprocess.PIPE)
                    process.communicate(text.encode('utf-8'))
                    if process.returncode == 0:
                        return True
                except FileNotFoundError:
                    continue
            return False

        else:
            # Windows or unsupported
            return False

    except Exception:
        return False


# ============================================================================
# Code Processing
# ============================================================================

def strip_code_fences(code: str) -> str:
    """
    Strip markdown code fences from code if present.

    Handles formats like:
        ```python
        code here
        ```
    Or just:
        ```
        code here
        ```

    Args:
        code: Code string that may be wrapped in fences

    Returns:
        Code with fences stripped, or original code if no fences
    """
    lines = code.strip().split('\n')

    if len(lines) < 2:
        return code.strip()

    # Check if first line is a code fence
    first_line = lines[0].strip()
    if first_line.startswith('```'):
        # Check if last line is closing fence
        last_line = lines[-1].strip()
        if last_line == '```':
            # Strip first and last lines
            return '\n'.join(lines[1:-1])

    return code.strip()


# ============================================================================
# Frontmatter Operations
# ============================================================================

def parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """
    Parse YAML frontmatter from markdown content.

    Args:
        content: Full markdown file content with frontmatter

    Returns:
        Tuple of (metadata_dict, code_body)

    Raises:
        ValueError: If frontmatter is malformed or missing
    """
    if not content.strip().startswith('---'):
        raise ValueError("Content does not start with frontmatter delimiter")

    # Split on frontmatter delimiters
    parts = content.split('---', 2)
    if len(parts) < 3:
        raise ValueError("Malformed frontmatter: missing closing delimiter")

    frontmatter_text = parts[1].strip()
    code_body = parts[2].strip()

    # Parse YAML
    try:
        metadata = yaml.safe_load(frontmatter_text)
        if metadata is None:
            metadata = {}
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in frontmatter: {e}")

    return metadata, code_body


def serialize_frontmatter(metadata: Dict[str, Any]) -> str:
    """
    Convert metadata dictionary to YAML frontmatter string.

    Args:
        metadata: Dictionary of frontmatter fields

    Returns:
        YAML frontmatter string with delimiters
    """
    yaml_content = yaml.dump(
        metadata,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False
    )
    return f"---\n{yaml_content}---\n"


def update_frontmatter_field(content: str, field: str, value: Any) -> str:
    """
    Update a specific field in frontmatter.

    Args:
        content: Full markdown content with frontmatter
        field: Field name to update
        value: New value for field

    Returns:
        Updated markdown content
    """
    metadata, code_body = parse_frontmatter(content)
    metadata[field] = value
    return serialize_frontmatter(metadata) + "\n" + code_body


def validate_frontmatter(metadata: Dict[str, Any]) -> List[str]:
    """
    Validate frontmatter metadata against schema requirements.

    Args:
        metadata: Frontmatter metadata dictionary

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    # Required fields
    required_fields = ['title', 'language', 'description', 'created', 'last_updated']
    for field in required_fields:
        if field not in metadata or not metadata[field]:
            errors.append(f"Missing required field: {field}")

    # Language validation: any non-empty string is valid
    # This allows adding snippets in any language (java, rust, go, etc.)
    if 'language' in metadata:
        if not isinstance(metadata['language'], str) or not metadata['language'].strip():
            errors.append("Language must be a non-empty string")

    # Validate dates
    for date_field in ['created', 'last_updated']:
        if date_field in metadata:
            if not validate_date(str(metadata[date_field])):
                errors.append(f"Invalid date format for {date_field}: {metadata[date_field]}")

    # Validate tags (should be list)
    if 'tags' in metadata:
        if not isinstance(metadata['tags'], list):
            errors.append(f"Tags must be a list, got: {type(metadata['tags'])}")

    return errors


# ============================================================================
# Language Operations
# ============================================================================

SUPPORTED_LANGUAGES = [
    'sql', 'python', 'shell', 'yaml', 'toml', 'json', 'markdown', 'text'
]

LANGUAGE_DIRECTORY_MAP = {
    'sql': 'sql',
    'python': 'python',
    'shell': 'shell',
    'bash': 'shell',
    'sh': 'shell',
    'yaml': 'config',
    'yml': 'config',
    'toml': 'config',
    'json': 'config',
    'markdown': 'prompts',
    'md': 'prompts',
    'text': 'prompts',
    'txt': 'prompts',
}


def get_language_directory(language: str, auto_create: bool = True) -> str:
    """
    Map language to target directory.

    For known languages, returns the mapped directory.
    For unknown languages, returns the language name as directory and
    optionally creates it.

    Args:
        language: Language identifier
        auto_create: Whether to create directory if it doesn't exist

    Returns:
        Directory name for the language
    """
    language_lower = language.lower()

    # Check known mappings
    if language_lower in LANGUAGE_DIRECTORY_MAP:
        return LANGUAGE_DIRECTORY_MAP[language_lower]

    # For unknown languages, use language name as directory
    # This allows adding snippets in any language (java, rust, go, etc.)
    directory = language_lower

    # Auto-create directory if requested
    if auto_create:
        repo_root = get_repo_root()
        dir_path = repo_root / directory
        if not dir_path.exists():
            log_info(f"Creating new directory: {directory}/")
            dir_path.mkdir(parents=True, exist_ok=True)

    return directory


def detect_language(code: str, hint: Optional[str] = None) -> str:
    """
    Detect language from code content or hint.

    Args:
        code: Code content to analyze
        hint: Optional language hint (e.g., from filename extension)

    Returns:
        Detected language identifier
    """
    # If hint provided and valid, use it
    if hint:
        hint_lower = hint.lower().lstrip('.')
        if hint_lower in SUPPORTED_LANGUAGES:
            return hint_lower
        if hint_lower in LANGUAGE_DIRECTORY_MAP:
            # Map to canonical language name
            for lang in SUPPORTED_LANGUAGES:
                if LANGUAGE_DIRECTORY_MAP.get(lang) == LANGUAGE_DIRECTORY_MAP.get(hint_lower):
                    return lang

    # Simple heuristic-based detection
    code_lower = code.lower()

    # SQL patterns
    if any(keyword in code_lower for keyword in ['select ', 'from ', 'where ', 'insert into', 'create table', 'update ', 'delete from']):
        return 'sql'

    # Python patterns
    if any(pattern in code for pattern in ['import ', 'from ', 'def ', 'class ', 'if __name__']):
        return 'python'

    # Shell patterns
    if code.strip().startswith('#!') and ('bash' in code_lower or 'sh' in code_lower):
        return 'shell'
    if any(keyword in code for keyword in ['#!/bin/bash', '#!/bin/sh', '#!/usr/bin/env bash']):
        return 'shell'

    # YAML patterns
    if re.match(r'^[\w-]+:\s*$', code.strip().split('\n')[0], re.MULTILINE):
        return 'yaml'

    # JSON patterns
    if code.strip().startswith('{') or code.strip().startswith('['):
        return 'json'

    # Default to text
    return 'text'


# ============================================================================
# File Operations
# ============================================================================

def slugify(text: str) -> str:
    """
    Convert text to filesystem-safe slug.

    Args:
        text: Text to slugify

    Returns:
        Slugified text (lowercase, hyphens, alphanumeric only)
    """
    # Convert to lowercase
    slug = text.lower()

    # Replace spaces and underscores with hyphens
    slug = re.sub(r'[\s_]+', '-', slug)

    # Remove non-alphanumeric characters (except hyphens)
    slug = re.sub(r'[^a-z0-9-]', '', slug)

    # Remove multiple consecutive hyphens
    slug = re.sub(r'-+', '-', slug)

    # Strip leading/trailing hyphens
    slug = slug.strip('-')

    return slug


def get_repo_root() -> Path:
    """
    Get repository root from script location.

    Returns:
        Path to repository root
    """
    # Scripts are in .scripts/, so parent is repo root
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    return repo_root


def find_snippet_files(directory: Path, pattern: str = "*.md") -> List[Path]:
    """
    Find snippet files matching pattern.

    Args:
        directory: Directory to search
        pattern: Glob pattern for matching files

    Returns:
        List of matching file paths (sorted by modification time, newest first)
    """
    files = list(directory.rglob(pattern))

    # Sort by modification time (newest first)
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

    return files


# ============================================================================
# Git Operations
# ============================================================================

def git_add(file_path: Path) -> bool:
    """
    Stage file for commit.

    Args:
        file_path: Path to file to stage

    Returns:
        True if successful, False otherwise
    """
    try:
        subprocess.run(
            ['git', 'add', str(file_path)],
            check=True,
            capture_output=True,
            text=True
        )
        return True
    except subprocess.CalledProcessError as e:
        log_error(f"Failed to git add: {e.stderr}")
        return False


def git_commit(message: str) -> bool:
    """
    Create git commit with message.

    Args:
        message: Commit message

    Returns:
        True if successful, False otherwise
    """
    try:
        # Add co-author
        full_message = f"{message}\n\nCo-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

        subprocess.run(
            ['git', 'commit', '-m', full_message],
            check=True,
            capture_output=True,
            text=True
        )
        return True
    except subprocess.CalledProcessError as e:
        log_error(f"Failed to commit: {e.stderr}")
        return False


def git_status_clean() -> bool:
    """
    Check if git working tree is clean.

    Returns:
        True if clean, False if there are uncommitted changes
    """
    try:
        result = subprocess.run(
            ['git', 'status', '--porcelain'],
            check=True,
            capture_output=True,
            text=True
        )
        return len(result.stdout.strip()) == 0
    except subprocess.CalledProcessError:
        return False


# ============================================================================
# Date Operations
# ============================================================================

def get_today() -> str:
    """
    Get today's date in YYYY-MM-DD format.

    Returns:
        Today's date string
    """
    return datetime.now().strftime('%Y-%m-%d')


def validate_date(date_str: str) -> bool:
    """
    Validate date string is in YYYY-MM-DD format.

    Args:
        date_str: Date string to validate

    Returns:
        True if valid, False otherwise
    """
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
        return True
    except ValueError:
        return False


# ============================================================================
# UUID Operations
# ============================================================================

def generate_uuid() -> str:
    """
    Generate a full UUID4 string for snippet identification.

    Returns:
        36-character UUID string (e.g., '550e8400-e29b-41d4-a716-446655440000')
    """
    return str(uuid.uuid4())


def find_snippet_by_id(snippet_id: str) -> Optional[Path]:
    """
    Find a snippet file by its UUID.

    Args:
        snippet_id: Full UUID string to search for

    Returns:
        Path to the snippet file if found, None otherwise
    """
    repo_root = get_repo_root()
    all_files = find_snippet_files(repo_root, "*.md")

    # Filter out non-snippet files
    excluded_files = ['README.md', 'CLAUDE.md', 'TODO.md']
    all_files = [f for f in all_files if f.name not in excluded_files]

    for file_path in all_files:
        try:
            content = file_path.read_text(encoding='utf-8')
            metadata, _ = parse_frontmatter(content)
            if metadata.get('id') == snippet_id:
                return file_path
        except Exception:
            continue

    return None


def get_all_snippet_ids() -> List[Dict[str, Any]]:
    """
    Get all snippet IDs with their metadata.

    Returns:
        List of dicts with 'id', 'title', 'file_path', 'relative_path'
    """
    repo_root = get_repo_root()
    all_files = find_snippet_files(repo_root, "*.md")

    # Filter out non-snippet files
    excluded_files = ['README.md', 'CLAUDE.md', 'TODO.md']
    all_files = [f for f in all_files if f.name not in excluded_files]

    results = []
    for file_path in all_files:
        try:
            content = file_path.read_text(encoding='utf-8')
            metadata, _ = parse_frontmatter(content)
            snippet_id = metadata.get('id')
            if snippet_id:
                results.append({
                    'id': snippet_id,
                    'title': metadata.get('title', 'Untitled'),
                    'language': metadata.get('language', 'unknown'),
                    'file_path': str(file_path),
                    'relative_path': str(file_path.relative_to(repo_root))
                })
        except Exception:
            continue

    return results


# ============================================================================
# Tag Operations
# ============================================================================

def normalize_tag(tag: str) -> str:
    """
    Normalize tag to lowercase-hyphenated format.

    Args:
        tag: Tag to normalize

    Returns:
        Normalized tag
    """
    return slugify(tag)


def suggest_tags(code: str, language: str) -> List[str]:
    """
    Auto-suggest tags based on code content and language.

    Args:
        code: Code content to analyze
        language: Programming language

    Returns:
        List of suggested tags
    """
    tags = [language]  # Always include language

    code_lower = code.lower()

    if language == 'python':
        # Extract common imports
        if 'import requests' in code or 'from requests' in code:
            tags.append('requests')
        if 'import pandas' in code or 'from pandas' in code:
            tags.append('pandas')
        if 'import flask' in code or 'from flask' in code:
            tags.append('flask')
        if 'import django' in code or 'from django' in code:
            tags.append('django')
        if 'import asyncio' in code or 'async def' in code:
            tags.append('async')
        if '@' in code and 'def ' in code:  # Decorators
            tags.append('decorators')

    elif language == 'sql':
        # Detect SQL patterns
        if 'select ' in code_lower:
            tags.append('query')
        if 'create table' in code_lower or 'alter table' in code_lower:
            tags.append('ddl')
        if 'insert into' in code_lower or 'update ' in code_lower or 'delete from' in code_lower:
            tags.append('dml')
        if '{{' in code and 'config(' in code_lower:
            tags.append('dbt')
        if 'incremental' in code_lower:
            tags.append('incremental')
        if 'join ' in code_lower:
            tags.append('join')

    elif language == 'shell':
        # Detect common shell commands
        if 'docker' in code_lower:
            tags.append('docker')
        if 'git ' in code_lower:
            tags.append('git')
        if 'psql' in code_lower or 'pg_' in code_lower:
            tags.append('postgresql')
        if 'curl' in code_lower or 'wget' in code_lower:
            tags.append('http')
        if 'ssh' in code_lower:
            tags.append('ssh')

    return tags


# ============================================================================
# Snippet File Operations
# ============================================================================

def get_recent_snippets(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get most recently modified snippets.

    Args:
        limit: Maximum number of snippets to return

    Returns:
        List of snippet info dictionaries with metadata and file info
    """
    repo_root = get_repo_root()
    all_files = find_snippet_files(repo_root, "*.md")

    # Filter out non-snippet files
    excluded_files = ['README.md', 'CLAUDE.md', 'TODO.md']
    all_files = [f for f in all_files if f.name not in excluded_files]

    results = []
    for file_path in all_files[:limit]:
        try:
            content = file_path.read_text(encoding='utf-8')
            metadata, code_body = parse_frontmatter(content)

            # Get modification time
            mtime = datetime.fromtimestamp(file_path.stat().st_mtime)

            results.append({
                'file_path': file_path,
                'relative_path': file_path.relative_to(repo_root),
                'metadata': metadata,
                'mtime': mtime,
                'mtime_str': mtime.strftime('%Y-%m-%d'),
                'preview': code_body[:100].strip().replace('\n', ' ')
            })
        except Exception:
            continue

    return results


def delete_snippet(file_path: Path, commit: bool = True) -> Dict[str, Any]:
    """
    Delete snippet file with git rm.

    Args:
        file_path: Path to snippet file
        commit: Whether to auto-commit the deletion

    Returns:
        Result dictionary with status
    """
    if not file_path.exists():
        return {
            'status': 'error',
            'error_type': 'file_not_found',
            'message': f'File not found: {file_path}'
        }

    # Get file info before deletion
    repo_root = get_repo_root()
    relative_path = file_path.relative_to(repo_root)
    directory = file_path.parent.name
    filename = file_path.name

    try:
        # Use git rm to remove file
        result = subprocess.run(
            ['git', 'rm', str(file_path)],
            capture_output=True,
            text=True,
            check=True
        )
    except subprocess.CalledProcessError as e:
        # If git rm fails, try regular delete (file may not be tracked)
        try:
            file_path.unlink()
            log_warn("File deleted (was not tracked by git)")
            return {
                'status': 'success',
                'file_path': str(file_path),
                'relative_path': str(relative_path),
                'committed': False,
                'message': 'File deleted (was not tracked by git)'
            }
        except Exception as e2:
            return {
                'status': 'error',
                'error_type': 'delete_error',
                'message': f'Failed to delete: {e2}'
            }

    # Commit if requested
    committed = False
    commit_hash = None
    if commit:
        commit_msg = f"chore({directory}): delete {filename.replace('.md', '')}"
        if git_commit(commit_msg):
            committed = True
            # Get commit hash
            try:
                result = subprocess.run(
                    ['git', 'rev-parse', '--short', 'HEAD'],
                    capture_output=True,
                    text=True,
                    check=True
                )
                commit_hash = result.stdout.strip()
            except subprocess.CalledProcessError:
                pass

    return {
        'status': 'success',
        'file_path': str(file_path),
        'relative_path': str(relative_path),
        'committed': committed,
        'commit_hash': commit_hash
    }


def open_in_finder(file_path: Path) -> bool:
    """
    Open file location in system file manager.

    Uses 'open -R' on macOS to reveal file in Finder,
    xdg-open on Linux to open parent directory.

    Args:
        file_path: Path to file

    Returns:
        True if successful, False otherwise
    """
    import platform

    system = platform.system()

    try:
        if system == 'Darwin':  # macOS
            subprocess.run(['open', '-R', str(file_path)], check=True)
            return True
        elif system == 'Linux':
            subprocess.run(['xdg-open', str(file_path.parent)], check=True)
            return True
        else:
            log_warn(f"Unsupported platform: {system}")
            return False
    except subprocess.CalledProcessError as e:
        log_error(f"Failed to open file manager: {e}")
        return False
    except FileNotFoundError:
        log_error("File manager command not found")
        return False


def duplicate_snippet(source_path: Path, new_title: str) -> Dict[str, Any]:
    """
    Duplicate snippet as template with new title.

    Args:
        source_path: Path to source snippet file
        new_title: Title for the new snippet

    Returns:
        Result dictionary with new file path
    """
    if not source_path.exists():
        return {
            'status': 'error',
            'error_type': 'file_not_found',
            'message': f'Source file not found: {source_path}'
        }

    try:
        content = source_path.read_text(encoding='utf-8')
        metadata, code_body = parse_frontmatter(content)
    except Exception as e:
        return {
            'status': 'error',
            'error_type': 'parse_error',
            'message': f'Failed to parse source: {e}'
        }

    # Update metadata for new file
    today = get_today()
    metadata['title'] = new_title
    metadata['created'] = today
    metadata['last_updated'] = today

    # Generate new filename from title
    new_filename = slugify(new_title) + '.md'
    new_path = source_path.parent / new_filename

    # Check if file already exists
    if new_path.exists():
        return {
            'status': 'error',
            'error_type': 'file_exists',
            'message': f'File already exists: {new_path}'
        }

    # Write new file
    try:
        new_content = serialize_frontmatter(metadata) + "\n" + code_body
        new_path.write_text(new_content, encoding='utf-8')
    except Exception as e:
        return {
            'status': 'error',
            'error_type': 'write_error',
            'message': f'Failed to write file: {e}'
        }

    # Git add and commit
    committed = False
    commit_hash = None
    if git_add(new_path):
        commit_msg = f"feat({source_path.parent.name}): duplicate {source_path.stem} as {new_path.stem}"
        if git_commit(commit_msg):
            committed = True
            try:
                result = subprocess.run(
                    ['git', 'rev-parse', '--short', 'HEAD'],
                    capture_output=True,
                    text=True,
                    check=True
                )
                commit_hash = result.stdout.strip()
            except subprocess.CalledProcessError:
                pass

    repo_root = get_repo_root()
    return {
        'status': 'success',
        'file_path': str(new_path),
        'relative_path': str(new_path.relative_to(repo_root)),
        'filename': new_filename,
        'directory': source_path.parent.name,
        'committed': committed,
        'commit_hash': commit_hash
    }


# ============================================================================
# Tag Management Operations
# ============================================================================

def get_all_tags() -> Dict[str, int]:
    """
    Get all tags with usage counts across all snippets.

    Returns:
        Dictionary mapping tag names to count of snippets using them
    """
    repo_root = get_repo_root()
    all_files = find_snippet_files(repo_root, "*.md")

    # Filter out non-snippet files
    excluded_files = ['README.md', 'CLAUDE.md', 'TODO.md']
    all_files = [f for f in all_files if f.name not in excluded_files]

    tag_counts: Dict[str, int] = {}

    for file_path in all_files:
        try:
            content = file_path.read_text(encoding='utf-8')
            metadata, _ = parse_frontmatter(content)
            tags = metadata.get('tags', [])
            if isinstance(tags, list):
                for tag in tags:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
        except Exception:
            continue

    return tag_counts


def rename_tag(old_tag: str, new_tag: str) -> Dict[str, Any]:
    """
    Rename tag across all snippets.

    Args:
        old_tag: Tag to rename
        new_tag: New tag name

    Returns:
        Result dictionary with list of modified files
    """
    repo_root = get_repo_root()
    all_files = find_snippet_files(repo_root, "*.md")

    # Filter out non-snippet files
    excluded_files = ['README.md', 'CLAUDE.md', 'TODO.md']
    all_files = [f for f in all_files if f.name not in excluded_files]

    modified_files = []
    old_tag_normalized = normalize_tag(old_tag)
    new_tag_normalized = normalize_tag(new_tag)

    for file_path in all_files:
        try:
            content = file_path.read_text(encoding='utf-8')
            metadata, code_body = parse_frontmatter(content)
            tags = metadata.get('tags', [])

            if old_tag_normalized in tags:
                # Replace old tag with new tag
                tags = [new_tag_normalized if t == old_tag_normalized else t for t in tags]
                # Remove duplicates while preserving order
                seen = set()
                tags = [t for t in tags if not (t in seen or seen.add(t))]

                metadata['tags'] = tags
                metadata['last_updated'] = get_today()

                # Write updated content
                updated_content = serialize_frontmatter(metadata) + "\n" + code_body
                file_path.write_text(updated_content, encoding='utf-8')

                git_add(file_path)
                modified_files.append(str(file_path.relative_to(repo_root)))
        except Exception:
            continue

    # Single commit for all changes
    committed = False
    if modified_files:
        commit_msg = f"chore: rename tag '{old_tag}' to '{new_tag}' ({len(modified_files)} files)"
        committed = git_commit(commit_msg)

    return {
        'status': 'success',
        'old_tag': old_tag_normalized,
        'new_tag': new_tag_normalized,
        'modified_files': modified_files,
        'count': len(modified_files),
        'committed': committed
    }


def merge_tags(tags_to_merge: List[str], target_tag: str) -> Dict[str, Any]:
    """
    Merge multiple tags into one target tag.

    Args:
        tags_to_merge: List of tags to merge (will be replaced)
        target_tag: Tag to merge into

    Returns:
        Result dictionary with list of modified files
    """
    repo_root = get_repo_root()
    all_files = find_snippet_files(repo_root, "*.md")

    # Filter out non-snippet files
    excluded_files = ['README.md', 'CLAUDE.md', 'TODO.md']
    all_files = [f for f in all_files if f.name not in excluded_files]

    modified_files = []
    tags_to_merge_normalized = {normalize_tag(t) for t in tags_to_merge}
    target_tag_normalized = normalize_tag(target_tag)

    for file_path in all_files:
        try:
            content = file_path.read_text(encoding='utf-8')
            metadata, code_body = parse_frontmatter(content)
            tags = metadata.get('tags', [])

            # Check if file has any of the tags to merge
            has_merge_tags = any(t in tags_to_merge_normalized for t in tags)

            if has_merge_tags:
                # Remove tags to merge and add target tag
                new_tags = [t for t in tags if t not in tags_to_merge_normalized]
                if target_tag_normalized not in new_tags:
                    new_tags.append(target_tag_normalized)

                metadata['tags'] = new_tags
                metadata['last_updated'] = get_today()

                # Write updated content
                updated_content = serialize_frontmatter(metadata) + "\n" + code_body
                file_path.write_text(updated_content, encoding='utf-8')

                git_add(file_path)
                modified_files.append(str(file_path.relative_to(repo_root)))
        except Exception:
            continue

    # Single commit for all changes
    committed = False
    if modified_files:
        merge_list = ', '.join(tags_to_merge)
        commit_msg = f"chore: merge tags [{merge_list}] into '{target_tag}' ({len(modified_files)} files)"
        committed = git_commit(commit_msg)

    return {
        'status': 'success',
        'merged_tags': list(tags_to_merge_normalized),
        'target_tag': target_tag_normalized,
        'modified_files': modified_files,
        'count': len(modified_files),
        'committed': committed
    }


def remove_tag(tag: str) -> Dict[str, Any]:
    """
    Remove tag from all snippets.

    Args:
        tag: Tag to remove

    Returns:
        Result dictionary with list of modified files
    """
    repo_root = get_repo_root()
    all_files = find_snippet_files(repo_root, "*.md")

    # Filter out non-snippet files
    excluded_files = ['README.md', 'CLAUDE.md', 'TODO.md']
    all_files = [f for f in all_files if f.name not in excluded_files]

    modified_files = []
    tag_normalized = normalize_tag(tag)

    for file_path in all_files:
        try:
            content = file_path.read_text(encoding='utf-8')
            metadata, code_body = parse_frontmatter(content)
            tags = metadata.get('tags', [])

            if tag_normalized in tags:
                # Remove tag
                tags = [t for t in tags if t != tag_normalized]

                metadata['tags'] = tags
                metadata['last_updated'] = get_today()

                # Write updated content
                updated_content = serialize_frontmatter(metadata) + "\n" + code_body
                file_path.write_text(updated_content, encoding='utf-8')

                git_add(file_path)
                modified_files.append(str(file_path.relative_to(repo_root)))
        except Exception:
            continue

    # Single commit for all changes
    committed = False
    if modified_files:
        commit_msg = f"chore: remove tag '{tag}' ({len(modified_files)} files)"
        committed = git_commit(commit_msg)

    return {
        'status': 'success',
        'removed_tag': tag_normalized,
        'modified_files': modified_files,
        'count': len(modified_files),
        'committed': committed
    }
