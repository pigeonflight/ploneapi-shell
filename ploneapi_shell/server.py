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

