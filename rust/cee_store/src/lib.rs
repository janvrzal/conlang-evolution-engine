//! Běhy CEE v souborech vedle projektu (dok. 36).
//!
//! Projekt `svet.cee.json` má běhy ve složce `svet.cee.behy/` ([`runs_dir`]), každý běh
//! v podsložce pojmenované časem spuštění (`20261109-153012`):
//!
//! ```text
//! beh.json            stav, doba, rodičovský běh a rok větvení („co kdyby“), počet snímků
//! zadani.json         zadání, ze kterého běh vznikl (čitelné)
//! snimky.jsonl.gz     průběžné snímky (`export::frame`), řádek po řádku
//! slovnik.jsonl.gz    slovník jazyků v čase: jen změny tvarů (řádek = rok + jazyk)
//! udalosti.jsonl.gz   záznam událostí běhu (jen se připisuje)
//! vysledek.json.gz    výsledek (export enginu), u hotového běhu
//! body/t00040_y300_e123456.bin.gz   kontrolní body (postcard) bez záznamu událostí;
//!                     `e` = kolik řádků `udalosti.jsonl.gz` k bodu patří
//! ```
//!
//! „Co kdyby“ převezme od rodiče snímky, slovník a záznam událostí do roku bodu, kontrolní
//! body ale ne: bod před rokem větvení hledá [`checkpoint_before`] i ve složce rodiče.
//!
//! Každý zápis do `.jsonl.gz` je samostatný člen gzipu připsaný na konec souboru, takže
//! pád aplikace nechá všechno zapsané čitelné; `beh.json` a výsledek se zapisují přes
//! dočasný soubor a přejmenování. Běh, který zůstal `running` po jiném procesu, se čte
//! jako `interrupted`. Složku se světem jde poslat i s běhy.

use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::io::{BufReader, Read, Write};
use std::path::{Path, PathBuf};

use cee_engine::export::LanguageLexicon;
use flate2::read::{GzDecoder, MultiGzDecoder};
use flate2::write::GzEncoder;
use flate2::Compression;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

pub mod recorder;

/// Formát `beh.json`.
pub const RUN_FORMAT: &str = "cee-run/2";

const INFO: &str = "beh.json";
const SPEC: &str = "zadani.json";
const FRAMES: &str = "snimky.jsonl.gz";
const LEXICON: &str = "slovnik.jsonl.gz";
const RESULT: &str = "vysledek.json.gz";
const EVENTS: &str = "udalosti.jsonl.gz";
const CHECKPOINTS: &str = "body";
/// Stav modulu jmen na konci běhu (svět a jména) pro generátor jmen v aplikaci.
const NAMES: &str = "jmena.bin.gz";

/// Stav běhu.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Status {
    Running,
    Done,
    Failed,
    Cancelled,
    /// Aplikace skončila uprostřed běhu.
    Interrupted,
}

/// Nový běh: z čeho vznikl.
#[derive(Clone, Debug, Default)]
pub struct NewRun<'a> {
    /// Jméno pro seznam běhů (např. „co kdyby: bez dobytí“).
    pub name: Option<&'a str>,
    pub spec: Option<&'a Value>,
    /// „Co kdyby“: běh (jméno složky), ze kterého se větví, a rok větvení.
    pub parent: Option<&'a str>,
    pub branch_year: Option<f64>,
    /// Verze enginu nebo API, která běh počítala.
    pub engine: Option<&'a str>,
}

/// Obsah `beh.json` a řádek seznamu běhů.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct RunInfo {
    pub format: String,
    /// Jméno složky běhu.
    pub id: String,
    pub name: Option<String>,
    pub spec_hash: String,
    pub parent: Option<String>,
    pub branch_year: Option<f64>,
    pub start_year: f64,
    pub end_year: f64,
    /// Rok, kam běh došel.
    pub year: f64,
    pub status: Status,
    pub error: Option<String>,
    pub seconds: f64,
    /// Sekundy od 1970.
    pub created: u64,
    pub finished: Option<u64>,
    pub engine: Option<String>,
    pub frames: usize,
    /// Proces, který běh zapisuje (pozná přerušený běh).
    pub pid: u32,
    /// Doplní se při čtení.
    #[serde(default)]
    pub checkpoints: usize,
    #[serde(default)]
    pub has_result: bool,
}

/// Kontrolní bod ve složce běhu (bez záznamu událostí).
#[derive(Clone, Debug)]
pub struct StoredCheckpoint {
    pub tick: u32,
    pub year: f64,
    /// Kolik řádků záznamu událostí k bodu patří.
    pub events: usize,
    /// Složka běhu, ve které bod leží (u „co kdyby“ i rodič).
    pub run: PathBuf,
    path: PathBuf,
}

/// Tvar slova od jednoho roku (historie slova).
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct WordForm {
    pub year: f64,
    /// `None`: jazyk pojem od toho roku nemá.
    pub form: Option<String>,
}

/// Řádek `slovnik.jsonl.gz`: rok, jazyk, skupina, podle které se tvary berou, a změněné
/// tvary (`null` = pojem zmizel).
#[derive(Clone, Debug, Serialize, Deserialize)]
struct LexiconLine {
    year: f64,
    language: String,
    group: String,
    forms: BTreeMap<String, Option<String>>,
}

fn err(path: &Path, e: impl std::fmt::Display) -> String {
    format!("{}: {e}", path.display())
}

fn now() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

/// `20261109-153012` z času v sekundách (UTC).
fn stamp(seconds: u64) -> String {
    let days = (seconds / 86_400) as i64;
    let rest = seconds % 86_400;
    // převod dní od 1970 na datum (Howard Hinnant, civil_from_days)
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1_460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = if mp < 10 { mp + 3 } else { mp - 9 };
    let year = yoe + era * 400 + i64::from(month <= 2);
    format!(
        "{year:04}{month:02}{day:02}-{:02}{:02}{:02}",
        rest / 3_600,
        rest % 3_600 / 60,
        rest % 60
    )
}

fn write_atomic(path: &Path, bytes: &[u8]) -> Result<(), String> {
    let tmp = path.with_extension(format!("tmp-{}", std::process::id()));
    fs::write(&tmp, bytes).map_err(|e| err(&tmp, e))?;
    fs::rename(&tmp, path).map_err(|e| err(path, e))
}

fn gzip(bytes: &[u8]) -> Vec<u8> {
    gzip_level(bytes, 6)
}

/// Kontrolní body (stovky MB rozbalené) se balí rychle: úroveň 1 je skoro stejně malá jako 6
/// (Talvera rok 500: 19 proti 17 MB) a dvakrát rychlejší.
fn gzip_level(bytes: &[u8], level: u32) -> Vec<u8> {
    let mut gz = GzEncoder::new(Vec::new(), Compression::new(level));
    gz.write_all(bytes).expect("zápis do paměti");
    gz.finish().expect("zápis do paměti")
}

fn gunzip(path: &Path) -> Result<Vec<u8>, String> {
    let file = fs::File::open(path).map_err(|e| err(path, e))?;
    let mut out = Vec::new();
    GzDecoder::new(file)
        .read_to_end(&mut out)
        .map_err(|e| err(path, e))?;
    Ok(out)
}

/// Připíše řádky jako nový člen gzipu na konec souboru.
fn append_lines(path: &Path, lines: &[String]) -> Result<(), String> {
    if lines.is_empty() {
        return Ok(());
    }
    let mut text = String::new();
    for line in lines {
        text.push_str(line);
        text.push('\n');
    }
    let mut file = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map_err(|e| err(path, e))?;
    file.write_all(&gzip(text.as_bytes()))
        .map_err(|e| err(path, e))
}

/// Řádky souboru `.jsonl.gz`. Useknutý konec (pád při zápisu) se vynechá: přečte se, co
/// jde rozbalit, a nedokončený poslední řádek se zahodí.
fn read_lines(path: &Path) -> Result<Vec<String>, String> {
    let file = match fs::File::open(path) {
        Ok(f) => f,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(e) => return Err(err(path, e)),
    };
    let mut decoder = MultiGzDecoder::new(BufReader::new(file));
    let mut bytes = Vec::new();
    let mut chunk = [0u8; 64 * 1024];
    let mut broken = false;
    loop {
        match decoder.read(&mut chunk) {
            Ok(0) => break,
            Ok(n) => bytes.extend_from_slice(&chunk[..n]),
            Err(_) => {
                broken = true;
                break;
            }
        }
    }
    if broken || bytes.last().is_some_and(|&b| b != b'\n') {
        let keep = bytes.iter().rposition(|&b| b == b'\n').map_or(0, |i| i + 1);
        bytes.truncate(keep);
    }
    let text = String::from_utf8_lossy(&bytes);
    Ok(text
        .lines()
        .filter(|l| !l.is_empty())
        .map(str::to_owned)
        .collect())
}

/// Otisk zadání (FNV-1a 64 nad JSON): pozná, jestli uložený běh sedí k zadání.
pub fn spec_hash(spec: &Value) -> String {
    let text = serde_json::to_string(spec).unwrap_or_default();
    let mut hash: u64 = 0xcbf29ce484222325;
    for byte in text.bytes() {
        hash ^= u64::from(byte);
        hash = hash.wrapping_mul(0x100000001b3);
    }
    format!("{hash:016x}")
}

/// Složka běhů projektu: `svet.cee.json` → `svet.cee.behy`.
pub fn runs_dir(project: &Path) -> PathBuf {
    let name = project
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("svet.cee.json");
    let stem = name.strip_suffix(".json").unwrap_or(name);
    project.with_file_name(format!("{stem}.behy"))
}

/// Běhy ve složce běhů (nejnovější první).
pub fn list(dir: &Path) -> Result<Vec<RunInfo>, String> {
    let entries = match fs::read_dir(dir) {
        Ok(e) => e,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(e) => return Err(err(dir, e)),
    };
    let mut runs: Vec<RunInfo> = entries
        .filter_map(Result::ok)
        .filter(|e| e.path().join(INFO).is_file())
        .filter_map(|e| info(&e.path()).ok())
        .collect();
    runs.sort_by(|a, b| b.created.cmp(&a.created).then(b.id.cmp(&a.id)));
    Ok(runs)
}

/// Popis běhu ze složky běhu.
pub fn info(run: &Path) -> Result<RunInfo, String> {
    let path = run.join(INFO);
    let text = fs::read_to_string(&path).map_err(|e| err(&path, e))?;
    let mut info: RunInfo = serde_json::from_str(&text).map_err(|e| err(&path, e))?;
    if info.status == Status::Running && info.pid != std::process::id() {
        info.status = Status::Interrupted;
    }
    info.checkpoints = checkpoint_files(run)?.len();
    info.has_result = run.join(RESULT).is_file();
    Ok(info)
}

/// Zadání, ze kterého běh vznikl.
pub fn spec(run: &Path) -> Result<Value, String> {
    let path = run.join(SPEC);
    let text = fs::read_to_string(&path).map_err(|e| err(&path, e))?;
    serde_json::from_str(&text).map_err(|e| err(&path, e))
}

/// Výsledek (export enginu), je-li běh hotový.
pub fn result(run: &Path) -> Result<Option<Value>, String> {
    let path = run.join(RESULT);
    if !path.is_file() {
        return Ok(None);
    }
    serde_json::from_slice(&gunzip(&path)?)
        .map(Some)
        .map_err(|e| err(&path, e))
}

/// Snímky od pořadí `since`.
pub fn frames(run: &Path, since: usize) -> Result<Vec<Value>, String> {
    let path = run.join(FRAMES);
    read_lines(&path)?
        .into_iter()
        .skip(since)
        .map(|l| serde_json::from_str(&l).map_err(|e| err(&path, e)))
        .collect()
}

fn lexicon_lines(run: &Path) -> Result<Vec<LexiconLine>, String> {
    let path = run.join(LEXICON);
    read_lines(&path)?
        .into_iter()
        .map(|l| serde_json::from_str(&l).map_err(|e| err(&path, e)))
        .collect()
}

/// Roky, ve kterých je slovník zapsaný, a jazyky v nich.
pub fn lexicon_years(run: &Path) -> Result<Vec<(f64, Vec<String>)>, String> {
    let mut out: Vec<(f64, Vec<String>)> = Vec::new();
    for line in lexicon_lines(run)? {
        match out.last_mut() {
            Some((year, list)) if *year == line.year => list.push(line.language),
            _ => out.push((line.year, vec![line.language])),
        }
    }
    Ok(out)
}

/// Slovník jazyka v roce `year` (poslední zápis nejpozději v tom roce). `None`, když jazyk
/// v posledním zapsaném roce do `year` neexistoval.
pub fn lexicon(run: &Path, language: &str, year: f64) -> Result<Option<LanguageLexicon>, String> {
    let lines = lexicon_lines(run)?;
    let Some(at) = lines
        .iter()
        .map(|l| l.year)
        .filter(|&y| y <= year)
        .fold(None, |m: Option<f64>, y| Some(m.map_or(y, |m| m.max(y))))
    else {
        return Ok(None);
    };
    let mut forms: BTreeMap<String, String> = BTreeMap::new();
    let mut group = None;
    for line in lines
        .iter()
        .filter(|l| l.language == language && l.year <= at)
    {
        for (concept, form) in &line.forms {
            match form {
                Some(f) => forms.insert(concept.clone(), f.clone()),
                None => forms.remove(concept),
            };
        }
        if line.year == at {
            group = Some(line.group.clone());
        }
    }
    Ok(group.map(|group| LanguageLexicon { group, forms }))
}

/// Historie slova: každá změna tvaru pojmu v jazyce (rok, nový tvar).
pub fn word_history(run: &Path, language: &str, concept: &str) -> Result<Vec<WordForm>, String> {
    Ok(lexicon_lines(run)?
        .into_iter()
        .filter(|l| l.language == language)
        .filter_map(|l| {
            l.forms.get(concept).map(|form| WordForm {
                year: l.year,
                form: form.clone(),
            })
        })
        .collect())
}

/// Kontrolní body složky běhu, seřazené podle roku.
fn checkpoint_files(run: &Path) -> Result<Vec<StoredCheckpoint>, String> {
    let dir = run.join(CHECKPOINTS);
    let entries = match fs::read_dir(&dir) {
        Ok(e) => e,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(e) => return Err(err(&dir, e)),
    };
    let mut out: Vec<StoredCheckpoint> = entries
        .filter_map(Result::ok)
        .filter_map(|e| {
            let name = e.file_name().to_str()?.strip_suffix(".bin.gz")?.to_owned();
            let (tick, rest) = name.strip_prefix('t')?.split_once("_y")?;
            let (year, events) = rest.split_once("_e")?;
            Some(StoredCheckpoint {
                tick: tick.parse().ok()?,
                year: year.parse().ok()?,
                events: events.parse().ok()?,
                run: run.to_owned(),
                path: e.path(),
            })
        })
        .collect();
    out.sort_by(|a, b| {
        a.year
            .partial_cmp(&b.year)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    Ok(out)
}

/// Nejpozdější kontrolní bod ostře před rokem `year` (pro „co kdyby“ od roku větvení). Když ho
/// běh nemá (větev „co kdyby“ má vlastní body až od roku větvení), hledá u rodiče.
pub fn checkpoint_before(run: &Path, year: f64) -> Result<Option<StoredCheckpoint>, String> {
    if let Some(found) = checkpoint_files(run)?
        .into_iter()
        .rev()
        .find(|c| c.year < year)
    {
        return Ok(Some(found));
    }
    let about = info(run)?;
    match (about.parent, run.parent()) {
        (Some(parent), Some(dir)) if dir.join(&parent).join(INFO).is_file() => {
            let limit = about.branch_year.map_or(year, |b| b.min(year));
            checkpoint_before(&dir.join(parent), limit)
        }
        _ => Ok(None),
    }
}

/// Úplný kontrolní bod: stav světa z bodu a záznam událostí doplněný z `udalosti.jsonl.gz`
/// složky, ve které bod leží.
pub fn load_checkpoint(
    point: &StoredCheckpoint,
) -> Result<cee_engine::checkpoint::Checkpoint, String> {
    let mut checkpoint = cee_engine::checkpoint::Checkpoint::from_bytes(&gunzip(&point.path)?)?;
    let lines = read_lines(&point.run.join(EVENTS))?;
    if lines.len() < point.events {
        return Err(format!(
            "{}: záznam událostí má {} řádků, bod jich potřebuje {}",
            point.run.display(),
            lines.len(),
            point.events
        ));
    }
    for line in &lines[..point.events] {
        checkpoint.history.events.push_line(line);
    }
    Ok(checkpoint)
}

/// Stav modulu jmen na konci běhu (`RunWriter::add_names`), nebo `None`, když ho běh nemá
/// (vznikl bez modulu jmen nebo před ním).
pub fn names_state(run: &Path) -> Result<Option<cee_engine::checkpoint::Checkpoint>, String> {
    let path = run.join(NAMES);
    if !path.is_file() {
        return Ok(None);
    }
    cee_engine::checkpoint::Checkpoint::from_bytes(&gunzip(&path)?).map(Some)
}

/// Smaže kontrolní body běhu (zabírají nejvíc místa); běh zůstane čitelný, jen se z něj
/// nedá větvit bez přepočtu od začátku.
pub fn drop_checkpoints(run: &Path) -> Result<(), String> {
    let dir = run.join(CHECKPOINTS);
    match fs::remove_dir_all(&dir) {
        Err(e) if e.kind() != std::io::ErrorKind::NotFound => Err(err(&dir, e)),
        _ => Ok(()),
    }
}

/// Smaže běh se vším, co k němu patří.
pub fn delete(run: &Path) -> Result<(), String> {
    if !run.join(INFO).is_file() {
        return Err(format!("{} není složka běhu", run.display()));
    }
    fs::remove_dir_all(run).map_err(|e| err(run, e))
}

/// Přejmenuje běh v seznamu.
pub fn rename(run: &Path, name: Option<&str>) -> Result<(), String> {
    let mut current = info(run)?;
    current.name = name.map(str::to_owned);
    write_info(run, &current)
}

/// Velikost dat běhu v bajtech po souborech.
pub fn size(run: &Path) -> BTreeMap<&'static str, u64> {
    let len = |p: PathBuf| fs::metadata(p).map(|m| m.len()).unwrap_or(0);
    let checkpoints = checkpoint_files(run)
        .unwrap_or_default()
        .into_iter()
        .map(|c| len(c.path))
        .sum();
    BTreeMap::from([
        ("frames", len(run.join(FRAMES))),
        ("events", len(run.join(EVENTS))),
        ("lexicon", len(run.join(LEXICON))),
        ("result", len(run.join(RESULT))),
        ("checkpoints", checkpoints),
        ("names", len(run.join(NAMES))),
    ])
}

fn write_info(run: &Path, info: &RunInfo) -> Result<(), String> {
    let mut stored = info.clone();
    stored.checkpoints = 0;
    stored.has_result = false;
    let text = serde_json::to_string_pretty(&stored).map_err(|e| err(run, e))?;
    write_atomic(&run.join(INFO), format!("{text}\n").as_bytes())
}

/// Zápis jednoho běhu do jeho složky.
pub struct RunWriter {
    pub dir: PathBuf,
    pub info: RunInfo,
    /// Kolik řádků záznamu událostí už je v souboru.
    pub events: usize,
    /// Kontrolní bod, který se právě balí a zapisuje na pozadí.
    pending: Option<std::thread::JoinHandle<Result<(), String>>>,
    /// Poslední zapsaný slovník (jazyk → pojem → tvar), aby se zapisovaly jen změny.
    last_forms: BTreeMap<String, BTreeMap<String, String>>,
}

impl RunWriter {
    /// Založí složku běhu ve složce běhů `dir` (vytvoří ji) a zapíše zadání a `beh.json`.
    pub fn create(dir: &Path, new: &NewRun<'_>) -> Result<RunWriter, String> {
        fs::create_dir_all(dir).map_err(|e| err(dir, e))?;
        let created = now();
        let base = stamp(created);
        let mut id = base.clone();
        let mut n = 1;
        while dir.join(&id).exists() {
            n += 1;
            id = format!("{base}-{n}");
        }
        let run = dir.join(&id);
        fs::create_dir(&run).map_err(|e| err(&run, e))?;
        let spec = new.spec.cloned().unwrap_or(Value::Null);
        let start = spec["start_year"].as_f64().unwrap_or(0.0);
        let info = RunInfo {
            format: RUN_FORMAT.into(),
            id,
            name: new.name.map(str::to_owned),
            spec_hash: spec_hash(&spec),
            parent: new.parent.map(str::to_owned),
            branch_year: new.branch_year,
            start_year: start,
            end_year: spec["end_year"].as_f64().unwrap_or(start),
            year: start,
            status: Status::Running,
            error: None,
            seconds: 0.0,
            created,
            finished: None,
            engine: new.engine.map(str::to_owned),
            frames: 0,
            pid: std::process::id(),
            checkpoints: 0,
            has_result: false,
        };
        let text = serde_json::to_string_pretty(&spec).map_err(|e| err(&run, e))?;
        write_atomic(&run.join(SPEC), format!("{text}\n").as_bytes())?;
        write_info(&run, &info)?;
        Ok(RunWriter {
            dir: run,
            info,
            events: 0,
            pending: None,
            last_forms: BTreeMap::new(),
        })
    }

    /// Průběžný snímek (`export::frame`); posune i rok běhu.
    pub fn add_frame(&mut self, frame: &Value, seconds: f64) -> Result<(), String> {
        let line = serde_json::to_string(frame).map_err(|e| err(&self.dir, e))?;
        append_lines(&self.dir.join(FRAMES), &[line])?;
        self.info.frames += 1;
        if let Some(year) = frame["year"].as_f64() {
            self.info.year = year;
        }
        self.info.seconds = seconds;
        write_info(&self.dir, &self.info)
    }

    /// Slovník jazyků v roce `year` (`export::language_lexicons`); zapíše jen změněné tvary.
    /// Vrátí počet zapsaných tvarů.
    pub fn add_lexicon(
        &mut self,
        year: f64,
        lexicons: &BTreeMap<String, LanguageLexicon>,
    ) -> Result<usize, String> {
        let mut lines = Vec::new();
        let mut written = 0;
        for (language, lexicon) in lexicons {
            let before = self.last_forms.entry(language.clone()).or_default();
            let mut forms: BTreeMap<String, Option<String>> = lexicon
                .forms
                .iter()
                .filter(|(c, f)| before.get(*c) != Some(f))
                .map(|(c, f)| (c.clone(), Some(f.clone())))
                .collect();
            for concept in before.keys() {
                if !lexicon.forms.contains_key(concept) {
                    forms.insert(concept.clone(), None);
                }
            }
            written += forms.len();
            *before = lexicon.forms.clone();
            let line = LexiconLine {
                year,
                language: language.clone(),
                group: lexicon.group.clone(),
                forms,
            };
            lines.push(serde_json::to_string(&line).map_err(|e| err(&self.dir, e))?);
        }
        append_lines(&self.dir.join(LEXICON), &lines)?;
        Ok(written)
    }

    /// Připíše řádky záznamu událostí (pokračování od `self.events`).
    pub fn add_events(&mut self, lines: &[String]) -> Result<(), String> {
        append_lines(&self.dir.join(EVENTS), lines)?;
        self.events += lines.len();
        Ok(())
    }

    /// Kontrolní bod bez záznamu událostí (`Simulation::checkpoint_without_events`); patří k němu
    /// prvních `events` řádků záznamu (záznam musí být zapsaný aspoň po ně).
    pub fn add_checkpoint(
        &mut self,
        tick: u32,
        year: f64,
        events: usize,
        bytes: &[u8],
    ) -> Result<(), String> {
        if events > self.events {
            return Err(format!(
                "kontrolní bod potřebuje {events} řádků záznamu, zapsáno {}",
                self.events
            ));
        }
        let dir = self.dir.join(CHECKPOINTS);
        fs::create_dir_all(&dir).map_err(|e| err(&dir, e))?;
        // předchozí bod musí být zapsaný (v paměti je nejvýš jeden rozbalený bod navíc)
        self.wait()?;
        let path = dir.join(format!("t{tick:05}_y{year}_e{events}.bin.gz"));
        let bytes = bytes.to_vec();
        self.pending = Some(
            std::thread::Builder::new()
                .name("cee-bod".into())
                .spawn(move || write_atomic(&path, &gzip_level(&bytes, 1)))
                .map_err(|e| err(&self.dir, e))?,
        );
        Ok(())
    }

    /// Počká, až se zapíše kontrolní bod balený na pozadí.
    pub fn wait(&mut self) -> Result<(), String> {
        match self.pending.take() {
            Some(handle) => handle
                .join()
                .map_err(|_| format!("{}: zápis kontrolního bodu spadl", self.dir.display()))?,
            None => Ok(()),
        }
    }

    /// „Co kdyby“: převezme od rodiče snímky a slovník do roku bodu (včetně) a záznam událostí
    /// do bodu, aby větev měla celou časovou osu; kontrolní body zůstanou u rodiče.
    pub fn branch_from(&mut self, point: &StoredCheckpoint) -> Result<(), String> {
        let parent = &point.run;
        let until_year = point.year;
        let frames: Vec<String> = read_lines(&parent.join(FRAMES))?
            .into_iter()
            .filter(|l| {
                serde_json::from_str::<Value>(l)
                    .ok()
                    .and_then(|v| v["year"].as_f64())
                    .is_some_and(|y| y <= until_year)
            })
            .collect();
        self.info.frames += frames.len();
        append_lines(&self.dir.join(FRAMES), &frames)?;
        let mut lines = Vec::new();
        for line in lexicon_lines(parent)?
            .into_iter()
            .filter(|l| l.year <= until_year)
        {
            let forms = self.last_forms.entry(line.language.clone()).or_default();
            for (concept, form) in &line.forms {
                match form {
                    Some(f) => forms.insert(concept.clone(), f.clone()),
                    None => forms.remove(concept),
                };
            }
            lines.push(serde_json::to_string(&line).map_err(|e| err(&self.dir, e))?);
        }
        append_lines(&self.dir.join(LEXICON), &lines)?;
        let mut events = read_lines(&parent.join(EVENTS))?;
        events.truncate(point.events);
        self.add_events(&events)?;
        self.info.year = until_year;
        write_info(&self.dir, &self.info)
    }

    /// Stav modulu jmen na konci běhu: kontrolní bod se světem a jmény (bez historie), ze kterého
    /// generátor jmen skládá jména i po novém spuštění aplikace. Kontrolní body ho nemažou.
    pub fn add_names(&mut self, point: &cee_engine::checkpoint::Checkpoint) -> Result<(), String> {
        write_atomic(&self.dir.join(NAMES), &gzip_level(&point.to_bytes()?, 1))
    }

    /// Konec běhu: stav, chyba, doba a (u hotového) výsledek.
    pub fn finish(
        &mut self,
        status: Status,
        error: Option<&str>,
        seconds: f64,
        result: Option<&Value>,
    ) -> Result<(), String> {
        self.wait()?;
        if let Some(result) = result {
            let bytes = serde_json::to_vec(result).map_err(|e| err(&self.dir, e))?;
            write_atomic(&self.dir.join(RESULT), &gzip(&bytes))?;
            if let Some(year) = result["year"].as_f64() {
                self.info.year = year;
            }
        }
        self.info.status = status;
        self.info.error = error.map(str::to_owned);
        self.info.seconds = seconds;
        self.info.finished = Some(now());
        write_info(&self.dir, &self.info)
    }

    /// Popis pro UI (jako [`info`]).
    pub fn describe(&self) -> Value {
        json!(self.info)
    }
}

impl Drop for RunWriter {
    fn drop(&mut self) {
        let _ = self.wait();
    }
}

/// Jazyky, které se ve slovníku běhu kdy objevily.
pub fn lexicon_languages(run: &Path) -> Result<BTreeSet<String>, String> {
    Ok(lexicon_lines(run)?
        .into_iter()
        .map(|l| l.language)
        .collect())
}

#[cfg(test)]
mod tests;
