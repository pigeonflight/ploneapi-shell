#!/usr/bin/env python3
"""
Plone API Shell - Interactive explorer for Plone REST API sites.

Most modern Plone 6.x sites expose their REST API at siteroot/++api++
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
import posixpath
import shlex
from urllib.parse import urljoin

import typer
from rich import box
from rich.console import Console
from rich.json import JSON
from rich.table import Table

from prompt_toolkit import prompt
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory

from ploneapi_shell import api, __version__

CONFIG_FILE = api.CONFIG_FILE
HISTORY_FILE = CONFIG_FILE.parent / "history.txt"
VERSION_MESSAGE = f"[dim]ploneapi-shell v{__version__}[/dim]"

APP = typer.Typer(
    help="Interactive shell and CLI for exploring Plone REST API sites.",
    invoke_without_command=True,
)
CONSOLE = Console()
DEFAULT_BASE = api.DEFAULT_BASE


class CliError(typer.Exit):
    """Wrap Typer exit with message."""

    def __init__(self, message: str, code: int = 1) -> None:
        CONSOLE.print(f"[red]Error:[/red] {message}")
        super().__init__(code)


def parse_key_values(entries: Iterable[str]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for raw in entries:
        if ":" not in raw:
            raise CliError(f"Invalid key/value pair '{raw}'. Use key:value syntax.")
        key, value = raw.split(":", 1)
        result[key.strip()] = value.strip()
    return result


# Alias API functions for CLI use
def load_config() -> Optional[Dict[str, Any]]:
    return api.load_config()


def save_config(data: Dict[str, Any]) -> None:
    api.save_config(data)


def delete_config() -> None:
    api.delete_config()


def get_base_url(provided: Optional[str] = None) -> str:
    return api.get_base_url(provided)


def fetch(
    path_or_url: str | None,
    base: str,
    headers: Dict[str, str],
    params: Dict[str, str],
    no_auth: bool = False,
) -> Tuple[str, Dict]:
    try:
        return api.fetch(path_or_url, base, headers, params, no_auth)
    except api.APIError as e:
        raise CliError(str(e)) from e


def post(
    path_or_url: str | None,
    base: str,
    json_data: Dict[str, Any],
    headers: Dict[str, str],
    no_auth: bool = False,
) -> Tuple[str, Dict]:
    try:
        return api.post(path_or_url, base, json_data, headers, no_auth)
    except api.APIError as e:
        raise CliError(str(e)) from e


def patch(
    path_or_url: str | None,
    base: str,
    json_data: Dict[str, Any],
    headers: Dict[str, str],
    no_auth: bool = False,
) -> Tuple[str, Dict]:
    try:
        return api.patch(path_or_url, base, json_data, headers, no_auth)
    except api.APIError as e:
        raise CliError(str(e)) from e


def dump_raw(data: Dict) -> None:
    CONSOLE.print(JSON.from_data(data, indent=2))


def print_summary(data: Dict) -> None:
    fields = ["@id", "@type", "title", "description", "review_state"]
    table = Table(title="Content Summary", show_header=False, box=box.SIMPLE)
    for field in fields:
        if value := data.get(field):
            table.add_row(field, str(value))
    if table.row_count:
        CONSOLE.print(table)


def print_items(items: List[Dict]) -> None:
    table = Table(title=f"{len(items)} result(s)", box=box.MINIMAL_DOUBLE_HEAD)
    table.add_column("Title", overflow="fold")
    table.add_column("Type", style="cyan", width=18)
    table.add_column("URL", overflow="fold")
    for item in items:
        table.add_row(item.get("title", "—"), item.get("@type", "—"), item.get("@id", "—"))
    CONSOLE.print(table)


def print_items_with_metadata(items: List[Dict]) -> None:
    """Print items with rich metadata for ls command."""
    if not items:
        CONSOLE.print("[dim]No items[/dim]")
        return
    table = Table(box=box.MINIMAL_DOUBLE_HEAD)
    table.add_column("Title", overflow="fold", style="bold")
    table.add_column("Type", style="cyan", width=20)
    table.add_column("State", style="yellow", width=12)
    table.add_column("Modified", style="dim", width=20)
    for item in items:
        title = item.get("title", item.get("id", "—"))
        item_type = item.get("@type", item.get("type_title", "—"))
        state = item.get("review_state", "—")
        modified = item.get("modified", item.get("effective", "—"))
        if modified and modified != "—":
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(modified.replace("Z", "+00:00"))
                modified = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, AttributeError):
                pass
        table.add_row(title, item_type, state, modified)
    CONSOLE.print(table)


def common_options(
    raw: bool,
    headers: Optional[List[str]],
    params: Optional[List[str]],
) -> Tuple[bool, Dict[str, str], Dict[str, str]]:
    header_map = parse_key_values(headers) if headers else {}
    param_map = parse_key_values(params) if params else {}
    return raw, header_map, param_map


@APP.command("get")
def cmd_get(
    path_or_url: str = typer.Argument(
        None,
        help="Optional path (relative to ++api++) or absolute URL. Defaults to the API root.",
    ),
    base: Optional[str] = typer.Option(None, "--base", help="Override the API base URL (defaults to saved config or example site)."),
    raw: bool = typer.Option(False, "--raw", help="Output raw JSON."),
    no_auth: bool = typer.Option(False, "--no-auth", help="Skip saved auth headers for this call."),
    headers: Optional[List[str]] = typer.Option(
        None,
        "--header",
        "-H",
        help="Additional request headers (key:value). Repeatable.",
    ),
    params: Optional[List[str]] = typer.Option(
        None,
        "--param",
        "-P",
        help="Query parameters (key:value). Repeatable.",
    ),
) -> None:
    raw_flag, header_map, param_map = common_options(raw, headers, params)
    resolved_base = get_base_url(base)
    url, data = fetch(path_or_url, resolved_base, header_map, param_map, no_auth=no_auth)
    CONSOLE.print(f"[green]GET[/green] {url}")
    if raw_flag:
        dump_raw(data)
        return
    print_summary(data)
    items = data.get("items") or data.get("results")
    if isinstance(items, list) and items:
        print_items(items)
    else:
        dump_raw({k: v for k, v in data.items() if k not in {"items", "results"}})


@APP.command("items")
def cmd_items(
    path_or_url: str = typer.Argument(..., help="Path or URL expected to return an 'items' array."),
    limit: int = typer.Option(0, "--limit", "-l", help="Limit number of rows displayed."),
    base: Optional[str] = typer.Option(None, "--base", help="Override the API base URL (defaults to saved config or example site)."),
    raw: bool = typer.Option(False, "--raw", help="Output raw JSON instead of table."),
    no_auth: bool = typer.Option(False, "--no-auth", help="Skip saved auth headers for this call."),
) -> None:
    resolved_base = get_base_url(base)
    url, data = fetch(path_or_url, resolved_base, {}, {}, no_auth=no_auth)
    items = data.get("items")
    if not isinstance(items, list):
        raise CliError("Response does not contain an 'items' array.")
    CONSOLE.print(f"[green]GET[/green] {url}")
    if raw:
        dump_raw(data)
        return
    if limit:
        items = items[:limit]
    print_items(items)


@APP.command("components")
def cmd_components(
    base: Optional[str] = typer.Option(None, "--base", help="Override the API base URL (defaults to saved config or example site)."),
    no_auth: bool = typer.Option(False, "--no-auth", help="Skip saved auth headers for this call."),
) -> None:
    resolved_base = get_base_url(base)
    url, data = fetch(None, resolved_base, {}, {}, no_auth=no_auth)
    components = data.get("@components")
    if not isinstance(components, dict):
        raise CliError("Root response is missing '@components'.")
    table = Table(title="Available components", box=box.MINIMAL)
    table.add_column("Name", style="bold")
    table.add_column("Endpoint")
    for name, meta in components.items():
        table.add_row(name, meta.get("@id", "—"))
    CONSOLE.print(f"[green]GET[/green] {url}")
    CONSOLE.print(table)

@APP.command("login")
def cmd_login(
    username: Optional[str] = typer.Option(None, "--username", "-u", help="Plone username."),
    password: Optional[str] = typer.Option(
        None,
        "--password",
        "-p",
        help="Plone password (will prompt if omitted).",
        prompt=False,
        hide_input=True,
    ),
    base: Optional[str] = typer.Option(None, "--base", help="API base to authenticate against (defaults to saved config or example site)."),
    force: bool = typer.Option(False, "--force", help="Overwrite existing saved credentials without prompting."),
) -> None:
    if CONFIG_FILE.exists() and not force:
        overwrite = typer.confirm(f"{CONFIG_FILE} already exists. Overwrite?", default=False)
        if not overwrite:
            raise typer.Exit(0)
    username = username or typer.prompt("Username")
    password = password or typer.prompt("Password", hide_input=True)
    resolved_base = get_base_url(base)
    try:
        api.login(resolved_base, username, password)
        CONSOLE.print(f"[green]Token saved to {CONFIG_FILE}[/green]")
    except api.APIError as e:
        raise CliError(str(e)) from e


@APP.command("repl")
def cmd_repl(
    base: Optional[str] = typer.Option(None, "--base", help="Override the API base URL (defaults to saved config or demo site)."),
) -> None:
    """Launch interactive shell with filesystem-like navigation."""
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise CliError("The REPL requires an interactive terminal. Run this command directly in a shell.")
    resolved_base = get_base_url(base)
    current_path = ""
    
    # Load history - ensure directory exists
    history = None
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        history = FileHistory(str(HISTORY_FILE))
    except Exception:
        history = None
    
    COMMANDS = ["ls", "cd", "pwd", "get", "items", "raw", "components", "tags", "similar-tags", "merge-tags", "rename-tag", "remove-tag", "login", "logout", "help", "exit", "quit"]

    class ReplCompleter(Completer):
        _tag_cache: Optional[List[str]] = None
        _tag_cache_path: str = ""
        
        def _item_suggestions(self) -> List[str]:
            results: List[str] = []
            try:
                _, data = fetch(current_path, resolved_base, {}, {}, no_auth=False)
                items = data.get("items", [])
                for item in items:
                    # Prefer the 'id' field (usually just the name like "images")
                    item_name = item.get("id")
                    if item_name:
                        if item_name not in results:
                            results.append(item_name)
                        continue
                    
                    # Fallback: extract from @id URL
                    item_id = item.get("@id", "")
                    if item_id:
                        # Remove base URL to get relative path
                        if resolved_base in item_id:
                            rel = item_id.replace(resolved_base, "").lstrip("/")
                        else:
                            # Parse URL to get just the last segment
                            from urllib.parse import urlparse
                            parsed = urlparse(item_id)
                            path_parts = parsed.path.rstrip("/").split("/")
                            rel = path_parts[-1] if path_parts else ""
                        
                        if rel and rel not in results:
                            results.append(rel)
            except Exception:
                pass
            return results
        
        def _tag_suggestions(self) -> List[str]:
            """Get tag suggestions, with caching."""
            # Cache tags per path to avoid fetching on every completion
            cache_key = f"{resolved_base}:{current_path}"
            if self._tag_cache is not None and self._tag_cache_path == cache_key:
                return self._tag_cache
            
            try:
                tag_counts = api.get_all_tags(resolved_base, current_path, no_auth=False)
                tags = sorted(tag_counts.keys())
                self._tag_cache = tags
                self._tag_cache_path = cache_key
                return tags
            except Exception:
                # If fetching fails, return empty list
                return []

        def get_completions(self, document, complete_event):
            text = document.text_before_cursor
            stripped = text.lstrip()
            if not stripped:
                for cmd in COMMANDS:
                    yield Completion(cmd, start_position=0)
                return

            parts = stripped.split()
            last_word = document.get_word_before_cursor(WORD=True)
            has_trailing_space = text.endswith(" ")

            if len(parts) == 1 and not has_trailing_space:
                prefix = parts[0]
                for cmd in COMMANDS:
                    if cmd.startswith(prefix):
                        yield Completion(cmd, start_position=-len(prefix))
                return

            cmd = parts[0]
            
            # Item suggestions for navigation/content commands
            if cmd in ("cd", "get", "items", "raw"):
                suggestions = self._item_suggestions()
                prefix = last_word if not has_trailing_space else ""
                for suggestion in suggestions:
                    if suggestion.startswith(prefix):
                        yield Completion(suggestion, start_position=-len(prefix))
            
            # Tag suggestions for tag management commands
            elif cmd in ("merge-tags", "rename-tag", "remove-tag", "similar-tags"):
                # For merge-tags, complete tags for all arguments except the last (which is target)
                # For rename-tag, complete tags for first argument
                # For remove-tag, complete tags for the argument
                # For similar-tags, complete tags for first argument (if provided)
                
                if cmd == "merge-tags":
                    # All arguments except last can be source tags
                    if len(parts) > 1:
                        suggestions = self._tag_suggestions()
                        prefix = last_word if not has_trailing_space else ""
                        for suggestion in suggestions:
                            if suggestion.startswith(prefix) and suggestion not in parts[1:]:
                                yield Completion(suggestion, start_position=-len(prefix))
                elif cmd in ("rename-tag", "remove-tag"):
                    # First argument is a tag
                    if len(parts) == 2 and not has_trailing_space:
                        suggestions = self._tag_suggestions()
                        prefix = last_word
                        for suggestion in suggestions:
                            if suggestion.startswith(prefix):
                                yield Completion(suggestion, start_position=-len(prefix))
                elif cmd == "similar-tags":
                    # First argument (if present) is a tag
                    if len(parts) == 2 and not has_trailing_space:
                        suggestions = self._tag_suggestions()
                        prefix = last_word
                        for suggestion in suggestions:
                            if suggestion.startswith(prefix):
                                yield Completion(suggestion, start_position=-len(prefix))
    
    completer = ReplCompleter()
    
    CONSOLE.print("[bold green]Plone API Shell[/bold green]")
    CONSOLE.print(f"Base URL: [cyan]{resolved_base}[/cyan]")
    CONSOLE.print("Type 'help' for commands. Use 'exit' to leave the shell, 'login' to authenticate, or 'logout' to remove saved credentials.\n")
    
    while True:
        try:
            text = prompt(
                "plone> ",
                completer=completer,
                history=history,
                complete_while_typing=False,
            )
            if not text.strip():
                continue
            
            parts = shlex.split(text)
            if not parts:
                continue
            
            cmd = parts[0].lower()
            args = parts[1:]
            
            if cmd == "exit" or cmd == "quit":
                break
            elif cmd == "help":
                CONSOLE.print("\n[bold]Navigation:[/bold]")
                CONSOLE.print("  [cyan]ls[/cyan]              - List items in current directory")
                CONSOLE.print("  [cyan]cd <path>[/cyan]        - Change directory (use '..' to go up)")
                CONSOLE.print("  [cyan]pwd[/cyan]              - Show current path")
                CONSOLE.print("\n[bold]Content:[/bold]")
                CONSOLE.print("  [cyan]get [path][/cyan]       - Fetch and display content")
                CONSOLE.print("  [cyan]items [path][/cyan]     - List items array")
                CONSOLE.print("  [cyan]raw [path][/cyan]      - Show raw JSON")
                CONSOLE.print("\n[bold]Tags:[/bold]")
                CONSOLE.print("  [cyan]tags [path][/cyan]     - List all tags with frequency")
                CONSOLE.print("  [cyan]similar-tags [tag] [threshold][/cyan] - Find similar tags")
                CONSOLE.print("    Examples: 'similar-tags mytag 80' or 'similar-tags -t 80' or 'similar-tags mytag --threshold 80'")
                CONSOLE.print("  [cyan]merge-tags <source>... <target>[/cyan] - Merge one or more source tags into target tag")
                CONSOLE.print("    Example: merge-tags 'swimming' 'swim' (single tag)")
                CONSOLE.print("    Example: merge-tags 'swimming' 'diving' 'water-sports' (multiple tags)")
                CONSOLE.print("  [cyan]rename-tag <old_name> <new_name>[/cyan] - Rename a tag")
                CONSOLE.print("  [cyan]remove-tag <tag>[/cyan] - Remove a tag from all items")
                CONSOLE.print("\n[bold]File Operations:[/bold]")
                CONSOLE.print("  [cyan]rename <new_name>[/cyan] - Rename current item")
                CONSOLE.print("  [cyan]cp <source> <dest>[/cyan] - Copy item")
                CONSOLE.print("  [cyan]mv <source> <dest>[/cyan] - Move item")
                CONSOLE.print("\n[bold]Workflow:[/bold]")
                CONSOLE.print("  [cyan]transitions[/cyan]     - List available workflow transitions")
                CONSOLE.print("  [cyan]transition <name>[/cyan] - Execute a workflow transition")
                CONSOLE.print("  [cyan]bulk-transition <name>[/cyan] - Execute transition on all items in current directory")
                CONSOLE.print("\n[bold]Other:[/bold]")
                CONSOLE.print("  [cyan]components[/cyan]      - List available components")
                CONSOLE.print("  [cyan]login [username] [password][/cyan] - Authenticate and save token (password optional; will prompt if omitted)")
                CONSOLE.print("  [cyan]logout[/cyan]          - Remove saved credentials (same as CLI command)")
                CONSOLE.print("  [cyan]help[/cyan]            - Show this help")
                CONSOLE.print("  [cyan]exit[/cyan] / [cyan]quit[/cyan] - Leave shell (does not log out)\n")
            elif cmd == "pwd":
                path_display = current_path if current_path else "/"
                CONSOLE.print(f"[cyan]{path_display}[/cyan]")
            elif cmd == "ls":
                try:
                    _, data = fetch(current_path, resolved_base, {}, {}, no_auth=False)
                    items = data.get("items", [])
                    if items:
                        print_items_with_metadata(items)
                    else:
                        CONSOLE.print("[dim]No items[/dim]")
                except CliError as e:
                    CONSOLE.print(f"[red]Error:[/red] {e}")
                except Exception as e:
                    CONSOLE.print(f"[red]Error:[/red] {e}")
            elif cmd == "cd":
                if not args:
                    current_path = ""
                    CONSOLE.print("[green]Changed to root[/green]")
                elif args[0] == "..":
                    # Go up one level
                    if current_path:
                        parts_path = current_path.rstrip("/").split("/")
                        if len(parts_path) > 1:
                            current_path = "/".join(parts_path[:-1])
                        else:
                            current_path = ""
                    else:
                        CONSOLE.print("[yellow]Already at root[/yellow]")
                else:
                    target = args[0]
                    # Handle full URLs
                    if target.startswith(("http://", "https://")):
                        # Extract path from full URL
                        from urllib.parse import urlparse
                        parsed = urlparse(target)
                        # Remove the base URL portion to get relative path
                        if resolved_base.rstrip("/") in target:
                            target = target.replace(resolved_base.rstrip("/"), "").lstrip("/")
                        else:
                            # If it's a different domain, extract just the path
                            target = parsed.path.lstrip("/")
                            # Remove ++api++ if present
                            if target.startswith("++api++/"):
                                target = target[8:]
                    
                    target = target.lstrip("/")
                    # Try to navigate to the item
                    try:
                        test_path = f"{current_path}/{target}".strip("/") if current_path else target
                        _, data = fetch(test_path, resolved_base, {}, {}, no_auth=False)
                        current_path = test_path
                        title = data.get("title", data.get("id", test_path))
                        CONSOLE.print(f"[green]Changed to:[/green] {title}")
                    except Exception as e:
                        CONSOLE.print(f"[red]Error:[/red] Cannot navigate to '{args[0]}': {e}")
            elif cmd == "get":
                path = args[0] if args else current_path
                try:
                    url, data = fetch(path, resolved_base, {}, {}, no_auth=False)
                    CONSOLE.print(f"[green]GET[/green] {url}")
                    print_summary(data)
                    items = data.get("items") or data.get("results")
                    if isinstance(items, list) and items:
                        print_items(items[:10])  # Limit to 10 for display
                except Exception as e:
                    CONSOLE.print(f"[red]Error:[/red] {e}")
            elif cmd == "items":
                path = args[0] if args else current_path
                try:
                    url, data = fetch(path, resolved_base, {}, {}, no_auth=False)
                    items = data.get("items")
                    if not isinstance(items, list):
                        CONSOLE.print("[red]Error:[/red] Response does not contain an 'items' array.")
                    else:
                        CONSOLE.print(f"[green]GET[/green] {url}")
                        print_items(items)
                except Exception as e:
                    CONSOLE.print(f"[red]Error:[/red] {e}")
            elif cmd == "raw":
                path = args[0] if args else current_path
                try:
                    url, data = fetch(path, resolved_base, {}, {}, no_auth=False)
                    CONSOLE.print(f"[green]GET[/green] {url}")
                    dump_raw(data)
                except Exception as e:
                    CONSOLE.print(f"[red]Error:[/red] {e}")
            elif cmd == "components":
                try:
                    url, data = fetch(None, resolved_base, {}, {}, no_auth=False)
                    components = data.get("@components")
                    if not isinstance(components, dict):
                        CONSOLE.print("[red]Error:[/red] Root response is missing '@components'.")
                    else:
                        table = Table(title="Available components", box=box.MINIMAL)
                        table.add_column("Name", style="bold")
                        table.add_column("Endpoint")
                        for name, meta in components.items():
                            table.add_row(name, meta.get("@id", "—"))
                        CONSOLE.print(f"[green]GET[/green] {url}")
                        CONSOLE.print(table)
                except Exception as e:
                    CONSOLE.print(f"[red]Error:[/red] {e}")
            elif cmd == "tags":
                path = args[0] if args else current_path
                try:
                    def warn_print(msg: str) -> None:
                        CONSOLE.print(msg)
                    
                    tag_counts = api.get_all_tags(resolved_base, path, no_auth=False, warn_callback=warn_print)
                    if not tag_counts:
                        CONSOLE.print("[yellow]No tags found.[/yellow]")
                    else:
                        sorted_tags = sorted(tag_counts.items(), key=lambda x: (-x[1], x[0].lower()))
                        table = Table(title=f"Tags ({len(tag_counts)} unique)", box=box.MINIMAL_DOUBLE_HEAD)
                        table.add_column("Tag", style="bold")
                        table.add_column("Count", style="cyan", justify="right")
                        for tag, count in sorted_tags:
                            table.add_row(tag, str(count))
                        CONSOLE.print(table)
                except Exception as e:
                    CONSOLE.print(f"[red]Error:[/red] {e}")
            elif cmd == "similar-tags":
                # Parse arguments: [tag] [threshold] or [threshold] if first arg is a number
                # Also supports: -t/--threshold flags
                # Examples:
                #   similar-tags 80              -> threshold=80, no query tag
                #   similar-tags mytag 80        -> query_tag="mytag", threshold=80
                #   similar-tags mytag           -> query_tag="mytag", threshold=70 (default)
                #   similar-tags -t 80           -> threshold=80, no query tag
                #   similar-tags mytag -t 80     -> query_tag="mytag", threshold=80
                #   similar-tags --threshold 80  -> threshold=80, no query tag
                query_tag = None
                threshold = 70
                
                # Parse flags first
                remaining_args = []
                i = 0
                while i < len(args):
                    arg = args[i]
                    if arg in ("-t", "--threshold"):
                        if i + 1 < len(args):
                            try:
                                threshold = int(args[i + 1])
                                if not (0 <= threshold <= 100):
                                    CONSOLE.print(f"[yellow]Warning: Threshold {threshold} out of range (0-100), using 70[/yellow]")
                                    threshold = 70
                                i += 2  # Skip flag and value
                                continue
                            except ValueError:
                                CONSOLE.print(f"[yellow]Warning: '{args[i + 1]}' is not a valid threshold (0-100), using 70[/yellow]")
                                i += 2  # Skip flag and invalid value
                                continue
                        else:
                            CONSOLE.print(f"[yellow]Warning: '{arg}' requires a value, using default threshold 70[/yellow]")
                            i += 1
                            continue
                    remaining_args.append(arg)
                    i += 1
                
                # Parse remaining positional arguments
                if remaining_args:
                    # Check if first arg is a number (threshold)
                    try:
                        # Try to parse as integer
                        threshold_candidate = int(remaining_args[0])
                        if 0 <= threshold_candidate <= 100:
                            # Valid threshold range, treat as threshold
                            threshold = threshold_candidate
                        else:
                            # Out of range, treat as tag name
                            query_tag = remaining_args[0]
                            if len(remaining_args) > 1:
                                try:
                                    threshold = int(remaining_args[1])
                                    if not (0 <= threshold <= 100):
                                        CONSOLE.print(f"[yellow]Warning: Threshold {threshold} out of range (0-100), using 70[/yellow]")
                                        threshold = 70
                                except ValueError:
                                    CONSOLE.print(f"[yellow]Warning: '{remaining_args[1]}' is not a valid threshold (0-100), using 70[/yellow]")
                    except ValueError:
                        # First arg is not a number, treat as tag name
                        query_tag = remaining_args[0]
                        if len(remaining_args) > 1:
                            try:
                                threshold = int(remaining_args[1])
                                if not (0 <= threshold <= 100):
                                    CONSOLE.print(f"[yellow]Warning: Threshold {threshold} out of range (0-100), using 70[/yellow]")
                                    threshold = 70
                            except ValueError:
                                CONSOLE.print(f"[yellow]Warning: '{remaining_args[1]}' is not a valid threshold (0-100), using 70[/yellow]")
                path = current_path
                try:
                    similar_tags = api.find_similar_tags(resolved_base, query_tag, path, threshold, no_auth=False)
                    if not similar_tags:
                        if query_tag:
                            CONSOLE.print(f"[yellow]No tags found similar to '{query_tag}' (threshold: {threshold}).[/yellow]")
                        else:
                            CONSOLE.print(f"[yellow]No similar tag pairs found (threshold: {threshold}).[/yellow]")
                    else:
                        if query_tag:
                            table = Table(
                                title=f"Tags similar to '{query_tag}' ({len(similar_tags)} found)",
                                box=box.MINIMAL_DOUBLE_HEAD
                            )
                            table.add_column("Tag", style="bold")
                            table.add_column("Count", style="cyan", justify="right")
                            table.add_column("Similarity", style="green", justify="right")
                            for tag, count, similarity, _ in similar_tags:
                                table.add_row(tag, str(count), f"{similarity}%")
                        else:
                            table = Table(
                                title=f"Similar Tag Pairs ({len(similar_tags)} found)",
                                box=box.MINIMAL_DOUBLE_HEAD
                            )
                            table.add_column("Tag", style="bold")
                            table.add_column("Count", style="cyan", justify="right")
                            table.add_column("Similarity", style="green", justify="right")
                            table.add_column("Similar To", style="yellow")
                            for tag, count, similarity, matched_tag in similar_tags:
                                table.add_row(tag, str(count), f"{similarity}%", matched_tag)
                        CONSOLE.print(table)
                except Exception as e:
                    CONSOLE.print(f"[red]Error:[/red] {e}")
            elif cmd == "merge-tags":
                if len(args) < 2:
                    CONSOLE.print("[red]Error:[/red] merge-tags requires at least two arguments: <source_tag>... <target_tag>")
                    CONSOLE.print("  Example: merge-tags 'swimming' 'swim' (merges 'swimming' into 'swim')")
                    CONSOLE.print("  Example: merge-tags 'swimming' 'diving' 'water-polo' 'water-sports' (merges multiple tags)")
                else:
                    # Last argument is target, all others are source tags
                    source_tags = args[:-1]
                    target_tag = args[-1]
                    try:
                        # Collect all items that have any of the source tags
                        all_items: Dict[str, Dict[str, Any]] = {}  # Use @id as key to deduplicate
                        source_tag_counts: Dict[str, int] = {}
                        
                        for source_tag in source_tags:
                            try:
                                items = api.search_by_subject(resolved_base, source_tag, current_path, no_auth=False)
                                source_tag_counts[source_tag] = len(items)
                                for item in items:
                                    item_id = item.get("@id")
                                    if item_id:
                                        all_items[item_id] = item
                            except Exception:
                                pass
                        
                        items_list = list(all_items.values())
                        
                        if not items_list:
                            tag_list = ", ".join(f"'{tag}'" for tag in source_tags)
                            CONSOLE.print(f"[yellow]No items found with any of the source tags: {tag_list}[/yellow]")
                        else:
                            if len(source_tags) == 1:
                                CONSOLE.print(f"[cyan]Found {len(items_list)} item(s) with tag '{source_tags[0]}'[/cyan]")
                                confirm_msg = f"Merge '{source_tags[0]}' into '{target_tag}' on {len(items_list)} item(s)?"
                            else:
                                tag_list = ", ".join(f"'{tag}'" for tag in source_tags)
                                CONSOLE.print(f"[cyan]Found {len(items_list)} unique item(s) with tags: {tag_list}[/cyan]")
                                for tag, count in source_tag_counts.items():
                                    CONSOLE.print(f"  - '{tag}': {count} item(s)")
                                confirm_msg = f"Merge {len(source_tags)} tags into '{target_tag}' on {len(items_list)} item(s)?"
                            
                            if typer.confirm(confirm_msg):
                                updated = 0
                                for item in items_list:
                                    try:
                                        item_path = item.get("@id", "").replace(resolved_base.rstrip("/"), "").lstrip("/")
                                        current_tags = item.get("subjects", [])
                                        # Remove all source tags, add target tag if not present
                                        new_tags = [tag for tag in current_tags if tag not in source_tags]
                                        if target_tag not in new_tags:
                                            new_tags.append(target_tag)
                                        api.update_item_subjects(resolved_base, item_path, new_tags, no_auth=False)
                                        updated += 1
                                    except Exception:
                                        pass
                                CONSOLE.print(f"[green]Updated {updated} item(s)[/green]")
                    except Exception as e:
                        CONSOLE.print(f"[red]Error:[/red] {e}")
            elif cmd == "rename-tag":
                if len(args) < 2:
                    CONSOLE.print("[red]Error:[/red] rename-tag requires two arguments: <old_name> <new_name>")
                    CONSOLE.print("  Example: rename-tag 'swimming' 'swim' (renames 'swimming' to 'swim' on all items)")
                else:
                    old_tag, new_tag = args[0], args[1]
                    try:
                        items = api.search_by_subject(resolved_base, old_tag, current_path, no_auth=False)
                        if not items:
                            CONSOLE.print(f"[yellow]No items found with tag '{old_tag}'.[/yellow]")
                        else:
                            CONSOLE.print(f"[cyan]Found {len(items)} item(s) with tag '{old_tag}'[/cyan]")
                            if typer.confirm(f"Rename tag '{old_tag}' to '{new_tag}' on {len(items)} item(s)?"):
                                updated = 0
                                errors = 0
                                for item in items:
                                    try:
                                        # Extract path from @id URL
                                        item_id = item.get("@id", "")
                                        if not item_id:
                                            CONSOLE.print(f"[yellow]Warning: Item {item.get('title', 'unknown')} has no @id[/yellow]")
                                            errors += 1
                                            continue
                                        
                                        # Convert full URL to relative API path
                                        if item_id.startswith(("http://", "https://")):
                                            from urllib.parse import urlparse
                                            parsed = urlparse(item_id)
                                            path = parsed.path
                                            
                                            # If the URL contains ++api++, extract the path after it
                                            if "/++api++/" in path:
                                                path = path.split("/++api++/", 1)[1]
                                            elif path.startswith("/++api++"):
                                                path = path[7:].lstrip("/")
                                            # If it's a public URL (no ++api++), extract the path
                                            else:
                                                # Extract domain from base URL to get the site root
                                                base_parsed = urlparse(resolved_base)
                                                site_root = f"{base_parsed.scheme}://{base_parsed.netloc}"
                                                
                                                # If the item URL starts with the site root, extract the path
                                                if item_id.startswith(site_root):
                                                    path = item_id.replace(site_root, "").lstrip("/")
                                                else:
                                                    # Just use the path portion
                                                    path = path.lstrip("/")
                                            
                                            item_path = path
                                        else:
                                            # Already a relative path
                                            item_path = item_id.lstrip("/")
                                        
                                        if not item_path:
                                            CONSOLE.print(f"[yellow]Warning: Could not extract path from item {item.get('title', 'unknown')}[/yellow]")
                                            errors += 1
                                            continue
                                        
                                        # Fetch current item to get actual subjects
                                        try:
                                            _, current_item = api.fetch(item_path, resolved_base, {}, {}, no_auth=False)
                                            # Try multiple field names for subjects
                                            current_tags = (
                                                current_item.get("Subject") or
                                                current_item.get("subjects") or
                                                current_item.get("subject") or
                                                []
                                            )
                                            # Ensure it's a list
                                            if isinstance(current_tags, str):
                                                current_tags = [current_tags] if current_tags else []
                                            elif not isinstance(current_tags, list):
                                                current_tags = list(current_tags) if current_tags else []
                                        except Exception as e:
                                            CONSOLE.print(f"[yellow]Warning: Could not fetch item {item_path}: {e}[/yellow]")
                                            # Fallback to subjects from search result
                                            current_tags = item.get("subjects", [])
                                        
                                        # Replace old tag with new tag (case-sensitive match)
                                        # Remove all instances of old_tag and add new_tag
                                        new_tags = [tag for tag in current_tags if tag != old_tag]
                                        # Add new tag if it's not already present (avoid duplicates)
                                        if new_tag not in new_tags:
                                            new_tags.append(new_tag)
                                        
                                        # Only update if tags actually changed
                                        if set(current_tags) != set(new_tags):
                                            try:
                                                api.update_item_subjects(resolved_base, item_path, new_tags, no_auth=False)
                                            except api.APIError as update_error:
                                                # API returned an error - report it with full details
                                                error_msg = str(update_error)
                                                # If it's the __getitem__ error, provide more context
                                                if "__getitem__" in error_msg or "500" in error_msg:
                                                    CONSOLE.print(f"[red]Server error updating '{item.get('title', 'unknown')}': {error_msg}[/red]")
                                                    CONSOLE.print(f"[yellow]This is a known issue with the Plone REST API on this server. The Subject field may not be updatable via REST API.[/yellow]")
                                                else:
                                                    CONSOLE.print(f"[red]Error updating '{item.get('title', 'unknown')}': {error_msg}[/red]")
                                                errors += 1
                                                continue
                                            
                                            # Verify the update succeeded by fetching the item again
                                            try:
                                                _, verify_item = api.fetch(item_path, resolved_base, {}, {}, no_auth=False)
                                                verify_tags = (
                                                    verify_item.get("Subject") or
                                                    verify_item.get("subjects") or
                                                    verify_item.get("subject") or
                                                    []
                                                )
                                                if isinstance(verify_tags, str):
                                                    verify_tags = [verify_tags] if verify_tags else []
                                                elif not isinstance(verify_tags, list):
                                                    verify_tags = list(verify_tags) if verify_tags else []
                                                
                                                # Verify the update: old tag should be gone, new tag should be present
                                                old_tag_still_present = old_tag in verify_tags
                                                new_tag_present = new_tag in verify_tags
                                                
                                                if old_tag_still_present:
                                                    if new_tag_present:
                                                        # Both tags present - update partially failed
                                                        CONSOLE.print(f"[yellow]Warning: Both old tag '{old_tag}' and new tag '{new_tag}' present in '{item.get('title', 'unknown')}'. Update may have failed.[/yellow]")
                                                        errors += 1
                                                        continue
                                                    else:
                                                        # Old tag still there, new tag not added - update failed
                                                        CONSOLE.print(f"[yellow]Warning: Update failed for '{item.get('title', 'unknown')}'. Old tag '{old_tag}' still present, new tag '{new_tag}' not added.[/yellow]")
                                                        errors += 1
                                                        continue
                                                elif not new_tag_present:
                                                    # Old tag removed but new tag not added - update failed
                                                    CONSOLE.print(f"[yellow]Warning: Update failed for '{item.get('title', 'unknown')}'. Old tag removed but new tag '{new_tag}' not added.[/yellow]")
                                                    errors += 1
                                                    continue
                                                # Success: old tag removed, new tag present
                                            except Exception:
                                                # Verification failed, but update was attempted
                                                pass
                                            
                                            updated += 1
                                        else:
                                            # Tags didn't change (maybe old_tag wasn't in the list)
                                            CONSOLE.print(f"[yellow]Warning: Tag '{old_tag}' not found in item '{item.get('title', 'unknown')}', skipping[/yellow]")
                                    except api.APIError as e:
                                        errors += 1
                                        item_title = item.get("title", item.get("id", "unknown"))
                                        CONSOLE.print(f"[red]Error updating '{item_title}': {e}[/red]")
                                    except Exception as e:
                                        errors += 1
                                        item_title = item.get("title", item.get("id", "unknown"))
                                        CONSOLE.print(f"[red]Error updating '{item_title}': {e}[/red]")
                                
                                if updated > 0:
                                    CONSOLE.print(f"[green]Updated {updated} item(s)[/green]")
                                if errors > 0:
                                    CONSOLE.print(f"[yellow]{errors} error(s) occurred[/yellow]")
                                if updated == 0 and errors == 0:
                                    CONSOLE.print(f"[yellow]No items were updated[/yellow]")
                    except Exception as e:
                        CONSOLE.print(f"[red]Error:[/red] {e}")
            elif cmd == "remove-tag":
                if not args:
                    CONSOLE.print("[red]Error:[/red] remove-tag requires a tag name")
                else:
                    tag = args[0]
                    try:
                        items = api.search_by_subject(resolved_base, tag, current_path, no_auth=False)
                        if not items:
                            CONSOLE.print(f"[yellow]No items found with tag '{tag}'.[/yellow]")
                        else:
                            CONSOLE.print(f"[cyan]Found {len(items)} item(s) with tag '{tag}'[/cyan]")
                            if typer.confirm(f"Remove tag '{tag}' from {len(items)} item(s)?"):
                                updated = 0
                                for item in items:
                                    try:
                                        item_path = item.get("@id", "").replace(resolved_base.rstrip("/"), "").lstrip("/")
                                        current_tags = item.get("subjects", [])
                                        new_tags = [t for t in current_tags if t != tag]
                                        api.update_item_subjects(resolved_base, item_path, new_tags, no_auth=False)
                                        updated += 1
                                    except Exception:
                                        pass
                                CONSOLE.print(f"[green]Updated {updated} item(s)[/green]")
                    except Exception as e:
                        CONSOLE.print(f"[red]Error:[/red] {e}")
            elif cmd == "login":
                username = args[0] if args else None
                password = args[1] if len(args) > 1 else None
                if not username:
                    username = typer.prompt("Username")
                if not password:
                    password = typer.prompt("Password", hide_input=True)
                try:
                    api.login(resolved_base, username, password)
                    CONSOLE.print(f"[green]Authenticated. Token saved to {CONFIG_FILE}[/green]")
                except api.APIError as e:
                    CONSOLE.print(f"[red]Login failed:[/red] {e}")
            elif cmd == "logout":
                if CONFIG_FILE.exists():
                    delete_config()
                    CONSOLE.print(f"[yellow]Removed saved credentials at {CONFIG_FILE}[/yellow]")
                else:
                    CONSOLE.print("No saved credentials found.")
            else:
                CONSOLE.print(f"[red]Unknown command:[/red] {cmd}. Type 'help' for available commands.")
        except KeyboardInterrupt:
            CONSOLE.print("\n[yellow]Use 'exit' to leave the shell or 'logout' to remove saved credentials[/yellow]")
        except EOFError:
            break
    
    CONSOLE.print("\n[dim]Goodbye![/dim]")


@APP.callback()
def main(ctx: typer.Context):
    """Default entrypoint: start REPL when no subcommand is provided."""
    ctx.obj = ctx.obj or {}
    if not ctx.obj.get("version_reported"):
        CONSOLE.print(VERSION_MESSAGE)
        ctx.obj["version_reported"] = True
    if ctx.invoked_subcommand is None:
        cmd_repl()


@APP.command("logout")
def cmd_logout() -> None:
    if CONFIG_FILE.exists():
        delete_config()
        CONSOLE.print(f"[yellow]Removed saved credentials at {CONFIG_FILE}[/yellow]")
    else:
        CONSOLE.print("No saved credentials found.")


@APP.command("serve")
def cmd_serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host interface for the API server."),
    port: int = typer.Option(8787, "--port", "-p", help="Port for the API server."),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload (development only)."),
    allow_origin: List[str] = typer.Option(
        [],
        "--allow-origin",
        help="Additional CORS origin allowed to access the API. Repeat to add more.",
    ),
) -> None:
    """Start the HTTP server used by the SvelteKit desktop UI."""
    from . import server

    origins = allow_origin or None
    try:
        server.run_server(host=host, port=port, reload=reload, allowed_origins=origins)
    except KeyboardInterrupt:
        CONSOLE.print("\n[dim]Server stopped[/dim]")


@APP.command("tags")
def cmd_tags(
    path: str = typer.Argument("", help="Path to analyze (defaults to current/root)."),
    base: Optional[str] = typer.Option(None, "--base", help="Override the API base URL."),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="Include tags from subdirectories."),
    no_auth: bool = typer.Option(False, "--no-auth", help="Skip saved auth headers."),
    debug: bool = typer.Option(False, "--debug", help="Show debug information about tag collection."),
) -> None:
    """List all tags/subjects with their frequency."""
    resolved_base = get_base_url(base)
    try:
        if debug:
            CONSOLE.print(f"[dim]Debug: Searching for tags in path: '{path or '(root)'}'[/dim]")
            CONSOLE.print(f"[dim]Debug: Base URL: {resolved_base}[/dim]")
        
        def warn_print(msg: str) -> None:
            """Print warning messages."""
            CONSOLE.print(msg)
        
        def debug_print(msg: str) -> None:
            """Print debug messages."""
            CONSOLE.print(f"[dim]{msg}[/dim]")
        
        tag_counts = api.get_all_tags(
            resolved_base, 
            path, 
            no_auth=no_auth, 
            debug=debug, 
            warn_callback=warn_print,
            debug_callback=debug_print if debug else None
        )
        
        if debug:
            CONSOLE.print(f"[dim]Debug: Found {len(tag_counts)} unique tags[/dim]")
        
        if not tag_counts:
            CONSOLE.print("[yellow]No tags found.[/yellow]")
            if debug:
                CONSOLE.print("[dim]Debug: Try fetching a specific item to see its structure: ploneapi-shell get /some-item --raw[/dim]")
            return
        
        # Sort by frequency (descending) then alphabetically
        sorted_tags = sorted(tag_counts.items(), key=lambda x: (-x[1], x[0].lower()))
        
        table = Table(title=f"Tags ({len(tag_counts)} unique)", box=box.MINIMAL_DOUBLE_HEAD)
        table.add_column("Tag", style="bold")
        table.add_column("Count", style="cyan", justify="right")
        
        for tag, count in sorted_tags:
            table.add_row(tag, str(count))
        
        CONSOLE.print(table)
    except api.APIError as e:
        raise CliError(str(e)) from e


@APP.command("merge-tags")
def cmd_merge_tags(
    source_tags: List[str] = typer.Argument(..., help="Source tag(s) to merge from (will be removed). Can specify multiple tags."),
    target_tag: str = typer.Argument(..., help="Target tag to merge into (existing or new tag, will be kept)."),
    path: str = typer.Option("", "--path", help="Limit to items in this path."),
    base: Optional[str] = typer.Option(None, "--base", help="Override the API base URL."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be changed without making changes."),
    no_auth: bool = typer.Option(False, "--no-auth", help="Skip saved auth headers."),
) -> None:
    """
    Merge one or more tags into a target tag.
    
    Examples:
    - Merge one tag: merge-tags swimming swim
    - Merge multiple tags: merge-tags swimming diving water-polo water-sports
    """
    resolved_base = get_base_url(base)
    
    # If only one source tag provided, use the old behavior
    # If multiple, merge all of them
    if not source_tags:
        CONSOLE.print("[red]Error:[/red] At least one source tag is required")
        raise typer.Exit(1)
    
    # Collect all items that have any of the source tags
    all_items: Dict[str, Dict[str, Any]] = {}  # Use @id as key to deduplicate
    source_tag_counts: Dict[str, int] = {}
    
    for source_tag in source_tags:
        try:
            items = api.search_by_subject(resolved_base, source_tag, path, no_auth=no_auth)
            source_tag_counts[source_tag] = len(items)
            for item in items:
                item_id = item.get("@id")
                if item_id:
                    all_items[item_id] = item
        except api.APIError as e:
            CONSOLE.print(f"[yellow]Warning: Could not search for tag '{source_tag}': {e}[/yellow]")
    
    items_list = list(all_items.values())
    
    if not items_list:
        tag_list = ", ".join(f"'{tag}'" for tag in source_tags)
        CONSOLE.print(f"[yellow]No items found with any of the source tags: {tag_list}[/yellow]")
        return
    
    # Show summary
    if len(source_tags) == 1:
        CONSOLE.print(f"[cyan]Found {len(items_list)} item(s) with tag '{source_tags[0]}'[/cyan]")
    else:
        tag_list = ", ".join(f"'{tag}'" for tag in source_tags)
        CONSOLE.print(f"[cyan]Found {len(items_list)} unique item(s) with tags: {tag_list}[/cyan]")
        for tag, count in source_tag_counts.items():
            CONSOLE.print(f"  - '{tag}': {count} item(s)")
    
    if dry_run:
        CONSOLE.print("[yellow]DRY RUN - No changes will be made[/yellow]")
        for item in items_list[:10]:  # Show first 10
            title = item.get("title", item.get("id", "—"))
            current_tags = item.get("subjects", [])
            # Remove all source tags, add target tag if not present
            new_tags = [tag for tag in current_tags if tag not in source_tags]
            if target_tag not in new_tags:
                new_tags.append(target_tag)
            CONSOLE.print(f"  {title}: {current_tags} → {new_tags}")
        if len(items_list) > 10:
            CONSOLE.print(f"  ... and {len(items_list) - 10} more")
        return
    
    # Confirm
    if len(source_tags) == 1:
        confirm_msg = f"Merge '{source_tags[0]}' into '{target_tag}' on {len(items_list)} item(s)?"
    else:
        tag_list = ", ".join(f"'{tag}'" for tag in source_tags)
        confirm_msg = f"Merge {len(source_tags)} tags ({tag_list}) into '{target_tag}' on {len(items_list)} item(s)?"
    
    if not typer.confirm(confirm_msg):
        raise typer.Exit(0)
    
    updated = 0
    errors = 0
    
    for item in items_list:
        try:
            item_path = item.get("@id", "").replace(resolved_base.rstrip("/"), "").lstrip("/")
            current_tags = item.get("subjects", [])
            # Remove all source tags, add target tag if not present
            new_tags = [tag for tag in current_tags if tag not in source_tags]
            if target_tag not in new_tags:
                new_tags.append(target_tag)
            
            api.update_item_subjects(resolved_base, item_path, new_tags, no_auth=no_auth)
            updated += 1
        except Exception as e:
            errors += 1
            CONSOLE.print(f"[red]Error updating {item.get('title', 'item')}: {e}[/red]")
    
    CONSOLE.print(f"[green]Updated {updated} item(s)[/green]")
    if errors:
        CONSOLE.print(f"[yellow]{errors} error(s) occurred[/yellow]")


@APP.command("rename-tag")
def cmd_rename_tag(
    old_tag: str = typer.Argument(..., help="Current tag name to rename."),
    new_tag: str = typer.Argument(..., help="New tag name (can be existing or new tag)."),
    path: str = typer.Option("", "--path", help="Limit to items in this path."),
    base: Optional[str] = typer.Option(None, "--base", help="Override the API base URL."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be changed without making changes."),
    no_auth: bool = typer.Option(False, "--no-auth", help="Skip saved auth headers."),
) -> None:
    """Rename a tag (same as merge-tags but removes old tag)."""
    # This is essentially the same as merge-tags with a single source
    cmd_merge_tags([old_tag], new_tag, path, base, dry_run, no_auth)


@APP.command("remove-tag")
def cmd_remove_tag(
    tag: str = typer.Argument(..., help="Tag to remove."),
    path: str = typer.Option("", "--path", help="Limit to items in this path."),
    base: Optional[str] = typer.Option(None, "--base", help="Override the API base URL."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be changed without making changes."),
    no_auth: bool = typer.Option(False, "--no-auth", help="Skip saved auth headers."),
) -> None:
    """Remove a tag from all items."""
    resolved_base = get_base_url(base)
    try:
        items = api.search_by_subject(resolved_base, tag, path, no_auth=no_auth)
        if not items:
            CONSOLE.print(f"[yellow]No items found with tag '{tag}'.[/yellow]")
            return
        
        CONSOLE.print(f"[cyan]Found {len(items)} item(s) with tag '{tag}'[/cyan]")
        
        if dry_run:
            CONSOLE.print("[yellow]DRY RUN - No changes will be made[/yellow]")
            for item in items[:10]:  # Show first 10
                title = item.get("title", item.get("id", "—"))
                current_tags = item.get("subjects", [])
                new_tags = [t for t in current_tags if t != tag]
                CONSOLE.print(f"  {title}: {current_tags} → {new_tags}")
            if len(items) > 10:
                CONSOLE.print(f"  ... and {len(items) - 10} more")
            return
        
        # Confirm
        if not typer.confirm(f"Remove tag '{tag}' from {len(items)} item(s)?"):
            raise typer.Exit(0)
        
        updated = 0
        errors = 0
        
        for item in items:
            try:
                item_path = item.get("@id", "").replace(resolved_base.rstrip("/"), "").lstrip("/")
                current_tags = item.get("subjects", [])
                new_tags = [t for t in current_tags if t != tag]
                
                api.update_item_subjects(resolved_base, item_path, new_tags, no_auth=no_auth)
                updated += 1
            except Exception as e:
                errors += 1
                CONSOLE.print(f"[red]Error updating {item.get('title', 'item')}: {e}[/red]")
        
        CONSOLE.print(f"[green]Updated {updated} item(s)[/green]")
        if errors:
            CONSOLE.print(f"[yellow]{errors} error(s) occurred[/yellow]")
    except api.APIError as e:
        raise CliError(str(e)) from e


@APP.command("similar-tags")
def cmd_similar_tags(
    query_tag: Optional[str] = typer.Argument(None, help="Tag to find similar matches for (optional - if omitted, finds all similar tag pairs)."),
    path: str = typer.Option("", "--path", help="Limit search to items in this path."),
    base: Optional[str] = typer.Option(None, "--base", help="Override the API base URL."),
    threshold: int = typer.Option(70, "--threshold", "-t", help="Minimum similarity score (0-100). Default: 70."),
    no_auth: bool = typer.Option(False, "--no-auth", help="Skip saved auth headers."),
) -> None:
    """Find tags similar to the given tag using fuzzy matching. If no tag is provided, finds all pairs of similar tags."""
    resolved_base = get_base_url(base)
    try:
        similar_tags = api.find_similar_tags(resolved_base, query_tag, path, threshold, no_auth=no_auth)
        if not similar_tags:
            if query_tag:
                CONSOLE.print(f"[yellow]No tags found similar to '{query_tag}' (threshold: {threshold}).[/yellow]")
            else:
                CONSOLE.print(f"[yellow]No similar tag pairs found (threshold: {threshold}).[/yellow]")
            return
        
        if query_tag:
            table = Table(
                title=f"Tags similar to '{query_tag}' ({len(similar_tags)} found)",
                box=box.MINIMAL_DOUBLE_HEAD
            )
            table.add_column("Tag", style="bold")
            table.add_column("Count", style="cyan", justify="right")
            table.add_column("Similarity", style="green", justify="right")
            
            for tag, count, similarity, _ in similar_tags:
                table.add_row(tag, str(count), f"{similarity}%")
        else:
            table = Table(
                title=f"Similar Tag Pairs ({len(similar_tags)} found)",
                box=box.MINIMAL_DOUBLE_HEAD
            )
            table.add_column("Tag", style="bold")
            table.add_column("Count", style="cyan", justify="right")
            table.add_column("Similarity", style="green", justify="right")
            table.add_column("Similar To", style="yellow")
            
            for tag, count, similarity, matched_tag in similar_tags:
                table.add_row(tag, str(count), f"{similarity}%", matched_tag)
        
        CONSOLE.print(table)
    except api.APIError as e:
        raise CliError(str(e)) from e


@APP.command("web")
def cmd_web(
    port: int = typer.Option(8501, "--port", "-p", help="Port to run Streamlit on."),
    host: str = typer.Option("localhost", "--host", "-h", help="Host to bind to."),
) -> None:
    """Launch web interface using Streamlit."""
    import subprocess
    import sys
    from pathlib import Path
    
    # Get the path to web.py
    web_file = Path(__file__).parent / "web.py"
    cmd = [
        sys.executable, "-m", "streamlit", "run",
        str(web_file),
        "--server.port", str(port),
        "--server.address", host,
    ]
    
    CONSOLE.print(f"[green]Starting web interface...[/green]")
    CONSOLE.print(f"[cyan]Open http://{host}:{port} in your browser[/cyan]")
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        CONSOLE.print("\n[yellow]Web interface stopped.[/yellow]")


if __name__ == "__main__":
    APP()

