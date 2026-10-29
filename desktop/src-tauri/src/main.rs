#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::Serialize;
use std::net::TcpListener;
use std::sync::Mutex;
use tauri::{Manager, State};
use tauri_plugin_shell::{process::CommandChild, ShellExt};
use uuid::Uuid;

mod player;
mod portable;

struct DesktopBackend {
    // 資料夾無法寫入時不啟動後端，改把原因交給前端顯示
    connection: Result<(u16, String), String>,
    child: Mutex<Option<CommandChild>>,
}

#[derive(Serialize)]
struct DesktopConnection {
    port: u16,
    token: String,
}

#[tauri::command]
fn desktop_connection(state: State<'_, DesktopBackend>) -> Result<DesktopConnection, String> {
    state
        .connection
        .clone()
        .map(|(port, token)| DesktopConnection { port, token })
}

/// 視窗在程式中建立，才能指定 WebView2 資料位置；設定檔的相對路徑只會落在 %LOCALAPPDATA%。
fn open_main_window(app: &tauri::App, webview_dir: &std::path::Path) -> tauri::Result<()> {
    tauri::WebviewWindowBuilder::new(app, "main", tauri::WebviewUrl::default())
        .title("AstraTube · AI 影片學習")
        .inner_size(1280.0, 850.0)
        .min_inner_size(850.0, 600.0)
        .resizable(true)
        .data_directory(webview_dir.to_path_buf())
        .build()?;
    Ok(())
}

fn main() {
    // 免安裝版：資料一律放在主程式旁的 data 資料夾（見 portable.rs）
    let exe_dir = std::env::current_exe()
        .ok()
        .and_then(|path| path.parent().map(|dir| dir.to_path_buf()))
        .expect("Could not locate the AstraTube executable");
    let dirs = portable::dirs_for(&exe_dir);
    let ready = portable::prepare(&dirs);
    // 位置無法寫入時，WebView2 仍需要可寫的資料夾才能開窗顯示錯誤，暫時改用系統暫存資料夾
    let webview_dir = if ready.is_ok() {
        dirs.webview.clone()
    } else {
        std::env::temp_dir().join("AstraTube-webview")
    };

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        // YouTube 播放器宿主頁放在獨立來源，避免第三方腳本進入具有 IPC 的主視窗。
        .register_uri_scheme_protocol(player::SCHEME, |_ctx, request| player::respond(&request))
        .invoke_handler(tauri::generate_handler![desktop_connection])
        .setup(move |app| {
            // 先登記後端狀態再開視窗，頁面一載入就能取得連線資訊（或無法啟動的原因）
            if let Err(message) = &ready {
                app.manage(DesktopBackend {
                    connection: Err(message.clone()),
                    child: Mutex::new(None),
                });
                open_main_window(app, &webview_dir)?;
                return Ok(());
            }

            // The port is selected by the OS; it is not a security boundary.
            // The per-launch random token is required for every backend request.
            let listener = TcpListener::bind("127.0.0.1:0")?;
            let port = listener.local_addr()?.port();
            drop(listener);

            let token = format!("{}{}", Uuid::new_v4(), Uuid::new_v4());

            let command = app
                .shell()
                .sidecar("astratube-backend")?
                .env("ASTRA_DESKTOP_TOKEN", &token)
                .env("ASTRA_DESKTOP_PORT", port.to_string())
                .env("ASTRA_DESKTOP_DATA_DIR", dirs.app.to_string_lossy().to_string())
                .env("AUTO_RUN_CLI", "0")
                // 本程式當掉、被強制結束，或 PyInstaller onefile 只停掉外層行程時，
                // Sidecar 會依此 PID 發現桌面程式已不在，並自行結束。
                .env("ASTRA_DESKTOP_PARENT_PID", std::process::id().to_string());

            let (_events, child) = command.spawn()?;
            app.manage(DesktopBackend {
                connection: Ok((port, token)),
                child: Mutex::new(Some(child)),
            });
            open_main_window(app, &webview_dir)?;
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
