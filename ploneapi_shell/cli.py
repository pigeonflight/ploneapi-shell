#!/usr/bin/env python3
"""
Plone API Shell - Interactive explorer for Plone REST API sites.

Most modern Plone 6.x sites expose their REST API at siteroot/++api++
"""

from __future__ import annotations

import json
import os
import sys
import time
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


def get_auth_status() -> str:
    """Return current authentication status for prompt display."""
    config = load_config()
    if not config:
        return "anonymous"
    auth = config.get("auth") or {}
    username = auth.get("username")
    if username:
        return username
    if auth:
        # Fall back to auth mode (e.g., token) if username missing
        return auth.get("mode", "authenticated")
    return "anonymous"


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
    table.add_column("Title (ID)", overflow="fold", style="bold")
    table.add_column("State", style="yellow", width=12)
    table.add_column("Modified", style="dim", width=20)
    for item in items:
        # Extract title - try multiple field names
        title = item.get("title") or item.get("Title") or item.get("name") or "—"
        # Extract ID - try id field first, then extract from @id URL, then try other fields
        item_id = item.get("id") or item.get("Id") or item.get("UID")
        if not item_id:
            # Extract from @id URL (e.g., "https://site.com/++api++/folder/item" -> "item")
            item_url = item.get("@id", "")
            if item_url:
                item_id = item_url.rstrip("/").split("/")[-1] or ""
        item_id = item_id or "—"
        # Extract type
        item_type = item.get("@type", item.get("type_title", "—"))
        # Combine title, ID, and type with color distinction: title in bold, ID in dim, type in cyan
        title_with_id_type = f"[bold]{title}[/bold] [dim]({item_id})[/dim] [cyan][{item_type}][/cyan]"
        state = item.get("review_state", "—")
        modified = item.get("modified", item.get("effective", "—"))
        if modified and modified != "—":
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(modified.replace("Z", "+00:00"))
                modified = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, AttributeError):
                pass
        table.add_row(title_with_id_type, state, modified)
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
    yes: bool = typer.Option(False, "-y", "--yes", help="Automatically answer 'yes' to all confirmation prompts."),
) -> None:
    """Launch interactive shell with filesystem-like navigation."""
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise CliError("The REPL requires an interactive terminal. Run this command directly in a shell.")
    resolved_base = get_base_url(base)
    current_path = ""
    
    # Helper function for confirmations that respects -y flag
    def confirm_prompt(message: str) -> bool:
        """Show confirmation prompt, respecting -y flag."""
        if yes:
            return True
        return typer.confirm(message, default=True)
    
    # Load history - ensure directory exists
    history = None
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        history = FileHistory(str(HISTORY_FILE))
    except Exception:
        history = None
    
    COMMANDS = ["ls", "cd", "pwd", "get", "items", "raw", "components", "tags", "similar-tags", "merge-tags", "rename-tag", "remove-tag", "search", "blocks", "show-block", "delete-block", "move-block", "move-block-up", "rename", "set-id", "mv", "cp", "connect", "login", "logout", "help", "exit", "quit"]

    class ReplCompleter(Completer):
        _tag_cache: Optional[List[str]] = None
        _tag_cache_path: str = ""
        
        def _item_suggestions(self, path_prefix: str = "") -> List[str]:
            """Get item suggestions from a specific path.
            
            Args:
                path_prefix: Optional path to fetch items from (e.g., "files/mystuff")
                            If empty, uses current_path
            """
            results: List[str] = []
            try:
                # Determine which path to fetch from
                if path_prefix:
                    # For deep paths, resolve relative to current_path
                    if path_prefix.startswith("/"):
                        # Absolute path - use as-is (remove leading slash)
                        fetch_path = path_prefix.lstrip("/")
                    else:
                        # Relative path - combine with current_path
                        if current_path:
                            # Combine: current_path + path_prefix
                            fetch_path = f"{current_path}/{path_prefix}".strip("/")
                        else:
                            # No current_path, use path_prefix as-is
                            fetch_path = path_prefix
                else:
                    fetch_path = current_path
                
                _, data = fetch(fetch_path, resolved_base, {}, {}, no_auth=False)
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
            
            # Helper function to handle path autocompletion
            def handle_path_completion(cmd_name: str, required_args_before_path: int = 0):
                """Handle path autocompletion for commands that take an optional path argument.
                
                Args:
                    cmd_name: The command name
                    required_args_before_path: Number of required arguments before the optional path
                """
                if len(parts) > required_args_before_path:
                    # Extract the path argument from the text
                    arg_start = text.find(cmd_name, 0) + len(cmd_name)
                    if arg_start < len(text):
                        # Skip required arguments to get to the path
                        path_text = text[arg_start:].lstrip()
                        # Skip required arguments (they're already typed)
                        for _ in range(required_args_before_path):
                            if " " in path_text:
                                path_text = path_text.split(" ", 1)[1].lstrip()
                        
                        if path_text:  # Only autocomplete if there's something to complete
                            # Handle deep paths: if path contains "/", extract directory and prefix
                            if "/" in path_text:
                                # Split path: "files/mystuff/here" -> dir="files/mystuff", prefix="here"
                                path_parts = path_text.rsplit("/", 1)
                                if len(path_parts) == 2:
                                    dir_path, prefix = path_parts
                                    suggestions = self._item_suggestions(dir_path)
                                    # Only suggest items that start with the prefix
                                    for suggestion in suggestions:
                                        if suggestion.startswith(prefix):
                                            # Return the full path including the directory
                                            full_suggestion = f"{dir_path}/{suggestion}"
                                            yield Completion(full_suggestion, start_position=-len(path_text))
                                else:
                                    # Just a trailing slash, suggest from the directory
                                    dir_path = path_text.rstrip("/")
                                    suggestions = self._item_suggestions(dir_path)
                                    for suggestion in suggestions:
                                        full_suggestion = f"{dir_path}/{suggestion}"
                                        yield Completion(full_suggestion, start_position=-len(path_text))
                            else:
                                # Simple case: no slashes, just suggest from current directory
                                suggestions = self._item_suggestions()
                                prefix = path_text if not has_trailing_space else ""
                                for suggestion in suggestions:
                                    if suggestion.startswith(prefix):
                                        yield Completion(suggestion, start_position=-len(path_text))
                elif len(parts) == required_args_before_path:
                    # All required args provided, suggest paths from current directory
                    suggestions = self._item_suggestions()
                    for suggestion in suggestions:
                        yield Completion(suggestion, start_position=0)
            
            # Item suggestions for navigation/content commands
            if cmd in ("cd", "get", "items", "raw"):
                # Get the full path argument being typed (not just the last word)
                # For "cd files/mystuff/here", we want "files/mystuff/here"
                if len(parts) > 1:
                    # Reconstruct the path argument from parts[1:] to handle quoted paths
                    # But for autocomplete, we need the raw text before cursor
                    # Extract the path argument from the text
                    cmd_end = len(cmd)
                    # Find where the command ends and the argument starts
                    arg_start = text.find(cmd, 0) + len(cmd)
                    if arg_start < len(text):
                        path_text = text[arg_start:].lstrip()
                        # Handle deep paths: if path contains "/", extract directory and prefix
                        if "/" in path_text:
                            # Split path: "files/mystuff/here" -> dir="files/mystuff", prefix="here"
                            path_parts = path_text.rsplit("/", 1)
                            if len(path_parts) == 2:
                                dir_path, prefix = path_parts
                                suggestions = self._item_suggestions(dir_path)
                                # Only suggest items that start with the prefix
                                for suggestion in suggestions:
                                    if suggestion.startswith(prefix):
                                        # Return the full path including the directory
                                        full_suggestion = f"{dir_path}/{suggestion}"
                                        yield Completion(full_suggestion, start_position=-len(path_text))
                            else:
                                # Just a trailing slash, suggest from the directory
                                dir_path = path_text.rstrip("/")
                                suggestions = self._item_suggestions(dir_path)
                                for suggestion in suggestions:
                                    full_suggestion = f"{dir_path}/{suggestion}"
                                    yield Completion(full_suggestion, start_position=-len(path_text))
                        else:
                            # Simple case: no slashes, just suggest from current directory
                            suggestions = self._item_suggestions()
                            prefix = path_text if not has_trailing_space else ""
                            for suggestion in suggestions:
                                if suggestion.startswith(prefix):
                                    yield Completion(suggestion, start_position=-len(path_text))
                else:
                    # No argument yet, suggest from current directory
                    suggestions = self._item_suggestions()
                    for suggestion in suggestions:
                        yield Completion(suggestion, start_position=0)
            
            # Block commands with optional path argument
            elif cmd == "blocks":
                # blocks [path] - path is optional, last argument
                yield from handle_path_completion("blocks", 0)
            
            elif cmd == "show-block":
                # show-block <id> [path] - path is optional, comes after block ID
                if len(parts) > 1:
                    # We have at least the block ID, check if we're typing a path
                    if len(parts) > 2 or (len(parts) == 2 and has_trailing_space):
                        # We have a path argument (or space after block ID)
                        yield from handle_path_completion("show-block", 1)
            
            elif cmd == "delete-block":
                # delete-block <id> [path] - path is optional, comes after block ID
                if len(parts) > 1:
                    # We have at least the block ID, check if we're typing a path
                    if len(parts) > 2 or (len(parts) == 2 and has_trailing_space):
                        # We have a path argument (or space after block ID)
                        yield from handle_path_completion("delete-block", 1)
            
            elif cmd == "move-block":
                # move-block <id> <direction> [path] - path is optional, comes after direction
                # Special case: if direction is "to", path comes after position number
                if len(parts) > 2:
                    # We have block ID and direction, check if we're typing a path
                    direction = parts[2].lower() if len(parts) > 2 else ""
                    if direction == "to" and len(parts) > 3:
                        # move-block <id> to <pos> [path] - path comes after position
                        if len(parts) > 4 or (len(parts) == 4 and has_trailing_space):
                            yield from handle_path_completion("move-block", 3)
                    elif direction != "to":
                        # move-block <id> <up|down> [path] - path comes after direction
                        if len(parts) > 3 or (len(parts) == 3 and has_trailing_space):
                            yield from handle_path_completion("move-block", 2)
            
            elif cmd == "rename":
                # rename <new_title> [path] - path is optional, comes after new title
                if len(parts) > 1:
                    # We have at least the new title, check if we're typing a path
                    if len(parts) > 2 or (len(parts) == 2 and has_trailing_space):
                        # We have a path argument (or space after new title)
                        yield from handle_path_completion("rename", 1)
            
            elif cmd == "set-id":
                # set-id <new_id> [path] - path is optional, comes after new id
                if len(parts) > 1:
                    # We have at least the new id, check if we're typing a path
                    if len(parts) > 2 or (len(parts) == 2 and has_trailing_space):
                        # We have a path argument (or space after new id)
                        yield from handle_path_completion("set-id", 1)
            
            elif cmd == "mv":
                # mv <source> <dest> - both are paths
                if len(parts) > 1:
                    # First arg is source, suggest paths
                    if len(parts) == 2:
                        # Typing source path
                        yield from handle_path_completion("mv", 0)
                    elif len(parts) > 2:
                        # Have source, typing destination
                        # Extract destination path from text
                        arg_start = text.find("mv", 0) + len("mv")
                        if arg_start < len(text):
                            path_text = text[arg_start:].lstrip()
                            # Skip source argument
                            if " " in path_text:
                                dest_text = path_text.split(" ", 1)[1].lstrip()
                                if dest_text:
                                    # Handle path completion for destination
                                    if "/" in dest_text:
                                        path_parts = dest_text.rsplit("/", 1)
                                        if len(path_parts) == 2:
                                            dir_path, prefix = path_parts
                                            suggestions = self._item_suggestions(dir_path)
                                            for suggestion in suggestions:
                                                if suggestion.startswith(prefix):
                                                    full_suggestion = f"{dir_path}/{suggestion}"
                                                    yield Completion(full_suggestion, start_position=-len(dest_text))
                                    else:
                                        suggestions = self._item_suggestions()
                                        prefix = dest_text if not has_trailing_space else ""
                                        for suggestion in suggestions:
                                            if suggestion.startswith(prefix):
                                                yield Completion(suggestion, start_position=-len(dest_text))
            
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
            status = get_auth_status()
            prompt_label = f"plone ({status})> "
            text = prompt(
                prompt_label,
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
                CONSOLE.print("  [cyan]search <type> [--path <path>][/cyan] - Search for items by object type")
                CONSOLE.print("    Example: search Document (finds all Document items)")
                CONSOLE.print("    Example: search Folder --path /some/path (finds Folders in specific path)")
                CONSOLE.print("\n[bold]Blocks (Plone 6):[/bold]")
                CONSOLE.print("  [cyan]blocks [path][/cyan]        - List all blocks in an item")
                CONSOLE.print("  [cyan]show-block <id|partial> [path][/cyan] - Show details of a specific block")
                CONSOLE.print("  [cyan]delete-block <id|partial> [path][/cyan] - Delete a block from an item")
                CONSOLE.print("  [cyan]move-block <id|partial> <up|down|to <pos>> [path][/cyan] - Move a block")
                CONSOLE.print("    Examples: move-block abc123 up")
                CONSOLE.print("              move-block abc up my-item (partial ID with path)")
                CONSOLE.print("              move-block abc123 down")
                CONSOLE.print("              move-block abc123 to 0 (move to first position)")
                CONSOLE.print("              move-block abc to 0 my-item (partial ID, position, path)")
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
                CONSOLE.print("  [cyan]rename <new_title> [path][/cyan] - Rename item title")
                CONSOLE.print("  [cyan]set-id <new_id> [path][/cyan] - Change item id (shortname/objectname)")
                CONSOLE.print("  [cyan]mv <source> <dest>[/cyan] - Move item to new location (optionally rename)")
                CONSOLE.print("    Examples: rename 'New Title'")
                CONSOLE.print("              rename 'New Title' my-item")
                CONSOLE.print("              set-id new-id")
                CONSOLE.print("              set-id new-id my-item")
                CONSOLE.print("              mv my-item new-folder")
                CONSOLE.print("              mv my-item new-folder/new-name (move and rename)")
                CONSOLE.print("  [cyan]cp <source> <dest>[/cyan] - Copy item")
                CONSOLE.print("\n[bold]Workflow:[/bold]")
                CONSOLE.print("  [cyan]transitions[/cyan]     - List available workflow transitions")
                CONSOLE.print("  [cyan]transition <name>[/cyan] - Execute a workflow transition")
                CONSOLE.print("  [cyan]bulk-transition <name>[/cyan] - Execute transition on all items in current directory")
                CONSOLE.print("\n[bold]Other:[/bold]")
                CONSOLE.print("  [cyan]components[/cyan]      - List available components")
                CONSOLE.print("  [cyan]connect <site>[/cyan]  - Change base URL (accepts bare host, adds scheme/++api++ automatically)")
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
                            
                            if confirm_prompt(confirm_msg):
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
                            if confirm_prompt(f"Rename tag '{old_tag}' to '{new_tag}' on {len(items)} item(s)?"):
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
                                            
                                            # Small delay to allow server to process the update before verification
                                            import time
                                            time.sleep(0.1)  # 100ms delay
                                            
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
            elif cmd == "search":
                if not args:
                    CONSOLE.print("[red]Error:[/red] search requires an object type (portal_type)")
                    CONSOLE.print("  Example: search Document (searches for all Document items)")
                    CONSOLE.print("  Example: search Folder --path /some/path (searches in specific path)")
                else:
                    portal_type = args[0]
                    # Parse path option if provided
                    search_path = current_path
                    if "--path" in args:
                        idx = args.index("--path")
                        if idx + 1 < len(args):
                            search_path = args[idx + 1]
                    try:
                        items = api.search_by_type(resolved_base, portal_type, search_path, no_auth=False)
                        if not items:
                            CONSOLE.print(f"[yellow]No items found with type '{portal_type}'.[/yellow]")
                        else:
                            CONSOLE.print(f"[cyan]Found {len(items)} item(s) with type '{portal_type}'[/cyan]")
                            print_items_with_metadata(items)
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
                            if confirm_prompt(f"Remove tag '{tag}' from {len(items)} item(s)?"):
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
            elif cmd == "rename":
                if not args:
                    CONSOLE.print("[red]Error:[/red] rename requires a new title")
                    CONSOLE.print("  Example: rename 'New Title'")
                    CONSOLE.print("  Example: rename 'New Title' my-item (rename specific item)")
                else:
                    new_title = args[0]
                    path = args[1] if len(args) > 1 else current_path
                    
                    if not path:
                        CONSOLE.print("[red]Error:[/red] No item specified. Use 'cd' to navigate to an item or provide a path.")
                        CONSOLE.print("  Example: rename 'New Title' my-item")
                    else:
                        try:
                            # Fetch current item to get current title
                            _, data = fetch(path, resolved_base, {}, {}, no_auth=False)
                            current_title = data.get("title", data.get("id", "unknown"))
                            
                            if confirm_prompt(f"Rename title from '{current_title}' to '{new_title}'?"):
                                # Update the title using PATCH
                                api.patch(path, resolved_base, {"title": new_title}, {}, no_auth=False)
                                CONSOLE.print(f"[green]Renamed title to '{new_title}'[/green]")
                        except Exception as e:
                            CONSOLE.print(f"[red]Error:[/red] {e}")
            elif cmd == "set-id":
                if not args:
                    CONSOLE.print("[red]Error:[/red] set-id requires a new id")
                    CONSOLE.print("  Example: set-id new-id")
                    CONSOLE.print("  Example: set-id new-id my-item (set id for specific item)")
                else:
                    new_id = args[0]
                    path = args[1] if len(args) > 1 else current_path
                    
                    if not path:
                        CONSOLE.print("[red]Error:[/red] No item specified. Use 'cd' to navigate to an item or provide a path.")
                        CONSOLE.print("  Example: set-id new-id my-item")
                    else:
                        try:
                            # Fetch current item to get current id
                            _, data = fetch(path, resolved_base, {}, {}, no_auth=False)
                            current_id = data.get("id", "unknown")
                            
                            if confirm_prompt(f"Change id from '{current_id}' to '{new_id}'?"):
                                # Update the id using PATCH
                                api.patch(path, resolved_base, {"id": new_id}, {}, no_auth=False)
                                CONSOLE.print(f"[green]Changed id to '{new_id}'[/green]")
                        except (CliError, api.APIError) as e:
                            error_msg = str(e)
                            # Check for 404 errors - CliError wraps the APIError message
                            if "404" in error_msg:
                                CONSOLE.print(f"[red]Error:[/red] Item at path '{path}' not found")
                                CONSOLE.print(f"[yellow]Syntax:[/yellow] set-id <new_id> <path>")
                                CONSOLE.print(f"[yellow]Hint:[/yellow] The path '{path}' doesn't exist. Use 'cd' to navigate to the item first, or check the path is correct")
                                CONSOLE.print(f"[yellow]Example:[/yellow] cd my-item (then) set-id new-id")
                                CONSOLE.print(f"[yellow]Example:[/yellow] set-id new-id correct/path/to/item")
                                # Don't print the raw error message for 404s since we've explained it
                            else:
                                CONSOLE.print(f"[red]Error:[/red] {e}")
                        except Exception as e:
                            CONSOLE.print(f"[red]Error:[/red] {e}")
            elif cmd == "mv":
                if len(args) < 2:
                    CONSOLE.print("[red]Error:[/red] mv requires a source and destination")
                    CONSOLE.print("  Example: mv my-item new-folder")
                    CONSOLE.print("  Example: mv my-item new-folder/new-name (move and rename)")
                    CONSOLE.print("  Example: mv folder/item new-folder")
                else:
                    source_path = args[0]
                    dest_path = args[1]
                    
                    try:
                        # Fetch source to get current info
                        _, source_data = fetch(source_path, resolved_base, {}, {}, no_auth=False)
                        source_title = source_data.get("title", source_data.get("id", "unknown"))
                        source_id = source_data.get("id", "unknown")
                        
                        # Check if destination includes a new name
                        new_id = None
                        dest_parts = dest_path.rstrip("/").split("/")
                        if len(dest_parts) > 1 and not dest_path.endswith("/"):
                            # Last part is the new name
                            new_id = dest_parts[-1]
                            dest_folder = "/".join(dest_parts[:-1])
                        else:
                            dest_folder = dest_path
                        
                        # Fetch destination to verify it exists and is a folder
                        try:
                            _, dest_data = fetch(dest_folder, resolved_base, {}, {}, no_auth=False)
                            dest_title = dest_data.get("title", dest_data.get("id", dest_folder))
                        except Exception:
                            CONSOLE.print(f"[red]Error:[/red] Destination '{dest_folder}' not found or not accessible")
                            continue
                        
                        # Build confirmation message
                        move_msg = f"Move '{source_title}' ({source_id}) to '{dest_title}'"
                        if new_id:
                            move_msg += f" as '{new_id}'"
                        move_msg += "?"
                        
                        if confirm_prompt(move_msg):
                            # Perform the move
                            api.move_item(resolved_base, source_path, dest_folder, new_id, no_auth=False)
                            result_msg = f"Moved '{source_title}' to '{dest_title}'"
                            if new_id:
                                result_msg += f" as '{new_id}'"
                            CONSOLE.print(f"[green]{result_msg}[/green]")
                    except api.APIError as e:
                        CONSOLE.print(f"[red]Error:[/red] {e}")
                    except Exception as e:
                        CONSOLE.print(f"[red]Error:[/red] {e}")
            elif cmd in ("connect", "set-base"):
                if not args:
                    CONSOLE.print(f"Current base URL: [cyan]{resolved_base}[/cyan]")
                    continue
                target = args[0]
                try:
                    normalized = api.normalize_base_input(target)
                    CONSOLE.print(f"[dim]Checking {normalized}...[/dim]")
                    api.verify_base_url(normalized)
                except api.APIError as e:
                    CONSOLE.print(f"[red]Error:[/red] {e}")
                    continue
                config = api.load_config() or {}
                persisted_base = normalized.rstrip("/")
                config["base"] = persisted_base
                if "auth" in config:
                    config.pop("auth")
                    CONSOLE.print("[yellow]Cleared saved credentials for the previous site. Run 'login' to authenticate again.[/yellow]")
                api.save_config(config)
                resolved_base = persisted_base
                current_path = ""
                completer._tag_cache = None
                completer._tag_cache_path = ""
                CONSOLE.print(f"[green]Base URL updated to {normalized}[/green]")
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
            elif cmd == "blocks":
                path = args[0] if args else current_path
                try:
                    _, data = fetch(path, resolved_base, {}, {}, no_auth=False)
                    blocks = data.get("blocks", {})
                    blocks_layout = data.get("blocks_layout", {})
                    
                    if not blocks:
                        CONSOLE.print("[dim]No blocks found in this item[/dim]")
                    else:
                        # Get the order from blocks_layout
                        layout_items = []
                        if isinstance(blocks_layout, dict) and "items" in blocks_layout:
                            layout_items = blocks_layout["items"]
                        elif isinstance(blocks_layout, list):
                            layout_items = blocks_layout
                        
                        table = Table(title="Blocks", box=box.MINIMAL_DOUBLE_HEAD)
                        table.add_column("#", style="dim", width=4)
                        table.add_column("ID", style="bold")
                        table.add_column("Type", style="cyan")
                        table.add_column("Preview", overflow="fold")
                        
                        for idx, block_id in enumerate(layout_items):
                            if block_id in blocks:
                                block = blocks[block_id]
                                block_type = block.get("@type", "unknown")
                                # Try to get a preview
                                preview = "—"
                                if "text" in block:
                                    preview = block["text"].get("plain", {}).get("plain", "")[:50] if isinstance(block["text"], dict) else str(block["text"])[:50]
                                elif "title" in block:
                                    preview = str(block["title"])[:50]
                                else:
                                    preview = str(block)[:50] + "..." if len(str(block)) > 50 else str(block)
                                table.add_row(str(idx + 1), block_id, block_type, preview)
                        
                        CONSOLE.print(table)
                except Exception as e:
                    CONSOLE.print(f"[red]Error:[/red] {e}")
            elif cmd == "show-block":
                if not args:
                    CONSOLE.print("[red]Error:[/red] show-block requires a block ID (or partial ID)")
                    CONSOLE.print("  Example: show-block abc123")
                    CONSOLE.print("  Example: show-block abc my-item (with path)")
                else:
                    partial_id = args[0]
                    path = args[1] if len(args) > 1 else current_path
                    try:
                        _, data = fetch(path, resolved_base, {}, {}, no_auth=False)
                        blocks = data.get("blocks", {})
                        
                        # Find block by partial ID
                        matching_blocks = [bid for bid in blocks.keys() if bid.startswith(partial_id)]
                        
                        if not matching_blocks:
                            CONSOLE.print(f"[yellow]No block found matching '{partial_id}'[/yellow]")
                        elif len(matching_blocks) > 1:
                            CONSOLE.print(f"[yellow]Multiple blocks match '{partial_id}':[/yellow]")
                            for bid in matching_blocks:
                                block_type = blocks[bid].get("@type", "unknown")
                                CONSOLE.print(f"  - {bid} ({block_type})")
                            CONSOLE.print(f"[yellow]Please use a more specific block ID[/yellow]")
                        else:
                            block_id = matching_blocks[0]
                            block = blocks[block_id]
                            CONSOLE.print(f"[green]Block:[/green] {block_id}")
                            CONSOLE.print(JSON(json.dumps(block, indent=2)))
                    except Exception as e:
                        CONSOLE.print(f"[red]Error:[/red] {e}")
            elif cmd == "delete-block":
                if not args:
                    CONSOLE.print("[red]Error:[/red] delete-block requires a block ID (or partial ID) or index")
                    CONSOLE.print("  Example: delete-block abc123")
                    CONSOLE.print("  Example: delete-block 3 (delete block at position 3, 1-based)")
                    CONSOLE.print("  Example: delete-block abc my-item (with path)")
                else:
                    identifier = args[0]
                    path = args[1] if len(args) > 1 else current_path
                    try:
                        _, data = fetch(path, resolved_base, {}, {}, no_auth=False)
                        blocks = data.get("blocks", {})
                        blocks_layout = data.get("blocks_layout", {})
                        
                        # Get layout items
                        layout_items = []
                        if isinstance(blocks_layout, dict) and "items" in blocks_layout:
                            layout_items = blocks_layout["items"].copy()
                        elif isinstance(blocks_layout, list):
                            layout_items = blocks_layout.copy()
                        
                        # Check if identifier is a number (index)
                        block_id = None
                        if identifier.isdigit():
                            # It's an index (1-based)
                            index = int(identifier) - 1  # Convert to 0-based
                            if index < 0 or index >= len(layout_items):
                                CONSOLE.print(f"[red]Error:[/red] Index must be between 1 and {len(layout_items)}")
                                continue
                            block_id = layout_items[index]
                        else:
                            # It's a partial ID - find block by partial ID
                            partial_id = identifier
                            matching_blocks = [bid for bid in blocks.keys() if bid.startswith(partial_id)]
                            
                            if not matching_blocks:
                                CONSOLE.print(f"[yellow]No block found matching '{partial_id}'[/yellow]")
                                continue
                            elif len(matching_blocks) > 1:
                                CONSOLE.print(f"[yellow]Multiple blocks match '{partial_id}':[/yellow]")
                                for bid in matching_blocks:
                                    block_type = blocks[bid].get("@type", "unknown")
                                    CONSOLE.print(f"  - {bid} ({block_type})")
                                CONSOLE.print(f"[yellow]Please use a more specific block ID or use index[/yellow]")
                                continue
                            else:
                                block_id = matching_blocks[0]
                        
                        if block_id:
                            # Get block type for confirmation message
                            block_type = blocks.get(block_id, {}).get("@type", "unknown")
                            if confirm_prompt(f"Delete block '{block_id}' ({block_type})?"):
                                # Remove from blocks dict
                                new_blocks = {k: v for k, v in blocks.items() if k != block_id}
                                
                                # Remove from blocks_layout
                                if isinstance(blocks_layout, dict) and "items" in blocks_layout:
                                    new_layout = {"items": [bid for bid in blocks_layout["items"] if bid != block_id]}
                                elif isinstance(blocks_layout, list):
                                    new_layout = [bid for bid in blocks_layout if bid != block_id]
                                else:
                                    new_layout = {"items": []}
                                
                                # Update the item
                                api.patch(path, resolved_base, {"blocks": new_blocks, "blocks_layout": new_layout}, {}, no_auth=False)
                                CONSOLE.print(f"[green]Deleted block '{block_id}'[/green]")
                    except Exception as e:
                        CONSOLE.print(f"[red]Error:[/red] {e}")
            elif cmd in ("move-block", "move-block-up"):
                if len(args) < 1:
                    CONSOLE.print("[red]Error:[/red] move-block requires a block ID (or partial ID), index, or direction")
                    CONSOLE.print("  Examples: move-block abc123 up")
                    CONSOLE.print("            move-block 3 up (move block at position 3 up, 1-based)")
                    CONSOLE.print("            move-block abc123 down")
                    CONSOLE.print("            move-block abc123 to 0")
                    CONSOLE.print("            move-block abc up my-item (with path)")
                    CONSOLE.print("            move-block-up 3 (move block at position 3 up, 1-based)")
                else:
                    # Check if this is the move-block-up shortcut
                    if cmd == "move-block-up":
                        # Format: move-block-up <index> [path]
                        if not args[0].isdigit():
                            CONSOLE.print("[red]Error:[/red] move-block-up requires a numeric index (1-based)")
                            continue
                        identifier = args[0]
                        direction = "up"
                        path = args[1] if len(args) > 1 else current_path
                    else:
                        # Regular move-block command
                        identifier = args[0]
                        direction = args[1].lower() if len(args) > 1 else None
                        
                        # Parse arguments: determine if last arg is a path
                        # Format: move-block <id|index> <direction> [path]
                        # Format: move-block <id|index> to <pos> [path]
                        path = current_path
                        if direction == "to":
                            # move-block <id|index> to <pos> [path]
                            if len(args) > 3:
                                # Last arg is path
                                path = args[3]
                            elif len(args) == 3:
                                # No path provided, use current_path
                                pass
                        else:
                            # move-block <id|index> <up|down> [path]
                            if len(args) > 2:
                                # Last arg is path
                                path = args[2]
                    
                    if not direction:
                        CONSOLE.print("[red]Error:[/red] Direction required: 'up', 'down', or 'to <position>'")
                        continue
                    
                    try:
                        _, data = fetch(path, resolved_base, {}, {}, no_auth=False)
                        blocks = data.get("blocks", {})
                        blocks_layout = data.get("blocks_layout", {})
                        
                        # Get layout items
                        layout_items = []
                        if isinstance(blocks_layout, dict) and "items" in blocks_layout:
                            layout_items = blocks_layout["items"].copy()
                        elif isinstance(blocks_layout, list):
                            layout_items = blocks_layout.copy()
                        
                        # Check if identifier is a number (index)
                        block_id = None
                        current_index = None
                        if identifier.isdigit():
                            # It's an index (1-based)
                            current_index = int(identifier) - 1  # Convert to 0-based
                            if current_index < 0 or current_index >= len(layout_items):
                                CONSOLE.print(f"[red]Error:[/red] Index must be between 1 and {len(layout_items)}")
                                continue
                            block_id = layout_items[current_index]
                        else:
                            # It's a partial ID - find block by partial ID
                            partial_id = identifier
                            matching_blocks = [bid for bid in blocks.keys() if bid.startswith(partial_id)]
                            
                            if not matching_blocks:
                                CONSOLE.print(f"[yellow]No block found matching '{partial_id}'[/yellow]")
                                continue
                            elif len(matching_blocks) > 1:
                                CONSOLE.print(f"[yellow]Multiple blocks match '{partial_id}':[/yellow]")
                                for bid in matching_blocks:
                                    block_type = blocks[bid].get("@type", "unknown")
                                    CONSOLE.print(f"  - {bid} ({block_type})")
                                CONSOLE.print(f"[yellow]Please use a more specific block ID or use index[/yellow]")
                                continue
                            else:
                                block_id = matching_blocks[0]
                                if block_id not in layout_items:
                                    CONSOLE.print(f"[yellow]Block '{block_id}' not found in layout[/yellow]")
                                    continue
                                current_index = layout_items.index(block_id)
                        
                        if block_id and current_index is not None:
                            if direction == "up":
                                if current_index == 0:
                                    CONSOLE.print("[yellow]Block is already at the top[/yellow]")
                                    continue
                                else:
                                    new_index = current_index - 1
                                    direction_desc = "up"
                            elif direction == "down":
                                if current_index == len(layout_items) - 1:
                                    CONSOLE.print("[yellow]Block is already at the bottom[/yellow]")
                                    continue
                                else:
                                    new_index = current_index + 1
                                    direction_desc = "down"
                            elif direction == "to" and len(args) > 2:
                                try:
                                    new_index = int(args[2])
                                    if new_index < 0 or new_index >= len(layout_items):
                                        CONSOLE.print(f"[red]Error:[/red] Position must be between 0 and {len(layout_items) - 1}")
                                        continue
                                    direction_desc = f"to position {new_index + 1}"
                                except ValueError:
                                    CONSOLE.print("[red]Error:[/red] Position must be a number")
                                    continue
                            else:
                                CONSOLE.print("[red]Error:[/red] Direction must be 'up', 'down', or 'to <position>'")
                                continue
                            
                            # Get block type for confirmation message
                            block_type = blocks.get(block_id, {}).get("@type", "unknown")
                            if confirm_prompt(f"Move block '{block_id}' ({block_type}) {direction_desc}?"):
                                # Move the block
                                layout_items.pop(current_index)
                                layout_items.insert(new_index, block_id)
                                
                                # Update blocks_layout
                                if isinstance(blocks_layout, dict):
                                    new_layout = {"items": layout_items}
                                else:
                                    new_layout = layout_items
                                
                                # Update the item
                                api.patch(path, resolved_base, {"blocks_layout": new_layout}, {}, no_auth=False)
                                CONSOLE.print(f"[green]Moved block '{block_id}' to position {new_index + 1}[/green]")
                    except Exception as e:
                        CONSOLE.print(f"[red]Error:[/red] {e}")
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
            if not item_path:
                errors += 1
                CONSOLE.print(f"[yellow]Warning: Could not extract path from item '{item.get('title', 'unknown')}'[/yellow]")
                continue
            
            # Fetch current item to get actual subjects (more reliable than search result)
            try:
                _, current_item = api.fetch(item_path, resolved_base, {}, {}, no_auth)
                current_tags = (
                    current_item.get("Subject") or
                    current_item.get("subjects") or
                    current_item.get("subject") or
                    []
                )
                if isinstance(current_tags, str):
                    current_tags = [current_tags] if current_tags else []
                elif not isinstance(current_tags, list):
                    current_tags = list(current_tags) if current_tags else []
            except Exception as e:
                # Fallback to subjects from search result
                current_tags = item.get("subjects", [])
            
            # Remove all source tags, add target tag if not present
            new_tags = [tag for tag in current_tags if tag not in source_tags]
            if target_tag not in new_tags:
                new_tags.append(target_tag)
            
            # Only update if tags actually changed
            if set(current_tags) != set(new_tags):
                try:
                    api.update_item_subjects(resolved_base, item_path, new_tags, no_auth=no_auth)
                except api.APIError as update_error:
                    errors += 1
                    error_msg = str(update_error)
                    if "__getitem__" in error_msg or "500" in error_msg:
                        CONSOLE.print(f"[red]Server error updating '{item.get('title', 'unknown')}': {error_msg}[/red]")
                        CONSOLE.print(f"[yellow]This is a known issue with the Plone REST API on this server. The Subject field may not be updatable via REST API.[/yellow]")
                    else:
                        CONSOLE.print(f"[red]Error updating '{item.get('title', 'unknown')}': {error_msg}[/red]")
                    continue
                
                # Small delay to allow server to process the update before verification
                time.sleep(0.1)  # 100ms delay
                
                # Verify the update succeeded by fetching the item again
                try:
                    _, verify_item = api.fetch(item_path, resolved_base, {}, {}, no_auth)
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
                    
                    # Verify the update: source tags should be gone, target tag should be present
                    source_tags_still_present = any(tag in verify_tags for tag in source_tags)
                    target_tag_present = target_tag in verify_tags
                    
                    if source_tags_still_present:
                        if target_tag_present:
                            # Both present - update partially failed
                            source_list = ", ".join(f"'{tag}'" for tag in source_tags if tag in verify_tags)
                            CONSOLE.print(f"[yellow]Warning: Update failed for '{item.get('title', 'unknown')}'. Source tag(s) {source_list} still present, target tag '{target_tag}' also present. Update may have failed.[/yellow]")
                            errors += 1
                            continue
                        else:
                            # Source tags still there, target tag not added - update failed
                            source_list = ", ".join(f"'{tag}'" for tag in source_tags if tag in verify_tags)
                            CONSOLE.print(f"[yellow]Warning: Update failed for '{item.get('title', 'unknown')}'. Source tag(s) {source_list} still present, target tag '{target_tag}' not added.[/yellow]")
                            errors += 1
                            continue
                    elif not target_tag_present:
                        # Source tags removed but target tag not added - update failed
                        CONSOLE.print(f"[yellow]Warning: Update failed for '{item.get('title', 'unknown')}'. Source tags removed but target tag '{target_tag}' not added.[/yellow]")
                        errors += 1
                        continue
                    # Success: source tags removed, target tag present
                except Exception:
                    # Verification failed, but update was attempted
                    # Assume it worked if we can't verify
                    pass
                
                updated += 1
            else:
                # Tags didn't change (maybe source tags weren't in the list)
                if len(source_tags) == 1:
                    CONSOLE.print(f"[yellow]Warning: Tag '{source_tags[0]}' not found in item '{item.get('title', 'unknown')}', skipping[/yellow]")
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


@APP.command("search")
def cmd_search(
    portal_type: str = typer.Argument(..., help="Object type to search for (e.g., 'Document', 'Folder', 'News Item')."),
    path: str = typer.Option("", "--path", help="Limit search to items in this path."),
    base: Optional[str] = typer.Option(None, "--base", help="Override the API base URL."),
    no_auth: bool = typer.Option(False, "--no-auth", help="Skip saved auth headers."),
) -> None:
    """Search for items by object type (portal_type)."""
    resolved_base = get_base_url(base)
    try:
        items = api.search_by_type(resolved_base, portal_type, path, no_auth=no_auth)
        if not items:
            CONSOLE.print(f"[yellow]No items found with type '{portal_type}'.[/yellow]")
            return
        
        CONSOLE.print(f"[cyan]Found {len(items)} item(s) with type '{portal_type}'[/cyan]")
        print_items_with_metadata(items)
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

