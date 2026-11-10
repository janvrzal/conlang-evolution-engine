//! Auditní historie běhu: log událostí, snímky a volitelné dráhy (zrcadlo `cee.v2.history`).
//!
//! Záznam je JSON objekt s `kind`, `tick`, `year` a obsahem (stejná schémata jako
//! v Pythonu, aby UI a `runner.py` fungovaly beze změny). Čísla se zaokrouhlují
//! na 6 míst, aby otisk běhu nezávisel na posledních bitech sčítání.

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};

use crate::ids::{GroupId, VariantId};

const DECIMALS: f64 = 1e6;

fn rounded(value: f64) -> f64 {
    (value * DECIMALS).round() / DECIMALS
}

/// Zaokrouhlí všechna desetinná čísla ve vnořené hodnotě.
fn round_value(value: Value) -> Value {
    match value {
        Value::Number(n) if n.is_f64() => {
            serde_json::Number::from_f64(rounded(n.as_f64().unwrap_or(0.0)))
                .map_or(Value::Null, Value::Number)
        }
        Value::Array(items) => Value::Array(items.into_iter().map(round_value).collect()),
        Value::Object(map) => {
            Value::Object(map.into_iter().map(|(k, v)| (k, round_value(v))).collect())
        }
        other => other,
    }
}

/// Snímek pozorování (dialekty a jazyky); jména skupin jsou už rozepsaná.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct Snapshot {
    pub tick: u32,
    pub year: f64,
    pub dialects: Vec<Vec<String>>,
    /// Linie jazyka → skupiny, které ji právě mluví.
    pub languages: std::collections::BTreeMap<String, Vec<String>>,
    /// Jména mluvených skupin v pořadí řádků `distances` (vyplňují se vždy).
    #[serde(default)]
    pub group_ids: Vec<String>,
    /// Čtvercová matice vzdáleností mluvených skupin po řádcích (`code_distances`); jen s
    /// `keep_distances`, protože roste se čtvercem počtu skupin.
    #[serde(default)]
    pub distances: Option<Vec<f64>>,
}

/// Kolik bajtů záznamů smí zůstat v paměti; starší se připíší do dočasného souboru.
pub const SPILL_BYTES: usize = 32 << 20;

/// Dočasný soubor se staršími záznamy (jen se připisuje; smaže se hned po otevření, takže po
/// běhu nezůstane na disku ani po pádu).
#[derive(Debug)]
struct Spill {
    file: std::fs::File,
    /// Kolik bajtů logu je v souboru (záznamy od začátku logu).
    bytes: usize,
}

impl Spill {
    fn create() -> std::io::Result<Spill> {
        use std::sync::atomic::{AtomicUsize, Ordering};
        static COUNTER: AtomicUsize = AtomicUsize::new(0);
        let path = std::env::temp_dir().join(format!(
            "cee-historie-{}-{}.jsonl",
            std::process::id(),
            COUNTER.fetch_add(1, Ordering::Relaxed)
        ));
        let file = std::fs::OpenOptions::new()
            .read(true)
            .write(true)
            .create_new(true)
            .open(&path)?;
        // Na Unixu soubor žije, dokud je otevřený; jinde se smaže až při zavření (`Drop`).
        let _ = std::fs::remove_file(&path);
        Ok(Spill { file, bytes: 0 })
    }

    fn append(&mut self, text: &str) -> std::io::Result<()> {
        use std::io::Write;
        self.file.write_all(text.as_bytes())?;
        self.bytes += text.len();
        Ok(())
    }

    fn read(&self, start: usize, end: usize) -> String {
        let mut buffer = vec![0_u8; end - start];
        read_at(&self.file, &mut buffer, start as u64).expect("čtení historie z dočasného souboru");
        String::from_utf8(buffer).expect("záznam historie je UTF-8")
    }
}

#[cfg(unix)]
fn read_at(file: &std::fs::File, buffer: &mut [u8], offset: u64) -> std::io::Result<()> {
    std::os::unix::fs::FileExt::read_exact_at(file, buffer, offset)
}

#[cfg(windows)]
fn read_at(file: &std::fs::File, buffer: &mut [u8], offset: u64) -> std::io::Result<()> {
    let mut done = 0;
    while done < buffer.len() {
        let read = std::os::windows::fs::FileExt::seek_read(
            file,
            &mut buffer[done..],
            offset + done as u64,
        )?;
        if read == 0 {
            return Err(std::io::ErrorKind::UnexpectedEof.into());
        }
        done += read;
    }
    Ok(())
}

/// Záznamy historie uložené kompaktně: každý záznam jako řádek JSON (klíče seřazené, přesně ten
/// text, ze kterého se počítá otisk), k tomu konec řádku a číslo druhu. Objekt se z řádku sestaví
/// až při čtení (`iter`, `get`, `History::of_kind`).
///
/// Text se s během jen připisuje a čte se zřídka (měřidla, export), proto v paměti zůstává jen
/// posledních [`SPILL_BYTES`] bajtů; starší jsou v dočasném souboru. V paměti tak zbývá rejstřík
/// (konec a druh záznamu). Dlouhý běh Evropy jinak držel stovky MB záznamů.
#[derive(Debug, Default)]
pub struct EventLog {
    /// Záznamy od `spilled()` dál.
    text: String,
    /// Konce řádků v celém logu (bajty od začátku logu).
    ends: Vec<usize>,
    kinds: Vec<u16>,
    kind_names: Vec<String>,
    spill: Option<Spill>,
    /// Limit textu v paměti (0 = [`SPILL_BYTES`]; testy volí menší).
    limit: usize,
}

impl Clone for EventLog {
    /// Kopie má všechny záznamy v paměti (kontrolní body; přesune se jen to, co je potřeba).
    fn clone(&self) -> Self {
        EventLog {
            text: self.lines().collect(),
            ends: self.ends.clone(),
            kinds: self.kinds.clone(),
            kind_names: self.kind_names.clone(),
            spill: None,
            limit: self.limit,
        }
    }
}

impl PartialEq for EventLog {
    fn eq(&self, other: &Self) -> bool {
        self.ends == other.ends
            && self.kinds.len() == other.kinds.len()
            && (0..self.len()).all(|index| self.kind_name(index) == other.kind_name(index))
            && self.lines().eq(other.lines())
    }
}

impl EventLog {
    /// Log, který odkládá na disk už nad `limit` bajtů textu.
    pub fn with_limit(limit: usize) -> EventLog {
        EventLog {
            limit,
            ..EventLog::default()
        }
    }

    pub fn len(&self) -> usize {
        self.ends.len()
    }

    pub fn is_empty(&self) -> bool {
        self.ends.is_empty()
    }

    fn spilled(&self) -> usize {
        self.spill.as_ref().map_or(0, |spill| spill.bytes)
    }

    /// Druh záznamu bez sestavení objektu (`None` mimo rozsah).
    pub fn kind_of(&self, index: usize) -> Option<&str> {
        (index < self.kinds.len()).then(|| self.kind_name(index))
    }

    fn kind_name(&self, index: usize) -> &str {
        &self.kind_names[self.kinds[index] as usize]
    }

    pub fn push(&mut self, event: Map<String, Value>) {
        let kind = event.get("kind").and_then(Value::as_str).unwrap_or("");
        let number = match self.kind_names.iter().position(|name| name == kind) {
            Some(found) => found,
            None => {
                self.kind_names.push(kind.to_owned());
                self.kind_names.len() - 1
            }
        };
        self.text
            .push_str(&serde_json::to_string(&event).expect("JSON"));
        self.ends.push(self.spilled() + self.text.len());
        self.kinds.push(number as u16);
        let limit = if self.limit == 0 {
            SPILL_BYTES
        } else {
            self.limit
        };
        if self.text.len() > limit {
            self.spill_text();
        }
    }

    /// Připíše text v paměti do dočasného souboru; když soubor nejde založit, zůstane v paměti.
    fn spill_text(&mut self) {
        if self.spill.is_none() {
            match Spill::create() {
                Ok(spill) => self.spill = Some(spill),
                Err(_) => return,
            }
        }
        let spill = self.spill.as_mut().expect("soubor historie");
        spill
            .append(&self.text)
            .expect("zápis historie do dočasného souboru");
        self.text.clear();
    }

    /// Připíše hotový řádek JSON (záznam uložený dřív, např. ze souboru běhu); druh vezme
    /// z pole `kind` bez rozboru celého řádku.
    pub fn push_line(&mut self, line: &str) {
        let kind = line
            .find("\"kind\":\"")
            .map(|at| &line[at + 8..])
            .and_then(|rest| rest.find('"').map(|end| &rest[..end]))
            .unwrap_or("");
        let number = match self.kind_names.iter().position(|name| name == kind) {
            Some(found) => found,
            None => {
                self.kind_names.push(kind.to_owned());
                self.kind_names.len() - 1
            }
        };
        self.text.push_str(line);
        self.ends.push(self.spilled() + self.text.len());
        self.kinds.push(number as u16);
        let limit = if self.limit == 0 {
            SPILL_BYTES
        } else {
            self.limit
        };
        if self.text.len() > limit {
            self.spill_text();
        }
    }

    pub fn extend(&mut self, events: impl IntoIterator<Item = Map<String, Value>>) {
        for event in events {
            self.push(event);
        }
    }

    /// Řádek JSON záznamu číslo `index`.
    pub fn line(&self, index: usize) -> std::borrow::Cow<'_, str> {
        let start = if index == 0 { 0 } else { self.ends[index - 1] };
        let end = self.ends[index];
        let spilled = self.spilled();
        if start >= spilled {
            std::borrow::Cow::Borrowed(&self.text[start - spilled..end - spilled])
        } else {
            std::borrow::Cow::Owned(
                self.spill
                    .as_ref()
                    .expect("soubor historie")
                    .read(start, end),
            )
        }
    }

    /// Řádky po řadě; ze souboru se čtou po větších kusech.
    pub fn lines(&self) -> impl Iterator<Item = std::borrow::Cow<'_, str>> + '_ {
        const CHUNK: usize = 8 << 20;
        let spilled = self.spilled();
        let mut buffer = String::new();
        let mut buffer_start = 0_usize;
        (0..self.len()).map(move |index| {
            let start = if index == 0 { 0 } else { self.ends[index - 1] };
            let end = self.ends[index];
            if start >= spilled {
                return std::borrow::Cow::Borrowed(&self.text[start - spilled..end - spilled]);
            }
            if start < buffer_start || end > buffer_start + buffer.len() {
                // Další kus souboru: od začátku záznamu po konec posledního celého záznamu v kusu.
                let limit = (start + CHUNK).max(end).min(spilled);
                let last = self.ends.partition_point(|&e| e <= limit);
                let stop = self.ends[last.saturating_sub(1)].max(end).min(spilled);
                buffer = self
                    .spill
                    .as_ref()
                    .expect("soubor historie")
                    .read(start, stop);
                buffer_start = start;
            }
            std::borrow::Cow::Owned(buffer[start - buffer_start..end - buffer_start].to_owned())
        })
    }

    /// Záznam číslo `index` jako objekt.
    pub fn get(&self, index: usize) -> Option<Map<String, Value>> {
        (index < self.len())
            .then(|| serde_json::from_str(&self.line(index)).expect("záznam historie je JSON"))
    }

    /// Všechny záznamy po řadě jako objekty.
    pub fn iter(&self) -> impl Iterator<Item = Map<String, Value>> + '_ {
        self.lines()
            .map(|line| serde_json::from_str(&line).expect("záznam historie je JSON"))
    }

    /// Záznamy daného druhu; ostatní řádky se nerozebírají.
    pub fn of_kind<'a>(&'a self, kind: &str) -> impl Iterator<Item = Map<String, Value>> + 'a {
        let wanted = self.kind_names.iter().position(|name| name == kind);
        (0..self.len())
            .filter(move |&index| Some(self.kinds[index] as usize) == wanted)
            .filter_map(|index| self.get(index))
    }
}

/// Kontrolní body ukládají záznamy jako jediný řetězec s polem JSON.
impl Serialize for EventLog {
    fn serialize<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        let mut text =
            String::with_capacity(self.ends.last().copied().unwrap_or(0) + self.len() + 2);
        text.push('[');
        for (index, line) in self.lines().enumerate() {
            if index > 0 {
                text.push(',');
            }
            text.push_str(&line);
        }
        text.push(']');
        serializer.serialize_str(&text)
    }
}

impl<'de> Deserialize<'de> for EventLog {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        let events: Vec<Map<String, Value>> = crate::json_string::deserialize(deserializer)?;
        let mut log = EventLog::default();
        log.extend(events);
        Ok(log)
    }
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct History {
    pub events: EventLog,
    pub snapshots: Vec<Snapshot>,
    /// (varianta, skupina) → [(tik, frekvence)]; plní se jen na vyžádání.
    pub trajectories: std::collections::BTreeMap<(VariantId, GroupId), Vec<(u32, f64)>>,
    /// Slovník protojazyků na startu běhu (jazyk → skupina a tvary), viz `export::code_language_lexicons`.
    #[serde(default)]
    pub proto: std::collections::BTreeMap<String, crate::export::LanguageLexicon>,
}

impl History {
    /// Zapíše událost; `payload` je JSON objekt s obsahem záznamu.
    pub fn record(&mut self, kind: &str, tick: u32, year: f64, payload: Value) {
        self.events.push(History::event(kind, tick, year, payload));
    }

    /// Záznam jako objekt (čistá funkce argumentů), aby se víc záznamů dalo sestavit souběžně
    /// a zapsat potom po řadě (`record` nebo `events.extend`).
    pub fn event(kind: &str, tick: u32, year: f64, payload: Value) -> Map<String, Value> {
        let mut event = Map::new();
        event.insert("kind".into(), kind.into());
        event.insert("tick".into(), tick.into());
        event.insert("year".into(), rounded(year).into());
        if let Value::Object(items) = payload {
            for (key, value) in items {
                event.insert(key, round_value(value));
            }
        }
        event
    }

    pub fn of_kind<'a>(&'a self, kind: &str) -> impl Iterator<Item = Map<String, Value>> + 'a {
        self.events.of_kind(kind)
    }

    /// Řádky logu: JSON s řazenými klíči (`json.dumps(sort_keys=True)`).
    pub fn lines(&self) -> Vec<String> {
        // `serde_json::Map` bez `preserve_order` drží klíče seřazené.
        self.events.lines().map(|line| line.into_owned()).collect()
    }

    /// Otisk celého logu (SHA-256 nad řádky); dva běhy se stejným semínkem ho mají shodný.
    ///
    /// Zápis desetinných čísel a nelatinských znaků se může lišit od Pythonu (`ensure_ascii`),
    /// otisk je proto určený k porovnání běhů Rustu mezi sebou, ne s otiskem Pythonu.
    pub fn digest(&self) -> String {
        let mut hash = Sha256::new();
        for line in self.events.lines() {
            hash.update(line.as_bytes());
            hash.update(b"\n");
        }
        hash.finalize()
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn filled(log: &mut EventLog) {
        for index in 0..5000 {
            let kind = ["innovation", "established", "language_shift"][index % 3];
            log.push(History::event(
                kind,
                index as u32,
                index as f64 * 0.5,
                serde_json::json!({"group": format!("g{index}"), "share": 1.0 / (index + 1) as f64}),
            ));
        }
    }

    #[test]
    fn odlozeny_log_cte_stejne_jako_v_pameti() {
        let (mut memory, mut spilled) =
            (EventLog::with_limit(usize::MAX), EventLog::with_limit(1000));
        filled(&mut memory);
        filled(&mut spilled);
        assert!(spilled.spilled() > 0 && memory.spilled() == 0);
        assert!(memory.lines().eq(spilled.lines()));
        assert_eq!(memory.get(1234), spilled.get(1234));
        assert_eq!(memory.get(4999), spilled.get(4999));
        assert_eq!(
            memory.of_kind("established").count(),
            spilled.of_kind("established").count()
        );
        assert!(memory
            .of_kind("language_shift")
            .eq(spilled.of_kind("language_shift")));
        assert!(memory.iter().eq(spilled.iter()));
        assert_eq!(memory, spilled);
        assert_eq!(memory, spilled.clone());
        let digest = |log: EventLog| {
            History {
                events: log,
                ..History::default()
            }
            .digest()
        };
        assert_eq!(digest(memory.clone()), digest(spilled));
        let text = serde_json::to_string(&memory).unwrap();
        let back: EventLog = serde_json::from_str(&text).unwrap();
        assert_eq!(back, memory);
    }
}
