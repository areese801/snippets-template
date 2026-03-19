"""
Interactive snippet browser using fzf.

Fuzzy-search and preview snippets interactively. Delegates to fzf for fuzzy
matching and uses bat (or cat) for file preview.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from common import (
    Colors,
    copy_to_clipboard,
    find_all_snippets,
    get_repo_root,
    log_error,
    log_success,
    parse_frontmatter,
)


def check_fzf() -> bool:
    """
    Check if fzf is installed.

    Returns:
        True if fzf is available on PATH, False otherwise
    """
    return shutil.which("fzf") is not None


def build_snippet_lines(
    snippets: List[Path],
    language_filter: Optional[str] = None,
    tag_filters: Optional[List[str]] = None,
) -> List[str]:
    """
    Build fzf input lines from snippet files.

    Each line is: /absolute/path.md\\t[language] title  (tag1, tag2)

    Args:
        snippets: List of snippet file paths
        language_filter: Optional language to filter by
        tag_filters: Optional list of tags to filter by (AND logic)

    Returns:
        List of formatted lines for fzf input
    """
    lines = []
    for file_path in snippets:
        try:
            content = file_path.read_text(encoding="utf-8")
            metadata, _ = parse_frontmatter(content)
        except Exception:
            continue

        title = metadata.get("title", file_path.stem)
        language = metadata.get("language", "unknown")
        tags = metadata.get("tags", [])
        if not isinstance(tags, list):
            tags = []

        # Apply pre-filters
        if language_filter and language.lower() != language_filter.lower():
            continue

        if tag_filters:
            tag_set = {t.lower() for t in tags}
            if not all(tf.lower() in tag_set for tf in tag_filters):
                continue

        # Format display line with ANSI colors
        tag_str = f"  ({', '.join(tags)})" if tags else ""
        display = (
            f"{Colors.CYAN}[{language}]{Colors.NC} "
            f"{Colors.BOLD}{title}{Colors.NC}"
            f"{Colors.YELLOW}{tag_str}{Colors.NC}"
        )

        lines.append(f"{file_path}\t{display}")

    return lines


def run_fzf(
    lines: List[str],
    query: Optional[str] = None,
) -> Optional[str]:
    """
    Run fzf with the given input lines and return the selected line.

    Args:
        lines: Input lines for fzf (path\\tdisplay)
        query: Optional initial query string

    Returns:
        The selected line (full, including path), or None if cancelled
    """
    preview_cmd = (
        'file=$(echo {} | cut -f1); '
        'if command -v bat > /dev/null 2>&1; then '
        'bat --style=header,grid --color=always --paging=never "$file"; '
        'else cat "$file"; fi'
    )

    fzf_cmd = [
        "fzf",
        "--delimiter", "\t",
        "--with-nth", "2..",
        "--preview", preview_cmd,
        "--preview-window", "right:60%:wrap",
        "--header", "Select a snippet (ESC to cancel)",
        "--ansi",
        "--no-mouse",
    ]

    if query:
        fzf_cmd.extend(["--query", query])

    result = subprocess.run(
        fzf_cmd,
        input="\n".join(lines),
        capture_output=True,
        text=True,
    )

    # Exit 130 = ESC/Ctrl-C, exit 1 = no match
    if result.returncode in (1, 130):
        return None

    selected = result.stdout.strip()
    return selected if selected else None


def browse_snippets(
    language: Optional[str] = None,
    tags: Optional[List[str]] = None,
    print_only: bool = False,
    query: Optional[str] = None,
) -> int:
    """
    Run the interactive snippet browser.

    Args:
        language: Optional language pre-filter
        tags: Optional tag pre-filters
        print_only: If True, print code to stdout instead of clipboard
        query: Optional initial fzf query

    Returns:
        Exit code (0 for success or clean cancel, 1 for error)
    """
    if not check_fzf():
        log_error("fzf is not installed.")
        print("Install with: brew install fzf", file=sys.stderr)
        return 1

    snippets = find_all_snippets()
    lines = build_snippet_lines(snippets, language, tags)

    if not lines:
        print("No snippets match your filters.", file=sys.stderr)
        return 0

    selected = run_fzf(lines, query)
    if selected is None:
        return 0

    # Extract file path (first field before tab)
    file_path = Path(selected.split("\t")[0])

    try:
        content = file_path.read_text(encoding="utf-8")
        metadata, code_body = parse_frontmatter(content)
    except Exception as e:
        log_error(f"Failed to read snippet: {e}")
        return 1

    title = metadata.get("title", file_path.stem)

    if print_only:
        print(code_body)
    else:
        if copy_to_clipboard(code_body):
            log_success(f"Copied '{title}' to clipboard")
        else:
            log_error("Failed to copy to clipboard")
            print(code_body)
            return 1

    return 0


def main() -> None:
    """
    CLI entry point for browse.py.
    """
    parser = argparse.ArgumentParser(
        description="Interactive snippet browser with fzf"
    )
    parser.add_argument(
        "--language",
        help="Pre-filter snippets by language",
    )
    parser.add_argument(
        "--tag",
        action="append",
        dest="tags",
        help="Pre-filter by tag (repeatable, AND logic)",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        dest="print_only",
        help="Print code to stdout instead of copying to clipboard",
    )
    parser.add_argument(
        "--query",
        help="Start fzf with a pre-filled query",
    )

    args = parser.parse_args()

    exit_code = browse_snippets(
        language=args.language,
        tags=args.tags,
        print_only=args.print_only,
        query=args.query,
    )
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
