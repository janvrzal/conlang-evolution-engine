//! Jména jako slova s vlastní historií (dok. 34, návrh `docs/scenare/generovani-jmen.md`).
//!
//! Jméno jazyka a lidí, místa nebo státu **vznikne jednou**, v určitém roce a komunitě, jako
//! hotový tvar složený z tehdejších slov ([`compose`]). Potom žije samo: prochází hláskovými
//! změnami řeči svého nositele (skupiny, jejíž výslovnost sleduje) a ustrne. Když se později
//! změní nebo nahradí obecné slovo, jméno se nemění.
//!
//! Každý záznam ([`NameRecord`]) je buď **endonymum** (jméno, které objekt užívá sám pro sebe),
//! nebo **exonymum** (jméno v řeči sousedů). Exonymum vzniká přejetím tehdejšího tvaru do
//! řeči sousední linie (adaptace na její hlásky, `contact::adapt`) a od té chvíle se vyvíjí
//! v ní. Exonymum se může stát endonymem: po přechodu jazyka (lidé, kteří přejdou na jazyk
//! sousedů, převezmou jejich jméno pro sebe) nebo z prestiže státu (vládnoucí jazyk státu
//! dlouho jmenuje poddané po svém). Nová linie po rozštěpení jméno zdědí, nebo se pojmenuje po
//! kraji, státu, dřívějším národě (substrát) či zakladateli (eponymum). Místo po přechodu
//! obyvatel na jiný jazyk staré jméno převezme (substrátové jméno), nebo dostane nové.
//!
//! Modul jen **čte** svět: nic nezapisuje do `World` ani do historie, takže dynamika i otisk
//! běhu jsou s jmény i bez nich stejné. Hláskové změny čte z kódu nositele: proces, který
//! v kódu převládne (podíl změny ≥ 0,5, stejný práh jako povrchový tvar slov), se zapíše do
//! deníku skupiny ([`SoundLog`]) a jména, která skupina nese, jím projdou v tomto pořadí.
//! Stejné semínko a stejné podklady dávají stejná jména (volby z `rng::stable_int`).

pub mod compose;
pub mod generate;
pub mod persons;

use std::collections::{BTreeMap, BTreeSet};

use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};

use crate::ids::{GroupId, LanguageId, ProcessId, TerritoryId};
use crate::model::group::Domain;
use crate::model::territory::TerritoryLevel;
use crate::onomastics::{romanize, smooth_compound};
use crate::phonology::surface::{apply_local, info_pure, ProcCache};
use crate::world::World;

use compose::{Adapted, Composed, Lexicon, Live, PlaceConditions, RecipePart};
use persons::PersonName;

/// Proces převládne v kódu, když ho má aspoň tento podíl mluvčích (jako povrchový tvar).
pub const PREVAIL: f64 = 0.5;
/// Pravděpodobnost, že noví obyvatelé převezmou staré jméno místa (místo nového).
pub const KEEP_SUBSTRATE_PLACE: f64 = 0.75;
/// Kolik let musí stát trvat, než jeho úřední jazyk může vnutit poddaným své jméno.
pub const PRESTIGE_YEARS: f64 = 200.0;
/// Podíl skupin linie, které musí ležet ve státě, aby jméno státu nebo jeho jazyka působilo.
pub const STATE_MAJORITY: f64 = 0.6;
/// Pravděpodobnost, že linie převezme exonymum vládnoucího jazyka (jednou za dvojici linie–stát).
pub const PRESTIGE_ADOPTION: f64 = 0.3;
/// Nejslabší vazba mezi skupinami dvou linií, při které sousedé linii pojmenují.
pub const CONTACT_STRENGTH: f64 = 0.05;

/// Druhy záznamů historie, které modul jmen čte.
pub const EVENT_KINDS: [&str; 4] = [
    "language_emerged",
    "language_split",
    "language_ended",
    "migration",
];

/// Endonymum, nebo exonymum.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum Role {
    Endonym,
    Exonym,
}

impl Role {
    pub fn name(self) -> &'static str {
        match self {
            Role::Endonym => "endonym",
            Role::Exonym => "exonym",
        }
    }
}

/// Jedna podoba jména v čase: rok, výslovnost a příčina změny.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct FormStep {
    pub year: f64,
    pub ipa: String,
    /// `founded`, `inherited`, `borrowed`, nebo popis hláskové změny (`sound: a → e /…`).
    pub cause: String,
}

/// Zdroj přejatého jména: jiný záznam a jeho tvar v okamžiku přejetí.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct SourceRef {
    pub record: String,
    pub ipa: String,
    pub language: String,
}

/// Jméno s vlastní historií.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct NameRecord {
    pub id: String,
    /// Pojmenovaný objekt: `language:<id>`, `lineage:<id>`, `territory:<id>`, `state:<id>`.
    pub object: String,
    pub role: Role,
    /// Jazyk (kód) uživatelů jména.
    pub language: String,
    /// Linie uživatelů, když je známá z pozorování.
    pub lineage: Option<String>,
    /// Skupina, jejíž výslovnost jméno sleduje.
    pub carrier: String,
    pub founded_tick: u32,
    pub founded_year: f64,
    /// Jak jméno vzniklo: vzor místa, `compound`, `inherited`, `borrowed`, `substrate`,
    /// `place`, `state`, `eponym`, `predecessor`, `exonym_adopted`, `authored`.
    pub motivation: String,
    /// Událost nebo podmínka, která vznik spustila (`split`, `language_shift`, `state_prestige`…).
    pub cause: Option<String>,
    /// Tradice pojmenování v roce vzniku (`archaic`, `state`, `literate`), u míst.
    pub tradition: Option<String>,
    /// Význam pro čtenáře (česky).
    pub meaning: String,
    pub recipe: Vec<RecipePart>,
    pub source: Option<SourceRef>,
    /// Dnešní tvar.
    pub form: Vec<i32>,
    /// Procesy, kterými jméno už prošlo (čísla procesů).
    pub applied: BTreeSet<u32>,
    /// Kolik záznamů deníku nositele už jméno přečetlo.
    pub cursor: usize,
    pub timeline: Vec<FormStep>,
    /// Rok, kdy jméno přestalo být v užívání (objekt zanikl nebo dostal jiné jméno).
    pub ended: Option<f64>,
    /// Celé jméno osoby v latince (u osob; `form` je rodné jméno).
    #[serde(default)]
    pub full_name: Option<String>,
}

/// Krok v historii tradice osobních jmen komunity.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct TraditionStep {
    pub year: f64,
    /// Paradigma katalogu (`dithematic_ie`, `house_surety`…).
    pub paradigm: String,
    /// `authored`, `initial`, `inherited`, `liturgy`, `state_standard`, `state_prestige`.
    pub cause: String,
    /// Komunita nebo instituce, od které tradice přišla.
    pub source: Option<String>,
}

impl NameRecord {
    /// Tvar (IPA) platný v daném roce.
    pub fn ipa_at(&self, year: f64) -> Option<&str> {
        self.timeline
            .iter()
            .take_while(|step| step.year <= year + 1e-9)
            .last()
            .map(|step| step.ipa.as_str())
    }
}

/// Deník hláskových změn kódu skupiny: (tik, proces) v pořadí, v jakém v kódu převládly.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct SoundLog {
    pub entries: Vec<(u32, u32)>,
    pub seen: BTreeSet<u32>,
    /// Jazyk kódu při posledním zápisu.
    pub language: String,
}

/// Stav státu z pohledu jmen.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct StateSeen {
    pub founded: f64,
    pub ended: Option<f64>,
    pub regions: Vec<String>,
}

/// Dobový snímek jedné linie: nositel, slova pro jména a hlásky.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct EpochLineage {
    pub carrier: String,
    pub language: String,
    /// Pravidlo přízvuku kódu (`cee_core::process::RULE_*`).
    pub rule: u8,
    pub head_initial: bool,
    pub inventory: Vec<i32>,
    pub forms: BTreeMap<String, Vec<i32>>,
}

/// Dobový snímek kraje: převládající linie a podmínky pojmenování.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct EpochRegion {
    pub lineage: Option<String>,
    pub state: Option<String>,
    /// Linie úředního jazyka státu (řeč sídla).
    pub ruling: Option<String>,
    pub literate: bool,
    pub urban: bool,
    pub terrain: String,
}

/// Snímek při pozorování (pro generátor jmen podle epochy).
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct Epoch {
    pub tick: u32,
    pub year: f64,
    pub lineages: BTreeMap<String, EpochLineage>,
    pub regions: BTreeMap<String, EpochRegion>,
}

/// Všechna jména běhu a podklady pro jejich vývoj.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct NameState {
    pub records: Vec<NameRecord>,
    /// Objekt → současné endonymum (index záznamu).
    pub current: BTreeMap<String, usize>,
    /// `objekt|linie` → exonymum té linie.
    pub exonyms: BTreeMap<String, usize>,
    /// Skupina → deník hláskových změn.
    pub logs: BTreeMap<String, SoundLog>,
    pub epochs: Vec<Epoch>,
    pub territories_seen: usize,
    pub states: BTreeMap<String, StateSeen>,
    /// Skupina → jazyk a linie při posledním pozorování.
    pub group_language: BTreeMap<String, String>,
    pub group_lineage: BTreeMap<String, String>,
    /// Jednorázová rozhodnutí, která už padla.
    pub decided: BTreeSet<String>,
    /// Romanizovaná jména míst v užívání (aby dvě místa nedostala totéž jméno).
    pub used: BTreeSet<String>,
    /// Rok začátku běhu a délka kroku (převod tiků deníku na roky).
    pub start_year: f64,
    pub dt: f64,
    /// Komunita (`language:…`, `lineage:…`) → historie tradice osobních jmen.
    pub traditions: BTreeMap<String, Vec<TraditionStep>>,
}

/// Objekt linie: ID linie už má tvar `lineage:…` (`observe::LineageTracker`).
pub fn lineage_object(lineage: &str) -> String {
    if lineage.starts_with("lineage:") {
        lineage.to_owned()
    } else {
        format!("lineage:{lineage}")
    }
}

fn exonym_key(object: &str, lineage: &str) -> String {
    format!("{object}|{lineage}")
}

/// Domácí mluvené skupiny (ne psaný kód, ne veřejná doména).
fn home_groups(world: &World) -> Vec<GroupId> {
    world
        .group_ids()
        .into_iter()
        .filter(|&g| {
            !world.groups.written[g.index()] && world.groups.domain[g.index()] == Domain::Home
        })
        .collect()
}

fn language_name(world: &World, group: GroupId) -> String {
    let language = world.groups.main_code(group).language;
    world.registry.languages.name(language.0).to_owned()
}

fn group_named(world: &World, name: &str) -> Option<GroupId> {
    world
        .registry
        .groups
        .get(name)
        .map(GroupId)
        .filter(|&g| world.groups.contains(g))
}

fn region_of(world: &World, territory: TerritoryId) -> Option<TerritoryId> {
    let mut at = territory;
    while !at.is_none() {
        let node = &world.territories[at.index()];
        if node.level == TerritoryLevel::Region {
            return Some(at);
        }
        at = node.parent;
    }
    None
}

/// Hlavní skupina území: u sídla největší domácí skupina, u kraje největší domácí skupina
/// kraje bez přenesené L1 (jako sídlo státu, `polity::seat_of`).
fn main_groups(world: &World) -> BTreeMap<TerritoryId, GroupId> {
    let mut best: BTreeMap<TerritoryId, (bool, u32, GroupId)> = BTreeMap::new();
    let mut consider = |territory: TerritoryId, group: GroupId, transplanted: bool| {
        let population = world.groups.population[group.index()];
        let better = match best.get(&territory) {
            None => true,
            Some(&(t, p, g)) => {
                (
                    transplanted,
                    std::cmp::Reverse(population),
                    world.group_name(group),
                ) < (t, std::cmp::Reverse(p), world.group_name(g))
            }
        };
        if better {
            best.insert(territory, (transplanted, population, group));
        }
    };
    for group in home_groups(world) {
        let territory = world.groups.territory[group.index()];
        if territory.is_none() {
            continue;
        }
        let transplanted = !world.groups.main_code(group).l1_source.is_none();
        consider(territory, group, false);
        if let Some(region) = region_of(world, territory) {
            if region != territory {
                consider(region, group, transplanted);
            }
        }
    }
    best.into_iter().map(|(t, (_, _, g))| (t, g)).collect()
}

impl NameState {
    /// Založí jména na začátku běhu: prajazyky, území a státy, které už existují.
    pub fn new(world: &World, dt: f64) -> NameState {
        let mut state = NameState {
            start_year: world.start_year,
            dt,
            ..NameState::default()
        };
        if world.table.is_none() {
            return state;
        }
        state.update_logs(world, 0);
        state.found_languages(world);
        state.found_territories(world, &[], 0, world.start_year);
        state.found_states(world, &[], 0, world.start_year);
        for group in home_groups(world) {
            state.group_language.insert(
                world.group_name(group).to_owned(),
                language_name(world, group),
            );
        }
        state
    }

    fn render(world: &World, form: &[i32]) -> String {
        world
            .table
            .as_ref()
            .map_or_else(String::new, |t| t.render(form))
    }

    #[allow(clippy::too_many_arguments)]
    fn push(
        &mut self,
        world: &World,
        object: String,
        role: Role,
        carrier: GroupId,
        lineage: Option<String>,
        tick: u32,
        year: f64,
        motivation: &str,
        cause: Option<String>,
        composed: Composed,
        source: Option<SourceRef>,
    ) -> usize {
        let index = self.records.len();
        let carrier_name = world.group_name(carrier).to_owned();
        let log = self.logs.get(&carrier_name);
        let applied = log.map(|l| l.seen.clone()).unwrap_or_default();
        let cursor = log.map_or(0, |l| l.entries.len());
        let ipa = Self::render(world, &composed.form);
        let first = if source.is_some() && motivation != "inherited" {
            "borrowed"
        } else if motivation == "inherited" {
            "inherited"
        } else {
            "founded"
        };
        let tradition = (object.starts_with("territory:") && role == Role::Endonym)
            .then(|| cause.clone())
            .flatten()
            .filter(|c| matches!(c.as_str(), "archaic" | "state" | "literate"));
        self.records.push(NameRecord {
            id: format!("nm{index:05}"),
            object,
            role,
            language: language_name(world, carrier),
            lineage,
            carrier: carrier_name,
            founded_tick: tick,
            founded_year: year,
            motivation: motivation.to_owned(),
            cause: if tradition.is_some() { None } else { cause },
            tradition,
            meaning: composed.meaning,
            recipe: composed.recipe,
            source,
            form: composed.form,
            applied,
            cursor,
            timeline: vec![FormStep {
                year,
                ipa,
                cause: first.into(),
            }],
            ended: None,
            full_name: None,
        });
        index
    }

    /// Zapíše procesy, které v kódech domácích skupin nově převládly.
    fn update_logs(&mut self, world: &World, tick: u32) {
        for group in home_groups(world) {
            let name = world.group_name(group);
            let log = self.logs.entry(name.to_owned()).or_default();
            log.language = language_name(world, group);
            for &process in &world.groups.main_code(group).phonology.sound.order {
                if log.seen.contains(&process.0) {
                    continue;
                }
                let Some((variable, changed)) = info_pure(world, process) else {
                    continue;
                };
                let share = crate::phonology::rows::changed_share(world, group, variable, changed);
                if share >= PREVAIL {
                    log.seen.insert(process.0);
                    log.entries.push((tick, process.0));
                }
            }
        }
    }

    /// Jméno projde procesy, které v kódu nositele převládly od posledního čtení.
    fn advance(&mut self, world: &World, index: usize, year: f64, cache: &mut ProcCache) {
        let record = &mut self.records[index];
        if record.ended.is_some() {
            return;
        }
        let Some(log) = self.logs.get(&record.carrier) else {
            return;
        };
        let Some(group) = group_named(world, &record.carrier) else {
            return;
        };
        let rule = world.groups.main_code(group).stress_rule.as_rule();
        while record.cursor < log.entries.len() {
            let process = log.entries[record.cursor].1;
            record.cursor += 1;
            if !record.applied.insert(process) {
                continue;
            }
            let Some(changed) = apply_local(world, cache, ProcessId(process), &record.form, rule)
            else {
                continue;
            };
            if changed.is_empty() || changed == record.form {
                continue;
            }
            record.form = changed;
            let label = world
                .process(ProcessId(process))
                .map_or_else(String::new, |d| d.label.clone());
            record.timeline.push(FormStep {
                year,
                ipa: Self::render(world, &record.form),
                cause: format!("sound: {label}"),
            });
        }
    }

    /// Nositel jména se mění: jméno dál sleduje řeč jiné skupiny téhož jazyka.
    fn set_carrier(&mut self, world: &World, index: usize, group: GroupId) {
        let name = world.group_name(group);
        let record = &mut self.records[index];
        if record.carrier != name {
            record.carrier = name.to_owned();
            record.cursor = 0;
        }
    }

    fn end(&mut self, index: usize, year: f64) {
        let record = &mut self.records[index];
        if record.ended.is_none() {
            record.ended = Some(year);
            if record.role == Role::Endonym && record.object.starts_with("territory:") {
                let name = romanize(
                    &record
                        .timeline
                        .last()
                        .map_or("", |s| s.ipa.as_str())
                        .to_owned(),
                );
                self.used.remove(&name);
            }
        }
    }

    /// Jméno, jak ho dnes vyslovují jeho uživatelé (IPA).
    pub fn ipa(&self, index: usize) -> &str {
        self.records[index]
            .timeline
            .last()
            .map_or("", |s| s.ipa.as_str())
    }

    /// Současné endonymum objektu.
    pub fn current_of(&self, object: &str) -> Option<&NameRecord> {
        self.current.get(object).map(|&i| &self.records[i])
    }

    /// Endonymum linie jazyka (IPA), pokud ho modul zná.
    pub fn lineage_endonym(&self, lineage: &str) -> Option<String> {
        self.current
            .get(&lineage_object(lineage))
            .map(|&i| self.ipa(i).to_owned())
    }

    /// Tvar jiného jména přejatý do řeči skupiny (adaptace na její hlásky).
    fn borrow_form(
        world: &World,
        form: &[i32],
        group: GroupId,
        inventory: Option<&[i32]>,
    ) -> Vec<i32> {
        let owned;
        let native = match inventory {
            Some(found) => found,
            None => {
                owned = crate::contact::inventory(world, group);
                &owned
            }
        };
        if native.is_empty() {
            form.to_vec()
        } else {
            crate::contact::adapt(world, native, form)
        }
    }

    // --- osoby a tradice ------------------------------------------------------------------

    /// Komunita skupiny pro tradici osobních jmen: její linie z posledního pozorování, jinak jazyk.
    fn community_of(&self, world: &World, group: GroupId) -> String {
        self.group_lineage
            .get(world.group_name(group))
            .map(|l| lineage_object(l))
            .filter(|l| self.traditions.contains_key(l))
            .unwrap_or_else(|| format!("language:{}", language_name(world, group)))
    }

    /// Současná tradice osobních jmen komunity.
    pub fn tradition_of(&self, community: &str) -> String {
        self.traditions
            .get(community)
            .and_then(|steps| steps.last())
            .map_or_else(|| "dithematic_ie".to_owned(), |s| s.paradigm.clone())
    }

    /// Tradice komunity platná v roce `year`.
    pub fn tradition_at(&self, community: &str, year: f64) -> Option<&TraditionStep> {
        let steps = self.traditions.get(community)?;
        steps
            .iter()
            .take_while(|s| s.year <= year + 1e-9)
            .last()
            .or_else(|| steps.first())
    }

    fn adopt_tradition(
        &mut self,
        community: &str,
        year: f64,
        paradigm: &str,
        cause: &str,
        source: Option<String>,
    ) {
        let steps = self.traditions.entry(community.to_owned()).or_default();
        if steps.last().is_some_and(|s| s.paradigm == paradigm) {
            return;
        }
        steps.push(TraditionStep {
            year,
            paradigm: paradigm.to_owned(),
            cause: cause.to_owned(),
            source,
        });
    }

    /// Prestižní řeč skupiny pro jména, která ji užívají: liturgie, spisovná norma, nebo sídlo státu.
    fn prestige_group(world: &World, group: GroupId) -> Option<GroupId> {
        let at = group.index();
        if !world.groups.liturgy[at].is_none() {
            return Some(world.groups.liturgy[at]);
        }
        if !world.groups.standard[at].is_none() {
            return Some(world.groups.standard[at]);
        }
        let region = region_of(world, world.groups.territory[at])?;
        world
            .society
            .states
            .values()
            .find(|p| p.regions.contains(&region))
            .map(|p| p.seat)
            .filter(|&s| world.groups.contains(s) && s != group)
    }

    /// Jméno osoby podle tradice komunity `community`, z dnešních slov skupiny.
    fn person(
        &self,
        world: &World,
        group: GroupId,
        community: &str,
        key: &str,
        tick: u32,
    ) -> Option<PersonName> {
        let table = world.table.as_ref()?;
        let is_vowel = |s: i32| table.is_vowel(s);
        let render = |f: &[i32]| table.render(f);
        let paradigm = self.tradition_of(community);
        let lexicon = Live { world, group };
        let donor = Self::prestige_group(world, group).map(|g| Live { world, group: g });
        let adapted = donor.as_ref().map(|d| Adapted {
            inner: d,
            world,
            inventory: crate::contact::inventory(world, group),
        });
        let origin = region_of(world, world.groups.territory[group.index()])
            .and_then(|r| {
                self.current.get(&format!(
                    "territory:{}",
                    world.registry.territories.name(r.0)
                ))
            })
            .map(|&i| romanize(self.ipa(i)));
        let h = compose::hash(world.seed, &["person", key, &tick.to_string()], 0);
        let name = persons::person_name(
            &paradigm,
            &lexicon,
            adapted.as_ref().map(|a| a as &dyn Lexicon),
            origin.as_deref(),
            h,
            &is_vowel,
            &render,
        );
        (!name.given().is_empty()).then_some(name)
    }

    /// Zapíše osobu (`person:<klíč>`, rodné jméno) a její rod (`house:<klíč>`), má-li ho tradice.
    #[allow(clippy::too_many_arguments)]
    fn push_person(
        &mut self,
        world: &World,
        group: GroupId,
        key: &str,
        name: &PersonName,
        tick: u32,
        year: f64,
        cause: &str,
    ) -> (usize, Option<usize>) {
        let render = |f: &[i32]| {
            world
                .table
                .as_ref()
                .map_or_else(String::new, |t| t.render(f))
        };
        let full = name.full(&render);
        let lineage = self.group_lineage.get(world.group_name(group)).cloned();
        let person = self.push(
            world,
            format!("person:{key}"),
            Role::Endonym,
            group,
            lineage.clone(),
            tick,
            year,
            &name.paradigm,
            Some(cause.to_owned()),
            Composed {
                form: name.given().to_vec(),
                pattern: name.paradigm.clone(),
                meaning: name.meaning.clone(),
                recipe: name.recipe.clone(),
            },
            None,
        );
        self.records[person].full_name = Some(full.clone());
        let house = name.house().filter(|h| !h.is_empty()).map(|form| {
            let index = self.push(
                world,
                format!("house:{key}"),
                Role::Endonym,
                group,
                lineage,
                tick,
                year,
                "house",
                Some(cause.to_owned()),
                Composed {
                    form: form.to_vec(),
                    pattern: "house".into(),
                    meaning: format!("rod osoby {full}"),
                    recipe: Vec::new(),
                },
                None,
            );
            self.current.insert(format!("house:{key}"), index);
            index
        });
        self.current.insert(format!("person:{key}"), person);
        (person, house)
    }

    /// Tradice osobních jmen se přenáší institucemi a prestiží státu (jednou za dvojici).
    fn follow_traditions(
        &mut self,
        world: &World,
        lineages: &BTreeMap<String, Vec<String>>,
        year: f64,
    ) {
        for (lineage, groups) in lineages {
            let object = lineage_object(lineage);
            if !self.traditions.contains_key(&object) {
                continue;
            }
            let alive: Vec<GroupId> = groups
                .iter()
                .filter_map(|g| group_named(world, g))
                .collect();
            if alive.is_empty() {
                continue;
            }
            // Liturgie: většina skupin má liturgický jazyk → kalendářní jména.
            let liturgy = alive
                .iter()
                .filter(|g| !world.groups.liturgy[g.index()].is_none())
                .count();
            if 2 * liturgy > alive.len()
                && self.decided.insert(format!("tradition|liturgy|{lineage}"))
            {
                let source = alive
                    .iter()
                    .map(|g| world.groups.liturgy[g.index()])
                    .find(|l| !l.is_none())
                    .map(|l| world.group_name(l).to_owned());
                self.adopt_tradition(&object, year, "liturgical_vernacular", "liturgy", source);
                continue;
            }
            let Some((state, _)) = self.majority_state(world, groups) else {
                continue;
            };
            let Some(founded) = self.states.get(&state).map(|s| s.founded) else {
                continue;
            };
            let seat = world.society.states[&state].seat;
            let Some(ruling) = self.group_lineage.get(world.group_name(seat)).cloned() else {
                continue;
            };
            if ruling == *lineage {
                continue;
            }
            // Spisovná norma státu v cizím jazyce, která skupiny skutečně zasáhla (většina má
            // spisovný kód a školu) → dvorská jména vedle domácích.
            let reached = alive
                .iter()
                .filter(|g| {
                    !world.groups.standard[g.index()].is_none()
                        && world.groups.schooling[g.index()] > 0.2
                })
                .count();
            let settled = self
                .traditions
                .get(&object)
                .and_then(|steps| steps.last())
                .is_none_or(|s| year - s.year >= 150.0);
            if world.society.standards.contains_key(&state)
                && 2 * reached > alive.len()
                && year - founded >= 50.0
                && self
                    .decided
                    .insert(format!("tradition|court|{lineage}|{state}"))
            {
                let h = compose::hash(world.seed, &["tradition", "court", lineage, &state], 0);
                if (h % 10_000) as f64 / 10_000.0 < 0.35 {
                    self.adopt_tradition(
                        &object,
                        year,
                        "polyglossic_court",
                        "state_standard",
                        Some(lineage_object(&ruling)),
                    );
                    continue;
                }
            }
            // Dlouhá vláda cizího jazyka → převzetí jeho tradice.
            if settled
                && year - founded >= 150.0
                && self
                    .decided
                    .insert(format!("tradition|prestige|{lineage}|{state}"))
            {
                let theirs = self.tradition_of(&lineage_object(&ruling));
                let h = compose::hash(world.seed, &["tradition", "prestige", lineage, &state], 0);
                if theirs != self.tradition_of(&object) && (h % 10_000) as f64 / 10_000.0 < 0.3 {
                    self.adopt_tradition(
                        &object,
                        year,
                        &theirs,
                        "state_prestige",
                        Some(lineage_object(&ruling)),
                    );
                }
            }
        }
    }

    // --- jazyky ----------------------------------------------------------------------------

    /// Vlastní jména prajazyků: složenina slov receptu, nebo tvar zadaný autorem.
    fn found_languages(&mut self, world: &World) {
        let Some(table) = world.table.clone() else {
            return;
        };
        let is_vowel = |s: i32| table.is_vowel(s);
        let render = |f: &[i32]| table.render(f);
        let mut representatives: BTreeMap<String, GroupId> = BTreeMap::new();
        for group in home_groups(world) {
            let language = language_name(world, group);
            let better = representatives.get(&language).is_none_or(|&b| {
                (
                    std::cmp::Reverse(world.groups.population[group.index()]),
                    world.group_name(group),
                ) < (
                    std::cmp::Reverse(world.groups.population[b.index()]),
                    world.group_name(b),
                )
            });
            if better {
                representatives.insert(language, group);
            }
        }
        for (language, group) in representatives {
            let id = world.registry.languages.get(&language).map(LanguageId);
            let concepts: Vec<String> = id
                .and_then(|l| world.society.endonyms.get(&l))
                .map(|c| {
                    c.iter()
                        .map(|c| world.registry.concepts.name(c.0).to_owned())
                        .collect()
                })
                .unwrap_or_else(|| vec!["language".into()]);
            let lexicon = Live { world, group };
            let mut composed = compose::people(&lexicon, &concepts, &is_vowel, &render);
            let mut motivation = "compound";
            if let Some(form) = id
                .and_then(|l| world.society.endonym_forms.get(&l))
                .and_then(|text| table.parse(text).ok())
            {
                composed.form = form;
                motivation = "authored";
            }
            if composed.form.is_empty() {
                continue;
            }
            let object = format!("language:{language}");
            let index = self.push(
                world,
                object.clone(),
                Role::Endonym,
                group,
                None,
                0,
                world.start_year,
                motivation,
                None,
                composed,
                None,
            );
            self.current.insert(object.clone(), index);
            // Tradice osobních jmen: zadaná autorem, jinak jedna z tradic bez institucí.
            let authored = id
                .and_then(|l| world.society.person_traditions.get(&l))
                .cloned();
            let (paradigm, cause) = match authored {
                Some(p) => (p, "authored"),
                None => {
                    let h = compose::hash(world.seed, &["tradition", &language], 0);
                    let base = persons::BASE_TRADITIONS;
                    (base[(h % base.len() as u64) as usize].to_owned(), "initial")
                }
            };
            self.adopt_tradition(&object, world.start_year, &paradigm, cause, None);
        }
    }

    /// Nové linie z pozorování: první dostane jméno prajazyka, odštěpená jméno zdědí nebo
    /// se pojmenuje jinak; zaniklé linie jméno přestanou užívat.
    fn follow_lineages(
        &mut self,
        world: &World,
        events: &[Map<String, Value>],
        tick: u32,
        year: f64,
    ) {
        let Some(table) = world.table.clone() else {
            return;
        };
        for event in events {
            let kind = event.get("kind").and_then(Value::as_str).unwrap_or("");
            let Some(lineage) = event.get("lineage").and_then(Value::as_str) else {
                continue;
            };
            let object = lineage_object(lineage);
            match kind {
                "language_ended" => {
                    if let Some(&index) = self.current.get(&object) {
                        self.end(index, year);
                    }
                    let held: Vec<usize> = self
                        .exonyms
                        .iter()
                        .filter(|(k, _)| k.ends_with(&format!("|{lineage}")))
                        .map(|(_, &i)| i)
                        .collect();
                    for index in held {
                        self.end(index, year);
                    }
                }
                "language_emerged" | "language_split" => {
                    let groups: Vec<String> = event
                        .get("groups")
                        .and_then(Value::as_array)
                        .map(|a| {
                            a.iter()
                                .filter_map(|v| v.as_str().map(str::to_owned))
                                .collect()
                        })
                        .unwrap_or_default();
                    let Some(group) = crate::naming::representative(world, &groups) else {
                        continue;
                    };
                    let parent = event
                        .get("parent")
                        .and_then(Value::as_str)
                        .map(str::to_owned);
                    self.name_lineage(world, &table, lineage, parent, &groups, group, tick, year);
                }
                _ => {}
            }
        }
    }

    #[allow(clippy::too_many_arguments)]
    fn name_lineage(
        &mut self,
        world: &World,
        table: &crate::segments::SegmentTable,
        lineage: &str,
        parent: Option<String>,
        groups: &[String],
        group: GroupId,
        tick: u32,
        year: f64,
    ) {
        let object = lineage_object(lineage);
        let language = language_name(world, group);
        let is_vowel = |s: i32| table.is_vowel(s);
        let render = |f: &[i32]| table.render(f);
        let proto = format!("language:{language}");
        // Tradice osobních jmen: první linie převezme tradici prajazyka, odštěpená zdědí rodičovu.
        let inherited_from = parent
            .as_deref()
            .map(lineage_object)
            .filter(|p| self.traditions.contains_key(p))
            .unwrap_or_else(|| proto.clone());
        if !self.traditions.contains_key(&object) {
            if let Some(steps) = self.traditions.get(&inherited_from).cloned() {
                if parent.is_none() {
                    self.traditions.insert(object.clone(), steps);
                } else if let Some(last) = steps.last() {
                    let step = TraditionStep {
                        year,
                        paradigm: last.paradigm.clone(),
                        cause: "inherited".into(),
                        source: Some(inherited_from.clone()),
                    };
                    self.traditions.insert(object.clone(), vec![step]);
                }
            }
        }
        // První linie jazyka převezme jméno prajazyka.
        if parent.is_none() {
            if let Some(&index) = self.current.get(&proto) {
                if self.records[index].lineage.is_none() {
                    self.records[index].lineage = Some(lineage.to_owned());
                    self.current.insert(object, index);
                    self.set_carrier(world, index, group);
                    return;
                }
            }
        }
        // Přešla většina skupin na jiný jazyk? Pak si berou jméno, kterým jim říkali sousedé.
        let mut shifted: BTreeMap<String, usize> = BTreeMap::new();
        for name in groups {
            let before = self.group_language.get(name);
            if before.is_some_and(|b| *b != language) {
                if let Some(old) = self.group_lineage.get(name) {
                    *shifted.entry(old.clone()).or_default() += 1;
                }
            }
        }
        let shifted_from = shifted
            .iter()
            .max_by(|a, b| a.1.cmp(b.1).then(b.0.cmp(a.0)))
            .filter(|(_, &n)| 2 * n > groups.len())
            .map(|(l, _)| l.clone());
        let parent_index = parent
            .as_ref()
            .and_then(|p| self.current.get(&lineage_object(p)).copied())
            .or_else(|| self.current.get(&proto).copied());
        let h = compose::hash(world.seed, &["lineage", lineage], 0);
        if let Some(old) = shifted_from {
            if let Some(&old_index) = self.current.get(&lineage_object(&old)) {
                // Exonymum, které pro staré lidi mají mluvčí nového jazyka.
                let existing = self
                    .exonyms
                    .iter()
                    .filter(|(k, _)| k.starts_with(&format!("{}|", lineage_object(&old))))
                    .map(|(_, &i)| i)
                    .find(|&i| {
                        self.records[i].language == language && self.records[i].ended.is_none()
                    });
                let (form, source_index) = match existing {
                    Some(i) => (self.records[i].form.clone(), i),
                    None => (
                        Self::borrow_form(world, &self.records[old_index].form, group, None),
                        old_index,
                    ),
                };
                let source = SourceRef {
                    record: self.records[source_index].id.clone(),
                    ipa: self.ipa(source_index).to_owned(),
                    language: self.records[source_index].language.clone(),
                };
                let meaning = format!("jméno, kterým sousedé říkali {}", self.ipa(old_index));
                let index = self.push(
                    world,
                    object.clone(),
                    Role::Endonym,
                    group,
                    Some(lineage.to_owned()),
                    tick,
                    year,
                    "exonym_adopted",
                    Some("language_shift".into()),
                    Composed {
                        form,
                        pattern: "exonym_adopted".into(),
                        meaning,
                        recipe: Vec::new(),
                    },
                    Some(source),
                );
                self.current.insert(object, index);
                return;
            }
        }
        // Možnosti pojmenování odštěpené linie podle podmínek.
        let region = crate::naming::origin_region(world, groups)
            .and_then(|r| world.registry.territories.get(&r).map(TerritoryId));
        let place = region.and_then(|r| {
            self.current
                .get(&format!(
                    "territory:{}",
                    world.registry.territories.name(r.0)
                ))
                .copied()
        });
        let state = self.majority_state(world, groups);
        let state_name = state
            .as_ref()
            .filter(|(id, _)| {
                self.states
                    .get(id)
                    .is_some_and(|s| year - s.founded >= 100.0)
            })
            .and_then(|(id, _)| self.current.get(&format!("state:{id}")).copied());
        let native = region
            .map(|r| world.territories[r.index()].native_language)
            .filter(|l| !l.is_none());
        let substrate = native
            .map(|l| world.registry.languages.name(l.0).to_owned())
            .filter(|l| *l != language)
            .and_then(|l| self.current.get(&format!("language:{l}")).copied());
        let mut options: Vec<(&str, f64)> = Vec::new();
        if parent_index.is_some() {
            options.push(("inherited", 4.0));
        }
        if place.is_some() {
            options.push(("place", 1.5));
        }
        if state_name.is_some() {
            options.push(("state", 1.5));
        }
        if substrate.is_some() {
            options.push(("substrate", 1.0));
        }
        options.push(("eponym", 0.7));
        options.push(("compound", if parent_index.is_none() { 3.0 } else { 0.3 }));
        let motivation = compose::choose(h, &options);
        let reference = match motivation {
            "inherited" => parent_index,
            "place" => place,
            "state" => state_name,
            "substrate" => substrate,
            _ => None,
        };
        let lexicon = Live { world, group };
        let (composed, source) = match (motivation, reference) {
            (_, Some(from)) => {
                let donor = &self.records[from];
                let form = if donor.language == language && motivation == "inherited" {
                    donor.form.clone()
                } else {
                    Self::borrow_form(world, &donor.form, group, None)
                };
                let meaning = match motivation {
                    "inherited" => format!("zděděno: {}", donor.meaning),
                    "place" => format!("podle kraje „{}“", donor.meaning),
                    "state" => format!("podle státu „{}“", donor.meaning),
                    _ => format!("podle dřívějšího národa „{}“", donor.meaning),
                };
                let source = SourceRef {
                    record: donor.id.clone(),
                    ipa: self.ipa(from).to_owned(),
                    language: donor.language.clone(),
                };
                (
                    Composed {
                        form,
                        pattern: motivation.into(),
                        meaning,
                        recipe: Vec::new(),
                    },
                    Some(source),
                )
            }
            ("eponym", _) => match self.person(
                world,
                group,
                &inherited_from,
                &format!("founder:{lineage}"),
                tick,
            ) {
                Some(founder) => {
                    let (person, _) = self.push_person(
                        world,
                        group,
                        &format!("founder:{lineage}"),
                        &founder,
                        tick,
                        year,
                        "lineage_founder",
                    );
                    let full = self.records[person].full_name.clone().unwrap_or_default();
                    let recipe = vec![RecipePart {
                        concept: None,
                        gloss: format!("zakladatel {full}"),
                        ipa: self.ipa(person).to_owned(),
                        name: Some(self.records[person].id.clone()),
                    }];
                    (
                        Composed {
                            form: founder.given().to_vec(),
                            pattern: "eponym".into(),
                            meaning: format!("lidé zakladatele {full}"),
                            recipe,
                        },
                        None,
                    )
                }
                None => {
                    let mut person = compose::person(&lexicon, h, &is_vowel, &render);
                    person.meaning = format!("lidé zakladatele „{}“", person.meaning);
                    (person, None)
                }
            },
            _ => {
                let concepts = world
                    .society
                    .endonyms
                    .get(&world.groups.main_code(group).language)
                    .map(|c| {
                        c.iter()
                            .map(|c| world.registry.concepts.name(c.0).to_owned())
                            .collect()
                    })
                    .unwrap_or_else(|| vec!["person".to_owned(), "language".to_owned()]);
                (
                    compose::people(&lexicon, &concepts, &is_vowel, &render),
                    None,
                )
            }
        };
        if composed.form.is_empty() {
            return;
        }
        let motivation =
            if motivation == "inherited" || reference.is_some() || motivation == "eponym" {
                motivation
            } else {
                "compound"
            };
        let cause = parent.as_ref().map(|_| "split".to_owned());
        let index = self.push(
            world,
            object.clone(),
            Role::Endonym,
            group,
            Some(lineage.to_owned()),
            tick,
            year,
            motivation,
            cause,
            composed,
            source,
        );
        self.current.insert(object, index);
    }

    /// Stát, ve kterém leží většina skupin (`STATE_MAJORITY`), a jeho úřední jazyk.
    fn majority_state(&self, world: &World, groups: &[String]) -> Option<(String, LanguageId)> {
        let mut counts: BTreeMap<&str, usize> = BTreeMap::new();
        let mut total = 0;
        for name in groups {
            let Some(group) = group_named(world, name) else {
                continue;
            };
            total += 1;
            let Some(region) = region_of(world, world.groups.territory[group.index()]) else {
                continue;
            };
            for (id, polity) in &world.society.states {
                if polity.regions.contains(&region) {
                    *counts.entry(id.as_str()).or_default() += 1;
                }
            }
        }
        let (id, n) = counts
            .into_iter()
            .max_by(|a, b| a.1.cmp(&b.1).then(b.0.cmp(a.0)))?;
        (total > 0 && n as f64 >= STATE_MAJORITY * total as f64)
            .then(|| (id.to_owned(), world.society.states[id].language))
    }

    // --- místa -----------------------------------------------------------------------------

    fn place_conditions(
        &self,
        world: &World,
        territory: TerritoryId,
        group: GroupId,
    ) -> PlaceConditions {
        let node = &world.territories[territory.index()];
        let region = region_of(world, territory);
        let terrain = region.map_or_else(
            || node.terrain.clone(),
            |r| world.territories[r.index()].terrain.clone(),
        );
        let urban = node.urban > 0.0
            || (node.level == TerritoryLevel::Region
                && node
                    .children
                    .iter()
                    .any(|c| world.territories[c.index()].urban > 0.0));
        let mut state = None;
        let mut standard = false;
        if let Some(region) = region {
            for (id, polity) in &world.society.states {
                if polity.regions.contains(&region) {
                    standard |= world.society.standards.contains_key(id);
                    if let Some(&index) = self.current.get(&format!("state:{id}")) {
                        let record = &self.records[index];
                        let form = if record.language == language_name(world, group) {
                            record.form.clone()
                        } else {
                            Self::borrow_form(world, &record.form, group, None)
                        };
                        state = Some((form, romanize(self.ipa(index)), record.id.clone()));
                    }
                    break;
                }
            }
        }
        let at = group.index();
        let literate =
            standard || world.groups.literacy[at] > 0.2 || world.groups.schooling[at] > 0.2;
        PlaceConditions {
            region: node.level == TerritoryLevel::Region,
            urban,
            terrain,
            state,
            literate,
            origin: None,
            founder: None,
        }
    }

    /// Jméno nového místa (nebo místa, kde se změnil jazyk obyvatel a staré jméno nepřevzali).
    #[allow(clippy::too_many_arguments)]
    fn found_place(
        &mut self,
        world: &World,
        territory: TerritoryId,
        group: GroupId,
        origin: Option<usize>,
        community: Option<String>,
        tick: u32,
        year: f64,
        cause: Option<&str>,
    ) -> Option<usize> {
        let table = world.table.clone()?;
        let is_vowel = |s: i32| table.is_vowel(s);
        let render = |f: &[i32]| table.render(f);
        let name = world.registry.territories.name(territory.0).to_owned();
        let mut conditions = self.place_conditions(world, territory, group);
        if let Some(origin) = origin {
            let record = &self.records[origin];
            let form = if record.language == language_name(world, group) {
                record.form.clone()
            } else {
                Self::borrow_form(world, &record.form, group, None)
            };
            conditions.origin = Some((form, romanize(self.ipa(origin)), record.id.clone()));
        }
        // Zakladatel podle tradice komunity (osadníci si ji nesou s sebou).
        let community = community.unwrap_or_else(|| self.community_of(world, group));
        let founder = self.person(world, group, &community, &format!("founder:{name}"), tick);
        if let Some(founder) = &founder {
            conditions.founder = Some((founder.given().to_vec(), founder.full(&render)));
        }
        let lexicon = Live { world, group };
        let mut composed = Composed::default();
        for attempt in 0..16_u64 {
            let h = compose::hash(world.seed, &["place", &name, &tick.to_string()], attempt);
            composed = compose::place(&lexicon, &conditions, h, &is_vowel, &render);
            let roman = romanize(&render(&composed.form));
            if !roman.is_empty() && !self.used.contains(&roman) {
                self.used.insert(roman);
                break;
            }
        }
        if composed.form.is_empty() {
            return None;
        }
        let tradition = conditions.tradition().name();
        if composed.pattern == "eponymous_founder" {
            if let Some(founder) = &founder {
                let migrated = community != self.community_of(world, group);
                let cause = if migrated {
                    "settlement_founder_migration"
                } else {
                    "settlement_founder"
                };
                let (person, _) = self.push_person(
                    world,
                    group,
                    &format!("founder:{name}"),
                    founder,
                    tick,
                    year,
                    cause,
                );
                if let Some(part) = composed.recipe.first_mut() {
                    part.name = Some(self.records[person].id.clone());
                }
            }
        }
        let object = format!("territory:{name}");
        let motivation = composed.pattern.clone();
        let index = self.push(
            world,
            object.clone(),
            Role::Endonym,
            group,
            None,
            tick,
            year,
            &motivation,
            Some(tradition.to_owned()),
            composed,
            None,
        );
        if let Some(cause) = cause {
            self.records[index].cause = Some(cause.to_owned());
        }
        self.current.insert(object, index);
        Some(index)
    }

    /// Území, která vznikla od posledního kroku (na začátku všechna).
    fn found_territories(
        &mut self,
        world: &World,
        events: &[Map<String, Value>],
        tick: u32,
        year: f64,
    ) {
        if self.territories_seen >= world.territories.len() {
            return;
        }
        let mains = main_groups(world);
        // Mateřské sídlo osady založené migrací (největší zdroj přistěhovalců).
        let mut origins: BTreeMap<String, (String, String)> = BTreeMap::new();
        for event in events {
            if event.get("kind").and_then(Value::as_str) != Some("migration") {
                continue;
            }
            let Some(target) = event.get("target").and_then(Value::as_str) else {
                continue;
            };
            let largest = event
                .get("sources")
                .and_then(Value::as_array)
                .and_then(|s| {
                    s.iter()
                        .filter_map(|p| Some((p.get(1)?.as_f64()?, p.get(0)?.as_str()?)))
                        .max_by(|a, b| {
                            a.0.partial_cmp(&b.0)
                                .unwrap_or(std::cmp::Ordering::Equal)
                                .then(a.1.cmp(b.1))
                        })
                });
            if let Some((_, source)) = largest {
                if let Some(group) = group_named(world, source) {
                    let territory = world.groups.territory[group.index()];
                    if !territory.is_none() {
                        origins.insert(
                            target.to_owned(),
                            (
                                world.registry.territories.name(territory.0).to_owned(),
                                self.community_of(world, group),
                            ),
                        );
                    }
                }
            }
        }
        for at in self.territories_seen..world.territories.len() {
            let territory = TerritoryId(at as u32);
            let level = world.territories[at].level;
            if matches!(level, TerritoryLevel::World | TerritoryLevel::Continent) {
                continue;
            }
            let Some(&group) = mains.get(&territory) else {
                continue;
            };
            let name = world.registry.territories.name(territory.0);
            let origin = origins
                .get(name)
                .and_then(|(o, _)| self.current.get(&format!("territory:{o}")).copied());
            let community = origins.get(name).map(|(_, c)| c.clone());
            self.found_place(world, territory, group, origin, community, tick, year, None);
        }
        self.territories_seen = world.territories.len();
    }

    /// Nositel jména místa je hlavní skupina území. Když hlavní skupina mluví jiným jazykem než
    /// uživatelé jména, noví obyvatelé jméno převezmou (substrát), nebo místo pojmenují znovu.
    fn follow_places(&mut self, world: &World, tick: u32, year: f64) {
        let mains = main_groups(world);
        let places: Vec<(String, usize)> = self
            .current
            .iter()
            .filter(|(k, _)| k.starts_with("territory:"))
            .map(|(k, &i)| (k.clone(), i))
            .collect();
        for (object, index) in places {
            let name = &object["territory:".len()..];
            let Some(territory) = world.registry.territories.get(name).map(TerritoryId) else {
                continue;
            };
            let Some(&group) = mains.get(&territory) else {
                continue;
            };
            let language = language_name(world, group);
            if self.records[index].language == language {
                self.set_carrier(world, index, group);
                continue;
            }
            let h = compose::hash(world.seed, &["substrate", name, &tick.to_string()], 0);
            let keep = (h % 10_000) as f64 / 10_000.0 < KEEP_SUBSTRATE_PLACE;
            self.end(index, year);
            if keep {
                let old = &self.records[index];
                let form = Self::borrow_form(world, &old.form, group, None);
                let source = SourceRef {
                    record: old.id.clone(),
                    ipa: self.ipa(index).to_owned(),
                    language: old.language.clone(),
                };
                let meaning = format!("převzato od dřívějších obyvatel: {}", old.meaning);
                let recipe = old.recipe.clone();
                let new = self.push(
                    world,
                    object.clone(),
                    Role::Endonym,
                    group,
                    None,
                    tick,
                    year,
                    "substrate",
                    Some("population_shift".into()),
                    Composed {
                        form,
                        pattern: "substrate".into(),
                        meaning,
                        recipe,
                    },
                    Some(source),
                );
                let roman = romanize(self.ipa(new));
                self.used.insert(roman);
                self.current.insert(object, new);
            } else {
                self.found_place(
                    world,
                    territory,
                    group,
                    None,
                    None,
                    tick,
                    year,
                    Some("population_shift"),
                );
            }
        }
    }

    // --- státy -----------------------------------------------------------------------------

    /// Jména nových států: podle hlavního města, lidí, zakladatele, nebo předchůdce.
    fn found_states(&mut self, world: &World, events: &[Map<String, Value>], tick: u32, year: f64) {
        let Some(table) = world.table.clone() else {
            return;
        };
        let is_vowel = |s: i32| table.is_vowel(s);
        let render = |f: &[i32]| table.render(f);
        // Konec států, které zmizely.
        let ended: Vec<String> = self
            .states
            .iter()
            .filter(|(id, s)| s.ended.is_none() && !world.society.states.contains_key(*id))
            .map(|(id, _)| id.clone())
            .collect();
        for id in ended {
            if let Some(seen) = self.states.get_mut(&id) {
                seen.ended = Some(year);
            }
            if let Some(&index) = self.current.get(&format!("state:{id}")) {
                self.end(index, year);
            }
        }
        let new: Vec<String> = world
            .society
            .states
            .keys()
            .filter(|id| self.states.get(*id).is_none_or(|s| s.ended.is_some()))
            .cloned()
            .collect();
        let _ = events;
        for id in new {
            let polity = &world.society.states[&id];
            let regions: Vec<String> = polity
                .regions
                .iter()
                .map(|r| world.registry.territories.name(r.0).to_owned())
                .collect();
            self.states.insert(
                id.clone(),
                StateSeen {
                    founded: year,
                    ended: None,
                    regions: regions.clone(),
                },
            );
            let group = polity.seat;
            if !world.groups.contains(group) {
                continue;
            }
            let language = language_name(world, group);
            // Předchůdce: zaniklý stát, který držel hlavní kraj nového státu.
            let capital_region = region_of(world, polity.capital)
                .map(|r| world.registry.territories.name(r.0).to_owned());
            let predecessor = self
                .states
                .iter()
                .filter(|(other, s)| {
                    **other != id
                        && s.ended.is_some_and(|e| year - e <= 100.0)
                        && capital_region
                            .as_ref()
                            .is_some_and(|c| s.regions.contains(c))
                })
                .filter_map(|(other, _)| self.current.get(&format!("state:{other}")).copied())
                .max();
            let capital = self
                .current
                .get(&format!(
                    "territory:{}",
                    world.registry.territories.name(polity.capital.0)
                ))
                .copied()
                .or_else(|| {
                    capital_region
                        .as_ref()
                        .and_then(|c| self.current.get(&format!("territory:{c}")).copied())
                });
            let people = self
                .group_lineage
                .get(world.group_name(group))
                .and_then(|l| self.current.get(&lineage_object(l)).copied())
                .or_else(|| self.current.get(&format!("language:{language}")).copied());
            // Zakladatel státu a jeho rod podle tradice komunity sídla.
            let community = self.community_of(world, group);
            let founder = self
                .person(world, group, &community, &format!("founder:{id}"), tick)
                .map(|name| {
                    self.push_person(
                        world,
                        group,
                        &format!("founder:{id}"),
                        &name,
                        tick,
                        year,
                        "state_founder",
                    )
                });
            let h = compose::hash(world.seed, &["state", &id], 0);
            let mut options: Vec<(&str, f64)> = Vec::new();
            if predecessor.is_some() {
                options.push(("predecessor", 3.0));
            }
            if capital.is_some() {
                options.push(("capital", 2.0));
            }
            if people.is_some() {
                options.push(("people", 1.5));
            }
            options.push(("eponym", 1.0));
            let motivation = compose::choose(h, &options);
            let lexicon = Live { world, group };
            let own = |index: usize, this: &NameState| -> Vec<i32> {
                let record = &this.records[index];
                if record.language == language {
                    record.form.clone()
                } else {
                    Self::borrow_form(world, &record.form, group, None)
                }
            };
            let civic = match polity.centralization.as_str() {
                "high" | "strong" => "king",
                "low" | "weak" => "trade",
                _ => "law",
            };
            let (composed, source) = match motivation {
                "predecessor" => {
                    let from = predecessor.unwrap_or_default();
                    let record = &self.records[from];
                    let source = SourceRef {
                        record: record.id.clone(),
                        ipa: self.ipa(from).to_owned(),
                        language: record.language.clone(),
                    };
                    (
                        Composed {
                            form: own(from, self),
                            pattern: "predecessor".into(),
                            meaning: format!("jméno předchozího státu ({})", record.meaning),
                            recipe: Vec::new(),
                        },
                        Some(source),
                    )
                }
                "capital" | "people" => {
                    let from = if motivation == "capital" {
                        capital
                    } else {
                        people
                    }
                    .unwrap_or_default();
                    let head = if motivation == "capital" {
                        civic
                    } else {
                        "earth"
                    };
                    let base = own(from, self);
                    let tail = compose::surface_concept(world, group, head);
                    let record = &self.records[from];
                    let recipe = vec![
                        RecipePart {
                            concept: None,
                            gloss: record.meaning.clone(),
                            ipa: self.ipa(from).to_owned(),
                            name: Some(record.id.clone()),
                        },
                        RecipePart {
                            concept: Some(head.to_owned()),
                            gloss: compose::gloss(head),
                            ipa: render(&tail),
                            name: None,
                        },
                    ];
                    let meaning = if motivation == "capital" {
                        format!(
                            "{} města {}",
                            compose::gloss(head),
                            romanize(self.ipa(from))
                        )
                    } else {
                        format!("země lidí {}", romanize(self.ipa(from)))
                    };
                    (
                        Composed {
                            form: smooth_compound(&[base, tail], &is_vowel),
                            pattern: motivation.into(),
                            meaning,
                            recipe,
                        },
                        None,
                    )
                }
                _ if founder.is_some() => {
                    // Jako *Osman → osmanský*: rodné jméno zakladatele a slovo pro dům.
                    let (person, _) = founder.unwrap_or_default();
                    let full = self.records[person].full_name.clone().unwrap_or_default();
                    let house = compose::surface_concept(world, group, "house");
                    let recipe = vec![
                        RecipePart {
                            concept: None,
                            gloss: format!("zakladatel {full}"),
                            ipa: self.ipa(person).to_owned(),
                            name: Some(self.records[person].id.clone()),
                        },
                        RecipePart {
                            concept: Some("house".into()),
                            gloss: compose::gloss("house"),
                            ipa: render(&house),
                            name: None,
                        },
                    ];
                    let form =
                        smooth_compound(&[self.records[person].form.clone(), house], &is_vowel);
                    (
                        Composed {
                            form,
                            pattern: "eponym".into(),
                            meaning: format!("dům zakladatele {full}"),
                            recipe,
                        },
                        None,
                    )
                }
                _ => {
                    let founder = compose::person(&lexicon, h, &is_vowel, &render);
                    let house = compose::surface_concept(world, group, "house");
                    let recipe = vec![
                        RecipePart {
                            concept: None,
                            gloss: format!("zakladatel „{}“", founder.meaning),
                            ipa: render(&founder.form),
                            name: None,
                        },
                        RecipePart {
                            concept: Some("house".into()),
                            gloss: compose::gloss("house"),
                            ipa: render(&house),
                            name: None,
                        },
                    ];
                    let meaning = format!("dům zakladatele „{}“", founder.meaning);
                    let form = smooth_compound(&[founder.form, house], &is_vowel);
                    (
                        Composed {
                            form,
                            pattern: "eponym".into(),
                            meaning,
                            recipe,
                        },
                        None,
                    )
                }
            };
            if composed.form.is_empty() {
                continue;
            }
            let object = format!("state:{id}");
            let lineage = self.group_lineage.get(world.group_name(group)).cloned();
            let index = self.push(
                world,
                object.clone(),
                Role::Endonym,
                group,
                lineage,
                tick,
                year,
                motivation,
                Some("state".into()),
                composed,
                source,
            );
            self.current.insert(object, index);
        }
    }

    fn follow_states(&mut self, world: &World) {
        for (id, polity) in &world.society.states {
            if let Some(&index) = self.current.get(&format!("state:{id}")) {
                if world.groups.contains(polity.seat)
                    && language_name(world, polity.seat) == self.records[index].language
                {
                    self.set_carrier(world, index, polity.seat);
                }
            }
        }
    }

    // --- pozorování: nositelé linií, exonyma, prestiž, dobový snímek ------------------------

    fn observe(&mut self, world: &World, tick: u32, year: f64) {
        let lineages = world.society.lineages.lineages.clone();
        let mut representative: BTreeMap<String, GroupId> = BTreeMap::new();
        for (lineage, groups) in &lineages {
            if let Some(group) = crate::naming::representative(world, groups) {
                representative.insert(lineage.clone(), group);
            }
        }
        // Nositelé endonym a exonym linií.
        for (lineage, &group) in &representative {
            if let Some(&index) = self.current.get(&lineage_object(lineage)) {
                if self.records[index].language == language_name(world, group) {
                    self.set_carrier(world, index, group);
                }
            }
            let held: Vec<usize> = self
                .exonyms
                .iter()
                .filter(|(k, _)| k.ends_with(&format!("|{lineage}")))
                .map(|(_, &i)| i)
                .collect();
            for index in held {
                if self.records[index].language == language_name(world, group) {
                    self.set_carrier(world, index, group);
                }
            }
        }
        let member: BTreeMap<String, String> = lineages
            .iter()
            .flat_map(|(l, groups)| groups.iter().map(move |g| (g.clone(), l.clone())))
            .collect();
        {
            let _t = crate::timing::scope("names/observe/exonyms");
            self.exonyms_from_contact(world, &member, &representative, tick, year);
        }
        self.prestige(world, &lineages, &representative, tick, year);
        self.name_world(world, &lineages, &representative, tick, year);
        self.follow_traditions(world, &lineages, year);
        let _t = crate::timing::scope("names/observe/epoch");
        self.epoch(world, &lineages, &representative, &member, tick, year);
        self.group_lineage = member;
        self.group_language = home_groups(world)
            .into_iter()
            .map(|g| (world.group_name(g).to_owned(), language_name(world, g)))
            .collect();
    }

    /// Linie, které jsou ve styku, pojmenují jazyky, města a státy svých sousedů.
    fn exonyms_from_contact(
        &mut self,
        world: &World,
        member: &BTreeMap<String, String>,
        representative: &BTreeMap<String, GroupId>,
        tick: u32,
        year: f64,
    ) {
        let mut contact: BTreeSet<(String, String)> = BTreeSet::new();
        for (&(source, target), link) in world.links.iter() {
            if link.strength < CONTACT_STRENGTH {
                continue;
            }
            let (Some(a), Some(b)) = (
                member.get(world.group_name(source)),
                member.get(world.group_name(target)),
            ) else {
                continue;
            };
            if a != b {
                contact.insert((a.clone(), b.clone()));
                contact.insert((b.clone(), a.clone()));
            }
        }
        // Objekty, které patří linii: její jazyk, města jejích mluvčích a státy s jejím sídlem.
        let mut objects: BTreeMap<String, Vec<String>> = BTreeMap::new();
        for (object, &index) in &self.current {
            let record = &self.records[index];
            if record.ended.is_some() || record.role != Role::Endonym {
                continue;
            }
            let owner = if object.starts_with("lineage:") {
                Some(object.clone())
            } else if object == "world" {
                member.get(&record.carrier).cloned()
            } else if object.starts_with("state:") || object.starts_with("territory:") {
                if let Some(t) = object.strip_prefix("territory:") {
                    let urban = world
                        .registry
                        .territories
                        .get(t)
                        .is_some_and(|t| world.territories[t as usize].urban > 0.0);
                    if !urban {
                        continue;
                    }
                }
                member.get(&record.carrier).cloned()
            } else {
                None
            };
            if let Some(owner) = owner {
                objects.entry(owner).or_default().push(object.clone());
            }
        }
        let mut inventories: BTreeMap<String, Vec<i32>> = BTreeMap::new();
        for (owner, other) in contact {
            let Some(list) = objects.get(&owner) else {
                continue;
            };
            let Some(&group) = representative.get(&other) else {
                continue;
            };
            let speech = language_name(world, group);
            for object in list.iter().cloned() {
                let key = exonym_key(&object, &other);
                if self.exonyms.contains_key(&key) {
                    continue;
                }
                let index = self.current[&object];
                // Sesterské linie téhož jazyka jméno zdědily; exonymum vzniká přejetím do cizí řeči.
                if self.records[index].language == speech {
                    continue;
                }
                let inventory = inventories
                    .entry(other.clone())
                    .or_insert_with(|| crate::contact::inventory(world, group))
                    .clone();
                let donor = &self.records[index];
                let form = Self::borrow_form(world, &donor.form, group, Some(&inventory));
                let source = SourceRef {
                    record: donor.id.clone(),
                    ipa: self.ipa(index).to_owned(),
                    language: donor.language.clone(),
                };
                let meaning = format!("jméno sousedů pro {}", romanize(self.ipa(index)));
                let new = self.push(
                    world,
                    object,
                    Role::Exonym,
                    group,
                    Some(other.clone()),
                    tick,
                    year,
                    "borrowed",
                    Some("contact".into()),
                    Composed {
                        form,
                        pattern: "borrowed".into(),
                        meaning,
                        recipe: Vec::new(),
                    },
                    Some(source),
                );
                self.exonyms.insert(key, new);
            }
        }
    }

    /// Jméno světa: exonymum nejstarší říše v nejrozšířenějším jazyce, který ji jmenoval
    /// (jako *Asie* nebo *Řecko* z cizího jména). Ostatní jazyky ho převezmou stykem jako jiná
    /// jména. Když jeho linie zanikne, jméno dál nese nejrozšířenější linie, která ho převzala.
    fn name_world(
        &mut self,
        world: &World,
        lineages: &BTreeMap<String, Vec<String>>,
        representative: &BTreeMap<String, GroupId>,
        tick: u32,
        year: f64,
    ) {
        if let Some(&index) = self.current.get("world") {
            let holder = self.records[index].lineage.clone();
            match holder.as_ref().and_then(|l| representative.get(l)) {
                Some(&group) => {
                    if self.records[index].language == language_name(world, group) {
                        self.set_carrier(world, index, group);
                    }
                }
                None => {
                    let heir = self
                        .exonyms
                        .iter()
                        .filter_map(|(k, &i)| k.strip_prefix("world|").map(|l| (l.to_owned(), i)))
                        .filter(|(l, i)| {
                            lineages.contains_key(l) && self.records[*i].ended.is_none()
                        })
                        .max_by(|a, b| {
                            lineages[&a.0]
                                .len()
                                .cmp(&lineages[&b.0].len())
                                .then(b.0.cmp(&a.0))
                        });
                    if let Some((lineage, heir)) = heir {
                        self.end(index, year);
                        self.exonyms.remove(&exonym_key("world", &lineage));
                        self.records[heir].role = Role::Endonym;
                        self.records[heir].cause = Some("world_name_inherited".into());
                        self.current.insert("world".into(), heir);
                    }
                }
            }
            return;
        }
        let Some(state) = self
            .states
            .iter()
            .min_by(|a, b| {
                a.1.founded
                    .partial_cmp(&b.1.founded)
                    .unwrap_or(std::cmp::Ordering::Equal)
                    .then(a.0.cmp(b.0))
            })
            .map(|(id, _)| id.clone())
        else {
            return;
        };
        let prefix = format!("state:{state}|");
        let Some((namer, exonym)) = self
            .exonyms
            .iter()
            .filter_map(|(k, &i)| k.strip_prefix(&prefix).map(|l| (l.to_owned(), i)))
            .filter(|(l, _)| representative.contains_key(l))
            .max_by(|a, b| {
                lineages[&a.0]
                    .len()
                    .cmp(&lineages[&b.0].len())
                    .then(b.0.cmp(&a.0))
            })
        else {
            return;
        };
        let group = representative[&namer];
        let empire = self
            .records
            .iter()
            .find(|r| r.object == format!("state:{state}") && r.role == Role::Endonym)
            .and_then(|r| r.ipa_at(year).or(r.timeline.last().map(|s| s.ipa.as_str())))
            .map(romanize)
            .unwrap_or_default();
        let donor = &self.records[exonym];
        let source = SourceRef {
            record: donor.id.clone(),
            ipa: self.ipa(exonym).to_owned(),
            language: donor.language.clone(),
        };
        let meaning = format!(
            "jméno, kterým jazyk {} říkal nejstarší říši ({empire}); přešlo na celou zemi",
            donor.language
        );
        let mut form = donor.form.clone();
        let mut cause = None;
        if let Some(locked) = world
            .society
            .world_name_form
            .as_ref()
            .and_then(|text| world.table.as_ref()?.parse(text).ok())
        {
            form = locked;
            cause = Some("authored".to_owned());
        }
        let index = self.push(
            world,
            "world".into(),
            Role::Endonym,
            group,
            Some(namer),
            tick,
            year,
            "oldest_empire_exonym",
            cause,
            Composed {
                form,
                pattern: "oldest_empire_exonym".into(),
                meaning,
                recipe: Vec::new(),
            },
            Some(source),
        );
        self.current.insert("world".into(), index);
    }

    /// Linie, která dlouho leží ve státě s jiným úředním jazykem, může převzít jméno, kterým
    /// jí říká vládnoucí jazyk (jednou za dvojici linie–stát).
    fn prestige(
        &mut self,
        world: &World,
        lineages: &BTreeMap<String, Vec<String>>,
        representative: &BTreeMap<String, GroupId>,
        tick: u32,
        year: f64,
    ) {
        for (lineage, groups) in lineages {
            let object = lineage_object(lineage);
            let (Some(&index), Some(&group)) =
                (self.current.get(&object), representative.get(lineage))
            else {
                continue;
            };
            let Some((state, _)) = self.majority_state(world, groups) else {
                continue;
            };
            let Some(seen) = self.states.get(&state) else {
                continue;
            };
            if year - seen.founded < PRESTIGE_YEARS {
                continue;
            }
            let seat = world.society.states[&state].seat;
            let Some(ruling) = self.group_lineage.get(world.group_name(seat)).cloned() else {
                continue;
            };
            if ruling == *lineage {
                continue;
            }
            let key = format!("prestige|{lineage}|{state}");
            if !self.decided.insert(key) {
                continue;
            }
            let Some(&exonym) = self.exonyms.get(&exonym_key(&object, &ruling)) else {
                continue;
            };
            let h = compose::hash(world.seed, &["prestige", lineage, &state], 0);
            if (h % 10_000) as f64 / 10_000.0 >= PRESTIGE_ADOPTION {
                continue;
            }
            let donor = &self.records[exonym];
            let form = Self::borrow_form(world, &donor.form, group, None);
            let source = SourceRef {
                record: donor.id.clone(),
                ipa: self.ipa(exonym).to_owned(),
                language: donor.language.clone(),
            };
            let meaning = format!(
                "jméno, kterým je jmenoval úřední jazyk státu (dříve {})",
                romanize(self.ipa(index))
            );
            self.end(index, year);
            let new = self.push(
                world,
                object.clone(),
                Role::Endonym,
                group,
                Some(lineage.clone()),
                tick,
                year,
                "exonym_adopted",
                Some("state_prestige".into()),
                Composed {
                    form,
                    pattern: "exonym_adopted".into(),
                    meaning,
                    recipe: Vec::new(),
                },
                Some(source),
            );
            self.current.insert(object, new);
        }
    }

    /// Dobový snímek pro generátor: slova pro jména každé linie a podmínky v krajích.
    fn epoch(
        &mut self,
        world: &World,
        lineages: &BTreeMap<String, Vec<String>>,
        representative: &BTreeMap<String, GroupId>,
        member: &BTreeMap<String, String>,
        tick: u32,
        year: f64,
    ) {
        let concepts = compose::naming_concepts();
        let mut epoch = Epoch {
            tick,
            year,
            ..Epoch::default()
        };
        // Kraj: linie s nejvíc domácími mluvčími, stát, písmo, město, terén.
        let mut population: BTreeMap<TerritoryId, BTreeMap<String, u64>> = BTreeMap::new();
        let mut literate: BTreeSet<TerritoryId> = BTreeSet::new();
        for group in home_groups(world) {
            let Some(region) = region_of(world, world.groups.territory[group.index()]) else {
                continue;
            };
            if let Some(lineage) = member.get(world.group_name(group)) {
                *population
                    .entry(region)
                    .or_default()
                    .entry(lineage.clone())
                    .or_default() += u64::from(world.groups.population[group.index()]);
            }
            if world.groups.literacy[group.index()] > 0.2
                || world.groups.schooling[group.index()] > 0.2
            {
                literate.insert(region);
            }
        }
        for (at, node) in world.territories.iter().enumerate() {
            if node.level != TerritoryLevel::Region {
                continue;
            }
            let region = TerritoryId(at as u32);
            let lineage = population.get(&region).and_then(|p| {
                p.iter()
                    .max_by(|a, b| a.1.cmp(b.1).then(b.0.cmp(a.0)))
                    .map(|(l, _)| l.clone())
            });
            let state = world
                .society
                .states
                .iter()
                .find(|(_, p)| p.regions.contains(&region))
                .map(|(id, _)| id.clone());
            let standard = state
                .as_ref()
                .is_some_and(|s| world.society.standards.contains_key(s));
            let ruling = state.as_ref().and_then(|s| {
                let seat = world.society.states[s].seat;
                world
                    .groups
                    .contains(seat)
                    .then(|| member.get(world.group_name(seat)).cloned())
                    .flatten()
            });
            epoch.regions.insert(
                world.registry.territories.name(region.0).to_owned(),
                EpochRegion {
                    lineage,
                    state,
                    ruling,
                    literate: standard || literate.contains(&region),
                    urban: node
                        .children
                        .iter()
                        .any(|c| world.territories[c.index()].urban > 0.0),
                    terrain: node.terrain.clone(),
                },
            );
        }
        // Slova jen pro linie, které v některém kraji převládají (jen ty generátor čte).
        let wanted: BTreeSet<String> = epoch
            .regions
            .values()
            .filter_map(|r| r.lineage.clone())
            .collect();
        let chosen: Vec<(&String, GroupId)> = lineages
            .keys()
            .filter(|l| wanted.contains(*l))
            .filter_map(|l| representative.get(l).map(|&g| (l, g)))
            .collect();
        let snapshots: Vec<EpochLineage> = {
            use rayon::prelude::*;
            let _t = crate::timing::scope("names/observe/epoch/forms");
            chosen
                .par_iter()
                .map(|&(_, group)| EpochLineage {
                    carrier: world.group_name(group).to_owned(),
                    language: language_name(world, group),
                    rule: world.groups.main_code(group).stress_rule.as_rule(),
                    head_initial: compose::head_initial(world, group),
                    inventory: crate::contact::inventory(world, group),
                    forms: concepts
                        .iter()
                        .cloned()
                        .zip(compose::surface_concepts(world, group, &concepts))
                        .filter(|(_, f)| !f.is_empty())
                        .collect(),
                })
                .collect()
        };
        for ((lineage, _), snapshot) in chosen.into_iter().zip(snapshots) {
            epoch.lineages.insert(lineage.clone(), snapshot);
        }
        self.epochs.push(epoch);
    }

    /// Krok jmen po kroku simulace. `events` jsou záznamy historie z tohoto kroku.
    pub fn step(
        &mut self,
        world: &World,
        events: &[Map<String, Value>],
        tick: u32,
        year: f64,
        observed: bool,
    ) {
        if world.table.is_none() {
            return;
        }
        {
            let _t = crate::timing::scope("names/logs");
            self.update_logs(world, tick);
        }
        // Nejdřív vývoj jmen, která už existují: nová jména a přejetí pak čtou dnešní tvary.
        {
            let _t = crate::timing::scope("names/advance");
            let mut cache = ProcCache::new();
            for index in 0..self.records.len() {
                self.advance(world, index, year, &mut cache);
            }
        }
        {
            let _t = crate::timing::scope("names/found");
            self.found_states(world, events, tick, year);
            self.found_territories(world, events, tick, year);
        }
        {
            let _t = crate::timing::scope("names/places");
            self.follow_places(world, tick, year);
            self.follow_states(world);
        }
        if observed {
            let _t = crate::timing::scope("names/observe");
            self.follow_lineages(world, events, tick, year);
            self.observe(world, tick, year);
        }
    }

    /// Dodatečné pozorování na konci běhu (`Simulation::observe_now`).
    pub fn observe_only(
        &mut self,
        world: &World,
        events: &[Map<String, Value>],
        tick: u32,
        year: f64,
    ) {
        if world.table.is_none() {
            return;
        }
        let mut cache = ProcCache::new();
        for index in 0..self.records.len() {
            self.advance(world, index, year, &mut cache);
        }
        self.follow_lineages(world, events, tick, year);
        self.observe(world, tick, year);
    }

    // --- export ----------------------------------------------------------------------------

    pub fn record_json(&self, record: &NameRecord) -> Value {
        let ipa = record.timeline.last().map_or("", |s| s.ipa.as_str());
        json!({
            "id": record.id,
            "object": record.object,
            "role": record.role.name(),
            "name": romanize(ipa),
            "ipa": ipa,
            "language": record.language,
            "lineage": record.lineage,
            "founded": record.founded_year,
            "ended": record.ended,
            "full_name": record.full_name,
            "motivation": record.motivation,
            "cause": record.cause,
            "tradition": record.tradition,
            "meaning": record.meaning,
            "recipe": record.recipe,
            "source": record.source,
            "timeline": record.timeline.iter().map(|s| json!({
                "year": s.year, "ipa": s.ipa, "name": romanize(&s.ipa), "cause": s.cause,
            })).collect::<Vec<_>>(),
        })
    }

    /// Export: všechny záznamy a rozcestník podle objektů.
    pub fn export(&self) -> Value {
        let mut objects: BTreeMap<&str, (Value, Vec<&str>, Map<String, Value>)> = BTreeMap::new();
        for record in &self.records {
            let entry = objects
                .entry(record.object.as_str())
                .or_insert_with(|| (Value::Null, Vec::new(), Map::new()));
            entry.1.push(record.id.as_str());
        }
        for (object, &index) in &self.current {
            if let Some(entry) = objects.get_mut(object.as_str()) {
                entry.0 = self.records[index].id.clone().into();
            }
        }
        for (key, &index) in &self.exonyms {
            if let Some((object, lineage)) = key.split_once('|') {
                if let Some(entry) = objects.get_mut(object) {
                    entry
                        .2
                        .insert(lineage.to_owned(), self.records[index].id.clone().into());
                }
            }
        }
        json!({
            "records": self.records.iter().map(|r| self.record_json(r)).collect::<Vec<_>>(),
            "traditions": self.traditions,
            "objects": objects.into_iter().map(|(object, (current, all, exonyms))| (object.to_owned(), json!({
                "endonym": current, "records": all, "exonyms": exonyms,
            }))).collect::<Map<String, Value>>(),
        })
    }
}
