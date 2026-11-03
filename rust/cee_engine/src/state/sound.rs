//! Stav zvukových změn a fonologie (R1b).
//!
//! **Svět:** index prostředí a opor zvukových změn (`SoundIndex` z `cee_core::index`),
//! vzorky a hodnocení procesů, seedované sklony slov (`word_biases`), registrace
//! procesů v bance tvarů (`cee_core::bank::Bank::register_proc`).
//! **Kód:** fronty fonologizace (`pending`, `queued`), `restructured`, `fixed_since`,
//! `closed`, pořadí procesů (`order`) – v Pythonu `PhonologyState`.

use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct SoundWorldState {
    /// Verze indexu prostředí; roste, když se změní slovní zásoba nebo tvary.
    pub index_version: u64,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct SoundCodeState {
    /// Pořadí, ve kterém procesy kód zasáhly (chronologie změn tohoto kódu).
    pub order: Vec<crate::ids::ProcessId>,
}
