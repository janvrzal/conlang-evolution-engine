//! Svět: strom území, skupiny mluvčích, jejich kódy a síť vazeb (zrcadlo `cee.v2.world`).
//!
//! Datový model je ve sloupcích podle čísel z registru ([`crate::ids`]): `Groups`,
//! `Variables`, `Variants`, `Morphemes`, `ConceptColumns`, vazby jako CSR. Textová jména
//! jsou jen v `registry`. Každá oblast, kterou plní jiný agent R1, má vlastní strukturu
//! ve [`crate::state`] (přenos, zvukové změny, gramatika, společnost).
//!
//! `World` je `Clone` (kontrolní bod je kopie) i `serde` (kontrolní bod na disku).

use std::collections::{BTreeMap, HashMap};
use std::sync::Arc;

use serde::{Deserialize, Serialize};

use crate::concepts::{ConceptColumns, ConceptData, ConceptGraph};
use crate::grammar::{Construction, GrammaticalFunction};
use crate::ids::{
    CellId, ConceptId, GroupId, Form, LanguageId, MorphemeId, ProcessId, Registry, TerritoryId, VariableId,
    VariantId, WordClassId,
};
use crate::model::forms::{FormBank, UnitForm};
use crate::model::group::{GroupInit, Groups};
use crate::model::lexicon::{
    FormChange, MorphemeInit, MorphemeKind, MorphemeMeta, Morphemes, Paradigm, ProcessDef,
};
use crate::model::links::{Link, LinkKind, Links};
use crate::model::pools::LivePools;
use crate::model::repertoire::{
    variable_name, Distribution, Origin, Payload, Repertoire, VariableKind, Variables, Variants,
};
use crate::model::territory::{Territory, TerritoryLevel};
use crate::parameters::Parameters;
use crate::rng::{stable_id, stable_int, Part};
use crate::segments::SegmentTable;
use crate::state::grammar::GrammarWorldState;
use crate::state::society::SocietyState;
use crate::state::sound::SoundWorldState;
use crate::state::transfer::TransferState;

/// Podíl vazby z obchodu pod touto mezí se nepočítá (zbytek zaokrouhlení `TradeShift`).
pub const TRADE_MINIMUM: f64 = 1e-3;

/// Tabulka hlásek se v kontrolním bodu nese jen jako příznak (tabulka je vložená data).
mod table_serde {
    use std::sync::Arc;

    use serde::{Deserialize, Deserializer, Serialize, Serializer};

    use crate::segments::SegmentTable;

    pub fn serialize<S: Serializer>(table: &Option<Arc<SegmentTable>>, serializer: S) -> Result<S::Ok, S::Error> {
        table.is_some().serialize(serializer)
    }

    pub fn deserialize<'de, D: Deserializer<'de>>(deserializer: D) -> Result<Option<Arc<SegmentTable>>, D::Error> {
        Ok(bool::deserialize(deserializer)?.then(SegmentTable::default_table))
    }
}

/// Koncovky buněk: (třída slova, buňka) → možnosti s vahami.
pub type Endings = BTreeMap<(String, String), Vec<(String, f64)>>;

/// Svět simulace.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct World {
    pub seed: i64,
    pub start_year: f64,
    /// Kalibrační konstanty (neměnné, sdílí je kopie stavu).
    pub params: Arc<Parameters>,
    /// Jména všech entit; čísla se nemění po celý běh.
    pub registry: Registry,
    #[serde(with = "table_serde")]
    pub table: Option<Arc<SegmentTable>>,
    pub concepts: ConceptColumns,
    /// Graf pojmů pro posun významu, odvozování a skládání.
    pub semantics: Option<Arc<ConceptGraph>>,
    /// Území podle čísla.
    pub territories: Vec<Territory>,
    pub groups: Groups,
    pub links: Links,
    pub variables: Variables,
    pub variants: Variants,
    pub morphemes: Morphemes,
    /// Proces podle čísla procesu (hodnota procesní proměnné), `None` = číslo bez procesu.
    pub processes: Vec<Option<ProcessDef>>,
    /// Paradigma podle čísla třídy slova.
    pub paradigms: Vec<Option<Paradigm>>,
    /// Analogické změny podle čísla formové proměnné.
    pub form_changes: BTreeMap<VariableId, FormChange>,
    /// Banka různých tvarů světa.
    pub bank: FormBank,
    /// Živé fondy: proměnné, ve kterých se skupiny liší.
    pub live: LivePools,
    pub derivational_suffix: Form,
    /// Protojazyky už dostaly souběžnou variabilitu (`variation::seed`).
    pub varied: bool,
    pub transfer: TransferState,
    pub sound: SoundWorldState,
    pub grammar: GrammarWorldState,
    pub society: SocietyState,
}

/// Rozbor zápisu výchozího tvaru: hlásky z tabulky nebo chyba.
fn parse_with(table: &Option<Arc<SegmentTable>>, ipa: &str) -> Result<Form, String> {
    table.as_ref().ok_or("svět nemá tabulku hlásek")?.parse(ipa)
}

impl World {
    pub fn new(seed: i64, params: Parameters) -> World {
        World::with_params(seed, Arc::new(params))
    }

    pub fn with_params(seed: i64, params: Arc<Parameters>) -> World {
        let table = SegmentTable::default_table();
        World {
            seed,
            start_year: 0.0,
            params,
            registry: Registry::default(),
            table: None,
            concepts: ConceptColumns::default(),
            semantics: None,
            territories: Vec::new(),
            groups: Groups::default(),
            links: Links::default(),
            variables: Variables::default(),
            variants: Variants::default(),
            morphemes: Morphemes::default(),
            processes: Vec::new(),
            paradigms: Vec::new(),
            form_changes: BTreeMap::new(),
            bank: FormBank::new(table),
            live: LivePools::default(),
            derivational_suffix: Vec::new(),
            varied: false,
            transfer: TransferState::default(),
            sound: SoundWorldState::default(),
            grammar: GrammarWorldState::default(),
            society: SocietyState::default(),
        }
    }

    /// Tabulka hlásek; svět bez hláskových tvarů (M1) ji nemá.
    pub fn segments(&self) -> Option<&Arc<SegmentTable>> {
        self.table.as_ref()
    }

    // --- území, skupiny, vazby ------------------------------------------------------

    pub fn add_territory(&mut self, name: &str, parent: Option<&str>, mut territory: Territory) -> Result<TerritoryId, String> {
        if self.registry.territories.contains(name) {
            return Err(format!("Území '{name}' už existuje."));
        }
        let parent_id = match parent {
            Some(parent_name) => {
                let id = self
                    .registry
                    .territories
                    .get(parent_name)
                    .ok_or_else(|| format!("Nadřazené území '{parent_name}' neexistuje."))?;
                let up = &self.territories[id as usize];
                if territory.level <= up.level {
                    return Err(format!(
                        "Území '{name}' musí ležet níž než '{parent_name}' ({}).", up.level.name()
                    ));
                }
                TerritoryId(id)
            }
            None => TerritoryId::NONE,
        };
        let id = self.registry.territory(name);
        territory.parent = parent_id;
        if !parent_id.is_none() {
            self.territories[parent_id.index()].children.push(id);
        }
        self.territories.push(territory);
        Ok(id)
    }

    /// Přidá skupinu; její kódy se napojí na číslování světa.
    pub fn add_group(&mut self, init: GroupInit) -> Result<GroupId, String> {
        let name = init.id.clone();
        if self.registry.groups.contains(&name) {
            return Err(format!("Skupina '{name}' už existuje."));
        }
        if init.territory.is_none() || init.territory.index() >= self.territories.len() {
            return Err(format!("Území skupiny '{name}' neexistuje."));
        }
        init.validate()?;
        let id = self.registry.group(&name);
        self.groups.store(id, init)?;
        Ok(id)
    }

    pub fn remove_group(&mut self, id: GroupId) {
        self.groups.remove(id);
        self.links.remove_group(id);
        self.society.trade.retain(|&(a, b), _| a != id && b != id);
    }

    /// Oboustranná vazba. Sousedé se učí jeden od druhého stejně často.
    pub fn connect(&mut self, first: GroupId, second: GroupId, strength: f64, kind: LinkKind) -> Result<(), String> {
        for id in [first, second] {
            if !self.groups.contains(id) {
                return Err(format!("Skupina '{}' neexistuje.", self.registry.groups.name(id.0)));
            }
        }
        if first == second {
            return Err("Skupina nemůže mít vazbu sama na sebe.".into());
        }
        let value = strength.clamp(0.0, 1.0);
        self.links.set(first, second, Link { strength: value, kind });
        self.links.set(second, first, Link { strength: value, kind });
        Ok(())
    }

    pub fn group_ids(&self) -> Vec<GroupId> {
        self.groups.sorted(&self.registry.groups)
    }

    pub fn group_name(&self, id: GroupId) -> &str {
        self.registry.groups.name(id.0)
    }

    pub fn position_of(&self, id: GroupId) -> Option<(f64, f64)> {
        self.territories[self.groups.territory[id.index()].index()].position
    }

    pub fn generation_ceiling(&self) -> f64 {
        self.groups.generation_ceiling()
    }

    // --- stav proměnných ---------------------------------------------------------

    /// Stav z repertoáru (bez živého skladu), včetně výchozí varianty.
    pub fn stored(&self, group: GroupId, variable: VariableId) -> Option<Distribution> {
        if let Some(found) = self.groups.main_code(group).repertoire.get(variable) {
            return Some(found.clone());
        }
        let default = self.variables.default.get(variable.index()).copied()?;
        (!default.is_none()).then(|| Distribution::fixed(default))
    }

    /// Jediné správné čtení stavu: živá proměnná má přednost před repertoárem.
    pub fn distribution(&self, group: GroupId, variable: VariableId) -> Option<Distribution> {
        if self.live.contains(variable) && self.live.column(group).is_some() {
            return self.live.get(group, variable, &self.registry.variants);
        }
        self.stored(group, variable)
    }

    /// Nejčastější varianta a její podíl.
    pub fn dominant(&self, group: GroupId, variable: VariableId) -> Option<(VariantId, f64)> {
        if self.live.contains(variable) && self.live.column(group).is_some() {
            return self.live.dominant(group, variable, &self.registry.variants);
        }
        self.stored(group, variable).map(|d| d.dominant())
    }

    /// Zapíše živé proměnné skupiny do jejího repertoáru (před odebráním či kopií).
    pub fn materialize(&mut self, group: GroupId) {
        if self.live.column(group).is_none() {
            return;
        }
        for variable in self.live.variable_ids() {
            if let Some(item) = self.live.get(group, variable, &self.registry.variants) {
                self.groups.main_code_mut(group).repertoire.set(variable, item);
            }
        }
    }

    /// Přizpůsobí osu živých fondů skupinám světa (po události, která skupiny přidala či ubrala).
    pub fn sync_live_groups(&mut self) -> Result<bool, String> {
        let ids = self.group_ids();
        if ids == self.live.group_ids {
            return Ok(false);
        }
        for group in self.live.group_ids.clone() {
            if self.groups.contains(group) {
                self.materialize(group);
            }
        }
        let mut live = std::mem::take(&mut self.live);
        let variables = live.variable_ids();
        live.set_axis(ids.clone());
        for variable in variables {
            let dists: Vec<Option<Distribution>> = ids.iter().map(|&g| self.stored(g, variable)).collect();
            live.load(variable, &dists, &self.registry.variants)?;
        }
        self.live = live;
        Ok(true)
    }

    /// Načte proměnné, ve kterých se repertoáry skupin liší, ač nejsou živé; vrací jejich čísla.
    pub fn load_differing(&mut self) -> Result<Vec<VariableId>, String> {
        let mut loaded = Vec::new();
        let mut live = std::mem::take(&mut self.live);
        let mut order: Vec<u32> = self.registry.variables.sorted();
        order.retain(|&n| (n as usize) < self.variables.len());
        for number in order {
            let variable = VariableId(number);
            if live.contains(variable) {
                continue;
            }
            let dists: Vec<Option<Distribution>> = live.group_ids.iter().map(|&g| self.stored(g, variable)).collect();
            let mut held: Vec<&Vec<VariantId>> = Vec::new();
            for item in dists.iter().flatten() {
                if !held.contains(&&item.variants) {
                    held.push(&item.variants);
                }
            }
            if held.len() <= 1 && dists.iter().all(|d| d.as_ref().map_or(true, Distribution::is_fixed)) {
                continue;
            }
            live.load(variable, &dists, &self.registry.variants)?;
            loaded.push(variable);
        }
        self.live = live;
        Ok(loaded)
    }

    // --- pojmy, slovník, tvary -----------------------------------------------------

    pub fn concept_frequency(&self, concept: ConceptId) -> f64 {
        self.concepts.frequency_of(concept)
    }

    /// Doplní sloupce pojmů o nové pojmy registru.
    pub fn grow_concepts(&mut self) {
        self.concepts.grow(&self.registry, ConceptData::shared());
    }

    /// Tvar morfému v kódu skupiny: vlastní, nebo výchozí z tabulky morfémů.
    pub fn unit_of(&self, group: GroupId, morpheme: MorphemeId) -> UnitForm {
        match self.groups.main_code(group).forms.get(morpheme) {
            Some(found) => found,
            None => UnitForm {
                form: self.morphemes.form[morpheme.index()],
                boundary: self.morphemes.boundary[morpheme.index()],
                exponent: self.morphemes.exponent[morpheme.index()],
            },
        }
    }

    pub fn form_of(&self, group: GroupId, morpheme: MorphemeId) -> &[i32] {
        self.bank.form(self.unit_of(group, morpheme).form)
    }

    fn make_morpheme(&mut self, name: &str, init: MorphemeInit) -> MorphemeId {
        let id = self.registry.morpheme(name);
        self.morphemes.store(id, init);
        id
    }

    /// Uloží proměnnou (registr, sloupce); lexikální zapíše do registru i svůj pojem.
    pub fn store_variable(&mut self, kind: VariableKind, key: &str, default: VariantId) -> VariableId {
        let id = self.registry.variable(&variable_name(kind, key));
        let concept = if kind == VariableKind::Lexical { self.registry.concept(key) } else { ConceptId::NONE };
        self.variables.store(id, kind, key, default, concept);
        self.grow_concepts();
        id
    }

    pub fn store_variant(&mut self, name: &str, variable: VariableId, payload: Payload, origin: Origin) -> VariantId {
        let id = self.registry.variant(name);
        self.variants.store(id, variable, payload, origin);
        id
    }

    /// Konstrukční proměnná a varianta; stejná konstrukce = stejná varianta (`syntax.register`).
    pub fn register_construction(&mut self, construction: &Construction, origin: &Origin) -> (VariableId, VariantId) {
        let name = variable_name(VariableKind::Construction, &construction.function);
        let variable = match self.registry.variables.get(&name) {
            Some(found) if found.min(u32::MAX - 1) < self.variables.len() as u32 => VariableId(found),
            _ => self.store_variable(VariableKind::Construction, &construction.function, VariantId::NONE),
        };
        let variant_name = stable_id("variant", &[Part::Str("construction"), Part::Str(&construction.key())]);
        let variant = match self.registry.variants.get(&variant_name) {
            Some(found) => VariantId(found),
            None => self.store_variant(&variant_name, variable, Payload::Construction(construction.clone()), origin.clone()),
        };
        (variable, variant)
    }

    /// Prozodická proměnná a varianta (`prosody.register_stress_rule` / `register_stress_strength`).
    pub fn register_prosody(&mut self, key: &str, value: &str, origin: &Origin) -> (VariableId, VariantId) {
        let name = variable_name(VariableKind::Prosody, key);
        let variable = match self.registry.variables.get(&name) {
            Some(found) if found < self.variables.len() as u32 => VariableId(found),
            _ => self.store_variable(VariableKind::Prosody, key, VariantId::NONE),
        };
        let variant_name = stable_id("variant", &[Part::Str("prosody"), Part::Str(&format!("{key}:{value}"))]);
        let variant = match self.registry.variants.get(&variant_name) {
            Some(found) => VariantId(found),
            None => {
                let payload = if key == "stress_rule" {
                    Payload::StressRule(value.to_owned())
                } else {
                    Payload::StressStrength(value.to_owned())
                };
                self.store_variant(&variant_name, variable, payload, origin.clone())
            }
        };
        (variable, variant)
    }

    // --- zasetí slovní zásoby ------------------------------------------------------

    fn seed_paradigm(
        &mut self,
        root: MorphemeId,
        endings: &Endings,
        cells: Option<&[String]>,
    ) -> Result<(), String> {
        let root_name = self.registry.morphemes.name(root.0).to_owned();
        let word_class = self.morphemes.word_class[root.index()];
        let class_name = self.registry.word_classes.name(word_class.0).to_owned();
        let paradigm = self.paradigms[word_class.index()].clone().ok_or("chybí paradigma")?;
        let language = self.morphemes.language[root.index()];
        let language_name = self.registry.languages.name(language.0).to_owned();
        let root_form = self.bank.form(self.morphemes.form[root.index()]).to_vec();
        let root_frequency = self.morphemes.frequency[root.index()];
        let citation = self.registry.cells.name(paradigm.citation().0).to_owned();
        for &cell in &paradigm.cells[1..] {
            let cell_name = self.registry.cells.name(cell.0).to_owned();
            if let Some(allowed) = cells {
                if !allowed.contains(&cell_name) {
                    continue;
                }
            }
            let options = endings
                .get(&(class_name.clone(), cell_name.clone()))
                .filter(|o| !o.is_empty())
                .ok_or_else(|| format!("Chybí koncovky pro {class_name}/{cell_name}."))?;
            let ending = choose(options, &format!("{root_name}{cell_name}"));
            let affix_name = if language_name == "proto" {
                stable_id("affix", &[Part::Str(&class_name), Part::Str(&cell_name), Part::Str(&ending)])
            } else {
                stable_id(
                    "affix",
                    &[Part::Str(&language_name), Part::Str(&class_name), Part::Str(&cell_name), Part::Str(&ending)],
                )
            };
            let affix = match self.registry.morphemes.get(&affix_name) {
                Some(found) if self.morphemes.contains(MorphemeId(found)) => MorphemeId(found),
                _ => {
                    let form = parse_with(&self.table, &ending)?;
                    let form_id = self.bank.id_of(&form);
                    self.make_morpheme(
                        &affix_name,
                        MorphemeInit {
                            meaning: format!("{class_name}.{cell_name}"),
                            form: form_id,
                            frequency: 0.5,
                            kind: MorphemeKind::Affix,
                            origin_group: GroupId::NONE,
                            origin_tick: 0,
                            word_class,
                            lexeme: MorphemeId::NONE,
                            cell,
                            exponent: MorphemeId::NONE,
                            boundary: -1,
                            language,
                            meta: MorphemeMeta::default(),
                        },
                    )
                }
            };
            let affix_form = self.bank.form(self.morphemes.form[affix.index()]).to_vec();
            let mut unit_form = root_form.clone();
            unit_form.extend_from_slice(&affix_form);
            let unit_form_id = self.bank.id_of(&unit_form);
            let unit_name = crate::model::lexicon::unit_name(&root_name, &cell_name, &citation);
            let weight = paradigm.weight(cell).unwrap_or(1.0);
            self.make_morpheme(
                &unit_name,
                MorphemeInit {
                    meaning: self.morphemes.meta[root.index()].meaning.clone(),
                    form: unit_form_id,
                    frequency: root_frequency * weight,
                    kind: MorphemeKind::Word,
                    origin_group: GroupId::NONE,
                    origin_tick: 0,
                    word_class,
                    lexeme: root,
                    cell,
                    exponent: affix,
                    boundary: root_form.len() as i32,
                    language,
                    meta: MorphemeMeta::default(),
                },
            );
        }
        Ok(())
    }

    /// Zmrazený protojazyk: každý pojem má jedno zděděné slovo (`World.seed_lexicon`).
    ///
    /// Bez `forms` je slovo jen identifikátor lexému (svět M1). S nimi dostane každý pojem
    /// morfém s hláskovou podobou a svět tabulku hlásek; pojmy s třídou, pro kterou má svět
    /// paradigma, dostanou i tvary ostatních buněk (kmen + koncovka podle vah z `endings`).
    #[allow(clippy::too_many_arguments)]
    pub fn seed_lexicon(
        &mut self,
        concepts: &[String],
        forms: Option<&HashMap<String, String>>,
        frequencies: Option<&HashMap<String, f64>>,
        classes: Option<&HashMap<String, String>>,
        endings: &Endings,
        language: &str,
        cells: Option<&HashMap<String, Vec<String>>>,
    ) -> Result<Arc<Repertoire>, String> {
        let mut repertoire = Repertoire::new();
        if forms.is_some() && self.table.is_none() {
            self.table = Some(SegmentTable::default_table());
        }
        let language_id = self.registry.language(language);
        let mut seen = std::collections::HashSet::new();
        for concept in concepts {
            if !seen.insert(concept.as_str()) {
                continue;
            }
            let variable_key = variable_name(VariableKind::Lexical, concept);
            let lexeme = stable_id("lexeme", &[Part::Str(language), Part::Str(concept)]);
            let concept_id = self.registry.concept(concept);
            self.grow_concepts();
            let (morpheme, origin) = match forms {
                Some(forms) => {
                    let mut word_class = classes.and_then(|c| c.get(concept)).cloned();
                    if let Some(name) = &word_class {
                        let known = self.registry.word_classes.get(name).is_some_and(|i| {
                            self.paradigms.get(i as usize).is_some_and(Option::is_some)
                        });
                        if !known {
                            word_class = None;
                        }
                    }
                    let class_id = word_class.as_deref().map_or(WordClassId::NONE, |n| self.registry.word_class(n));
                    if !self.concepts.word_class_set[concept_id.index()] {
                        self.concepts.word_class_set[concept_id.index()] = true;
                        self.concepts.word_class[concept_id.index()] = class_id;
                    }
                    let given = frequencies.and_then(|f| f.get(concept)).copied().unwrap_or(0.5);
                    let frequency = self.concepts.default_frequency(concept_id, given);
                    let form = parse_with(&self.table, forms.get(concept).ok_or_else(|| format!("chybí tvar pojmu {concept}"))?)?;
                    let form_id = self.bank.id_of(&form);
                    let morpheme_name = stable_id("morpheme", &[Part::Str(language), Part::Str(concept)]);
                    let morpheme = self.make_morpheme(
                        &morpheme_name,
                        MorphemeInit {
                            meaning: concept.clone(),
                            form: form_id,
                            frequency,
                            kind: MorphemeKind::Root,
                            origin_group: GroupId::NONE,
                            origin_tick: 0,
                            word_class: class_id,
                            lexeme: MorphemeId::NONE,
                            cell: CellId::NONE,
                            exponent: MorphemeId::NONE,
                            boundary: -1,
                            language: language_id,
                            meta: MorphemeMeta::default(),
                        },
                    );
                    if !class_id.is_none() {
                        let allowed = cells.map(|c| {
                            c.get(word_class.as_deref().unwrap_or("")).cloned().unwrap_or_default()
                        });
                        self.seed_paradigm(morpheme, endings, allowed.as_deref())?;
                    }
                    (morpheme, "inherited")
                }
                None => (MorphemeId::NONE, ""),
            };
            let variable = self.store_variable(VariableKind::Lexical, concept, VariantId::NONE);
            let variant_name = stable_id("variant", &[Part::Str(language), Part::Str(&variable_key)]);
            let payload = Payload::Lexical {
                lexeme,
                morpheme,
                origin: origin.to_owned(),
                appeal: 0.0,
            };
            let variant = self.store_variant(&variant_name, variable, payload, Origin::inherited(self.start_year));
            repertoire.set(variable, Distribution::fixed(variant));
        }
        Ok(repertoire.freeze())
    }

    /// Doplní paradigmata světa (třída slova → paradigma).
    pub fn set_paradigm(&mut self, class: &str, cells: &[(&str, f64)]) {
        let id = self.registry.word_class(class);
        let cell_ids: Vec<CellId> = cells.iter().map(|(c, _)| self.registry.cell(c)).collect();
        if self.paradigms.len() <= id.index() {
            self.paradigms.resize(id.index() + 1, None);
        }
        self.paradigms[id.index()] =
            Some(Paradigm { word_class: id, cells: cell_ids, weights: cells.iter().map(|(_, w)| *w).collect() });
    }

    /// Proces podle čísla (jen ke čtení).
    pub fn process(&self, id: ProcessId) -> Option<&ProcessDef> {
        self.processes.get(id.index()).and_then(Option::as_ref)
    }

    /// Katalogová funkce s přepisy parametrů světa.
    pub fn grammar_catalog(&self) -> Result<Vec<GrammaticalFunction>, String> {
        Ok(crate::grammar::Catalog::shared().with_overrides(&self.params)?.functions)
    }

    /// Podíl síly vazby mezi skupinami, který přinesla obchodní cesta (0 až 1).
    pub fn trade_share(&self, first: GroupId, second: GroupId) -> f64 {
        let key = if first < second { (first, second) } else { (second, first) };
        let carried = self.society.trade.get(&key).copied().unwrap_or(0.0);
        let Some(link) = self.links.get(first, second) else { return 0.0 };
        if carried <= 0.0 || link.strength <= 0.0 {
            return 0.0;
        }
        let share = carried / link.strength;
        if share < TRADE_MINIMUM { 0.0 } else { share.min(1.0) }
    }

    /// Jazyk (linie) podle jména; nová linie dostane další číslo.
    pub fn language(&mut self, name: &str) -> LanguageId {
        self.registry.language(name)
    }
}

/// Deterministická volba podle vah (bez stavu generátoru): `world._choose`.
fn choose(options: &[(String, f64)], key: &str) -> String {
    let total: f64 = options.iter().map(|(_, w)| *w).sum();
    let mut point = (stable_int(&[Part::Str("ending"), Part::Str(key)]) % 1_000_000) as f64 / 1_000_000.0 * total;
    for (value, weight) in options {
        point -= weight;
        if point < 0.0 {
            return value.clone();
        }
    }
    options.last().expect("možnosti").0.clone()
}

/// Dvojice skupin a síla jejich gravitační vazby (`gravity_pairs`), v pořadí tvorby.
pub fn gravity_pairs(
    world: &World,
    scale: f64,
    reference_population: f64,
    reference_distance: f64,
    max_distance: Option<f64>,
    groups: Option<&[GroupId]>,
) -> Vec<(GroupId, GroupId, f64)> {
    let ids: Vec<GroupId> = match groups {
        None => world.group_ids(),
        Some(given) => {
            let mut sorted = given.to_vec();
            sorted.sort_by(|a, b| world.group_name(*a).cmp(world.group_name(*b)));
            sorted
        }
    };
    let placed: Vec<(GroupId, (f64, f64))> =
        ids.iter().filter_map(|&g| world.position_of(g).map(|p| (g, p))).collect();
    let mut pairs = Vec::new();
    for (index, &(first, first_position)) in placed.iter().enumerate() {
        for &(second, second_position) in &placed[index + 1..] {
            let distance = (first_position.0 - second_position.0).hypot(first_position.1 - second_position.1);
            if distance == 0.0 || max_distance.is_some_and(|m| distance > m) {
                continue;
            }
            let mass = (f64::from(world.groups.population[first.index()])
                * f64::from(world.groups.population[second.index()]))
            .sqrt();
            let pull = scale * (mass / reference_population) / (distance / reference_distance).powi(2);
            pairs.push((first, second, pull / (1.0 + pull)));
        }
    }
    pairs
}

/// Doplní vazby podle gravitačního modelu (Trudgill 1974); vrací počet oboustranných vazeb.
pub fn gravity_links(world: &mut World, max_distance: Option<f64>, groups: Option<&[GroupId]>) -> Result<usize, String> {
    let pairs = gravity_pairs(world, 1.0, 1_000.0, 10.0, max_distance, groups);
    for &(first, second, strength) in &pairs {
        world.connect(first, second, strength, LinkKind::Weak)?;
    }
    Ok(pairs.len())
}

impl World {
    /// Úroveň území jako text (pro export).
    pub fn level_name(level: TerritoryLevel) -> &'static str {
        level.name()
    }
}
