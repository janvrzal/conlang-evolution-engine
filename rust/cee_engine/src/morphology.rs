//! Morfologie v běžící simulaci: tvary paradigmatu a analogie (zrcadlo `cee.v2.morphology`).
//!
//! Zvukové změny pracují s celými tvary slov, takže alomorfie, eroze koncovek i
//! synkretismus vznikají samy. Tady jsou jen dvě věci navíc:
//!
//! - **Produktivita**: která koncovka je pro danou buňku třídy nejčastější (podle počtu
//!   lexémů, ne tokenů). Nové slovo dostane produktivní koncovku ([`class_stats`]).
//! - **Analogie**: varianta tvaru jedné buňky (vyrovnání kmene, rozšíření koncovky,
//!   přesun hranice) se šíří jako každá jiná. Když ve skupině převáží, nová generace si
//!   tvar zapíše a změna se uzavře ([`restructure`]).
//!
//! **Návrh.** Pohledy odvozené ze stavu kódu (koncovky tříd, kandidáti vyrovnání a
//! rozšíření, slabost buněk) jsou v keši kódu podle jeho verze ([`code_version`]); čtou je
//! souběžné fáze, proto jsou neměnné (`Arc`). Čísla morfémů, tříd a buněk jsou z registru,
//! jména se berou jen tam, kde určují pořadí (kandidáti se řadí podle jména formové
//! proměnné jako v Pythonu) nebo ID nových entit. Jádra `cee_core::form_restructure` a
//! `form_assess` zůstávají pro R2 (jsou psaná pro volání z Pythonu a drží vlastní index
//! kódu synchronizovaný přes deníky); tady je totéž přímo nad stavem kódu, protože
//! přestavby jsou řídké (jen analogie, která ve skupině převážila).
//!
//! **Fonologie (R1b).** Zařazení přepsaného tvaru do front fonologizace
//! (`phonology::requeue_all`) a vstup tvaru do slovní zásoby (`phonology::enter_units`) volá
//! morfologie a syntax přímo; dočasné náhrady z R1c odpadly.

use std::collections::{BTreeMap, HashMap};
use std::sync::Arc;

use serde_json::json;

use crate::ids::{CellId, GroupId, MorphemeId, VariableId, VariantId, WordClassId};
use crate::model::code::Code;
use crate::model::forms::UnitForm;
use crate::model::lexicon::{
    unit_name, FormChange, FormOperation, MorphemeInit, MorphemeKind, MorphemeMeta,
};
use crate::model::repertoire::{variable_name, Origin, Payload, VariableKind};
use crate::phases::StepContext;
use crate::rng::{stable_id, Part};
use crate::world::World;

/// Verze stavu kódu, ze které jsou odvozené pohledy; roste s každou změnou tvarů, slovní
/// zásoby a dominantních kořenů.
pub fn code_version(code: &Code) -> u64 {
    code.forms.version
        + code.phonology.version
        + code.phonology.lexicon_version
        + code.phonology.vocabulary_log.len() as u64
        + code.phonology.dominant_log.len() as u64
}

/// Rozdělení tvaru na kmen a koncovku (`UnitForm.stem`, `ending`); hranice −1 = bez koncovky.
pub fn split(form: &[i32], boundary: i32) -> (&[i32], &[i32]) {
    if boundary < 0 {
        (form, &[])
    } else {
        let at = (boundary as usize).min(form.len());
        (&form[..at], &form[at..])
    }
}

/// Nový stav tvaru slova (tvar jako hlásky, hranice koncovky, koncovka).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct NewUnit {
    pub form: Vec<i32>,
    pub boundary: i32,
    pub exponent: MorphemeId,
}

// --- koncovky tříd ---------------------------------------------------------------------

/// Kolik lexémů nese kterou koncovku a jak ta koncovka dnes zní (`morphology.ClassStats`).
#[derive(Debug, Default)]
pub struct ClassStats {
    /// (třída, buňka) → koncovka → počet lexémů; koncovky v pořadí jmen.
    exponents: BTreeMap<(WordClassId, CellId), Vec<(MorphemeId, u32)>>,
    /// Koncovka → nejčastější dnešní podoba koncovky.
    endings: BTreeMap<MorphemeId, Vec<i32>>,
}

impl ClassStats {
    /// Nejčastější koncovka buňky (shodu rozhodne první ve jménech).
    pub fn productive(&self, class: WordClassId, cell: CellId) -> Option<MorphemeId> {
        let counts = self.exponents.get(&(class, cell))?;
        let mut best: Option<(MorphemeId, u32)> = None;
        for &(exponent, count) in counts {
            if best.is_none_or(|(_, held)| count > held) {
                best = Some((exponent, count));
            }
        }
        best.map(|(exponent, _)| exponent)
    }

    /// Podíl lexémů buňky, které nesou koncovku `exponent`.
    pub fn share(&self, class: WordClassId, cell: CellId, exponent: MorphemeId) -> f64 {
        let Some(counts) = self.exponents.get(&(class, cell)) else {
            return 0.0;
        };
        if counts.is_empty() || exponent.is_none() {
            return 0.0;
        }
        let total: u32 = counts.iter().map(|c| c.1).sum();
        let own = counts.iter().find(|c| c.0 == exponent).map_or(0, |c| c.1);
        f64::from(own) / f64::from(total)
    }

    /// Dnešní podoba koncovky (`None` = koncovka v kódu není).
    pub fn ending(&self, exponent: MorphemeId) -> Option<&[i32]> {
        self.endings.get(&exponent).map(Vec::as_slice)
    }

    /// Koncovka s neprázdnou podobou (prázdná koncovka v Pythonu neplatí).
    pub fn sounding(&self, exponent: MorphemeId) -> bool {
        self.ending(exponent).is_some_and(|e| !e.is_empty())
    }
}

/// Tvary slov ve slovní zásobě kódu (kind `Word`), v pořadí čísel.
fn word_units(world: &World, group: GroupId) -> Vec<MorphemeId> {
    let code = world.groups.main_code(group);
    code.phonology
        .vocabulary
        .iter()
        .filter(|&unit| world.morphemes.kind[unit.index()] == MorphemeKind::Word)
        .collect()
}

/// Citační tvar lexému tvaru slova (číslo tvaru v bance).
pub(crate) fn citation_id(world: &World, group: GroupId, unit: MorphemeId) -> u32 {
    world.unit_of(group, world.morphemes.lexeme_id(unit)).form
}

/// Počty koncovek kódu (pohled `morphology.class_stats`).
pub fn class_stats(world: &World, group: GroupId) -> Arc<ClassStats> {
    let code = world.groups.main_code(group);
    code.phonology
        .grammar
        .cache
        .get_or("class-stats", code_version(code), || {
            let mut counts: HashMap<(WordClassId, CellId), HashMap<MorphemeId, u32>> =
                HashMap::new();
            let mut shapes: HashMap<MorphemeId, BTreeMap<Vec<i32>, u32>> = HashMap::new();
            for unit in word_units(world, group) {
                let class = world.morphemes.word_class[unit.index()];
                let cell = world.morphemes.cell[unit.index()];
                if class.is_none() || cell.is_none() {
                    continue;
                }
                let state = world.unit_of(group, unit);
                if state.exponent.is_none() {
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
            let exponents = counts
                .into_iter()
                .map(|(key, held)| {
                    let mut items: Vec<(MorphemeId, u32)> = held.into_iter().collect();
                    items.sort_by(|a, b| names.name(a.0 .0).cmp(names.name(b.0 .0)));
                    (key, items)
                })
                .collect();
            let endings = shapes
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
            ClassStats { exponents, endings }
        })
}

/// Podíl tvarů buňky, které splynuly s citačním tvarem (`syntax._weakness_reference`).
pub fn cell_weakness(world: &World, group: GroupId, class: WordClassId, cell: CellId) -> f64 {
    let code = world.groups.main_code(group);
    let table = code
        .phonology
        .grammar
        .cache
        .get_or("weakness", code_version(code), || {
            let mut counts: HashMap<(WordClassId, CellId), (u32, u32)> = HashMap::new();
            for unit in word_units(world, group) {
                let class = world.morphemes.word_class[unit.index()];
                let cell = world.morphemes.cell[unit.index()];
                let entry = counts.entry((class, cell)).or_insert((0, 0));
                entry.1 += 1;
                if world.unit_of(group, unit).form == citation_id(world, group, unit) {
                    entry.0 += 1;
                }
            }
            counts
        });
    match table.get(&(class, cell)) {
        Some(&(merged, total)) if total > 0 => f64::from(merged) / f64::from(total),
        _ => 1.0,
    }
}

// --- místa analogických změn --------------------------------------------------------------

/// Kandidáti formové změny kódu seřazení podle jména formové proměnné (jako v Pythonu).
#[derive(Debug, Default)]
pub struct FormSites {
    pub changes: Vec<FormChange>,
    pub keys: Vec<String>,
}

impl FormSites {
    fn from(world: &World, mut found: Vec<FormChange>) -> FormSites {
        let names = &world.registry.morphemes;
        let mut keyed: Vec<(String, FormChange)> = found
            .drain(..)
            .map(|c| (variable_name(VariableKind::Form, &c.key(names)), c))
            .collect();
        keyed.sort_by(|a, b| a.0.cmp(&b.0));
        FormSites {
            keys: keyed.iter().map(|k| k.0.clone()).collect(),
            changes: keyed.into_iter().map(|k| k.1).collect(),
        }
    }

    pub fn len(&self) -> usize {
        self.changes.len()
    }

    pub fn is_empty(&self) -> bool {
        self.changes.is_empty()
    }
}

/// Aktivní morfologie: svět má hláskové tvary a paradigmata.
pub fn active(world: &World) -> bool {
    world.table.is_some() && world.paradigms.iter().any(Option::is_some)
}

/// Vyrovnání: tvar buňky s kmenem jiným než citační tvar.
pub fn leveling_sites(world: &World, group: GroupId) -> Arc<FormSites> {
    let code = world.groups.main_code(group);
    code.phonology
        .grammar
        .cache
        .get_or("level-sites", code_version(code), || {
            let mut found = Vec::new();
            for unit in word_units(world, group) {
                let state = world.unit_of(group, unit);
                let form = world.bank.form(state.form);
                let (stem, _) = split(form, state.boundary);
                let citation = world.bank.form(citation_id(world, group, unit));
                if stem != citation {
                    found.push(FormChange {
                        operation: FormOperation::Level,
                        unit,
                        exponent: MorphemeId::NONE,
                        segment: None,
                    });
                }
            }
            FormSites::from(world, found)
        })
}

/// Rozšíření vzoru: buňka s menšinovou koncovkou, nebo splynulá s citačním tvarem.
pub fn extension_sites(world: &World, group: GroupId) -> Arc<FormSites> {
    let code = world.groups.main_code(group);
    let stats = class_stats(world, group);
    code.phonology
        .grammar
        .cache
        .get_or("extension-sites", code_version(code), || {
            let mut found = Vec::new();
            for unit in word_units(world, group) {
                let class = world.morphemes.word_class[unit.index()];
                let cell = world.morphemes.cell[unit.index()];
                if class.is_none() || cell.is_none() {
                    continue;
                }
                let Some(productive) = stats.productive(class, cell) else {
                    continue;
                };
                if !stats.sounding(productive) {
                    continue;
                }
                let current = world.unit_of(group, unit);
                let syncretic = current.form == citation_id(world, group, unit);
                if current.exponent != productive || syncretic {
                    found.push(FormChange {
                        operation: FormOperation::Extend,
                        unit,
                        exponent: productive,
                        segment: None,
                    });
                }
            }
            FormSites::from(world, found)
        })
}

/// Reanalýza hranice mezi záporkou a slovesem (`Rebracketing.candidates`). Závisí na rozdělení
/// konstrukcí, proto se nekešuje.
pub fn rebracketing_sites(world: &World, group: GroupId) -> FormSites {
    let Some(table) = world.table.as_ref() else {
        return FormSites::default();
    };
    // Záporka před slovesem: dominantní konstrukce `pre` první záporkové funkce.
    let negation = crate::syntax::functions(world, Some(crate::grammar::Template::Negation))
        .into_iter()
        .filter_map(|entry| crate::syntax::dominant(world, group, &entry.id))
        .find(|c| c.kind == "pre");
    let Some(negation) = negation else {
        return FormSites::default();
    };
    let particle = crate::syntax::particle_form(world, group, negation.source.as_deref());
    let Some(&last) = particle.last() else {
        return FormSites::default();
    };
    let code = world.groups.main_code(group);
    let verb = world.registry.word_classes.get("verb").map(WordClassId);
    let mut roots: Vec<MorphemeId> = code
        .phonology
        .dominant
        .iter()
        .copied()
        .filter(|root| !root.is_none() && Some(world.morphemes.word_class[root.index()]) == verb)
        .collect();
    roots.sort();
    roots.dedup();
    let mut found = Vec::new();
    for root in roots {
        let form = world.form_of(group, root);
        let Some(&first) = form.first() else { continue };
        let (operation, segment) = if !table.is_vowel(last) && table.is_vowel(first) {
            (FormOperation::Prepend, last)
        } else if table.is_vowel(last) && !table.is_vowel(first) && form.len() >= 3 {
            (FormOperation::DropInitial, first)
        } else {
            continue;
        };
        found.push(FormChange {
            operation,
            unit: root,
            exponent: MorphemeId::NONE,
            segment: Some(segment),
        });
    }
    FormSites::from(world, found)
}

// --- registrace a použití změny tvaru ---------------------------------------------------------

/// ID varianty „beze změny“ formové (nebo procesní) proměnné.
pub fn none_name(variable: &str) -> String {
    stable_id("variant", &[Part::Str("none"), Part::Str(variable)])
}

/// ID varianty „změna“ formové proměnné.
pub fn changed_name(variable: &str) -> String {
    stable_id("variant", &[Part::Str("changed"), Part::Str(variable)])
}

/// Formová proměnná analogické změny; tatáž změna = tatáž proměnná (`morphology.register`).
pub fn register(
    world: &mut World,
    change: &FormChange,
    origin: &Origin,
) -> (VariableId, VariantId) {
    let key = change.key(&world.registry.morphemes);
    let name = variable_name(VariableKind::Form, &key);
    let known = world
        .registry
        .variables
        .get(&name)
        .filter(|&n| (n as usize) < world.variables.len());
    let variable = match known {
        Some(found) => VariableId(found),
        None => {
            let id = world.registry.variable(&name);
            let none = world.store_variant(
                &none_name(&name),
                id,
                Payload::Other(json!({ "form": null })),
                Origin {
                    change: None,
                    tick: origin.tick,
                    year: origin.year,
                    group: GroupId::NONE,
                    parent: VariantId::NONE,
                },
            );
            world.store_variant(
                &changed_name(&name),
                id,
                Payload::Other(json!({ "form": name })),
                origin.clone(),
            );
            world.store_variable(VariableKind::Form, &key, none);
            world.form_changes.insert(id, change.clone());
            world.grammar.form_variables += 1;
            id
        }
    };
    let changed = world
        .registry
        .variants
        .get(&changed_name(&name))
        .map(VariantId)
        .expect("varianta změny je zaregistrovaná");
    (variable, changed)
}

/// Nový stav tvaru po přesunu hranice (`morphology.rebracket`); `None`, když se nic nemění.
pub fn rebracket(
    form: &[i32],
    boundary: i32,
    exponent: MorphemeId,
    operation: FormOperation,
    segment: i32,
) -> Option<NewUnit> {
    match operation {
        FormOperation::Prepend => {
            let mut next = Vec::with_capacity(form.len() + 1);
            next.push(segment);
            next.extend_from_slice(form);
            Some(NewUnit {
                form: next,
                boundary: if boundary < 0 { -1 } else { boundary + 1 },
                exponent,
            })
        }
        _ => {
            if form.first() != Some(&segment) || form.len() < 3 {
                return None;
            }
            Some(NewUnit {
                form: form[1..].to_vec(),
                boundary: if boundary < 0 { -1 } else { boundary - 1 },
                exponent,
            })
        }
    }
}

/// Analogický tvar podle dnešního stavu kódu, nebo `None`, když nic nezmění
/// (`morphology.apply_form_change`).
pub fn apply_form_change(world: &World, group: GroupId, change: &FormChange) -> Option<NewUnit> {
    let state = world.unit_of(group, change.unit);
    let form = world.bank.form(state.form);
    if change.operation.lexeme_wide() {
        return rebracket(
            form,
            state.boundary,
            state.exponent,
            change.operation,
            change.segment?,
        );
    }
    let (stem, ending) = split(form, state.boundary);
    if change.operation == FormOperation::Level {
        let citation = world.bank.form(citation_id(world, group, change.unit));
        if stem == citation {
            return None;
        }
        let mut next = citation.to_vec();
        next.extend_from_slice(ending);
        return Some(NewUnit {
            form: next,
            boundary: citation.len() as i32,
            exponent: state.exponent,
        });
    }
    let stats = class_stats(world, group);
    let target = stats.ending(change.exponent)?;
    if state.exponent == change.exponent && ending == target {
        return None;
    }
    let mut next = stem.to_vec();
    next.extend_from_slice(target);
    Some(NewUnit {
        form: next,
        boundary: stem.len() as i32,
        exponent: change.exponent,
    })
}

/// Aktivace analogie v kódu (`morphology.activate`): změna se zařadí mezi živé.
pub fn activate(world: &mut World, group: GroupId, variable: VariableId) {
    let Some(unit) = world.form_changes.get(&variable).map(|c| c.unit) else {
        return;
    };
    let state = &mut world.groups.main_code_mut(group).phonology.grammar;
    if !state.morph_closed.contains(&variable)
        && !state.morph_active.iter().any(|(v, _)| *v == variable)
    {
        state.morph_active.push((variable, unit));
    }
}

/// Co se stane s živou analogií podle podílu změněného tvaru (`phases.ANALOGY_*`).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Decision {
    Wait,
    Remove,
    Apply,
}

/// Rozhodnutí podle podílu a prahu (`phases.analogy_decisions`).
pub fn decide(share: f64, threshold: f64) -> Decision {
    if share <= 0.0 {
        Decision::Remove
    } else if share < threshold {
        Decision::Wait
    } else {
        Decision::Apply
    }
}

/// Podíl změněné varianty formové proměnné ve skupině (`phonology.changed_share`).
pub fn changed_share(world: &World, group: GroupId, variable: VariableId) -> f64 {
    let name = world.registry.variables.name(variable.0);
    let Some(changed) = world
        .registry
        .variants
        .get(&changed_name(name))
        .map(VariantId)
    else {
        return 0.0;
    };
    if world.live.contains(variable) && world.live.column(group).is_some() {
        return world
            .live
            .frequency(group, variable, changed)
            .unwrap_or(0.0);
    }
    world
        .stored(group, variable)
        .map_or(0.0, |d| d.frequency(changed))
}

/// Živá analogie skupiny: (proměnná, tvar slova, rozhodnutí).
pub type AnalogyPlan = Vec<(VariableId, MorphemeId, Decision)>;

/// Rozhodnutí o živých analogiích skupiny v pořadí jmen proměnných (`morphology.analogy_plan`).
pub fn analogy_plan(world: &World, group: GroupId) -> AnalogyPlan {
    let mut items = world
        .groups
        .main_code(group)
        .phonology
        .grammar
        .morph_active
        .clone();
    items.sort_by(|a, b| {
        world
            .registry
            .variables
            .name(a.0 .0)
            .cmp(world.registry.variables.name(b.0 .0))
    });
    let threshold = world.params.analogy_threshold;
    items
        .into_iter()
        .map(|(variable, unit)| {
            (
                variable,
                unit,
                decide(changed_share(world, group, variable), threshold),
            )
        })
        .collect()
}

// --- tvary slova nového lexému ----------------------------------------------------------------

/// Založí morfém tvaru slova (buňku paradigmatu lexému) s výchozí podobou `form`.
#[allow(clippy::too_many_arguments)]
fn make_unit(
    world: &mut World,
    name: &str,
    root: MorphemeId,
    cell: CellId,
    exponent: MorphemeId,
    form: &[i32],
    boundary: i32,
    weight: f64,
) -> MorphemeId {
    let form_id = world.bank.id_of(form);
    let id = world.registry.morpheme(name);
    let class = world.morphemes.word_class[root.index()];
    let init = MorphemeInit {
        meaning: world.morphemes.meta[root.index()].meaning.clone(),
        form: form_id,
        frequency: world.morphemes.frequency[root.index()] * weight,
        kind: MorphemeKind::Word,
        origin_group: world.morphemes.origin_group[root.index()],
        origin_tick: world.morphemes.origin_tick[root.index()],
        word_class: class,
        lexeme: root,
        cell,
        exponent,
        boundary,
        language: world.morphemes.language[root.index()],
        meta: MorphemeMeta::default(),
    };
    world.morphemes.store(id, init);
    id
}

/// Tvary slova (citační tvar a buňky paradigmatu) lexému v kódu (`morphology.units_of`).
///
/// Lexém, který vznikl až během simulace, dostane tvary buněk podle produktivní koncovky
/// kódu, kde je poprvé potřeba. Výpůjčka (kořen jiné linie jazyka) dostane v kódu jen buňky,
/// které kód má, a to s jeho produktivními koncovkami, ne s koncovkami dárce.
pub fn units_of(world: &mut World, group: GroupId, root: MorphemeId) -> Vec<MorphemeId> {
    let class = world.morphemes.word_class[root.index()];
    let Some(paradigm) = (!class.is_none())
        .then(|| world.paradigms.get(class.index()).cloned().flatten())
        .flatten()
    else {
        return vec![root];
    };
    let loan = world.morphemes.language[root.index()] != world.groups.main_code(group).language;
    let root_name = world.registry.morphemes.name(root.0).to_owned();
    let citation = world.registry.cells.name(paradigm.citation().0).to_owned();
    let mut result = vec![root];
    for (at, &cell) in paradigm.cells.iter().enumerate().skip(1) {
        let name = unit_name(&root_name, world.registry.cells.name(cell.0), &citation);
        let existing = world
            .registry
            .morphemes
            .get(&name)
            .map(MorphemeId)
            .filter(|&m| world.morphemes.contains(m));
        let stats = class_stats(world, group);
        let Some(exponent) = stats.productive(class, cell) else {
            if let (false, Some(found)) = (loan, existing) {
                result.push(found);
            }
            continue;
        };
        let ending = match stats.ending(exponent) {
            Some(ending) => ending.to_vec(),
            None => world
                .bank
                .form(world.morphemes.form[exponent.index()])
                .to_vec(),
        };
        let stem = world.form_of(group, root).to_vec();
        if loan {
            let missing = world
                .groups
                .main_code(group)
                .forms
                .get(existing.unwrap_or(MorphemeId::NONE))
                .is_none()
                || existing.is_none();
            if missing {
                let unit = match existing {
                    Some(found) => found,
                    None => make_unit(
                        world,
                        &name,
                        root,
                        cell,
                        exponent,
                        &[stem.clone(), ending.clone()].concat(),
                        stem.len() as i32,
                        paradigm.weights[at],
                    ),
                };
                let mut form = stem.clone();
                form.extend_from_slice(&ending);
                let form_id = world.bank.id_of(&form);
                world.groups.main_code_mut(group).forms.set(
                    unit,
                    UnitForm {
                        form: form_id,
                        boundary: stem.len() as i32,
                        exponent,
                    },
                );
                result.push(unit);
            } else {
                result.push(existing.expect("tvar slova"));
            }
        } else {
            let unit = match existing {
                Some(found) => found,
                None => make_unit(
                    world,
                    &name,
                    root,
                    cell,
                    exponent,
                    &[stem.clone(), ending.clone()].concat(),
                    stem.len() as i32,
                    paradigm.weights[at],
                ),
            };
            result.push(unit);
        }
    }
    result
}

// --- přestavba ---------------------------------------------------------------------------

/// Analogie, která ve skupině převážila, se zapíše do tvaru slova (`morphology.restructure`).
pub fn restructure(ctx: &mut StepContext<'_>, group: GroupId) -> Result<(), String> {
    if ctx
        .world
        .groups
        .main_code(group)
        .phonology
        .grammar
        .morph_active
        .is_empty()
    {
        return Ok(());
    }
    let plan = analogy_plan(ctx.world, group);
    let group_name = ctx.world.group_name(group).to_owned();
    for (variable, unit, decision) in plan {
        let world = &mut *ctx.world;
        let state = &mut world.groups.main_code_mut(group).phonology.grammar;
        match decision {
            Decision::Remove => {
                state.morph_active.retain(|(v, _)| *v != variable);
                continue;
            }
            Decision::Wait => continue,
            Decision::Apply => {}
        }
        let change = world
            .form_changes
            .get(&variable)
            .cloned()
            .ok_or("živá analogie bez zaregistrované změny")?;
        let state = &mut world.groups.main_code_mut(group).phonology.grammar;
        state.morph_active.retain(|(v, _)| *v != variable);
        state.morph_closed.insert(variable);
        let targets = if change.operation.lexeme_wide() {
            units_of(world, group, unit)
        } else {
            vec![unit]
        };
        let mut rewritten = false;
        for target in targets {
            let new = if change.operation.lexeme_wide() {
                let current = world.unit_of(group, target);
                match change.segment {
                    Some(segment) => rebracket(
                        world.bank.form(current.form),
                        current.boundary,
                        current.exponent,
                        change.operation,
                        segment,
                    ),
                    None => None,
                }
            } else {
                apply_form_change(world, group, &change)
            };
            let Some(new) = new else { continue };
            let form = world.bank.id_of(&new.form);
            world.groups.main_code_mut(group).forms.set(
                target,
                UnitForm {
                    form,
                    boundary: new.boundary,
                    exponent: new.exponent,
                },
            );
            rewritten = true;
            crate::phonology::requeue_all(world, group, target)?;
        }
        if !rewritten {
            continue;
        }
        world.groups.main_code_mut(group).phonology.version += 1;
        let meaning = world.morphemes.meta[unit.index()].meaning.clone();
        let cell = world.morphemes.cell[unit.index()];
        let cell_name = if cell.is_none() {
            serde_json::Value::Null
        } else {
            json!(world.registry.cells.name(cell.0))
        };
        let payload = json!({
            "group": group_name,
            "variable": world.registry.variables.name(variable.0),
            "operation": change.operation.name(),
            "concept": meaning,
            "cell": cell_name,
        });
        ctx.history.record("analogy", ctx.tick, ctx.year, payload);
    }
    Ok(())
}

// --- četnost užití tvarů --------------------------------------------------------------------

/// Součet četností pojmů, které vyjadřuje dominantní kořen (kořen → součet), pro jeden kód.
pub fn concept_totals(world: &World, group: GroupId) -> HashMap<MorphemeId, f64> {
    let code = world.groups.main_code(group);
    let mut totals: HashMap<MorphemeId, f64> = HashMap::new();
    for (at, &root) in code.phonology.dominant.iter().enumerate() {
        if root.is_none() {
            continue;
        }
        *totals.entry(root).or_insert(0.0) +=
            world.concepts.frequency_of(crate::ids::ConceptId::new(at));
    }
    totals
}

/// Jak často kód tvar užívá (`world.usage_frequency`): součet četností pojmů, které vyjadřuje;
/// tvar buňky má navíc váhu své buňky. Bez dominantních pojmů platí statická frekvence morfému.
pub fn usage_frequency(
    world: &World,
    totals: &HashMap<MorphemeId, f64>,
    morpheme: MorphemeId,
) -> f64 {
    let lexeme = world.morphemes.lexeme_id(morpheme);
    let Some(&sum) = totals.get(&lexeme) else {
        return world.morphemes.frequency[morpheme.index()];
    };
    let mut total = sum.min(1.0);
    let class = world.morphemes.word_class[morpheme.index()];
    let cell = world.morphemes.cell[morpheme.index()];
    if world.morphemes.kind[morpheme.index()] == MorphemeKind::Word
        && !class.is_none()
        && !cell.is_none()
    {
        if let Some(Some(paradigm)) = world.paradigms.get(class.index()) {
            if let Some(weight) = paradigm.weight(cell) {
                total *= weight;
            }
        }
    }
    total
}
