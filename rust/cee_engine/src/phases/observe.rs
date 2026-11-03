//! Fáze 6: pozorování dialektů a jazyků (R1d).
//!
//! **Vstup:** `World` (kódy, repertoáry, živé fondy), prahy z `SimulationConfig`,
//! sledování linií (`SocietyState::lineages`). **Výstup:** snímek v `History::snapshots`
//! a události `language_emerged`, `language_split`, `language_ended` v historii.
//! Zrcadlo `observe.observe` (vzdálenosti kódů, shlukování, `LineageTracker`).
//!
//! R0: snímek rozdělí skupiny podle linie jazyka jejich hlavního kódu (každý jazyk je
//! jedno nářečí); vzdálenosti a shlukování přináší R1d.

use std::collections::BTreeMap;

use crate::history::Snapshot;
use crate::phases::StepContext;

/// Zapíše snímek pozorování.
pub fn run(ctx: &mut StepContext<'_>) -> Result<(), String> {
    let world = &*ctx.world;
    let mut languages: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for group in world.group_ids() {
        if world.groups.written[group.index()] {
            continue;
        }
        let language = world
            .registry
            .languages
            .name(world.groups.main_code(group).language.0)
            .to_owned();
        languages
            .entry(language)
            .or_default()
            .push(world.group_name(group).to_owned());
    }
    let dialects = languages.values().cloned().collect();
    ctx.history.snapshots.push(Snapshot {
        tick: ctx.tick,
        year: ctx.year,
        dialects,
        languages,
    });
    Ok(())
}
