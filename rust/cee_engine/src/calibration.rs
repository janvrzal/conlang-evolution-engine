//! Kalibrace M7: měřidla cílů a běh variant parametrů (`cee calibrate`, dokument 22).
//!
//! Brány milníků ([`crate::gates`]) říkají, zda model *umí* jev a zda ho drží ve věrohodném
//! rozsahu. Kalibrace se ptá jemněji: jak daleko je model od cílové hodnoty z literatury a
//! která varianta metaparametrů ji přiblíží. Cíle jsou data v
//! `src/cee/data/v2_calibration_targets.json` (stav „návrh“); každý cíl patří k jednomu
//! **kalibračnímu běhu** (scénář, délka, co se měří) a má jeden ze tří druhů:
//!
//! - **pásmo**: veličina na `N` semínkách; cíl je splněný, když **medián** leží v pásmu
//!   (přísnější než brána, kde stačí překryv intervalu); výpis uvádí i 95% bootstrapový
//!   interval mediánu;
//! - **typologie**: rozložení stavů rysu WALS přes jazyky všech semínek dohromady (jako část A
//!   v dokumentu 10). Start se losuje z WALS; cíl je splněný, když Hellingerova vzdálenost
//!   konečného rozložení od WALS nepřekročí 95% kvantil vzdálenosti, kterou by dal stejně velký
//!   náhodný vzorek přímo z WALS (stacionarita do šumu vzorku);
//! - **informace**: veličina se jen vypíše (chybí cíl, který by se dal z dat poctivě určit).
//!
//! Varianty parametrů se podstrčí přes [`with_defaults`]: scénáře berou výchozí parametry při
//! stavbě světa, takže varianta platí pro všechny světy jednoho běhu. Semínka běží souběžně
//! (výsledek semínka na počtu vláken nezávisí).

use std::collections::BTreeMap;
use std::fmt::Write as _;
use std::io::Write as _;
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::sync::OnceLock;

use rayon::prelude::*;
use serde::Deserialize;
use serde_json::{json, Map, Value};

use crate::gates::metrics::{
    group_named, hellinger, lexicon_forms, mean, morphology_profile, spearman,
};
use crate::gates::statistical::{bootstrap_median_interval, median_of, metric_value};
use crate::gates::{m3b, m5, Cmp, Report};
use crate::grammar::profile::Grammar;
use crate::grammar::Construction;
use crate::model::code::StressRule;
use crate::parameters::{with_defaults, Parameters};
use crate::rng::{Part, Stream};
use crate::scenarios::{village_grid_default, SeedOptions};
use crate::{prosody, syntax, Simulation, SimulationConfig};

/// Cíle kalibrace jako data (vložená při sestavení).
pub const TARGETS_JSON: &str = include_str!("../../../src/cee/data/v2_calibration_targets.json");
/// Referenční rozložení WALS (výřez z `scripts/build_v2_typology.py`).
pub const TYPOLOGY_JSON: &str = include_str!("../../../src/cee/data/v2_typology.json");

/// Počet losování nulového rozdělení Hellingerovy vzdálenosti.
const NULL_DRAWS: usize = 4000;

// --- cíle -----------------------------------------------------------------------------------

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq)]
pub enum Kind {
    #[serde(rename = "pásmo")]
    Band,
    #[serde(rename = "typologie")]
    Typology,
    #[serde(rename = "informace")]
    Info,
    /// Jev nastal aspoň v `k` z `N` běhů (`k` z `p_min` jako u bran, falešný poplach ≤ 1 %).
    #[serde(rename = "možnost")]
    Possibility,
}

impl Kind {
    pub fn label(self) -> &'static str {
        match self {
            Kind::Band => "pásmo",
            Kind::Typology => "typologie",
            Kind::Info => "informace",
            Kind::Possibility => "možnost",
        }
    }
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Measure {
    pub label: String,
    pub metric: String,
    #[serde(default)]
    pub band: Option<[f64; 2]>,
    #[serde(default)]
    pub reference: Option<f64>,
    pub support: String,
    pub source: String,
    pub conversion: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Target {
    pub id: String,
    pub run: String,
    pub kind: Kind,
    pub n: usize,
    /// Rys WALS (`33A`) u typologie.
    #[serde(default)]
    pub feature: Option<String>,
    #[serde(default)]
    pub measures: Vec<Measure>,
    #[serde(default)]
    pub support: String,
    #[serde(default)]
    pub source: String,
    #[serde(default)]
    pub note: String,
    /// U „možnosti“: nejnižší skutečná míra jevu, při které cíl ještě nemá selhat.
    #[serde(default)]
    pub p_min: f64,
    /// U „možnosti“: jev = metrika reportu ve vztahu `op` k hodnotě (`>=`, `<=`, `>`, `<`, `==`).
    #[serde(default)]
    pub event: Option<Event>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Event {
    pub label: String,
    pub metric: String,
    pub op: String,
    pub value: f64,
    pub support: String,
    pub source: String,
}

impl Event {
    fn holds(&self, report: &Report) -> bool {
        let v = metric_value(report, &self.metric);
        match self.op.as_str() {
            ">=" => v >= self.value,
            "<=" => v <= self.value,
            ">" => v > self.value,
            "<" => v < self.value,
            "==" => v == self.value,
            _ => false,
        }
    }
}

#[derive(Debug, Deserialize)]
pub struct Targets {
    pub status: String,
    #[serde(default)]
    pub popis: String,
    pub targets: Vec<Target>,
}

impl Targets {
    pub fn shared() -> Result<Targets, String> {
        let targets: Targets = serde_json::from_str(TARGETS_JSON)
            .map_err(|e| format!("v2_calibration_targets.json: {e}"))?;
        targets.check()?;
        Ok(targets)
    }

    fn check(&self) -> Result<(), String> {
        for target in &self.targets {
            if runs().iter().all(|run| run.id != target.run) {
                return Err(format!("{}: neznámý běh {}", target.id, target.run));
            }
            match target.kind {
                Kind::Typology => {
                    let feature = target.feature.as_deref().unwrap_or("");
                    if !TYPOLOGY_FEATURES.contains(&feature) {
                        return Err(format!("{}: neznámý rys {feature}", target.id));
                    }
                }
                Kind::Band if target.measures.iter().any(|m| m.band.is_none()) => {
                    return Err(format!("{}: pásmo bez meze", target.id));
                }
                Kind::Possibility
                    if target.event.is_none() || !(target.p_min > 0.0 && target.p_min < 1.0) =>
                {
                    return Err(format!("{}: možnost chce event a 0 < p_min < 1", target.id));
                }
                _ => {}
            }
        }
        Ok(())
    }
}

// --- typologie ------------------------------------------------------------------------------

/// Rysy WALS, které měřidlo umí zařadit (dokument 10, tabulka A1).
pub const TYPOLOGY_FEATURES: [&str; 7] = ["33A", "37A", "66A", "67A", "81A", "143A", "14A"];

/// Referenční rozložení rysu: `engine_distribution` (podmíněné na stavy, které model vyjádří).
pub fn reference(feature: &str) -> Option<&'static BTreeMap<String, f64>> {
    static TABLE: OnceLock<BTreeMap<String, BTreeMap<String, f64>>> = OnceLock::new();
    TABLE
        .get_or_init(|| {
            let data: Value = serde_json::from_str(TYPOLOGY_JSON).expect("v2_typology.json");
            TYPOLOGY_FEATURES
                .iter()
                .filter_map(|&f| {
                    let distribution = data["features"][f]["engine_distribution"].as_object()?;
                    let map = distribution
                        .iter()
                        .filter_map(|(k, v)| Some((k.clone(), v.as_f64()?)))
                        .collect();
                    Some((f.to_owned(), map))
                })
                .collect()
        })
        .get(feature)
}

/// Stav z rozložení podle jednoho tahu `u` z `[0, 1)` (klíče v pevném pořadí).
fn draw(distribution: &BTreeMap<String, f64>, u: f64) -> &str {
    let total: f64 = distribution.values().sum();
    let mut acc = 0.0;
    for (state, weight) in distribution {
        acc += weight / total;
        if u < acc {
            return state;
        }
    }
    distribution.keys().last().map_or("", String::as_str)
}

const ORDERS: [&str; 6] = ["SOV", "SVO", "VSO", "VOS", "OVS", "OSV"];

/// Gramatika a pravidlo přízvuku protojazyka losované z WALS (vlastní proud na rys).
pub fn wals_start(seed: i64) -> (Grammar, StressRule) {
    let pick = |feature: &str| {
        let mut rng = Stream::new(
            seed as u64,
            &[Part::Str("typology-wals-start"), Part::Str(feature)],
        );
        let reference = reference(feature).expect("rys WALS");
        draw(reference, rng.random()).to_owned()
    };
    let present = |state: String, function: &str, kind: &str| {
        if state.ends_with("_present") {
            Construction::new(function, kind)
        } else {
            Construction::new(function, "zero")
        }
    };
    let past = present(pick("66A"), "PAST", "synthetic");
    let plural = present(pick("33A"), "PL", "synthetic");
    let definite = if pick("37A") == "definite_present" {
        let mut c = Construction::new("DEFINITE", "periphrastic").with_source("this");
        c.stage = Some("free".into());
        c
    } else {
        Construction::new("DEFINITE", "zero")
    };
    let future = if pick("67A") == "67A-1" {
        Construction::new("FUTURE", "synthetic")
    } else {
        Construction::new("FUTURE", "zero")
    };
    let negation = match pick("143A").as_str() {
        "143A-2" => Construction::new("NEG", "post").with_source("not"),
        "143A-14" => {
            let mut c = Construction::new("NEG", "embraced").with_source("not");
            c.reinforcer = Some("thing".into());
            c
        }
        _ => Construction::new("NEG", "pre").with_source("not"),
    };
    let order_state = pick("81A");
    let index = order_state
        .strip_prefix("81A-")
        .and_then(|k| k.parse::<usize>().ok())
        .filter(|k| (1..=6).contains(k))
        .unwrap_or(1);
    let order = Construction::new("ORDER", "fixed").with_order(ORDERS[index - 1]);
    let stress = match pick("14A").as_str() {
        "14A-2" => StressRule::Initial,
        "14A-3" => StressRule::Second,
        "14A-5" => StressRule::Antepenult,
        "14A-7" => StressRule::Final,
        _ => StressRule::Penult,
    };
    let grammar = vec![
        ("PAST", past),
        ("FUTURE", future),
        ("PL", plural),
        ("OBJ", Construction::new("OBJ", "synthetic")),
        ("DEFINITE", definite),
        ("ASPECT", Construction::new("ASPECT", "zero")),
        ("NEG", negation),
        ("ORDER", order),
    ];
    (grammar, stress)
}

/// Stav rysu v jedné skupině; `None` = model stav nevyjádří (neznámý, ne kategorie).
fn group_state(
    world: &crate::world::World,
    group: crate::ids::GroupId,
    feature: &str,
) -> Option<String> {
    let construction = |function: &str| syntax::dominant(world, group, function);
    let presence = |function: &str, prefix: &str| {
        construction(function).and_then(|c| match c.kind.as_str() {
            "synthetic" | "periphrastic" => Some(format!("{prefix}_present")),
            "zero" => Some(format!("{prefix}_absent")),
            _ => None,
        })
    };
    match feature {
        "33A" => presence("PL", "plural"),
        "37A" => presence("DEFINITE", "definite"),
        "66A" => presence("PAST", "past"),
        "67A" => construction("FUTURE").map(|c| {
            if c.kind == "synthetic" {
                "67A-1"
            } else {
                "67A-2"
            }
            .to_owned()
        }),
        "81A" => construction("ORDER").and_then(|c| {
            if c.kind != "fixed" {
                return None;
            }
            let order = c.order.as_deref()?;
            ORDERS
                .iter()
                .position(|o| *o == order)
                .map(|i| format!("81A-{}", i + 1))
        }),
        "143A" => construction("NEG").and_then(|c| match c.kind.as_str() {
            "pre" => Some("143A-1".to_owned()),
            "post" => Some("143A-2".to_owned()),
            "embraced" => Some("143A-14".to_owned()),
            _ => None,
        }),
        "14A" => Some(
            match prosody::dominant_rule(world, group) {
                StressRule::Initial => "14A-2",
                StressRule::Second => "14A-3",
                StressRule::Antepenult => "14A-5",
                StressRule::Penult => "14A-6",
                StressRule::Final => "14A-7",
            }
            .to_owned(),
        ),
        _ => None,
    }
}

/// Podíl samohlásek s tónem ve slovníku skupiny (výskyty v podkladových tvarech).
fn tone_share(world: &crate::world::World, group: crate::ids::GroupId) -> f64 {
    let Some(table) = world.table.as_ref() else {
        return f64::NAN;
    };
    let (mut vowels, mut toned) = (0usize, 0usize);
    for form in lexicon_forms(world, group).values() {
        for &segment in form {
            if table.is_vowel(segment) {
                vowels += 1;
                toned += usize::from(table.tone_of(segment) != 0);
            }
        }
    }
    if vowels == 0 {
        f64::NAN
    } else {
        toned as f64 / vowels as f64
    }
}

/// Zapíše do reportu počty jazyků podle stavu rysů (`"<předpona> 33A plural_present"`) a podíl
/// samohlásek s tónem. Jednotkou je jazyk (`languages`: linie → skupiny); stav jazyka je
/// převládající stav jeho skupin vážený počtem mluvčích (dokument 10, protokol části A).
fn record_typology(
    simulation: &Simulation,
    languages: &BTreeMap<String, Vec<String>>,
    prefix: &str,
    report: &mut Report,
) {
    let world = &simulation.world;
    let mut shares = Vec::new();
    for groups in languages.values() {
        let members: Vec<_> = groups
            .iter()
            .filter_map(|name| group_named(world, name))
            .collect();
        let weight = |g: crate::ids::GroupId| f64::from(world.groups.population[g.index()]);
        for feature in TYPOLOGY_FEATURES {
            let mut votes: BTreeMap<String, f64> = BTreeMap::new();
            for &g in &members {
                if let Some(state) = group_state(world, g, feature) {
                    *votes.entry(state).or_default() += weight(g);
                }
            }
            if let Some((state, _)) = votes
                .into_iter()
                .max_by(|a, b| a.1.total_cmp(&b.1).then_with(|| b.0.cmp(&a.0)))
            {
                let name = format!("{prefix} {feature} {state}");
                let previous = metric_value(report, &name);
                report.metrics.retain(|m| m.name != name);
                let count = if previous.is_nan() {
                    1.0
                } else {
                    previous + 1.0
                };
                info(report, &name, count);
            }
        }
        let total: f64 = members.iter().map(|&g| weight(g)).sum();
        let toned: f64 = members
            .iter()
            .map(|&g| tone_share(world, g) * weight(g))
            .filter(|v| !v.is_nan())
            .sum();
        if total > 0.0 {
            shares.push(toned / total);
        }
    }
    info(report, &format!("{prefix} jazyků"), languages.len() as f64);
    info(
        report,
        &format!("{prefix} podíl samohlásek s tónem"),
        mean(&shares),
    );
}

/// Zapíše hodnotu bez prahu (kalibrace prahy reportu nepoužívá).
fn info(report: &mut Report, name: &str, value: f64) {
    report.check(name, value, Cmp::Ge, f64::NEG_INFINITY);
}

/// Počty stavů rysu přes reporty všech semínek (`"<předpona> <rys> <stav>"`).
fn pooled(reports: &[&Report], prefix: &str, feature: &str) -> BTreeMap<String, f64> {
    let head = format!("{prefix} {feature} ");
    let mut counts: BTreeMap<String, f64> = BTreeMap::new();
    for report in reports {
        for metric in &report.metrics {
            if let Some(state) = metric.name.strip_prefix(&head) {
                *counts.entry(state.to_owned()).or_default() += metric.value;
            }
        }
    }
    counts
}

/// 95% kvantil Hellingerovy vzdálenosti vzorku `n` jazyků taženého přímo z `reference`.
pub fn null_quantile(reference: &BTreeMap<String, f64>, n: usize, salt: &str) -> f64 {
    if n == 0 {
        return f64::NAN;
    }
    let mut rng = Stream::new(0, &[Part::Str("calibration-null"), Part::Str(salt)]);
    let mut distances: Vec<f64> = (0..NULL_DRAWS)
        .map(|_| {
            let mut sample: BTreeMap<String, f64> = BTreeMap::new();
            for _ in 0..n {
                *sample
                    .entry(draw(reference, rng.random()).to_owned())
                    .or_default() += 1.0;
            }
            hellinger(&sample, reference)
        })
        .collect();
    distances.sort_by(f64::total_cmp);
    distances[(0.95 * (NULL_DRAWS - 1) as f64).round() as usize]
}

/// Normovaná entropie s pevným jmenovatelem (počet kategorií rysu v referenci).
pub fn entropy(counts: &BTreeMap<String, f64>, categories: usize) -> f64 {
    let total: f64 = counts.values().sum();
    if total <= 0.0 || categories < 2 {
        return f64::NAN;
    }
    let h: f64 = counts
        .values()
        .filter(|&&c| c > 0.0)
        .map(|&c| {
            let p = c / total;
            -p * p.ln()
        })
        .sum();
    h / (categories as f64).ln()
}

// --- kalibrační běhy ------------------------------------------------------------------------

/// Kalibrační běh: scénář jednoho semínka a report naměřených veličin.
pub struct Run {
    pub id: &'static str,
    pub description: &'static str,
    pub measure: fn(i64) -> Result<Report, String>,
}

/// Délka typologického běhu v letech (dokument 10: odečet 5 000 let).
pub const TYPOLOGY_YEARS: f64 = 5000.0;

fn typology(seed: i64) -> Result<Report, String> {
    let (grammar, stress) = wals_start(seed);
    let options = SeedOptions {
        phonology: true,
        morphology: true,
        semantics: true,
        syntax: true,
        prosody: true,
        stress_rule: stress,
        grammar: Some(grammar),
        ..SeedOptions::default()
    };
    let world = village_grid_default(6, 1, seed, &options)?;
    let mut simulation = Simulation::new(world, SimulationConfig::default(), Vec::new())?;
    let mut report = Report::new();
    // Na startu mluví všech šest vesnic jedním protojazykem (snímek ještě není).
    let start: BTreeMap<String, Vec<String>> = BTreeMap::from([(
        "proto".to_owned(),
        simulation
            .world
            .group_ids()
            .into_iter()
            .map(|g| simulation.world.group_name(g).to_owned())
            .collect(),
    )]);
    record_typology(&simulation, &start, "start", &mut report);
    simulation.run(TYPOLOGY_YEARS)?;
    let end = simulation
        .history
        .snapshots
        .last()
        .map(|s| s.languages.clone())
        .ok_or("chybí snímek po běhu")?;
    record_typology(&simulation, &end, "konec", &mut report);
    record_erosion(&simulation, &mut report);
    Ok(report)
}

/// Rodiny zvukových změn konce slova, které mohou oslabit koncovku.
const FINAL_FAMILIES: [&str; 3] = ["coda_loss", "apocope", "hiatus_elision"];
/// Funkce, jejichž syntetická koncovka může zeslábnout.
const ERODIBLE: [&str; 5] = ["PL", "PAST", "OBJ", "FUTURE", "DEFINITE"];

/// Diagnostika eroze koncovek (M7.2): kolik změn konce slova se navrhlo, ustálilo
/// a zfonologizovalo, a průměrná slabost syntetických koncovek po běhu.
fn record_erosion(simulation: &Simulation, report: &mut Report) {
    let history = &simulation.history;
    let mut family_of: BTreeMap<String, String> = BTreeMap::new();
    for event in history.of_kind("innovation") {
        let change = event.get("change").and_then(Value::as_str).unwrap_or("");
        if FINAL_FAMILIES.contains(&change) {
            *report_count(report, &format!("eroze návrhy {change}")) += 1.0;
            if let Some(variant) = event.get("variant").and_then(Value::as_str) {
                family_of.insert(variant.to_owned(), change.to_owned());
            }
        }
    }
    for event in history.of_kind("established") {
        let variant = event.get("variant").and_then(Value::as_str).unwrap_or("");
        if let Some(family) = family_of.get(variant) {
            *report_count(report, &format!("eroze ustálené {family}")) += 1.0;
        }
    }
    for event in history.of_kind("phonologized") {
        let variable = event.get("variable").and_then(Value::as_str).unwrap_or("");
        for family in FINAL_FAMILIES {
            if variable.starts_with(&format!("process:{family}|")) {
                *report_count(report, &format!("eroze zfonologizované {family}")) += 1.0;
            }
        }
    }
    let world = &simulation.world;
    for function in ERODIBLE {
        let values: Vec<f64> = world
            .group_ids()
            .into_iter()
            .filter(|&g| {
                syntax::dominant(world, g, function).is_some_and(|c| c.kind == "synthetic")
            })
            .map(|g| syntax::weakness(world, g, function))
            .collect();
        if !values.is_empty() {
            info(report, &format!("eroze slabost {function}"), mean(&values));
        }
    }
}

/// Počítadlo v reportu (metrika se založí s nulou).
fn report_count<'a>(report: &'a mut Report, name: &str) -> &'a mut f64 {
    if !report.metrics.iter().any(|m| m.name == name) {
        info(report, name, 0.0);
    }
    let metric = report
        .metrics
        .iter_mut()
        .find(|m| m.name == name)
        .expect("metrika");
    &mut metric.value
}

fn lexicon(seed: i64) -> Result<Report, String> {
    Ok(m3b::check_metrika_1(&m3b::run_m3b(seed)?))
}

fn region(seed: i64) -> Result<Report, String> {
    let mut simulation = Simulation::new(
        crate::behavior::square_world(seed)?,
        SimulationConfig::default(),
        Vec::new(),
    )?;
    simulation.run(3000.0)?;
    let measured = crate::behavior::region_measure(&simulation);
    let mut report = Report::new();
    for (key, name) in [
        ("near", "sousedé v regionu"),
        ("across", "sousedé přes hranici regionu"),
        ("far", "vzdálené regiony"),
    ] {
        info(
            &mut report,
            name,
            measured[key].as_f64().unwrap_or(f64::NAN),
        );
    }
    let languages = simulation
        .history
        .snapshots
        .last()
        .map_or(0, |s| s.languages.len());
    info(&mut report, "počet jazyků", languages as f64);
    Ok(report)
}

fn complexity(seed: i64) -> Result<Report, String> {
    let (simulation, places) = m5::run_metrika_11(seed)?;
    let mut report = m5::check_metrika_11(&simulation, &places);
    let world = &simulation.world;
    // Trudgill: kořenová alternace podle populace při pevném podílu L2 (průměr Spearmanů).
    let mut levels: Vec<f64> = places.iter().map(|p| p.2).collect();
    levels.sort_by(f64::total_cmp);
    levels.dedup();
    let values: Vec<f64> = levels
        .iter()
        .map(|&level| {
            let chosen: Vec<&(String, u32, f64)> = places.iter().filter(|p| p.2 == level).collect();
            let x: Vec<f64> = chosen.iter().map(|p| f64::from(p.1)).collect();
            let y: Vec<f64> = chosen
                .iter()
                .map(|p| {
                    group_named(world, &p.0)
                        .map_or(f64::NAN, |g| morphology_profile(world, g).alternation)
                })
                .collect();
            spearman(&x, &y)
        })
        .collect();
    info(
        &mut report,
        "korelace kořenové alternace s populací při pevném podílu L2",
        mean(&values),
    );
    Ok(report)
}

// --- Romania (M7.3) -------------------------------------------------------------------------

/// Popis světa Romanie: latina ve čtyřech větvích od roku 100 př. n. l. (dok. 22, M7.3).
pub const ROMANIA_JSON: &str = include_str!("../../../src/cee/data/scenarios/romania.json");
/// Větve (regiony) Romanie a roky odečtu.
pub const ROMANIA_BRANCHES: [&str; 4] = ["italia", "gallia", "hispania", "dacia"];
pub const ROMANIA_YEARS: [f64; 7] = [100.0, 250.0, 400.0, 600.0, 1200.0, 1300.0, 1900.0];

/// Všechny skupiny větve (vesnice regionu; region je rodič území vesnice).
fn region_groups(world: &crate::world::World, branch: &str) -> Vec<crate::ids::GroupId> {
    world
        .group_ids()
        .into_iter()
        .filter(|&g| {
            let territory = world.groups.territory[g.index()];
            let parent = world.territories[territory.index()].parent;
            !parent.is_none() && world.registry.territories.name(parent.0) == branch
        })
        .collect()
}

/// Je hlavní kód skupiny z linie latiny?
fn latin_speaking(world: &crate::world::World, group: crate::ids::GroupId) -> bool {
    world
        .registry
        .languages
        .name(world.groups.main_code(group).language.0)
        == "latin"
}

/// Latinsky mluvící skupiny větve (v provincii ty, které na latinu přešly).
fn branch_groups(world: &crate::world::World, branch: &str) -> Vec<crate::ids::GroupId> {
    region_groups(world, branch)
        .into_iter()
        .filter(|&g| latin_speaking(world, g))
        .collect()
}

/// Převládající konstrukce funkce ve větvi (vážená mluvčími).
fn branch_construction(
    world: &crate::world::World,
    groups: &[crate::ids::GroupId],
    function: &str,
) -> Option<Construction> {
    let mut votes: BTreeMap<String, (f64, Construction)> = BTreeMap::new();
    for &g in groups {
        if let Some(c) = syntax::dominant(world, g, function) {
            let entry = votes.entry(c.key()).or_insert((0.0, c));
            entry.0 += f64::from(world.groups.population[g.index()]);
        }
    }
    votes
        .into_values()
        .max_by(|a, b| a.0.total_cmp(&b.0))
        .map(|(_, c)| c)
}

/// Odečet jedné větve v jednom roce: stav pádu, `-m`, člen, futurum, slovosled, zápor,
/// retence a koncové samohlásky.
fn record_branch(simulation: &Simulation, branch: &str, year: f64, report: &mut Report) {
    let world = &simulation.world;
    let tag = format!("{branch} {year:.0}");
    let everyone = region_groups(world, branch);
    let population = |list: &[crate::ids::GroupId]| -> f64 {
        list.iter()
            .map(|&g| f64::from(world.groups.population[g.index()]))
            .sum()
    };
    let groups = branch_groups(world, branch);
    let total = population(&everyone);
    info(
        report,
        &format!("{tag} podíl mluvčích latiny"),
        if total > 0.0 {
            population(&groups) / total
        } else {
            f64::NAN
        },
    );
    if groups.is_empty() {
        return;
    }
    let mean_of = |f: &dyn Fn(crate::ids::GroupId) -> f64| {
        let values: Vec<f64> = groups
            .iter()
            .map(|&g| f(g))
            .filter(|v| !v.is_nan())
            .collect();
        mean(&values)
    };
    let kind = |function: &str| branch_construction(world, &groups, function);
    // Pád: předmět vyjádřený koncovkou a jeho slabost (splynutí s citačním tvarem).
    let obj = kind("OBJ");
    info(
        report,
        &format!("{tag} pád"),
        f64::from(u8::from(
            obj.as_ref().is_some_and(|c| c.kind == "synthetic"),
        )),
    );
    info(
        report,
        &format!("{tag} slabost předmětu"),
        mean_of(&|g| syntax::weakness(world, g, "OBJ")),
    );
    // Koncové -m: podíl tvarů buňky OBJ, které končí na m.
    let m_share = mean_of(&|g| final_m_share(world, g));
    info(report, &format!("{tag} tvary předmětu s -m"), m_share);
    info(
        report,
        &format!("{tag} člen"),
        f64::from(u8::from(kind("DEFINITE").is_some_and(|c| c.kind != "zero"))),
    );
    let future = kind("FUTURE");
    let future_state = match &future {
        Some(c) if c.kind == "synthetic" && c.exponent.is_none() && c.donor.is_none() => 0.0,
        Some(c) if c.kind == "synthetic" => 2.0,
        Some(c) if c.kind == "periphrastic" => 1.0,
        _ => -1.0,
    };
    info(report, &format!("{tag} futurum"), future_state);
    let order = kind("ORDER");
    info(
        report,
        &format!("{tag} pevné SVO"),
        f64::from(u8::from(order.as_ref().is_some_and(|c| {
            c.kind == "fixed" && c.order.as_deref() == Some("SVO")
        }))),
    );
    info(
        report,
        &format!("{tag} pevný slovosled"),
        f64::from(u8::from(order.as_ref().is_some_and(|c| c.kind == "fixed"))),
    );
    let negation = kind("NEG");
    info(
        report,
        &format!("{tag} zápor před slovesem"),
        f64::from(u8::from(negation.as_ref().is_some_and(|c| c.kind == "pre"))),
    );
    info(
        report,
        &format!("{tag} dvojitý zápor"),
        f64::from(u8::from(
            negation.as_ref().is_some_and(|c| c.kind == "embraced"),
        )),
    );
    info(
        report,
        &format!("{tag} retence"),
        mean_of(&|g| crate::gates::metrics::retention(world, g)),
    );
    info(
        report,
        &format!("{tag} slova na samohlásku"),
        mean_of(&|g| vowel_final_share(world, g)),
    );
}

/// Podíl tvarů buňky OBJ (slova třídy noun), které končí na `m`.
fn final_m_share(world: &crate::world::World, group: crate::ids::GroupId) -> f64 {
    let (Some(table), Some(cell)) = (world.table.as_ref(), world.registry.cells.get("OBJ")) else {
        return f64::NAN;
    };
    let Ok(m) = table.parse("m") else {
        return f64::NAN;
    };
    let code = world.groups.main_code(group);
    let (mut total, mut with_m) = (0usize, 0usize);
    for unit in code.phonology.vocabulary.iter() {
        if world.morphemes.cell[unit.index()].0 != cell {
            continue;
        }
        let form = world.form_of(group, unit);
        total += 1;
        with_m += usize::from(form.last() == m.first());
    }
    if total == 0 {
        f64::NAN
    } else {
        with_m as f64 / total as f64
    }
}

/// Podíl citačních tvarů slovníku, které končí samohláskou.
fn vowel_final_share(world: &crate::world::World, group: crate::ids::GroupId) -> f64 {
    let Some(table) = world.table.as_ref() else {
        return f64::NAN;
    };
    let forms = lexicon_forms(world, group);
    if forms.is_empty() {
        return f64::NAN;
    }
    let vowel_final = forms
        .values()
        .filter(|f| f.last().is_some_and(|&s| table.is_vowel(s)))
        .count();
    vowel_final as f64 / forms.len() as f64
}

fn romania(seed: i64) -> Result<Report, String> {
    let mut spec = crate::spec::WorldSpec::from_json(ROMANIA_JSON)?;
    spec.seed = seed;
    let (world, events) = crate::spec::build(&spec)?;
    let mut simulation = Simulation::new(world, SimulationConfig::default(), events)?;
    let mut report = Report::new();
    for year in ROMANIA_YEARS {
        simulation.run(year)?;
        for branch in ROMANIA_BRANCHES {
            record_branch(&simulation, branch, year, &mut report);
        }
    }
    // Souhrny přes větve (počty větví), na které míří cíle.
    let count = |report: &Report, year: f64, what: &str, test: &dyn Fn(f64) -> bool| {
        ROMANIA_BRANCHES
            .iter()
            .filter(|b| test(metric_value(report, &format!("{b} {year:.0} {what}"))))
            .count() as f64
    };
    let summary = [
        (
            "větve bez -m do roku 400",
            count(&report, 400.0, "tvary předmětu s -m", &|v| v < 0.5),
        ),
        (
            "větve bez pádu v roce 1200",
            count(&report, 1200.0, "pád", &|v| v < 0.5),
        ),
        (
            "větve se členem v roce 1200",
            count(&report, 1200.0, "člen", &|v| v > 0.5),
        ),
        (
            "větve bez původního futura v roce 600",
            count(&report, 600.0, "futurum", &|v| v != 0.0),
        ),
        (
            "větve s novým syntetickým futurem v roce 1300",
            count(&report, 1300.0, "futurum", &|v| v == 2.0),
        ),
        (
            "větve s pevným SVO v roce 1300",
            count(&report, 1300.0, "pevné SVO", &|v| v > 0.5),
        ),
        (
            "větve se záporem před slovesem v roce 1200",
            count(&report, 1200.0, "zápor před slovesem", &|v| v > 0.5),
        ),
        (
            "větve s dvojitým záporem v roce 1900",
            count(&report, 1900.0, "dvojitý zápor", &|v| v > 0.5),
        ),
    ];
    for (name, value) in summary {
        info(&mut report, name, value);
    }
    // Profil rodinné podobnosti (M7.3i): stav rodiny v roce 1900 a pořadí změn.
    let profile = [
        (
            "větve bez pádu v roce 1900",
            count(&report, 1900.0, "pád", &|v| v < 0.5),
        ),
        (
            "větve bez latinského futura v roce 1900",
            count(&report, 1900.0, "futurum", &|v| v != 0.0),
        ),
        (
            "větve s obnoveným futurem v roce 1900",
            count(&report, 1900.0, "futurum", &|v| v >= 1.0),
        ),
        (
            "větve se členem v roce 1900",
            count(&report, 1900.0, "člen", &|v| v > 0.5),
        ),
        (
            "větve s pevným slovosledem v roce 1900",
            count(&report, 1900.0, "pevný slovosled", &|v| v > 0.5),
        ),
        (
            "větve s pádem v roce 1200",
            count(&report, 1200.0, "pád", &|v| v > 0.5),
        ),
    ];
    for (name, value) in profile {
        info(&mut report, name, value);
    }
    // Pořadí: koncovka předmětu zeslábne (méně než polovina tvarů s -m) nejpozději v odečtu,
    // kdy zanikne pád; podíl takových větví mezi větvemi, které pád ztratily.
    let first = |branch: &str, what: &str, test: &dyn Fn(f64) -> bool| {
        ROMANIA_YEARS
            .iter()
            .position(|&y| test(metric_value(&report, &format!("{branch} {y:.0} {what}"))))
    };
    let (mut lost, mut ordered) = (0, 0);
    for branch in ROMANIA_BRANCHES {
        if let Some(case) = first(branch, "pád", &|v| v < 0.5) {
            lost += 1;
            if first(branch, "tvary předmětu s -m", &|v| v < 0.5).is_some_and(|m| m <= case) {
                ordered += 1;
            }
        }
    }
    info(
        &mut report,
        "podíl větví, kde koncovka zeslábla dřív, než zanikl pád",
        if lost == 0 {
            f64::NAN
        } else {
            f64::from(ordered) / f64::from(lost)
        },
    );
    let retention: Vec<f64> = ROMANIA_BRANCHES
        .iter()
        .map(|b| metric_value(&report, &format!("{b} 1900 retence")))
        .collect();
    info(
        &mut report,
        "retence vůči latině v roce 1900 (průměr větví)",
        mean(&retention),
    );
    let vowels: Vec<f64> = ROMANIA_BRANCHES
        .iter()
        .map(|b| metric_value(&report, &format!("{b} 1900 slova na samohlásku")))
        .collect();
    let spread = vowels.iter().cloned().fold(f64::NEG_INFINITY, f64::max)
        - vowels.iter().cloned().fold(f64::INFINITY, f64::min);
    info(
        &mut report,
        "rozdíl podílu slov na samohlásku mezi větvemi v roce 1900",
        spread,
    );
    Ok(report)
}

// --- Evropa (M8) ----------------------------------------------------------------------------

/// Popis světa Evropy (dok. 23, M8).
pub const EVROPA_JSON: &str = include_str!("../../../src/cee/data/scenarios/evropa.json");

/// Nejmenší podíl původního jazyka v regionu, který se počítá jako přežití (ostrůvek).
const ISLAND_MIN: f64 = 0.02;

/// Skupiny regionu, které mluví jazykem z linie `lineage`.
fn lineage_groups(
    world: &crate::world::World,
    region: &str,
    lineage: &str,
) -> Vec<crate::ids::GroupId> {
    region_groups(world, region)
        .into_iter()
        .filter(|&g| {
            world
                .registry
                .languages
                .name(world.groups.main_code(g).language.0)
                == lineage
        })
        .collect()
}

/// Podíl mluvčích linie v regionu: domácí jazyk mluvených skupin regionu. Veřejná
/// dvojjazyčnost (dospělí užívají úřední jazyk mimo domov) se nepočítá.
fn lineage_share(world: &crate::world::World, region: &str, lineage: &str) -> f64 {
    let pop = |list: &[crate::ids::GroupId]| -> f64 {
        list.iter()
            .filter(|&&g| {
                !world.groups.written[g.index()]
                    && world.groups.domain[g.index()] == crate::model::group::Domain::Home
            })
            .map(|&g| f64::from(world.groups.population[g.index()]))
            .sum()
    };
    let total = pop(&region_groups(world, region));
    if total > 0.0 {
        pop(&lineage_groups(world, region, lineage)) / total
    } else {
        f64::NAN
    }
}

/// Má linie v regionu syntetický předmět (pád) a člen? (`None`, když tam nikdo nemluví.)
fn lineage_grammar(
    world: &crate::world::World,
    region: &str,
    lineage: &str,
) -> Option<(bool, bool)> {
    let groups = lineage_groups(world, region, lineage);
    if groups.is_empty() {
        return None;
    }
    let case = branch_construction(world, &groups, "OBJ").is_some_and(|c| c.kind == "synthetic");
    let article = branch_construction(world, &groups, "DEFINITE").is_some_and(|c| c.kind != "zero");
    Some((case, article))
}

fn evropa(seed: i64) -> Result<Report, String> {
    let mut spec = crate::spec::WorldSpec::from_json(EVROPA_JSON)?;
    spec.seed = seed;
    let (world, events) = crate::spec::build(&spec)?;
    let config = SimulationConfig {
        keep_distances: true,
        ..SimulationConfig::default()
    };
    let mut simulation = Simulation::new(world, config, events)?;
    simulation.run(1900.0)?;
    let world = &simulation.world;
    let mut report = Report::new();
    let flag = |v: bool| f64::from(u8::from(v));
    // Podíly jazyků v regionech v roce 1900.
    for (region, lineage) in [
        ("gallia", "gaulish"),
        ("gallia", "germanic"),
        ("hispania", "iberian"),
        ("britannia", "gaulish"),
        ("britannia", "germanic"),
        ("armorica", "gaulish"),
        ("dacia", "latin"),
        ("balkan", "slavic"),
        ("vasconia", "basque"),
        ("cambria", "gaulish"),
        ("graecia", "greek"),
    ] {
        info(
            &mut report,
            &format!("{region} podíl {lineage}"),
            lineage_share(world, region, lineage),
        );
    }
    // Pád a člen po rodinách a regionech.
    let mut grammar = |region: &str, lineage: &str| {
        if let Some((case, article)) = lineage_grammar(world, region, lineage) {
            info(&mut report, &format!("{region} {lineage} pád"), flag(case));
            info(
                &mut report,
                &format!("{region} {lineage} člen"),
                flag(article),
            );
        }
    };
    for region in ["italia", "gallia", "hispania", "dacia"] {
        grammar(region, "latin");
    }
    grammar("britannia", "germanic");
    grammar("germania", "germanic");
    grammar("scandinavia", "germanic");
    grammar("slavia", "slavic");
    grammar("balkan", "slavic");
    grammar("dacia", "slavic");
    grammar("graecia", "greek");
    // Přežití původních jazyků regionů: ostrůvek = původní jazyk drží menšinu (2 až 50 %).
    let (mut islands, mut survivors) = (0.0, std::collections::BTreeSet::new());
    for region in &spec.regions {
        let Some(native) = region.language.as_deref() else {
            continue;
        };
        let share = lineage_share(world, &region.id, native);
        info(&mut report, &format!("{} původní jazyk", region.id), share);
        if share > ISLAND_MIN && share < 0.5 {
            islands += 1.0;
        }
        if share > ISLAND_MIN {
            survivors.insert(native.to_owned());
        }
    }
    info(&mut report, "ostrůvky původních jazyků", islands);
    info(
        &mut report,
        "přeživší původní jazyky",
        survivors.len() as f64,
    );
    let v = |name: &str| metric_value(&report, name);
    let latin_caseless = ["italia", "gallia", "hispania", "dacia"]
        .iter()
        .filter(|r| v(&format!("{r} latin pád")) == 0.0)
        .count() as f64;
    let summary = [
        ("románské větve bez pádu", latin_caseless),
        (
            "keltský a iberský ústup",
            flag(v("gallia podíl gaulish") < 0.1 && v("hispania podíl iberian") < 0.1),
        ),
        (
            "keltština přežije na okraji",
            flag(v("armorica podíl gaulish") > 0.5 || v("britannia podíl gaulish") > 0.3),
        ),
        (
            "germánština v Británii převládne",
            flag(v("britannia podíl germanic") > 0.5),
        ),
        (
            "angličtina ztratí pád a pevninská germánština ne",
            flag(v("britannia germanic pád") == 0.0 && v("germania germanic pád") == 1.0),
        ),
        (
            "franská elita přejde na latinu",
            flag(v("gallia podíl germanic") < 0.1),
        ),
        (
            "slovanská pravlast drží pád",
            flag(v("slavia slavic pád") == 1.0),
        ),
        (
            "baskičtina přežije v horách",
            flag(v("vasconia podíl basque") > 0.5),
        ),
        (
            "velština přežije i pod anglickým státem",
            flag(v("cambria podíl gaulish") > 0.5),
        ),
        (
            "řečtina přežije s vlastním státem",
            flag(v("graecia podíl greek") > 0.5),
        ),
        (
            "balkánská slovanština ztratí pád nebo získá člen",
            flag(v("balkan slavic pád") == 0.0 || v("balkan slavic člen") == 1.0),
        ),
    ];
    for (name, value) in summary {
        info(&mut report, name, value);
    }
    // Vzdálenost uvnitř rodin a mezi nimi (poslední snímek).
    if let Some(snapshot) = simulation.history.snapshots.last() {
        info(
            &mut report,
            "počet jazyků v roce 1900",
            snapshot.languages.len() as f64,
        );
        if let Some(flat) = snapshot.distances.as_deref() {
            let n = snapshot.group_ids.len();
            let lineage: Vec<String> = snapshot
                .group_ids
                .iter()
                .map(|name| {
                    group_named(world, name).map_or(String::new(), |g| {
                        world
                            .registry
                            .languages
                            .name(world.groups.main_code(g).language.0)
                            .to_owned()
                    })
                })
                .collect();
            let (mut within, mut between) = (Vec::new(), Vec::new());
            for i in 0..n {
                for j in i + 1..n {
                    if lineage[i].is_empty() || lineage[j].is_empty() {
                        continue;
                    }
                    if lineage[i] == lineage[j] {
                        within.push(flat[i * n + j]);
                    } else {
                        between.push(flat[i * n + j]);
                    }
                }
            }
            info(
                &mut report,
                "vzdálenost uvnitř rodin / mezi rodinami",
                mean(&within) / mean(&between),
            );
        }
    }
    Ok(report)
}

// --- Tempo hláskových změn (M9) ----------------------------------------------------------

/// Délka běhu tempa v letech.
pub const TEMPO_YEARS: f64 = 1000.0;

/// Levenshteinova vzdálenost po hláskách.
fn edit_distance(a: &[i32], b: &[i32]) -> usize {
    let mut row: Vec<usize> = (0..=b.len()).collect();
    for (i, x) in a.iter().enumerate() {
        let mut previous = row[0];
        row[0] = i + 1;
        for (j, y) in b.iter().enumerate() {
            let current = row[j + 1];
            row[j + 1] = (row[j + 1] + 1)
                .min(row[j] + 1)
                .min(previous + usize::from(x != y));
            previous = current;
        }
    }
    row[b.len()]
}

/// Průměrná normalizovaná vzdálenost zděděných slov domácích skupin regionu `region` od tvarů
/// prajazyka (`words`: pojem → IPA) a podíl slov beze změny.
fn form_drift(
    world: &crate::world::World,
    region: &str,
    words: &BTreeMap<String, String>,
) -> (f64, f64) {
    let Some(table) = world.table.as_ref() else {
        return (f64::NAN, f64::NAN);
    };
    let proto: BTreeMap<&str, Vec<i32>> = words
        .iter()
        .filter_map(|(c, w)| table.parse(w).ok().map(|f| (c.as_str(), f)))
        .collect();
    let (mut distances, mut same) = (Vec::new(), 0usize);
    for group in region_groups(world, region) {
        let g = group.index();
        if world.groups.written[g] || world.groups.domain[g] != crate::model::group::Domain::Home {
            continue;
        }
        for (variable, concept) in crate::gates::metrics::lexical_variables(world) {
            let name = world.registry.concepts.name(concept.0);
            let Some(start) = proto.get(name) else {
                continue;
            };
            let Some((variant, _)) = world.dominant(group, variable) else {
                continue;
            };
            if world.variants.origin[variant.index()].change.is_some() {
                continue;
            }
            let Some(root) = crate::gates::metrics::root_of(world, group, variable) else {
                continue;
            };
            let Ok(now) = crate::phonology::surface(world, group, root) else {
                continue;
            };
            let d = edit_distance(start, &now) as f64 / start.len().max(now.len()).max(1) as f64;
            same += usize::from(d == 0.0);
            distances.push(d);
        }
    }
    (
        mean(&distances),
        same as f64 / distances.len().max(1) as f64,
    )
}

/// Kontrolovaný svět tempa: region `r0` (12 vesnic jazyka `language`), volitelně sousední
/// region latiny a stát s úřední latinou (politika `policy`) nad oběma.
fn tempo_world(
    language: &Value,
    contact: Option<(&Value, &str)>,
    seed: i64,
) -> Result<Simulation, String> {
    let evropa: Value = serde_json::from_str(EVROPA_JSON).map_err(|e| e.to_string())?;
    let mut languages = vec![language.clone()];
    let mut regions = vec![
        json!({"id": "r0", "name": "r0", "position": [0, 0], "neighbours": [],
        "language": language["id"], "villages": 12}),
    ];
    let mut events = Vec::new();
    if let Some((other, policy)) = contact {
        languages.push(other.clone());
        regions[0]["neighbours"] = json!(["r1"]);
        regions.push(
            json!({"id": "r1", "name": "r1", "position": [60, 0], "neighbours": ["r0"],
            "language": other["id"], "villages": 12, "density": 2.0}),
        );
        events.push(
            json!({"kind": "state", "year": 100, "id": "st", "regions": ["r0", "r1"],
            "capital": "r1", "language": other["id"], "policy": policy}),
        );
    }
    let text = json!({"format": evropa["format"], "name": "tempo", "seed": seed, "start_year": 0,
        "end_year": TEMPO_YEARS, "languages": languages, "regions": regions, "events": events,
        "parameters": evropa["parameters"]})
    .to_string();
    let spec = crate::spec::WorldSpec::from_json(&text)?;
    let (world, events) = crate::spec::build(&spec)?;
    let mut simulation = Simulation::new(world, SimulationConfig::default(), events)?;
    simulation.run(TEMPO_YEARS)?;
    Ok(simulation)
}

/// Tempo hláskových změn: rychlost r = −ln(1 − d) za tisíciletí (d = vzdálenost tvarů
/// zděděných slov od prajazyka), jako u skutečných dvojic IE-CoR (dok. 24).
fn tempo(seed: i64) -> Result<Report, String> {
    let evropa: Value = serde_json::from_str(EVROPA_JSON).map_err(|e| e.to_string())?;
    let language = |id: &str| -> Result<Value, String> {
        evropa["languages"]
            .as_array()
            .and_then(|l| l.iter().find(|x| x["id"] == id))
            .cloned()
            .ok_or_else(|| format!("jazyk {id} ve scénáři Evropy chybí"))
    };
    let (slavic, latin) = (language("slavic")?, language("latin")?);
    let words = |l: &Value| -> BTreeMap<String, String> {
        serde_json::from_value(l["words"].clone()).unwrap_or_default()
    };
    let rate = |d: f64| -(1.0 - d).ln() / (TEMPO_YEARS / 1000.0);
    let mut report = Report::new();
    let mut quiet = Vec::new();
    for (name, l, contact) in [
        ("slovanština bez kontaktu", &slavic, None),
        ("latina bez kontaktu", &latin, None),
        (
            "slovanština s latinským státem",
            &slavic,
            Some((&latin, "tolerant")),
        ),
    ] {
        let simulation = tempo_world(l, contact, seed)?;
        let (d, same) = form_drift(&simulation.world, "r0", &words(l));
        info(&mut report, &format!("{name} tempo"), rate(d));
        info(&mut report, &format!("{name} beze změny"), same);
        if contact.is_none() {
            quiet.push(rate(d));
        }
    }
    let quiet_mean = mean(&quiet);
    info(&mut report, "tempo bez kontaktu", quiet_mean);
    let speedup = metric_value(&report, "slovanština s latinským státem tempo")
        / metric_value(&report, "slovanština bez kontaktu tempo");
    info(&mut report, "zrychlení kontaktem", speedup);
    Ok(report)
}

/// Všechny kalibrační běhy.
pub fn runs() -> Vec<Run> {
    vec![
        Run {
            id: "tempo",
            description: "tempo hláskových změn: 12 vesnic staroslověnštiny / latiny 1 000 let, bez kontaktu a pod latinským státem",
            measure: tempo,
        },
        Run {
            id: "evropa",
            description: "Evropa: latina, keltština, iberština, dáčtina, germánština, slovanština, řečtina; 10 regionů, −500 až 1900",
            measure: evropa,
        },
        Run {
            id: "romania",
            description: "latina ve čtyřech větvích (Itálie, Galie, Hispánie, Dácie), −100 až 1900",
            measure: romania,
        },
        Run {
            id: "typologie",
            description: "village_grid 6 vesnic, start gramatiky a přízvuku z WALS, 5 000 let",
            measure: typology,
        },
        Run {
            id: "lexikon",
            description: "8 vesnic se sémantikou (běh m3b), 3 000 let",
            measure: lexicon,
        },
        Run {
            id: "region",
            description: "čtyři regiony po pěti vesnicích (region-square), 3 000 let",
            measure: region,
        },
        Run {
            id: "slozitost",
            description:
                "20 míst: populace 100 až 10 000 × podíl L2 0 až 45 % (běh metriky 11), 1 500 let",
            measure: complexity,
        },
    ]
}

// --- varianty a vyhodnocení -----------------------------------------------------------------

/// Varianta metaparametrů: jméno a přepisy (`None` = výchozí soubor).
#[derive(Clone, Debug)]
pub struct Variant {
    pub name: String,
    pub overrides: Map<String, Value>,
    pub params: Option<Parameters>,
}

impl Variant {
    pub fn base() -> Variant {
        Variant {
            name: "výchozí".into(),
            overrides: Map::new(),
            params: None,
        }
    }

    pub fn new(name: &str, overrides: Map<String, Value>) -> Result<Variant, String> {
        let params = Parameters::from_overrides(&overrides).map_err(|e| format!("{name}: {e}"))?;
        Ok(Variant {
            name: name.to_owned(),
            overrides,
            params: Some(params),
        })
    }
}

/// Jeden řádek výpisu.
#[derive(Clone, Debug)]
pub struct Row {
    pub variant: String,
    pub target: String,
    pub kind: Kind,
    pub label: String,
    pub n: usize,
    pub estimate: f64,
    pub low: f64,
    pub high: f64,
    pub goal: String,
    /// `None` = informace bez cíle.
    pub met: Option<bool>,
}

pub struct Options {
    pub start: i64,
    pub only: Vec<String>,
    pub variants: Vec<Variant>,
    pub jsonl: Option<String>,
}

fn wanted(only: &[String], target: &Target) -> bool {
    only.is_empty() || only.iter().any(|o| *o == target.id || *o == target.run)
}

fn evaluate(target: &Target, variant: &str, reports: &[&Report]) -> Vec<Row> {
    let base = |label: &str| Row {
        variant: variant.to_owned(),
        target: target.id.clone(),
        kind: target.kind,
        label: label.to_owned(),
        n: reports.len(),
        estimate: f64::NAN,
        low: f64::NAN,
        high: f64::NAN,
        goal: String::new(),
        met: None,
    };
    match target.kind {
        Kind::Possibility => {
            let event = target.event.as_ref().expect("zkontrolováno");
            let n = reports.len();
            let occurred = reports.iter().filter(|r| event.holds(r)).count() as u32;
            let k = crate::gates::statistical::required_successes(n, target.p_min);
            let mut row = base(&event.label);
            row.n = n;
            row.estimate = if n == 0 {
                f64::NAN
            } else {
                f64::from(occurred) / n as f64
            };
            if let Ok((low, high)) = crate::gates::stats::wilson_interval(occurred, n as u32) {
                row.low = low;
                row.high = high;
            }
            row.goal = format!(
                "{} {} {} v ≥ {k} z {n} běhů (p_min {})",
                event.metric,
                event.op,
                fmt(event.value),
                fmt(target.p_min)
            );
            row.met = Some(occurred >= k);
            vec![row]
        }
        Kind::Band | Kind::Info => target
            .measures
            .iter()
            .map(|measure| {
                let values: Vec<f64> = reports
                    .iter()
                    .map(|r| metric_value(r, &measure.metric))
                    .filter(|v| !v.is_nan())
                    .collect();
                let mut row = base(&measure.label);
                row.n = values.len();
                if !values.is_empty() {
                    row.estimate = median_of(&values);
                    (row.low, row.high) = bootstrap_median_interval(
                        &values,
                        &format!("{}|{}", target.id, measure.label),
                    );
                }
                match (target.kind, measure.band) {
                    (Kind::Band, Some([low, high])) => {
                        row.goal = format!("medián v [{}, {}]", fmt(low), fmt(high));
                        row.met = Some(row.estimate >= low && row.estimate <= high);
                    }
                    _ => {
                        row.goal = measure
                            .reference
                            .map_or("informace".to_owned(), |r| format!("reference {}", fmt(r)));
                    }
                }
                row
            })
            .collect(),
        Kind::Typology => {
            let feature = target.feature.as_deref().unwrap_or("");
            let Some(reference) = reference(feature) else {
                return vec![base("neznámý rys")];
            };
            let mut rows = Vec::new();
            for (prefix, judged) in [("start", false), ("konec", true)] {
                let counts = pooled(reports, prefix, feature);
                let n = counts.values().sum::<f64>().round() as usize;
                let distance = hellinger(&counts, reference);
                let quantile = null_quantile(reference, n, &format!("{feature}|{n}"));
                let mut row = base(&format!(
                    "{feature} Hellinger od WALS ({prefix}; entropie {}, WALS {})",
                    fmt(entropy(&counts, reference.len())),
                    fmt(entropy(reference, reference.len()))
                ));
                row.n = n;
                row.estimate = distance;
                row.goal = format!("<= {} (95 % šumu vzorku {n} jazyků)", fmt(quantile));
                if judged {
                    row.met = Some(distance <= quantile);
                }
                rows.push(row);
            }
            let (gained, lost, changed) = transitions(reports, feature);
            let mut row = base(&format!(
                "{feature} přechody jazyků za {} let (vznik / zánik / jiná změna stavu)",
                TYPOLOGY_YEARS
            ));
            row.estimate = (gained + lost + changed) as f64;
            row.goal = format!("+{gained} / −{lost} / ~{changed} (informace)");
            rows.push(row);
            rows
        }
    }
}

/// Je stav rysu „kategorie vyjádřená“ (33A, 37A, 66A přítomné, 67A inflexní)? `None` u rysů,
/// které nejsou přítomnost/nepřítomnost (81A, 143A, 14A).
fn expressed(feature: &str, state: &str) -> Option<bool> {
    match feature {
        "33A" | "37A" | "66A" => Some(state.ends_with("_present")),
        "67A" => Some(state == "67A-1"),
        _ => None,
    }
}

/// Přechody jazyků od startu semínka (jeden protojazyk) ke konci: kolik jazyků kategorii
/// získalo, ztratilo a (u vícestavových rysů) změnilo stav. Stacionární rozložení může vzniknout
/// rovnováhou vzniku a zániku, nebo tím, že se nic neděje; počty přechodů je rozliší.
fn transitions(reports: &[&Report], feature: &str) -> (usize, usize, usize) {
    let (mut gained, mut lost, mut changed) = (0, 0, 0);
    for report in reports {
        let start = pooled(&[report], "start", feature);
        let Some(origin) = start.iter().find(|(_, &n)| n > 0.0).map(|(s, _)| s.clone()) else {
            continue;
        };
        for (state, count) in pooled(&[report], "konec", feature) {
            let count = count.round() as usize;
            if state == origin {
                continue;
            }
            match (expressed(feature, &origin), expressed(feature, &state)) {
                (Some(false), Some(true)) => gained += count,
                (Some(true), Some(false)) => lost += count,
                _ => changed += count,
            }
        }
    }
    (gained, lost, changed)
}

fn fmt(value: f64) -> String {
    if value.is_nan() {
        "nic".to_owned()
    } else if value.abs() >= 100.0 {
        format!("{value:.0}")
    } else {
        format!("{value:.3}")
    }
}

fn execute(run: &Run, seed: i64, params: Option<&Parameters>) -> Result<Report, String> {
    let outcome = catch_unwind(AssertUnwindSafe(|| {
        with_defaults(params, || (run.measure)(seed))
    }));
    outcome.unwrap_or_else(|_| Err("pád enginu".to_owned()))
}

/// Spustí kalibrační běhy pro všechny varianty a vyhodnotí cíle.
pub fn run_rows(options: &Options) -> Result<Vec<Row>, String> {
    let targets = Targets::shared()?;
    let chosen: Vec<&Target> = targets
        .targets
        .iter()
        .filter(|t| wanted(&options.only, t))
        .collect();
    if chosen.is_empty() {
        return Err("žádný cíl neodpovídá výběru".into());
    }
    let mut sink = match &options.jsonl {
        Some(path) => Some(std::fs::File::create(path).map_err(|e| format!("{path}: {e}"))?),
        None => None,
    };
    let mut rows = Vec::new();
    let all = runs();
    for variant in &options.variants {
        let mut reports: BTreeMap<&str, Vec<Report>> = BTreeMap::new();
        for run in &all {
            let Some(count) = chosen.iter().filter(|t| t.run == run.id).map(|t| t.n).max() else {
                continue;
            };
            eprintln!(
                "varianta {} běh {} ({} semínek)",
                variant.name, run.id, count
            );
            let seeds: Vec<i64> = (0..count as i64).map(|i| options.start + i).collect();
            let results: Vec<(i64, Result<Report, String>)> = seeds
                .par_iter()
                .map(|&seed| (seed, execute(run, seed, variant.params.as_ref())))
                .collect();
            let mut kept = Vec::new();
            for (seed, result) in results {
                match result {
                    Ok(report) => {
                        if let Some(file) = sink.as_mut() {
                            let metrics: Vec<_> = report
                                .metrics
                                .iter()
                                .map(|m| json!({"metric": m.name, "value": m.value}))
                                .collect();
                            let line = json!({"variant": variant.name, "overrides": variant.overrides,
                                "run": run.id, "seed": seed, "metrics": metrics});
                            writeln!(file, "{line}").map_err(|e| e.to_string())?;
                        }
                        kept.push(report);
                    }
                    Err(message) => eprintln!(
                        "varianta {} běh {} semínko {seed}: {message}",
                        variant.name, run.id
                    ),
                }
            }
            reports.insert(run.id, kept);
        }
        for target in &chosen {
            let Some(all_reports) = reports.get(target.run.as_str()) else {
                continue;
            };
            let used: Vec<&Report> = all_reports.iter().take(target.n).collect();
            rows.extend(evaluate(target, &variant.name, &used));
        }
    }
    Ok(rows)
}

/// Markdown tabulka výsledků.
pub fn render(rows: &[Row]) -> String {
    let mut text = String::from(
        "| varianta | cíl | druh | veličina | N | medián / hodnota | interval 95 % | cíl | splněno |\n|---|---|---|---|---:|---:|---|---|---|\n",
    );
    for row in rows {
        let interval = if row.low.is_nan() {
            "–".to_owned()
        } else {
            format!("[{}, {}]", fmt(row.low), fmt(row.high))
        };
        let _ = writeln!(
            text,
            "| {} | {} | {} | {} | {} | {} | {interval} | {} | {} |",
            row.variant,
            row.target,
            row.kind.label(),
            row.label,
            row.n,
            fmt(row.estimate),
            row.goal,
            match row.met {
                Some(true) => "ano",
                Some(false) => "ne",
                None => "–",
            }
        );
    }
    let judged: Vec<&Row> = rows.iter().filter(|r| r.met.is_some()).collect();
    let met = judged.iter().filter(|r| r.met == Some(true)).count();
    let _ = writeln!(
        text,
        "\nSplněno {met} z {} posuzovaných veličin.",
        judged.len()
    );
    text
}

/// Seznam cílů a běhů (`cee calibrate --list`).
pub fn list() -> Result<String, String> {
    let targets = Targets::shared()?;
    let mut text = format!(
        "Stav cílů: {}\n\n| cíl | druh | běh | N | veličiny |\n|---|---|---|---:|---|\n",
        targets.status
    );
    for target in &targets.targets {
        let measures: Vec<String> = match target.kind {
            Kind::Possibility => target
                .event
                .iter()
                .map(|e| format!("{} (p_min {})", e.label, fmt(target.p_min)))
                .collect(),
            Kind::Typology => vec![format!(
                "rys WALS {}",
                target.feature.as_deref().unwrap_or("")
            )],
            _ => target
                .measures
                .iter()
                .map(|m| match m.band {
                    Some([low, high]) => format!("{} [{}, {}]", m.label, fmt(low), fmt(high)),
                    None => m.label.clone(),
                })
                .collect(),
        };
        let _ = writeln!(
            text,
            "| {} | {} | {} | {} | {} |",
            target.id,
            target.kind.label(),
            target.run,
            target.n,
            measures.join("; ")
        );
    }
    text.push_str("\n| běh | popis |\n|---|---|\n");
    for run in runs() {
        let _ = writeln!(text, "| {} | {} |", run.id, run.description);
    }
    Ok(text)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cile_jsou_platne() {
        Targets::shared().unwrap();
    }

    #[test]
    fn nulovy_kvantil_klesa_s_velikosti_vzorku() {
        let reference = reference("37A").unwrap();
        let small = null_quantile(reference, 10, "t");
        let large = null_quantile(reference, 200, "t");
        assert!(small > large && large > 0.0, "{small} {large}");
    }

    #[test]
    fn start_z_wals_sleduje_rozlozeni() {
        // Podíl jazyků s členem ve 400 losech blízko WALS (0,61).
        let present = (0..400)
            .filter(|&seed| {
                wals_start(seed)
                    .0
                    .iter()
                    .any(|(f, c)| *f == "DEFINITE" && c.kind != "zero")
            })
            .count() as f64
            / 400.0;
        assert!((present - 0.61).abs() < 0.07, "{present}");
    }

    #[test]
    fn entropie_rovnomerneho_je_jedna() {
        let counts: BTreeMap<String, f64> = [("a".to_owned(), 5.0), ("b".to_owned(), 5.0)].into();
        assert!((entropy(&counts, 2) - 1.0).abs() < 1e-12);
    }
}
