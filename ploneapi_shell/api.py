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
from thefuzz import fuzz

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
        return base.rstrip("/") + "/"
    if path_or_url.startswith(("http://", "https://")):
        return path_or_url
    # Ensure base ends with / for proper urljoin behavior
    if not base.endswith("/"):
        base = base + "/"
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


def get_all_tags(base: str, path: str = "", no_auth: bool = False, debug: bool = False) -> Dict[str, int]:
    """Get all tags/subjects with their frequency from items in a path."""
    # Ensure base is a string (handle Typer Option objects)
    if not isinstance(base, str):
        base = get_base_url(None)
    
    tag_counts: Dict[str, int] = {}
    
    # Try search endpoint first
    try:
        search_url = resolve_url("@search", base)
        params = {
            "b_size": 1000,  # Get up to 1000 items
        }
        if path:
            params["path"] = path
        
        headers = apply_auth({}, base, no_auth)
        response = httpx.get(
            search_url,
            params=params,
            headers=headers or None,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        items = data.get("items", [])
        
        if debug:
            print(f"DEBUG: Search returned {len(items)} items")
            if items:
                print(f"DEBUG: First item keys: {list(items[0].keys())}")
                print(f"DEBUG: First item sample: {list(items[0].items())[:10]}")
        
        # Collect all subjects from items - try multiple field names
        # If search results don't have subjects, fetch full items
        items_without_subjects = []
        for item in items:
            # Try different possible field names for subjects/tags
            subjects = (
                item.get("subjects") or 
                item.get("Subject") or 
                item.get("subject") or
                item.get("keywords") or
                item.get("Keywords") or
                item.get("tags") or
                item.get("Tags") or
                []
            )
            
            # If it's a string, convert to list
            if isinstance(subjects, str):
                subjects = [subjects]
            
            if subjects:
                for subject in subjects:
                    if subject:
                        tag_counts[subject] = tag_counts.get(subject, 0) + 1
            else:
                # Store item URL to fetch full details later
                item_url = item.get("@id")
                if item_url:
                    items_without_subjects.append(item_url)
        
        # Fetch full item details for items that didn't have subjects in search results
        if items_without_subjects and not tag_counts:
            if debug:
                print(f"DEBUG: Fetching full details for {len(items_without_subjects[:10])} items (showing first 10)")
            for item_url in items_without_subjects[:100]:  # Limit to 100 to avoid too many requests
                try:
                    # Extract path from full URL
                    item_path = item_url.replace(base.rstrip("/"), "").lstrip("/")
                    _, full_item = fetch(item_path, base, {}, {}, no_auth)
                    
                    subjects = (
                        full_item.get("subjects") or 
                        full_item.get("Subject") or 
                        full_item.get("subject") or
                        full_item.get("keywords") or
                        full_item.get("Keywords") or
                        full_item.get("tags") or
                        full_item.get("Tags") or
                        []
                    )
                    
                    if isinstance(subjects, str):
                        subjects = [subjects]
                    
                    if subjects:
                        for subject in subjects:
                            if subject:
                                tag_counts[subject] = tag_counts.get(subject, 0) + 1
                except Exception:
                    continue
        
        # Handle pagination if there are more results
        items_total = data.get("items_total", len(items))
        
        # If there are more items, fetch them (up to a reasonable limit)
        max_items = 10000  # Limit to prevent excessive requests
        while items_total > len(items) and len(items) < max_items:
            params["b_start"] = len(items)
            response = httpx.get(
                search_url,
                params=params,
                headers=headers or None,
                timeout=15,
            )
            response.raise_for_status()
            page_data = response.json()
            page_items = page_data.get("items", [])
            if not page_items:
                break
            
            for item in page_items:
                # Try different possible field names for subjects/tags
                subjects = (
                    item.get("subjects") or 
                    item.get("Subject") or 
                    item.get("subject") or
                    item.get("keywords") or
                    item.get("Keywords") or
                    item.get("tags") or
                    item.get("Tags") or
                    []
                )
                
                # If it's a string, convert to list
                if isinstance(subjects, str):
                    subjects = [subjects]
                
                if subjects:
                    for subject in subjects:
                        if subject:
                            tag_counts[subject] = tag_counts.get(subject, 0) + 1
            
            items.extend(page_items)
            if len(page_items) < params.get("b_size", 1000):
                break
        
        # If we found tags, return them
        if tag_counts:
            return tag_counts
                
    except (httpx.HTTPStatusError, httpx.RequestError, Exception):
        # Fallback to browsing if search fails or returns no subjects
        pass
    
    # Fallback: Browse recursively through the site
    try:
        def collect_tags_recursive(current_path: str, visited: set) -> None:
            """Recursively collect tags from items."""
            if current_path in visited:
                return
            visited.add(current_path)
            
            try:
                url, data = fetch(current_path, base, {}, {}, no_auth)
                items = data.get("items", [])
                
                for item in items:
                    # Try different possible field names for subjects/tags
                    subjects = (
                        item.get("subjects") or 
                        item.get("Subject") or 
                        item.get("subject") or
                        item.get("keywords") or
                        item.get("Keywords") or
                        item.get("tags") or
                        item.get("Tags") or
                        []
                    )
                    
                    # If it's a string, convert to list
                    if isinstance(subjects, str):
                        subjects = [subjects]
                    
                    if subjects:
                        for subject in subjects:
                            if subject:
                                tag_counts[subject] = tag_counts.get(subject, 0) + 1
                    
                    # If it's a container, recurse into it
                    if item.get("is_folderish") or item.get("@type") in ("Folder", "Collection"):
                        item_path = item.get("@id", "").replace(base.rstrip("/"), "").lstrip("/")
                        if item_path and item_path not in visited:
                            collect_tags_recursive(item_path, visited)
            except Exception:
                pass  # Skip if we can't access this path
        
        # Start from the given path or root
        collect_tags_recursive(path if path else "", set())
        
    except Exception:
        pass
    
    return tag_counts


def update_item_subjects(base: str, item_path: str, subjects: List[str], no_auth: bool = False) -> Dict[str, Any]:
    """Update the subjects/tags of an item."""
    # Ensure base is a string (handle Typer Option objects)
    if not isinstance(base, str):
        base = get_base_url(None)
    url = resolve_url(item_path, base)
    return patch(url, base, {"subjects": subjects}, {}, no_auth)[1]


def find_similar_tags(base: str, query_tag: Optional[str] = None, path: str = "", threshold: int = 70, no_auth: bool = False) -> List[Tuple[str, int, int, Optional[str]]]:
    """
    Find tags similar to the query tag using fuzzy matching.
    If no query_tag is provided, finds all pairs of similar tags.
    
    Returns a list of tuples: (tag_name, frequency, similarity_score, matched_tag)
    - If query_tag is provided: matched_tag is None
    - If query_tag is None: matched_tag is the tag it's similar to
    Sorted by similarity score (descending), then by frequency (descending).
    """
    # Ensure base is a string (handle Typer Option objects)
    if not isinstance(base, str):
        base = get_base_url(None)
    
    # Get all tags
    tag_counts = get_all_tags(base, path, no_auth)
    
    if not tag_counts:
        return []
    
    # If query tag is provided, find tags similar to it
    if query_tag:
        similar_tags: List[Tuple[str, int, int, Optional[str]]] = []
        query_lower = query_tag.lower()
        
        for tag, count in tag_counts.items():
            # Calculate similarity using ratio (0-100)
            similarity = fuzz.ratio(query_lower, tag.lower())
            
            if similarity >= threshold:
                similar_tags.append((tag, count, similarity, None))
        
        # Sort by similarity (descending), then by frequency (descending), then alphabetically
        similar_tags.sort(key=lambda x: (-x[2], -x[1], x[0].lower()))
        return similar_tags
    
    # If no query tag, find all pairs of similar tags
    similar_pairs: List[Tuple[str, int, int, str]] = []
    tag_list = list(tag_counts.items())
    
    # Compare all pairs of tags
    for i, (tag1, count1) in enumerate(tag_list):
        for tag2, count2 in tag_list[i + 1:]:
            similarity = fuzz.ratio(tag1.lower(), tag2.lower())
            
            if similarity >= threshold:
                # Add both tags (we'll deduplicate later)
                # Prefer the tag with higher frequency as the "matched" tag
                if count1 >= count2:
                    similar_pairs.append((tag1, count1, similarity, tag2))
                else:
                    similar_pairs.append((tag2, count2, similarity, tag1))
    
    # Sort by similarity (descending), then by frequency (descending)
    similar_pairs.sort(key=lambda x: (-x[2], -x[1], x[0].lower()))
    
    return similar_pairs

