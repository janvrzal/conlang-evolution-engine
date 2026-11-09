//! Desktopová aplikace CEE: okno s UI a engine v2 přímo v procesu (crate `cee_engine`).
//!
//! UI volá příkazy Tauri (`engine_*`, `run_*`) místo HTTP serveru; tvary odpovědí jsou stejné
//! jako dřív u `/api/v2`, takže UI (desktop/src/lib/engine.ts) se změnilo jen v přenosu.

mod engine;

use serde_json::{json, Value};
use tauri::State;

use engine::Runs;

/// Stav enginu pro UI (místo `/api/health`).
#[tauri::command]
fn engine_health() -> Value {
    json!({
        "status": "ok",
        "engine": "Conlang Evolution Engine",
        "version": format!("v2 (Rust, desktop {})", env!("CARGO_PKG_VERSION")),
        "api_revision": engine::API_REVISION,
        "v2_binding_fresh": true,
    })
}

#[tauri::command]
fn engine_schema() -> Value {
    engine::schema()
}

#[tauri::command]
async fn engine_validate(spec: Value) -> Value {
    let issues = tauri::async_runtime::spawn_blocking(move || engine::validate(&spec)).await.unwrap_or_default();
    json!({ "ok": issues.iter().all(|i| i.severity != "error"), "issues": issues })
}

/// Spustí běh; neplatný popis vrátí `{ detail: { issues } }` jako dřív server (422).
#[tauri::command]
async fn run_start(spec: Value, runs: State<'_, Runs>) -> Result<Value, Value> {
    let runs = runs.inner();
    match runs.start(&spec) {
        Ok(run) => Ok(json!({ "run_id": run.status(usize::MAX)["id"], "status": "running" })),
        Err(issues) => Err(json!({ "detail": { "issues": issues } })),
    }
}

#[tauri::command]
fn run_status(id: String, since: usize, runs: State<'_, Runs>) -> Result<Value, String> {
    Ok(runs.get(&id)?.status(since))
}

#[tauri::command]
async fn run_result(id: String, runs: State<'_, Runs>) -> Result<Value, String> {
    let run = runs.get(&id)?;
    Ok((*run.result()?).clone())
}

#[tauri::command]
fn run_cancel(id: String, runs: State<'_, Runs>) -> Result<Value, String> {
    let run = runs.get(&id)?;
    run.cancel();
    Ok(json!({ "run_id": id, "status": "cancelled" }))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(Runs::default())
        .invoke_handler(tauri::generate_handler![engine_health, engine_schema, engine_validate, run_start, run_status, run_result, run_cancel])
        .run(tauri::generate_context!())
        .expect("Aplikaci CEE se nepodařilo spustit");
}
