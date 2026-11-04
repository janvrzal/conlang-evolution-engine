//! Engine CEE v2 celý v Rustu (základ R0).
//!
//! Čistý Rust bez PyO3. Jádra výpočtů (banka tvarů, zvukové procesy, přenos, tlaky,
//! indexy) bere z `cee_core` (bez vazby na Python); tady je datový model světa, náhoda,
//! stavba světa, historie a export, kostra smyčky a kontrolní body. Přehled architektury,
//! rozhraní fází pro R1 a stav hotového: `docs/engine-v2/19-engine-v-rustu.md`.

pub mod background;
pub mod changes;
pub mod checkpoint;
pub mod concepts;
pub mod contact;
pub mod data;
pub mod edits;
pub mod events;
pub mod export;
pub mod grammar;
pub mod history;
pub mod ids;
pub mod json_string;
pub mod legacy_numpy;
pub mod model;
pub mod observe;
pub mod parallel;
pub mod parameters;
pub mod phases;
pub mod polity;
pub mod protoform;
pub mod rng;
pub mod scenarios;
pub mod segments;
pub mod simulation;
pub mod spec;
pub mod state;
pub mod variation;
pub mod vocabulary;
pub mod world;

pub use ids::{
    CellId, CodeId, ConceptId, Form, FormId, GroupId, LanguageId, MorphemeId, ProcessId,
    TerritoryId, VariableId, VariantId, WordClassId,
};
pub use simulation::{Simulation, SimulationConfig};
pub use world::World;
