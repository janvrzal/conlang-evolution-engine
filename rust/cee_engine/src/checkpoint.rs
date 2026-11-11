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

/// Verze formátu kontrolního bodu; mění se s rozložením hlavičky.
pub const CHECKPOINT_VERSION: u32 = 3;

/// Otisk sestavení enginu (zdroj enginu a jádra, vložená data; `build.rs`). Kontrolní bod
/// z jiného sestavení se nenačte: struktury nebo dynamika se mohly změnit.
pub const ENGINE_BUILD: &str = env!("CEE_ENGINE_BUILD");

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Checkpoint {
    pub tick: u32,
    pub year: f64,
    pub world: World,
    pub history: History,
}

/// Bod z jiné verze nebo jiného sestavení enginu (ne poškozený soubor).
pub const STALE: &str = "kontrolní bod je z jiné verze enginu";

impl Checkpoint {
    /// Uloží kontrolní bod do bajtů (verze, otisk sestavení, obsah).
    pub fn to_bytes(&self) -> Result<Vec<u8>, String> {
        postcard::to_stdvec(&(CHECKPOINT_VERSION, ENGINE_BUILD, self))
            .map_err(|e| format!("kontrolní bod: {e}"))
    }

    /// Načte kontrolní bod. Bod z jiné verze formátu nebo jiného sestavení vrátí chybu, která
    /// začíná [`STALE`] (volající pak počítá od začátku).
    pub fn from_bytes(bytes: &[u8]) -> Result<Checkpoint, String> {
        let (version, rest): (u32, &[u8]) =
            postcard::take_from_bytes(bytes).map_err(|e| format!("kontrolní bod: {e}"))?;
        if version != CHECKPOINT_VERSION {
            return Err(format!(
                "{STALE} (formát {version}, čekám {CHECKPOINT_VERSION})"
            ));
        }
        let (build, rest): (&str, &[u8]) =
            postcard::take_from_bytes(rest).map_err(|e| format!("kontrolní bod: {e}"))?;
        if build != ENGINE_BUILD {
            return Err(format!("{STALE} (sestavení {build}, teď {ENGINE_BUILD})"));
        }
        postcard::from_bytes(rest).map_err(|e| format!("kontrolní bod: {e}"))
    }
}
