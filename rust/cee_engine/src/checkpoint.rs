//! Kontrolní body běhu přes `serde` (formát postcard).
//!
//! Kontrolní bod je úplný stav po kroku `tick`: `World` (včetně banky tvarů, živých
//! fondů a stavů oblastí R1) a `History`. Formát **postcard** (MIT/Apache-2.0) je
//! kompaktní, má stabilní specifikaci a rychle se (de)serializuje; nepopisuje typy,
//! proto se volný JSON obsah ukládá jako text (`json_string`). Odvozené keše
//! (`#[serde(skip)]`) se po načtení staví znovu. Fronta událostí se neukládá: kdo
//! pokračuje, zadá pozdější události znovu (`Simulation::resume`).

use serde::{Deserialize, Serialize};

use crate::history::History;
use crate::world::World;

/// Verze formátu kontrolního bodu; mění se s rozložením uložených struktur.
pub const CHECKPOINT_VERSION: u32 = 2;

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Checkpoint {
    pub tick: u32,
    pub year: f64,
    pub world: World,
    pub history: History,
    /// Jména s historií (modul jmen), pokud byl zapnutý.
    pub names: Option<crate::names::NameState>,
}

impl Checkpoint {
    /// Uloží kontrolní bod do bajtů (verze + obsah).
    pub fn to_bytes(&self) -> Result<Vec<u8>, String> {
        postcard::to_stdvec(&(CHECKPOINT_VERSION, self)).map_err(|e| format!("kontrolní bod: {e}"))
    }

    pub fn from_bytes(bytes: &[u8]) -> Result<Checkpoint, String> {
        let (version, checkpoint): (u32, Checkpoint) =
            postcard::from_bytes(bytes).map_err(|e| format!("kontrolní bod: {e}"))?;
        if version != CHECKPOINT_VERSION {
            return Err(format!(
                "kontrolní bod verze {version}, čekám {CHECKPOINT_VERSION}"
            ));
        }
        Ok(checkpoint)
    }
}
