//! Repertoár: proměnné, varianty a jejich frekvence (zrcadlo `cee.v2.repertoire`).
//!
//! Jazyk kódu *je* jeho repertoár. Proměnné a varianty jsou sloupcové tabulky
//! ([`Variables`], [`Variants`]) indexované čísly z registru; textové ID jsou jen
//! v registru. **Rozdělení variant** ([`Distribution`]) drží varianty seřazené podle
//! *jména* (jako Python podle ID), aby shodu při hledání nejčastější varianty
//! rozhodovalo pořadí jmen, ne pořadí vzniku.

use std::collections::BTreeMap;
use std::sync::Arc;

use serde::{Deserialize, Serialize};

use crate::grammar::Construction;
use crate::ids::{ConceptId, GroupId, MorphemeId, Numbering, ProcessId, VariableId, VariantId};

/// Druh proměnné (předpona jejího ID).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub enum VariableKind {
    Process,
    Lexical,
    Form,
    Construction,
    Prosody,
}

impl VariableKind {
    pub fn name(self) -> &'static str {
        match self {
            VariableKind::Process => "process",
            VariableKind::Lexical => "lexical",
            VariableKind::Form => "form",
            VariableKind::Construction => "construction",
            VariableKind::Prosody => "prosody",
        }
    }

    pub fn parse(name: &str) -> Option<VariableKind> {
        Some(match name {
            "process" => VariableKind::Process,
            "lexical" => VariableKind::Lexical,
            "form" => VariableKind::Form,
            "construction" => VariableKind::Construction,
            "prosody" => VariableKind::Prosody,
            _ => return None,
        })
    }
}

/// ID proměnné: `druh:klíč`.
pub fn variable_name(kind: VariableKind, key: &str) -> String {
    format!("{}:{}", kind.name(), key)
}

/// Sloupce proměnných (místo, kde může existovat variace, např. slovo pro pojem WATER).
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct Variables {
    pub kind: Vec<VariableKind>,
    /// Klíč proměnné (pojem u lexikální, jméno pravidla u prozodie…); chladné pole.
    pub key: Vec<String>,
    /// Varianta pro skupinu, která proměnnou nikdy neslyšela (`NONE` = skupina ji nemá).
    pub default: Vec<VariantId>,
    /// U lexikální proměnné její pojem, jinak `NONE`.
    pub concept: Vec<ConceptId>,
    /// U procesní proměnné číslo procesu, jinak `NONE`.
    pub process: Vec<ProcessId>,
    /// Roste, když se uloží nebo přepíše lexikální proměnná (podle něj platí seznamy
    /// lexikálních proměnných kódů); neukládá se.
    #[serde(skip)]
    pub lexical_version: u64,
}

impl Variables {
    pub fn len(&self) -> usize {
        self.kind.len()
    }

    pub fn is_empty(&self) -> bool {
        self.kind.is_empty()
    }

    /// Uloží proměnnou pod číslem (nové číslo musí být právě další, nebo existující se přepíše).
    pub fn store(
        &mut self,
        id: VariableId,
        kind: VariableKind,
        key: &str,
        default: VariantId,
        concept: ConceptId,
    ) {
        let at = id.index();
        let was_lexical = self.kind.get(at) == Some(&VariableKind::Lexical);
        while self.kind.len() <= at {
            self.kind.push(VariableKind::Lexical);
            self.key.push(String::new());
            self.default.push(VariantId::NONE);
            self.concept.push(ConceptId::NONE);
            self.process.push(ProcessId::NONE);
        }
        if kind == VariableKind::Lexical || was_lexical {
            self.lexical_version += 1;
        }
        self.kind[at] = kind;
        self.key[at] = key.to_owned();
        self.default[at] = default;
        self.concept[at] = concept;
    }
}

/// Původ varianty; `change = None` znamená zděděnou z protojazyka.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Origin {
    pub change: Option<String>,
    pub tick: u32,
    pub year: f64,
    pub group: GroupId,
    pub parent: VariantId,
}

impl Origin {
    pub fn inherited(year: f64) -> Origin {
        Origin {
            change: None,
            tick: 0,
            year,
            group: GroupId::NONE,
            parent: VariantId::NONE,
        }
    }
}

/// Obsah varianty podle druhu proměnné.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub enum Payload {
    /// Slovo pro pojem: lexém, morfém, původ (`inherited`, `coinage`, …) a přitažlivost.
    Lexical {
        lexeme: String,
        morpheme: MorphemeId,
        origin: String,
        appeal: f64,
    },
    /// Změněná podoba procesu (hodnota procesní proměnné).
    Process { process: ProcessId, changed: bool },
    /// Konstrukce gramatické funkce.
    Construction(Construction),
    /// Pravidlo přízvuku (`initial`, `penult`, …).
    StressRule(String),
    /// Síla přízvuku (`weak`, `strong`).
    StressStrength(String),
    /// Ostatní obsah (formové změny, odvozeniny…), který si fáze popíše sama.
    Other(#[serde(with = "crate::json_string")] serde_json::Value),
}

/// Sloupce variant.
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct Variants {
    pub variable: Vec<VariableId>,
    /// Vznikla varianta změnou? (`origin.change` není `None`); horký sloupec pro sledování inovací.
    pub innovation: Vec<bool>,
    pub origin: Vec<Origin>,
    pub payload: Vec<Payload>,
}

impl Variants {
    pub fn len(&self) -> usize {
        self.variable.len()
    }

    pub fn is_empty(&self) -> bool {
        self.variable.is_empty()
    }

    pub fn store(&mut self, id: VariantId, variable: VariableId, payload: Payload, origin: Origin) {
        let at = id.index();
        while self.variable.len() <= at {
            self.variable.push(VariableId::NONE);
            self.innovation.push(false);
            self.origin.push(Origin::inherited(0.0));
            self.payload.push(Payload::Other(serde_json::Value::Null));
        }
        self.variable[at] = variable;
        self.innovation[at] = origin.change.is_some();
        self.origin[at] = origin;
        self.payload[at] = payload;
    }
}

/// Frekvence soutěžících variant jedné proměnné v jednom kódu.
///
/// Varianty jsou seřazené podle jména; `previous` je klouzavý stav zhruba o generaci
/// zpět, z něhož přenos počítá inkrementaci (Labov).
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Distribution {
    pub variants: Vec<VariantId>,
    pub freqs: Vec<f64>,
    pub previous: Vec<f64>,
}

impl Distribution {
    pub fn fixed(variant: VariantId) -> Distribution {
        Distribution {
            variants: vec![variant],
            freqs: vec![1.0],
            previous: vec![1.0],
        }
    }

    /// Rozdělení z (varianta, frekvence); varianty se seřadí podle jmen v `names`.
    pub fn from_pairs(mut pairs: Vec<(VariantId, f64)>, names: &Numbering) -> Distribution {
        pairs.sort_by(|a, b| names.name(a.0 .0).cmp(names.name(b.0 .0)));
        let freqs: Vec<f64> = pairs.iter().map(|p| p.1).collect();
        Distribution {
            variants: pairs.iter().map(|p| p.0).collect(),
            previous: freqs.clone(),
            freqs,
        }
    }

    pub fn is_fixed(&self) -> bool {
        self.variants.len() == 1
    }

    pub fn frequency(&self, variant: VariantId) -> f64 {
        self.variants
            .iter()
            .position(|&v| v == variant)
            .map_or(0.0, |i| self.freqs[i])
    }

    /// Nejčastější varianta; shodu rozhodne pořadí jmen (první maximum), ne náhoda.
    pub fn dominant(&self) -> (VariantId, f64) {
        let mut best = 0;
        for index in 1..self.freqs.len() {
            if self.freqs[index] > self.freqs[best] {
                best = index;
            }
        }
        (self.variants[best], self.freqs[best])
    }

    /// Nová varianta vstoupí s podílem `share`; ostatní se úměrně zmenší, bez trendu.
    pub fn with_innovation(
        &self,
        variant: VariantId,
        share: f64,
        names: &Numbering,
    ) -> Distribution {
        assert!(
            !self.variants.contains(&variant),
            "varianta už v rozdělení je"
        );
        let mut pairs: Vec<(VariantId, f64)> = self
            .variants
            .iter()
            .zip(&self.freqs)
            .map(|(&v, &f)| (v, f * (1.0 - share)))
            .collect();
        pairs.push((variant, share));
        Distribution::from_pairs(pairs, names)
    }
}

/// Mapa proměnná → rozdělení s copy-on-write vrstvami.
///
/// Skupiny z jednoho protojazyka sdílejí zmrazenou základní vrstvu (`Arc`)
/// a ukládají jen to, v čem se od ní liší. Pořadí průchodu je podle čísla proměnné;
/// kdo potřebuje pořadí jmen, použije [`Repertoire::variable_ids_by_name`].
#[derive(Clone, Debug, Default)]
pub struct Repertoire {
    base: Option<Arc<Repertoire>>,
    own: BTreeMap<VariableId, Distribution>,
}

// --- sdílené základy v kontrolním bodu ---------------------------------------------------
//
// V paměti skupiny jednoho protojazyka sdílejí základní vrstvu (`Arc`). Prostá serializace by
// ji zapsala u každé skupiny znovu (v Talveře 48 MB na bod) a po načtení by každá skupina měla
// vlastní kopii. Uvnitř `shared_bases` se základ zapíše jen poprvé, další výskyty jsou číslo
// a načtení je zase sdílí. Mimo `shared_bases` (JSON) je formát stejný jako dřív.

#[derive(Default)]
struct SharedBases {
    /// Zapsané základy: adresa → pořadí (číslují se po dokončení zápisu, i vnořené).
    seen: std::collections::HashMap<*const Repertoire, u32>,
    /// Načtené základy v pořadí čísel.
    loaded: Vec<Arc<Repertoire>>,
}

thread_local! {
    static SHARED: std::cell::RefCell<Option<SharedBases>> = const { std::cell::RefCell::new(None) };
}

/// Spustí `f` se sdílenými základy repertoárů (serializace i načtení kontrolního bodu).
pub fn shared_bases<R>(f: impl FnOnce() -> R) -> R {
    struct Reset(Option<SharedBases>);
    impl Drop for Reset {
        fn drop(&mut self) {
            let previous = self.0.take();
            SHARED.with(|cell| *cell.borrow_mut() = previous);
        }
    }
    let previous = SHARED.with(|cell| cell.borrow_mut().replace(SharedBases::default()));
    let _reset = Reset(previous);
    f()
}

fn sharing() -> bool {
    SHARED.with(|cell| cell.borrow().is_some())
}

#[derive(Serialize)]
struct PlainOut<'a> {
    base: Option<&'a Repertoire>,
    own: &'a BTreeMap<VariableId, Distribution>,
}

#[derive(Deserialize)]
struct PlainIn {
    base: Option<Repertoire>,
    own: BTreeMap<VariableId, Distribution>,
}

/// Nový základ: zapíše obsah a teprve potom si ho očísluje (stejně jako načtení).
struct NewBase<'a>(&'a Arc<Repertoire>);

impl Serialize for NewBase<'_> {
    fn serialize<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        let out = (**self.0).serialize(serializer)?;
        SHARED.with(|cell| {
            if let Some(shared) = cell.borrow_mut().as_mut() {
                let next = shared.seen.len() as u32;
                shared.seen.insert(Arc::as_ptr(self.0), next);
            }
        });
        Ok(out)
    }
}

#[derive(Serialize)]
enum BaseOut<'a> {
    New(NewBase<'a>),
    Seen(u32),
}

#[derive(Serialize)]
struct SharedOut<'a> {
    base: Option<BaseOut<'a>>,
    own: &'a BTreeMap<VariableId, Distribution>,
}

#[derive(Deserialize)]
enum BaseIn {
    New(Repertoire),
    Seen(u32),
}

#[derive(Deserialize)]
struct SharedIn {
    base: Option<BaseIn>,
    own: BTreeMap<VariableId, Distribution>,
}

impl Serialize for Repertoire {
    fn serialize<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        if !sharing() {
            return PlainOut {
                base: self.base.as_deref(),
                own: &self.own,
            }
            .serialize(serializer);
        }
        let base = self.base.as_ref().map(|base| {
            let seen = SHARED.with(|cell| {
                cell.borrow()
                    .as_ref()
                    .and_then(|shared| shared.seen.get(&Arc::as_ptr(base)).copied())
            });
            match seen {
                Some(index) => BaseOut::Seen(index),
                None => BaseOut::New(NewBase(base)),
            }
        });
        SharedOut {
            base,
            own: &self.own,
        }
        .serialize(serializer)
    }
}

impl<'de> Deserialize<'de> for Repertoire {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        if !sharing() {
            let plain = PlainIn::deserialize(deserializer)?;
            return Ok(Repertoire {
                base: plain.base.map(Arc::new),
                own: plain.own,
            });
        }
        let shared = SharedIn::deserialize(deserializer)?;
        let base = match shared.base {
            None => None,
            Some(BaseIn::New(repertoire)) => {
                let base = Arc::new(repertoire);
                SHARED.with(|cell| {
                    if let Some(shared) = cell.borrow_mut().as_mut() {
                        shared.loaded.push(base.clone());
                    }
                });
                Some(base)
            }
            Some(BaseIn::Seen(index)) => {
                let found = SHARED.with(|cell| {
                    cell.borrow()
                        .as_ref()
                        .and_then(|shared| shared.loaded.get(index as usize).cloned())
                });
                Some(found.ok_or_else(|| {
                    serde::de::Error::custom(format!("sdílený základ repertoáru č. {index} chybí"))
                })?)
            }
        };
        Ok(Repertoire {
            base,
            own: shared.own,
        })
    }
}

impl Repertoire {
    pub fn new() -> Repertoire {
        Repertoire::default()
    }

    /// Repertoár nad zmrazeným základem.
    pub fn over(base: Arc<Repertoire>) -> Repertoire {
        Repertoire {
            base: Some(base),
            own: BTreeMap::new(),
        }
    }

    pub fn get(&self, variable: VariableId) -> Option<&Distribution> {
        let mut layer = self;
        loop {
            if let Some(found) = layer.own.get(&variable) {
                return Some(found);
            }
            layer = layer.base.as_deref()?;
        }
    }

    pub fn set(&mut self, variable: VariableId, distribution: Distribution) {
        self.own.insert(variable, distribution);
    }

    /// Čísla proměnných, které repertoár má (vzestupně).
    pub fn variable_ids(&self) -> Vec<VariableId> {
        let mut ids = std::collections::BTreeSet::new();
        let mut layer = Some(self);
        while let Some(current) = layer {
            ids.extend(current.own.keys().copied());
            layer = current.base.as_deref();
        }
        ids.into_iter().collect()
    }

    /// Totéž v pořadí jmen proměnných (kanonické pořadí průchodu).
    pub fn variable_ids_by_name(&self, names: &Numbering) -> Vec<VariableId> {
        let mut ids = self.variable_ids();
        ids.sort_by(|a, b| names.name(a.0).cmp(names.name(b.0)));
        ids
    }

    /// Zmrazí repertoár jako sdílený základ.
    pub fn freeze(self) -> Arc<Repertoire> {
        Arc::new(self)
    }

    /// Nezávislý potomek: dnešní obsah se přesune do sdílené vrstvy a potomek nad ní pokračuje.
    pub fn branch(&mut self) -> Repertoire {
        let snapshot = Repertoire {
            base: self.base.take(),
            own: std::mem::take(&mut self.own),
        };
        let shared = Arc::new(snapshot);
        self.base = Some(shared.clone());
        Repertoire::over(shared)
    }
}
