//! Povrchový tvar slova: podkladový tvar prohnaný živými procesy (`phonology.surface`).
//!
//! Slovo, které si změnu procesu ještě nezapsalo do podkladového tvaru, ji vyslovuje s pravděpodobností
//! `σ(logit podílu + náskok frekvence + sklon slova)`; je-li aspoň polovina, projde jím. Podkladový
//! tvar je přitom tvar po analogiích, které ve skupině převažují. Gramatika a metriky (délka slova,
//! homofonie, počet hlásek) čtou povrchové tvary; export jazyka (`export::lexicon`) dál čte
//! podkladové tvary jako Python.

use cee_core::bank::Outcome;

use crate::ids::{GroupId, MorphemeId, ProcessId};
use crate::morphology::{apply_form_change, changed_share as morph_share, concept_totals, usage_frequency};
use crate::phonology::columns::bias_value;
use crate::phonology::rows::{changed_share, info_of, resolve_maps, row_of};
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

/// Dominantní povrchový tvar morfému ve skupině. Prochází živé procesy kódu v pořadí jejich
/// vzniku; banka tvarů si zapamatuje mezitvary (proto `&mut World`).
pub fn surface(
    world: &mut World,
    group: GroupId,
    morpheme: MorphemeId,
) -> Result<Vec<i32>, String> {
    if world.table.is_none() {
        return Err("svět nemá tabulku hlásek".into());
    }
    let mut form = analogical(world, group, morpheme);
    let (rule, lead_scale) = (
        world.groups.main_code(group).stress_rule.as_rule(),
        world.params.frequency_lead,
    );
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
        let (variable, changed) = info_of(world, process)?;
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
        let row = row_of(world, process)?;
        let id = i64::from(world.bank.id_of(&form));
        let result = loop {
            match world.bank.bank.results(row, rule, &[id])? {
                Outcome::Done(found) => break found[0],
                Outcome::Needs(segments) => resolve_maps(world, &[(row, segments)])?,
            }
        };
        if result >= 0 {
            form = world.bank.form(result as u32).to_vec();
        }
    }
    Ok(form)
}

/// Pojem → povrchový tvar dominantního slova skupiny, podle jmen pojmů (`phonology.lexicon`).
pub fn surface_lexicon(
    world: &mut World,
    group: GroupId,
) -> Result<Vec<(String, Vec<i32>)>, String> {
    let mut concepts: Vec<(String, MorphemeId)> = world
        .groups
        .main_code(group)
        .phonology
        .dominant
        .iter()
        .enumerate()
        .filter(|(_, root)| !root.is_none())
        .map(|(concept, &root)| (world.registry.concepts.name(concept as u32).to_owned(), root))
        .collect();
    concepts.sort();
    concepts
        .into_iter()
        .map(|(concept, root)| Ok((concept, surface(world, group, root)?)))
        .collect()
}
