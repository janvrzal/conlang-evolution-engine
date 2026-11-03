//! Fáze 3: přenos jazyka mezi skupinami a tlaky (R1a).
//!
//! **Vstup:** `World.live` (bloky podílů variant), `World.links` (CSR vazby),
//! skupiny (populace, prestiž, otevřenost, obnova), `Parameters`, tlaky změn.
//! **Výstup:** nové podíly variant ve fondech (`PoolBlock::cells`), záznamy
//! `milestone`, `established`, `extinct` v historii, aktivace procesů a analogií
//! (nad prahem `activation_share`), změny dominantních kořenů a slovní zásoby
//! kódů, uvolnění ustálených proměnných do repertoárů.
//!
//! Python (`simulation._transmit`, `transmission.py`, `phases_transmission.py`,
//! `pressures*.py`) staví vstupy kroku (`prepare`), spočítá všechny bloky ze starého
//! stavu (`transmit`: míšení, selekce s tlaky, drift, inkrementace), vytvoří plán událostí
//! a zapíše ho v kanonickém pořadí. Jádra jsou v `cee_core::transmission` (`hear`,
//! `settle`) a `cee_core::pressures`; R1a je napojí na `PoolBlock` a `World`.
//!
//! **R0 dodává** jen rámec: počítadlo kroku a [`release`], které vrací ustálené
//! proměnné do repertoárů skupin (konec `_transmit`), a tak je kostra úplná.

use crate::phases::StepContext;

/// Vrátí ustálené proměnné z fondů do repertoárů skupin.
pub fn release(ctx: &mut StepContext<'_>) {
    let world = &mut *ctx.world;
    let mut live = std::mem::take(&mut world.live);
    let released = live.release(&world.registry.variants);
    let axis = live.group_ids.clone();
    world.live = live;
    for (variable, distributions) in released {
        for (group, distribution) in axis.iter().zip(distributions) {
            if let Some(distribution) = distribution {
                world.groups.main_code_mut(*group).repertoire.set(variable, distribution);
            }
        }
    }
}

/// Provede fázi přenosu (R0: kostra).
pub fn run(ctx: &mut StepContext<'_>) -> Result<(), String> {
    ctx.world.transfer.steps += 1;
    if ctx.world.live.is_empty() {
        return Ok(());
    }
    // TODO(R1a): prepare → transmit po blocích → plán → zápis → aktivace → záznamy.
    release(ctx);
    Ok(())
}
