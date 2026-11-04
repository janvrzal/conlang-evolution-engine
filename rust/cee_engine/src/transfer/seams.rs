//! Místa, kde přenos čte stav jiné oblasti enginu a ten zatím není ve společném datovém modelu.
//!
//! Funkce tu mají pevný podpis a nejjednodušší správné tělo; až vlastník oblasti stav doplní,
//! změní se jen tělo (R2 při slučování). Každá je popsaná tím, co od druhé oblasti čekám.

use crate::ids::{GroupId, VariableId};
use crate::world::World;

/// Uzavřela si skupina zvukovou změnu do podkladových tvarů (`PhonologyState.closed`)?
///
/// Tlak `Norm` zvukovou změnu, kterou už si kód uzavřel do tvarů slov, nevrací zpět. Stav
/// `closed` (množina proměnných) patří fonologii (R1b, `SoundCodeState`); do té doby je
/// odpověď vždy `false`, tedy norma působí na všechny proměnné.
pub fn closed(_world: &World, _group: GroupId, _variable: VariableId) -> bool {
    false
}

/// Hodnocení změny (procesu či analogie) ve skupinách `columns` (sloupce osy), kam dolehla.
///
/// Pro proměnnou druhu `Process` jsou hodnoty `[pokrytí, splynutí, krátká slova, příznakovost,
/// rozptyl vokálů]` (`assessment.ProcessAssessment`), pro druh `Form` `[zisk, frekvence,
/// splynutí před, splynutí po, 0]` (`morphology.FormAssessment`; `None` = změna by tvar
/// nezměnila). Hodnocení stojí na bance tvarů s tabulkami procesů (R1b: registrace procesu,
/// vzorek slov kódu, mapy hlásek) a na morfologickém indexu kódů (R1c). Dokud tyto stavy ve
/// společném modelu nejsou, vrací `None` všude, tedy tlaky nad hodnocením jsou nulové.
pub fn assess_cells(
    _world: &World,
    _variable: VariableId,
    columns: &[usize],
    _tick: u32,
) -> Vec<Option<crate::transfer::assessed::Assessment>> {
    vec![None; columns.len()]
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
