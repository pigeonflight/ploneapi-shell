use axum::{
    extract::{Query, Request, State},
    http::StatusCode,
    middleware::Next,
    response::{Json, Response},
    routing::{get, post},
    Router,
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::Mutex;
use tower_http::cors::{Any, CorsLayer};

use crate::api::APIClient;

#[derive(Clone)]
pub struct AppState {
    pub api_client: Arc<Mutex<APIClient>>,
    pub progress: Arc<Mutex<ProgressState>>,
}

#[derive(Default, Clone)]
pub struct ProgressState {
    pub current: usize,
    pub total: usize,
    pub message: String,
}

#[derive(Deserialize)]
struct LoginRequest {
    base_url: String,
    username: String,
    password: String,
}

#[derive(Serialize)]
struct LoginResponse {
    status: String,
    base_url: String,
}

#[derive(Serialize)]
struct HealthResponse {
    status: String,
}

#[derive(Serialize)]
struct ConfigResponse {
    base_url: String,
}

#[derive(Serialize)]
struct LogoutResponse {
    status: String,
}

#[derive(Deserialize)]
struct GetQuery {
    path: Option<String>,
    raw: Option<bool>,
}

#[derive(Deserialize)]
struct ItemsQuery {
    path: Option<String>,
}

#[derive(Deserialize)]
struct TagsQuery {
    path: Option<String>,
    no_auth: Option<bool>,
}

#[derive(Deserialize)]
struct SimilarTagsQuery {
    tag: Option<String>,
    path: Option<String>,
    threshold: Option<i32>,
    no_auth: Option<bool>,
}

#[derive(Deserialize)]
struct MergeTagsRequest {
    sources: Vec<String>,
    target: String,
    path: Option<String>,
    dry_run: Option<bool>,
    no_auth: Option<bool>,
}

#[derive(Deserialize)]
struct RenameTagRequest {
    old_tag: String,
    new_tag: String,
    path: Option<String>,
    dry_run: Option<bool>,
    no_auth: Option<bool>,
}

#[derive(Deserialize)]
struct RemoveTagRequest {
    tag: String,
    path: Option<String>,
    dry_run: Option<bool>,
    no_auth: Option<bool>,
}

#[derive(Deserialize)]
struct ExecuteCommandRequest {
    command: String,
    path: String,
}

fn serialize_item(item: &Value) -> Value {
    serde_json::json!({
        "id": item.get("id"),
        "title": item.get("title"),
        "type": item.get("@type"),
        "review_state": item.get("review_state"),
        "modified": item.get("modified"),
        "path": item.get("@id"),
        "description": item.get("description"),
    })
}

pub fn create_app() -> Router {
    let api_client = Arc::new(Mutex::new(
        APIClient::new().expect("Failed to create API client"),
    ));
    
    let state = AppState { 
        api_client,
        progress: Arc::new(Mutex::new(ProgressState::default())),
    };
    
    let cors = CorsLayer::new()
        .allow_origin(Any)
        .allow_methods(Any)
        .allow_headers(Any);
    
    Router::new()
        .route("/", get(root))
        .route("/api/health", get(health))
        .route("/api/config", get(get_config))
        .route("/api/login", post(login))
        .route("/api/logout", post(logout))
        .route("/api/get", get(get_content))
        .route("/api/items", get(list_items))
        .route("/api/tags", get(list_tags))
        .route("/api/similar-tags", get(similar_tags))
        .route("/api/similar-tags/progress", get(similar_tags_progress))
        .route("/api/tags/merge", post(merge_tags))
        .route("/api/tags/rename", post(rename_tag))
        .route("/api/tags/remove", post(remove_tag))
        .route("/api/execute", post(execute_command))
        .layer(axum::middleware::from_fn(logging_middleware))
        .layer(cors)
        .with_state(state)
}

async fn logging_middleware(request: Request, next: Next) -> Response {
    let method = request.method().clone();
    let uri = request.uri().clone();
    let path = uri.path();
    let query = uri.query().unwrap_or("");
    
    log::info!("{} {}?{}", method, path, query);
    
    let response = next.run(request).await;
    let status = response.status();
    
    if status.is_server_error() {
        log::error!("{} {}?{} -> {} (Server Error)", method, path, query, status);
    } else if status.is_client_error() {
        log::warn!("{} {}?{} -> {} (Client Error)", method, path, query, status);
    }
    
    response
}

async fn root() -> Json<Value> {
    Json(serde_json::json!({
        "service": "Plone API Shell Server",
        "version": "1.0.0",
        "endpoints": {
            "health": "/api/health",
            "config": "/api/config",
            "login": "/api/login",
            "logout": "/api/logout",
            "get": "/api/get",
            "items": "/api/items",
            "tags": "/api/tags",
            "similar_tags": "/api/similar-tags",
            "merge_tags": "/api/tags/merge",
            "rename_tag": "/api/tags/rename",
            "remove_tag": "/api/tags/remove",
            "execute": "/api/execute"
        }
    }))
}

async fn health() -> Json<HealthResponse> {
    Json(HealthResponse {
        status: "ok".to_string(),
    })
}

async fn get_config(State(state): State<AppState>) -> Json<ConfigResponse> {
    let client = state.api_client.lock().await;
    let base_url = client.get_base_url().await;
    Json(ConfigResponse { base_url })
}

async fn login(
    State(state): State<AppState>,
    Json(request): Json<LoginRequest>,
) -> Result<Json<LoginResponse>, (StatusCode, Json<Value>)> {
    log::info!("Login attempt for base_url: {}", request.base_url);
    let client = state.api_client.lock().await;
    client
        .login(&request.base_url, &request.username, &request.password)
        .await
        .map_err(|e| {
            log::error!("Login failed: {}", e);
            (
                StatusCode::BAD_REQUEST,
                Json(serde_json::json!({
                    "error": format!("Login failed: {}", e)
                })),
            )
        })?;
    Ok(Json(LoginResponse {
        status: "ok".to_string(),
        base_url: request.base_url,
    }))
}

async fn logout(State(state): State<AppState>) -> Json<LogoutResponse> {
    let client = state.api_client.lock().await;
    client.delete_config().await.ok();
    Json(LogoutResponse {
        status: "ok".to_string(),
    })
}

async fn get_content(
    State(state): State<AppState>,
    Query(params): Query<GetQuery>,
) -> Result<Json<Value>, StatusCode> {
    let client = state.api_client.lock().await;
    let (url, data) = client
        .fetch(params.path.as_deref(), None, None, false)
        .await
        .map_err(|_| StatusCode::BAD_REQUEST)?;
    
    if params.raw.unwrap_or(false) {
        Ok(Json(serde_json::json!({
            "url": url,
            "data": data
        })))
    } else {
        let summary = serde_json::json!({
            "title": data.get("title"),
            "id": data.get("id"),
            "type": data.get("@type"),
            "description": data.get("description"),
            "items_count": data.get("items").and_then(|v| v.as_array()).map(|a| a.len()).unwrap_or(0),
        });
        Ok(Json(serde_json::json!({
            "url": url,
            "summary": summary,
            "data": data
        })))
    }
}

async fn list_items(
    State(state): State<AppState>,
    Query(params): Query<ItemsQuery>,
) -> Result<Json<Value>, (StatusCode, Json<Value>)> {
    log::info!("list_items called with path: {:?}", params.path);
    let client = state.api_client.lock().await;
    let (url, data) = client
        .fetch(params.path.as_deref(), None, None, false)
        .await
        .map_err(|e| {
            log::error!("Failed to fetch items: {}", e);
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(serde_json::json!({
                    "error": format!("Failed to fetch items: {}", e)
                })),
            )
        })?;
    
    let items = data
        .get("items")
        .and_then(|v| v.as_array())
        .ok_or_else(|| {
            log::error!("Response does not contain 'items' array");
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(serde_json::json!({
                    "error": "Response does not contain 'items' array"
                })),
            )
        })?;
    
    let serialized_items: Vec<Value> = items.iter().map(serialize_item).collect();
    
    Ok(Json(serde_json::json!({
        "url": url,
        "items": serialized_items
    })))
}

async fn list_tags(
    State(state): State<AppState>,
    Query(params): Query<TagsQuery>,
) -> Result<Json<Value>, (StatusCode, Json<Value>)> {
    log::info!("list_tags called with path: {:?}, no_auth: {:?}", params.path, params.no_auth);
    let client = state.api_client.lock().await;
    let tag_counts = client
        .get_all_tags(params.path.as_deref(), params.no_auth.unwrap_or(false))
        .await
        .map_err(|e| {
            log::error!("Failed to get tags: {} (path: {:?})", e, params.path);
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(serde_json::json!({
                    "error": format!("Failed to get tags: {}", e),
                    "path": params.path
                })),
            )
        })?;
    
    let mut tags: Vec<Value> = tag_counts
        .iter()
        .map(|(name, count)| {
            serde_json::json!({
                "name": name,
                "count": count
            })
        })
        .collect();
    
    tags.sort_by(|a, b| {
        let count_a = a.get("count").and_then(|v| v.as_i64()).unwrap_or(0);
        let count_b = b.get("count").and_then(|v| v.as_i64()).unwrap_or(0);
        count_b.cmp(&count_a).then_with(|| {
            let name_a = a.get("name").and_then(|v| v.as_str()).unwrap_or("");
            let name_b = b.get("name").and_then(|v| v.as_str()).unwrap_or("");
            name_a.to_lowercase().cmp(&name_b.to_lowercase())
        })
    });
    
    Ok(Json(serde_json::json!({
        "path": params.path.unwrap_or_default(),
        "total": tags.len(),
        "tags": tags
    })))
}

async fn similar_tags(
    State(state): State<AppState>,
    Query(params): Query<SimilarTagsQuery>,
) -> Result<Json<Value>, (StatusCode, Json<Value>)> {
    log::info!("similar_tags called with tag: {:?}, path: {:?}, threshold: {:?}", 
        params.tag, params.path, params.threshold);
    
    // Check if user is logged in before attempting to fetch tags
    let client = state.api_client.lock().await;
    let base = client.get_base_url().await;
    
    if base.is_empty() {
        log::warn!("similar_tags called but user is not logged in (no base URL)");
        return Err((
            StatusCode::UNAUTHORIZED,
            Json(serde_json::json!({
                "error": "Not logged in. Please log in first.",
                "tag": params.tag,
                "path": params.path,
                "threshold": params.threshold
            })),
        ));
    }
    
    // Reset progress
    {
        let mut progress = state.progress.lock().await;
        *progress = ProgressState {
            current: 0,
            total: 0,
            message: "Starting...".to_string(),
        };
    }
    
    // Get tag counts first to know total
    let tag_counts = client
        .get_all_tags(params.path.as_deref(), params.no_auth.unwrap_or(false))
        .await
        .map_err(|e| {
            log::error!("Failed to get tags: {}", e);
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(serde_json::json!({
                    "error": format!("Failed to get tags: {}", e)
                })),
            )
        })?;
    
    let total_tags = tag_counts.len();
    {
        let mut progress = state.progress.lock().await;
        progress.total = total_tags;
        progress.message = format!("Processing {} tags...", total_tags);
    }
    
    // Now find similar tags with progress updates
    let results = client
        .find_similar_tags_with_progress(
            params.tag.as_deref(),
            params.path.as_deref(),
            params.threshold.unwrap_or(70),
            params.no_auth.unwrap_or(false),
            Some(state.progress.clone()),
        )
        .await
        .map_err(|e| {
            log::error!("Failed to find similar tags: {} (tag: {:?}, path: {:?}, threshold: {:?}, base: {})", 
                e, params.tag, params.path, params.threshold, base);
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(serde_json::json!({
                    "error": format!("Failed to find similar tags: {}", e),
                    "tag": params.tag,
                    "path": params.path,
                    "threshold": params.threshold
                })),
            )
        })?;
    
    let serialized: Vec<Value> = results
        .iter()
        .map(|(tag, count, similarity, matched)| {
            serde_json::json!({
                "tag": tag,
                "count": count,
                "similarity": similarity,
                "matched": matched
            })
        })
        .collect();
    
    Ok(Json(serde_json::json!({
        "path": params.path.unwrap_or_default(),
        "threshold": params.threshold.unwrap_or(70),
        "query": params.tag,
        "results": serialized
    })))
}

async fn similar_tags_progress(
    State(state): State<AppState>,
) -> Json<Value> {
    let progress = state.progress.lock().await;
    Json(serde_json::json!({
        "current": progress.current,
        "total": progress.total,
        "message": progress.message.clone(),
        "percent": if progress.total > 0 {
            (progress.current as f64 / progress.total as f64 * 100.0) as i32
        } else {
            0
        }
    }))
}

async fn merge_tags(
    State(state): State<AppState>,
    Json(request): Json<MergeTagsRequest>,
) -> Result<Json<Value>, StatusCode> {
    let client = state.api_client.lock().await;
    
    // Collect items for all source tags
    let mut all_items: HashMap<String, Value> = HashMap::new();
    let mut tag_counts: HashMap<String, usize> = HashMap::new();
    
    for source_tag in &request.sources {
        if let Ok(items) = client
            .search_by_subject(
                source_tag,
                request.path.as_deref(),
                request.no_auth.unwrap_or(false),
            )
            .await
        {
            tag_counts.insert(source_tag.clone(), items.len());
            for item in items {
                if let Some(item_id) = item.get("@id").and_then(|v| v.as_str()) {
                    all_items.insert(item_id.to_string(), item);
                }
            }
        }
    }
    
    let items_list: Vec<Value> = all_items.values().cloned().collect();
    
    if items_list.is_empty() {
        return Ok(Json(serde_json::json!({
            "updated": 0,
            "errors": 0,
            "items": 0,
            "dry_run": request.dry_run.unwrap_or(false),
            "message": "No matching items found."
        })));
    }
    
    // Build preview
    let mut preview = Vec::new();
    for item in items_list.iter().take(10) {
            let current_tags = item
                .get("subjects")
                .and_then(|v| v.as_array())
                .cloned()
                .unwrap_or_else(|| vec![]);
            
            let mut new_tags: Vec<Value> = current_tags
                .iter()
                .filter(|v| {
                    if let Some(tag) = v.as_str() {
                        !request.sources.contains(&tag.to_string())
                    } else {
                        true
                    }
                })
                .cloned()
                .collect();
        
        if !new_tags.iter().any(|v| {
            v.as_str().map(|s| s == request.target).unwrap_or(false)
        }) {
            new_tags.push(Value::String(request.target.clone()));
        }
        
        preview.push(serde_json::json!({
            "title": item.get("title").or_else(|| item.get("id")),
            "current": current_tags,
            "updated": new_tags
        }));
    }
    
    if request.dry_run.unwrap_or(false) {
        return Ok(Json(serde_json::json!({
            "updated": 0,
            "errors": 0,
            "items": items_list.len(),
            "preview": preview,
            "tag_counts": tag_counts,
            "dry_run": true
        })));
    }
    
    // Perform actual merge
    let mut updated = 0;
    let mut errors = 0;
    
    for item in &items_list {
        if let Some(item_id) = item.get("@id").and_then(|v| v.as_str()) {
            let item_path = item_id
                .trim_start_matches(&client.get_base_url().await)
                .trim_start_matches('/');
            
            let current_tags = item
                .get("subjects")
                .and_then(|v| v.as_array())
                .cloned()
                .unwrap_or_else(|| vec![]);
            
            let mut new_tags: Vec<String> = current_tags
                .iter()
                .filter_map(|v| v.as_str())
                .filter(|tag| !request.sources.contains(&tag.to_string()))
                .map(|s| s.to_string())
                .collect();
            
            if !new_tags.contains(&request.target) {
                new_tags.push(request.target.clone());
            }
            
            if client
                .update_item_subjects(
                    item_path,
                    new_tags,
                    request.no_auth.unwrap_or(false),
                )
                .await
                .is_ok()
            {
                updated += 1;
            } else {
                errors += 1;
            }
        }
    }
    
    Ok(Json(serde_json::json!({
        "updated": updated,
        "errors": errors,
        "items": items_list.len(),
        "tag_counts": tag_counts,
        "preview": preview,
        "dry_run": false
    })))
}

async fn rename_tag(
    State(state): State<AppState>,
    Json(request): Json<RenameTagRequest>,
) -> Result<Json<Value>, StatusCode> {
    let merge_request = MergeTagsRequest {
        sources: vec![request.old_tag],
        target: request.new_tag,
        path: request.path,
        dry_run: request.dry_run,
        no_auth: request.no_auth,
    };
    merge_tags(State(state), Json(merge_request)).await
}

async fn remove_tag(
    State(state): State<AppState>,
    Json(request): Json<RemoveTagRequest>,
) -> Result<Json<Value>, StatusCode> {
    let client = state.api_client.lock().await;
    
    let items = client
        .search_by_subject(
            &request.tag,
            request.path.as_deref(),
            request.no_auth.unwrap_or(false),
        )
        .await
        .map_err(|_| StatusCode::BAD_REQUEST)?;
    
    if items.is_empty() {
        return Ok(Json(serde_json::json!({
            "updated": 0,
            "errors": 0,
            "items": 0,
            "dry_run": request.dry_run.unwrap_or(false),
            "message": "No matching items found."
        })));
    }
    
    // Build preview
        let mut preview = Vec::new();
        for item in items.iter().take(10) {
            let current_tags = item
                .get("subjects")
                .and_then(|v| v.as_array())
                .cloned()
                .unwrap_or_else(|| vec![]);
            
            let new_tags: Vec<Value> = current_tags
                .iter()
                .filter(|v| {
                    v.as_str().map(|s| s != request.tag).unwrap_or(true)
                })
                .cloned()
                .collect();
        
        preview.push(serde_json::json!({
            "title": item.get("title").or_else(|| item.get("id")),
            "current": current_tags,
            "updated": new_tags
        }));
    }
    
    if request.dry_run.unwrap_or(false) {
        return Ok(Json(serde_json::json!({
            "updated": 0,
            "errors": 0,
            "items": items.len(),
            "preview": preview,
            "dry_run": true
        })));
    }
    
    // Perform actual removal
    let mut updated = 0;
    let mut errors = 0;
    
    for item in &items {
        if let Some(item_id) = item.get("@id").and_then(|v| v.as_str()) {
            let item_path = item_id
                .trim_start_matches(&client.get_base_url().await)
                .trim_start_matches('/');
            
            let current_tags = item
                .get("subjects")
                .and_then(|v| v.as_array())
                .cloned()
                .unwrap_or_else(|| vec![]);
            
            let new_tags: Vec<String> = current_tags
                .iter()
                .filter_map(|v| v.as_str())
                .filter(|tag| *tag != request.tag)
                .map(|s| s.to_string())
                .collect();
            
            if client
                .update_item_subjects(
                    item_path,
                    new_tags,
                    request.no_auth.unwrap_or(false),
                )
                .await
                .is_ok()
            {
                updated += 1;
            } else {
                errors += 1;
            }
        }
    }
    
    Ok(Json(serde_json::json!({
        "updated": updated,
        "errors": errors,
        "items": items.len(),
        "preview": preview,
        "dry_run": false
    })))
}

async fn execute_command(
    State(state): State<AppState>,
    Json(request): Json<ExecuteCommandRequest>,
) -> Json<Value> {
    let client = state.api_client.lock().await;
    let current_path = request.path;
    
    let parts: Vec<&str> = request.command.split_whitespace().collect();
    if parts.is_empty() {
        return Json(serde_json::json!({
            "success": false,
            "error": "Empty command",
            "output": "",
            "new_path": current_path
        }));
    }
    
    let cmd = parts[0].to_lowercase();
    let args = &parts[1..];
    
    match cmd.as_str() {
        "help" => {
            let help_text = "Navigation:\n  ls [path] - List items in current directory\n  cd <path> - Change directory (use '..' to go up)\n  pwd - Show current path\n\nContent:\n  get [path] - Fetch and display content\n  items [path] - List items array\n  raw [path] - Show raw JSON response\n\nTags:\n  tags [path] - List all tags with frequency\n  similar-tags [tag] [threshold] - Find similar tags";
            Json(serde_json::json!({
                "success": true,
                "output": help_text,
                "new_path": current_path
            }))
        }
        "pwd" => {
            let path_display = if current_path.is_empty() { "/" } else { &current_path };
            Json(serde_json::json!({
                "success": true,
                "output": path_display,
                "new_path": current_path
            }))
        }
        "cd" => {
            if args.is_empty() {
                return Json(serde_json::json!({
                    "success": false,
                    "error": "cd requires a path",
                    "output": "",
                    "new_path": current_path
                }));
            }
            
            let new_path = if args[0] == ".." {
                if current_path.is_empty() {
                    "".to_string()
                } else {
                    let parts: Vec<&str> = current_path.trim_end_matches('/').split('/').collect();
                    if parts.len() > 1 {
                        parts[..parts.len() - 1].join("/")
                    } else {
                        "".to_string()
                    }
                }
            } else if args[0].starts_with('/') {
                args[0].trim_start_matches('/').to_string()
            } else {
                if current_path.is_empty() {
                    args[0].to_string()
                } else {
                    format!("{}/{}", current_path.trim_end_matches('/'), args[0])
                }
            };
            
            let _ = new_path.clone();
            Json(serde_json::json!({
                "success": true,
                "output": format!("Changed to: /{}", new_path),
                "new_path": new_path
            }))
        }
        "ls" => {
            let target_path = if args.is_empty() {
                current_path.as_str()
            } else {
                args[0]
            };
            
            match client.fetch(Some(target_path), None, None, false).await {
                Ok((url, data)) => {
                    let empty_vec = vec![];
                    let items = data.get("items").and_then(|v| v.as_array()).unwrap_or(&empty_vec);
                    if items.is_empty() {
                        return Json(serde_json::json!({
                            "success": true,
                            "output": "No items found",
                            "new_path": current_path
                        }));
                    }
                    
                    let mut output_lines = vec![format!("Found {} items:", items.len())];
                    for item in items.iter().take(50) {
                        let title = item
                            .get("title")
                            .or_else(|| item.get("id"))
                            .and_then(|v| v.as_str())
                            .unwrap_or("untitled");
                        let item_type = item
                            .get("@type")
                            .and_then(|v| v.as_str())
                            .unwrap_or("unknown");
                        output_lines.push(format!("  {} ({})", title, item_type));
                    }
                    if items.len() > 50 {
                        output_lines.push(format!("  ... and {} more", items.len() - 50));
                    }
                    
                    Json(serde_json::json!({
                        "success": true,
                        "output": output_lines.join("\n"),
                        "new_path": current_path,
                        "url": url
                    }))
                }
                Err(_) => Json(serde_json::json!({
                    "success": false,
                    "error": "Failed to fetch items",
                    "output": "",
                    "new_path": current_path
                })),
            }
        }
        "get" => {
            let target_path = if args.is_empty() {
                current_path.as_str()
            } else {
                args[0]
            };
            
            match client.fetch(Some(target_path), None, None, false).await {
                Ok((url, data)) => {
                    let title = data
                        .get("title")
                        .or_else(|| data.get("id"))
                        .and_then(|v| v.as_str())
                        .unwrap_or("untitled");
                    let item_type = data
                        .get("@type")
                        .and_then(|v| v.as_str())
                        .unwrap_or("unknown");
                    
                    let mut output_lines = vec![
                        format!("Title: {}", title),
                        format!("Type: {}", item_type),
                        format!("URL: {}", url),
                    ];
                    
                    if let Some(desc) = data.get("description").and_then(|v| v.as_str()) {
                        output_lines.push(format!("Description: {}", desc));
                    }
                    
                    Json(serde_json::json!({
                        "success": true,
                        "output": output_lines.join("\n"),
                        "new_path": current_path,
                        "url": url,
                        "data": data
                    }))
                }
                Err(_) => Json(serde_json::json!({
                    "success": false,
                    "error": "Failed to fetch content",
                    "output": "",
                    "new_path": current_path
                })),
            }
        }
        "items" => {
            let target_path = if args.is_empty() {
                current_path.as_str()
            } else {
                args[0]
            };
            
            match client.fetch(Some(target_path), None, None, false).await {
                Ok((url, data)) => {
                    let empty_vec = vec![];
                    let items = data.get("items").and_then(|v| v.as_array()).unwrap_or(&empty_vec);
                    if items.is_empty() {
                        return Json(serde_json::json!({
                            "success": true,
                            "output": "No items array found",
                            "new_path": current_path
                        }));
                    }
                    
                    let mut output_lines = vec![format!("Items ({})", items.len())];
                    for item in items.iter().take(20) {
                        let title = item
                            .get("title")
                            .or_else(|| item.get("id"))
                            .and_then(|v| v.as_str())
                            .unwrap_or("untitled");
                        output_lines.push(format!("  - {}", title));
                    }
                    if items.len() > 20 {
                        output_lines.push(format!("  ... and {} more", items.len() - 20));
                    }
                    
                    Json(serde_json::json!({
                        "success": true,
                        "output": output_lines.join("\n"),
                        "new_path": current_path,
                        "url": url
                    }))
                }
                Err(_) => Json(serde_json::json!({
                    "success": false,
                    "error": "Failed to fetch items",
                    "output": "",
                    "new_path": current_path
                })),
            }
        }
        "raw" => {
            let target_path = if args.is_empty() {
                current_path.as_str()
            } else {
                args[0]
            };
            
            match client.fetch(Some(target_path), None, None, false).await {
                Ok((url, data)) => {
                    Json(serde_json::json!({
                        "success": true,
                        "output": serde_json::to_string_pretty(&data).unwrap_or_default(),
                        "new_path": current_path,
                        "url": url
                    }))
                }
                Err(_) => Json(serde_json::json!({
                    "success": false,
                    "error": "Failed to fetch content",
                    "output": "",
                    "new_path": current_path
                })),
            }
        }
        "tags" => {
            let target_path = if args.is_empty() {
                current_path.as_str()
            } else {
                args[0]
            };
            
            match client.get_all_tags(Some(target_path), false).await {
                Ok(tag_counts) => {
                    if tag_counts.is_empty() {
                        return Json(serde_json::json!({
                            "success": true,
                            "output": "No tags found",
                            "new_path": current_path
                        }));
                    }
                    
                    let mut sorted_tags: Vec<_> = tag_counts.iter().collect();
                    sorted_tags.sort_by(|a, b| {
                        b.1.cmp(a.1).then_with(|| a.0.to_lowercase().cmp(&b.0.to_lowercase()))
                    });
                    
                    let mut output_lines = vec![format!("Tags ({} unique):", tag_counts.len())];
                    for (tag, count) in sorted_tags.iter().take(50) {
                        output_lines.push(format!("  {}: {}", tag, count));
                    }
                    if sorted_tags.len() > 50 {
                        output_lines.push(format!("  ... and {} more", sorted_tags.len() - 50));
                    }
                    
                    Json(serde_json::json!({
                        "success": true,
                        "output": output_lines.join("\n"),
                        "new_path": current_path
                    }))
                }
                Err(_) => Json(serde_json::json!({
                    "success": false,
                    "error": "Failed to fetch tags",
                    "output": "",
                    "new_path": current_path
                })),
            }
        }
        _ => Json(serde_json::json!({
            "success": false,
            "error": format!("Unknown command: {}. Type 'help' for available commands.", cmd),
            "output": "",
            "new_path": current_path
        })),
    }
}

pub async fn run_server(host: &str, port: u16) -> Result<(), Box<dyn std::error::Error>> {
    let app = create_app();
    
    let listener = tokio::net::TcpListener::bind(format!("{}:{}", host, port)).await?;
    log::info!("Server listening on {}:{}", host, port);
    
    axum::serve(listener, app).await?;
    
    Ok(())
}

