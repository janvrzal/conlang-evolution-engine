//! Metriky realističnosti pro brány (zrcadlo `cee.v2.metrics`), počítané z historie, snímků
//! a stavu světa v Rustu.
//!
//! Zjednodušení proti Pythonu: povrchový tvar slova (`phonology.surface`: podkladový tvar
//! prohnaný živými procesy) Rust zatím nemá, profily slovní zásoby proto čtou **podkladové**
//! tvary dominantních kořenů (`World::form_of`).

use std::collections::{BTreeMap, BTreeSet, HashMap};

use crate::history::History;
use crate::ids::{ConceptId, GroupId, MorphemeId, VariableId, VariantId};
use crate::model::lexicon::MorphemeKind;
use crate::model::repertoire::{Payload, VariableKind};
use crate::morphology::{class_stats, split};
use crate::world::World;

/// Pásma velikosti inventáře podle WALS 1A a 2A (Maddieson 2013).
pub const CONSONANT_BAND: (f64, f64) = (6.0, 40.0);
pub const VOWEL_BAND: (f64, f64) = (2.0, 14.0);

// --- drobné pomůcky ---------------------------------------------------------------------

/// Skupina podle jména, jen pokud ve světě žije.
pub fn group_named(world: &World, name: &str) -> Option<GroupId> {
    world
        .registry
        .groups
        .get(name)
        .map(GroupId)
        .filter(|&id| world.groups.contains(id))
}

pub fn mean(values: &[f64]) -> f64 {
    if values.is_empty() {
        return f64::NAN;
    }
    values.iter().sum::<f64>() / values.len() as f64
}

pub fn median(values: &[f64]) -> f64 {
    if values.is_empty() {
        return f64::NAN;
    }
    let mut sorted = values.to_vec();
    sorted.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    let middle = sorted.len() / 2;
    if sorted.len() % 2 == 1 {
        sorted[middle]
    } else {
        (sorted[middle - 1] + sorted[middle]) / 2.0
    }
}

pub fn maximum(values: &[f64]) -> f64 {
    values.iter().copied().fold(f64::NAN, f64::max)
}

pub fn minimum(values: &[f64]) -> f64 {
    values.iter().copied().fold(f64::NAN, f64::min)
}

/// Lexikální proměnné ve světě seřazené podle jména (pořadí `sorted(world.variables)`).
pub fn lexical_variables(world: &World) -> Vec<(VariableId, ConceptId)> {
    let mut found: Vec<(VariableId, ConceptId)> = (0..world.variables.len())
        .filter(|&v| world.variables.kind[v] == VariableKind::Lexical)
        .map(|v| (VariableId::new(v), world.variables.concept[v]))
        .collect();
    found.sort_by(|a, b| {
        world
            .registry
            .variables
            .name(a.0 .0)
            .cmp(world.registry.variables.name(b.0 .0))
    });
    found
}

/// Dominantní kořen lexikální proměnné ve skupině (`None` = skupina ji nemá nebo slovo nemá tvar).
pub fn root_of(world: &World, group: GroupId, variable: VariableId) -> Option<MorphemeId> {
    let (variant, _) = world.dominant(group, variable)?;
    match world.variants.payload.get(variant.index())? {
        Payload::Lexical { morpheme, .. } => morpheme.option(),
        _ => None,
    }
}

/// Dominantní kořeny skupiny podle pojmů seřazených podle jména.
pub fn dominant_roots(world: &World, group: GroupId) -> Vec<(ConceptId, MorphemeId)> {
    let mut found: Vec<(ConceptId, MorphemeId)> = world
        .groups
        .main_code(group)
        .phonology
        .dominant
        .iter()
        .enumerate()
        .filter(|(_, root)| !root.is_none())
        .map(|(concept, &root)| (ConceptId::new(concept), root))
        .collect();
    found.sort_by(|a, b| {
        world
            .registry
            .concepts
            .name(a.0 .0)
            .cmp(world.registry.concepts.name(b.0 .0))
    });
    found
}

/// Pojmy se známou frekvencí (`World.concept_frequencies`) a jejich frekvence.
pub fn explicit_frequencies(world: &World) -> Vec<(ConceptId, f64)> {
    world
        .concepts
        .frequency
        .iter()
        .enumerate()
        .filter(|(_, value)| !value.is_nan())
        .map(|(concept, &value)| (ConceptId::new(concept), value))
        .collect()
}

/// Pojmy seřazené podle (frekvence, jméno), jako `sorted(..., key=(frequency, concept))`.
pub fn concepts_by_frequency(world: &World) -> Vec<ConceptId> {
    let mut found = explicit_frequencies(world);
    found.sort_by(|a, b| {
        a.1.partial_cmp(&b.1)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then_with(|| {
                world
                    .registry
                    .concepts
                    .name(a.0 .0)
                    .cmp(world.registry.concepts.name(b.0 .0))
            })
    });
    found.into_iter().map(|(concept, _)| concept).collect()
}

pub fn mean_frequency(world: &World) -> f64 {
    let values: Vec<f64> = explicit_frequencies(world).iter().map(|f| f.1).collect();
    mean(&values)
}

pub fn variant_named(world: &World, name: &str) -> Option<VariantId> {
    world.registry.variants.get(name).map(VariantId)
}

/// Jméno proměnné události historie (`event["variable"]`).
pub fn text<'a>(event: &'a serde_json::Map<String, serde_json::Value>, key: &str) -> &'a str {
    event.get(key).and_then(|v| v.as_str()).unwrap_or("")
}

// --- šíření a přežití inovací (M1) --------------------------------------------------------

/// Jak dobře průběh šíření sedí na logistickou křivku (metrika 7); `None` při málo bodech.
pub fn logistic_r2(points: &[(f64, f64)]) -> Option<f64> {
    let inner: Vec<(f64, f64)> = points
        .iter()
        .copied()
        .filter(|&(_, value)| value > 0.01 && value < 0.99)
        .collect();
    if inner.len() < 4 {
        return None;
    }
    let first = inner[0].0;
    if inner.iter().all(|&(time, _)| time == first) {
        return None;
    }
    let times: Vec<f64> = inner.iter().map(|p| p.0).collect();
    let logits: Vec<f64> = inner.iter().map(|p| (p.1 / (1.0 - p.1)).ln()).collect();
    let (slope, intercept) = linear_fit(&times, &logits);
    let values: Vec<f64> = points.iter().map(|p| p.1).collect();
    let average = mean(&values);
    let total: f64 = values.iter().map(|v| (v - average).powi(2)).sum();
    if total == 0.0 {
        return None;
    }
    let residual: f64 = points
        .iter()
        .map(|&(time, value)| {
            let predicted = 1.0 / (1.0 + (-(slope * time + intercept)).exp());
            (value - predicted).powi(2)
        })
        .sum();
    Some(1.0 - residual / total)
}

/// Přímka metodou nejmenších čtverců: (sklon, úsek).
pub fn linear_fit(x: &[f64], y: &[f64]) -> (f64, f64) {
    let (mx, my) = (mean(x), mean(y));
    let sxx: f64 = x.iter().map(|v| (v - mx).powi(2)).sum();
    let sxy: f64 = x.iter().zip(y).map(|(a, b)| (a - mx) * (b - my)).sum();
    let slope = if sxx == 0.0 { 0.0 } else { sxy / sxx };
    (slope, my - slope * mx)
}

fn r_squared(x: &[f64], y: &[f64]) -> f64 {
    let (slope, intercept) = linear_fit(x, y);
    let my = mean(y);
    let total: f64 = y.iter().map(|v| (v - my).powi(2)).sum();
    if total == 0.0 {
        return 0.0;
    }
    let residual: f64 = x
        .iter()
        .zip(y)
        .map(|(a, b)| (b - (slope * a + intercept)).powi(2))
        .sum();
    1.0 - residual / total
}

fn correlation(x: &[f64], y: &[f64]) -> f64 {
    let (mx, my) = (mean(x), mean(y));
    let sxy: f64 = x.iter().zip(y).map(|(a, b)| (a - mx) * (b - my)).sum();
    let sxx: f64 = x.iter().map(|a| (a - mx).powi(2)).sum();
    let syy: f64 = y.iter().map(|b| (b - my).powi(2)).sum();
    if sxx == 0.0 || syy == 0.0 {
        return 0.0;
    }
    sxy / (sxx * syy).sqrt()
}

/// Podíl inovací, které se aspoň v jedné skupině ustálily (metrika 8).
pub fn establishment_fraction(history: &History) -> f64 {
    let innovations: BTreeSet<&str> = history
        .of_kind("innovation")
        .map(|event| text(event, "variant"))
        .collect();
    if innovations.is_empty() {
        return 0.0;
    }
    let established: BTreeSet<&str> = history
        .of_kind("established")
        .map(|event| text(event, "variant"))
        .filter(|variant| innovations.contains(variant))
        .collect();
    established.len() as f64 / innovations.len() as f64
}

/// Souvislost jazykové a zeměpisné vzdálenosti (metrika 9, Séguyho zákon).
#[derive(Clone, Copy, Debug)]
pub struct DistanceFit {
    pub correlation: f64,
    pub r2_linear: f64,
    pub r2_log: f64,
}

impl DistanceFit {
    pub fn sublinear(&self) -> bool {
        self.r2_log >= self.r2_linear
    }
}

/// `distances` je čtvercová matice po řádcích (`Snapshot::distances`), `positions` poloha skupin.
pub fn isolation_by_distance(distances: &[f64], positions: &[(f64, f64)]) -> DistanceFit {
    let n = positions.len();
    let (mut linguistic, mut geographic) = (Vec::new(), Vec::new());
    for first in 0..n {
        for second in first + 1..n {
            linguistic.push(distances[first * n + second]);
            geographic.push(
                (positions[first].0 - positions[second].0)
                    .hypot(positions[first].1 - positions[second].1),
            );
        }
    }
    let deviation = {
        let m = mean(&linguistic);
        (linguistic.iter().map(|v| (v - m).powi(2)).sum::<f64>() / linguistic.len() as f64).sqrt()
    };
    let corr = if deviation > 0.0 {
        correlation(&geographic, &linguistic)
    } else {
        0.0
    };
    let logs: Vec<f64> = geographic.iter().map(|d| d.ln()).collect();
    DistanceFit {
        correlation: corr,
        r2_linear: r_squared(&geographic, &linguistic),
        r2_log: r_squared(&logs, &linguistic),
    }
}

// --- zvuk (M2, metriky 3 až 6) --------------------------------------------------------------

/// Podoba slovní zásoby jedné skupiny (z podkladových tvarů, viz hlavička modulu).
#[derive(Clone, Copy, Debug)]
pub struct LexiconProfile {
    pub mean_length: f64,
    pub consonants: usize,
    pub vowels: usize,
    /// Podíl pojmů, jejichž dominantní slovo zní stejně jako slovo jiného kořene.
    pub homophony: f64,
    pub tones: usize,
}

/// Podíl pojmů, které skupina pořád vyjadřuje zděděným slovem (metrika 1).
pub fn retention(world: &World, group: GroupId) -> f64 {
    let (mut kept, mut total) = (0_u32, 0_u32);
    for (variable, _) in lexical_variables(world) {
        let Some((variant, _)) = world.dominant(group, variable) else {
            continue;
        };
        total += 1;
        kept += u32::from(world.variants.origin[variant.index()].change.is_none());
    }
    if total == 0 {
        0.0
    } else {
        f64::from(kept) / f64::from(total)
    }
}

/// Povrchové tvary dominantních kořenů skupiny: pojem → tvar (`phonology.lexicon`).
pub fn lexicon_forms(world: &World, group: GroupId) -> BTreeMap<String, Vec<i32>> {
    let mut found = BTreeMap::new();
    for (variable, concept) in lexical_variables(world) {
        if let Some(root) = root_of(world, group, variable) {
            found.insert(
                world.registry.concepts.name(concept.0).to_owned(),
                crate::phonology::surface(world, group, root)
                    .unwrap_or_else(|_| world.form_of(group, root).to_vec()),
            );
        }
    }
    found
}

pub fn lexicon_profile(world: &World, group: GroupId) -> LexiconProfile {
    let table = world.table.as_ref().expect("tabulka hlásek");
    let mut forms: Vec<Vec<i32>> = Vec::new();
    let mut owners: HashMap<Vec<i32>, BTreeSet<MorphemeId>> = HashMap::new();
    for (variable, _) in lexical_variables(world) {
        if let Some(root) = root_of(world, group, variable) {
            let form = crate::phonology::surface(world, group, root)
                .unwrap_or_else(|_| world.form_of(group, root).to_vec());
            owners.entry(form.clone()).or_default().insert(root);
            forms.push(form);
        }
    }
    let inventory: BTreeSet<i32> = forms.iter().flatten().copied().collect();
    let vowels: BTreeSet<i32> = inventory
        .iter()
        .filter(|&&s| table.is_vowel(s))
        .map(|&s| table.with_tone(s, 0).unwrap_or(s))
        .collect();
    let consonants = inventory.iter().filter(|&&s| !table.is_vowel(s)).count();
    let tones: BTreeSet<u32> = inventory
        .iter()
        .filter(|&&s| table.is_vowel(s))
        .map(|&s| table.tone_of(s))
        .filter(|&t| t != 0)
        .collect();
    let shared = forms
        .iter()
        .filter(|form| owners.get(*form).is_some_and(|set| set.len() > 1))
        .count();
    let lengths: Vec<f64> = forms.iter().map(|f| f.len() as f64).collect();
    LexiconProfile {
        mean_length: if forms.is_empty() {
            0.0
        } else {
            mean(&lengths)
        },
        consonants,
        vowels: vowels.len(),
        tones: tones.len(),
        homophony: if forms.is_empty() {
            0.0
        } else {
            shared as f64 / forms.len() as f64
        },
    }
}

/// Procesní proměnné (jména), které se aspoň v jedné skupině ustálily.
pub fn established_processes(history: &History) -> BTreeSet<String> {
    history
        .of_kind("established")
        .map(|event| text(event, "variable"))
        .filter(|name| name.starts_with("process:"))
        .map(str::to_owned)
        .collect()
}

/// Hellingerova vzdálenost dvou rozdělení (0 = shodná, 1 = disjunktní).
pub fn hellinger(observed: &BTreeMap<String, f64>, expected: &BTreeMap<String, f64>) -> f64 {
    let keys: BTreeSet<&String> = observed.keys().chain(expected.keys()).collect();
    let p: Vec<f64> = keys
        .iter()
        .map(|k| observed.get(*k).copied().unwrap_or(0.0))
        .collect();
    let q: Vec<f64> = keys
        .iter()
        .map(|k| expected.get(*k).copied().unwrap_or(0.0))
        .collect();
    let (sp, sq): (f64, f64) = (p.iter().sum(), q.iter().sum());
    let sum: f64 = p
        .iter()
        .zip(&q)
        .map(|(a, b)| ((a / sp).sqrt() - (b / sq).sqrt()).powi(2))
        .sum();
    (0.5 * sum).sqrt()
}

// --- morfologie (M3) ---------------------------------------------------------------------

/// Stav paradigmat jedné skupiny.
#[derive(Clone, Copy, Debug)]
pub struct MorphologyProfile {
    pub alternation: f64,
    pub morphologized: f64,
    pub syncretism: f64,
    pub productive_share: f64,
    pub irregular_frequent: f64,
    pub irregular_rare: f64,
}

pub fn morphology_profile(world: &World, group: GroupId) -> MorphologyProfile {
    let stats = class_stats(world, group);
    let code = world.groups.main_code(group);
    let (mut cells, mut alternating, mut morphologized, mut syncretic) =
        (0_u32, 0_u32, 0_u32, 0_u32);
    let (mut frequent, mut rare): (Vec<f64>, Vec<f64>) = (Vec::new(), Vec::new());
    let mut keys: BTreeSet<(u32, u32)> = BTreeSet::new();
    for unit in code.phonology.vocabulary.iter() {
        let at = unit.index();
        if world.morphemes.kind[at] != MorphemeKind::Word {
            continue;
        }
        let (class, cell) = (world.morphemes.word_class[at], world.morphemes.cell[at]);
        if class.is_none() || cell.is_none() {
            continue;
        }
        let state = world.unit_of(group, unit);
        let lexeme = world.morphemes.lexeme_id(unit);
        let citation = world.unit_of(group, lexeme).form;
        let form = world.bank.form(state.form);
        let (stem, ending) = split(form, state.boundary);
        cells += 1;
        alternating += u32::from(stem != world.bank.form(citation));
        syncretic += u32::from(state.form == citation);
        morphologized += u32::from(ending.is_empty() && state.form != citation);
        let irregular = f64::from(u8::from(
            state.exponent.option() != stats.productive(class, cell),
        ));
        if world.morphemes.frequency[lexeme.index()] >= 0.5 {
            frequent.push(irregular);
        } else {
            rare.push(irregular);
        }
        if !state.exponent.is_none() {
            keys.insert((class.0, cell.0));
        }
    }
    let shares: Vec<f64> = keys
        .iter()
        .filter_map(|&(class, cell)| {
            let (class, cell) = (crate::ids::WordClassId(class), crate::ids::CellId(cell));
            stats
                .productive(class, cell)
                .map(|exponent| stats.share(class, cell, exponent))
        })
        .collect();
    let per = |count: u32| {
        if cells == 0 {
            0.0
        } else {
            f64::from(count) / f64::from(cells)
        }
    };
    let or_zero = |values: &[f64]| if values.is_empty() { 0.0 } else { mean(values) };
    MorphologyProfile {
        alternation: per(alternating),
        morphologized: per(morphologized),
        syncretism: per(syncretic),
        productive_share: or_zero(&shares),
        irregular_frequent: or_zero(&frequent),
        irregular_rare: or_zero(&rare),
    }
}

/// Podíl tvarů s menšinovou (nepravidelnou) koncovkou buňky (metrika 11).
pub fn morphological_complexity(world: &World, group: GroupId) -> f64 {
    1.0 - morphology_profile(world, group).productive_share
}

/// Spearmanova pořadová korelace (shody dostanou průměrné pořadí).
pub fn spearman(first: &[f64], second: &[f64]) -> f64 {
    fn ranks(values: &[f64]) -> Vec<f64> {
        let mut order: Vec<usize> = (0..values.len()).collect();
        order.sort_by(|&a, &b| {
            values[a]
                .partial_cmp(&values[b])
                .unwrap_or(std::cmp::Ordering::Equal)
        });
        let mut result = vec![0.0; values.len()];
        let mut start = 0;
        while start < order.len() {
            let mut end = start;
            while end + 1 < order.len() && values[order[end + 1]] == values[order[start]] {
                end += 1;
            }
            let average = (start + end) as f64 / 2.0;
            for &index in &order[start..=end] {
                result[index] = average;
            }
            start = end + 1;
        }
        result
    }
    let (a, b) = (ranks(first), ranks(second));
    let flat = |v: &[f64]| v.iter().all(|x| *x == v[0]);
    if a.is_empty() || flat(&a) || flat(&b) {
        return 0.0;
    }
    correlation(&a, &b)
}

// --- stopy jazyka po kontaktu (M5, M6) -----------------------------------------------------

const TRACE_KINDS: [VariableKind; 3] = [
    VariableKind::Lexical,
    VariableKind::Process,
    VariableKind::Construction,
];

/// Proměnné, ve kterých má skupina jinou převládající variantu než reference.
pub fn distinctive_variants(
    world: &World,
    group: GroupId,
    reference: GroupId,
) -> BTreeMap<VariableId, (VariableKind, VariantId)> {
    let mut found = BTreeMap::new();
    for variable in 0..world.variables.len() {
        let kind = world.variables.kind[variable];
        if !TRACE_KINDS.contains(&kind) {
            continue;
        }
        let id = VariableId::new(variable);
        let (Some(own), Some(other)) = (world.dominant(group, id), world.dominant(reference, id))
        else {
            continue;
        };
        if own.0 != other.0 {
            found.insert(id, (kind, own.0));
        }
    }
    found
}

/// Průměrný podíl daných variant ve skupině podle druhu proměnné.
pub fn trace_shares(
    world: &World,
    group: GroupId,
    variants: &BTreeMap<VariableId, (VariableKind, VariantId)>,
) -> BTreeMap<VariableKind, f64> {
    let mut shares: BTreeMap<VariableKind, Vec<f64>> = BTreeMap::new();
    for (&variable, &(kind, variant)) in variants {
        let share = world
            .distribution(group, variable)
            .map_or(0.0, |d| d.frequency(variant));
        shares.entry(kind).or_default().push(share);
    }
    shares.into_iter().map(|(k, v)| (k, mean(&v))).collect()
}

/// Součet vzdáleností dvou kódů přes druhy proměnných (scénář S4); jednotlivé druhy zvlášť.
pub fn code_distance(
    world: &World,
    first: GroupId,
    second: GroupId,
) -> BTreeMap<VariableKind, f64> {
    let lexical = (0..world.variables.len())
        .filter(|&v| world.variables.kind[v] == VariableKind::Lexical)
        .count();
    let mut totals: BTreeMap<VariableKind, f64> = TRACE_KINDS.iter().map(|&k| (k, 0.0)).collect();
    for variable in 0..world.variables.len() {
        let kind = world.variables.kind[variable];
        let Some(total) = totals.get_mut(&kind) else {
            continue;
        };
        let id = VariableId::new(variable);
        let (Some(a), Some(b)) = (
            world.distribution(first, id),
            world.distribution(second, id),
        ) else {
            continue;
        };
        let variants: BTreeSet<VariantId> = a
            .variants
            .iter()
            .chain(b.variants.iter())
            .copied()
            .collect();
        *total += 0.5
            * variants
                .iter()
                .map(|&v| (a.frequency(v) - b.frequency(v)).abs())
                .sum::<f64>();
    }
    let divisor = lexical.max(1) as f64;
    totals.into_iter().map(|(k, t)| (k, t / divisor)).collect()
}

/// Součet přes druhy (`sum(code_distance(...).values())`).
pub fn total_distance(world: &World, first: GroupId, second: GroupId) -> f64 {
    code_distance(world, first, second).values().sum()
}

/// Počet dominantních kořenů skupiny z jazyka `language` (jméno linie).
pub fn roots_of_language(world: &World, group: GroupId, language: &str) -> usize {
    let Some(id) = world.registry.languages.get(language) else {
        return 0;
    };
    dominant_roots(world, group)
        .iter()
        .filter(|(_, root)| world.morphemes.language[root.index()].0 == id)
        .count()
}

/// Výpůjčky skupiny: pojem → kořen jiného jazyka, než je jazyk kódu.
pub fn loans(world: &World, group: GroupId) -> Vec<(ConceptId, MorphemeId)> {
    let language = world.groups.main_code(group).language;
    dominant_roots(world, group)
        .into_iter()
        .filter(|(_, root)| world.morphemes.language[root.index()] != language)
        .collect()
}
