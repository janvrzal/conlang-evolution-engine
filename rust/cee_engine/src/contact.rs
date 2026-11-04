//! Kontakt jazyků: filtry výpůjček a interference, kanály, dárci a adaptace cizích slov
//! (zrcadlo části `contact.py`; demografii komunit řeší `phases::communities`).
//!
//! Kontakt nemá vlastní mechanismus šíření. Varianta jiného jazyka vstupuje do proměnné
//! stejně jako varianta sousedního dialektu, jen přes dva filtry přenositelnosti
//! (Thomason & Kaufman 1988): **výpůjčka** (mluvčí si drží svůj jazyk; nejsnáz slova, spíš
//! vzácná než základní) a **interference** (dospělí se učí cizí kód a nesou do něj svůj
//! první jazyk: hlavně výslovnost a konstrukce).
//!
//! # Rozhraní pro přenos (R1a, R1c)
//!
//! * [`BorrowTable::build`] jednou za krok spočítá váhu každého pojmu; potom je
//!   [`BorrowTable::factor`]`(variable, channel)` filtr výpůjček proměnné v kanálu
//!   (číslo kanálu: [`NEIGHBOR`], [`ELITE`], [`TRADE`], [`LITURGY`], [`READING`],
//!   [`SCHOOL`]). Pro slova je to `BORROWING × přenositelnost pojmu × váha domény v kanálu`.
//! * [`interference_factor`] je filtr interference podle druhu proměnné.
//! * [`distinct_channels`] řekne, které kanály `elite`, `trade` mají jiné váhy domén než
//!   obecný kontakt sousedů (jen ty se v přenosu počítají zvlášť).
//! * [`channel_split`]`(world, učící se, zdroj, distinct)` rozdělí jednu vazbu mezi
//!   kanály: podíly `(neighbor, elite, trade)` se sčítají na 1. Je **řídké** (po vazbě),
//!   nikdy nestaví čtvercovou matici skupin.
//! * [`adopt`] převezme cizí kořen do slovní zásoby skupiny (tvar od dárce, adaptovaný
//!   na hlásky příjemce); volá ho `phases::hooks::adopt`.

use std::collections::BTreeSet;
use std::sync::OnceLock;

use crate::concepts::{ConceptData, Defaults};
use crate::edits::neighbors;
use crate::ids::{ConceptId, GroupId, MorphemeId, VariableId};
use crate::model::forms::UnitForm;
use crate::model::repertoire::VariableKind;
use crate::parameters::{Parameters, CHANNELS, DOMAINS};
use crate::world::World;

/// Čísla kanálů (pořadí `parameters::CHANNELS`).
pub const NEIGHBOR: usize = 0;
pub const ELITE: usize = 1;
pub const TRADE: usize = 2;
pub const LITURGY: usize = 3;
pub const READING: usize = 4;
pub const SCHOOL: usize = 5;

/// Kanály, které se v přenosu odlišují od obecného kontaktu sousedů (pořadí je pevné).
pub const FLOW_CHANNELS: [usize; 2] = [ELITE, TRADE];

/// Půjčitelnost pod touto hodnotou se bere jako tato hodnota: slovo, které WOLD nikde
/// nenašla přejaté (*this*, *we*), se nepůjčuje skoro, ale ne nikdy.
pub const BORROWED_FLOOR: f64 = 0.01;

/// Filtr výpůjček podle druhu proměnné (slova se dál násobí váhou pojmu a domény).
pub fn borrowing_kind(kind: VariableKind) -> f64 {
    match kind {
        VariableKind::Lexical => 0.5,
        VariableKind::Process | VariableKind::Construction => 0.1,
        VariableKind::Form | VariableKind::Prosody => 0.0,
    }
}

/// Filtr interference při osvojování druhého jazyka podle druhu proměnné.
pub fn interference_factor(kind: VariableKind) -> f64 {
    match kind {
        VariableKind::Lexical => 0.05,
        VariableKind::Process | VariableKind::Construction => 1.0,
        VariableKind::Form | VariableKind::Prosody => 0.0,
    }
}

/// Průměrná půjčitelnost výchozích pojmů z dat (kotva `borrowability_strength`).
pub fn reference() -> f64 {
    static REFERENCE: OnceLock<f64> = OnceLock::new();
    *REFERENCE.get_or_init(|| {
        let scores: Vec<f64> = ConceptData::shared()
            .engine_concepts()
            .into_iter()
            .filter_map(|(_, b)| b)
            .collect();
        scores.iter().sum::<f64>() / scores.len().max(1) as f64
    })
}

/// Průměr váhy pojmu (bez normalizace) přes pojmy z dat vůči průměru `1 − frekvence`,
/// aby `borrowability_strength` nezměnila průměrnou míru výpůjček výchozího slovníku.
pub fn normalizer(strength: f64) -> f64 {
    let data = ConceptData::shared();
    let mean = reference();
    let rarity = |name: &str| 1.0 - data.frequency(name).unwrap_or(0.0);
    let all = data.engine_concepts();
    let rarity_mean = all.iter().map(|(n, _)| rarity(n)).sum::<f64>() / all.len().max(1) as f64;
    let weights: Vec<f64> = all
        .iter()
        .filter_map(|(name, b)| {
            b.map(|b| {
                rarity(name).powf((1.0 - strength).max(0.0))
                    * (b.max(BORROWED_FLOOR) / mean).powf(strength)
            })
        })
        .collect();
    (weights.iter().sum::<f64>() / weights.len().max(1) as f64) / rarity_mean
}

/// Váha pojmu při přenosu slova z cizího kódu (bez kanálu a domény).
///
/// S `Parameters::borrowability_strength` *s* je to
/// `(1 − frekvence)^max(0, 1 − s) · (půjčitelnost / průměr)^s`, přepočtené tak, aby měla
/// přes výchozí pojmy stejný průměr jako `1 − frekvence`.
pub fn transfer(world: &World, concept: ConceptId, normalizer_value: f64) -> f64 {
    let rarity = 1.0 - world.concept_frequency(concept);
    let strength = world.params.borrowability_strength;
    if strength == 0.0 {
        return rarity;
    }
    let borrowed = world
        .concepts
        .borrowed
        .get(concept.index())
        .copied()
        .unwrap_or_else(reference)
        .max(BORROWED_FLOOR);
    let mut weight = (borrowed / reference()).powf(strength);
    if strength < 1.0 {
        weight *= rarity.powf(1.0 - strength);
    }
    weight / normalizer_value
}

/// Váhy pojmů pro filtr výpůjček, spočtené jednou za krok (pojmy a frekvence se mění pomalu).
#[derive(Clone, Debug)]
pub struct BorrowTable {
    /// Přenositelnost pojmu podle čísla pojmu.
    transfer: Vec<f64>,
    /// Váha domény pojmu v kanálu: `[kanál][pojem]`.
    domain: Vec<Vec<f64>>,
}

impl BorrowTable {
    pub fn build(world: &World) -> BorrowTable {
        let norm = if world.params.borrowability_strength == 0.0 {
            1.0
        } else {
            normalizer(world.params.borrowability_strength)
        };
        let size = world.registry.concepts.len();
        let transfer_of: Vec<f64> = (0..size)
            .map(|c| transfer(world, ConceptId::new(c), norm))
            .collect();
        let domain = (0..CHANNELS.len())
            .map(|channel| {
                (0..size)
                    .map(|c| {
                        domain_weight(
                            &world.params,
                            channel,
                            world.concepts.domain.get(c).copied().unwrap_or(0),
                        )
                    })
                    .collect()
            })
            .collect();
        BorrowTable {
            transfer: transfer_of,
            domain,
        }
    }

    /// Filtr výpůjček proměnné v kanálu (`contact.borrowing_factor`).
    pub fn factor(&self, world: &World, variable: VariableId, channel: usize) -> f64 {
        let kind = world.variables.kind[variable.index()];
        let mut factor = borrowing_kind(kind);
        if kind == VariableKind::Lexical {
            let concept = world.variables.concept[variable.index()];
            factor *= self.transfer[concept.index()];
            let weight = self.domain[channel][concept.index()];
            if weight != 1.0 {
                factor *= weight;
            }
        }
        factor
    }
}

/// Váha domény (číslo domény z `ConceptColumns::domain`) v kanálu.
pub fn domain_weight(params: &Parameters, channel: usize, domain: u8) -> f64 {
    params
        .channel_domains
        .get(CHANNELS[channel])
        .and_then(|row| row.get(DOMAINS[usize::from(domain)]))
        .copied()
        .unwrap_or(1.0)
}

/// Kanály s jinými vahami domén než obecný kontakt sousedů (jen ty se počítají zvlášť).
pub fn distinct_channels(params: &Parameters) -> Vec<usize> {
    let base = params.channel_domains.get(CHANNELS[NEIGHBOR]);
    FLOW_CHANNELS
        .iter()
        .copied()
        .filter(|&c| params.channel_domains.get(CHANNELS[c]) != base)
        .collect()
}

/// Rozdělení vazby mezi kanály: podíly se sčítají na 1.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ChannelSplit {
    pub neighbor: f64,
    pub elite: f64,
    pub trade: f64,
}

/// Kanály, kterými slova od dárce přicházejí (`contact.donor_channels`): zdroj-elita je celý
/// kanál `elite`, z ostatních vazeb patří `trade` podíl síly, který přinesla obchodní cesta.
pub fn channel_split(
    world: &World,
    learner: GroupId,
    donor: GroupId,
    distinct: &[usize],
) -> ChannelSplit {
    if distinct.contains(&ELITE) && world.groups.elite[donor.index()] {
        return ChannelSplit {
            neighbor: 0.0,
            elite: 1.0,
            trade: 0.0,
        };
    }
    let share = if distinct.contains(&TRADE) {
        world.trade_share(learner, donor)
    } else {
        0.0
    };
    ChannelSplit {
        neighbor: 1.0 - share,
        elite: 0.0,
        trade: share,
    }
}

// --- adaptace výpůjček ------------------------------------------------------------

/// Hlásky, které kód skupiny ve slovní zásobě užívá (vzestupně).
pub fn inventory(world: &World, group: GroupId) -> Vec<i32> {
    let code = world.groups.main_code(group);
    let mut found: BTreeSet<i32> = BTreeSet::new();
    for unit in code.phonology.vocabulary.iter() {
        found.extend(world.form_of(group, unit).iter().copied());
    }
    found.into_iter().collect()
}

/// Cizí hlásky se nahradí nejbližší hláskou příjemce (podle rysů); samohláska zůstane
/// samohláskou, souhláska souhláskou.
pub fn adapt(world: &World, native: &[i32], form: &[i32]) -> Vec<i32> {
    let Some(table) = world.table.as_ref() else {
        return form.to_vec();
    };
    if native.is_empty() || form.iter().all(|s| native.binary_search(s).is_ok()) {
        return form.to_vec();
    }
    form.iter()
        .map(|&segment| {
            if native.binary_search(&segment).is_ok() {
                return segment;
            }
            let here = table.row(segment as usize);
            let vowel = table.is_vowel(segment);
            let mut best = (u32::MAX, native[0]);
            for &candidate in native {
                let mut distance = table
                    .row(candidate as usize)
                    .iter()
                    .zip(here)
                    .filter(|(a, b)| a != b)
                    .count() as u32;
                if table.is_vowel(candidate) != vowel {
                    distance += 1000;
                }
                if distance < best.0 {
                    best = (distance, candidate);
                }
            }
            best.1
        })
        .collect()
}

/// Tvar slova u nejbližšího mluvčího jeho jazyka, jak ho skupina slyší.
pub fn donor_form(world: &World, group: GroupId, morpheme: MorphemeId) -> Vec<i32> {
    let language = world.morphemes.language[morpheme.index()];
    let mut candidates: Vec<(f64, GroupId)> = neighbors(world, group)
        .into_iter()
        .map(|(target, link)| (link.strength, target))
        .collect();
    let code = world.groups.main_code(group);
    for source in [
        code.l1_source,
        world.groups.standard[group.index()],
        world.groups.liturgy[group.index()],
    ] {
        if !source.is_none() && world.groups.contains(source) {
            candidates.push((1.0, source));
        }
    }
    candidates.sort_by(|a, b| {
        b.0.partial_cmp(&a.0)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then(world.group_name(a.1).cmp(world.group_name(b.1)))
    });
    for (_, donor) in candidates {
        let code = world.groups.main_code(donor);
        if code.language == language && code.phonology.vocabulary.contains(morpheme) {
            return world.form_of(donor, morpheme).to_vec();
        }
    }
    world
        .bank
        .form(world.morphemes.form[morpheme.index()])
        .to_vec()
}

/// Cizí kořen vstupuje do slovní zásoby: převezme a adaptuje jeho tvar. Tvary buněk
/// paradigmatu dostane výpůjčka podle produktivních koncovek příjemce (R1c).
pub fn adopt(world: &mut World, group: GroupId, morpheme: MorphemeId) -> Result<(), String> {
    let code = world.groups.main_code(group);
    if world.morphemes.language[morpheme.index()] == code.language
        || code.forms.get(morpheme).is_some()
        || world.table.is_none()
    {
        return Ok(());
    }
    let donor = donor_form(world, group, morpheme);
    let native = inventory(world, group);
    let adapted = adapt(world, &native, &donor);
    let form = world.bank.id_of(&adapted);
    world.groups.main_code_mut(group).forms.set(
        morpheme,
        UnitForm {
            form,
            boundary: -1,
            exponent: MorphemeId::NONE,
        },
    );
    Ok(())
}

/// Kolik pojmů výchozího slovníku (pro testy a kalibraci kotvy).
pub fn default_concept_count() -> usize {
    Defaults::shared().default_concepts.len()
}
