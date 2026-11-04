//! Pozorování: linie jazyků mezi snímky (zrcadlo `observe.LineageTracker`).
//!
//! Shluky skupin počítá `cee_core::observe` (průměrná vazba s omezením sousedství);
//! tady se párují shluky mezi snímky a zapisují rozštěpení jazyků. Členové linie se
//! drží jako **jména** skupin (jména se nemění, pořadí podle jmen jako v Pythonu).

use std::collections::{BTreeMap, BTreeSet, HashMap};

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use crate::rng::{Part, stable_id};

/// Páruje shluky jazyků mezi snímky a zapisuje jejich rozštěpení.
///
/// Nový shluk zdědí linii toho předchozího, s nímž sdílí nejvíc skupin. Když z jedné
/// linie vzejde víc shluků, největší pokračuje a ostatní jsou nové linie odštěpené od
/// ní. Z těchto záznamů vzniká emergentní strom jazyků.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct LineageTracker {
    /// ID linie → členové (seřazená jména skupin).
    pub lineages: BTreeMap<String, Vec<String>>,
}

/// Výsledek `update`: linie → členové a události (`language_emerged`, `language_split`,
/// `language_ended`).
pub struct LineageUpdate {
    pub languages: BTreeMap<String, Vec<String>>,
    pub events: Vec<Value>,
}

impl LineageTracker {
    /// Linie, do které skupina (jméno) patří.
    pub fn member_of(&self) -> HashMap<&str, &str> {
        let mut map = HashMap::new();
        for (lineage, members) in &self.lineages {
            for member in members {
                map.insert(member.as_str(), lineage.as_str());
            }
        }
        map
    }

    pub fn update(&mut self, clusters: &[Vec<String>], tick: u32) -> LineageUpdate {
        let member_of = self.member_of();
        // Rodič každého shluku: linie s největším překryvem (při shodě menší ID).
        let mut claims: BTreeMap<Option<String>, Vec<BTreeSet<&str>>> = BTreeMap::new();
        for cluster in clusters {
            let members: BTreeSet<&str> = cluster.iter().map(String::as_str).collect();
            let mut overlap: BTreeMap<&str, usize> = BTreeMap::new();
            for name in &members {
                if let Some(&lineage) = member_of.get(name) {
                    *overlap.entry(lineage).or_default() += 1;
                }
            }
            let parent = overlap
                .iter()
                .max_by(|a, b| a.1.cmp(b.1).then(b.0.cmp(a.0)))
                .map(|(&lineage, _)| lineage.to_owned());
            claims.entry(parent).or_default().push(members);
        }
        let mut events = Vec::new();
        let mut assigned: BTreeMap<String, Vec<String>> = BTreeMap::new();
        // Pořadí rodičů: nejdřív pojmenovaní podle ID, nakonec „žádný“.
        let mut parents: Vec<&Option<String>> = claims.keys().collect();
        parents.sort_by(|a, b| (a.is_none(), a.as_deref()).cmp(&(b.is_none(), b.as_deref())));
        for parent in parents {
            let previous: BTreeSet<&str> = parent
                .as_deref()
                .and_then(|p| self.lineages.get(p))
                .map(|v| v.iter().map(String::as_str).collect())
                .unwrap_or_default();
            let mut successors: Vec<&BTreeSet<&str>> = claims[parent].iter().collect();
            successors.sort_by(|a, b| {
                let overlap_a = a.intersection(&previous).count();
                let overlap_b = b.intersection(&previous).count();
                overlap_b
                    .cmp(&overlap_a)
                    .then(b.len().cmp(&a.len()))
                    .then(a.iter().next().cmp(&b.iter().next()))
            });
            for (position, members) in successors.into_iter().enumerate() {
                let sorted: Vec<String> = members.iter().map(|s| (*s).to_owned()).collect();
                if let (Some(parent), 0) = (parent, position) {
                    assigned.insert(parent.clone(), sorted);
                    continue;
                }
                let first = members.iter().next().copied().unwrap_or("");
                let lineage = stable_id(
                    "lineage",
                    &[
                        Part::from(parent.as_deref().unwrap_or("None")),
                        Part::from(tick),
                        Part::from(first),
                    ],
                );
                events.push(json!({
                    "kind": if parent.is_some() { "language_split" } else { "language_emerged" },
                    "lineage": lineage,
                    "parent": parent,
                    "groups": sorted,
                }));
                assigned.insert(lineage, sorted);
            }
        }
        for lineage in self.lineages.keys() {
            if !assigned.contains_key(lineage) {
                events.push(json!({"kind": "language_ended", "lineage": lineage}));
            }
        }
        self.lineages = assigned.clone();
        LineageUpdate {
            languages: assigned,
            events,
        }
    }
}
