#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .plugin(tauri_plugin_shell::init())
    .manage(BackendState::default())
    .setup(|app| {
      if cfg!(debug_assertions) {
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build(),
        )?;
      }

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

use std::{
  env,
  process::{Child, Command, Stdio},
  sync::Arc,
};

use tauri::{Manager, WindowEvent};
use tauri::async_runtime::Mutex;

#[derive(Default)]
struct BackendState {
  inner: Arc<Mutex<Option<Child>>>,
}

fn backend_command() -> (String, Vec<String>) {
  let command = env::var("PLONEAPI_SHELL_CMD").unwrap_or_else(|_| "ploneapi-shell".into());
  let args = vec![
    "serve".into(),
    "--host".into(),
    "127.0.0.1".into(),
    "--port".into(),
    "8787".into(),
  ];
  (command, args)
}

async fn start_backend(state: Arc<Mutex<Option<Child>>>) -> Result<(), String> {
  let mut guard = state.lock().await;
  if guard.is_some() {
    return Ok(());
  }

  let (cmd, args) = backend_command();
  let mut command = Command::new(&cmd);
  command.args(args);
  command.stdout(Stdio::null());
  command.stderr(Stdio::null());

  let child = command.spawn().map_err(|err| {
    format!(
      "Unable to spawn `{cmd}` (set PLONEAPI_SHELL_CMD to override): {err}"
    )
  })?;

  *guard = Some(child);
  Ok(())
}

async fn stop_backend(state: Arc<Mutex<Option<Child>>>) -> Result<(), String> {
  let mut guard = state.lock().await;
  if let Some(mut child) = guard.take() {
    child.kill().map_err(|err| format!("Failed to stop backend: {err}"))?;
  }
  Ok(())
}
