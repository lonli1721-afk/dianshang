use tauri::Manager;
use tauri_plugin_shell::ShellExt;
use std::sync::{Arc, Mutex};
use std::time::Duration;

const SERVER_PORT: u16 = 57991;
const HEALTH_URL: &str = "http://127.0.0.1:57991/health";

fn cache_bust_url() -> String {
    let ts = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_secs();
    let app_mode = option_env!("WANPI_APP_MODE").unwrap_or("main");
    if app_mode == "game" {
        format!("http://127.0.0.1:{}/?app=game&_v={}", SERVER_PORT, ts)
    } else {
        format!("http://127.0.0.1:{}/?_v={}", SERVER_PORT, ts)
    }
}

fn wait_for_server(timeout: Duration) -> bool {
    let start = std::time::Instant::now();
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(2))
        .build()
        .unwrap();
    while start.elapsed() < timeout {
        if let Ok(resp) = client.get(HEALTH_URL).send() {
            if resp.status().is_success() {
                return true;
            }
        }
        std::thread::sleep(Duration::from_millis(500));
    }
    false
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let sidecar_cmd = app.shell()
                .sidecar("wanpi-server")
                .expect("failed to create sidecar command")
                .args(["--sidecar", "--host", "127.0.0.1", "--port", &SERVER_PORT.to_string()]);

            let ready_flag = Arc::new(Mutex::new(false));
            let ready_clone = ready_flag.clone();

            let (mut rx, _child) = sidecar_cmd.spawn().expect("Failed to spawn sidecar");

            let app_handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                use tauri_plugin_shell::process::CommandEvent;
                while let Some(event) = rx.recv().await {
                    match event {
                        CommandEvent::Stdout(line) => {
                            let text = String::from_utf8_lossy(&line);
                            if text.trim() == "READY" {
                                let mut flag = ready_clone.lock().unwrap();
                                *flag = true;
                                if let Some(win) = app_handle.get_webview_window("main") {
                                    let url_str = cache_bust_url();
                                    let _ = win.navigate(url_str.parse().unwrap());
                                    let _ = win.show();
                                }
                            }
                        }
                        CommandEvent::Stderr(line) => {
                            let text = String::from_utf8_lossy(&line);
                            eprintln!("[sidecar] {}", text.trim());
                        }
                        CommandEvent::Terminated(status) => {
                            eprintln!("[sidecar] process terminated: {:?}", status);
                            break;
                        }
                        _ => {}
                    }
                }
            });

            let ready_for_fallback = ready_flag.clone();
            let app_handle_fb = app.handle().clone();
            std::thread::spawn(move || {
                std::thread::sleep(Duration::from_secs(3));
                let already = { *ready_for_fallback.lock().unwrap() };
                if !already {
                    if wait_for_server(Duration::from_secs(60)) {
                        let mut flag = ready_for_fallback.lock().unwrap();
                        *flag = true;
                        if let Some(win) = app_handle_fb.get_webview_window("main") {
                            let url_str = cache_bust_url();
                            let _ = win.navigate(url_str.parse().unwrap());
                            let _ = win.show();
                        }
                    } else {
                        eprintln!("[sidecar] server failed to start within 60s");
                    }
                }
            });

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
