//! Stav zvukových změn a fonologie (R1b).
//!
//! **Svět:** index prostředí a opor zvukových změn (`cee_core::index::SoundIndex`),
//! sklony slov vůči procesům (`biases`), řádky procesů v bance tvarů a mezipaměť
//! čísel proměnných a změněných variant procesů. To všechno je **odvozený stav**: při
//! kopii světa (kontrolní bod, větev) a po obnově z disku se zahodí a postaví se znovu
//! z toho, co svět nese (tvary kódů, slovní zásoba, registr, procesy). Výsledek je tentýž.
//!
//! **Kód:** fronty fonologizace živých procesů (`cee_core::code_state::CodeState`: fronta
//! čekajících slov podle potřebného logitu, přepsaná slova, kdy se proces ustálil),
//! pořadí procesů, deník aktivací a uzavření a dominantní kořeny pro četnosti užití.
//! Fronty se ukládají do kontrolního bodu; paměť četností užití se po obnově doplní
//! z deníku dominantních kořenů (`PhonologyState::dominant_log`).

use std::fmt;
use std::sync::Mutex;

use cee_core::code_state::{CodeState, Proc};
use cee_core::index::SoundIndex;
use serde::{Deserialize, Serialize};

use crate::ids::{ProcessId, VariableId, VariantId};

/// Stav indexu prostředí a opor, který smí číst souběžně víc vláken (za zámkem).
///
/// Míry inovací se počítají přes skupiny souběžně a každá skupina si index dorovná sama
/// (`phonology::index`); skupiny jsou nezávislé a výsledek nezáleží na pořadí zpracování,
/// protože opory jsou celá čísla.
#[derive(Default)]
pub struct IndexState {
    pub index: Option<SoundIndex>,
    /// Pro každou skupinu (podle čísla): s jakým stavem kódu je v indexu dorovnána
    /// (verze tvarů, délka deníku slovní zásoby, počet slov, pravidlo přízvuku).
    pub synced: Vec<Option<(u64, usize, usize, u8)>>,
}

/// Odvozený stav světa, který se při kopii zahazuje.
#[derive(Default)]
pub struct Runtime {
    pub index: Mutex<IndexState>,
    /// Sklon slov vůči změně: `biases[proces][lexém]`, `NaN` = ještě nelosováno.
    pub biases: Vec<Vec<f64>>,
    /// Řádek procesu v bance tvarů podle čísla procesu (−1 = neregistrován).
    pub rows: Vec<i32>,
    /// Číslo procesu podle řádku v bance.
    pub row_process: Vec<ProcessId>,
    /// Proměnná a změněná varianta podle čísla procesu (`NONE`, dokud se nenajde).
    pub info: Vec<(VariableId, VariantId)>,
}

impl Clone for Runtime {
    fn clone(&self) -> Self {
        Runtime::default()
    }
}

impl fmt::Debug for Runtime {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "Runtime({} procesů v bance, {} sklonů)",
            self.row_process.len(),
            self.biases.len()
        )
    }
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct SoundWorldState {
    /// Verze indexu prostředí; roste, když se změní slovní zásoba nebo tvary.
    pub index_version: u64,
    #[serde(skip)]
    pub runtime: Runtime,
}

/// Fronty fonologizace kódu: obal `cee_core::code_state::CodeState`, který se dá uložit.
#[derive(Clone, Debug, Default)]
pub struct Queues(pub CodeState);

#[derive(Clone, Serialize, Deserialize)]
struct ProcRepr {
    number: usize,
    live: bool,
    reductive: bool,
    queued: Vec<u8>,
    done: Vec<u8>,
    needed: Vec<f64>,
    morphemes: Vec<i32>,
    fixed_since: Option<i64>,
}

#[derive(Clone, Serialize, Deserialize)]
struct QueuesRepr {
    procs: Vec<ProcRepr>,
}

impl From<&Queues> for QueuesRepr {
    fn from(queues: &Queues) -> Self {
        QueuesRepr {
            procs: queues
                .0
                .procs
                .iter()
                .map(|proc| ProcRepr {
                    number: proc.number,
                    live: proc.live,
                    reductive: proc.reductive,
                    queued: proc.queued.clone(),
                    done: proc.done.clone(),
                    needed: proc.needed.clone(),
                    morphemes: proc.morphemes.clone(),
                    fixed_since: proc.fixed_since,
                })
                .collect(),
        }
    }
}

impl From<QueuesRepr> for Queues {
    fn from(repr: QueuesRepr) -> Self {
        let procs = repr
            .procs
            .into_iter()
            .map(|proc| Proc {
                number: proc.number,
                live: proc.live,
                reductive: proc.reductive,
                row: None,
                own_row: None,
                queued: proc.queued,
                done: proc.done,
                needed: proc.needed,
                morphemes: proc.morphemes,
                fixed_since: proc.fixed_since,
            })
            .collect();
        Queues(CodeState {
            procs,
            ..CodeState::default()
        })
    }
}

impl Serialize for Queues {
    fn serialize<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        QueuesRepr::from(self).serialize(serializer)
    }
}

impl<'de> Deserialize<'de> for Queues {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        Ok(QueuesRepr::deserialize(deserializer)?.into())
    }
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct SoundCodeState {
    /// Pořadí, ve kterém procesy kód zasáhly (chronologie změn tohoto kódu).
    pub order: Vec<ProcessId>,
    /// Fronty fonologizace živých procesů, přepsaná slova a uzavřené procesy.
    pub queues: Queues,
    /// Deník životního cyklu procesů: (proces, `true` = aktivace, `false` = uzavření).
    pub lifecycle_log: Vec<(ProcessId, bool)>,
    /// Kolik záznamů `PhonologyState::dominant_log` už je v paměti četností užití.
    /// Po obnově z disku je nula a paměť se doplní z celého deníku.
    #[serde(skip)]
    pub usage_cursor: usize,
    /// Verze četností pojmů, pro kterou platí paměť četností užití.
    #[serde(skip)]
    pub concept_version: u64,
}
