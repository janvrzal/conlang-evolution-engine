//! Projekty na disku: zadání světa (`*.cee.json`), jeho běhy ve složce vedle něj
//! (`*.cee.behy/`, zapisuje `cee_store`) a seznam nedávných projektů.
//!
//! Každý běh nese zadání, ze kterého vznikl (`spec_hash`); UI podle toho pozná, jestli
//! ještě sedí. Zadání se zapisuje přes dočasný soubor a přejmenování.

use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};

use serde_json::{json, Value};

/// Kolik nedávných projektů si aplikace pamatuje.
const RECENT: usize = 12;

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

/// Otevře projekt: zadání (čisté nebo v obálce `cee-project/1`).
pub fn open(path: &Path) -> Result<Value, String> {
    let text = fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
    let parsed: Value = serde_json::from_str(&text).map_err(|_| "Soubor není popis světa CEE.".to_string())?;
    let world = if parsed["format"] == "cee-project/1" { parsed["world"].clone() } else { parsed };
    if world["format"] != "cee-v2-world/1" {
        return Err("Soubor není popis světa CEE.".into());
    }
    Ok(world)
}

/// Běhy projektu pro UI: složka a seznam (nejnovější první) s příznakem, zda běh sedí k zadání.
pub fn runs(dir: &Path, world: &Value) -> Result<Value, String> {
    let hash = cee_store::spec_hash(world);
    let list = if dir.is_dir() { cee_store::list(dir)? } else { Vec::new() };
    let runs: Vec<Value> = list
        .into_iter()
        .map(|info| {
            let matches = info.spec_hash == hash;
            let mut v = serde_json::to_value(&info).unwrap_or(Value::Null);
            v["matches"] = json!(matches);
            v["path"] = json!(dir.join(&info.id));
            // velikost po částech (bajty); kontrolní body jsou největší a dají se smazat
            v["size"] = json!(cee_store::size(&dir.join(&info.id)));
            v
        })
        .collect();
    Ok(json!({ "dir": dir, "runs": runs }))
}

/// Přesune běhy (složku `*.behy`) k jinému projektu, např. z dočasné složky neuloženého
/// projektu nebo při „Uložit jako“. Existující cílová složka se doplní po bězích.
pub fn move_runs(from: &Path, to: &Path) -> Result<(), String> {
    if !from.is_dir() || from == to {
        return Ok(());
    }
    if !to.exists() {
        if let Some(parent) = to.parent() {
            fs::create_dir_all(parent).map_err(|e| e.to_string())?;
        }
        if fs::rename(from, to).is_ok() {
            return Ok(());
        }
    }
    fs::create_dir_all(to).map_err(|e| e.to_string())?;
    for entry in fs::read_dir(from).map_err(|e| e.to_string())? {
        let entry = entry.map_err(|e| e.to_string())?;
        let target = to.join(entry.file_name());
        if !target.exists() {
            fs::rename(entry.path(), &target).or_else(|_| copy_dir(&entry.path(), &target)).map_err(|e| e.to_string())?;
        }
    }
    Ok(())
}

fn copy_dir(from: &Path, to: &Path) -> std::io::Result<()> {
    fs::create_dir_all(to)?;
    for entry in fs::read_dir(from)? {
        let entry = entry?;
        let target = to.join(entry.file_name());
        if entry.file_type()?.is_dir() {
            copy_dir(&entry.path(), &target)?;
        } else {
            fs::copy(entry.path(), target)?;
        }
    }
    Ok(())
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
                let runs = item["path"].as_str().map(|p| cee_store::runs_dir(Path::new(p))).filter(|d| d.is_dir()).and_then(|d| cee_store::list(&d).ok()).map_or(0, |l| l.len());
                item["exists"] = json!(exists);
                item["runs"] = json!(runs);
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
        // souběžné testy: čas sám nestačí (na macOS má hrubé rozlišení), proto i počítadlo
        static NEXT: std::sync::atomic::AtomicU32 = std::sync::atomic::AtomicU32::new(0);
        let n = NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
        let d = std::env::temp_dir().join(format!("cee-project-test-{}-{}-{n}", std::process::id(), rand_suffix()));
        fs::create_dir_all(&d).unwrap();
        d
    }
    fn rand_suffix() -> u128 {
        std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos()
    }

    #[test]
    fn ulozeni_otevreni_a_presun_behu() {
        let d = dir();
        let path = d.join("talvera.cee.json");
        let world: Value = serde_json::from_str(include_str!("../../static/projects/talvera.cee.json")).unwrap();
        save_world(&path, &world).unwrap();
        assert_eq!(open(&path).unwrap(), world);
        // běh v dočasné složce se při uložení přesune k projektu
        let tmp = d.join("neulozeno.cee.behy");
        let mut writer = cee_store::RunWriter::create(&tmp, &cee_store::NewRun { spec: Some(&world), ..Default::default() }).unwrap();
        writer.finish(cee_store::Status::Done, None, 1.0, None).unwrap();
        let target = cee_store::runs_dir(&path);
        move_runs(&tmp, &target).unwrap();
        assert!(!tmp.exists());
        let listed = runs(&target, &world).unwrap();
        assert_eq!(listed["runs"].as_array().unwrap().len(), 1);
        assert_eq!(listed["runs"][0]["matches"], true);
        let mut changed = world.clone();
        changed["seed"] = json!(2);
        assert_eq!(runs(&target, &changed).unwrap()["runs"][0]["matches"], false);
        fs::remove_dir_all(d).unwrap();
    }

    #[test]
    fn obalka_projektu_a_cizi_soubor() {
        let d = dir();
        let path = d.join("x.json");
        fs::write(&path, r#"{"format":"cee-project/1","world":{"format":"cee-v2-world/1","end_year":10,"languages":[],"regions":[]}}"#).unwrap();
        assert_eq!(open(&path).unwrap()["end_year"], 10);
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
