//! Události světa: rozhraní pro R1d.
//!
//! Událost zasahuje do světa v kroku, ve kterém její rok nastal (`Simulation::step`
//! ji zavolá fáze `events`). R0 definuje jen rozhraní ([`WorldEvent`]) a datový nosič
//! [`PendingEvent`], do kterého scénáře a popis světa (`WorldSpec`) ukládají druh
//! a parametry události. Skutečné provedení (`State`, `Conquest`, `Contact`, …)
//! přináší R1d: přidá konkrétní typy, které `WorldEvent` implementují, a převodník
//! [`from_pending`] je začne vracet místo `PendingEvent`.

use serde_json::Value;

use crate::history::History;
use crate::world::World;

/// Událost v dějinách světa.
pub trait WorldEvent: Send + Sync + std::fmt::Debug {
    /// Rok, od kterého událost působí.
    fn year(&self) -> f64;
    /// Druh události (`state`, `conquest`, …) – klíč záznamu v historii.
    fn kind(&self) -> &str;
    /// Provede událost: změní svět a zapíše záznamy do historie.
    fn apply(&self, world: &mut World, history: &mut History, tick: u32) -> Result<(), String>;
    /// Popis (druh a parametry) pro uložení a porovnání událostí.
    fn describe(&self) -> Value;
}

/// Událost, kterou R0 ještě neumí provést: nese druh a parametry.
#[derive(Clone, Debug)]
pub struct PendingEvent {
    pub year: f64,
    pub kind: String,
    pub params: Value,
}

impl PendingEvent {
    pub fn new(year: f64, kind: &str, params: Value) -> PendingEvent {
        PendingEvent { year, kind: kind.to_owned(), params }
    }
}

impl WorldEvent for PendingEvent {
    fn year(&self) -> f64 {
        self.year
    }

    fn kind(&self) -> &str {
        &self.kind
    }

    fn apply(&self, _world: &mut World, _history: &mut History, _tick: u32) -> Result<(), String> {
        Err(format!("Událost '{}' (rok {}) zatím nemá provedení v Rustu (patří R1d).", self.kind, self.year))
    }

    fn describe(&self) -> Value {
        serde_json::json!({"year": self.year, "kind": self.kind, "params": self.params})
    }
}

/// Převede popis události na provedenou událost; R1d sem doplňuje konkrétní druhy.
pub fn from_pending(pending: PendingEvent) -> Box<dyn WorldEvent> {
    Box::new(pending)
}
