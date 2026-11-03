//! Společnost: státy, normy, hranice, obchod, pozadí dějin, sledování linií (R1d).
//!
//! Zrcadlo polí `World` z Pythonu, která patří událostem, politice, kontaktu
//! a pozorování: `states`, `standards`, `border_factors`, `base_prestige`,
//! `prestige_mirror`, `trade`, `edit_log`, `endonyms` a `LineageTracker`.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

use crate::ids::{ConceptId, GroupId, LanguageId};

/// Záznam o změně světa provedené událostí (`cee.v2.edits`): tik, operace, argumenty.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Edit {
    pub tick: u32,
    pub operation: String,
    #[serde(with = "crate::json_string")]
    pub arguments: serde_json::Value,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct SocietyState {
    /// Státy světa podle ID (obsah popíše R1d; zatím volný JSON se schématem exportu).
    #[serde(with = "crate::json_string")]
    pub states: BTreeMap<String, serde_json::Value>,
    /// Spisovné jazyky států a regionů: ID státu či regionu → psaný kód (skupina).
    pub standards: BTreeMap<String, GroupId>,
    /// Pojmy, ze kterých se skládá vlastní jméno jazyka (jen pro export).
    pub endonyms: BTreeMap<LanguageId, Vec<ConceptId>>,
    /// Vazby oslabené hranicí států: (zdroj, cíl) → použitý násobek.
    pub border_factors: BTreeMap<(GroupId, GroupId), f64>,
    /// Základní prestiž skupin před vlivem států a spisovných jazyků.
    pub base_prestige: BTreeMap<GroupId, f64>,
    /// Skupina → skupina, jejíž prestiž přebírá.
    pub prestige_mirror: BTreeMap<GroupId, GroupId>,
    /// Síla vazby z obchodu: dvojice skupin (menší číslo první) → část síly vazby.
    pub trade: BTreeMap<(GroupId, GroupId), f64>,
    /// Podíl lidí, kteří se za generaci přestěhují k sousedům (nula vypne migraci).
    pub migration: f64,
    /// Deník změn světa (na dynamiku nemá vliv).
    pub edit_log: Vec<Edit>,
    /// Linie jazyků z posledního pozorování: jméno linie → skupiny (párování shluků).
    pub lineages: BTreeMap<String, Vec<GroupId>>,
}
