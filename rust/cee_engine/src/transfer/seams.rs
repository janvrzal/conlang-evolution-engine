//! Místa, kde přenos čte stav jiné oblasti enginu a ten zatím není ve společném datovém modelu.
//!
//! Funkce tu mají pevný podpis a nejjednodušší správné tělo; až vlastník oblasti stav doplní,
//! změní se jen tělo (R2 při slučování). Každá je popsaná tím, co od druhé oblasti čekám.

use crate::ids::{GroupId, VariableId};
use crate::model::repertoire::VariableKind;
use crate::world::World;

/// Uzavřela si skupina zvukovou změnu do podkladových tvarů (`PhonologyState.closed`)?
///
/// Tlak `Norm` zvukovou změnu, kterou už si kód uzavřel do tvarů slov, nevrací zpět. Uzavřený je
/// proces, který kód zná a jehož fronta už není živá (`SoundCodeState::queues`); analogie
/// a ostatní proměnné se v Pythonu do `closed` nezapisují, norma na ně působí vždy.
pub fn closed(world: &World, group: GroupId, variable: VariableId) -> bool {
    if world.variables.kind.get(variable.index()) != Some(&VariableKind::Process) {
        return false;
    }
    let process = world.variables.process[variable.index()];
    if process.is_none() {
        return false;
    }
    world
        .groups
        .main_code(group)
        .phonology
        .sound
        .queues
        .state
        .find(process.index())
        .is_some_and(|at| {
            !world
                .groups
                .main_code(group)
                .phonology
                .sound
                .queues
                .state
                .procs[at]
                .live
        })
}

/// Hodnocení změny (procesu či analogie) ve skupinách `columns` (sloupce osy), kam dolehla.
///
/// Pro proměnnou druhu `Process` jsou hodnoty `[pokrytí, splynutí, krátká slova, příznakovost,
/// rozptyl vokálů]` (`assessment.ProcessAssessment`), pro druh `Form` `[zisk, frekvence,
/// splynutí před, splynutí po, 0]` (`morphology.FormAssessment`; `None` = změna by tvar
/// nezměnila). Hodnocení procesů spočítá a uloží [`crate::transfer::assess::refresh`] před
/// přenosem (mění banku tvarů), tady se jen čtou; hodnocení tvarů se počítá rovnou.
pub fn assess_cells(
    world: &World,
    variable: VariableId,
    columns: &[usize],
    _tick: u32,
) -> Vec<Option<crate::transfer::assessed::Assessment>> {
    match world.variables.kind.get(variable.index()) {
        Some(VariableKind::Process) => {
            crate::transfer::assess::process_cells(world, variable, columns)
        }
        Some(VariableKind::Form) => crate::transfer::assess::form_cells(world, variable, columns),
        _ => vec![None; columns.len()],
    }
}

/// Podíl slov ve slovní zásobě skupiny, která končí souhláskou (`pressures.linguistic.coda_share`).
pub fn coda_share(world: &World, group: GroupId) -> f64 {
    let code = world.groups.main_code(group);
    let (mut codas, mut total) = (0_u32, 0_u32);
    for unit in code.phonology.vocabulary.iter() {
        let form = world.form_of(group, unit);
        if let Some(&last) = form.last() {
            total += 1;
            if !world
                .table
                .as_ref()
                .is_some_and(|table| table.is_vowel(last))
            {
                codas += 1;
            }
        }
    }
    if total == 0 {
        0.0
    } else {
        f64::from(codas) / f64::from(total)
    }
}
