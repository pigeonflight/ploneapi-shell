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

from ploneapi_shell import api

CONFIG_FILE = api.CONFIG_FILE
HISTORY_FILE = CONFIG_FILE.parent / "history.txt"

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
    
    COMMANDS = ["ls", "cd", "pwd", "get", "items", "raw", "components", "help", "exit", "quit"]

    class ReplCompleter(Completer):
        def _item_suggestions(self) -> List[str]:
            results: List[str] = []
            try:
                _, data = fetch(current_path, resolved_base, {}, {}, no_auth=False)
                items = data.get("items", [])
                for item in items:
                    item_id = item.get("@id", "")
                    if not item_id:
                        continue
                    rel = item_id.replace(resolved_base, "").lstrip("/")
                    if rel:
                        results.append(rel)
                    item_name = item.get("id")
                    if item_name and item_name not in results:
                        results.append(item_name)
            except Exception:
                pass
            return results

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
            if cmd in ("cd", "get", "items", "raw"):
                suggestions = self._item_suggestions()
                prefix = last_word if not has_trailing_space else ""
                for suggestion in suggestions:
                    if suggestion.startswith(prefix):
                        yield Completion(suggestion, start_position=-len(prefix))
    
    completer = ReplCompleter()
    
    CONSOLE.print("[bold green]Plone API Shell[/bold green]")
    CONSOLE.print(f"Base URL: [cyan]{resolved_base}[/cyan]")
    CONSOLE.print("Type 'help' for commands, 'exit' to quit.\n")
    
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
                CONSOLE.print("  [cyan]help[/cyan]            - Show this help")
                CONSOLE.print("  [cyan]exit[/cyan]            - Exit shell\n")
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
                    target = args[0].lstrip("/")
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
            else:
                CONSOLE.print(f"[red]Unknown command:[/red] {cmd}. Type 'help' for available commands.")
        except KeyboardInterrupt:
            CONSOLE.print("\n[yellow]Use 'exit' to quit[/yellow]")
        except EOFError:
            break
    
    CONSOLE.print("\n[dim]Goodbye![/dim]")


@APP.callback()
def main(ctx: typer.Context):
    """Default entrypoint: start REPL when no subcommand is provided."""
    if ctx.invoked_subcommand is None:
        cmd_repl()


@APP.command("logout")
def cmd_logout() -> None:
    if CONFIG_FILE.exists():
        delete_config()
        CONSOLE.print(f"[yellow]Removed saved credentials at {CONFIG_FILE}[/yellow]")
    else:
        CONSOLE.print("No saved credentials found.")


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

