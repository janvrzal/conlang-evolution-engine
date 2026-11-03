//! Fáze 1: události světa (R1d).
//!
//! **Vstup:** fronta událostí seřazená podle roku a pořadí zadání, `StepContext`.
//! **Výstup:** svět změněný událostmi, záznamy v historii. Po události se přepočítá
//! osa živých fondů, načtou se proměnné, ve kterých se skupiny liší, a doplní slovní
//! zásoba nových skupin (jako `Simulation._apply_events`).

use std::collections::VecDeque;

use crate::events::WorldEvent;
use crate::phases::StepContext;
use crate::vocabulary::seed_vocabulary_all;

/// Provede všechny události, jejichž rok už nastal; vrací, zda se něco provedlo.
pub fn run(ctx: &mut StepContext<'_>, pending: &mut VecDeque<Box<dyn WorldEvent>>) -> Result<bool, String> {
    let mut applied = false;
    while pending.front().is_some_and(|e| e.year() <= ctx.year) {
        let event = pending.pop_front().expect("událost");
        event.apply(ctx.world, ctx.history, ctx.tick)?;
        applied = true;
    }
    if applied {
        if ctx.config.dt > ctx.world.generation_ceiling() {
            return Err(format!(
                "Krok {} let je delší než nejkratší generace ({} let).",
                ctx.config.dt,
                ctx.world.generation_ceiling()
            ));
        }
        ctx.world.sync_live_groups()?;
        ctx.world.load_differing()?;
        if ctx.world.table.is_some() {
            seed_vocabulary_all(ctx.world)?;
        }
    }
    Ok(applied)
}
