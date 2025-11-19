"""HTTP server that exposes Plone API Shell functionality to web clients."""

from __future__ import annotations

import asyncio
from typing import Dict, List, Optional, Tuple

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from . import __version__ as PACKAGE_VERSION
from . import api


class LoginRequest(BaseModel):
    base_url: str = Field(..., description="Plone API base URL (e.g., https://yoursite.com/++api++/)")
    username: str = Field(..., description="Plone username")
    password: str = Field(..., description="Plone password")


def _serialize_item(item: Dict) -> Dict:
    """Return a subset of item fields that the UI cares about."""
    return {
        "id": item.get("id"),
        "title": item.get("title"),
        "type": item.get("@type"),
        "review_state": item.get("review_state"),
        "modified": item.get("modified"),
        "path": item.get("@id"),
        "description": item.get("description"),
    }


def create_app(allowed_origins: Optional[List[str]] = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="Plone API Shell Server", version=PACKAGE_VERSION)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins or ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/config")
    async def get_config() -> Dict[str, str]:
        base = api.get_base_url(None)
        return {"base_url": base}

    @app.post("/api/login")
    async def login(request: LoginRequest = Body(...)) -> Dict[str, str]:
        """Login to Plone site and save credentials."""
        try:
            api.login(request.base_url, request.username, request.password)
            return {"status": "ok", "base_url": request.base_url}
        except api.APIError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/logout")
    async def logout() -> Dict[str, str]:
        """Remove saved credentials."""
        api.delete_config()
        return {"status": "ok"}

    @app.get("/api/get")
    async def get_content(
        path: Optional[str] = Query(default=None, description="Path or URL to fetch"),
        raw: bool = Query(default=False, description="Return raw JSON response"),
    ) -> Dict:
        base = api.get_base_url(None)
        try:
            url, data = api.fetch(path, base, headers={}, params={}, no_auth=False)
        except api.APIError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if raw:
            return {"url": url, "data": data}
        summary = {
            "title": data.get("title"),
            "id": data.get("id"),
            "type": data.get("@type"),
            "description": data.get("description"),
            "items_count": len(data.get("items", []) or []),
        }
        return {"url": url, "summary": summary, "data": data}

    @app.get("/api/items")
    async def list_items(
        path: Optional[str] = Query(default=None, description="Container path to list"),
    ) -> Dict:
        base = api.get_base_url(None)
        try:
            url, data = api.fetch(path, base, headers={}, params={}, no_auth=False)
        except api.APIError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        items = data.get("items")
        if not isinstance(items, list):
            raise HTTPException(status_code=400, detail="Endpoint does not expose an items array.")
        return {
            "url": url,
            "items": [_serialize_item(item) for item in items],
        }

    @app.get("/api/tags")
    async def list_tags(
        path: str = Query(default="", description="Limit to items under this path."),
        no_auth: bool = Query(default=False, description="Skip saved auth headers."),
    ) -> Dict:
        base = api.get_base_url(None)
        try:
            tag_counts = await asyncio.to_thread(
                api.get_all_tags,
                base,
                path,
                no_auth,
                False,
                None,
                None,
            )
        except api.APIError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        tags = [
            {"name": tag, "count": count}
            for tag, count in sorted(tag_counts.items(), key=lambda x: (-x[1], x[0].lower()))
        ]
        return {"path": path, "total": len(tags), "tags": tags}

    @app.get("/api/similar-tags")
    async def similar_tags(
        tag: Optional[str] = Query(default=None, description="Tag to compare against (optional)."),
        path: str = Query(default="", description="Limit search to this path."),
        threshold: int = Query(default=70, ge=0, le=100, description="Similarity threshold (0-100)."),
        no_auth: bool = Query(default=False, description="Skip saved auth headers."),
    ) -> Dict:
        base = api.get_base_url(None)
        try:
            matches = await asyncio.to_thread(
                api.find_similar_tags,
                base,
                tag,
                path,
                threshold,
                no_auth,
            )
        except api.APIError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        results = [
            {
                "tag": entry[0],
                "count": entry[1],
                "similarity": entry[2],
                "matched": entry[3],
            }
            for entry in matches
        ]
        return {"path": path, "threshold": threshold, "query": tag, "results": results}

    class MergeTagsRequest(BaseModel):
        sources: List[str] = Field(..., min_length=1, description="Source tags to merge.")
        target: str = Field(..., min_length=1, description="Target tag name.")
        path: str = Field("", description="Limit to items under this path.")
        dry_run: bool = Field(False, description="Preview changes without saving.")
        no_auth: bool = Field(False, description="Skip saved auth headers.")

    class RenameTagRequest(BaseModel):
        old_tag: str = Field(..., min_length=1)
        new_tag: str = Field(..., min_length=1)
        path: str = Field("", description="Limit to items under this path.")
        dry_run: bool = Field(False, description="Preview changes without saving.")
        no_auth: bool = Field(False, description="Skip saved auth headers.")

    class RemoveTagRequest(BaseModel):
        tag: str = Field(..., min_length=1)
        path: str = Field("", description="Limit to items under this path.")
        dry_run: bool = Field(False, description="Preview changes without saving.")
        no_auth: bool = Field(False, description="Skip saved auth headers.")

    async def _collect_items_for_tags(
        base: str,
        tags: List[str],
        path: str,
        no_auth: bool,
    ) -> Tuple[List[Dict], Dict[str, int]]:
        all_items: Dict[str, Dict] = {}
        per_tag_counts: Dict[str, int] = {}

        for tag in tags:
            items = await asyncio.to_thread(api.search_by_subject, base, tag, path, no_auth)
            per_tag_counts[tag] = len(items)
            for item in items:
                item_id = item.get("@id")
                if item_id:
                    all_items[item_id] = item

        return list(all_items.values()), per_tag_counts

    def _item_path_from_id(item_id: Optional[str], base: str) -> str:
        if not item_id:
            return ""
        prefix = base.rstrip("/")
        if item_id.startswith(prefix):
            return item_id[len(prefix):].lstrip("/")
        return item_id

    @app.post("/api/tags/merge")
    async def merge_tags(request: MergeTagsRequest = Body(...)) -> Dict:
        base = api.get_base_url(None)
        items, counts = await _collect_items_for_tags(base, request.sources, request.path, request.no_auth)

        if not items:
            return {"updated": 0, "errors": 0, "items": 0, "dry_run": request.dry_run, "message": "No matching items found."}

        preview = []
        for item in items[:10]:
            current_tags = item.get("subjects", [])
            new_tags = [tag for tag in current_tags if tag not in request.sources]
            if request.target not in new_tags:
                new_tags.append(request.target)
            preview.append(
                {
                    "title": item.get("title", item.get("id")),
                    "current": current_tags,
                    "updated": new_tags,
                }
            )

        if request.dry_run:
            return {
                "updated": 0,
                "errors": 0,
                "items": len(items),
                "preview": preview,
                "tag_counts": counts,
                "dry_run": True,
            }

        updated = 0
        errors = 0
        for item in items:
            try:
                item_path = _item_path_from_id(item.get("@id"), base)
                current_tags = item.get("subjects", [])
                new_tags = [tag for tag in current_tags if tag not in request.sources]
                if request.target not in new_tags:
                    new_tags.append(request.target)
                await asyncio.to_thread(
                    api.update_item_subjects,
                    base,
                    item_path,
                    new_tags,
                    request.no_auth,
                )
                updated += 1
            except Exception:
                errors += 1

        return {
            "updated": updated,
            "errors": errors,
            "items": len(items),
            "tag_counts": counts,
            "preview": preview,
            "dry_run": False,
        }

    @app.post("/api/tags/rename")
    async def rename_tag(request: RenameTagRequest = Body(...)) -> Dict:
        merge_request = MergeTagsRequest(
            sources=[request.old_tag],
            target=request.new_tag,
            path=request.path,
            dry_run=request.dry_run,
            no_auth=request.no_auth,
        )
        return await merge_tags(merge_request)

    class ExecuteCommandRequest(BaseModel):
        command: str = Field(..., description="Command to execute (e.g., 'ls', 'cd /news', 'get /item')")
        path: str = Field("", description="Current working path context")

    @app.post("/api/execute")
    async def execute_command(request: ExecuteCommandRequest = Body(...)) -> Dict:
        """Execute a REPL command and return the result."""
        import shlex
        base = api.get_base_url(None)
        current_path = request.path
        
        parts = shlex.split(request.command)
        if not parts:
            return {"success": False, "error": "Empty command", "output": "", "new_path": current_path}
        
        cmd = parts[0].lower()
        args = parts[1:]
        
        try:
            if cmd == "help":
                help_text = """
Navigation:
  ls [path] - List items in current directory
  cd <path> - Change directory (use '..' to go up)
  pwd - Show current path

Content:
  get [path] - Fetch and display content
  items [path] - List items array
  raw [path] - Show raw JSON response

Tags:
  tags [path] - List all tags with frequency
  similar-tags [tag] [threshold] - Find similar tags

Other:
  components - List available components
                """
                return {"success": True, "output": help_text.strip(), "new_path": current_path}
            
            elif cmd == "pwd":
                path_display = current_path if current_path else "/"
                return {"success": True, "output": path_display, "new_path": current_path}
            
            elif cmd == "cd":
                if not args:
                    return {"success": False, "error": "cd requires a path", "output": "", "new_path": current_path}
                new_path = args[0]
                if new_path == "..":
                    # Go up one level
                    if current_path:
                        parts = current_path.rstrip("/").split("/")
                        new_path = "/".join(parts[:-1]) if len(parts) > 1 else ""
                    else:
                        new_path = ""
                elif new_path.startswith("/"):
                    new_path = new_path.lstrip("/")
                else:
                    # Relative path
                    if current_path:
                        new_path = f"{current_path.rstrip('/')}/{new_path}"
                    else:
                        new_path = new_path
                return {"success": True, "output": f"Changed to: /{new_path}", "new_path": new_path}
            
            elif cmd == "ls":
                target_path = args[0] if args else current_path
                url, data = api.fetch(target_path, base, headers={}, params={}, no_auth=False)
                items = data.get("items", [])
                if not items:
                    return {"success": True, "output": "No items found", "new_path": current_path}
                output_lines = [f"Found {len(items)} items:"]
                for item in items[:50]:  # Limit to 50 items
                    title = item.get("title") or item.get("id", "untitled")
                    item_type = item.get("@type", "unknown")
                    output_lines.append(f"  {title} ({item_type})")
                if len(items) > 50:
                    output_lines.append(f"  ... and {len(items) - 50} more")
                return {"success": True, "output": "\n".join(output_lines), "new_path": current_path, "url": url}
            
            elif cmd == "get":
                target_path = args[0] if args else current_path
                url, data = api.fetch(target_path, base, headers={}, params={}, no_auth=False)
                title = data.get("title", data.get("id", "untitled"))
                item_type = data.get("@type", "unknown")
                output_lines = [
                    f"Title: {title}",
                    f"Type: {item_type}",
                    f"URL: {url}"
                ]
                if data.get("description"):
                    output_lines.append(f"Description: {data.get('description')}")
                return {"success": True, "output": "\n".join(output_lines), "new_path": current_path, "url": url, "data": data}
            
            elif cmd == "items":
                target_path = args[0] if args else current_path
                url, data = api.fetch(target_path, base, headers={}, params={}, no_auth=False)
                items = data.get("items", [])
                if not items:
                    return {"success": True, "output": "No items array found", "new_path": current_path}
                output_lines = [f"Items ({len(items)}):"]
                for item in items[:20]:
                    title = item.get("title") or item.get("id", "untitled")
                    output_lines.append(f"  - {title}")
                if len(items) > 20:
                    output_lines.append(f"  ... and {len(items) - 20} more")
                return {"success": True, "output": "\n".join(output_lines), "new_path": current_path, "url": url}
            
            elif cmd == "raw":
                target_path = args[0] if args else current_path
                url, data = api.fetch(target_path, base, headers={}, params={}, no_auth=False)
                import json
                return {"success": True, "output": json.dumps(data, indent=2), "new_path": current_path, "url": url}
            
            elif cmd == "tags":
                target_path = args[0] if args else current_path
                tag_counts = await asyncio.to_thread(api.get_all_tags, base, target_path, False, False, None, None)
                if not tag_counts:
                    return {"success": True, "output": "No tags found", "new_path": current_path}
                sorted_tags = sorted(tag_counts.items(), key=lambda x: (-x[1], x[0].lower()))
                output_lines = [f"Tags ({len(tag_counts)} unique):"]
                for tag, count in sorted_tags[:50]:
                    output_lines.append(f"  {tag}: {count}")
                if len(sorted_tags) > 50:
                    output_lines.append(f"  ... and {len(sorted_tags) - 50} more")
                return {"success": True, "output": "\n".join(output_lines), "new_path": current_path}
            
            else:
                return {"success": False, "error": f"Unknown command: {cmd}. Type 'help' for available commands.", "output": "", "new_path": current_path}
        
        except api.APIError as exc:
            return {"success": False, "error": str(exc), "output": "", "new_path": current_path}
        except Exception as exc:
            return {"success": False, "error": f"Error: {str(exc)}", "output": "", "new_path": current_path}

    @app.post("/api/tags/remove")
    async def remove_tag(request: RemoveTagRequest = Body(...)) -> Dict:
        base = api.get_base_url(None)
        items = await asyncio.to_thread(api.search_by_subject, base, request.tag, request.path, request.no_auth)

        if not items:
            return {"updated": 0, "errors": 0, "items": 0, "dry_run": request.dry_run, "message": "No matching items found."}

        preview = []
        for item in items[:10]:
            current_tags = item.get("subjects", [])
            new_tags = [tag for tag in current_tags if tag != request.tag]
            preview.append(
                {
                    "title": item.get("title", item.get("id")),
                    "current": current_tags,
                    "updated": new_tags,
                }
            )

        if request.dry_run:
            return {
                "updated": 0,
                "errors": 0,
                "items": len(items),
                "preview": preview,
                "dry_run": True,
            }

        updated = 0
        errors = 0
        for item in items:
            try:
                item_path = _item_path_from_id(item.get("@id"), base)
                current_tags = item.get("subjects", [])
                new_tags = [tag for tag in current_tags if tag != request.tag]
                await asyncio.to_thread(
                    api.update_item_subjects,
                    base,
                    item_path,
                    new_tags,
                    request.no_auth,
                )
                updated += 1
            except Exception:
                errors += 1

        return {
            "updated": updated,
            "errors": errors,
            "items": len(items),
            "preview": preview,
            "dry_run": False,
        }

    return app


def run_server(
    host: str = "127.0.0.1",
    port: int = 8787,
    reload: bool = False,
    allowed_origins: Optional[List[str]] = None,
) -> None:
    """Run the FastAPI server with uvicorn."""
    app = create_app(allowed_origins=allowed_origins)
    uvicorn.run(app, host=host, port=port, reload=reload)


if __name__ == "__main__":
    run_server()

