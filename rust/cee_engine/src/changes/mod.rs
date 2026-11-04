//! Změny jazyka a jejich rozhraní pro fázi inovací.
//!
//! Změna (zvuková, lexikální, morfologická, syntaktická, prozodická) určuje, kde
//! může inovace vzniknout (**místa** a jejich váhy) a jak vypadá nová varianta
//! (`propose`). Fázi inovací (`phases::innovation`) řídí jen tohle rozhraní, takže
//! každý agent R1 přidává své změny **do vlastního souboru** a registruje je v
//! [`default_changes`]:
//!
//! | agent | soubor | změny |
//! |---|---|---|
//! | R1b | `changes/sound.rs` | zvukové změny (rodiny, tóny) |
//! | R1c | `changes/lexicon.rs`, `morphology.rs`, `syntax.rs`, `prosody.rs` | lexikální, morfologické, syntaktické, prozodické |
//!
//! Čtení (`weighted_sites`, `rate_sum`) bere `&World` a běží souběžně přes skupiny
//! (rayon, výsledek nezávisí na počtu vláken). `propose` smí svět měnit (např. založit
//! nový morfém) a běží sekvenčně v kanonickém pořadí skupin a změn.

pub mod lexicon;
pub mod morphology;
pub mod prosody;
pub mod syntax;

use crate::ids::{GroupId, VariableId};
use crate::model::repertoire::{Origin, Payload};
use crate::rng::Stream;
use crate::world::World;

/// Skupina a krok, ve kterých inovace vzniká.
#[derive(Clone, Copy, Debug)]
pub struct InnovationContext {
    pub group: GroupId,
    pub tick: u32,
    pub year: f64,
}

/// Místa změny (proměnné) a jejich váhy; bez vah jsou místa rovnocenná.
#[derive(Clone, Debug, Default)]
pub struct Sites {
    pub sites: Vec<VariableId>,
    pub weights: Option<Vec<f64>>,
}

/// Navržená varianta: jméno (stabilní ID), proměnná, obsah a původ.
#[derive(Clone, Debug)]
pub struct NewVariant {
    pub name: String,
    pub variable: VariableId,
    pub payload: Payload,
    pub origin: Origin,
}

pub trait Change: Send + Sync {
    /// Druh změny (`sound`, `coinage`, …) – klíč náhody a záznamů.
    fn kind(&self) -> &'static str;

    /// Tempo podle obnovy generace (`true`), nebo podle délky kroku (`false`).
    fn rate_basis_generation(&self) -> bool {
        false
    }

    /// Místa změny ve skupině a jejich váhy (stav na začátku kroku).
    fn weighted_sites(&self, world: &World, ctx: &InnovationContext) -> Sites;

    /// Celková míra všech míst ve skupině (0 = změna tu nemá co dělat).
    fn rate_sum(&self, world: &World, ctx: &InnovationContext) -> f64;

    /// Návrh varianty na místě `site`; čerpá z proudu náhody `rng` (po výběru místa).
    fn propose(
        &self,
        world: &mut World,
        ctx: &InnovationContext,
        site: VariableId,
        rng: &mut Stream,
        index: usize,
    ) -> Option<NewVariant>;
}

/// Všechny změny enginu v kanonickém pořadí (pořadí určuje indexy sloupců náhody).
///
/// Pořadí jako `DEFAULT_CHANGES` v Pythonu: lexikální, zvukové (R1b), morfologické,
/// syntaktické, prozodické. R1b přidá své zvukové změny mezi lexikální a morfologické.
pub fn default_changes() -> Vec<Box<dyn Change>> {
    let mut all = lexicon::changes();
    // Zde: zvukové změny (R1b, `changes/sound.rs`).
    all.extend(morphology::changes());
    all.extend(syntax::changes());
    all.extend(prosody::changes());
    all
}
