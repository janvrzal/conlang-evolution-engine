//! Fáze 5: komunity, přechod jazyka a dvojjazyčnost (R1d).
//!
//! **Vstup:** `World` (skupiny, kódy, vazby, prestiž), `dt`, tik, rok, historie.
//! **Výstup:** změněné populace a podíly kódů (přechod na jiný jazyk, přistěhovalci,
//! migrace), nové či zaniklé skupiny; vrací `true`, když se změnila osa skupin
//! (pak kostra přepočte živé fondy `World::sync_live_groups`). Zrcadlo
//! `contact.community_step`.

use crate::phases::StepContext;

/// Provede fázi komunit (R0: kostra, nic nemění).
pub fn run(_ctx: &mut StepContext<'_>) -> Result<bool, String> {
    Ok(false) // TODO(R1d)
}
