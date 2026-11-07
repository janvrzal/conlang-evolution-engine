//! Stav zvukových změn a fonologie (R1b).
//!
//! **Svět:** index prostředí a opor zvukových změn (`cee_core::index::SoundIndex`),
//! sklony slov vůči procesům (`biases`), řádky procesů v bance tvarů, sloupce morfémů
//! pro jádro fronty a paměť čísel proměnných a změněných variant procesů. To všechno je
//! **odvozený stav** (`Runtime`): při kopii světa (kontrolní bod, větev) a po obnově
//! z disku se zahodí a postaví se znovu z toho, co svět nese (tvary kódů, slovní zásoba,
//! registr, procesy). Výsledek je tentýž, protože každá položka je čistá funkce stavu
//! světa (sklon slova je funkce semínka, procesu a lexému).
//!
//! **Kód:** fronty fonologizace živých procesů (`cee_core::code_state::CodeState`: fronta
//! čekajících slov podle potřebného logitu, přepsaná slova, kdy se proces ustálil),
//! pořadí procesů a deník aktivací a uzavření. Fronty se ukládají do kontrolního bodu;
//! paměť četností užití (`Usage`) se po obnově doplní z deníku dominantních kořenů
//! (`PhonologyState::dominant_log`).

use std::fmt;
use std::sync::RwLock;

use cee_core::code_state::{CodeState, Proc};
use cee_core::index::SoundIndex;
use serde::{Deserialize, Serialize};

use crate::ids::{ProcessId, VariableId, VariantId};

/// S jakým stavem kódu je skupina v indexu dorovnána: verze fonologie, verze tvarů,
/// délka deníku slovní zásoby a pravidlo přízvuku. Počet morfémů světa v něm není: nový morfém
/// se do slovní zásoby skupiny dostane zápisem do deníku, který razítko už obsahuje.
pub type Stamp = (u64, u64, usize, u8);

/// Stav indexu prostředí a opor, který smí číst souběžně víc vláken (za zámkem pro čtení;
/// dorovnání skupiny bere zámek pro zápis).
///
/// Míry inovací se počítají přes skupiny souběžně a každá skupina si index dorovná sama
/// (`phonology::index`); skupiny jsou nezávislé a výsledek nezáleží na pořadí zpracování,
/// protože opory jsou celá čísla.
#[derive(Default)]
pub struct IndexState {
    pub index: Option<SoundIndex>,
    /// Pro každou skupinu (podle čísla): s jakým stavem kódu je v indexu dorovnána.
    pub synced: Vec<Option<Stamp>>,
}

/// Sloupce morfémů ve tvaru, který čeká jádro fronty (`i32`, −1 = žádný).
#[derive(Default)]
pub struct Columns {
    /// Počet morfémů, počet obsazených čísel a počet paradigmat, pro které platí.
    pub stamp: (usize, usize, usize),
    /// Váha buňky paradigmatu tvaru slova, NaN = morfém váhu nemá.
    pub weight: Vec<f64>,
    /// Lexém morfému (u kořene a koncovky on sám, u neobsazeného čísla −1).
    pub lexeme: Vec<i32>,
    pub default_form: Vec<i32>,
    pub default_cut: Vec<i32>,
    pub default_exponent: Vec<i32>,
}

/// Odvozený stav světa, který se při kopii zahazuje.
#[derive(Default)]
pub struct Runtime {
    pub index: RwLock<IndexState>,
    /// Sklon slov vůči změně: `biases[proces][lexém]`, `NaN` = ještě nelosováno.
    pub biases: Vec<Vec<f64>>,
    /// Řádek procesu v bance tvarů podle čísla procesu (−1 = neregistrován).
    pub rows: Vec<i32>,
    /// Číslo procesu podle řádku v bance.
    pub row_process: Vec<ProcessId>,
    /// Proměnná a změněná varianta podle čísla procesu (`NONE`, dokud se nenajde).
    pub info: Vec<(VariableId, VariantId)>,
    pub columns: Columns,
    /// Četnost každého pojmu (podle čísla pojmu) pro četnosti užití.
    pub concept: Vec<f64>,
    /// Verze četností pojmů a počet pojmů, pro které platí `concept`.
    pub concept_stamp: (u64, usize),
    /// Roste, kdykoli se změní vstup četností užití (pojmy, váhy buněk); kód podle něj
    /// zahodí paměť četností. Začíná od nuly, kód od nuly „nikdy nesrovnáno“.
    pub epoch: u64,
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
///
/// `cursor` je počet záznamů `PhonologyState::dominant_log`, které už jsou v paměti
/// četností užití (`state.usage`); `epoch` je verze vstupů četností, pro kterou paměť
/// platí (`Runtime::epoch`). Kopie nese paměť, ale `epoch` nuluje, takže ji kód při
/// prvním použití zkontroluje; uložený a obnovený kód začíná prázdnou pamětí.
#[derive(Debug, Default)]
pub struct Queues {
    pub state: CodeState,
    pub cursor: usize,
    pub epoch: u64,
}

impl Clone for Queues {
    fn clone(&self) -> Self {
        Queues {
            state: self.state.clone(),
            cursor: self.cursor,
            epoch: 0,
        }
    }
}

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
                .state
                .procs
                .iter()
                .map(|proc| ProcRepr {
                    number: proc.number,
                    live: proc.live,
                    reductive: proc.reductive,
                    queued: proc.queued.to_bytes(),
                    done: proc.done.to_bytes(),
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
                queued: cee_core::flags::Flags::from_bytes(&proc.queued),
                done: cee_core::flags::Flags::from_bytes(&proc.done),
                needed: proc.needed,
                morphemes: proc.morphemes,
                fixed_since: proc.fixed_since,
            })
            .collect();
        Queues {
            state: CodeState {
                procs,
                ..CodeState::default()
            },
            cursor: 0,
            epoch: 0,
        }
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
}
