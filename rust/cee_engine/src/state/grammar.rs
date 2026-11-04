//! Stav morfologie, syntaxe, prozodie a lexikálních změn (R1c).
//!
//! **Svět:** verze indexu míst a počty zaregistrovaných formových proměnných
//! (`GrammarWorldState`).
//! **Kód:** živé morfologické změny (`morph_active`, `morph_closed`), konstrukce,
//! které si kód už zapsal do tvarů (`grammar_applied`), a keše míst změn. V Pythonu to
//! je `PhonologyState`.
//!
//! **Keše míst.** Místa změn (sémantické cesty slov, kandidáti vyrovnání a rozšíření,
//! koncovky tříd, slabost buněk) se počítají z dominantních kořenů, slovní zásoby a tvarů
//! kódu. Čtou je fáze, které běží souběžně přes skupiny (`rate_sum`, `weighted_sites`),
//! proto jsou za zámkem ([`ViewCache`]) a drží se podle verze stavu, ze kterého vznikly.
//! Keš je jen odvozený údaj: do kontrolního bodu se neukládá a kopie stavu začíná prázdná.

use std::any::Any;
use std::collections::{BTreeMap, BTreeSet};
use std::sync::{Arc, Mutex};

use serde::{Deserialize, Serialize};

use crate::ids::{MorphemeId, VariableId, VariantId};

/// Pohled uložený v keši: verze stavu, ze kterého vznikl, a hodnota.
type View = (u64, Arc<dyn Any + Send + Sync>);

/// Odvozené pohledy kódu držené podle verze stavu (viz popis modulu).
#[derive(Default)]
pub struct ViewCache {
    inner: Mutex<BTreeMap<&'static str, View>>,
}

impl ViewCache {
    /// Pohled `key`, pokud vznikl ze stavu `version`; jinak se postaví a zapamatuje.
    ///
    /// Zámek se při stavbě pohledu nedrží, takže stavba smí číst jiné pohledy téhož kódu.
    pub fn get_or<T: Any + Send + Sync>(
        &self,
        key: &'static str,
        version: u64,
        make: impl FnOnce() -> T,
    ) -> Arc<T> {
        {
            let held = self.inner.lock().expect("keš pohledů");
            if let Some((made, value)) = held.get(key) {
                if *made == version {
                    if let Ok(found) = value.clone().downcast::<T>() {
                        return found;
                    }
                }
            }
        }
        let built = Arc::new(make());
        let mut held = self.inner.lock().expect("keš pohledů");
        held.insert(key, (version, built.clone()));
        built
    }

    /// Zahodí všechny pohledy (po změně, kterou verze nezachytí).
    pub fn clear(&self) {
        self.inner.lock().expect("keš pohledů").clear();
    }
}

impl Clone for ViewCache {
    /// Kopie stavu začíná s prázdnou keší (pohledy se postaví znovu).
    fn clone(&self) -> Self {
        ViewCache::default()
    }
}

impl std::fmt::Debug for ViewCache {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "ViewCache")
    }
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct GrammarWorldState {
    /// Verze indexu míst; roste s každou změnou slovní zásoby kódů.
    pub site_version: u64,
    /// Počet formových proměnných, které svět zaregistroval (jen ladění a statistiky).
    pub form_variables: u64,
    /// Odvozené pohledy světa (katalog funkcí s přepisy, přenositelnost pojmů); neukládají se.
    #[serde(skip)]
    pub cache: ViewCache,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct GrammarCodeState {
    /// Živé morfologické změny: proměnná → tvar slova, kterého se týká.
    pub morph_active: Vec<(VariableId, MorphemeId)>,
    pub morph_closed: BTreeSet<VariableId>,
    /// Syntetické konstrukce (nové koncovky), které už kód zapsal do tvarů.
    pub grammar_applied: BTreeSet<VariantId>,
    /// Odvozené pohledy (místa změn, koncovky tříd); nikdy se neukládají.
    #[serde(skip)]
    pub cache: ViewCache,
    /// Průběžně udržované pohledy slov kódu ([`crate::views`]); neukládají se, po obnově
    /// z kontrolního bodu se postaví znovu.
    #[serde(skip)]
    pub index: crate::views::ClassIndex,
}
