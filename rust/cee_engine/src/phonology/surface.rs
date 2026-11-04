//! Povrchový tvar slova: podkladový tvar prohnaný živými procesy (`phonology.surface`).
//!
//! Slovo, které si změnu procesu ještě nezapsalo do podkladového tvaru, ji vyslovuje s pravděpodobností
//! `σ(logit podílu + náskok frekvence + sklon slova)`; je-li aspoň polovina, projde jím. Podkladový
//! tvar je přitom tvar po analogiích, které ve skupině převažují. Gramatika a metriky (délka slova,
//! homofonie, počet hlásek) čtou povrchové tvary; export jazyka (`export::lexicon`) dál čte
//! podkladové tvary jako Python.

use std::collections::BTreeSet;

use cee_core::process::{apply, missing_map, Proc, Scratch};

use crate::ids::{GroupId, MorphemeId, ProcessId, VariableId, VariantId};
use crate::model::lexicon::Operation;
use crate::morphology::{
    apply_form_change, changed_share as morph_share, concept_totals, usage_frequency,
};
use crate::phonology::columns::bias_value;
use crate::phonology::rows::{changed_share, proc_of};
use crate::world::World;

/// `_logit`: logit podílu oříznutého na 0,01 až 0,99.
fn logit(share: f64) -> f64 {
    let share = share.clamp(0.01, 0.99);
    (share / (1.0 - share)).ln()
}

/// Podkladový tvar, nebo analogický tvar, který ve skupině převažuje (`phonology.analogical`).
fn analogical(world: &World, group: GroupId, morpheme: MorphemeId) -> Vec<i32> {
    let unit = world.unit_of(group, morpheme);
    let mut form = world.bank.form(unit.form).to_vec();
    let mut active: Vec<_> = world
        .groups
        .main_code(group)
        .phonology
        .grammar
        .morph_active
        .iter()
        .filter(|(_, target)| *target == morpheme)
        .map(|&(variable, _)| variable)
        .collect();
    active.sort_by(|a, b| {
        world
            .registry
            .variables
            .name(a.0)
            .cmp(world.registry.variables.name(b.0))
    });
    for variable in active {
        if morph_share(world, group, variable) < 0.5 {
            continue;
        }
        if let Some(change) = world.form_changes.get(&variable) {
            if let Some(new) = apply_form_change(world, group, change) {
                form = new.form;
            }
        }
    }
    form
}

/// Proměnná a varianta „změna“ procesu z registru (čistě ze jmen, bez paměti).
fn info_pure(world: &World, process: ProcessId) -> Option<(VariableId, VariantId)> {
    let name = world.registry.processes.name(process.0);
    let variable = world.registry.variables.get(name)?;
    let changed = world
        .registry
        .variants
        .get(&crate::phonology::rows::changed_name(name))?;
    Some((VariableId(variable), VariantId(changed)))
}

/// Proces pro povrchové tvary: masky hlásek a mapy výstupů se doplňují podle potřeby. Banka tvarů
/// se nemění, proto jde povrch počítat ze `&World` (metriky bran čtou svět jen pro čtení).
pub type ProcCache = Vec<Option<Proc>>;

fn apply_local(
    world: &World,
    cache: &mut ProcCache,
    process: ProcessId,
    form: &[i32],
    rule: u8,
) -> Option<Vec<i32>> {
    let table = world.table.as_ref()?;
    let def = world.process(process)?;
    if cache.len() <= process.index() {
        cache.resize_with(process.index() + 1, || None);
    }
    let proc = cache[process.index()].get_or_insert_with(|| proc_of(def, table));
    let mut scratch = Scratch::default();
    loop {
        let mut missing = BTreeSet::new();
        missing_map(
            proc,
            form,
            &table.vowel,
            table.boundary(),
            rule,
            &mut scratch,
            &mut missing,
        );
        if missing.is_empty() {
            break;
        }
        for segment in missing {
            let output = if def.operation == Operation::Tone {
                table.with_tone(segment, def.tone?)
            } else {
                let changes: Vec<(&str, &str)> = def
                    .changes
                    .iter()
                    .map(|(n, v)| (n.as_str(), v.as_str()))
                    .collect();
                table.changed(segment, &changes, &def.allow).ok()?
            };
            proc.map[segment as usize] = output.unwrap_or(-1);
        }
    }
    apply(
        proc,
        form,
        &table.vowel,
        table.boundary(),
        rule,
        &mut scratch,
    )
}

/// Dominantní povrchový tvar morfému ve skupině (živé procesy v pořadí jejich vzniku).
pub fn surface(world: &World, group: GroupId, morpheme: MorphemeId) -> Result<Vec<i32>, String> {
    surface_cached(world, group, morpheme, &mut Vec::new())
}

fn surface_cached(
    world: &World,
    group: GroupId,
    morpheme: MorphemeId,
    cache: &mut ProcCache,
) -> Result<Vec<i32>, String> {
    if world.table.is_none() {
        return Err("svět nemá tabulku hlásek".into());
    }
    let mut form = analogical(world, group, morpheme);
    let rule = world.groups.main_code(group).stress_rule.as_rule();
    let lead_scale = world.params.frequency_lead;
    let live: Vec<(usize, bool)> = {
        let state = &world.groups.main_code(group).phonology.sound.queues.state;
        state
            .live()
            .into_iter()
            .filter(|&at| {
                state.procs[at]
                    .done
                    .get(morpheme.index())
                    .copied()
                    .unwrap_or(0)
                    != 1
            })
            .map(|at| (state.procs[at].number, state.procs[at].reductive))
            .collect()
    };
    if live.is_empty() {
        return Ok(form);
    }
    let lexeme = world.morphemes.lexeme_id(morpheme);
    let frequency = {
        let totals = concept_totals(world, group);
        usage_frequency(world, &totals, lexeme)
    };
    for (number, reductive) in live {
        let process = ProcessId::new(number);
        let (variable, changed) = info_pure(world, process)
            .ok_or_else(|| format!("proces č. {number} nemá proměnnou"))?;
        let share = changed_share(world, group, variable, changed);
        if share <= 0.0 {
            continue;
        }
        let lead = if reductive {
            lead_scale * (2.0 * frequency - 1.0)
        } else {
            0.0
        };
        let value = logit(share) + lead + bias_value(world, number, lexeme.index());
        if 1.0 / (1.0 + (-value).exp()) < 0.5 {
            continue;
        }
        if let Some(changed) = apply_local(world, cache, process, &form, rule) {
            form = changed;
        }
    }
    Ok(form)
}

/// Pojem → povrchový tvar dominantního slova skupiny, podle jmen pojmů (`phonology.lexicon`).
pub fn surface_lexicon(world: &World, group: GroupId) -> Result<Vec<(String, Vec<i32>)>, String> {
    let mut concepts: Vec<(String, MorphemeId)> = world
        .groups
        .main_code(group)
        .phonology
        .dominant
        .iter()
        .enumerate()
        .filter(|(_, root)| !root.is_none())
        .map(|(concept, &root)| {
            (
                world.registry.concepts.name(concept as u32).to_owned(),
                root,
            )
        })
        .collect();
    concepts.sort();
    let mut cache = Vec::new();
    concepts
        .into_iter()
        .map(|(concept, root)| Ok((concept, surface_cached(world, group, root, &mut cache)?)))
        .collect()
}
