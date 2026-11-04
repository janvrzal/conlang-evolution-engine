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
    /// Jména mluvených skupin v pořadí řádků `distances` (jen s `keep_distances`).
    #[serde(default)]
    pub group_ids: Vec<String>,
    /// Čtvercová matice vzdáleností mluvených skupin po řádcích (`code_distances`); jen s
    /// `keep_distances`, protože roste se čtvercem počtu skupin.
    #[serde(default)]
    pub distances: Option<Vec<f64>>,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct History {
    #[serde(with = "crate::json_string")]
    pub events: Vec<Map<String, Value>>,
    pub snapshots: Vec<Snapshot>,
    /// (varianta, skupina) → [(tik, frekvence)]; plní se jen na vyžádání.
    pub trajectories: std::collections::BTreeMap<(VariantId, GroupId), Vec<(u32, f64)>>,
}

impl History {
    /// Zapíše událost; `payload` je JSON objekt s obsahem záznamu.
    pub fn record(&mut self, kind: &str, tick: u32, year: f64, payload: Value) {
        let mut event = Map::new();
        event.insert("kind".into(), kind.into());
        event.insert("tick".into(), tick.into());
        event.insert("year".into(), rounded(year).into());
        if let Value::Object(items) = payload {
            for (key, value) in items {
                event.insert(key, round_value(value));
            }
        }
        self.events.push(event);
    }

    pub fn of_kind<'a>(
        &'a self,
        kind: &'a str,
    ) -> impl Iterator<Item = &'a Map<String, Value>> + 'a {
        self.events
            .iter()
            .filter(move |e| e.get("kind").and_then(Value::as_str) == Some(kind))
    }

    /// Řádky logu: JSON s řazenými klíči (`json.dumps(sort_keys=True)`).
    pub fn lines(&self) -> Vec<String> {
        // `serde_json::Map` bez `preserve_order` drží klíče seřazené.
        self.events
            .iter()
            .map(|e| serde_json::to_string(e).expect("JSON"))
            .collect()
    }

    /// Otisk celého logu (SHA-256 nad řádky); dva běhy se stejným semínkem ho mají shodný.
    ///
    /// Zápis desetinných čísel a nelatinských znaků se může lišit od Pythonu (`ensure_ascii`),
    /// otisk je proto určený k porovnání běhů Rustu mezi sebou, ne s otiskem Pythonu.
    pub fn digest(&self) -> String {
        let mut hash = Sha256::new();
        for line in self.lines() {
            hash.update(line.as_bytes());
            hash.update(b"\n");
        }
        hash.finalize()
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect()
    }
}
