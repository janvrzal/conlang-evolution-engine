//! Společnost: státy, normy, hranice, obchod, pozadí dějin, sledování linií (R1d).
//!
//! Zrcadlo polí `World` z Pythonu, která patří událostem, politice, kontaktu
//! a pozorování: `states`, `standards`, `border_factors`, `base_prestige`,
//! `prestige_mirror`, `trade`, `edit_log`, `endonyms` a `LineageTracker`.
//!
//! Všechno je ve sloupcích a mapách podle čísel (`GroupId`, `TerritoryId`); jen stát
//! a spisovná norma se jmenují podle textového ID (stát je vzácný a jméno zadává autor).

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

use crate::edits::Edit;
use crate::ids::{ConceptId, GroupId, LanguageId, TerritoryId};
use crate::observe::LineageTracker;

/// Stát ve světě (`polity.Polity`): území, sídlo a jazyková politika.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Polity {
    pub id: String,
    /// Jméno státu pro autora a export; na dynamiku nemá vliv.
    pub name: Option<String>,
    pub regions: Vec<TerritoryId>,
    pub capital: TerritoryId,
    /// Skupina, jejíž řeč je úředním jazykem (největší vesnice hlavního města).
    pub seat: GroupId,
    pub language: LanguageId,
    pub centralization: String,
    pub policy: String,
    pub border: String,
    /// Vazby vesnic k sídlu, které stát vytvořil (centralizace): skupina → síla.
    pub links: BTreeMap<GroupId, f64>,
}

/// Co se zapisuje do deníku změn světa.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
pub enum JournalMode {
    /// Nic (deník nemá vliv na dynamiku, jen na paměť).
    Off,
    /// Všechny změny událostí, států a pozadí dějin a ve fázi komunit jen změny struktury
    /// (vznik a zánik skupin, vazby, obchod, hranice, prestiž, předávání jazyka).
    /// Běžné každokrokové úpravy populace, podílu L2 a přistěhovalců se nezapisují.
    #[default]
    Structure,
    /// Úplný deník jako v Pythonu (i každokrokové úpravy komunit).
    All,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct SocietyState {
    /// Státy světa podle ID (seřazené podle ID jako `sorted(world.states.values())`).
    pub states: BTreeMap<String, Polity>,
    /// Spisovné jazyky států a regionů: ID státu či regionu → psaný kód (skupina).
    pub standards: BTreeMap<String, GroupId>,
    /// Pojmy, ze kterých se skládá vlastní jméno jazyka (jen pro export).
    pub endonyms: BTreeMap<LanguageId, Vec<ConceptId>>,
    /// Uzamčená vlastní jména prajazyků (IPA), jen pro modul jmen.
    #[serde(default)]
    pub endonym_forms: BTreeMap<LanguageId, String>,
    /// Zadané tradice osobních jmen prajazyků (paradigma katalogu), jen pro modul jmen.
    #[serde(default)]
    pub person_traditions: BTreeMap<LanguageId, String>,
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
    /// Co se zapisuje do deníku (viz [`JournalMode`]).
    pub journal: JournalMode,
    /// Deník změn světa (na dynamiku nemá vliv).
    pub edit_log: Vec<Edit>,
    /// Linie jazyků z posledního pozorování (párování shluků mezi snímky).
    pub lineages: LineageTracker,
}
