//! Projekty na disku: zadání světa (`*.cee.json`), výsledek běhu vedle něj
//! (`*.cee.vysledek.json.gz`: zadání, snímky, export) a seznam nedávných projektů.
//!
//! Výsledek nese zadání, ze kterého vznikl; po otevření UI pozná, jestli ještě sedí
//! (jinak ho ukáže jako zastaralý). Zápis jde přes dočasný soubor a přejmenování,
//! aby pád uprostřed nezanechal rozbitý projekt.

use std::fs;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};

use flate2::read::GzDecoder;
use flate2::write::GzEncoder;
use flate2::Compression;
use serde_json::{json, Value};

/// Kolik nedávných projektů si aplikace pamatuje.
const RECENT: usize = 12;
pub const RUN_FORMAT: &str = "cee-run/1";

/// Soubor s výsledkem vedle projektu: `svet.cee.json` → `svet.cee.vysledek.json.gz`.
pub fn result_path(project: &Path) -> PathBuf {
    let name = project.file_name().and_then(|n| n.to_str()).unwrap_or("svet.cee.json");
    let stem = name.strip_suffix(".json").unwrap_or(name);
    project.with_file_name(format!("{stem}.vysledek.json.gz"))
}

fn write_atomic(path: &Path, bytes: &[u8]) -> Result<(), String> {
    let tmp = path.with_extension(format!("tmp-{}", std::process::id()));
    fs::write(&tmp, bytes).map_err(|e| format!("{}: {e}", tmp.display()))?;
    fs::rename(&tmp, path).map_err(|e| format!("{}: {e}", path.display()))
}

/// Uloží zadání (čitelný JSON). Projekt v obálce `cee-project/1` se ukládá jako čisté zadání.
pub fn save_world(path: &Path, world: &Value) -> Result<(), String> {
    let text = serde_json::to_string_pretty(world).map_err(|e| e.to_string())?;
    write_atomic(path, format!("{text}\n").as_bytes())
}

/// Uloží výsledek běhu vedle projektu (gzip).
pub fn save_result(project: &Path, spec: &Value, frames: &Value, result: &Value, seconds: f64) -> Result<PathBuf, String> {
    let payload = json!({ "format": RUN_FORMAT, "spec": spec, "seconds": seconds, "frames": frames, "result": result });
    let mut gz = GzEncoder::new(Vec::new(), Compression::new(6));
    serde_json::to_writer(&mut gz, &payload).map_err(|e| e.to_string())?;
    let bytes = gz.finish().map_err(|e| e.to_string())?;
    let path = result_path(project);
    write_atomic(&path, &bytes)?;
    Ok(path)
}

/// Otevře projekt: zadání a (je-li) uložený výsledek s příznakem, zda k zadání sedí.
pub fn open(path: &Path) -> Result<Value, String> {
    let text = fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
    let parsed: Value = serde_json::from_str(&text).map_err(|_| "Soubor není popis světa CEE.".to_string())?;
    let world = if parsed["format"] == "cee-project/1" { parsed["world"].clone() } else { parsed };
    if world["format"] != "cee-v2-world/1" {
        return Err("Soubor není popis světa CEE.".into());
    }
    let run = load_result(path).ok();
    let matches = run.as_ref().is_some_and(|r| r["spec"] == world);
    Ok(json!({ "path": path, "world": world, "run": run, "run_matches": matches }))
}

fn load_result(project: &Path) -> Result<Value, String> {
    let file = fs::File::open(result_path(project)).map_err(|e| e.to_string())?;
    let mut text = String::new();
    GzDecoder::new(file).read_to_string(&mut text).map_err(|e| e.to_string())?;
    let run: Value = serde_json::from_str(&text).map_err(|e| e.to_string())?;
    if run["format"] != RUN_FORMAT {
        return Err("neznámý formát výsledku".into());
    }
    Ok(run)
}

/// Nedávné projekty (nejnovější první), uložené v konfigurační složce aplikace.
pub struct Recent {
    pub file: PathBuf,
}

impl Recent {
    fn read(&self) -> Vec<Value> {
        fs::read_to_string(&self.file).ok().and_then(|t| serde_json::from_str(&t).ok()).unwrap_or_default()
    }

    /// Seznam s příznakem, jestli soubor ještě existuje.
    pub fn list(&self) -> Vec<Value> {
        self.read()
            .into_iter()
            .map(|mut item| {
                let exists = item["path"].as_str().is_some_and(|p| Path::new(p).is_file());
                let has_result = item["path"].as_str().is_some_and(|p| result_path(Path::new(p)).is_file());
                item["exists"] = json!(exists);
                item["has_result"] = json!(has_result);
                item
            })
            .collect()
    }

    /// Zapíše projekt na začátek seznamu (jméno světa, čas v sekundách od 1970).
    pub fn touch(&self, path: &Path, name: Option<&str>) -> Result<(), String> {
        let path_text = path.to_string_lossy().to_string();
        let mut items: Vec<Value> = self.read().into_iter().filter(|i| i["path"] != path_text.as_str()).collect();
        let now = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0);
        items.insert(0, json!({ "path": path_text, "name": name, "opened": now }));
        items.truncate(RECENT);
        if let Some(dir) = self.file.parent() {
            fs::create_dir_all(dir).map_err(|e| e.to_string())?;
        }
        let mut f = fs::File::create(&self.file).map_err(|e| e.to_string())?;
        f.write_all(serde_json::to_string_pretty(&items).unwrap_or_default().as_bytes()).map_err(|e| e.to_string())
    }

    pub fn forget(&self, path: &str) -> Result<(), String> {
        let items: Vec<Value> = self.read().into_iter().filter(|i| i["path"] != path).collect();
        fs::write(&self.file, serde_json::to_string_pretty(&items).unwrap_or_default()).map_err(|e| e.to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn dir() -> PathBuf {
        let d = std::env::temp_dir().join(format!("cee-project-test-{}-{}", std::process::id(), rand_suffix()));
        fs::create_dir_all(&d).unwrap();
        d
    }
    fn rand_suffix() -> u128 {
        std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos()
    }

    #[test]
    fn ulozeni_a_otevreni_projektu_s_vysledkem() {
        let d = dir();
        let path = d.join("talvera.cee.json");
        let world: Value = serde_json::from_str(include_str!("../../static/projects/talvera.cee.json")).unwrap();
        save_world(&path, &world).unwrap();
        let opened = open(&path).unwrap();
        assert_eq!(opened["world"], world);
        assert!(opened["run"].is_null());

        let saved = save_result(&path, &world, &json!([{ "year": -700 }]), &json!({ "format": "cee-v2/1", "year": 1950 }), 12.5).unwrap();
        assert_eq!(saved.file_name().unwrap(), "talvera.cee.vysledek.json.gz");
        let opened = open(&path).unwrap();
        assert_eq!(opened["run"]["result"]["year"], 1950);
        assert_eq!(opened["run_matches"], true);

        // změněné zadání: výsledek se načte, ale nesedí
        let mut changed = world.clone();
        changed["seed"] = json!(2);
        save_world(&path, &changed).unwrap();
        assert_eq!(open(&path).unwrap()["run_matches"], false);
        fs::remove_dir_all(d).unwrap();
    }

    #[test]
    fn obalka_projektu_a_cizi_soubor() {
        let d = dir();
        let path = d.join("x.json");
        fs::write(&path, r#"{"format":"cee-project/1","world":{"format":"cee-v2-world/1","end_year":10,"languages":[],"regions":[]}}"#).unwrap();
        assert_eq!(open(&path).unwrap()["world"]["end_year"], 10);
        fs::write(&path, r#"{"hello":1}"#).unwrap();
        assert!(open(&path).is_err());
        fs::remove_dir_all(d).unwrap();
    }

    #[test]
    fn nedavne_projekty() {
        let d = dir();
        let recent = Recent { file: d.join("recent.json") };
        let a = d.join("a.cee.json");
        fs::write(&a, "{}").unwrap();
        recent.touch(&a, Some("A")).unwrap();
        recent.touch(&d.join("b.cee.json"), Some("B")).unwrap();
        recent.touch(&a, Some("A")).unwrap();
        let list = recent.list();
        assert_eq!(list.len(), 2);
        assert_eq!(list[0]["name"], "A");
        assert_eq!(list[0]["exists"], true);
        assert_eq!(list[1]["exists"], false);
        recent.forget(list[1]["path"].as_str().unwrap()).unwrap();
        assert_eq!(recent.list().len(), 1);
        fs::remove_dir_all(d).unwrap();
    }
}
