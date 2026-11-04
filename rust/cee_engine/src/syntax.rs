//! Konstrukce v běžící simulaci (zrcadlo `cee.v2.syntax`).
//!
//! Nic tu není napsané pro konkrétní funkci: vše řídí katalog (`v2_grammar.json`).
//! Konstrukční proměnná se šíří jako každá jiná; navíc jsou tu jen tyto věci:
//!
//! - **slabost syntetického vyjádření**: kolik tvarů buňky paradigmatu zní stejně jako
//!   citační tvar. Funkce bez buňky v jazyce (neexistuje koncovka) má slabost 1;
//! - **síla vyjádření** konstrukce (0 až 1) a **nadbytečnost** (funkce, jejíž roli převzala
//!   jiná, skoro nic neztratí, když zanikne);
//! - **zápis nové koncovky**: když převáží nová syntetická konstrukce, zapíše se do tvarů
//!   slov a buňka paradigmatu, kterou jazyk dosud neměl, vznikne.
//!
//! Katalog je malý (desítky funkcí), proto se tu pracuje po jménech funkcí a řetězcích
//! konstrukcí; horké cesty (míry změn) čtou jen dominantní konstrukci funkce.

use std::sync::Arc;

use serde_json::json;

use crate::grammar::{Catalog, Construction, GrammaticalFunction, Template};
use crate::ids::{CellId, ConceptId, GroupId, MorphemeId, VariableId, VariantId, WordClassId};
use crate::model::forms::UnitForm;
use crate::model::lexicon::{unit_name, MorphemeInit, MorphemeKind, MorphemeMeta};
use crate::model::repertoire::{variable_name, Payload, VariableKind};
use crate::morphology::{self, class_stats};
use crate::phases::StepContext;
use crate::rng::{stable_id, Part};
use crate::world::World;

/// Funkce katalogu s přepisy parametrů světa, seřazené podle jména (kanonické pořadí).
pub fn catalog(world: &World) -> Arc<Vec<GrammaticalFunction>> {
    world.grammar.cache.get_or("catalog", 0, || {
        let mut functions = world
            .grammar_catalog()
            .unwrap_or_else(|_| Catalog::shared().functions.clone());
        functions.sort_by(|a, b| a.id.cmp(&b.id));
        functions
    })
}

/// Funkce katalogu podle jména.
pub fn entry(world: &World, name: &str) -> Option<GrammaticalFunction> {
    let found = catalog(world);
    found
        .binary_search_by(|f| f.id.as_str().cmp(name))
        .ok()
        .map(|at| found[at].clone())
}

/// Konstrukční proměnná funkce, pokud ji svět sleduje.
pub fn variable_of(world: &World, function: &str) -> Option<VariableId> {
    let name = variable_name(VariableKind::Construction, function);
    world
        .registry
        .variables
        .get(&name)
        .filter(|&n| (n as usize) < world.variables.len())
        .map(VariableId)
}

/// Funkce katalogu, které jazykový svět sleduje (mají konstrukční proměnnou), v pořadí jmen.
pub fn functions(world: &World, template: Option<Template>) -> Vec<GrammaticalFunction> {
    catalog(world)
        .iter()
        .filter(|f| template.is_none_or(|t| f.template == t))
        .filter(|f| variable_of(world, &f.id).is_some())
        .cloned()
        .collect()
}

/// Konstrukce z varianty.
pub fn construction_of(world: &World, variant: VariantId) -> Option<&Construction> {
    match world.variants.payload.get(variant.index())? {
        Payload::Construction(construction) => Some(construction),
        _ => None,
    }
}

/// Dominantní konstrukce funkce ve skupině.
pub fn dominant(world: &World, group: GroupId, function: &str) -> Option<Construction> {
    let variable = variable_of(world, function)?;
    let (variant, _) = world.dominant(group, variable)?;
    construction_of(world, variant).cloned()
}

/// Číslo pojmu podle jména (pojem, který registr nezná, žádný kořen mít nemůže).
pub fn concept_of(world: &World, name: &str) -> Option<ConceptId> {
    world.registry.concepts.get(name).map(ConceptId)
}

/// Dominantní kořen pojmu v kódu skupiny.
pub fn dominant_root(world: &World, group: GroupId, concept: ConceptId) -> Option<MorphemeId> {
    world
        .groups
        .main_code(group)
        .phonology
        .dominant_of(concept)
        .option()
}

fn class_of(world: &World, name: Option<&str>) -> Option<WordClassId> {
    world.registry.word_classes.get(name?).map(WordClassId)
}

fn cell_of(world: &World, name: Option<&str>) -> Option<CellId> {
    world.registry.cells.get(name?).map(CellId)
}

/// Slabost syntetického vyjádření funkce (`syntax.weakness`): podíl splynulých tvarů buňky.
///
/// Funkce bez buňky má slabost 0 (neinflexní), funkce s buňkou, ale bez třídy slova, 1.
pub fn weakness(world: &World, group: GroupId, function: &str) -> f64 {
    let Some(found) = entry(world, function) else {
        return 0.0;
    };
    let Some(cell) = found.cell.as_deref() else {
        return 0.0;
    };
    let (Some(class), Some(cell)) = (
        class_of(world, found.word_class()),
        cell_of(world, Some(cell)),
    ) else {
        return 1.0;
    };
    if found.word_class().is_none() {
        return 1.0;
    }
    morphology::cell_weakness(world, group, class, cell)
}

/// Tvar dominantního slova pojmu (zdroj gramatikalizace); prázdný, když pojem slovo nemá.
pub fn particle_form<'a>(world: &'a World, group: GroupId, concept: Option<&str>) -> &'a [i32] {
    let Some(concept) = concept.and_then(|c| concept_of(world, c)) else {
        return &[];
    };
    match dominant_root(world, group, concept) {
        Some(root) => world.form_of(group, root),
        None => &[],
    }
}

/// Ztratilo slovo pojmu zvukovými změnami hlásky? Krátké odjakživa není slabé.
pub fn eroded(world: &World, group: GroupId, concept: Option<&str>) -> bool {
    let Some(concept) = concept.and_then(|c| concept_of(world, c)) else {
        return true;
    };
    let Some(root) = dominant_root(world, group, concept) else {
        return true;
    };
    let original = world.bank.form(world.morphemes.form[root.index()]).len();
    world.form_of(group, root).len() < original
}

/// Zapsala skupina konstrukci do tvarů (nová koncovka)?
pub fn applied(world: &World, group: GroupId, construction: &Construction) -> bool {
    let name = stable_id(
        "variant",
        &[Part::Str("construction"), Part::Str(&construction.key())],
    );
    world.registry.variants.get(&name).is_some_and(|n| {
        world
            .groups
            .main_code(group)
            .phonology
            .grammar
            .grammar_applied
            .contains(&VariantId(n))
    })
}

/// Je výraz vázaný na slovo (koncovka nebo přiklonka)?
pub fn bound(construction: &Construction) -> bool {
    construction.kind == "synthetic"
        || (construction.kind == "periphrastic" && construction.stage.as_deref() == Some("clitic"))
}

/// Nese konstrukce roli funkcí, které její funkce zastupuje (`syntax.carries_role`)?
pub fn carries_role(world: &World, construction: &Construction) -> bool {
    match entry(world, &construction.function) {
        Some(found) if found.template == Template::Order => construction.kind == "fixed",
        _ => construction.kind != "zero",
    }
}

/// Jakou měrou roli funkce přebírají jiné dominantní konstrukce (0 až 1).
pub fn compensation(world: &World, group: GroupId, function: &str) -> f64 {
    let mut found = 0.0_f64;
    for item in catalog(world).iter() {
        if item.compensates.iter().any(|c| c == function) {
            if let Some(current) = dominant(world, group, &item.id) {
                if carries_role(world, &current) {
                    found = found.max(item.coverage);
                }
            }
        }
    }
    found
}

/// Převzala roli funkce jiná konstrukce?
pub fn compensated(world: &World, group: GroupId, function: &str) -> bool {
    compensation(world, group, function) > 0.0
}

/// Jak zřetelně konstrukce svou funkci vyjadřuje (0 až 1; `syntax.strength`).
pub fn strength(
    world: &World,
    group: GroupId,
    construction: &Construction,
    with_compensation: bool,
) -> f64 {
    match construction.kind.as_str() {
        "periphrastic" => 1.0,
        "synthetic" => {
            if construction.exponent.is_some() && !applied(world, group, construction) {
                // Nová koncovka, kterou jazyk ještě nezapsal: zní, jak zněla přiklonka
                // (plně), nebo jako zbytková koncovka dárce.
                return match &construction.donor {
                    None => 1.0,
                    Some(donor) => 1.0 - weakness(world, group, donor),
                };
            }
            1.0 - weakness(world, group, &construction.function)
        }
        "pre" | "embraced" | "post" => {
            let words = [
                construction.source.as_deref(),
                construction.reinforcer.as_deref(),
            ];
            let sounding = words
                .into_iter()
                .flatten()
                .any(|word| !eroded(world, group, Some(word)));
            f64::from(u8::from(sounding))
        }
        "zero" => {
            let context = entry(world, &construction.function).map_or(0.0, |e| e.context);
            let compensated = if with_compensation {
                compensation(world, group, &construction.function)
            } else {
                0.0
            };
            context.max(compensated)
        }
        _ => 0.0,
    }
}

/// Koncovka dárcovské buňky, která ještě zní (je co převzít; `syntax.residual_exponent`).
pub fn residual_exponent(
    world: &World,
    group: GroupId,
    donor: &GrammaticalFunction,
) -> Option<MorphemeId> {
    let class = class_of(world, donor.word_class())?;
    let cell = cell_of(world, donor.cell.as_deref())?;
    let stats = class_stats(world, group);
    let exponent = stats.productive(class, cell)?;
    stats.sounding(exponent).then_some(exponent)
}

/// Koncovka z pomocného slova: srůstáním se zkrátí na první slabiku (`syntax.new_affix`).
pub fn new_affix(
    world: &mut World,
    group: GroupId,
    construction: &Construction,
    tick: u32,
) -> Option<MorphemeId> {
    let table = world.table.clone()?;
    let found = entry(world, &construction.function)?;
    let form = particle_form(world, group, construction.source.as_deref()).to_vec();
    let vowel = form.iter().position(|&s| table.is_vowel(s))?;
    let cell = found.cell.clone()?;
    let reduced = &form[..=vowel];
    let shape = format!(
        "({}{})",
        reduced
            .iter()
            .map(i32::to_string)
            .collect::<Vec<_>>()
            .join(", "),
        if reduced.len() == 1 { "," } else { "" }
    );
    let group_name = world.group_name(group).to_owned();
    let name = stable_id(
        "affix",
        &[
            Part::Str("grammaticalized"),
            Part::Str(&construction.function),
            Part::Str(&group_name),
            Part::Uint(u64::from(tick)),
            Part::Str(&shape),
        ],
    );
    let existing = world
        .registry
        .morphemes
        .get(&name)
        .map(MorphemeId)
        .filter(|&m| world.morphemes.contains(m));
    if let Some(found) = existing {
        return Some(found);
    }
    let class = class_of(world, found.word_class()).unwrap_or(WordClassId::NONE);
    let class_name = found.word_class().unwrap_or("None");
    let cell_id = world.registry.cell(&cell);
    let form_id = world.bank.id_of(reduced);
    let language = world.groups.main_code(group).language;
    let id = world.registry.morpheme(&name);
    world.morphemes.store(
        id,
        MorphemeInit {
            meaning: format!("{class_name}.{cell}"),
            form: form_id,
            frequency: 0.5,
            kind: MorphemeKind::Affix,
            origin_group: group,
            origin_tick: tick,
            word_class: class,
            lexeme: MorphemeId::NONE,
            cell: cell_id,
            exponent: MorphemeId::NONE,
            boundary: -1,
            language,
            meta: MorphemeMeta {
                etymology: Some("grammaticalization".into()),
                sources: vec![construction.source.clone().unwrap_or_default()],
                base: None,
                meaning: String::new(),
            },
        },
    );
    Some(id)
}

/// Buňka paradigmatu vznikne, až ji jazyk poprvé vyjádří koncovkou (`syntax._ensure_cell`).
fn ensure_cell(world: &mut World, class: WordClassId, cell: &str, weight: f64) {
    let id = world.registry.cell(cell);
    if let Some(Some(paradigm)) = world.paradigms.get_mut(class.index()) {
        if !paradigm.cells.contains(&id) {
            paradigm.cells.push(id);
            paradigm.weights.push(weight);
        }
    }
}

/// Nová syntetická konstrukce k zapsání: funkce, varianta a konstrukce.
#[derive(Clone, Debug)]
pub struct Ready {
    pub function: GrammaticalFunction,
    pub variant: VariantId,
    pub construction: Construction,
}

/// Funkce skupiny, jejichž nová syntetická konstrukce převážila a čeká na zápis
/// (`syntax.ready_constructions`). Rozhodnutí čte jen rozdělení proměnných a značku „už
/// zapsáno“ té skupiny; funkce jsou v pořadí jmen.
pub fn ready_constructions(world: &World, group: GroupId) -> Vec<Ready> {
    let mut plan = Vec::new();
    let applied = &world
        .groups
        .main_code(group)
        .phonology
        .grammar
        .grammar_applied;
    for entry in functions(world, Some(Template::Inflection)) {
        let Some(variable) = variable_of(world, &entry.id) else {
            continue;
        };
        let has_paradigm = class_of(world, entry.word_class())
            .is_some_and(|c| world.paradigms.get(c.index()).is_some_and(Option::is_some));
        if !has_paradigm {
            continue;
        }
        let Some((variant, share)) = world.dominant(group, variable) else {
            continue;
        };
        let Some(construction) = construction_of(world, variant) else {
            continue;
        };
        let ready = share >= world.params.grammar_threshold
            && construction.kind == "synthetic"
            && construction.exponent.is_some()
            && !applied.contains(&variant);
        if ready {
            plan.push(Ready {
                function: entry,
                variant,
                construction: construction.clone(),
            });
        }
    }
    plan
}

/// Co se stane s lexémem při zápisu nové koncovky (`phases.ENDING_*`).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Ending {
    Skip,
    Kept,
    FromDonor,
    FromCitation,
}

/// Nová syntetická konstrukce, která převážila, se zapíše do tvarů slov (`syntax.restructure`).
pub fn restructure(ctx: &mut StepContext<'_>, group: GroupId) -> Result<(), String> {
    let ready = ready_constructions(ctx.world, group);
    let group_name = ctx.world.group_name(group).to_owned();
    for item in ready {
        let world = &mut *ctx.world;
        let Ready {
            function,
            variant,
            construction,
        } = item;
        world
            .groups
            .main_code_mut(group)
            .phonology
            .mark_grammar_applied(variant);
        let class = class_of(world, function.word_class()).ok_or("funkce bez třídy slova")?;
        let cell_name = function.cell.clone().ok_or("funkce bez buňky")?;
        ensure_cell(world, class, &cell_name, function.weight);
        let cell = world.registry.cell(&cell_name);
        let paradigm = world.paradigms[class.index()]
            .clone()
            .ok_or("chybí paradigma")?;
        let citation = world.registry.cells.name(paradigm.citation().0).to_owned();
        let donor = construction.donor.as_deref().and_then(|d| entry(world, d));
        let exponent = construction
            .exponent
            .as_deref()
            .and_then(|e| world.registry.morphemes.get(e))
            .map(MorphemeId)
            .ok_or("konstrukce bez koncovky")?;
        let ending = world
            .bank
            .form(world.morphemes.form[exponent.index()])
            .to_vec();
        // Lexémy slovní zásoby kódu příslušné třídy v pořadí jmen.
        let mut roots: Vec<MorphemeId> = {
            let state = &world.groups.main_code(group).phonology;
            let mut found: Vec<MorphemeId> = state
                .vocabulary
                .iter()
                .filter(|u| {
                    matches!(
                        world.morphemes.kind[u.index()],
                        MorphemeKind::Root | MorphemeKind::Word
                    ) && world.morphemes.word_class[u.index()] == class
                })
                .map(|u| world.morphemes.lexeme_id(u))
                .collect();
            found.sort();
            found.dedup();
            found
        };
        roots.sort_by(|a, b| {
            world
                .registry
                .morphemes
                .name(a.0)
                .cmp(world.registry.morphemes.name(b.0))
        });
        let unit_of_cell =
            |world: &World, root: MorphemeId, cell: &str| -> (String, Option<MorphemeId>) {
                let name = unit_name(world.registry.morphemes.name(root.0), cell, &citation);
                let found = world
                    .registry
                    .morphemes
                    .get(&name)
                    .map(MorphemeId)
                    .filter(|&m| world.morphemes.contains(m));
                (name, found)
            };
        let totals = morphology::concept_totals(world, group).into_owned();
        let mut rewritten = 0_u32;
        let mut kept = 0_u32;
        for root in roots {
            let (unit_name_text, unit) = unit_of_cell(world, root, &cell_name);
            let state = &world.groups.main_code(group).phonology;
            let exists = unit.is_some_and(|u| state.vocabulary.contains(u));
            let donor_unit = donor
                .as_ref()
                .and_then(|d| d.cell.as_deref())
                .map(|c| unit_of_cell(world, root, c).1);
            let action = match &donor {
                Some(_) => {
                    let present = donor_unit
                        .flatten()
                        .is_some_and(|u| state.vocabulary.contains(u));
                    let matches = present
                        && donor_unit
                            .flatten()
                            .is_some_and(|u| world.unit_of(group, u).exponent == exponent);
                    if present && matches {
                        Ending::FromDonor
                    } else {
                        Ending::Skip
                    }
                }
                None => {
                    let frequency = if exists {
                        morphology::usage_frequency(world, &totals, root)
                    } else {
                        0.0
                    };
                    if exists && frequency >= world.params.conserved_frequency {
                        Ending::Kept
                    } else {
                        Ending::FromCitation
                    }
                }
            };
            let new = match action {
                Ending::Kept => {
                    kept += 1;
                    continue;
                }
                Ending::Skip => continue,
                Ending::FromDonor => {
                    world.unit_of(group, donor_unit.flatten().ok_or("dárcovský tvar chybí")?)
                }
                Ending::FromCitation => {
                    let citation_form = world.form_of(group, root).to_vec();
                    let mut form = citation_form.clone();
                    form.extend_from_slice(&ending);
                    UnitForm {
                        form: world.bank.id_of(&form),
                        boundary: citation_form.len() as i32,
                        exponent,
                    }
                }
            };
            let unit = match unit {
                Some(found) => found,
                None => {
                    let language = world.morphemes.language[root.index()];
                    let id = world.registry.morpheme(&unit_name_text);
                    world.morphemes.store(
                        id,
                        MorphemeInit {
                            meaning: world.morphemes.meta[root.index()].meaning.clone(),
                            form: new.form,
                            frequency: world.morphemes.frequency[root.index()] * function.weight,
                            kind: MorphemeKind::Word,
                            origin_group: group,
                            origin_tick: ctx.tick,
                            word_class: class,
                            lexeme: root,
                            cell,
                            exponent: new.exponent,
                            boundary: new.boundary,
                            language,
                            meta: MorphemeMeta::default(),
                        },
                    );
                    id
                }
            };
            crate::views::set_form(world, group, unit, new);
            rewritten += 1;
            if exists {
                crate::phonology::requeue_all(world, group, unit)?;
            } else {
                crate::phonology::enter_units(world, group, &[unit])?;
            }
        }
        world.groups.main_code_mut(group).phonology.version += 1;
        let kind = if donor.is_some() {
            "exapted"
        } else {
            "grammaticalized"
        };
        let payload = json!({
            "group": group_name, "function": function.id, "source": construction.source,
            "donor": construction.donor, "words": rewritten, "kept": kept,
        });
        ctx.history.record(kind, ctx.tick, ctx.year, payload);
    }
    Ok(())
}
