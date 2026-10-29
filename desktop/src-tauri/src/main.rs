#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::Serialize;
use std::net::TcpListener;
use std::sync::Mutex;
use tauri::{Manager, State};
use tauri_plugin_shell::{process::CommandChild, ShellExt};
use uuid::Uuid;

struct DesktopBackend {
    port: u16,
    token: String,
    child: Mutex<Option<CommandChild>>,
}

#[derive(Serialize)]
struct DesktopConnection {
    port: u16,
    token: String,
}

#[tauri::command]
fn desktop_connection(state: State<'_, DesktopBackend>) -> DesktopConnection {
    DesktopConnection {
        port: state.port,
        token: state.token.clone(),
    }
}

fn main() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![desktop_connection])
        .setup(|app| {
            // The port is selected by the OS; it is not a security boundary.
            // The per-launch random token is required for every backend request.
            let listener = TcpListener::bind("127.0.0.1:0")?;
            let port = listener.local_addr()?.port();
            drop(listener);

            let token = format!("{}{}", Uuid::new_v4(), Uuid::new_v4());
            let data_dir = app.path().app_data_dir()?;
            std::fs::create_dir_all(&data_dir)?;

            let command = app
                .shell()
                .sidecar("astratube-backend")?
                .env("ASTRA_DESKTOP_TOKEN", &token)
                .env("ASTRA_DESKTOP_PORT", port.to_string())
                .env("ASTRA_DESKTOP_DATA_DIR", data_dir.to_string_lossy().to_string())
                .env("AUTO_RUN_CLI", "0");

            let (_events, child) = command.spawn()?;
            app.manage(DesktopBackend {
                port,
                token,
                child: Mutex::new(Some(child)),
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("Could not create AstraTube desktop application");

    app.run(|handle, event| {
        if let tauri::RunEvent::Exit = event {
            if let Some(state) = handle.try_state::<DesktopBackend>() {
                if let Ok(mut child) = state.child.lock() {
                    if let Some(process) = child.take() {
                        let _ = process.kill();
                    }
                }
            }
        }
    });
}
