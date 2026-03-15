#!/usr/bin/env python
"""
notes.py — Search and read Obsidian notes from the terminal.

Wraps the Obsidian CLI to search notes across multiple vaults,
read note contents, and list tags.

Usage:
    notes search <query>              # Search all vaults
    notes search <query> --context    # With matching lines
    notes read <name>                 # Read a note
    notes tags                        # List all tags
    notes tags --counts               # With occurrence counts
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).parent))

from common import log_info, log_success, log_warn, log_error, copy_to_clipboard, Colors

OBSIDIAN_BINARY = "obsidian"

KNOWN_STDERR_PATTERNS = [
    "Loading updated app package",
    "installer is out of date",
    "Please download the latest installer",
]


def check_obsidian_available() -> tuple[bool, str]:
    """
    Check if the obsidian binary is on PATH.
    Returns (available, message).
    """
    if shutil.which(OBSIDIAN_BINARY) is None:
        return False, (
            "Obsidian CLI not found on PATH.\n"
            "To enable it: Obsidian > Settings > General > CLI\n"
            "More info: https://help.obsidian.md/cli"
        )
    return True, ""


def run_obsidian_cmd(args: list[str], timeout: int = 30) -> str:
    """
    Run an obsidian CLI command and return stdout.
    Filters known stderr warnings. Raises on timeout or real errors.
    """
    cmd = [OBSIDIAN_BINARY] + args
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    # Filter known noise from stderr
    stderr_lines = result.stderr.strip().splitlines()
    real_errors = [
        line
        for line in stderr_lines
        if not any(pattern in line for pattern in KNOWN_STDERR_PATTERNS)
    ]

    if result.returncode != 0 and real_errors:
        raise RuntimeError("\n".join(real_errors))

    # Filter known noise from stdout too (CLI sometimes writes warnings there)
    stdout_lines = result.stdout.strip().splitlines()
    clean_stdout = "\n".join(
        line
        for line in stdout_lines
        if not any(pattern in line for pattern in KNOWN_STDERR_PATTERNS)
    )
    return clean_stdout.strip()


def discover_vaults(retries: int = 2) -> list[dict]:
    """
    Returns list of {'name': str, 'path': str} from `obsidian vaults verbose`.
    Parses TSV output. Retries on empty output since the Obsidian CLI
    can intermittently return nothing when called in quick succession.
    """
    import time

    for attempt in range(retries + 1):
        output = run_obsidian_cmd(["vaults", "verbose"])
        if output:
            break
        if attempt < retries:
            time.sleep(0.5)

    if not output:
        return []

    vaults = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            vaults.append({"name": parts[0], "path": parts[1]})
    return vaults


def get_vault_ignore_filters(vault_path: str) -> list[str]:
    """
    Reads .obsidian/app.json from vault_path, returns userIgnoreFilters list.
    Returns empty list if key is not set or file doesn't exist.

    Filters are folder path prefixes (e.g., '_PERSONAL/EVERNOTE/', '_ARCHIVE/').
    Applied via str.startswith() matching against result file paths.
    """
    app_json_path = Path(vault_path) / ".obsidian" / "app.json"
    if not app_json_path.exists():
        return []

    try:
        with open(app_json_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        return config.get("userIgnoreFilters", [])
    except (json.JSONDecodeError, IOError):
        return []


def build_obsidian_uri(vault_name: str, file_path: str) -> str:
    """
    Construct an obsidian:// URI for opening a note.
    Strips .md extension and URL-encodes vault name and file path.
    """
    # Strip .md extension
    if file_path.endswith(".md"):
        file_path = file_path[:-3]

    encoded_vault = quote(vault_name, safe="")
    encoded_file = quote(file_path, safe="/")
    return f"obsidian://open?vault={encoded_vault}&file={encoded_file}"


def filter_ignored_paths(paths: list[str], ignore_filters: list[str]) -> list[str]:
    """
    Filter out paths that start with any of the ignore filter prefixes.
    Pure function for testability.
    """
    if not ignore_filters:
        return paths
    return [
        p for p in paths if not any(p.startswith(f) for f in ignore_filters)
    ]


def _resolve_vaults(
    vault_filter: str | None = None,
) -> tuple[list[dict], dict | None]:
    """
    Discover vaults and optionally filter to a specific one.
    Returns (vaults_list, error_dict_or_none).
    """
    vaults = discover_vaults()
    if not vaults:
        return [], {
            "status": "error",
            "error_type": "no_vaults",
            "message": "No Obsidian vaults found.",
        }

    if vault_filter:
        matched = [v for v in vaults if v["name"] == vault_filter]
        if not matched:
            names = [v["name"] for v in vaults]
            return [], {
                "status": "error",
                "error_type": "vault_not_found",
                "message": f"Vault '{vault_filter}' not found. Available: {', '.join(names)}",
            }
        return matched, None

    return vaults, None


def cmd_search(
    query: str,
    vault_filter: str | None = None,
    limit: int | None = None,
    context: bool = False,
    case_sensitive: bool = False,
) -> dict:
    """
    Search notes across vaults. Returns structured result dict.
    """
    vaults, error = _resolve_vaults(vault_filter)
    if error:
        return error

    all_results = []
    for vault in vaults:
        ignore_filters = get_vault_ignore_filters(vault["path"])

        # Build CLI args
        if context:
            cmd_args = [
                "search:context",
                f"query={query}",
                f"vault={vault['name']}",
                "format=json",
            ]
        else:
            cmd_args = [
                "search",
                f"query={query}",
                f"vault={vault['name']}",
            ]

        if limit:
            cmd_args.append(f"limit={limit}")
        if case_sensitive:
            cmd_args.append("case")

        try:
            output = run_obsidian_cmd(cmd_args)
        except (RuntimeError, subprocess.TimeoutExpired):
            continue

        if not output or output == "No matches found.":
            continue

        if context:
            # Parse JSON array from search:context
            entries = json.loads(output)
            for entry in entries:
                file_path = entry["file"]
                if any(file_path.startswith(f) for f in ignore_filters):
                    continue
                all_results.append(
                    {
                        "vault": vault["name"],
                        "file": file_path,
                        "title": Path(file_path).stem,
                        "matches": entry.get("matches", []),
                        "uri": build_obsidian_uri(vault["name"], file_path),
                    }
                )
        else:
            # Parse line-per-file text output
            file_paths = output.splitlines()
            filtered = filter_ignored_paths(
                [p.strip() for p in file_paths if p.strip()], ignore_filters
            )
            for file_path in filtered:
                all_results.append(
                    {
                        "vault": vault["name"],
                        "file": file_path,
                        "title": Path(file_path).stem,
                        "uri": build_obsidian_uri(vault["name"], file_path),
                    }
                )

    vault_count = len(set(r["vault"] for r in all_results)) if all_results else 0
    return {
        "status": "success",
        "query": query,
        "vault_filter": vault_filter,
        "count": len(all_results),
        "vault_count": vault_count,
        "results": all_results,
    }


def cmd_read(
    name: str | None = None,
    path: str | None = None,
    vault_filter: str | None = None,
) -> dict:
    """
    Read a note's contents. Returns structured result dict.
    Tries specified vault first, then falls back to other vaults.
    """
    vaults = discover_vaults()
    if not vaults:
        return {
            "status": "error",
            "error_type": "no_vaults",
            "message": "No Obsidian vaults found.",
        }

    if vault_filter:
        matched = [v for v in vaults if v["name"] == vault_filter]
        if not matched:
            names = [v["name"] for v in vaults]
            return {
                "status": "error",
                "error_type": "vault_not_found",
                "message": f"Vault '{vault_filter}' not found. Available: {', '.join(names)}",
            }
        # Put the requested vault first, keep others as fallback
        others = [v for v in vaults if v["name"] != vault_filter]
        vaults = matched + others

    for vault in vaults:
        cmd_args = ["read"]
        if path:
            cmd_args.append(f"path={path}")
        elif name:
            cmd_args.append(f"file={name}")
        cmd_args.append(f"vault={vault['name']}")

        try:
            output = run_obsidian_cmd(cmd_args)
        except (RuntimeError, subprocess.TimeoutExpired):
            continue

        if not output:
            continue

        file_ref = path if path else name
        return {
            "status": "success",
            "vault": vault["name"],
            "file": file_ref,
            "title": Path(file_ref).stem if file_ref else "",
            "content": output,
            "uri": build_obsidian_uri(vault["name"], file_ref or ""),
        }

    search_name = path or name or "unknown"
    return {
        "status": "error",
        "error_type": "not_found",
        "message": f"Note '{search_name}' not found in any vault. Try: ./notes search {search_name}",
    }


def cmd_tags(
    vault_filter: str | None = None,
    sort_by: str = "name",
) -> dict:
    """
    List tags across vaults with counts. Merges across vaults.
    """
    vaults, error = _resolve_vaults(vault_filter)
    if error:
        return error

    # Aggregate: tag_name -> {"count": int, "vaults": set}
    aggregated: dict[str, dict] = {}

    for vault in vaults:
        cmd_args = [
            "tags",
            f"vault={vault['name']}",
            "format=json",
            "counts",
        ]
        try:
            output = run_obsidian_cmd(cmd_args)
        except (RuntimeError, subprocess.TimeoutExpired):
            continue

        if not output:
            continue

        entries = json.loads(output)
        for entry in entries:
            tag_name = entry["tag"].lstrip("#")
            count = int(entry["count"])
            if tag_name in aggregated:
                aggregated[tag_name]["count"] += count
                aggregated[tag_name]["vaults"].add(vault["name"])
            else:
                aggregated[tag_name] = {"count": count, "vaults": {vault["name"]}}

    # Build sorted result
    tags_list = [
        {"name": tag_name, "count": data["count"], "vaults": sorted(data["vaults"])}
        for tag_name, data in aggregated.items()
    ]

    if sort_by == "count":
        tags_list.sort(key=lambda t: (-t["count"], t["name"]))
    else:
        tags_list.sort(key=lambda t: t["name"])

    return {
        "status": "success",
        "vault_filter": vault_filter,
        "count": len(tags_list),
        "tags": tags_list,
    }


def _open_note_in_obsidian(result_entry: dict) -> None:
    """Open a note in Obsidian via the CLI using path= for reliable resolution."""
    cmd_args = [
        "open",
        f"path={result_entry['file']}",
        f"vault={result_entry['vault']}",
    ]
    try:
        run_obsidian_cmd(cmd_args)
        # Bring Obsidian to the foreground on macOS
        import platform
        if platform.system() == "Darwin":
            subprocess.run(["open", "-a", "Obsidian"], capture_output=True)
        log_success(f"Opened '{result_entry['title']}' in Obsidian.")
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        log_error(f"Failed to open note: {e}")


def _format_search_human(result: dict) -> None:
    """Format search results for human output. Prompts to open a note if interactive."""
    if result["count"] == 0:
        log_info("No notes found.")
        return

    vault_word = "vault" if result["vault_count"] == 1 else "vaults"
    print(
        f"\nFound {result['count']} note{'s' if result['count'] != 1 else ''} "
        f"across {result['vault_count']} {vault_word}:\n"
    )

    for i, r in enumerate(result["results"], 1):
        print(f"  {Colors.BOLD}{i}. {r['title']}{Colors.NC} ({r['vault']})")
        if "matches" in r:
            for m in r["matches"][:5]:  # Show up to 5 matching lines
                print(f"     Line {m['line']}: {m['text']}")
        print()

    # Prompt to open a note if interactive
    if sys.stdout.isatty():
        try:
            answer = input("Open a note? Enter number (or press Enter to skip): ").strip()
            if answer:
                idx = int(answer) - 1
                if 0 <= idx < len(result["results"]):
                    _open_note_in_obsidian(result["results"][idx])
                else:
                    log_warn(f"Invalid number. Choose 1-{result['count']}.")
        except (EOFError, KeyboardInterrupt):
            pass
        except ValueError:
            log_warn("Enter a number or press Enter to skip.")


def _format_read_human(result: dict, no_prompt: bool = False) -> None:
    """Format read results for human output."""
    # Print content to stdout
    print(result["content"])

    # Print URI to stderr so stdout is clean for piping
    print(
        f"\n{Colors.CYAN}{result['uri']}{Colors.NC}",
        file=sys.stderr,
    )

    # Prompt for clipboard if interactive
    if not no_prompt and sys.stdout.isatty():
        try:
            answer = input("\nCopy to clipboard? [y/N] ").strip().lower()
            if answer == "y":
                if copy_to_clipboard(result["content"]):
                    log_success("Copied to clipboard.")
                else:
                    log_error("Failed to copy to clipboard.")
        except (EOFError, KeyboardInterrupt):
            pass


def _format_tags_human(result: dict, show_counts: bool = False) -> None:
    """Format tags results for human output."""
    if result["count"] == 0:
        log_info("No tags found.")
        return

    vault_desc = f"vault '{result['vault_filter']}'" if result["vault_filter"] else "all vaults"
    print(f"\nTags across {vault_desc} ({result['count']} unique):\n")

    for tag in result["tags"]:
        if show_counts:
            print(f"  {tag['name']} ({tag['count']})")
        else:
            print(f"  {tag['name']}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Search and read Obsidian notes from the terminal.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  notes search postgres
  notes search API rate limiting --vault "My Vault"
  notes search postgres --context
  notes read Meeting Notes
  notes read --path "folder/note.md" --vault "My Vault"
  notes tags --counts --sort count
        """,
    )

    subparsers = parser.add_subparsers(dest="subcommand", help="Available commands")

    # --- search ---
    search_parser = subparsers.add_parser("search", help="Search notes across vaults")
    search_parser.add_argument(
        "query_parts", nargs="*", help="Search query (multi-word, no quotes needed)"
    )
    search_parser.add_argument("--vault", help="Target a specific vault by name")
    search_parser.add_argument(
        "--limit", type=int, help="Max results per vault"
    )
    search_parser.add_argument(
        "--context",
        action="store_true",
        help="Include matching lines with line numbers",
    )
    search_parser.add_argument(
        "--case", action="store_true", help="Case-sensitive search"
    )
    search_parser.add_argument(
        "--format",
        choices=["human", "json"],
        default="human",
        dest="output_format",
        help="Output format (default: human)",
    )

    # --- read ---
    read_parser = subparsers.add_parser("read", help="Read a note's contents")
    read_parser.add_argument(
        "name_parts", nargs="*", help="Note name (multi-word, no quotes needed)"
    )
    read_parser.add_argument("--path", help="Exact file path instead of name")
    read_parser.add_argument("--vault", help="Target a specific vault by name")
    read_parser.add_argument(
        "--no-prompt",
        action="store_true",
        help="Skip the clipboard prompt",
    )
    read_parser.add_argument(
        "--format",
        choices=["human", "json"],
        default="human",
        dest="output_format",
        help="Output format (default: human)",
    )

    # --- tags ---
    tags_parser = subparsers.add_parser("tags", help="List tags across vaults")
    tags_parser.add_argument("--vault", help="Target a specific vault by name")
    tags_parser.add_argument(
        "--counts", action="store_true", help="Show occurrence counts"
    )
    tags_parser.add_argument(
        "--sort",
        choices=["name", "count"],
        default="name",
        dest="sort_by",
        help="Sort order (default: name)",
    )
    tags_parser.add_argument(
        "--format",
        choices=["human", "json"],
        default="human",
        dest="output_format",
        help="Output format (default: human)",
    )

    args = parser.parse_args()

    if not args.subcommand:
        parser.print_help()
        sys.exit(2)

    # Check if --format json was requested (for error formatting)
    output_format = getattr(args, "output_format", "human")

    # Check obsidian availability
    available, msg = check_obsidian_available()
    if not available:
        if output_format == "json":
            print(
                json.dumps(
                    {
                        "status": "error",
                        "error_type": "not_installed",
                        "message": msg,
                    },
                    indent=2,
                )
            )
        else:
            log_error(msg)
        sys.exit(1)

    # Dispatch subcommands
    if args.subcommand == "search":
        query = " ".join(args.query_parts)
        if not query:
            log_error("Search query is required.")
            sys.exit(1)

        result = cmd_search(
            query=query,
            vault_filter=args.vault,
            limit=args.limit,
            context=args.context,
            case_sensitive=args.case,
        )

        if output_format == "json":
            print(json.dumps(result, indent=2))
        else:
            if result["status"] == "error":
                log_error(result["message"])
            else:
                _format_search_human(result)

    elif args.subcommand == "read":
        name = " ".join(args.name_parts) if args.name_parts else None
        if not name and not args.path:
            log_error("Note name or --path is required.")
            sys.exit(1)

        result = cmd_read(
            name=name,
            path=args.path,
            vault_filter=args.vault,
        )

        if output_format == "json":
            print(json.dumps(result, indent=2))
        else:
            if result["status"] == "error":
                log_error(result["message"])
            else:
                _format_read_human(result, no_prompt=args.no_prompt)

    elif args.subcommand == "tags":
        result = cmd_tags(
            vault_filter=args.vault,
            sort_by=args.sort_by,
        )

        if output_format == "json":
            print(json.dumps(result, indent=2))
        else:
            if result["status"] == "error":
                log_error(result["message"])
            else:
                _format_tags_human(result, show_counts=args.counts)

    exit_code = 0 if result["status"] == "success" else 1
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
