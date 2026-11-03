//! Souběžná variabilita slovní zásoby protojazyka (zrcadlo `cee.v2.variation`).
//!
//! Python rozdá variabilitu při tvorbě světa podle naměřeného modelu vesnice
//! (`v2_standing_variation.json`, `data::STANDING_VARIATION_JSON`), šíří ji po grafu
//! vazeb a návrhy slov bere z lexikálních změn (`LEXICAL_CHANGES.propose`) na numpy
//! generátoru. Tuhle práci převezme R1c spolu s lexikálními změnami; R0 ji vynechává,
//! takže svět v Rustu začíná **bez** souběžné variability (jako Python s
//! `standing_variation = 0`). Tak se také porovnává tik 0.

use crate::world::World;

/// Rozdá souběžnou variabilitu vesnicím (R0: nic, viz popis modulu).
pub fn seed(world: &mut World) -> Result<(), String> {
    let _ = world;
    Ok(())
}
