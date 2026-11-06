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
pub mod sound;
pub mod syntax;

use crate::ids::{GroupId, VariableId};
use cee_core::pressures::id;

use crate::model::repertoire::{Origin, Payload, VariableKind};
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

/// Tlaky zvukových změn (`changes.sound.SOUND_PRESSURES`): (číslo tlaku z `cee_core::pressures::id`, váha).
///
/// Zřetelnost 1,5 (dříve 0,6) a funkční zatížení 1,5 (dříve 1,0) od M9b: při realistickém tempu
/// hláskových změn (`Parameters::sound_actuation`) chrání rozlišení, jinak eroze gramatických
/// značek rozhází typologii (člen, zápor); dok. 24.
pub const SOUND_PRESSURES: [(u8, f64); 7] = [
    (id::ARTICULATION, 1.0),
    (id::CLARITY, 1.5),
    (id::FUNCTIONAL_LOAD, 1.5),
    (id::DISPERSION, 0.5),
    (id::PHONOTACTICS, 0.4),
    (id::CONFORMITY, 0.1),
    (id::ACTUATION, 1.0),
];

/// Tlaky lexikálních změn (`changes.lexicon.LEXICAL_PRESSURES`).
pub const LEXICAL_PRESSURES: [(u8, f64); 6] = [
    (id::LEXICAL_CLARITY, 1.0),
    (id::ENTRENCHMENT, 1.0),
    (id::MOTIVATION, 1.0),
    (id::TABOO, 1.0),
    (id::LEXICAL_ACTUATION, 1.0),
    (id::CONFORMITY, 0.1),
];

/// Tlaky expresivního tvoření slov: přitažlivost a tlaky lexikálních změn.
pub const COINAGE_PRESSURES: [(u8, f64); 7] = [
    (id::APPEAL, 1.0),
    (id::CONFORMITY, 0.1),
    (id::LEXICAL_CLARITY, 1.0),
    (id::ENTRENCHMENT, 1.0),
    (id::MOTIVATION, 1.0),
    (id::TABOO, 1.0),
    (id::LEXICAL_ACTUATION, 1.0),
];

/// Tlaky analogických změn tvarů (`changes.morphology.MORPH_PRESSURES`).
pub const MORPH_PRESSURES: [(u8, f64); 6] = [
    (id::UNIFORMITY, 1.0),
    (id::CONSERVATION, 1.0),
    (id::DISTINCTIVENESS, 1.0),
    (id::TEACHABILITY, 1.0),
    (id::CONFORMITY, 0.1),
    (id::ACTUATION, 1.0),
];

/// Tlaky syntaktických změn (`changes.syntax.SYNTAX_PRESSURES`).
pub const SYNTAX_PRESSURES: [(u8, f64); 7] = [
    (id::EXPRESSIVITY, 1.0),
    (id::ECONOMY, 1.0),
    (id::FUSION, 1.0),
    (id::AMBIGUITY, 1.0),
    (id::LEARNABILITY, 1.0),
    (id::CONFORMITY, 0.1),
    (id::ACTUATION, 1.0),
];

/// Tlaky prozodických změn (`changes.prosody.PROSODY_PRESSURES`).
pub const PROSODY_PRESSURES: [(u8, f64); 2] = [(id::CONFORMITY, 0.1), (id::ACTUATION, 1.0)];

pub trait Change: Send + Sync {
    /// Druh změny (`sound`, `coinage`, …) – klíč náhody a záznamů.
    fn kind(&self) -> &'static str;

    /// Cílový druh proměnné, jejíž varianty změna vyrábí (`Change.target`); varianty téhož druhu
    /// se hodnotí společným plánem tlaků ([`crate::transfer::pressures::plan_for`]).
    fn target(&self) -> VariableKind;

    /// Tlaky, které hodnotí varianty cílového druhu, a jejich váhy (`Change.pressures`); tlak
    /// deklarovaný víc změnami téhož cíle platí s nejvyšší váhou.
    fn pressures(&self) -> &'static [(u8, f64)];

    /// Tempo podle obnovy generace (`true`), nebo podle délky kroku (`false`).
    fn rate_basis_generation(&self) -> bool {
        false
    }

    /// Příprava sdíleného stavu, který míry a místa čtou (stav na začátku kroku): změna smí
    /// dorovnat své indexy pro všechny skupiny najednou (souběžně) dřív, než se jednotlivé
    /// skupiny začnou ptát. Výsledek nesmí záviset na tom, zda se volá; výchozí nedělá nic.
    fn prepare(&self, _world: &World, _groups: &[GroupId]) -> Result<(), String> {
        Ok(())
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
    all.extend(sound::sound_changes());
    all.extend(morphology::changes());
    all.extend(syntax::changes());
    all.extend(prosody::changes());
    all
}
