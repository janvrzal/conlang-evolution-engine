//! Desktopová aplikace CEE: okno s UI a engine v2 přímo v procesu (crate `cee_engine`).
//!
//! UI volá příkazy Tauri (`engine_*`, `run_*`) místo HTTP serveru; tvary odpovědí jsou stejné
//! jako dřív u `/api/v2`, takže UI (desktop/src/lib/engine.ts) se změnilo jen v přenosu.

mod engine;
mod project;
mod spec_schema;

use std::path::PathBuf;

use serde_json::{json, Value};
use tauri::{Manager, State};

use engine::Runs;
use project::Recent;

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

/// Otevře projekt z disku: zadání a uložený výsledek (`run`, `run_matches`).
#[tauri::command]
async fn project_open(path: PathBuf, recent: State<'_, Recent>) -> Result<Value, String> {
    let opened = tauri::async_runtime::spawn_blocking({
        let path = path.clone();
        move || project::open(&path)
    })
    .await
    .map_err(|e| e.to_string())??;
    let _ = recent.touch(&path, opened["world"]["name"].as_str());
    Ok(opened)
}

/// Uloží zadání. S hotovým během (`run_id`) uloží i výsledek vedle projektu; při „Uložit jako“
/// přenese výsledek načtený ze souboru (`result_from` = původní projekt).
#[tauri::command]
async fn project_save(
    path: PathBuf,
    world: Value,
    run_id: Option<String>,
    spec: Option<Value>,
    result_from: Option<PathBuf>,
    runs: State<'_, Runs>,
    recent: State<'_, Recent>,
) -> Result<Value, String> {
    let run = run_id.map(|id| runs.get(&id).and_then(|r| r.finished())).transpose()?;
    let saved = tauri::async_runtime::spawn_blocking({
        let (path, world) = (path.clone(), world.clone());
        move || -> Result<Option<PathBuf>, String> {
            project::save_world(&path, &world)?;
            match (run, result_from) {
                // výsledek nese zadání, ze kterého vznikl (může být starší než ukládané)
                (Some((frames, result, seconds)), _) => Ok(Some(project::save_result(&path, spec.as_ref().unwrap_or(&world), &frames, &result, seconds)?)),
                (None, Some(from)) if from != path && project::result_path(&from).is_file() => {
                    let to = project::result_path(&path);
                    std::fs::copy(project::result_path(&from), &to).map_err(|e| e.to_string())?;
                    Ok(Some(to))
                }
                _ => Ok(None),
            }
        }
    })
    .await
    .map_err(|e| e.to_string())??;
    let _ = recent.touch(&path, world["name"].as_str());
    Ok(json!({ "path": path, "result": saved }))
}

/// Uloží jen výsledek hotového běhu vedle projektu (hned po doběhnutí, zadání se nemění).
#[tauri::command]
async fn result_save(path: PathBuf, run_id: String, spec: Value, runs: State<'_, Runs>) -> Result<Value, String> {
    let (frames, result, seconds) = runs.get(&run_id)?.finished()?;
    let saved = tauri::async_runtime::spawn_blocking(move || project::save_result(&path, &spec, &frames, &result, seconds))
        .await
        .map_err(|e| e.to_string())??;
    Ok(json!({ "result": saved }))
}

#[tauri::command]
fn recent_list(recent: State<'_, Recent>) -> Vec<Value> {
    recent.list()
}

#[tauri::command]
fn recent_forget(path: String, recent: State<'_, Recent>) -> Result<(), String> {
    recent.forget(&path)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(Runs::default())
        .setup(|app| {
            let dir = app.path().app_config_dir()?;
            app.manage(Recent { file: dir.join("recent.json") });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            engine_health,
            engine_schema,
            engine_validate,
            run_start,
            run_status,
            run_result,
            run_cancel,
            project_open,
            project_save,
            result_save,
            recent_list,
            recent_forget
        ])
        .run(tauri::generate_context!())
        .expect("Aplikaci CEE se nepodařilo spustit");
}
