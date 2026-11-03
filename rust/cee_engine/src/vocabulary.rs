//! Slovní zásoba kódů na začátku běhu (zrcadlo `Simulation._seed_vocabulary`).
//!
//! Každý kód dostane jako dominantní slovo pojmu to, které je dominantní v jeho
//! rozdělení lexikální proměnné; do slovní zásoby vstoupí slovo i jeho tvary buněk.

use crate::ids::{GroupId, MorphemeId};
use crate::model::lexicon::unit_name;
use crate::model::repertoire::{Payload, VariableKind};
use crate::world::World;

/// Tvary slova (citační tvar a buňky paradigmatu), které svět už zná.
///
/// Lexém vzniklý až za běhu a výpůjčky dostávají tvary buněk podle produktivních koncovek
/// kódu (`morphology.units_of`); to přináší R1c.
pub fn units_of(world: &World, root: MorphemeId) -> Vec<MorphemeId> {
    let class = world.morphemes.word_class[root.index()];
    let paradigm = if class.is_none() {
        None
    } else {
        world.paradigms.get(class.index()).and_then(Option::as_ref)
    };
    let Some(paradigm) = paradigm else {
        return vec![root];
    };
    let root_name = world.registry.morphemes.name(root.0);
    let citation = world.registry.cells.name(paradigm.citation().0);
    let mut units = vec![root];
    for &cell in &paradigm.cells[1..] {
        let name = unit_name(root_name, world.registry.cells.name(cell.0), citation);
        if let Some(found) = world.registry.morphemes.get(&name) {
            if world.morphemes.contains(MorphemeId(found)) {
                units.push(MorphemeId(found));
            }
        }
    }
    units
}

/// Doplní slovní zásobu jedné skupiny, pokud ji nemá.
pub fn seed_vocabulary(world: &mut World, group: GroupId) -> Result<(), String> {
    if !world
        .groups
        .main_code(group)
        .phonology
        .vocabulary
        .is_empty()
    {
        return Ok(());
    }
    let mut found = Vec::new();
    for number in world.registry.variables.sorted() {
        let variable = crate::ids::VariableId(number);
        if variable.index() >= world.variables.len()
            || world.variables.kind[variable.index()] != VariableKind::Lexical
        {
            continue;
        }
        let Some((dominant, _)) = world.dominant(group, variable) else {
            continue;
        };
        if let Payload::Lexical { morpheme, .. } = &world.variants.payload[dominant.index()] {
            if !morpheme.is_none() {
                found.push((world.variables.concept[variable.index()], *morpheme));
            }
        }
    }
    for (concept, morpheme) in found {
        let units = units_of(world, morpheme);
        let state = &mut world.groups.main_code_mut(group).phonology;
        state.set_dominant(concept, morpheme);
        state.adjust_uses(morpheme, 1, 0);
        for unit in units {
            state.enter_vocabulary(unit);
        }
        state.version += 1;
        state.lexicon_version += 1;
    }
    Ok(())
}

/// Doplní slovní zásobu všech skupin světa.
pub fn seed_vocabulary_all(world: &mut World) -> Result<(), String> {
    for group in world.group_ids() {
        seed_vocabulary(world, group)?;
    }
    Ok(())
}
