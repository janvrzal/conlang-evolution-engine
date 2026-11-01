//! Desktopová skořápka CEE: okno s UI a engine jako pomocný proces.
//!
//! Engine (Python, `cee.api.server`) se spustí na volném portu a UI se jeho
//! adresu dozví příkazem `engine_url`. Při zavření aplikace se proces ukončí.
//! Ve vývoji se Python bere z `CEE_PYTHON` (jinak `python3`) a zdroje enginu
//! z `CEE_ENGINE_SRC` (dosadí se do `PYTHONPATH`). Zabalený engine (PyInstaller)
//! a později přímé volání enginu v Rustu přijdou místo toho.

use std::net::TcpListener;
use std::process::{Child, Command};
use std::sync::Mutex;

use tauri::{Manager, RunEvent, State};

struct EngineProcess {
    url: String,
    child: Mutex<Option<Child>>,
}

/// Adresa API enginu pro UI.
#[tauri::command]
fn engine_url(engine: State<'_, EngineProcess>) -> String {
    engine.url.clone()
}

fn free_port() -> u16 {
    TcpListener::bind("127.0.0.1:0")
        .and_then(|listener| listener.local_addr())
        .map(|address| address.port())
        .unwrap_or(8000)
}

fn spawn_engine(port: u16) -> Option<Child> {
    let python = std::env::var("CEE_PYTHON").unwrap_or_else(|_| "python3".into());
    let mut command = Command::new(python);
    command.args([
        "-m",
        "uvicorn",
        "cee.api.server:app",
        "--host",
        "127.0.0.1",
        "--port",
        &port.to_string(),
    ]);
    if let Ok(src) = std::env::var("CEE_ENGINE_SRC") {
        command.env("PYTHONPATH", src);
    }
    // Engine skončí sám, když aplikace spadne nebo ji systém zabije.
    command.env("CEE_PARENT_PID", std::process::id().to_string());
    match command.spawn() {
        Ok(child) => Some(child),
        Err(error) => {
            eprintln!("Engine CEE se nepodařilo spustit: {error}");
            None
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let port = free_port();
    let child = spawn_engine(port);
    tauri::Builder::default()
        .manage(EngineProcess {
            url: format!("http://127.0.0.1:{port}"),
            child: Mutex::new(child),
        })
        .invoke_handler(tauri::generate_handler![engine_url])
        .build(tauri::generate_context!())
        .expect("Aplikaci CEE se nepodařilo sestavit")
        .run(|handle, event| {
            if let RunEvent::Exit = event {
                let engine = handle.state::<EngineProcess>();
                let mut slot = engine.child.lock().expect("zámek procesu enginu");
                if let Some(mut child) = slot.take() {
                    let _ = child.kill();
                }
            }
        });
}
