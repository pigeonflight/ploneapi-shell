"""
Shared API functions for Plone REST API interactions.
Used by both CLI and web interface.
"""

from __future__ import annotations

import json
import os
import base64
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse, urlunparse
import time

import httpx
from thefuzz import fuzz

CONFIG_ENV = os.environ.get("PLONEAPI_SHELL_CONFIG")
CONFIG_FILE = Path(CONFIG_ENV).expanduser() if CONFIG_ENV else Path.home() / ".config" / "ploneapi_shell" / "config.json"
DEFAULT_BASE = "https://demo.plone.org/++api++/"
TOKEN_REFRESH_LEEWAY = 120  # seconds before expiry to proactively renew
TOKEN_REFRESH_MIN_INTERVAL = 30  # avoid hammering renew endpoint
LOCAL_HOST_PREFIXES = ("localhost", "127.", "0.0.0.0", "::1", "[::1]")
IP_PATTERN = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


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


def _infer_scheme(host: str) -> str:
    """Choose http/https when user omitted scheme."""
    host_lower = host.lower()
    if host_lower.startswith(LOCAL_HOST_PREFIXES) or IP_PATTERN.match(host_lower):
        return "http"
    if ":" in host_lower and host_lower.split(":", 1)[0].startswith(LOCAL_HOST_PREFIXES):
        return "http"
    return "https"


def normalize_base_input(raw: str) -> str:
    """Normalize user-provided base URL and ensure it points at ++api++."""
    if raw is None:
        raise APIError("Base URL cannot be empty.")
    text = raw.strip()
    if not text:
        raise APIError("Base URL cannot be empty.")

    if "://" not in text:
        # Assume user omitted scheme
        host_fragment = text.split("/", 1)[0]
        scheme = _infer_scheme(host_fragment)
        text = f"{scheme}://{text}"

    parsed = urlparse(text)
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc or ""
    path = parsed.path or ""

    if not netloc:
        # urlparse treats "http://example" differently than bare strings, but handle safety.
        if parsed.path:
            netloc = parsed.path
            path = ""
        else:
            raise APIError("Could not determine host from base URL.")

    # Ensure path points to ++api++
    if "++api++" in path:
        before, _ = path.split("++api++", 1)
        before = before.rstrip("/")
        path = f"{before}/++api++/"
    else:
        trimmed = path.rstrip("/")
        if trimmed and trimmed != "/":
            path = trimmed + "/++api++/"
        else:
            path = "/++api++/"

    # Collapse duplicate slashes (without touching netloc)
    while "//" in path:
        path = path.replace("//", "/")

    normalized = urlunparse((scheme, netloc, path, "", "", ""))
    return normalized


def verify_base_url(base: str) -> None:
    """Attempt to fetch base URL to confirm it's reachable."""
    url = resolve_url(None, base)
    try:
        response = httpx.get(url, timeout=10)
    except httpx.RequestError as exc:
        raise APIError(f"Unable to reach {url}: {exc}") from exc

    if response.status_code in (200, 401):
        # 200 OK or 401 Unauthorized (needs auth) are both acceptable
        return

    raise APIError(f"Base URL responded with status {response.status_code} for {url}")


def _decode_jwt_exp(token: str) -> Optional[int]:
    """Return exp timestamp from JWT token without verifying signature."""
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        payload_segment = parts[1]
        padding = "=" * (-len(payload_segment) % 4)
        payload_bytes = base64.urlsafe_b64decode(payload_segment + padding)
        payload = json.loads(payload_bytes.decode("utf-8"))
        exp = payload.get("exp")
        return int(exp) if exp is not None else None
    except Exception:
        return None


def _write_auth_config(base: str, auth_data: Dict[str, Any]) -> None:
    """Persist auth block while preserving other config keys."""
    config = load_config() or {}
    config["base"] = base.rstrip("/")
    config["auth"] = auth_data
    save_config(config)


def _save_token(base: str, token: str, username: Optional[str]) -> None:
    """Save token plus metadata to config."""
    auth_block: Dict[str, Any] = {
        "mode": "token",
        "token": token,
        "updated_at": int(time.time()),
    }
    if username:
        auth_block["username"] = username
    token_exp = _decode_jwt_exp(token)
    if token_exp:
        auth_block["token_exp"] = token_exp
    _write_auth_config(base, auth_block)


def _should_refresh_token(auth: Dict[str, Any]) -> bool:
    """Determine if token is close to expiry and needs refresh."""
    token_exp = auth.get("token_exp")
    if not token_exp:
        return False
    now = int(time.time())
    if token_exp - TOKEN_REFRESH_LEEWAY <= now:
        last_attempt = auth.get("updated_at", 0)
        if now - last_attempt >= TOKEN_REFRESH_MIN_INTERVAL:
            return True
    return False


def _renew_token(base: str, current_token: str, username: Optional[str]) -> Optional[str]:
    """Call @login-renew to obtain a new token."""
    renew_url = resolve_url("@login-renew", base)
    headers = {"Authorization": f"Bearer {current_token}"}
    try:
        response = httpx.post(renew_url, headers=headers, timeout=15)
        response.raise_for_status()
        payload = response.json()
        new_token = payload.get("token")
        if new_token:
            _save_token(base, new_token, username)
            return new_token
    except (httpx.HTTPStatusError, httpx.RequestError, ValueError):
        # Silently ignore so callers can fall back to prompting for login.
        pass
    return None


def get_saved_auth_headers(base: str) -> Dict[str, str]:
    """Get saved authentication headers for a base URL."""
    config = load_config()
    if not config:
        return {}
    saved_base = config.get("base")
    if not saved_base or saved_base.rstrip("/") != base.rstrip("/"):
        return {}
    auth = config.get("auth") or {}
    mode = auth.get("mode")
    token = auth.get("token")
    if mode != "token" or not token:
        return {}
    if _should_refresh_token(auth):
        refreshed = _renew_token(base, token, auth.get("username"))
        if refreshed:
            token = refreshed
        else:
            auth_copy = dict(auth)
            auth_copy["updated_at"] = int(time.time())
            _write_auth_config(base, auth_copy)
    return {"Authorization": f"Bearer {token}"} if token else {}


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
    # Ensure Accept header is set for JSON response (required by Plone REST API)
    if "Accept" not in prepared_headers:
        prepared_headers["Accept"] = "application/json"
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
            elif "error" in error_data:
                error_msg += f": {error_data['error']}"
            elif "type" in error_data:
                error_msg += f": {error_data['type']}"
            # Include full error data for debugging if it's a 500 error
            if exc.response.status_code == 500:
                error_msg += f" (Error details: {error_data})"
        except ValueError:
            # If response is not JSON, include the text
            try:
                error_text = exc.response.text[:200]  # First 200 chars
                if error_text:
                    error_msg += f": {error_text}"
            except Exception:
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
    # Normalize base URL to ensure it includes /++api++/
    base = normalize_base_input(base)
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
    _save_token(base, token, username)
    return payload


def search_by_type(base: str, portal_type: str, path: str = "", no_auth: bool = False) -> List[Dict[str, Any]]:
    """Search for items by portal_type (object type).
    
    Args:
        base: Base API URL
        portal_type: The portal_type to search for (e.g., 'Document', 'Folder', 'News Item')
        path: Optional path to limit search to
        no_auth: Skip authentication
    
    Returns:
        List of items matching the portal_type
    """
    # Ensure base is a string (handle Typer Option objects)
    if not isinstance(base, str):
        base = get_base_url(None)
    search_url = resolve_url("@search", base)
    params = {
        "portal_type": portal_type,
        "b_size": 1000,  # Get up to 1000 items per page
    }
    if path:
        params["path"] = path
    
    headers = apply_auth({}, base, no_auth)
    all_items = []
    
    try:
        # First page
        response = httpx.get(
            search_url,
            params=params,
            headers=headers or None,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        items = data.get("items", [])
        all_items.extend(items)
        
        # Handle pagination if there are more results
        items_total = data.get("items_total", len(items))
        max_items = 10000  # Limit to prevent excessive requests
        
        while items_total > len(all_items) and len(all_items) < max_items:
            params["b_start"] = len(all_items)
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
            all_items.extend(page_items)
            if len(page_items) < params.get("b_size", 1000):
                break
        
        return all_items
    except httpx.HTTPStatusError as exc:
        raise APIError(f"Search failed with status {exc.response.status_code}.") from exc
    except httpx.RequestError as exc:
        raise APIError(f"Unable to reach {search_url}: {exc}") from exc
    except ValueError:
        return []


def search_by_subject(base: str, subject: str, path: str = "", no_auth: bool = False) -> List[Dict[str, Any]]:
    """Search for items with a specific subject/tag.
    
    Note: This uses the Plone catalog search which may not find all items if they're not
    properly indexed. The catalog search is case-sensitive and may miss items due to
    indexing issues. For a more comprehensive search, consider using get_all_tags() and
    filtering the results.
    """
    # Ensure base is a string (handle Typer Option objects)
    if not isinstance(base, str):
        base = get_base_url(None)
    search_url = resolve_url("@search", base)
    params = {
        "Subject": subject,
        "b_size": 1000,  # Get up to 1000 items per page
    }
    if path:
        params["path"] = path
    
    headers = apply_auth({}, base, no_auth)
    all_items = []
    
    try:
        # First page
        response = httpx.get(
            search_url,
            params=params,
            headers=headers or None,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        items = data.get("items", [])
        all_items.extend(items)
        
        # Handle pagination if there are more results
        items_total = data.get("items_total", len(items))
        max_items = 10000  # Limit to prevent excessive requests
        
        while items_total > len(all_items) and len(all_items) < max_items:
            params["b_start"] = len(all_items)
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
            all_items.extend(page_items)
            if len(page_items) < params.get("b_size", 1000):
                break
        
        return all_items
    except httpx.HTTPStatusError as exc:
        raise APIError(f"Search failed with status {exc.response.status_code}.") from exc
    except httpx.RequestError as exc:
        raise APIError(f"Unable to reach {search_url}: {exc}") from exc
    except ValueError:
        return []


def get_all_tags(base: str, path: str = "", no_auth: bool = False, debug: bool = False, warn_callback: Optional[Callable[[str], None]] = None, debug_callback: Optional[Callable[[str], None]] = None) -> Dict[str, int]:
    """
    Get all tags/subjects with their frequency from items in a path.
    
    Args:
        base: Base API URL
        path: Path to search (empty for root)
        no_auth: Skip authentication
        debug: Enable debug output
        warn_callback: Optional function to call with warning messages (e.g., print or CONSOLE.print)
        debug_callback: Optional function to call with debug messages (if None, uses print)
    """
    # Ensure base is a string (handle Typer Option objects)
    if not isinstance(base, str):
        base = get_base_url(None)
    
    tag_counts: Dict[str, int] = {}
    used_search = False
    
    # Try search endpoint first - query the catalog for items with subjects
    try:
        search_url = resolve_url("@search", base)
        # Query for items that have subjects (Subject index is a KeywordIndex)
        # We'll get all items and extract their subjects
        params = {
            "b_size": 1000,  # Get up to 1000 items per page
            "metadata_fields": "_all",  # Request all metadata including Subject field
        }
        # Explicitly request Subject field if the API supports it
        # Some Plone REST API versions need explicit field requests
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
        used_search = True
        
        if debug:
            debug_msg = debug_callback or print
            debug_msg(f"DEBUG: Search returned {len(items)} items")
            if items:
                debug_msg(f"DEBUG: First item keys: {list(items[0].keys())}")
                # Check specifically for Subject field (Plone's standard field name)
                if "Subject" in items[0]:
                    debug_msg(f"DEBUG: ✓ Found 'Subject' field: {items[0]['Subject']}")
                elif "subject" in items[0]:
                    debug_msg(f"DEBUG: ✓ Found 'subject' field (lowercase): {items[0]['subject']}")
                else:
                    debug_msg(f"DEBUG: ✗ 'Subject' field NOT found in first item")
                    # Show all keys that might contain subjects
                    subject_keys = [k for k in items[0].keys() if 'subject' in k.lower() or 'tag' in k.lower() or 'keyword' in k.lower()]
                    if subject_keys:
                        debug_msg(f"DEBUG: Potential subject-related keys found: {subject_keys}")
                        for key in subject_keys[:3]:  # Show first 3 subject keys
                            debug_msg(f"DEBUG: {key} = {items[0].get(key)}")
                    else:
                        debug_msg(f"DEBUG: No subject-related keys found. All keys: {list(items[0].keys())}")
                # Show full first item structure for debugging
                debug_msg(f"DEBUG: First item full structure (first 30 keys):")
                for i, (k, v) in enumerate(list(items[0].items())[:30]):
                    if isinstance(v, (list, dict)) and len(str(v)) > 100:
                        debug_msg(f"  {k}: {type(v).__name__} (length: {len(v) if hasattr(v, '__len__') else 'N/A'})")
                    else:
                        debug_msg(f"  {k}: {v}")
        
        # Collect all subjects from items
        # In Plone, subjects are stored in the Subject field and indexed in portal_catalog
        # The REST API should return them in the item metadata
        items_without_subjects = []
        items_checked = 0
        for item in items:
            items_checked += 1
            # In Plone, the Subject field is the primary field for tags/keywords
            # It's indexed in portal_catalog as a KeywordIndex
            # Check for Subject field first (capital S is the standard)
            subjects = None
            
            # Priority 1: Direct Subject field (most common in Plone REST API)
            if "Subject" in item:
                subjects = item["Subject"]
            # Priority 2: Lowercase subject (some REST API implementations)
            elif "subject" in item:
                subjects = item["subject"]
            # Priority 3: Check in @components (some REST API versions nest it)
            elif "@components" in item and "Subject" in item["@components"]:
                subjects = item["@components"]["Subject"]
            # Priority 4: Check in metadata if present
            elif "metadata" in item and "Subject" in item["metadata"]:
                subjects = item["metadata"]["Subject"]
            # Priority 5: Other possible field names
            elif "subjects" in item:
                subjects = item["subjects"]
            elif "keywords" in item:
                subjects = item["keywords"]
            elif "Keywords" in item:
                subjects = item["Keywords"]
            elif "tags" in item:
                subjects = item["tags"]
            elif "Tags" in item:
                subjects = item["Tags"]
            
            # Handle different data types
            if subjects is None:
                subjects = []
            elif isinstance(subjects, str):
                # Single string value - convert to list
                subjects = [subjects] if subjects else []
            elif not isinstance(subjects, list):
                # Try to convert other types
                try:
                    subjects = list(subjects) if subjects else []
                except (TypeError, ValueError):
                    subjects = []
            
            # Filter out empty strings and None values
            subjects = [s for s in subjects if s and isinstance(s, str) and s.strip()]
            
            if subjects:
                for subject in subjects:
                    subject = subject.strip()
                    if subject:
                        tag_counts[subject] = tag_counts.get(subject, 0) + 1
                if debug and items_checked <= 5:
                    debug_msg = debug_callback or print
                    debug_msg(f"DEBUG: Item {items_checked} has subjects: {subjects}")
            else:
                # Store item URL to fetch full details later
                item_url = item.get("@id")
                if item_url:
                    items_without_subjects.append(item_url)
                if debug and items_checked <= 5:
                    debug_msg = debug_callback or print
                    debug_msg(f"DEBUG: Item {items_checked} has no subjects. Keys: {list(item.keys())[:20]}")
        
        # Fetch full item details for items that didn't have subjects in search results
        if items_without_subjects and not tag_counts:
            if debug:
                print(f"DEBUG: No subjects found in search results. Fetching full details for {min(len(items_without_subjects), 100)} items")
            for idx, item_url in enumerate(items_without_subjects[:100]):  # Limit to 100 to avoid too many requests
                try:
                    # Extract path from full URL
                    item_path = item_url.replace(base.rstrip("/"), "").lstrip("/")
                    _, full_item = fetch(item_path, base, {}, {}, no_auth)
                    
                    # Try same comprehensive field checking for full items
                    # Priority: Subject field first (Plone's standard)
                    subjects = None
                    if "Subject" in full_item:
                        subjects = full_item["Subject"]
                    elif "subject" in full_item:
                        subjects = full_item["subject"]
                    elif "@components" in full_item and "Subject" in full_item["@components"]:
                        subjects = full_item["@components"]["Subject"]
                    elif "metadata" in full_item and "Subject" in full_item["metadata"]:
                        subjects = full_item["metadata"]["Subject"]
                    elif "subjects" in full_item:
                        subjects = full_item["subjects"]
                    elif "keywords" in full_item:
                        subjects = full_item["keywords"]
                    elif "Keywords" in full_item:
                        subjects = full_item["Keywords"]
                    elif "tags" in full_item:
                        subjects = full_item["tags"]
                    elif "Tags" in full_item:
                        subjects = full_item["Tags"]
                    
                    if subjects is None:
                        subjects = []
                    elif isinstance(subjects, str):
                        subjects = [subjects] if subjects else []
                    elif not isinstance(subjects, list):
                        try:
                            subjects = list(subjects) if subjects else []
                        except (TypeError, ValueError):
                            subjects = []
                    
                    subjects = [s for s in subjects if s and isinstance(s, str) and s.strip()]
                    
                    if subjects:
                        for subject in subjects:
                            subject = subject.strip()
                            if subject:
                                tag_counts[subject] = tag_counts.get(subject, 0) + 1
                        if debug and idx < 5:
                            debug_msg = debug_callback or print
                            debug_msg(f"DEBUG: Full item fetch {idx+1} found subjects: {subjects}")
                    elif debug and idx < 5:
                        debug_msg = debug_callback or print
                        debug_msg(f"DEBUG: Full item fetch {idx+1} still has no subjects. Keys: {list(full_item.keys())[:20]}")
                except Exception as e:
                    if debug and idx < 5:
                        print(f"DEBUG: Failed to fetch full item {idx+1}: {e}")
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
                # Priority: Subject field first (Plone's standard)
                subjects = None
                if "Subject" in item:
                    subjects = item["Subject"]
                elif "subject" in item:
                    subjects = item["subject"]
                elif "@components" in item and "Subject" in item["@components"]:
                    subjects = item["@components"]["Subject"]
                elif "metadata" in item and "Subject" in item["metadata"]:
                    subjects = item["metadata"]["Subject"]
                elif "subjects" in item:
                    subjects = item["subjects"]
                elif "keywords" in item:
                    subjects = item["keywords"]
                elif "Keywords" in item:
                    subjects = item["Keywords"]
                elif "tags" in item:
                    subjects = item["tags"]
                elif "Tags" in item:
                    subjects = item["Tags"]
                
                if subjects is None:
                    subjects = []
                elif isinstance(subjects, str):
                    subjects = [subjects] if subjects else []
                elif not isinstance(subjects, list):
                    try:
                        subjects = list(subjects) if subjects else []
                    except (TypeError, ValueError):
                        subjects = []
                
                subjects = [s for s in subjects if s and isinstance(s, str) and s.strip()]
                
                if subjects:
                    for subject in subjects:
                        subject = subject.strip()
                        if subject:
                            tag_counts[subject] = tag_counts.get(subject, 0) + 1
        
            items.extend(page_items)
            if len(page_items) < params.get("b_size", 1000):
                break
        
        # If we found tags, return them
        if tag_counts:
            if debug:
                print(f"DEBUG: Found {len(tag_counts)} unique tags via search")
            return tag_counts
        elif debug:
            print(f"DEBUG: Search succeeded but found no tags in {len(items)} items")
                
    except (httpx.HTTPStatusError, httpx.RequestError, Exception) as e:
        if debug:
            print(f"DEBUG: Search failed: {type(e).__name__}: {e}")
        # Fallback to browsing if search fails or returns no subjects
        pass
    
    # Fallback: Browse recursively through the site
    if not used_search or not tag_counts:
        if warn_callback:
            warn_callback("[yellow]Warning:[/yellow] Search endpoint didn't return tags. Falling back to recursive browsing (this may take a while on large sites)...")
        
        # Cache for fetched items to avoid re-fetching
        item_cache: Dict[str, Dict[str, Any]] = {}
        visited_paths: set = set()
        
        def collect_tags_recursive(current_path: str, depth: int = 0, max_depth: int = 20) -> None:
            """Recursively collect tags from items with caching."""
            if current_path in visited_paths or depth > max_depth:
                return
            visited_paths.add(current_path)
            
            try:
                # Check cache first
                if current_path in item_cache:
                    data = item_cache[current_path]
                else:
                    url, data = fetch(current_path, base, {}, {}, no_auth)
                    item_cache[current_path] = data
                
                items = data.get("items", [])
                
                for item in items:
                    # Priority: Subject field first (Plone's standard)
                    subjects = None
                    if "Subject" in item:
                        subjects = item["Subject"]
                    elif "subject" in item:
                        subjects = item["subject"]
                    elif "@components" in item and "Subject" in item["@components"]:
                        subjects = item["@components"]["Subject"]
                    elif "metadata" in item and "Subject" in item["metadata"]:
                        subjects = item["metadata"]["Subject"]
                    elif "subjects" in item:
                        subjects = item["subjects"]
                    elif "keywords" in item:
                        subjects = item["keywords"]
                    elif "Keywords" in item:
                        subjects = item["Keywords"]
                    elif "tags" in item:
                        subjects = item["tags"]
                    elif "Tags" in item:
                        subjects = item["Tags"]
                    
                    if subjects is None:
                        subjects = []
                    elif isinstance(subjects, str):
                        subjects = [subjects] if subjects else []
                    elif not isinstance(subjects, list):
                        try:
                            subjects = list(subjects) if subjects else []
                        except (TypeError, ValueError):
                            subjects = []
                    
                    subjects = [s for s in subjects if s and isinstance(s, str) and s.strip()]
                    
                    if subjects:
                        for subject in subjects:
                            subject = subject.strip()
                            if subject:
                                tag_counts[subject] = tag_counts.get(subject, 0) + 1
                    
                    # If it's a container, recurse into it
                    if item.get("is_folderish") or item.get("@type") in ("Folder", "Collection"):
                        item_path = item.get("@id", "").replace(base.rstrip("/"), "").lstrip("/")
                        if item_path and item_path not in visited_paths:
                            collect_tags_recursive(item_path, depth + 1, max_depth)
            except Exception:
                pass  # Skip if we can't access this path
        
        try:
            # Start from the given path or root
            collect_tags_recursive(path if path else "", max_depth=20)
        except Exception:
            pass
    
    return tag_counts


def update_item_subjects(base: str, item_path: str, subjects: List[str], no_auth: bool = False) -> Dict[str, Any]:
    """Update the subjects/tags of an item.
    
    Based on Plone REST API documentation, content updates should use PATCH with the field name
    directly in the JSON body. However, some Plone sites may have custom serializers or require
    different formats.
    """
    # Ensure base is a string (handle Typer Option objects)
    if not isinstance(base, str):
        base = get_base_url(None)
    url = resolve_url(item_path, base)
    
    # First, fetch the current item to understand its structure
    # According to Plone REST API docs, GET returns "subjects" (lowercase) as an array
    # But PATCH should use "Subject" (capital S) with an array
    try:
        _, current_item = fetch(item_path, base, {}, {}, no_auth)
    except Exception as e:
        raise APIError(f"Could not fetch item to determine structure: {e}") from e
    
    # Try to get schema information if available (some Plone REST API versions expose this)
    # This can help us understand what fields are available and how they should be updated
    schema_info = None
    try:
        schema_url = url.rstrip("/") + "/@schema"
        _, schema_data = fetch(schema_url, base, {}, {}, no_auth)
        schema_info = schema_data
        # Check if Subject field is in schema and what its properties are
        if isinstance(schema_data, dict) and "properties" in schema_data:
            subject_props = schema_data["properties"].get("Subject") or schema_data["properties"].get("subjects")
            if subject_props:
                # Log schema info for debugging (we can use this later)
                pass
    except Exception:
        # Schema endpoint might not be available, that's okay
        pass
    
    # Check where Subject field actually is in the response and its format
    subject_location = None
    current_subjects_value = None
    subjects_type = None
    
    if "Subject" in current_item:
        subject_location = "top_level"
        current_subjects_value = current_item["Subject"]
        subjects_type = type(current_subjects_value).__name__
    elif "subjects" in current_item:
        subject_location = "top_level_lowercase"
        current_subjects_value = current_item["subjects"]
        subjects_type = type(current_subjects_value).__name__
    elif "@components" in current_item and isinstance(current_item["@components"], dict):
        components = current_item["@components"]
        if "Subject" in components:
            subject_location = "components"
            current_subjects_value = components["Subject"]
            subjects_type = type(current_subjects_value).__name__
        elif "subjects" in components:
            subject_location = "components_lowercase"
            current_subjects_value = components["subjects"]
            subjects_type = type(current_subjects_value).__name__
        # Check what's actually in @components for debugging
        component_keys = list(components.keys()) if isinstance(components, dict) else []
    
    # Try different approaches based on what the API expects
    # Plone REST API might need the field in different formats
    
    # According to Plone REST API documentation:
    # - GET responses return "subjects" (lowercase) as an array: {"subjects": ["tag1", "tag2"]}
    # - PATCH requests should use "Subject" (capital S) with an array: {"Subject": ["tag1", "tag2"]}
    # The field expects a list of strings (not tuple, not other types)
    
    # Ensure subjects is a clean list of strings
    if not isinstance(subjects, list):
        subjects = list(subjects)
    # Ensure all items are strings and filter out empty values
    subjects = [str(s).strip() for s in subjects if s and str(s).strip()]
    
    # Approach 1: Use "Subject" (capital S) with list of strings - this is the documented format
    # According to official Plone REST API docs, PATCH should use capital S "Subject"
    # even though GET responses show lowercase "subjects"
    try:
        result = patch(url, base, {"Subject": subjects}, {}, no_auth)[1]
        # Verify the update by checking if subjects were actually updated in the response
        # Some APIs return success but don't actually update
        if isinstance(result, dict):
            updated_subjects = result.get("Subject") or result.get("subjects", [])
            if isinstance(updated_subjects, str):
                updated_subjects = [updated_subjects]
            # Check if the update actually took effect
            if set(updated_subjects) != set(subjects):
                # Update didn't match what we sent - the server returned success but didn't update
                # This is a server-side issue - raise an error so the caller knows
                raise APIError(
                    f"PATCH request returned success but subjects were not updated. "
                    f"Sent: {subjects}, Got back: {updated_subjects}. "
                    f"This indicates the server accepted the request but did not apply the changes."
                )
        return result
    except APIError as e1:
        # Check if this is the __getitem__ error we've been seeing
        if "__getitem__" in str(e1) or "500" in str(e1):
            # This is the known server-side error - continue to fallback approaches
            pass
        else:
            # Some other error - might be worth trying fallbacks too
            pass
        # Approach 2: Try with "subjects" (lowercase - as it appears in some API responses)
        # Some REST API serializers use lowercase field names in responses but may accept both
        try:
            return patch(url, base, {"subjects": subjects}, {}, no_auth)[1]
        except APIError as e2:
            # The __getitem__ AttributeError persists even with the documented format.
            # This strongly suggests a server-side issue. Let's try a few more things:
            
            # Approach 2b: Try with empty list first, then set subjects (workaround for some serializer bugs)
            try:
                # Some serializers have issues with updating non-empty lists, try clearing first
                patch(url, base, {"Subject": []}, {}, no_auth)
                return patch(url, base, {"Subject": subjects}, {}, no_auth)[1]
            except APIError:
                pass
            
            # Approach 2c: Try including @type (some serializers need this to identify content type)
            try:
                update_data = {
                    "@type": current_item.get("@type"),
                    "Subject": subjects
                }
                return patch(url, base, update_data, {}, no_auth)[1]
            except APIError:
                pass
            
            # Approach 3: Try using @content endpoint if available
            content_url = url.rstrip("/") + "/@content"
            try:
                return patch(content_url, base, {"Subject": subjects}, {}, no_auth)[1]
            except APIError as e3:
                # Approach 4: Try with minimal update - only send what's needed
                # Some Plone REST API versions require only the fields being updated
                try:
                    # Try with just the field name that matches where it was found
                    if subject_location == "components":
                        update_data = {"@components": {"Subject": subjects}}
                    elif subject_location == "components_lowercase":
                        update_data = {"@components": {"subjects": subjects}}
                    else:
                        update_data = {"Subject": subjects}
                    return patch(url, base, update_data, {}, no_auth)[1]
                except APIError as e4:
                    # Approach 5: Try POST to @content endpoint (some APIs use POST for updates)
                    try:
                        return post(content_url, base, {"Subject": subjects}, {}, no_auth)[1]
                    except APIError as e5:
                        # Approach 6: Check if there's a @types endpoint that shows how to update
                        # Some Plone REST API versions require using specific field update endpoints
                        # Try using the field name directly in the path
                        try:
                            field_url = url.rstrip("/") + "/@fields/subject"
                            return patch(field_url, base, subjects, {}, no_auth)[1]
                        except APIError as e6:
                            # If all approaches fail, provide detailed error with component info
                            component_info = ""
                            if "@components" in current_item and isinstance(current_item["@components"], dict):
                                component_info = f"@components keys: {list(current_item['@components'].keys())[:10]}"
                            
                            # Build detailed error message
                            current_subjects_info = ""
                            if current_subjects_value is not None:
                                current_subjects_info = f"Current subjects value type: {subjects_type}, value: {current_subjects_value[:3] if isinstance(current_subjects_value, (list, tuple)) and len(current_subjects_value) > 3 else current_subjects_value}"
                            
                            # Final error message with all diagnostic information
                            schema_info_text = ""
                            if schema_info:
                                schema_info_text = f"Schema available: {bool(schema_info)}. "
                            
                            raise APIError(
                                f"Failed to update subjects using the documented Plone REST API format. "
                                f"According to official docs, PATCH with {{'Subject': ['tag1', 'tag2']}} should work. "
                                f"Tried: 'Subject' (capital S with list), 'subjects' (lowercase), '@content' endpoint, minimal update, POST, and field endpoint. "
                                f"Subject location in item: {subject_location}. {current_subjects_info}. {component_info}. {schema_info_text}"
                                f"Errors: Subject={e1}, subjects={e2}, content_patch={e3}, minimal={e4}, content_post={e5}, field_endpoint={e6}. "
                                f"Item structure keys: {list(current_item.keys())[:20]}. "
                                f"The persistent '__getitem__' AttributeError (500) suggests a server-side issue. "
                                f"This could be: (1) a bug in the Plone REST API version on this server, "
                                f"(2) the Subject field is not included in writable fields for this content type, "
                                f"or (3) a custom serializer issue. "
                                f"Recommendation: Check server logs or contact the site administrator about Subject field updates via REST API."
                            ) from e6


def move_item(base: str, source_path: str, dest_path: str, new_id: Optional[str] = None, no_auth: bool = False) -> Dict[str, Any]:
    """Move an item to a new location.
    
    Args:
        base: Base API URL
        source_path: Path to the item to move
        dest_path: Destination folder path (or folder/new-id to rename during move)
        new_id: Optional new id/name for the item (if None, keeps current id)
        no_auth: Whether to skip authentication
        
    Returns:
        Response data from the move operation
    """
    # Ensure base is a string
    if not isinstance(base, str):
        base = get_base_url(None)
    
    # Resolve source and destination URLs
    source_url = resolve_url(source_path, base)
    dest_url = resolve_url(dest_path, base)
    
    # Check if dest_path includes a new name (has a slash with something after)
    # If dest_path ends with a name (not just a folder), extract folder and new_id
    dest_parts = dest_path.rstrip("/").split("/")
    if len(dest_parts) > 1 and not dest_path.endswith("/"):
        # Last part is the new name
        dest_folder = "/".join(dest_parts[:-1])
        if not new_id:
            new_id = dest_parts[-1]
        dest_url = resolve_url(dest_folder, base)
    
    # Use @move endpoint: POST to destination/@move with source reference
    move_url = dest_url.rstrip("/") + "/@move"
    prepared_headers = apply_auth({}, base, no_auth)
    if "Content-Type" not in prepared_headers:
        prepared_headers["Content-Type"] = "application/json"
    if "Accept" not in prepared_headers:
        prepared_headers["Accept"] = "application/json"
    
    # Build move payload
    move_data = {"source": source_url}
    if new_id:
        move_data["id"] = new_id
    
    try:
        response = httpx.post(
            move_url,
            json=move_data,
            headers=prepared_headers or None,
            timeout=15,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        error_msg = f"Move failed with status {exc.response.status_code} for {move_url}"
        try:
            error_data = exc.response.json()
            if "message" in error_data:
                error_msg += f": {error_data['message']}"
            elif "error" in error_data:
                error_msg += f": {error_data['error']}"
        except ValueError:
            pass
        raise APIError(error_msg) from exc
    except httpx.RequestError as exc:
        raise APIError(f"Unable to reach {move_url}: {exc}") from exc
    
    try:
        data = response.json() if response.content else {}
    except ValueError:
        data = {}
    return data


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

