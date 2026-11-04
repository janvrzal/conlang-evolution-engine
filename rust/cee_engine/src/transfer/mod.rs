//! Přenos jazyka mezi skupinami a tlaky (R1a): příprava kroku, přenos bloků živých proměnných,
//! tlaky na varianty a události po přenosu. Fázi řídí [`crate::phases::transmission`].
//!
//! | modul | obsah | zrcadlí |
//! |---|---|---|
//! | [`network`] | míšení z vazeb, komponenty, kanály, kohorty, klíče driftu | `transmission.prepare` |
//! | [`factors`] | filtry kanálů podle druhu proměnné, frekvence a domény pojmu | `contact.*_factors`, `institutions.*_factors` |
//! | [`pressures`] | všech 23 tlaků, plán podle druhu proměnné | `cee.v2.pressures` |
//! | [`block`] | přenos bloku (`hear`, tlaky, `settle`) a události z před/po | `transmission.transmit`, `simulation._plan` |
//! | [`seams`] | místa, kde se čte stav jiné oblasti, který zatím chybí | – |

pub mod assessed;
pub mod block;
pub mod factors;
pub mod network;
pub mod pressures;
pub mod seams;

use crate::model::repertoire::VariableKind;
use crate::rng::{stable_id, Part};
use crate::world::World;

/// Dorovná odvozený stav přenosu na aktuální svět: sloupce variant a u sledovaných proměnných
/// (procesy, analogie) číslo varianty „změna“ (`phonology.changed_id`).
pub fn sync(world: &mut World) {
    let mut derived = std::mem::take(&mut world.transfer.derived);
    derived
        .variants
        .sync(&world.variants, &world.registry.variants);
    derived.changed.resize(world.variables.len(), u32::MAX);
    for variable in world.live.variable_ids() {
        let kind = world.variables.kind[variable.index()];
        if derived.changed[variable.index()] != u32::MAX
            || !matches!(kind, VariableKind::Process | VariableKind::Form)
        {
            continue;
        }
        let name = world.registry.variables.name(variable.0);
        let changed = stable_id("variant", &[Part::Str("changed"), Part::Str(name)]);
        if let Some(number) = world.registry.variants.get(&changed) {
            derived.changed[variable.index()] = number;
        }
    }
    world.transfer.derived = derived;
}
