#!/usr/bin/env python3
"""
Plone API Shell - Interactive explorer for Plone REST API sites.

Most modern Plone 6.x sites expose their REST API at siteroot/++api++
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
import posixpath
import shlex
from urllib.parse import urljoin

import httpx
import typer
from rich import box
from rich.console import Console
from rich.json import JSON
from rich.table import Table

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory

CONFIG_ENV = os.environ.get("PLONEAPI_SHELL_CONFIG")
CONFIG_FILE = Path(CONFIG_ENV).expanduser() if CONFIG_ENV else Path.home() / ".config" / "ploneapi_shell" / "config.json"
HISTORY_FILE = CONFIG_FILE.parent / "history.txt"

APP = typer.Typer(help="Interactive shell and CLI for exploring Plone REST API sites.")
CONSOLE = Console()
DEFAULT_BASE = "https://www.asaj.com.jm/++api++/"


class CliError(typer.Exit):
    """Wrap Typer exit with message."""

    def __init__(self, message: str, code: int = 1) -> None:
        CONSOLE.print(f"[red]Error:[/red] {message}")
        super().__init__(code)


def resolve_url(path_or_url: str | None, base: str) -> str:
    if not path_or_url:
        return base
    if path_or_url.startswith(("http://", "https://")):
        return path_or_url
    path = path_or_url.lstrip("/")
    return urljoin(base, path)


def parse_key_values(entries: Iterable[str]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for raw in entries:
        if ":" not in raw:
            raise CliError(f"Invalid key/value pair '{raw}'. Use key:value syntax.")
        key, value = raw.split(":", 1)
        result[key.strip()] = value.strip()
    return result


def load_config() -> Optional[Dict[str, Any]]:
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        CONSOLE.print(f"[yellow]Warning:[/yellow] Could not parse {CONFIG_FILE}, ignoring.")
        return None


def save_config(data: Dict[str, Any]) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_FILE.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
    if os.name == "posix":
        os.chmod(CONFIG_FILE, 0o600)


def delete_config() -> None:
    try:
        CONFIG_FILE.unlink()
    except FileNotFoundError:
        return


def has_authorization_header(headers: Dict[str, str]) -> bool:
    return any(key.lower() == "authorization" for key in headers)


def get_saved_base() -> Optional[str]:
    """Get saved base URL from config."""
    config = load_config()
    if not config:
        return None
    saved_base = config.get("base")
    return saved_base if saved_base else None


def get_base_url(provided: Optional[str] = None) -> str:
    """Get base URL from provided value, saved config, or default."""
    if provided:
        return provided
    saved = get_saved_base()
    return saved if saved else DEFAULT_BASE


def get_saved_auth_headers(base: str) -> Dict[str, str]:
    config = load_config()
    if not config:
        return {}
    saved_base = config.get("base")
    if not saved_base:
        return {}
    if saved_base.rstrip("/") != base.rstrip("/"):
        return {}
    auth = config.get("auth") or {}
    mode = auth.get("mode")
    if mode == "token" and auth.get("token"):
        return {"Authorization": f"Bearer {auth['token']}"}
    return {}


def apply_auth(headers: Dict[str, str], base: str, no_auth: bool) -> Dict[str, str]:
    merged = dict(headers)
    if no_auth or has_authorization_header(merged):
        return merged
    merged.update(get_saved_auth_headers(base))
    return merged


def fetch(
    path_or_url: str | None,
    base: str,
    headers: Dict[str, str],
    params: Dict[str, str],
    no_auth: bool = False,
) -> Tuple[str, Dict]:
    url = resolve_url(path_or_url, base)
    prepared_headers = apply_auth(headers, base, no_auth)
    try:
        response = httpx.get(
            url,
            headers=prepared_headers or None,
            params=params or None,
            timeout=15,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise CliError(f"Request failed with status {exc.response.status_code} for {url}") from exc
    except httpx.RequestError as exc:
        raise CliError(f"Unable to reach {url}: {exc}") from exc
    try:
        data = response.json()
    except ValueError as exc:
        raise CliError("Response is not JSON.") from exc
    return url, data


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
    login_url = resolve_url("@login", resolved_base)
    try:
        response = httpx.post(login_url, json={"login": username, "password": password}, timeout=15)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise CliError(f"Login failed with status {exc.response.status_code}.") from exc
    except httpx.RequestError as exc:
        raise CliError(f"Unable to reach {login_url}: {exc}") from exc
    payload = response.json()
    token = payload.get("token")
    if not token:
        raise CliError("Login response did not include a token.")
    save_config({"base": resolved_base.rstrip("/"), "auth": {"mode": "token", "token": token, "username": username}})
    CONSOLE.print(f"[green]Token saved to {CONFIG_FILE}[/green]")


@APP.command("logout")
def cmd_logout() -> None:
    if CONFIG_FILE.exists():
        delete_config()
        CONSOLE.print(f"[yellow]Removed saved credentials at {CONFIG_FILE}[/yellow]")
    else:
        CONSOLE.print("No saved credentials found.")


if __name__ == "__main__":
    APP()

