mod api;
pub mod server;

use std::sync::Arc;
use tauri::{Manager, WindowEvent};
use tokio::sync::Mutex;
use tokio::task::JoinHandle;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .plugin(tauri_plugin_shell::init())
    .manage(BackendState::default())
    .setup(|app| {
      // Enable logging in both debug and release builds
      // Logs will appear in:
      // - Terminal/stdout when running `tauri dev`
      // - Log files in ~/Library/Logs/com.ploneapishell.desktop/ (macOS) when running built app
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build(),
        )?;

      let backend_state = app.state::<BackendState>().inner.clone();
      tauri::async_runtime::spawn(async move {
        if let Err(err) = start_backend(backend_state.clone()).await {
          log::error!("Failed to start backend: {err}");
        }
      });

      if let Some(window) = app.get_webview_window("main") {
        let backend_state = app.state::<BackendState>().inner.clone();
        window.on_window_event(move |event| {
          if matches!(event, WindowEvent::CloseRequested { .. }) {
            let state = backend_state.clone();
            tauri::async_runtime::spawn(async move {
              if let Err(err) = stop_backend(state).await {
                log::error!("Failed to stop backend: {err}");
              }
            });
          }
        });
      }

      Ok(())
    })
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}

#[derive(Default)]
struct BackendState {
  inner: Arc<Mutex<Option<JoinHandle<()>>>>,
}

async fn start_backend(state: Arc<Mutex<Option<JoinHandle<()>>>>) -> Result<(), String> {
  let mut guard = state.lock().await;
  if guard.is_some() {
    return Ok(());
  }

  log::info!("Starting Rust backend server on 127.0.0.1:8787");
  
  let handle = tokio::spawn(async {
    if let Err(e) = server::run_server("127.0.0.1", 8787).await {
      log::error!("Backend server error: {}", e);
      if e.to_string().contains("Address already in use") {
        log::error!("Port 8787 is already in use. Please stop any other processes using this port, or kill the old Python backend server.");
      }
    }
  });
  
  *guard = Some(handle);
  Ok(())
}

async fn stop_backend(state: Arc<Mutex<Option<JoinHandle<()>>>>) -> Result<(), String> {
  let mut guard = state.lock().await;
  if let Some(handle) = guard.take() {
    handle.abort();
    log::info!("Backend server stopped");
  }
  Ok(())
}
