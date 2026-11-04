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
