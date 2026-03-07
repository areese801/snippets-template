"""
Snippets Repository Manager - Unified Terminal Interface.

This TUI provides menu-driven access to all snippet operations:
- Add new snippets
- Search snippets
- Edit snippet metadata
- Audit metadata completeness
- View repository statistics

The TUI delegates to the core scripts (add.py, search.py, edit.py, audit.py)
while providing a unified, user-friendly interface.

Usage:
    ./snippets_tui.py
"""

import sys
import subprocess
import os
from pathlib import Path
from typing import Optional

# Add .scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from common import (
    log_info, log_success, log_warn, log_error,
    get_repo_root, find_all_snippets, parse_frontmatter,
    Colors, get_menu_choice, get_recent_snippets, delete_snippet,
    open_in_finder, get_all_tags, rename_tag, merge_tags, remove_tag,
    copy_to_clipboard, serialize_frontmatter
)


def clear_screen():
    """
    Clear the terminal screen.
    """
    os.system('clear' if os.name != 'nt' else 'cls')


def display_box(title: str, width: int = 60):
    """
    Display a centered title with simple ASCII borders.

    Args:
        title: The title text to display
        width: Width of the box interior (default 60)
    """
    print(f"{Colors.BOLD}{'=' * width}{Colors.NC}")
    print(f"{Colors.CYAN}{title:^{width}}{Colors.NC}")
    print(f"{Colors.BOLD}{'=' * width}{Colors.NC}")


def display_header():
    """
    Display TUI header with branding.
    """
    print()
    display_box("Snippets Repository Manager")
    print()


def get_repository_stats() -> dict:
    """
    Get repository statistics.

    Returns:
        Dictionary with stats
    """
    all_files = find_all_snippets()

    stats = {
        'total': len(all_files),
        'by_language': {}
    }

    for file_path in all_files:
        try:
            content = file_path.read_text(encoding='utf-8')
            metadata, _ = parse_frontmatter(content)
            lang = metadata.get('language', 'unknown')
            stats['by_language'][lang] = stats['by_language'].get(lang, 0) + 1
        except Exception:
            continue

    return stats


def display_stats():
    """
    Display repository statistics.
    """
    repo_root = get_repo_root()
    stats = get_repository_stats()

    print(f"{Colors.CYAN}Repository:{Colors.NC} {repo_root}")
    print(f"{Colors.CYAN}Snippets:{Colors.NC} {stats['total']} total", end='')

    if stats['by_language']:
        lang_summary = ', '.join([f"{lang}: {count}" for lang, count in sorted(stats['by_language'].items())])
        print(f" | {lang_summary}")
    else:
        print()


def display_menu():
    """
    Display main menu options.
    """
    print(f"\n{Colors.BOLD}Main Menu:{Colors.NC}")
    print("  [a] Add new snippet")
    print("  [s] Search snippets")
    print("  [e] Edit snippet")
    print("  [d] Delete snippet")
    print("  [r] Recent snippets")
    print("  [b] Browse all")
    print("  [t] Tag management")
    print("  [u] Audit metadata")
    print("  [i] Info/stats")
    print("  [q] Quit")


def run_script(script_name: str, args: list = None) -> int:
    """
    Run a CRUD script.

    Args:
        script_name: Name of script (e.g., 'add.py')
        args: Optional list of arguments

    Returns:
        Exit code
    """
    script_path = Path(__file__).parent / script_name
    cmd = [sys.executable, str(script_path)]

    if args:
        cmd.extend(args)

    try:
        result = subprocess.run(cmd)
        return result.returncode
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user")
        return 1
    except Exception as e:
        log_error(f"Failed to run {script_name}: {e}")
        return 1


def add_snippet_menu():
    """
    Add new snippet submenu.
    """
    clear_screen()
    display_header()

    display_box("Add New Snippet")
    print()

    # Run add.py in interactive mode
    exit_code = run_script('add.py')

    if exit_code == 0:
        input("\n\nPress Enter to return to main menu...")
    else:
        input("\n\nOperation failed or cancelled. Press Enter to continue...")


def search_snippets_menu():
    """
    Search snippets submenu.
    """
    clear_screen()
    display_header()

    display_box("Search Snippets")
    print()

    # Run search.py in interactive mode
    exit_code = run_script('search.py', ['--interactive'])

    input("\n\nPress Enter to return to main menu...")


def edit_snippet_menu():
    """
    Edit snippet submenu.
    """
    clear_screen()
    display_header()

    display_box("Edit Snippet")
    print()

    # Run edit.py (will show file selection menu)
    exit_code = run_script('edit.py')

    if exit_code == 0:
        input("\n\nPress Enter to return to main menu...")
    else:
        input("\n\nOperation failed or cancelled. Press Enter to continue...")


def audit_metadata_menu():
    """
    Audit metadata submenu.
    """
    clear_screen()
    display_header()

    display_box("Audit Metadata")
    print()

    print("  [s] Scan for issues (dry-run)")
    print("  [f] Fix issues interactively")
    print("  [i] Auto-migrate old schema")
    print("  [b] Back to main menu")

    choice = get_menu_choice("\nChoice: ", valid_chars="sfib").strip().lower()

    if choice == 's':
        clear_screen()
        display_header()
        print(f"{Colors.CYAN}Scanning for metadata issues...{Colors.NC}\n")
        run_script('audit.py', ['--scan'])
        input("\n\nPress Enter to return to audit menu...")
        audit_metadata_menu()  # Return to submenu

    elif choice == 'f':
        clear_screen()
        display_header()
        print(f"{Colors.CYAN}Interactive fix mode{Colors.NC}\n")
        run_script('audit.py', ['--fix-interactive'])
        input("\n\nPress Enter to return to main menu...")

    elif choice == 'i':
        clear_screen()
        display_header()
        print(f"{Colors.CYAN}Auto-migrating old schema...{Colors.NC}\n")
        run_script('audit.py', ['--migrate-schema'])
        input("\n\nPress Enter to return to main menu...")

    elif choice == 'b':
        return
    else:
        log_warn("Invalid choice")
        input("Press Enter to try again...")
        audit_metadata_menu()


def delete_snippet_menu():
    """
    Delete snippet with confirmation.
    """
    clear_screen()
    display_header()

    display_box("Delete Snippet")
    print()

    repo_root = get_repo_root()
    all_files = find_all_snippets()

    if not all_files:
        log_error("No snippet files found")
        input("\n\nPress Enter to return to main menu...")
        return

    # Search/filter prompt
    print(f"{Colors.CYAN}Total snippets:{Colors.NC} {len(all_files)}")
    search_term = input(f"\nSearch (or Enter to browse all): ").strip().lower()

    # Filter files based on search term
    if search_term:
        files = [f for f in all_files
                 if search_term in str(f.relative_to(repo_root)).lower()]
        if not files:
            log_warn(f"No snippets matching '{search_term}'")
            input("\n\nPress Enter to try again...")
            delete_snippet_menu()
            return
    else:
        files = all_files

    # Display matching files
    max_display = 20
    print(f"\n{Colors.BOLD}Select snippet to delete:{Colors.NC}\n")

    for i, file in enumerate(files[:max_display], 1):
        rel_path = file.relative_to(repo_root)
        # Get title from metadata
        try:
            content = file.read_text(encoding='utf-8')
            metadata, _ = parse_frontmatter(content)
            title = metadata.get('title', 'Untitled')
        except Exception:
            title = 'Untitled'
        print(f"  [{i}] {rel_path}")
        print(f"      {Colors.CYAN}{title}{Colors.NC}")

    if len(files) > max_display:
        print(f"\n  {Colors.YELLOW}... and {len(files) - max_display} more (refine your search){Colors.NC}")

    print(f"\n  [s] New search")
    print(f"  [b] Back to main menu")

    choice = get_menu_choice("\nChoice: ", valid_chars="sb").strip().lower()

    if choice == 'b':
        return
    elif choice == 's':
        delete_snippet_menu()
        return

    try:
        index = int(choice) - 1
        if 0 <= index < min(max_display, len(files)):
            file_path = files[index]

            # Show snippet info and confirm
            print(f"\n{Colors.BOLD}Selected:{Colors.NC} {file_path.relative_to(repo_root)}")
            try:
                content = file_path.read_text(encoding='utf-8')
                metadata, code_body = parse_frontmatter(content)
                print(f"  Title: {metadata.get('title', 'N/A')}")
                print(f"  Description: {metadata.get('description', 'N/A')}")
                print(f"  Tags: {', '.join(metadata.get('tags', []))}")
                # Show first 3 lines of code
                lines = code_body.strip().split('\n')[:3]
                print(f"\n  {Colors.CYAN}Preview:{Colors.NC}")
                for line in lines:
                    print(f"    {line[:60]}{'...' if len(line) > 60 else ''}")
            except Exception:
                pass

            # Require explicit y confirmation
            confirm = input(f"\n{Colors.RED}Delete this snippet? [y/N]:{Colors.NC} ").strip().lower()
            if confirm == 'y':
                result = delete_snippet(file_path, commit=True)
                if result['status'] == 'success':
                    log_success(f"Deleted: {result['relative_path']}")
                    if result.get('committed'):
                        log_success(f"Committed with hash: {result.get('commit_hash', 'N/A')}")
                else:
                    log_error(f"Failed to delete: {result.get('message', 'Unknown error')}")
            else:
                log_info("Deletion cancelled")
        else:
            log_error("Invalid selection")
    except ValueError:
        log_error("Invalid input")

    input("\n\nPress Enter to return to main menu...")


def recent_snippets_menu():
    """
    Display and interact with recent snippets.
    """
    clear_screen()
    display_header()

    display_box("Recent Snippets")
    print()

    # Get recent snippets
    recent = get_recent_snippets(limit=10)

    if not recent:
        print(f"{Colors.YELLOW}No snippets found{Colors.NC}")
        input("\n\nPress Enter to return to main menu...")
        return

    print(f"{Colors.BOLD}Last modified snippets:{Colors.NC}\n")

    for i, snippet in enumerate(recent, 1):
        rel_path = snippet['relative_path']
        title = snippet['metadata'].get('title', 'Untitled')
        mtime = snippet['mtime_str']
        print(f"  [{i}] {rel_path} ({mtime})")
        print(f"      {Colors.CYAN}{title}{Colors.NC}")

    print(f"\n  [b] Back to main menu")

    choice = get_menu_choice("\nSelect snippet: ", valid_chars="b").strip().lower()

    if choice == 'b':
        return

    try:
        index = int(choice) - 1
        if 0 <= index < len(recent):
            snippet = recent[index]
            recent_snippet_actions(snippet)
        else:
            log_warn("Invalid selection")
            input("\n\nPress Enter to try again...")
            recent_snippets_menu()
    except ValueError:
        log_warn("Invalid choice")
        input("\n\nPress Enter to try again...")
        recent_snippets_menu()


def recent_snippet_actions(snippet: dict):
    """
    Show actions for a selected recent snippet.
    """
    file_path = snippet['file_path']
    repo_root = get_repo_root()

    while True:
        clear_screen()
        display_header()

        metadata = snippet['metadata']
        print(f"\n{Colors.BOLD}{metadata.get('title', 'Untitled')}{Colors.NC}")
        print(f"  Path: {snippet['relative_path']}")
        print(f"  Language: {metadata.get('language', 'N/A')}")
        print(f"  Tags: {', '.join(metadata.get('tags', []))}")
        print(f"  Description: {metadata.get('description', 'N/A')}")
        print(f"  Last Modified: {snippet['mtime_str']}")

        print(f"\n{Colors.BOLD}Actions:{Colors.NC}")
        print("  [v] View full content")
        print("  [y] Copy code to clipboard")
        print("  [e] Edit snippet")
        print("  [o] Open in Finder")
        print("  [x] Delete snippet")
        print("  [b] Back to recent list")

        choice = get_menu_choice("\nChoice: ", valid_chars="vyeoxb").strip().lower()

        if choice == 'b':
            recent_snippets_menu()
            return
        elif choice == 'v':
            # View full content
            try:
                content = file_path.read_text(encoding='utf-8')
                _, code_body = parse_frontmatter(content)
                print("\n" + "=" * 60)
                print(code_body)
                print("=" * 60)
                if copy_to_clipboard(code_body.strip()):
                    log_success("Code copied to clipboard!")
            except Exception as e:
                log_error(f"Failed to read file: {e}")
            input("\n\nPress Enter to continue...")
        elif choice == 'y':
            # Copy to clipboard
            try:
                content = file_path.read_text(encoding='utf-8')
                _, code_body = parse_frontmatter(content)
                if copy_to_clipboard(code_body.strip()):
                    log_success("Code copied to clipboard!")
                else:
                    log_warn("Could not copy to clipboard")
            except Exception as e:
                log_error(f"Failed to read file: {e}")
            input("\n\nPress Enter to continue...")
        elif choice == 'e':
            # Edit snippet
            run_script('edit.py', [str(snippet['relative_path'])])
            # Refresh snippet data after edit
            try:
                content = file_path.read_text(encoding='utf-8')
                metadata, _ = parse_frontmatter(content)
                snippet['metadata'] = metadata
            except Exception:
                pass
        elif choice == 'o':
            if open_in_finder(file_path):
                log_success("Opened in Finder")
            else:
                log_warn("Could not open in Finder")
            input("\n\nPress Enter to continue...")
        elif choice == 'x':
            confirm = input(f"\n{Colors.RED}Delete this snippet? [y/N]:{Colors.NC} ").strip().lower()
            if confirm == 'y':
                result = delete_snippet(file_path, commit=True)
                if result['status'] == 'success':
                    log_success(f"Deleted: {result['relative_path']}")
                    input("\n\nPress Enter to return to recent list...")
                    recent_snippets_menu()
                    return
                else:
                    log_error(f"Failed to delete: {result.get('message', 'Unknown error')}")
            else:
                log_info("Deletion cancelled")
            input("\n\nPress Enter to continue...")


def browse_all_menu():
    """
    Browse all snippets grouped by language directory.
    """
    clear_screen()
    display_header()

    display_box("Browse All Snippets")
    print()

    repo_root = get_repo_root()
    all_files = find_all_snippets()

    if not all_files:
        print(f"{Colors.YELLOW}No snippets found{Colors.NC}")
        input("\n\nPress Enter to return to main menu...")
        return

    # Group by parent directory
    by_directory = {}
    for file_path in all_files:
        dir_name = file_path.parent.name
        if dir_name not in by_directory:
            by_directory[dir_name] = []
        by_directory[dir_name].append(file_path)

    print(f"{Colors.BOLD}All Snippets ({len(all_files)} total):{Colors.NC}\n")

    # Flatten to letter-indexed list
    letter_map = {}
    letters = 'abcdefghijklmnopqrstuvwxyz'
    letter_idx = 0

    for dir_name in sorted(by_directory.keys()):
        files = by_directory[dir_name]
        print(f"\n{Colors.CYAN}{dir_name}/ ({len(files)} snippets){Colors.NC}")

        for file_path in sorted(files, key=lambda x: x.name)[:10]:  # Max 10 per dir
            if letter_idx >= len(letters):
                break
            letter = letters[letter_idx]
            letter_map[letter] = file_path
            try:
                content = file_path.read_text(encoding='utf-8')
                metadata, _ = parse_frontmatter(content)
                title = metadata.get('title', file_path.stem)
            except Exception:
                title = file_path.stem
            print(f"  [{letter}] {file_path.name}")
            print(f"      {title}")
            letter_idx += 1

        if len(files) > 10:
            print(f"  {Colors.YELLOW}... and {len(files) - 10} more in {dir_name}/{Colors.NC}")

    print(f"\n  [b] Back to main menu")

    valid_chars = letters[:letter_idx] + 'b'
    choice = get_menu_choice("\nSelect snippet: ", valid_chars=valid_chars).strip().lower()

    if choice == 'b':
        return

    if choice in letter_map:
        file_path = letter_map[choice]
        browse_snippet_actions(file_path)


def browse_snippet_actions(file_path: Path):
    """
    Show actions for a selected snippet from browse.
    """
    repo_root = get_repo_root()

    while True:
        clear_screen()
        display_header()

        try:
            content = file_path.read_text(encoding='utf-8')
            metadata, code_body = parse_frontmatter(content)
        except Exception as e:
            log_error(f"Failed to read file: {e}")
            input("\n\nPress Enter to return...")
            browse_all_menu()
            return

        print(f"\n{Colors.BOLD}{metadata.get('title', 'Untitled')}{Colors.NC}")
        print(f"  Path: {file_path.relative_to(repo_root)}")
        print(f"  Language: {metadata.get('language', 'N/A')}")
        print(f"  Tags: {', '.join(metadata.get('tags', []))}")
        print(f"  Description: {metadata.get('description', 'N/A')}")

        print(f"\n{Colors.BOLD}Actions:{Colors.NC}")
        print("  [v] View full content")
        print("  [y] Copy code to clipboard")
        print("  [e] Edit snippet")
        print("  [o] Open in Finder")
        print("  [x] Delete snippet")
        print("  [b] Back to browse")

        choice = get_menu_choice("\nChoice: ", valid_chars="vyeoxb").strip().lower()

        if choice == 'b':
            browse_all_menu()
            return
        elif choice == 'v':
            print("\n" + "=" * 60)
            print(code_body)
            print("=" * 60)
            if copy_to_clipboard(code_body.strip()):
                log_success("Code copied to clipboard!")
            input("\n\nPress Enter to continue...")
        elif choice == 'y':
            if copy_to_clipboard(code_body.strip()):
                log_success("Code copied to clipboard!")
            else:
                log_warn("Could not copy to clipboard")
            input("\n\nPress Enter to continue...")
        elif choice == 'e':
            run_script('edit.py', [str(file_path.relative_to(repo_root))])
        elif choice == 'o':
            if open_in_finder(file_path):
                log_success("Opened in Finder")
            else:
                log_warn("Could not open in Finder")
            input("\n\nPress Enter to continue...")
        elif choice == 'x':
            confirm = input(f"\n{Colors.RED}Delete this snippet? [y/N]:{Colors.NC} ").strip().lower()
            if confirm == 'y':
                result = delete_snippet(file_path, commit=True)
                if result['status'] == 'success':
                    log_success(f"Deleted: {result['relative_path']}")
                    input("\n\nPress Enter to return to browse...")
                    browse_all_menu()
                    return
                else:
                    log_error(f"Failed to delete: {result.get('message', 'Unknown error')}")
            else:
                log_info("Deletion cancelled")
            input("\n\nPress Enter to continue...")


def tag_management_menu():
    """
    Tag management submenu.
    """
    clear_screen()
    display_header()

    display_box("Tag Management")
    print()

    # Get all tags
    all_tags = get_all_tags()

    if not all_tags:
        print(f"{Colors.YELLOW}No tags found{Colors.NC}")
        input("\n\nPress Enter to return to main menu...")
        return

    print(f"{Colors.BOLD}All Tags ({len(all_tags)} total):{Colors.NC}\n")

    # Sort by count descending
    sorted_tags = sorted(all_tags.items(), key=lambda x: x[1], reverse=True)

    for tag, count in sorted_tags[:20]:
        plural = "s" if count != 1 else ""
        print(f"  {tag}: {count} snippet{plural}")

    if len(sorted_tags) > 20:
        print(f"\n  {Colors.YELLOW}... and {len(sorted_tags) - 20} more tags{Colors.NC}")

    print(f"\n{Colors.BOLD}Actions:{Colors.NC}")
    print("  [r] Rename tag")
    print("  [m] Merge tags")
    print("  [d] Delete tag")
    print("  [b] Back to main menu")

    choice = get_menu_choice("\nChoice: ", valid_chars="rmdb").strip().lower()

    if choice == 'b':
        return
    elif choice == 'r':
        rename_tag_interactive()
    elif choice == 'm':
        merge_tags_interactive()
    elif choice == 'd':
        delete_tag_interactive()


def rename_tag_interactive():
    """
    Interactive tag rename.
    """
    print(f"\n{Colors.CYAN}Rename Tag{Colors.NC}")

    old_tag = input("Tag to rename: ").strip()
    if not old_tag:
        log_warn("No tag specified")
        input("\n\nPress Enter to continue...")
        tag_management_menu()
        return

    # Check if tag exists
    all_tags = get_all_tags()
    if old_tag not in all_tags:
        log_warn(f"Tag '{old_tag}' not found")
        input("\n\nPress Enter to continue...")
        tag_management_menu()
        return

    new_tag = input("New tag name: ").strip()
    if not new_tag:
        log_warn("No new tag specified")
        input("\n\nPress Enter to continue...")
        tag_management_menu()
        return

    count = all_tags[old_tag]
    confirm = input(f"\nRename '{old_tag}' to '{new_tag}' in {count} file(s)? [y/N]: ").strip().lower()

    if confirm == 'y':
        result = rename_tag(old_tag, new_tag)
        if result['status'] == 'success':
            log_success(f"Renamed '{old_tag}' to '{new_tag}' in {result['count']} file(s)")
            if result.get('committed'):
                log_success("Changes committed to git")
        else:
            log_error(f"Failed: {result.get('message', 'Unknown error')}")
    else:
        log_info("Cancelled")

    input("\n\nPress Enter to continue...")
    tag_management_menu()


def merge_tags_interactive():
    """
    Interactive tag merge.
    """
    print(f"\n{Colors.CYAN}Merge Tags{Colors.NC}")

    tags_input = input("Tags to merge (comma-separated): ").strip()
    if not tags_input:
        log_warn("No tags specified")
        input("\n\nPress Enter to continue...")
        tag_management_menu()
        return

    tags_to_merge = [t.strip() for t in tags_input.split(',') if t.strip()]
    if len(tags_to_merge) < 2:
        log_warn("Need at least 2 tags to merge")
        input("\n\nPress Enter to continue...")
        tag_management_menu()
        return

    target_tag = input("Target tag name: ").strip()
    if not target_tag:
        log_warn("No target tag specified")
        input("\n\nPress Enter to continue...")
        tag_management_menu()
        return

    # Get affected file count
    all_tags = get_all_tags()
    affected = sum(all_tags.get(t, 0) for t in tags_to_merge)

    confirm = input(f"\nMerge [{', '.join(tags_to_merge)}] into '{target_tag}'? (affects ~{affected} files) [y/N]: ").strip().lower()

    if confirm == 'y':
        result = merge_tags(tags_to_merge, target_tag)
        if result['status'] == 'success':
            log_success(f"Merged tags into '{target_tag}' in {result['count']} file(s)")
            if result.get('committed'):
                log_success("Changes committed to git")
        else:
            log_error(f"Failed: {result.get('message', 'Unknown error')}")
    else:
        log_info("Cancelled")

    input("\n\nPress Enter to continue...")
    tag_management_menu()


def delete_tag_interactive():
    """
    Interactive tag deletion.
    """
    print(f"\n{Colors.CYAN}Delete Tag{Colors.NC}")

    tag = input("Tag to delete: ").strip()
    if not tag:
        log_warn("No tag specified")
        input("\n\nPress Enter to continue...")
        tag_management_menu()
        return

    # Check if tag exists
    all_tags = get_all_tags()
    if tag not in all_tags:
        log_warn(f"Tag '{tag}' not found")
        input("\n\nPress Enter to continue...")
        tag_management_menu()
        return

    count = all_tags[tag]
    confirm = input(f"\n{Colors.RED}Delete tag '{tag}' from {count} file(s)? [y/N]:{Colors.NC} ").strip().lower()

    if confirm == 'y':
        result = remove_tag(tag)
        if result['status'] == 'success':
            log_success(f"Removed tag '{tag}' from {result['count']} file(s)")
            if result.get('committed'):
                log_success("Changes committed to git")
        else:
            log_error(f"Failed: {result.get('message', 'Unknown error')}")
    else:
        log_info("Cancelled")

    input("\n\nPress Enter to continue...")
    tag_management_menu()


def info_stats_menu():
    """
    Display detailed repository statistics (renamed from repository_stats_menu).
    """
    clear_screen()
    display_header()

    display_box("Repository Statistics")
    print()

    repo_root = get_repo_root()
    stats = get_repository_stats()

    print(f"{Colors.BOLD}Repository Path:{Colors.NC}")
    print(f"  {repo_root}\n")

    print(f"{Colors.BOLD}Total Snippets:{Colors.NC} {stats['total']}\n")

    if stats['by_language']:
        print(f"{Colors.BOLD}Snippets by Language:{Colors.NC}")
        for lang, count in sorted(stats['by_language'].items(), key=lambda x: x[1], reverse=True):
            print(f"  {lang}: {count}")
    else:
        print(f"{Colors.YELLOW}No snippets found{Colors.NC}")

    # Get tag statistics
    print(f"\n{Colors.BOLD}Most Common Tags:{Colors.NC}")
    try:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).parent / 'search.py'), '--list-tags'],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            # Parse output to show top 10 tags
            lines = [line.strip() for line in result.stdout.split('\n') if ':' in line]
            for line in lines[:10]:
                print(f"  {line}")
    except Exception:
        print(f"  {Colors.YELLOW}Unable to fetch tag statistics{Colors.NC}")

    input("\n\nPress Enter to return to main menu...")


def main_menu():
    """
    Main menu loop.
    """
    while True:
        clear_screen()
        display_header()
        display_stats()
        display_menu()

        choice = get_menu_choice("\nChoice: ", valid_chars="asedrbtuiq").strip().lower()

        if choice == 'q':
            clear_screen()
            print(f"\n{Colors.GREEN}Goodbye!{Colors.NC}\n")
            break

        elif choice == 'a':
            add_snippet_menu()

        elif choice == 's':
            search_snippets_menu()

        elif choice == 'e':
            edit_snippet_menu()

        elif choice == 'd':
            delete_snippet_menu()

        elif choice == 'r':
            recent_snippets_menu()

        elif choice == 'b':
            browse_all_menu()

        elif choice == 't':
            tag_management_menu()

        elif choice == 'u':
            audit_metadata_menu()

        elif choice == 'i':
            info_stats_menu()

        else:
            log_warn("Invalid choice.")
            input("Press Enter to try again...")


def main():
    """
    Main entry point.
    """
    try:
        main_menu()
    except KeyboardInterrupt:
        clear_screen()
        print(f"\n{Colors.YELLOW}Operation cancelled by user{Colors.NC}\n")
        sys.exit(0)
    except Exception as e:
        log_error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
