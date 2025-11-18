"""
Shared API functions for Plone REST API interactions.
Used by both CLI and web interface.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
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

