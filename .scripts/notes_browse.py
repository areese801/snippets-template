"""
Interactive Obsidian notes browser using fzf.

Fuzzy-search and preview notes from Obsidian vaults interactively.
Delegates to fzf for fuzzy matching. Supports markdown rendering
in preview and stdout via glow, bat, or plain cat.

Modes:
  - Browse all notes:  notes_browse.py
  - Search then browse: notes_browse.py search <query>
"""

import argparse
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent))

from common import Colors, copy_to_clipboard, log_error, log_success, log_warn
from notes import (
    _open_note_in_obsidian,
    build_obsidian_uri,
    cmd_search,
    discover_vaults,
    filter_ignored_paths,
    get_vault_ignore_filters,
)


def _discover_vaults_from_config() -> List[dict]:
    """
    Read vault paths directly from Obsidian's config file on disk.
    Fallback when the Obsidian CLI is unavailable or broken.

    On macOS: ~/Library/Application Support/obsidian/obsidian.json
    """
    if platform.system() == "Darwin":
        config_path = Path.home() / "Library" / "Application Support" / "obsidian" / "obsidian.json"
    else:
        # Linux: ~/.config/obsidian/obsidian.json
        config_path = Path.home() / ".config" / "obsidian" / "obsidian.json"

    if not config_path.exists():
        return []

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, IOError):
        return []

    vaults = []
    for vault_id, vault_info in config.get("vaults", {}).items():
        vault_path = vault_info.get("path", "")
        if vault_path and Path(vault_path).is_dir():
            # Derive vault name from directory name
            vaults.append({"name": Path(vault_path).name, "path": vault_path})

    return vaults


def _discover_vaults_with_fallback() -> List[dict]:
    """
    Try Obsidian CLI first, fall back to reading config file from disk.
    Warns the user when falling back.
    """
    try:
        vaults = discover_vaults()
        if vaults:
            return vaults
    except RuntimeError:
        pass

    # CLI failed — try config file fallback
    vaults = _discover_vaults_from_config()
    if vaults:
        log_warn(
            "Obsidian CLI unavailable. Reading vault paths from config file.\n"
            "  To fix: update Obsidian from https://obsidian.md/download\n"
            "  Note: 'notes search' requires the CLI. Browse mode works without it."
        )
    return vaults


def _detect_md_renderer() -> List[str]:
    """
    Return a command prefix for rendering markdown.
    Tries glow, then bat, then falls back to cat.
    Uses full paths so fzf preview subshells can find them.
    """
    mdcat_path = shutil.which("mdcat")
    if mdcat_path:
        return [mdcat_path]
    bat_path = shutil.which("bat")
    if bat_path:
        return [bat_path, "--style=plain", "--color=always", "--paging=never", "--language=md"]
    return ["cat"]


def gather_vault_notes(
    vault_filter: Optional[str] = None,
) -> List[dict]:
    """
    Walk all vaults and collect .md files, respecting ignore filters.

    Returns list of {'vault': str, 'path': str, 'title': str, 'relative': str}
    where 'path' is the absolute path and 'relative' is the vault-relative path.
    """
    vaults = _discover_vaults_with_fallback()
    if not vaults:
        return []

    if vault_filter:
        vaults = [v for v in vaults if v["name"] == vault_filter]
        if not vaults:
            return []

    results = []
    for vault in vaults:
        vault_path = Path(vault["path"])
        if not vault_path.is_dir():
            continue
        ignore_filters = get_vault_ignore_filters(vault["path"])

        md_files = sorted(vault_path.rglob("*.md"))
        for md_file in md_files:
            # Skip hidden directories (like .obsidian, .trash)
            parts = md_file.relative_to(vault_path).parts
            if any(p.startswith(".") for p in parts):
                continue

            relative = str(md_file.relative_to(vault_path))

            # Apply ignore filters
            if filter_ignored_paths([relative], ignore_filters) == []:
                continue

            title = md_file.stem
            results.append({
                "vault": vault["name"],
                "path": str(md_file),
                "title": title,
                "relative": relative,
            })

    return results


def search_to_notes(
    query: str,
    vault_filter: Optional[str] = None,
) -> List[dict]:
    """
    Run Obsidian CLI search and convert results to the notes list format
    used by the fzf browser.

    Returns list of {'vault': str, 'path': str, 'title': str, 'relative': str}
    """
    result = cmd_search(query=query, vault_filter=vault_filter)
    if result["status"] != "success" or result["count"] == 0:
        return []

    # Build vault name → path map for resolving absolute paths
    vault_map = {v["name"]: v["path"] for v in _discover_vaults_with_fallback()}

    notes = []
    for r in result["results"]:
        vault_name = r["vault"]
        file_path = r["file"]
        vault_path = vault_map.get(vault_name, "")
        abs_path = str(Path(vault_path) / file_path) if vault_path else file_path

        notes.append({
            "vault": vault_name,
            "path": abs_path,
            "title": Path(file_path).stem,
            "relative": file_path,
        })

    return notes


def build_fzf_lines(notes: List[dict]) -> List[str]:
    """
    Build fzf input lines from gathered notes.

    Each line: /absolute/path.md\\t[vault-name] Note Title
    """
    lines = []
    for note in notes:
        display = (
            f"{Colors.CYAN}[{note['vault']}]{Colors.NC} "
            f"{Colors.BOLD}{note['title']}{Colors.NC}"
        )
        lines.append(f"{note['path']}\t{display}")
    return lines


def run_fzf(
    lines: List[str],
    query: Optional[str] = None,
) -> Optional[str]:
    """
    Run fzf with the given input lines and return the selected line.
    """
    renderer = _detect_md_renderer()
    preview_cmd = (
        'file=$(echo {} | cut -f1); '
        f'head -50 "$file" | {" ".join(renderer)}'
    )

    fzf_cmd = [
        "fzf",
        "--delimiter", "\t",
        "--with-nth", "2..",
        "--preview", preview_cmd,
        "--preview-window", "right:60%:wrap",
        "--header", "Select a note (ESC to cancel)",
        "--ansi",
        "--no-mouse",
        "--height=100%",
    ]

    if query:
        fzf_cmd.extend(["--query", query])

    result = subprocess.run(
        fzf_cmd,
        input="\n".join(lines),
        capture_output=True,
        text=True,
    )

    if result.returncode in (1, 130):
        return None

    selected = result.stdout.strip()
    return selected if selected else None


def render_markdown_to_stdout(file_path: str) -> None:
    """
    Render a markdown file to stdout using the best available renderer.
    """
    renderer = _detect_md_renderer()
    subprocess.run(renderer + [file_path])


def browse_notes(
    vault_filter: Optional[str] = None,
    query: Optional[str] = None,
    print_only: bool = False,
    search_query: Optional[str] = None,
) -> int:
    """
    Run the interactive notes browser.

    Args:
        vault_filter: Optional vault name to scope to
        query: Optional initial fzf query
        print_only: If True, render note to stdout instead of opening in Obsidian
        search_query: If set, pre-filter notes via Obsidian CLI search

    Returns:
        Exit code (0 for success or clean cancel, 1 for error)
    """
    if not shutil.which("fzf"):
        log_error("fzf is not installed.")
        print("Install with: brew install fzf", file=sys.stderr)
        return 1

    if search_query:
        try:
            notes = search_to_notes(search_query, vault_filter)
        except RuntimeError as e:
            log_error(f"Obsidian CLI search failed: {e}")
            log_warn("Falling back to browse mode with fzf filtering.")
            notes = gather_vault_notes(vault_filter)
    else:
        notes = gather_vault_notes(vault_filter)

    if not notes:
        print("No notes found.", file=sys.stderr)
        return 0

    lines = build_fzf_lines(notes)

    # For search mode, use the search query as the initial fzf query too
    fzf_query = query or search_query
    selected = run_fzf(lines, fzf_query)
    if selected is None:
        return 0

    file_path = selected.split("\t")[0]
    note_entry = next((n for n in notes if n["path"] == file_path), None)

    if print_only:
        render_markdown_to_stdout(file_path)
        return 0

    # Default action: open in Obsidian via URI
    if note_entry:
        uri = build_obsidian_uri(note_entry["vault"], note_entry["relative"])
        subprocess.run(["open", uri], capture_output=True)
        log_success(f"Opened '{note_entry['title']}' in Obsidian")
    else:
        log_error("Could not resolve note for opening.")
        return 1

    return 0


def main() -> None:
    # Manual arg parsing to support: notes singer server (no quotes needed)
    # argparse subparsers conflict with positional query words, so we route manually.
    args = sys.argv[1:]

    # Detect search subcommand
    if args and args[0] == "search":
        args = args[1:]  # strip "search"
        vault_filter = None
        print_only = False
        query_parts = []

        i = 0
        while i < len(args):
            if args[i] == "--vault" and i + 1 < len(args):
                vault_filter = args[i + 1]
                i += 2
            elif args[i] == "--print":
                print_only = True
                i += 1
            elif args[i] in ("-h", "--help"):
                print("Usage: notes search <query> [--vault <name>] [--print]")
                raise SystemExit(0)
            else:
                query_parts.append(args[i])
                i += 1

        if not query_parts:
            log_error("Search query is required.")
            print("Usage: notes search <query> [--vault <name>] [--print]", file=sys.stderr)
            raise SystemExit(1)

        exit_code = browse_notes(
            vault_filter=vault_filter,
            print_only=print_only,
            search_query=" ".join(query_parts),
        )
    else:
        # Browse mode: all remaining non-flag args are the fzf query
        vault_filter = None
        print_only = False
        query_parts = []

        i = 0
        while i < len(args):
            if args[i] == "--vault" and i + 1 < len(args):
                vault_filter = args[i + 1]
                i += 2
            elif args[i] == "--print":
                print_only = True
                i += 1
            elif args[i] in ("-h", "--help"):
                print(
                    "Usage: notes [query ...] [--vault <name>] [--print]\n"
                    "       notes search <query> [--vault <name>] [--print]"
                )
                raise SystemExit(0)
            else:
                query_parts.append(args[i])
                i += 1

        query = " ".join(query_parts) if query_parts else None
        exit_code = browse_notes(
            vault_filter=vault_filter,
            query=query,
            print_only=print_only,
        )

    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
