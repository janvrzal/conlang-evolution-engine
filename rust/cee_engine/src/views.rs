//! Průběžně udržované pohledy kódu: počty koncovek, slabost buněk a místa analogií.
//!
//! Dřív byly tyto pohledy keší podle verze kódu (`ViewCache`): každá změna tvaru nebo slovní
//! zásoby zvýšila verzi a další čtení znovu prošlo všechna slova. Tady je to stav kódu
//! ([`ClassIndex`], `GrammarCodeState::index`), který se **upravuje přímo v místech, kde se mění
//! jeho vstupy**: vstup a odchod slova ze slovní zásoby, zápis tvaru, hranice nebo koncovky.
//! Každé takové místo po změně zavolá [`refresh`] pro dotčená slova; ten z aktuálního stavu
//! slova spočte jeho příspěvek a odečte předchozí. Příspěvek je čistá funkce stavu slova
//! (a tvaru lexému, který určuje citační tvar), takže výsledek je stejný jako výpočet od nuly
//! ([`reference`]), a hlavně nezávisí na pořadí změn.
//!
//! **Co se drží:**
//! - počty koncovek podle (třída slova, buňka) v pořadí jmen koncovek a z nich nejčastější
//!   (produktivní) koncovka; shodu rozhodne první ve jménech jako dřív;
//! - počty podob koncovky podle koncovky a z nich nejčastější podoba (shodu rozhodne první
//!   v lexikografickém pořadí hlásek jako dřív);
//! - slabost buněk (kolik tvarů splynulo s citačním tvarem);
//! - místa vyrovnání (kmen jiný než citační tvar) a rozšíření (menšinová koncovka nebo
//!   tvar splynulý s citačním), seřazená podle jména formové proměnné.
//!
//! Slova v kódu jsou čísla z registru; řetězce se skládají jen při změně členství místa
//! (klíč řazení), nikdy při čtení. Pohled je jen odvozený: do kontrolního bodu se neukládá,
//! kopie kódu ho kopíruje a po obnově z kontrolního bodu se postaví znovu ([`build_all`]);
//! dokud pohled postavený není, čtení spočte stav od nuly, jen pomaleji.

use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::sync::atomic::{AtomicBool, Ordering};

use crate::ids::{CellId, FormId, GroupId, MorphemeId, WordClassId};
use crate::model::lexicon::{FormChange, FormOperation, MorphemeKind};
use crate::model::repertoire::{variable_name, VariableKind};
use crate::morphology::split;
use crate::world::World;

/// Příspěvek jednoho slova ve slovní zásobě kódu (z jeho stavu a tvaru jeho lexému).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct Rec {
    class: WordClassId,
    cell: CellId,
    exponent: MorphemeId,
    form: FormId,
    boundary: i32,
    /// Tvar splynul s citačním tvarem lexému.
    merged: bool,
    /// Kmen se liší od citačního tvaru.
    level: bool,
}

impl Rec {
    fn in_grid(&self) -> bool {
        !self.class.is_none() && !self.cell.is_none()
    }
}

/// Počty koncovek jedné buňky třídy.
#[derive(Clone, Debug, Default)]
struct CellCounts {
    /// Koncovka → počet lexémů (jen kladné), v pořadí jmen koncovek.
    exps: Vec<(MorphemeId, u32)>,
    total: u32,
    /// Nejčastější koncovka (shodu rozhodne první ve jménech).
    best: Option<MorphemeId>,
    /// Koncovka, podle které se hledají místa rozšíření (nejčastější a znějící).
    basis: Option<MorphemeId>,
    /// Slova buňky (ve slovní zásobě, s třídou i buňkou).
    units: BTreeSet<MorphemeId>,
}

/// Počty podob koncovky.
#[derive(Clone, Debug, Default)]
struct ShapeCounts {
    shapes: BTreeMap<Vec<i32>, u32>,
    /// Nejčastější podoba (shodu rozhodne první v pořadí hlásek).
    best: Vec<i32>,
}

impl ShapeCounts {
    fn refresh_best(&mut self) {
        let mut best: Option<(&Vec<i32>, u32)> = None;
        for (shape, &count) in &self.shapes {
            if best.is_none_or(|(_, kept)| count > kept) {
                best = Some((shape, count));
            }
        }
        let found = best.map(|b| b.0.clone()).unwrap_or_default();
        self.best = found;
    }
}

/// Průběžně udržovaný stav kódu (viz popis modulu).
#[derive(Clone, Debug, Default)]
pub struct ClassIndex {
    /// Postavený pohled; dokud není, čtení počítá od nuly.
    built: bool,
    /// Příspěvky slov podle čísla morfému.
    recs: Vec<Option<Rec>>,
    cells: HashMap<(WordClassId, CellId), CellCounts>,
    shapes: HashMap<MorphemeId, ShapeCounts>,
    /// (třída, buňka) → (splynulé tvary, všechny tvary); počítají se všechna slova.
    weak: HashMap<(WordClassId, CellId), (u32, u32)>,
    /// Lexém → jeho slova ve slovní zásobě (citační tvar a buňky).
    by_lexeme: HashMap<MorphemeId, Vec<MorphemeId>>,
    /// Místa vyrovnání podle jména formové proměnné; verze roste jen se změnou členů.
    level: BTreeMap<String, FormChange>,
    level_keys: HashMap<MorphemeId, String>,
    pub level_version: u64,
    /// Místa rozšíření (stejně).
    ext: BTreeMap<String, FormChange>,
    ext_keys: HashMap<MorphemeId, String>,
    pub ext_version: u64,
    /// Při stavbě od nuly se místa rozšíření dopočtou najednou.
    bulk: bool,
}

impl ClassIndex {
    pub fn is_built(&self) -> bool {
        self.built
    }

    /// Nejčastější koncovka buňky (shodu rozhodne první ve jménech).
    pub fn productive(&self, class: WordClassId, cell: CellId) -> Option<MorphemeId> {
        self.cells.get(&(class, cell))?.best
    }

    /// Podíl lexémů buňky, které nesou koncovku `exponent`.
    pub fn share(&self, class: WordClassId, cell: CellId, exponent: MorphemeId) -> f64 {
        let Some(counts) = self.cells.get(&(class, cell)) else {
            return 0.0;
        };
        if counts.total == 0 || exponent.is_none() {
            return 0.0;
        }
        let own = counts
            .exps
            .iter()
            .find(|c| c.0 == exponent)
            .map_or(0, |c| c.1);
        f64::from(own) / f64::from(counts.total)
    }

    /// Dnešní nejčastější podoba koncovky (`None` = koncovka v kódu není).
    pub fn ending(&self, exponent: MorphemeId) -> Option<&[i32]> {
        self.shapes.get(&exponent).map(|s| s.best.as_slice())
    }

    /// Koncovka s neprázdnou podobou (prázdná koncovka v Pythonu neplatí).
    pub fn sounding(&self, exponent: MorphemeId) -> bool {
        self.ending(exponent).is_some_and(|e| !e.is_empty())
    }

    /// Podíl tvarů buňky splynulých s citačním tvarem (1 bez tvarů).
    pub fn weakness(&self, class: WordClassId, cell: CellId) -> f64 {
        match self.weak.get(&(class, cell)) {
            Some(&(merged, total)) if total > 0 => f64::from(merged) / f64::from(total),
            _ => 1.0,
        }
    }

    /// Místa vyrovnání v pořadí jmen formových proměnných.
    pub fn level_sites(&self) -> (Vec<FormChange>, Vec<String>) {
        (
            self.level.values().cloned().collect(),
            self.level.keys().cloned().collect(),
        )
    }

    /// Místa rozšíření v pořadí jmen formových proměnných.
    pub fn extension_sites(&self) -> (Vec<FormChange>, Vec<String>) {
        (
            self.ext.values().cloned().collect(),
            self.ext.keys().cloned().collect(),
        )
    }

    // --- stavba a úprava ----------------------------------------------------------------

    /// Postaví pohled od nuly ze slovní zásoby kódu.
    pub fn build(world: &World, group: GroupId) -> ClassIndex {
        let mut index = ClassIndex {
            bulk: true,
            ..ClassIndex::default()
        };
        let units: Vec<MorphemeId> = world
            .groups
            .main_code(group)
            .phonology
            .vocabulary
            .iter()
            .collect();
        for unit in units {
            index.update(world, group, unit);
        }
        index.bulk = false;
        let keys: Vec<(WordClassId, CellId)> = index.cells.keys().copied().collect();
        for key in keys {
            index.settle_cell(world, key);
        }
        index.built = true;
        index
    }

    /// Stav slova ve slovní zásobě kódu (příspěvek), nebo `None`, když v ní není.
    fn record(world: &World, group: GroupId, unit: MorphemeId) -> Option<Rec> {
        let code = world.groups.main_code(group);
        if !code.phonology.vocabulary.contains(unit)
            || world.morphemes.kind[unit.index()] != MorphemeKind::Word
        {
            return None;
        }
        let state = world.unit_of(group, unit);
        let citation = world.unit_of(group, world.morphemes.lexeme_id(unit)).form;
        let form = world.bank.form(state.form);
        let (stem, _) = split(form, state.boundary);
        Some(Rec {
            class: world.morphemes.word_class[unit.index()],
            cell: world.morphemes.cell[unit.index()],
            exponent: state.exponent,
            form: state.form,
            boundary: state.boundary,
            merged: state.form == citation,
            level: stem != world.bank.form(citation),
        })
    }

    /// Dorovná příspěvek jednoho slova na jeho aktuální stav.
    pub fn update(&mut self, world: &World, group: GroupId, unit: MorphemeId) {
        let at = unit.index();
        if self.recs.len() <= at {
            self.recs.resize(at + 1, None);
        }
        let old = self.recs[at];
        let new = Self::record(world, group, unit);
        let lexeme = world.morphemes.lexeme_id(unit);
        if old != new {
            // Znějící koncovky, jejichž podoba se může změnit (a s ní místa rozšíření buněk).
            let touched: Vec<MorphemeId> = [old, new]
                .iter()
                .flatten()
                .map(|r| r.exponent)
                .filter(|e| !e.is_none())
                .collect();
            let before: Vec<bool> = touched.iter().map(|&e| self.sounding(e)).collect();
            if old.is_none() {
                self.by_lexeme.entry(lexeme).or_default().push(unit);
            } else if new.is_none() {
                if let Some(list) = self.by_lexeme.get_mut(&lexeme) {
                    list.retain(|&u| u != unit);
                    if list.is_empty() {
                        self.by_lexeme.remove(&lexeme);
                    }
                }
            }
            if let Some(rec) = old {
                self.remove(world, unit, rec);
            }
            if let Some(rec) = new {
                self.add(world, unit, rec);
            }
            self.recs[at] = new;
            if !self.bulk {
                let mut cells: Vec<(WordClassId, CellId)> = Vec::new();
                for rec in [old, new].iter().flatten() {
                    if rec.in_grid() && !cells.contains(&(rec.class, rec.cell)) {
                        cells.push((rec.class, rec.cell));
                    }
                }
                // Koncovka, která začala nebo přestala znít, mění místa rozšíření buněk,
                // kde je nejčastější.
                for (&exponent, was) in touched.iter().zip(&before) {
                    if self.sounding(exponent) != *was {
                        for (key, counts) in &self.cells {
                            if counts.best == Some(exponent) && !cells.contains(key) {
                                cells.push(*key);
                            }
                        }
                    }
                }
                for key in cells {
                    self.settle_cell(world, key);
                }
            }
        }
        if !self.bulk {
            self.set_level(world, unit);
            self.set_extension(world, unit);
        }
        // Citační tvar se mohl změnit: ostatní slova lexému mají jiné splynutí a kmen.
        if !self.bulk && lexeme == unit {
            let siblings: Vec<MorphemeId> = self
                .by_lexeme
                .get(&lexeme)
                .map(|l| l.iter().copied().filter(|&u| u != unit).collect())
                .unwrap_or_default();
            for sibling in siblings {
                self.update(world, group, sibling);
            }
        }
        if self.bulk {
            self.set_level(world, unit);
        }
    }

    /// Odečte příspěvek slova.
    fn remove(&mut self, world: &World, unit: MorphemeId, rec: Rec) {
        let weak = self.weak.entry((rec.class, rec.cell)).or_default();
        weak.0 -= u32::from(rec.merged);
        weak.1 -= 1;
        if weak.1 == 0 {
            self.weak.remove(&(rec.class, rec.cell));
        }
        if !rec.in_grid() {
            return;
        }
        let key = (rec.class, rec.cell);
        let counts = self.cells.entry(key).or_default();
        counts.units.remove(&unit);
        if rec.exponent.is_none() {
            return;
        }
        if let Some(at) = counts.exps.iter().position(|c| c.0 == rec.exponent) {
            counts.exps[at].1 -= 1;
            if counts.exps[at].1 == 0 {
                counts.exps.remove(at);
            }
        }
        counts.total -= 1;
        counts.best = best_of(&counts.exps);
        let ending = split(world.bank.form(rec.form), rec.boundary).1;
        if let Some(shapes) = self.shapes.get_mut(&rec.exponent) {
            if let Some(count) = shapes.shapes.get_mut(ending) {
                *count -= 1;
                if *count == 0 {
                    shapes.shapes.remove(ending);
                }
            }
            if shapes.shapes.is_empty() {
                self.shapes.remove(&rec.exponent);
            } else {
                shapes.refresh_best();
            }
        }
    }

    /// Přičte příspěvek slova.
    fn add(&mut self, world: &World, unit: MorphemeId, rec: Rec) {
        let weak = self.weak.entry((rec.class, rec.cell)).or_default();
        weak.0 += u32::from(rec.merged);
        weak.1 += 1;
        if !rec.in_grid() {
            return;
        }
        let key = (rec.class, rec.cell);
        let counts = self.cells.entry(key).or_default();
        counts.units.insert(unit);
        if rec.exponent.is_none() {
            return;
        }
        match counts.exps.iter().position(|c| c.0 == rec.exponent) {
            Some(at) => counts.exps[at].1 += 1,
            None => {
                let names = &world.registry.morphemes;
                let name = names.name(rec.exponent.0);
                let at = counts.exps.partition_point(|c| names.name(c.0 .0) < name);
                counts.exps.insert(at, (rec.exponent, 1));
            }
        }
        counts.total += 1;
        counts.best = best_of(&counts.exps);
        let ending = split(world.bank.form(rec.form), rec.boundary).1;
        let shapes = self.shapes.entry(rec.exponent).or_default();
        match shapes.shapes.get_mut(ending) {
            Some(count) => *count += 1,
            None => {
                shapes.shapes.insert(ending.to_vec(), 1);
            }
        }
        shapes.refresh_best();
    }

    /// Koncovka, podle které se v buňce hledají místa rozšíření; změní-li se, přehodnotí
    /// se všechna slova buňky.
    fn settle_cell(&mut self, world: &World, key: (WordClassId, CellId)) {
        let Some(counts) = self.cells.get(&key) else {
            return;
        };
        let basis = counts.best.filter(|&p| self.sounding(p));
        if counts.basis == basis {
            return;
        }
        let units: Vec<MorphemeId> = counts.units.iter().copied().collect();
        if let Some(counts) = self.cells.get_mut(&key) {
            counts.basis = basis;
        }
        if self.bulk {
            return;
        }
        for unit in units {
            self.set_extension(world, unit);
        }
    }

    /// Dorovná členství slova v místech vyrovnání.
    fn set_level(&mut self, world: &World, unit: MorphemeId) {
        let wanted = self
            .recs
            .get(unit.index())
            .copied()
            .flatten()
            .is_some_and(|r| r.level);
        let held = self.level_keys.contains_key(&unit);
        if wanted == held {
            return;
        }
        self.level_version += 1;
        if wanted {
            let change = FormChange {
                operation: FormOperation::Level,
                unit,
                exponent: MorphemeId::NONE,
                segment: None,
            };
            let name = variable_name(VariableKind::Form, &change.key(&world.registry.morphemes));
            self.level_keys.insert(unit, name.clone());
            self.level.insert(name, change);
        } else if let Some(name) = self.level_keys.remove(&unit) {
            self.level.remove(&name);
        }
    }

    /// Dorovná členství slova v místech rozšíření.
    fn set_extension(&mut self, world: &World, unit: MorphemeId) {
        let rec = self.recs.get(unit.index()).copied().flatten();
        let wanted = rec.and_then(|r| {
            if !r.in_grid() {
                return None;
            }
            let p = self.cells.get(&(r.class, r.cell))?.basis?;
            (r.exponent != p || r.merged).then_some(p)
        });
        let held = self.ext_keys.get(&unit).cloned();
        let name = wanted.map(|p| {
            let change = FormChange {
                operation: FormOperation::Extend,
                unit,
                exponent: p,
                segment: None,
            };
            (
                variable_name(VariableKind::Form, &change.key(&world.registry.morphemes)),
                change,
            )
        });
        match (held, name) {
            (None, None) => {}
            (Some(old), Some((new, _))) if old == new => {}
            (_, name) => {
                self.ext_version += 1;
                if let Some(old) = self.ext_keys.remove(&unit) {
                    self.ext.remove(&old);
                }
                if let Some((new, change)) = name {
                    self.ext_keys.insert(unit, new.clone());
                    self.ext.insert(new, change);
                }
            }
        }
    }
}

/// Nejčastější koncovka ze seznamu v pořadí jmen (shodu rozhodne první).
fn best_of(exps: &[(MorphemeId, u32)]) -> Option<MorphemeId> {
    let mut best: Option<(MorphemeId, u32)> = None;
    for &(exponent, count) in exps {
        if best.is_none_or(|(_, held)| count > held) {
            best = Some((exponent, count));
        }
    }
    best.map(|(exponent, _)| exponent)
}

/// Pohled kódu skupiny: živý, nebo (dokud pohled není postavený) spočtený od nuly.
pub enum Stats<'a> {
    Live(&'a ClassIndex),
    Fresh(Box<ClassIndex>),
}

impl std::ops::Deref for Stats<'_> {
    type Target = ClassIndex;

    fn deref(&self) -> &ClassIndex {
        match self {
            Stats::Live(index) => index,
            Stats::Fresh(index) => index,
        }
    }
}

/// Pohled kódu skupiny pro čtení.
pub fn stats(world: &World, group: GroupId) -> Stats<'_> {
    let index = &world.groups.main_code(group).phonology.grammar.index;
    if index.built {
        Stats::Live(index)
    } else {
        Stats::Fresh(Box::new(built_fresh(world, group)))
    }
}

fn built_fresh(world: &World, group: GroupId) -> ClassIndex {
    ClassIndex::build(world, group)
}

/// Slova kódu se změnila (vstup nebo odchod ze slovní zásoby, zápis tvaru): dorovná pohled.
///
/// Volá se po změně, ze skutečného stavu slov; pohled, který ještě není postavený, se
/// postaví celý.
pub fn refresh(world: &mut World, group: GroupId, units: &[MorphemeId]) {
    let mut index = std::mem::take(&mut world.groups.main_code_mut(group).phonology.grammar.index);
    if index.built {
        for &unit in units {
            index.update(world, group, unit);
        }
    } else {
        index = built_fresh(world, group);
        world
            .groups
            .main_code(group)
            .phonology
            .grammar
            .cache
            .clear();
    }
    world.groups.main_code_mut(group).phonology.grammar.index = index;
}

static VERIFY: AtomicBool = AtomicBool::new(false);

/// Zapne (nebo vypne) kontrolu pohledů proti výpočtu od nuly po každém kroku simulace.
pub fn set_verify(on: bool) {
    VERIFY.store(on, Ordering::Relaxed);
}

/// Kontroluje se po každém kroku? V ladicím sestavení vždy, jinak po `set_verify` nebo s
/// proměnnou prostředí `CEE_VERIFY_VIEWS`.
pub fn verifying() -> bool {
    cfg!(debug_assertions)
        || VERIFY.load(Ordering::Relaxed)
        || std::env::var_os("CEE_VERIFY_VIEWS").is_some_and(|v| !v.is_empty() && v != "0")
}

/// Postaví pohledy skupin, které je nemají postavené (po obnově z kontrolního bodu).
pub fn build_missing(world: &mut World) {
    for group in world.group_ids() {
        let code = world.groups.main_code(group);
        if !code.phonology.grammar.dominant.built {
            let dominant = DominantIndex::build(world, group);
            world.groups.main_code_mut(group).phonology.grammar.dominant = dominant;
            crate::changes::lexicon::build_rates(world, group);
            vocabulary_changed(world, group, &[]);
        }
        let code = world.groups.main_code(group);
        if code.phonology.grammar.index.built || code.phonology.vocabulary.is_empty() {
            continue;
        }
        let index = built_fresh(world, group);
        let code = world.groups.main_code_mut(group);
        code.phonology.grammar.index = index;
        code.phonology.grammar.cache.clear();
    }
}

/// Zápis tvaru slova a dorovnání pohledů (místo `forms.set`).
pub fn set_form(
    world: &mut World,
    group: GroupId,
    unit: MorphemeId,
    form: crate::model::forms::UnitForm,
) {
    world.groups.main_code_mut(group).forms.set(unit, form);
    refresh(world, group, &[unit]);
}

// --- výpočet od nuly a kontrola ----------------------------------------------------------

/// Výpočet pohledů od nuly (původní algoritmus bez průběžného stavu).
pub mod reference {
    use super::*;

    pub struct Reference {
        pub exponents: BTreeMap<(WordClassId, CellId), Vec<(MorphemeId, u32)>>,
        pub endings: BTreeMap<MorphemeId, Vec<i32>>,
        pub weakness: HashMap<(WordClassId, CellId), (u32, u32)>,
        pub level: Vec<(String, FormChange)>,
        pub extension: Vec<(String, FormChange)>,
    }

    fn word_units(world: &World, group: GroupId) -> Vec<MorphemeId> {
        world
            .groups
            .main_code(group)
            .phonology
            .vocabulary
            .iter()
            .filter(|&unit| world.morphemes.kind[unit.index()] == MorphemeKind::Word)
            .collect()
    }

    pub fn compute(world: &World, group: GroupId) -> Reference {
        let mut counts: HashMap<(WordClassId, CellId), HashMap<MorphemeId, u32>> = HashMap::new();
        let mut shapes: HashMap<MorphemeId, BTreeMap<Vec<i32>, u32>> = HashMap::new();
        let mut weakness: HashMap<(WordClassId, CellId), (u32, u32)> = HashMap::new();
        let citation =
            |unit: MorphemeId| world.unit_of(group, world.morphemes.lexeme_id(unit)).form;
        for unit in word_units(world, group) {
            let class = world.morphemes.word_class[unit.index()];
            let cell = world.morphemes.cell[unit.index()];
            let state = world.unit_of(group, unit);
            let entry = weakness.entry((class, cell)).or_insert((0, 0));
            entry.1 += 1;
            if state.form == citation(unit) {
                entry.0 += 1;
            }
            if class.is_none() || cell.is_none() || state.exponent.is_none() {
                continue;
            }
            *counts
                .entry((class, cell))
                .or_default()
                .entry(state.exponent)
                .or_insert(0) += 1;
            let form = world.bank.form(state.form);
            let (_, ending) = split(form, state.boundary);
            *shapes
                .entry(state.exponent)
                .or_default()
                .entry(ending.to_vec())
                .or_insert(0) += 1;
        }
        let names = &world.registry.morphemes;
        let exponents: BTreeMap<_, _> = counts
            .into_iter()
            .map(|(key, held)| {
                let mut items: Vec<(MorphemeId, u32)> = held.into_iter().collect();
                items.sort_by(|a, b| names.name(a.0 .0).cmp(names.name(b.0 .0)));
                (key, items)
            })
            .collect();
        let endings: BTreeMap<_, _> = shapes
            .into_iter()
            .map(|(exponent, held)| {
                let mut best: Option<(&Vec<i32>, u32)> = None;
                for (shape, &count) in &held {
                    if best.is_none_or(|(_, kept)| count > kept) {
                        best = Some((shape, count));
                    }
                }
                (exponent, best.map(|b| b.0.clone()).unwrap_or_default())
            })
            .collect();
        let productive =
            |class, cell| -> Option<MorphemeId> { best_of(exponents.get(&(class, cell))?) };
        let sounding = |e: MorphemeId| endings.get(&e).is_some_and(|s| !s.is_empty());
        let mut level = Vec::new();
        let mut extension = Vec::new();
        for unit in word_units(world, group) {
            let class = world.morphemes.word_class[unit.index()];
            let cell = world.morphemes.cell[unit.index()];
            let state = world.unit_of(group, unit);
            let form = world.bank.form(state.form);
            let (stem, _) = split(form, state.boundary);
            let cit = world.bank.form(citation(unit));
            let key = |change: &FormChange| variable_name(VariableKind::Form, &change.key(names));
            if stem != cit {
                let change = FormChange {
                    operation: FormOperation::Level,
                    unit,
                    exponent: MorphemeId::NONE,
                    segment: None,
                };
                level.push((key(&change), change));
            }
            if class.is_none() || cell.is_none() {
                continue;
            }
            let Some(p) = productive(class, cell) else {
                continue;
            };
            if !sounding(p) {
                continue;
            }
            if state.exponent != p || state.form == citation(unit) {
                let change = FormChange {
                    operation: FormOperation::Extend,
                    unit,
                    exponent: p,
                    segment: None,
                };
                extension.push((key(&change), change));
            }
        }
        level.sort_by(|a, b| a.0.cmp(&b.0));
        extension.sort_by(|a, b| a.0.cmp(&b.0));
        Reference {
            exponents,
            endings,
            weakness,
            level,
            extension,
        }
    }
}

/// Porovná pohled skupiny s výpočtem od nuly; chyba nese popis první odchylky.
pub fn verify_group(world: &World, group: GroupId) -> Result<(), String> {
    let index = &world.groups.main_code(group).phonology.grammar.index;
    let vocabulary = &world.groups.main_code(group).phonology.vocabulary;
    if !index.built && !vocabulary.is_empty() {
        return Err("pohled kódu není postavený".into());
    }
    if !index.built {
        return Ok(());
    }
    verify_dominant(world, group)?;
    let reference = reference::compute(world, group);
    let name = world.group_name(group).to_owned();
    // Počty koncovek.
    let mut held: BTreeMap<(WordClassId, CellId), Vec<(MorphemeId, u32)>> = BTreeMap::new();
    for (key, counts) in &index.cells {
        if !counts.exps.is_empty() {
            held.insert(*key, counts.exps.clone());
        }
    }
    if held != reference.exponents {
        return Err(format!("{name}: počty koncovek se liší od výpočtu od nuly"));
    }
    let endings: BTreeMap<MorphemeId, Vec<i32>> = index
        .shapes
        .iter()
        .map(|(k, v)| (*k, v.best.clone()))
        .collect();
    if endings != reference.endings {
        return Err(format!(
            "{name}: podoby koncovek se liší od výpočtu od nuly"
        ));
    }
    if index.weak != reference.weakness {
        return Err(format!("{name}: slabost buněk se liší od výpočtu od nuly"));
    }
    let level: Vec<(String, FormChange)> = index
        .level
        .iter()
        .map(|(k, v)| (k.clone(), v.clone()))
        .collect();
    if level != reference.level {
        return Err(format!(
            "{name}: místa vyrovnání se liší od výpočtu od nuly"
        ));
    }
    let extension: Vec<(String, FormChange)> = index
        .ext
        .iter()
        .map(|(k, v)| (k.clone(), v.clone()))
        .collect();
    if extension != reference.extension {
        return Err(format!(
            "{name}: místa rozšíření se liší od výpočtu od nuly"
        ));
    }
    Ok(())
}

/// Porovná pohledy všech skupin s výpočtem od nuly (testy, ladění).
pub fn verify(world: &World) -> Result<(), String> {
    for group in world.group_ids() {
        verify_group(world, group)?;
    }
    Ok(())
}

// --- dominantní kořeny: odvozeniny, součty četností a míry sémantických změn ---------------

use crate::ids::ConceptId;

/// Počet druhů sémantických změn (`changes::lexicon::Semantic`).
pub const SEMANTIC_KINDS: usize = 7;

/// Pohledy odvozené z dominantních kořenů kódu; upravují se při každé změně dominantního kořene
/// pojmu ([`set_dominant`]).
#[derive(Clone, Debug, Default)]
pub struct DominantIndex {
    built: bool,
    /// Počet pojmů registru, pro který je pohled postavený.
    concepts: usize,
    /// Základní pojem → (pojem, kořen) odvozenin z něj, seřazeno podle jména pojmu.
    derived: Vec<Vec<(ConceptId, MorphemeId)>>,
    /// Kořen → pojmy, které vyjadřuje (vzestupně podle čísla pojmu).
    by_root: HashMap<MorphemeId, Vec<ConceptId>>,
    /// Kořen → součet četností jeho pojmů (v pořadí čísel pojmů, jako při výpočtu od nuly).
    totals: HashMap<MorphemeId, f64>,
}

/// Míry sémantických změn podle druhu a pojmu (`None` = pojem nemá cestu); verze druhu roste
/// jen se změnou některé míry.
#[derive(Clone, Debug, Default)]
pub struct SemanticRates {
    pub built: bool,
    pub concepts: usize,
    pub rates: Vec<Vec<Option<f64>>>,
    pub versions: [u64; SEMANTIC_KINDS],
}

/// Základní pojem odvozeniny, kterou kořen je (`_derivations`).
pub fn derivation_base(world: &World, root: MorphemeId) -> Option<usize> {
    let meta = &world.morphemes.meta[root.index()];
    if meta.etymology.as_deref() == Some("derivation") && meta.sources.len() == 1 {
        world
            .registry
            .concepts
            .get(&meta.sources[0])
            .map(|b| b as usize)
    } else {
        None
    }
}

fn concept_name_cmp(world: &World, a: ConceptId, b: ConceptId) -> std::cmp::Ordering {
    world
        .registry
        .concepts
        .name(a.0)
        .cmp(world.registry.concepts.name(b.0))
}

impl DominantIndex {
    pub fn is_built(&self) -> bool {
        self.built
    }

    /// Odvozeniny podle základního pojmu.
    pub fn derived(&self) -> &[Vec<(ConceptId, MorphemeId)>] {
        &self.derived
    }

    /// Součty četností pojmů podle dominantního kořene.
    pub fn totals(&self) -> &HashMap<MorphemeId, f64> {
        &self.totals
    }

    fn total_of(world: &World, concepts: &[ConceptId]) -> f64 {
        let mut total = 0.0;
        for &concept in concepts {
            total += world.concepts.frequency_of(concept);
        }
        total
    }

    /// Postaví pohled od nuly z dominantních kořenů kódu.
    pub fn build(world: &World, group: GroupId) -> DominantIndex {
        let code = world.groups.main_code(group);
        let size = world.registry.concepts.len();
        let mut index = DominantIndex {
            built: true,
            concepts: size,
            derived: vec![Vec::new(); size],
            ..DominantIndex::default()
        };
        let mut items: Vec<(ConceptId, MorphemeId)> = Vec::new();
        for (at, &root) in code.phonology.dominant.iter().enumerate() {
            if root.is_none() {
                continue;
            }
            index
                .by_root
                .entry(root)
                .or_default()
                .push(ConceptId::new(at));
            items.push((ConceptId::new(at), root));
        }
        for (root, concepts) in &index.by_root {
            index
                .totals
                .insert(*root, DominantIndex::total_of(world, concepts));
        }
        items.sort_by(|a, b| concept_name_cmp(world, a.0, b.0));
        for (other, root) in items {
            if let Some(base) = derivation_base(world, root) {
                index.derived[base].push((other, root));
            }
        }
        index
    }

    /// Dominantní kořen pojmu se změnil z `old` na `new`.
    fn change(&mut self, world: &World, concept: ConceptId, old: MorphemeId, new: MorphemeId) {
        if !old.is_none() {
            if let Some(base) = derivation_base(world, old) {
                self.derived[base].retain(|&(c, _)| c != concept);
            }
            if let Some(list) = self.by_root.get_mut(&old) {
                list.retain(|&c| c != concept);
                if list.is_empty() {
                    self.by_root.remove(&old);
                    self.totals.remove(&old);
                } else {
                    let total = DominantIndex::total_of(world, list);
                    self.totals.insert(old, total);
                }
            }
        }
        if !new.is_none() {
            if let Some(base) = derivation_base(world, new) {
                let list = &mut self.derived[base];
                let at = list.partition_point(|&(c, _)| {
                    concept_name_cmp(world, c, concept) == std::cmp::Ordering::Less
                });
                list.insert(at, (concept, new));
            }
            let list = self.by_root.entry(new).or_default();
            let at = list.partition_point(|&c| c < concept);
            list.insert(at, concept);
            let total = DominantIndex::total_of(world, list);
            self.totals.insert(new, total);
        }
    }
}

/// Dominantní kořen pojmu kódu se změnil (volá se po zápisu do `phonology.dominant`).
pub fn dominant_changed(
    world: &mut World,
    group: GroupId,
    concept: ConceptId,
    old: MorphemeId,
    new: MorphemeId,
) {
    let mut index =
        std::mem::take(&mut world.groups.main_code_mut(group).phonology.grammar.dominant);
    if index.built && index.concepts == world.registry.concepts.len() {
        index.change(world, concept, old, new);
    } else {
        index = DominantIndex::build(world, group);
    }
    world.groups.main_code_mut(group).phonology.grammar.dominant = index;
    lexemes_reweighed(world, group, [old, new]);
    crate::changes::lexicon::update_rates(world, group, concept, old, new);
}

/// Změní dominantní kořen pojmu kódu a dorovná odvozené pohledy; `false`, když se nic nemění.
pub fn set_dominant(
    world: &mut World,
    group: GroupId,
    concept: ConceptId,
    root: MorphemeId,
) -> bool {
    let state = &mut world.groups.main_code_mut(group).phonology;
    let old = state.dominant_of(concept);
    if !state.set_dominant(concept, root) {
        return false;
    }
    dominant_changed(world, group, concept, old, root);
    true
}

/// Součty četností pojmů podle dominantního kořene kódu: průběžný pohled, nebo (dokud není
/// postavený) výpočet od nuly.
pub fn totals(world: &World, group: GroupId) -> std::borrow::Cow<'_, HashMap<MorphemeId, f64>> {
    let index = &world.groups.main_code(group).phonology.grammar.dominant;
    if index.built {
        std::borrow::Cow::Borrowed(&index.totals)
    } else {
        std::borrow::Cow::Owned(DominantIndex::build(world, group).totals)
    }
}

/// Porovná odvozeniny a součty s výpočtem od nuly.
fn verify_dominant(world: &World, group: GroupId) -> Result<(), String> {
    let code = world.groups.main_code(group);
    let index = &code.phonology.grammar.dominant;
    if !index.built {
        return Err("pohled dominantních kořenů není postavený".into());
    }
    let name = world.group_name(group);
    let fresh = DominantIndex::build(world, group);
    if index.derived != fresh.derived {
        return Err(format!("{name}: odvozeniny se liší od výpočtu od nuly"));
    }
    if index.totals.len() != fresh.totals.len()
        || index
            .totals
            .iter()
            .any(|(k, v)| fresh.totals.get(k).map(|f| f.to_bits()) != Some(v.to_bits()))
    {
        return Err(format!(
            "{name}: součty četností se liší od výpočtu od nuly"
        ));
    }
    verify_sample(world, group)?;
    crate::changes::lexicon::verify_rates(world, group)
}

// --- vzorek nejčastějších slov ------------------------------------------------------------

/// Klíč slova ve vzorku: nejčastější první, shodu rozhodne jméno (pořadí `select`).
#[derive(Clone, Debug)]
struct SampleKey {
    freq: f64,
    name: String,
    unit: MorphemeId,
}

impl PartialEq for SampleKey {
    fn eq(&self, other: &Self) -> bool {
        self.cmp(other).is_eq()
    }
}

impl Eq for SampleKey {}

impl PartialOrd for SampleKey {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(other))
    }
}

impl Ord for SampleKey {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        other
            .freq
            .total_cmp(&self.freq)
            .then_with(|| self.name.cmp(&other.name))
            .then_with(|| self.unit.cmp(&other.unit))
    }
}

/// Slova slovní zásoby kódu seřazená podle četnosti užití (podklad vzorku slov pro hodnocení
/// procesů); upravuje se při vstupu a odchodu slova a při změně součtu četností jeho lexému.
#[derive(Clone, Debug, Default)]
pub struct SampleIndex {
    built: bool,
    /// Lexém → slova jeho tvarů ve slovní zásobě (všechna, ne jen `Word`).
    members: HashMap<MorphemeId, Vec<MorphemeId>>,
    keys: HashMap<MorphemeId, SampleKey>,
    ordered: BTreeSet<SampleKey>,
}

impl SampleIndex {
    pub fn is_built(&self) -> bool {
        self.built
    }

    /// Prvních `limit` slov v pořadí od nejčastějšího: (číslo, četnost).
    pub fn top(&self, limit: usize) -> impl Iterator<Item = (MorphemeId, f64)> + '_ {
        self.ordered.iter().take(limit).map(|k| (k.unit, k.freq))
    }

    fn update(
        &mut self,
        world: &World,
        group: GroupId,
        totals: &HashMap<MorphemeId, f64>,
        unit: MorphemeId,
    ) {
        let code = world.groups.main_code(group);
        let lexeme = world.morphemes.lexeme_id(unit);
        let present = code.phonology.vocabulary.contains(unit);
        let known = self.keys.contains_key(&unit);
        if present && !known {
            self.members.entry(lexeme).or_default().push(unit);
        } else if !present && known {
            if let Some(list) = self.members.get_mut(&lexeme) {
                list.retain(|&u| u != unit);
                if list.is_empty() {
                    self.members.remove(&lexeme);
                }
            }
        }
        let wanted = present.then(|| {
            (
                crate::morphology::usage_frequency(world, totals, unit),
                unit,
            )
        });
        match (self.keys.get(&unit), wanted) {
            (Some(held), Some((freq, _))) if held.freq.to_bits() == freq.to_bits() => {}
            (held, wanted) => {
                if held.is_some() {
                    if let Some(old) = self.keys.remove(&unit) {
                        self.ordered.remove(&old);
                    }
                }
                if let Some((freq, unit)) = wanted {
                    let key = SampleKey {
                        freq,
                        name: world.registry.morphemes.name(unit.0).to_owned(),
                        unit,
                    };
                    self.ordered.insert(key.clone());
                    self.keys.insert(unit, key);
                }
            }
        }
    }

    fn build(world: &World, group: GroupId, totals: &HashMap<MorphemeId, f64>) -> SampleIndex {
        let mut index = SampleIndex::default();
        let units: Vec<MorphemeId> = world
            .groups
            .main_code(group)
            .phonology
            .vocabulary
            .iter()
            .collect();
        for unit in units {
            index.update(world, group, totals, unit);
        }
        index.built = true;
        index
    }
}

/// Slova vstoupila do slovní zásoby kódu nebo ji opustila: dorovná pořadí podle četnosti.
pub fn vocabulary_changed(world: &mut World, group: GroupId, units: &[MorphemeId]) {
    let grammar = &mut world.groups.main_code_mut(group).phonology.grammar;
    let mut index = std::mem::take(&mut grammar.sample);
    let dominant = std::mem::take(&mut grammar.dominant);
    if dominant.built {
        let totals = &dominant.totals;
        if index.built {
            for &unit in units {
                index.update(world, group, totals, unit);
            }
        } else {
            index = SampleIndex::build(world, group, totals);
        }
    }
    let grammar = &mut world.groups.main_code_mut(group).phonology.grammar;
    grammar.sample = index;
    grammar.dominant = dominant;
}

/// Součet četností lexému se změnil: dorovná jeho slova ve vzorku.
fn lexemes_reweighed(world: &mut World, group: GroupId, roots: [MorphemeId; 2]) {
    let grammar = &mut world.groups.main_code_mut(group).phonology.grammar;
    if !grammar.sample.built || !grammar.dominant.built {
        return;
    }
    let mut index = std::mem::take(&mut grammar.sample);
    let dominant = std::mem::take(&mut grammar.dominant);
    for root in roots {
        let units: Vec<MorphemeId> = index.members.get(&root).cloned().unwrap_or_default();
        for unit in units {
            index.update(world, group, &dominant.totals, unit);
        }
    }
    let grammar = &mut world.groups.main_code_mut(group).phonology.grammar;
    grammar.sample = index;
    grammar.dominant = dominant;
}

/// Porovná pořadí vzorku s tříděním od nuly.
fn verify_sample(world: &World, group: GroupId) -> Result<(), String> {
    let grammar = &world.groups.main_code(group).phonology.grammar;
    if !grammar.sample.built {
        return Err("pořadí vzorku není postavené".into());
    }
    let fresh = SampleIndex::build(world, group, &grammar.dominant.totals);
    let held: Vec<(MorphemeId, u64)> = grammar
        .sample
        .ordered
        .iter()
        .map(|k| (k.unit, k.freq.to_bits()))
        .collect();
    let want: Vec<(MorphemeId, u64)> = fresh
        .ordered
        .iter()
        .map(|k| (k.unit, k.freq.to_bits()))
        .collect();
    if held != want {
        return Err(format!(
            "{}: pořadí vzorku se liší od výpočtu od nuly",
            world.group_name(group)
        ));
    }
    Ok(())
}
