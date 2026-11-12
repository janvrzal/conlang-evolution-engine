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

use engine::{NamesCache, Runs, StartRun};
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

/// Náhled protojazyků zadání bez běhu; neplatný popis vrátí `{ detail: { issues } }`.
#[tauri::command]
async fn engine_preview(spec: Value) -> Result<Value, Value> {
    tauri::async_runtime::spawn_blocking(move || engine::preview(&spec))
        .await
        .map_err(|e| json!({ "detail": e.to_string() }))?
        .map_err(|issues| json!({ "detail": { "issues": issues } }))
}

/// Složka běhů: u uloženého projektu `svet.cee.behy` vedle něj, jinak dočasná v datech aplikace.
fn runs_dir(app: &tauri::AppHandle, project: Option<&PathBuf>) -> Result<PathBuf, String> {
    match project {
        Some(p) => Ok(cee_store::runs_dir(p)),
        None => Ok(app.path().app_data_dir().map_err(|e| e.to_string())?.join(UNSAVED_RUNS)),
    }
}
const UNSAVED_RUNS: &str = "neulozeny-projekt.cee.behy";

/// Spustí běh (s `parent` jako „co kdyby“ od roku větvení); neplatný popis vrátí
/// `{ detail: { issues } }` jako dřív server (422).
#[tauri::command]
async fn run_start(
    app: tauri::AppHandle,
    spec: Value,
    project: Option<PathBuf>,
    name: Option<String>,
    parent: Option<PathBuf>,
    runs: State<'_, Runs>,
) -> Result<Value, Value> {
    let dir = runs_dir(&app, project.as_ref()).map_err(|e| json!({ "detail": e }))?;
    let new = StartRun { spec: &spec, dir: &dir, name: name.as_deref(), parent: parent.as_deref() };
    match runs.start(new) {
        Ok(run) => Ok(json!({ "run_id": run.id(), "status": "running" })),
        Err(issues) => Err(json!({ "detail": { "issues": issues } })),
    }
}

/// Stav běhu: z paměti (běží nebo doběhl v tomto spuštění aplikace), jinak ze složky běhu.
#[tauri::command]
async fn run_status(id: String, since: usize, runs: State<'_, Runs>) -> Result<Value, String> {
    if let Some(run) = runs.get(&id) {
        return Ok(run.status(since));
    }
    let dir = PathBuf::from(&id);
    tauri::async_runtime::spawn_blocking(move || -> Result<Value, String> {
        let info = cee_store::info(&dir)?;
        let frames = cee_store::frames(&dir, since)?;
        let span = (info.end_year - info.start_year).max(1e-9);
        Ok(json!({
            "id": id, "status": info.status, "year": info.year,
            "progress": ((info.year - info.start_year) / span).clamp(0.0, 1.0),
            "start_year": info.start_year, "end_year": info.end_year, "seconds": info.seconds, "error": info.error,
            "frame_count": info.frames, "frames": frames, "info": info,
        }))
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn run_result(id: String, runs: State<'_, Runs>) -> Result<Value, String> {
    if let Some(run) = runs.get(&id) {
        return Ok((*run.result()?).clone());
    }
    let dir = PathBuf::from(&id);
    tauri::async_runtime::spawn_blocking(move || cee_store::result(&dir)?.ok_or_else(|| "Běh nemá výsledek.".to_string())).await.map_err(|e| e.to_string())?
}

#[tauri::command]
fn run_cancel(id: String, runs: State<'_, Runs>) -> Result<Value, String> {
    let run = runs.get(&id).ok_or("Běh už neběží.")?;
    run.cancel();
    Ok(json!({ "run_id": id, "status": "cancelled" }))
}

/// Běhy projektu (složka a seznam s příznakem `matches` k zadání `spec`).
#[tauri::command]
async fn runs_list(app: tauri::AppHandle, project: Option<PathBuf>, spec: Value) -> Result<Value, String> {
    let dir = runs_dir(&app, project.as_ref())?;
    tauri::async_runtime::spawn_blocking(move || project::runs(&dir, &spec)).await.map_err(|e| e.to_string())?
}

/// Slovník jazyka (linie nebo protojazyka) v roce: `{group, forms}`, nebo null.
#[tauri::command]
async fn run_lexicon(id: String, language: String, year: f64) -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(move || {
        Ok(cee_store::lexicon(&PathBuf::from(id), &language, year)?.map(|l| json!({ "group": l.group, "forms": l.forms })).unwrap_or(Value::Null))
    })
    .await
    .map_err(|e| e.to_string())?
}

/// Roky, ve kterých má běh slovník, a jazyky v nich.
#[tauri::command]
async fn run_lexicon_years(id: String) -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(move || {
        Ok(json!(cee_store::lexicon_years(&PathBuf::from(id))?.into_iter().map(|(y, l)| json!({ "year": y, "languages": l })).collect::<Vec<_>>()))
    })
    .await
    .map_err(|e| e.to_string())?
}

/// Historie slova v jazyce: `[{year, form|null}]`.
#[tauri::command]
async fn run_word_history(id: String, language: String, concept: String) -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(move || Ok(json!(cee_store::word_history(&PathBuf::from(id), &language, &concept)?)))
        .await
        .map_err(|e| e.to_string())?
}

/// Generátor jmen sídel a osob podle kraje a epochy (modul jmen, dok. 34): dotaz
/// `{region, year, count, until, urban, attempt, kind}`.
#[tauri::command]
async fn run_names(id: String, query: Value, runs: State<'_, Runs>, cache: State<'_, NamesCache>) -> Result<Value, String> {
    let (run, cache) = (runs.get(&id), cache.inner().clone());
    tauri::async_runtime::spawn_blocking(move || cache.generate(run, &id, &query)).await.map_err(|e| e.to_string())?
}

#[tauri::command]
fn run_rename(id: String, name: Option<String>) -> Result<(), String> {
    cee_store::rename(&PathBuf::from(id), name.as_deref())
}

/// Smaže kontrolní body běhu (zabírají nejvíc místa); výsledek a slovník zůstanou,
/// jen „co kdyby“ z tohoto běhu se pak počítá od začátku.
#[tauri::command]
async fn run_drop_checkpoints(id: String, runs: State<'_, Runs>) -> Result<(), String> {
    if runs.get(&id).is_some_and(|r| r.status(usize::MAX)["status"] == "running") {
        return Err("Běh ještě počítá; nejdřív ho zastav.".into());
    }
    tauri::async_runtime::spawn_blocking(move || cee_store::drop_checkpoints(&PathBuf::from(id))).await.map_err(|e| e.to_string())?
}

#[tauri::command]
fn run_delete(id: String, runs: State<'_, Runs>) -> Result<(), String> {
    if runs.get(&id).is_some_and(|r| r.status(usize::MAX)["status"] == "running") {
        return Err("Běh ještě počítá; nejdřív ho zastav.".into());
    }
    cee_store::delete(&PathBuf::from(id))
}

/// Otevře projekt: zadání a jeho běhy.
#[tauri::command]
async fn project_open(path: PathBuf, recent: State<'_, Recent>) -> Result<Value, String> {
    let opened = tauri::async_runtime::spawn_blocking({
        let path = path.clone();
        move || -> Result<Value, String> {
            let world = project::open(&path)?;
            let runs = project::runs(&cee_store::runs_dir(&path), &world)?;
            Ok(json!({ "path": path, "world": world, "runs": runs }))
        }
    })
    .await
    .map_err(|e| e.to_string())??;
    let _ = recent.touch(&path, opened["world"]["name"].as_str());
    Ok(opened)
}

/// Uloží zadání a přesune k projektu běhy z `runs_from` (dočasná složka neuloženého projektu
/// nebo složka běhů před „Uložit jako“).
#[tauri::command]
async fn project_save(app: tauri::AppHandle, path: PathBuf, world: Value, runs_from: Option<PathBuf>, recent: State<'_, Recent>) -> Result<Value, String> {
    // bez `runs_from` se nic nepřesouvá (UI ho posílá u neuloženého projektu a u „Uložit jako“)
    let from = runs_from;
    let _ = &app;
    let runs = tauri::async_runtime::spawn_blocking({
        let (path, world) = (path.clone(), world.clone());
        move || -> Result<Value, String> {
            project::save_world(&path, &world)?;
            let target = cee_store::runs_dir(&path);
            if let Some(from) = from {
                project::move_runs(&from, &target)?;
            }
            project::runs(&target, &world)
        }
    })
    .await
    .map_err(|e| e.to_string())??;
    let _ = recent.touch(&path, world["name"].as_str());
    Ok(json!({ "path": path, "runs": runs }))
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
        .manage(NamesCache::default())
        .setup(|app| {
            let dir = app.path().app_config_dir()?;
            app.manage(Recent { file: dir.join("recent.json") });
            // běhy neuloženého projektu z minulého spuštění nejsou k ničemu přiřazené
            let _ = std::fs::remove_dir_all(app.path().app_data_dir()?.join(UNSAVED_RUNS));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            engine_health,
            engine_schema,
            engine_validate,
            engine_preview,
            run_start,
            run_status,
            run_result,
            run_cancel,
            runs_list,
            run_lexicon,
            run_lexicon_years,
            run_word_history,
            run_names,
            run_rename,
            run_delete,
            run_drop_checkpoints,
            project_open,
            project_save,
            recent_list,
            recent_forget
        ])
        .run(tauri::generate_context!())
        .expect("Aplikaci CEE se nepodařilo spustit");
}
