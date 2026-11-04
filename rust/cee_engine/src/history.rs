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

/// Záznamy historie uložené kompaktně: každý záznam jako řádek JSON (klíče seřazené, přesně ten
/// text, ze kterého se počítá otisk) v jednom řetězci, k tomu konec řádku a číslo druhu.
/// Objekt se z řádku sestaví až při čtení (`iter`, `get`, `History::of_kind`).
#[derive(Clone, Debug, Default, PartialEq)]
pub struct EventLog {
    text: String,
    ends: Vec<usize>,
    kinds: Vec<u16>,
    kind_names: Vec<String>,
}

impl EventLog {
    pub fn len(&self) -> usize {
        self.ends.len()
    }

    pub fn is_empty(&self) -> bool {
        self.ends.is_empty()
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
        self.ends.push(self.text.len());
        self.kinds.push(number as u16);
    }

    pub fn extend(&mut self, events: impl IntoIterator<Item = Map<String, Value>>) {
        for event in events {
            self.push(event);
        }
    }

    /// Řádek JSON záznamu číslo `index`.
    pub fn line(&self, index: usize) -> &str {
        let start = if index == 0 { 0 } else { self.ends[index - 1] };
        &self.text[start..self.ends[index]]
    }

    pub fn lines(&self) -> impl Iterator<Item = &str> + '_ {
        (0..self.len()).map(|index| self.line(index))
    }

    /// Záznam číslo `index` jako objekt.
    pub fn get(&self, index: usize) -> Option<Map<String, Value>> {
        (index < self.len())
            .then(|| serde_json::from_str(self.line(index)).expect("záznam historie je JSON"))
    }

    /// Všechny záznamy po řadě jako objekty.
    pub fn iter(&self) -> impl Iterator<Item = Map<String, Value>> + '_ {
        (0..self.len()).filter_map(|index| self.get(index))
    }

    /// Záznamy daného druhu; ostatní řádky se nerozebírají.
    pub fn of_kind<'a>(&'a self, kind: &str) -> impl Iterator<Item = Map<String, Value>> + 'a {
        let wanted = self.kind_names.iter().position(|name| name == kind);
        (0..self.len())
            .filter(move |&index| Some(self.kinds[index] as usize) == wanted)
            .filter_map(|index| self.get(index))
    }
}

impl std::ops::Index<usize> for EventLog {
    type Output = str;

    /// Řádek JSON záznamu (objekt viz [`EventLog::get`]).
    fn index(&self, index: usize) -> &str {
        self.line(index)
    }
}

/// Kontrolní body ukládají záznamy jako jediný řetězec s polem JSON.
impl Serialize for EventLog {
    fn serialize<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        let mut text = String::with_capacity(self.text.len() + self.len() + 2);
        text.push('[');
        for (index, line) in self.lines().enumerate() {
            if index > 0 {
                text.push(',');
            }
            text.push_str(line);
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
        self.events.lines().map(str::to_owned).collect()
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
