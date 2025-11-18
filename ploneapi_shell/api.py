"""
Shared API functions for Plone REST API interactions.
Used by both CLI and web interface.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import httpx

CONFIG_ENV = os.environ.get("PLONEAPI_SHELL_CONFIG")
CONFIG_FILE = Path(CONFIG_ENV).expanduser() if CONFIG_ENV else Path.home() / ".config" / "ploneapi_shell" / "config.json"
DEFAULT_BASE = "https://demo.plone.org/++api++/"


class APIError(Exception):
    """Base exception for API operations."""
    pass


def resolve_url(path_or_url: str | None, base: str) -> str:
    """Resolve a path or URL relative to base URL."""
    # Ensure base is a string (handle Typer Option objects)
    if not isinstance(base, str):
        base = get_base_url(None)
    if not path_or_url:
        return base
    if path_or_url.startswith(("http://", "https://")):
        return path_or_url
    path = path_or_url.lstrip("/")
    return urljoin(base, path)


def load_config() -> Optional[Dict[str, Any]]:
    """Load configuration from file."""
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None


def save_config(data: Dict[str, Any]) -> None:
    """Save configuration to file."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_FILE.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
    if os.name == "posix":
        os.chmod(CONFIG_FILE, 0o600)


def delete_config() -> None:
    """Delete configuration file."""
    try:
        CONFIG_FILE.unlink()
    except FileNotFoundError:
        pass


def get_saved_base() -> Optional[str]:
    """Get saved base URL from config."""
    config = load_config()
    if not config:
        return None
    saved_base = config.get("base")
    return saved_base if saved_base else None


def get_base_url(provided: Optional[str] = None) -> str:
    """Get base URL from provided value, saved config, or default."""
    # Handle case where Typer Option object might be passed instead of value
    if provided and not isinstance(provided, str):
        provided = None
    if provided:
        return provided
    saved = get_saved_base()
    if saved:
        return saved
    return DEFAULT_BASE


def get_saved_auth_headers(base: str) -> Dict[str, str]:
    """Get saved authentication headers for a base URL."""
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


def apply_auth(headers: Dict[str, str], base: str, no_auth: bool = False) -> Dict[str, str]:
    """Apply authentication headers if not already present."""
    merged = dict(headers)
    if no_auth or any(key.lower() == "authorization" for key in merged):
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
    """Fetch data from API endpoint."""
    # Ensure base is a string (handle Typer Option objects)
    if not isinstance(base, str):
        base = get_base_url(None)
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
        raise APIError(f"Request failed with status {exc.response.status_code} for {url}") from exc
    except httpx.RequestError as exc:
        raise APIError(f"Unable to reach {url}: {exc}") from exc
    try:
        data = response.json()
    except ValueError as exc:
        raise APIError("Response is not JSON.") from exc
    return url, data


def post(
    path_or_url: str | None,
    base: str,
    json_data: Dict[str, Any],
    headers: Dict[str, str],
    no_auth: bool = False,
) -> Tuple[str, Dict]:
    """POST request to API endpoint."""
    # Ensure base is a string (handle Typer Option objects)
    if not isinstance(base, str):
        base = get_base_url(None)
    url = resolve_url(path_or_url, base)
    prepared_headers = apply_auth(headers, base, no_auth)
    if "Content-Type" not in prepared_headers:
        prepared_headers["Content-Type"] = "application/json"
    try:
        response = httpx.post(
            url,
            json=json_data,
            headers=prepared_headers or None,
            timeout=15,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        error_msg = f"Request failed with status {exc.response.status_code} for {url}"
        try:
            error_data = exc.response.json()
            if "message" in error_data:
                error_msg += f": {error_data['message']}"
        except ValueError:
            pass
        raise APIError(error_msg) from exc
    except httpx.RequestError as exc:
        raise APIError(f"Unable to reach {url}: {exc}") from exc
    try:
        data = response.json() if response.content else {}
    except ValueError:
        data = {}
    return url, data


def patch(
    path_or_url: str | None,
    base: str,
    json_data: Dict[str, Any],
    headers: Dict[str, str],
    no_auth: bool = False,
) -> Tuple[str, Dict]:
    """PATCH request to API endpoint."""
    # Ensure base is a string (handle Typer Option objects)
    if not isinstance(base, str):
        base = get_base_url(None)
    url = resolve_url(path_or_url, base)
    prepared_headers = apply_auth(headers, base, no_auth)
    if "Content-Type" not in prepared_headers:
        prepared_headers["Content-Type"] = "application/json"
    try:
        response = httpx.patch(
            url,
            json=json_data,
            headers=prepared_headers or None,
            timeout=15,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        error_msg = f"Request failed with status {exc.response.status_code} for {url}"
        try:
            error_data = exc.response.json()
            if "message" in error_data:
                error_msg += f": {error_data['message']}"
        except ValueError:
            pass
        raise APIError(error_msg) from exc
    except httpx.RequestError as exc:
        raise APIError(f"Unable to reach {url}: {exc}") from exc
    try:
        data = response.json() if response.content else {}
    except ValueError:
        data = {}
    return url, data


def login(base: str, username: str, password: str) -> Dict[str, Any]:
    """Login to Plone site and return token."""
    # Ensure base is a string (handle Typer Option objects)
    if not isinstance(base, str):
        base = get_base_url(None)
    login_url = resolve_url("@login", base)
    try:
        response = httpx.post(
            login_url,
            json={"login": username, "password": password},
            timeout=15,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise APIError(f"Login failed with status {exc.response.status_code}.") from exc
    except httpx.RequestError as exc:
        raise APIError(f"Unable to reach {login_url}: {exc}") from exc
    payload = response.json()
    token = payload.get("token")
    if not token:
        raise APIError("Login response did not include a token.")
    save_config({
        "base": base.rstrip("/"),
        "auth": {"mode": "token", "token": token, "username": username}
    })
    return payload


def search_by_subject(base: str, subject: str, path: str = "", no_auth: bool = False) -> List[Dict[str, Any]]:
    """Search for items with a specific subject/tag."""
    # Ensure base is a string (handle Typer Option objects)
    if not isinstance(base, str):
        base = get_base_url(None)
    search_url = resolve_url("@search", base)
    params = {
        "Subject": subject,
    }
    if path:
        params["path"] = path
    
    headers = apply_auth({}, base, no_auth)
    try:
        response = httpx.get(
            search_url,
            params=params,
            headers=headers or None,
            timeout=15,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise APIError(f"Search failed with status {exc.response.status_code}.") from exc
    except httpx.RequestError as exc:
        raise APIError(f"Unable to reach {search_url}: {exc}") from exc
    
    try:
        data = response.json()
        return data.get("items", [])
    except ValueError:
        return []


def get_all_tags(base: str, path: str = "", no_auth: bool = False) -> Dict[str, int]:
    """Get all tags/subjects with their frequency from items in a path."""
    # Ensure base is a string (handle Typer Option objects)
    if not isinstance(base, str):
        base = get_base_url(None)
    url, data = fetch(path, base, {}, {}, no_auth)
    items = data.get("items", [])
    
    tag_counts: Dict[str, int] = {}
    
    def collect_tags(item: Dict[str, Any]) -> None:
        """Recursively collect tags from item and its children."""
        subjects = item.get("subjects", [])
        for subject in subjects:
            if subject:
                tag_counts[subject] = tag_counts.get(subject, 0) + 1
        
        # Recursively process children if this is a container
        if item.get("is_folderish"):
            item_path = item.get("@id", "").replace(base.rstrip("/"), "").lstrip("/")
            try:
                _, child_data = fetch(item_path, base, {}, {}, no_auth)
                child_items = child_data.get("items", [])
                for child in child_items:
                    collect_tags(child)
            except Exception:
                pass  # Skip if we can't access children
    
    for item in items:
        collect_tags(item)
    
    return tag_counts


def update_item_subjects(base: str, item_path: str, subjects: List[str], no_auth: bool = False) -> Dict[str, Any]:
    """Update the subjects/tags of an item."""
    # Ensure base is a string (handle Typer Option objects)
    if not isinstance(base, str):
        base = get_base_url(None)
    url = resolve_url(item_path, base)
    return patch(url, base, {"subjects": subjects}, {}, no_auth)[1]

