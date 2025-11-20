use base64::Engine;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;
use tokio::sync::Mutex;
use url::Url;

pub const DEFAULT_BASE: &str = "https://demo.plone.org/++api++/";
const TOKEN_REFRESH_LEEWAY: i64 = 120; // seconds before expiry to proactively renew
const TOKEN_REFRESH_MIN_INTERVAL: i64 = 30; // avoid hammering renew endpoint

#[derive(Debug, Clone)]
pub struct Config {
    pub base: String,
    pub auth: Option<AuthData>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuthData {
    pub mode: String,
    pub token: String,
    pub updated_at: i64,
    pub username: Option<String>,
    pub token_exp: Option<i64>,
}

#[derive(Debug, thiserror::Error)]
pub enum APIError {
    #[error("Request failed with status {0} for {1}")]
    HttpStatus(u16, String),
    #[error("Unable to reach {0}: {1}")]
    RequestError(String, String),
    #[error("Response is not JSON")]
    InvalidJson,
    #[error("{0}")]
    Other(String),
}

pub struct APIClient {
    config_path: PathBuf,
    client: reqwest::Client,
    config: Arc<Mutex<Config>>,
}

impl APIClient {
    pub fn new() -> Result<Self, APIError> {
        let config_path = dirs::home_dir()
            .ok_or_else(|| APIError::Other("Could not find home directory".to_string()))?
            .join(".config")
            .join("ploneapi_shell")
            .join("config.json");

        let config = Self::load_config(&config_path)?;
        
        Ok(Self {
            config_path,
            client: reqwest::Client::new(),
            config: Arc::new(Mutex::new(config)),
        })
    }

    fn load_config(path: &PathBuf) -> Result<Config, APIError> {
        if path.exists() {
            let content = std::fs::read_to_string(path)
                .map_err(|e| APIError::Other(format!("Failed to read config: {}", e)))?;
            let value: Value = serde_json::from_str(&content)
                .map_err(|_| APIError::Other("Invalid JSON in config".to_string()))?;
            
            let base = value
                .get("base")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string())
                .unwrap_or_else(|| DEFAULT_BASE.to_string());
            
            let auth = value.get("auth").and_then(|v| {
                serde_json::from_value::<AuthData>(v.clone()).ok()
            });
            
            Ok(Config { base, auth })
        } else {
            Ok(Config {
                base: DEFAULT_BASE.to_string(),
                auth: None,
            })
        }
    }

    pub async fn save_config(&self) -> Result<(), APIError> {
        let config = self.config.lock().await;
        if let Some(parent) = self.config_path.parent() {
            std::fs::create_dir_all(parent)
                .map_err(|e| APIError::Other(format!("Failed to create config dir: {}", e)))?;
        }
        
        let mut value = serde_json::json!({
            "base": config.base
        });
        
        if let Some(auth) = &config.auth {
            value["auth"] = serde_json::to_value(auth)
                .map_err(|e| APIError::Other(format!("Failed to serialize auth: {}", e)))?;
        }
        
        std::fs::write(&self.config_path, serde_json::to_string_pretty(&value).unwrap())
            .map_err(|e| APIError::Other(format!("Failed to write config: {}", e)))?;
        
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            std::fs::set_permissions(&self.config_path, std::fs::Permissions::from_mode(0o600))
                .ok();
        }
        
        Ok(())
    }

    pub async fn delete_config(&self) -> Result<(), APIError> {
        std::fs::remove_file(&self.config_path).ok();
        let mut config = self.config.lock().await;
        config.auth = None;
        self.save_config().await
    }

    pub async fn get_base_url(&self) -> String {
        let config = self.config.lock().await;
        config.base.clone()
    }

    pub async fn set_base_url(&self, base: String) -> Result<(), APIError> {
        let mut config = self.config.lock().await;
        config.base = base;
        config.auth = None; // Clear auth when base changes
        self.save_config().await
    }

    fn resolve_url(&self, path_or_url: Option<&str>, base: &str) -> String {
        if let Some(path) = path_or_url {
            if path.starts_with("http://") || path.starts_with("https://") {
                return path.to_string();
            }
        }
        
        let base_url = base.trim_end_matches('/');
        let path = path_or_url
            .map(|p| p.trim_start_matches('/'))
            .unwrap_or("");
        
        format!("{}/{}", base_url, path)
    }

    fn decode_jwt_exp(token: &str) -> Option<i64> {
        let parts: Vec<&str> = token.split('.').collect();
        if parts.len() < 2 {
            return None;
        }
        
        let payload_segment = parts[1];
        let padding = "=".repeat((4 - payload_segment.len() % 4) % 4);
        let payload_str = format!("{}{}", payload_segment, padding);
        
        if let Ok(payload_bytes) = base64::engine::general_purpose::URL_SAFE.decode(&payload_str) {
            if let Ok(payload) = serde_json::from_slice::<Value>(&payload_bytes) {
                return payload.get("exp").and_then(|v| v.as_i64());
            }
        }
        None
    }

    fn should_refresh_token(auth: &AuthData) -> bool {
        if let Some(token_exp) = auth.token_exp {
            let now = chrono::Utc::now().timestamp();
            if token_exp - TOKEN_REFRESH_LEEWAY <= now {
                let last_attempt = auth.updated_at;
                if now - last_attempt >= TOKEN_REFRESH_MIN_INTERVAL {
                    return true;
                }
            }
        }
        false
    }

    async fn renew_token(&self, base: &str, current_token: &str, username: Option<&str>) -> Option<String> {
        let renew_url = self.resolve_url(Some("@login-renew"), base);
        let response = self
            .client
            .post(&renew_url)
            .header("Authorization", format!("Bearer {}", current_token))
            .send()
            .await
            .ok()?;
        
        if response.status().is_success() {
            if let Ok(json) = response.json::<Value>().await {
                if let Some(new_token) = json.get("token").and_then(|v| v.as_str()) {
                    let token_exp = Self::decode_jwt_exp(new_token);
                    let mut config = self.config.lock().await;
                    config.auth = Some(AuthData {
                        mode: "token".to_string(),
                        token: new_token.to_string(),
                        updated_at: chrono::Utc::now().timestamp(),
                        username: username.map(|s| s.to_string()),
                        token_exp,
                    });
                    self.save_config().await.ok();
                    return Some(new_token.to_string());
                }
            }
        }
        None
    }

    fn get_auth_headers(&self, _base: &str, auth: &Option<AuthData>) -> HashMap<String, String> {
        let mut headers = HashMap::new();
        
        if let Some(auth_data) = auth {
            if auth_data.mode == "token" && !auth_data.token.is_empty() {
                let token = if Self::should_refresh_token(auth_data) {
                    // Try to refresh synchronously (in real implementation, this would be async)
                    // For now, just use the current token
                    &auth_data.token
                } else {
                    &auth_data.token
                };
                headers.insert("Authorization".to_string(), format!("Bearer {}", token));
            }
        }
        
        headers
    }

    pub async fn fetch(
        &self,
        path_or_url: Option<&str>,
        headers: Option<HashMap<String, String>>,
        params: Option<HashMap<String, String>>,
        no_auth: bool,
    ) -> Result<(String, Value), APIError> {
        let config = self.config.lock().await;
        let base = config.base.clone();
        let auth = config.auth.clone();
        drop(config);
        
        let url = self.resolve_url(path_or_url, &base);
        let mut request_headers = self.get_auth_headers(&base, &auth);
        
        if !no_auth {
            if let Some(custom_headers) = headers {
                request_headers.extend(custom_headers);
            }
        }
        
        let mut request = self.client.get(&url);
        
        for (key, value) in request_headers {
            request = request.header(&key, value);
        }
        
        if let Some(query_params) = params {
            request = request.query(&query_params);
        }
        
        let response = request
            .send()
            .await
            .map_err(|e| APIError::RequestError(url.clone(), e.to_string()))?;
        
        let status = response.status();
        if !status.is_success() {
            return Err(APIError::HttpStatus(status.as_u16(), url));
        }
        
        let json: Value = response
            .json()
            .await
            .map_err(|_| APIError::InvalidJson)?;
        
        Ok((url, json))
    }

    pub async fn post(
        &self,
        path_or_url: Option<&str>,
        json_data: Value,
        headers: Option<HashMap<String, String>>,
        no_auth: bool,
    ) -> Result<(String, Value), APIError> {
        let config = self.config.lock().await;
        let base = config.base.clone();
        let auth = config.auth.clone();
        drop(config);
        
        let url = self.resolve_url(path_or_url, &base);
        let mut request_headers = self.get_auth_headers(&base, &auth);
        request_headers.insert("Content-Type".to_string(), "application/json".to_string());
        
        if !no_auth {
            if let Some(custom_headers) = headers {
                request_headers.extend(custom_headers);
            }
        }
        
        let mut request = self.client.post(&url).json(&json_data);
        
        for (key, value) in request_headers {
            request = request.header(&key, value);
        }
        
        let response = request
            .send()
            .await
            .map_err(|e| APIError::RequestError(url.clone(), e.to_string()))?;
        
        let status = response.status();
        if !status.is_success() {
            return Err(APIError::HttpStatus(status.as_u16(), url));
        }
        
        let json: Value = response
            .json()
            .await
            .unwrap_or(Value::Object(serde_json::Map::new()));
        
        Ok((url, json))
    }

    pub async fn patch(
        &self,
        path_or_url: Option<&str>,
        json_data: Value,
        headers: Option<HashMap<String, String>>,
        no_auth: bool,
    ) -> Result<(String, Value), APIError> {
        let config = self.config.lock().await;
        let base = config.base.clone();
        let auth = config.auth.clone();
        drop(config);
        
        let url = self.resolve_url(path_or_url, &base);
        let mut request_headers = self.get_auth_headers(&base, &auth);
        request_headers.insert("Content-Type".to_string(), "application/json".to_string());
        request_headers.insert("Accept".to_string(), "application/json".to_string());
        
        if !no_auth {
            if let Some(custom_headers) = headers {
                request_headers.extend(custom_headers);
            }
        }
        
        let mut request = self.client.patch(&url).json(&json_data);
        
        for (key, value) in request_headers {
            request = request.header(&key, value);
        }
        
        let response = request
            .send()
            .await
            .map_err(|e| APIError::RequestError(url.clone(), e.to_string()))?;
        
        let status = response.status();
        if !status.is_success() {
            return Err(APIError::HttpStatus(status.as_u16(), url));
        }
        
        let json: Value = response
            .json()
            .await
            .unwrap_or(Value::Object(serde_json::Map::new()));
        
        Ok((url, json))
    }

    pub async fn login(&self, base: &str, username: &str, password: &str) -> Result<Value, APIError> {
        let login_url = self.resolve_url(Some("@login"), base);
        let response = self
            .client
            .post(&login_url)
            .json(&serde_json::json!({
                "login": username,
                "password": password
            }))
            .send()
            .await
            .map_err(|e| APIError::RequestError(login_url.clone(), e.to_string()))?;
        
        if !response.status().is_success() {
            return Err(APIError::HttpStatus(
                response.status().as_u16(),
                login_url,
            ));
        }
        
        let json: Value = response
            .json()
            .await
            .map_err(|_| APIError::InvalidJson)?;
        
        if let Some(token) = json.get("token").and_then(|v| v.as_str()) {
            let token_exp = Self::decode_jwt_exp(token);
            let mut config = self.config.lock().await;
            config.base = base.to_string();
            config.auth = Some(AuthData {
                mode: "token".to_string(),
                token: token.to_string(),
                updated_at: chrono::Utc::now().timestamp(),
                username: Some(username.to_string()),
                token_exp,
            });
            self.save_config().await?;
        } else {
            return Err(APIError::Other("Login response did not include a token".to_string()));
        }
        
        Ok(json)
    }

    pub async fn search_by_type(
        &self,
        portal_type: &str,
        path: Option<&str>,
        no_auth: bool,
    ) -> Result<Vec<Value>, APIError> {
        let config = self.config.lock().await;
        let base = config.base.clone();
        let auth = config.auth.clone();
        drop(config);
        
        let search_url = self.resolve_url(Some("@search"), &base);
        let mut params = HashMap::new();
        params.insert("portal_type".to_string(), portal_type.to_string());
        params.insert("b_size".to_string(), "1000".to_string());
        
        if let Some(p) = path {
            params.insert("path".to_string(), p.to_string());
        }
        
        let request_headers = self.get_auth_headers(&base, &auth);
        let mut request = self.client.get(&search_url);
        
        if !no_auth {
            for (key, value) in request_headers {
                request = request.header(&key, value);
            }
        }
        
        request = request.query(&params);
        
        let response = request
            .send()
            .await
            .map_err(|e| APIError::RequestError(search_url.clone(), e.to_string()))?;
        
        if !response.status().is_success() {
            return Err(APIError::HttpStatus(
                response.status().as_u16(),
                search_url,
            ));
        }
        
        let json: Value = response
            .json()
            .await
            .map_err(|_| APIError::InvalidJson)?;
        
        let items = json
            .get("items")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();
        
        Ok(items)
    }

    pub async fn search_by_subject(
        &self,
        subject: &str,
        path: Option<&str>,
        no_auth: bool,
    ) -> Result<Vec<Value>, APIError> {
        let config = self.config.lock().await;
        let base = config.base.clone();
        let auth = config.auth.clone();
        drop(config);
        
        let search_url = self.resolve_url(Some("@search"), &base);
        let mut params = HashMap::new();
        params.insert("Subject".to_string(), subject.to_string());
        params.insert("b_size".to_string(), "1000".to_string());
        
        if let Some(p) = path {
            params.insert("path".to_string(), p.to_string());
        }
        
        let request_headers = self.get_auth_headers(&base, &auth);
        let mut request = self.client.get(&search_url);
        
        if !no_auth {
            for (key, value) in request_headers {
                request = request.header(&key, value);
            }
        }
        
        request = request.query(&params);
        
        let response = request
            .send()
            .await
            .map_err(|e| APIError::RequestError(search_url.clone(), e.to_string()))?;
        
        if !response.status().is_success() {
            return Err(APIError::HttpStatus(
                response.status().as_u16(),
                search_url,
            ));
        }
        
        let json: Value = response
            .json()
            .await
            .map_err(|_| APIError::InvalidJson)?;
        
        let items = json
            .get("items")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();
        
        Ok(items)
    }

    pub async fn get_all_tags(
        &self,
        path: Option<&str>,
        no_auth: bool,
    ) -> Result<HashMap<String, i32>, APIError> {
        let config = self.config.lock().await;
        let base = config.base.clone();
        
        if base.is_empty() {
            return Err(APIError::Other("Not logged in. Please log in first.".to_string()));
        }
        
        let auth = config.auth.clone();
        drop(config);
        
        let search_url = self.resolve_url(Some("@search"), &base);
        let mut params = HashMap::new();
        params.insert("b_size".to_string(), "1000".to_string());
        params.insert("metadata_fields".to_string(), "_all".to_string());
        
        if let Some(p) = path {
            params.insert("path".to_string(), p.to_string());
        }
        
        let request_headers = self.get_auth_headers(&base, &auth);
        let mut request = self.client.get(&search_url);
        
        if !no_auth {
            for (key, value) in request_headers {
                request = request.header(&key, value);
            }
        }
        
        request = request.query(&params);
        
        let response = request
            .send()
            .await
            .map_err(|e| APIError::RequestError(search_url.clone(), e.to_string()))?;
        
        if !response.status().is_success() {
            return Err(APIError::HttpStatus(
                response.status().as_u16(),
                search_url,
            ));
        }
        
        let json: Value = response
            .json()
            .await
            .map_err(|_| APIError::InvalidJson)?;
        
        let items = json
            .get("items")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();
        
        let mut tag_counts = HashMap::new();
        
        for item in items {
            let subjects = item
                .get("Subject")
                .or_else(|| item.get("subject"))
                .or_else(|| item.get("subjects"));
            
            if let Some(subjects_value) = subjects {
                let subjects_list = if subjects_value.is_array() {
                    subjects_value.as_array().unwrap().iter()
                        .filter_map(|v| v.as_str())
                        .map(|s| s.to_string())
                        .collect::<Vec<_>>()
                } else if subjects_value.is_string() {
                    vec![subjects_value.as_str().unwrap().to_string()]
                } else {
                    vec![]
                };
                
                for subject in subjects_list {
                    *tag_counts.entry(subject).or_insert(0) += 1;
                }
            }
        }
        
        Ok(tag_counts)
    }

    pub async fn update_item_subjects(
        &self,
        item_path: &str,
        subjects: Vec<String>,
        no_auth: bool,
    ) -> Result<Value, APIError> {
        let _config = self.config.lock().await;
        
        let json_data = serde_json::json!({
            "Subject": subjects
        });
        
        self.patch(Some(item_path), json_data, None, no_auth)
            .await
            .map(|(_, data)| data)
    }

    pub async fn find_similar_tags(
        &self,
        query_tag: Option<&str>,
        path: Option<&str>,
        threshold: i32,
        no_auth: bool,
    ) -> Result<Vec<(String, i32, i32, Option<String>)>, APIError> {
        self.find_similar_tags_with_progress(query_tag, path, threshold, no_auth, None).await
    }
    
    pub async fn find_similar_tags_with_progress(
        &self,
        query_tag: Option<&str>,
        path: Option<&str>,
        threshold: i32,
        no_auth: bool,
        progress: Option<Arc<tokio::sync::Mutex<crate::server::ProgressState>>>,
    ) -> Result<Vec<(String, i32, i32, Option<String>)>, APIError> {
        let tag_counts = self.get_all_tags(path, no_auth).await?;
        
        if tag_counts.is_empty() {
            return Ok(vec![]);
        }
        
        if let Some(query) = query_tag {
            let query_lower = query.to_lowercase();
            let mut similar_tags = Vec::new();
            
            for (tag, count) in tag_counts {
                let similarity = (strsim::jaro_winkler(&query_lower, &tag.to_lowercase()) * 100.0) as i32;
                
                if similarity >= threshold {
                    similar_tags.push((tag, count, similarity, None));
                }
            }
            
            similar_tags.sort_by(|a, b| {
                b.2.cmp(&a.2)
                    .then_with(|| b.1.cmp(&a.1))
                    .then_with(|| a.0.to_lowercase().cmp(&b.0.to_lowercase()))
            });
            
            Ok(similar_tags)
        } else {
            // Find all pairs - optimized for performance
            let mut similar_pairs = Vec::new();
            let tag_list: Vec<_> = tag_counts.into_iter().collect();
            
            // Pre-compute lowercase versions to avoid repeated conversions
            let tag_list_lower: Vec<(String, String, i32)> = tag_list
                .iter()
                .map(|(tag, count)| (tag.clone(), tag.to_lowercase(), *count))
                .collect();
            
            // Only compare tags that could potentially be similar
            // Skip comparisons if length difference is too large (heuristic)
            let max_length_diff = 10; // Maximum character difference to consider
            
            for i in 0..tag_list_lower.len() {
                let (tag1, tag1_lower, count1) = &tag_list_lower[i];
                
                // Update progress every 10 tags processed
                if let Some(prog) = &progress {
                    if i % 10 == 0 {
                        let mut p = prog.lock().await;
                        p.current = i;
                        p.message = format!("Comparing tags: {}/{}", i, tag_list_lower.len());
                    }
                }
                
                for j in (i + 1)..tag_list_lower.len() {
                    let (tag2, tag2_lower, count2) = &tag_list_lower[j];
                    
                    // Quick length check to skip obviously different tags
                    let length_diff = (tag1_lower.len() as i32 - tag2_lower.len() as i32).abs();
                    if length_diff > max_length_diff {
                        continue;
                    }
                    
                    let similarity = (strsim::jaro_winkler(tag1_lower, tag2_lower) * 100.0) as i32;
                    
                    if similarity >= threshold {
                        if count1 >= count2 {
                            similar_pairs.push((tag1.clone(), *count1, similarity, Some(tag2.clone())));
                        } else {
                            similar_pairs.push((tag2.clone(), *count2, similarity, Some(tag1.clone())));
                        }
                    }
                }
            }
            
            similar_pairs.sort_by(|a, b| {
                b.2.cmp(&a.2)
                    .then_with(|| b.1.cmp(&a.1))
                    .then_with(|| a.0.to_lowercase().cmp(&b.0.to_lowercase()))
            });
            
            // Update progress to complete
            if let Some(prog) = &progress {
                let mut p = prog.lock().await;
                p.current = tag_list_lower.len();
                p.message = format!("Found {} similar pairs", similar_pairs.len());
            }
            
            Ok(similar_pairs)
        }
    }
}

impl Default for APIClient {
    fn default() -> Self {
        Self::new().expect("Failed to create API client")
    }
}

