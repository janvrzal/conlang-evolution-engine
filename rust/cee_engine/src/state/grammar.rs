//! Stav morfologie, syntaxe, prozodie a lexikálních změn (R1c).
//!
//! **Svět:** index míst morfologických, sémantických a syntaktických změn
//! (`cee_core::sites::SiteIndex`), seznam paradigmat a konstrukcí.
//! **Kód:** živé morfologické změny (`morph_active`, `morph_closed`) a konstrukce,
//! které si kód už zapsal do tvarů (`grammar_applied`) – v Pythonu `PhonologyState`.

use std::collections::BTreeSet;

use serde::{Deserialize, Serialize};

use crate::ids::{VariableId, VariantId};

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct GrammarWorldState {
    /// Verze indexu míst; roste s každou změnou slovní zásoby kódů.
    pub site_version: u64,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct GrammarCodeState {
    /// Živé morfologické změny: proměnná → tvar slova, kterého se týká.
    pub morph_active: Vec<(VariableId, crate::ids::MorphemeId)>,
    pub morph_closed: BTreeSet<VariableId>,
    /// Syntetické konstrukce (nové koncovky), které už kód zapsal do tvarů.
    pub grammar_applied: BTreeSet<VariantId>,
}
