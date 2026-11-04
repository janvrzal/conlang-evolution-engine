//! Souhrn chování běhu pro kalibraci proti Pythonu (`cee behavior`).
//!
//! Zrcadlo `scripts/v2_reference_behavior.py`: stejné scénáře, semínka a tvar výstupu, takže
//! `scripts/v2_compare_behavior.py` porovná Rust s `tests/v2/data/reference_behavior.json`.

use std::collections::BTreeMap;

use serde_json::{json, Map, Value};

use crate::gates::metrics::{group_named, retention};
use crate::scenarios;
use crate::{Simulation, SimulationConfig};

/// Scénáře a délky v letech, pořadí jako v Pythonu.
pub const SCENARIOS: [(&str, f64); 7] = [
    ("phonology", 1000.0),
    ("morphology", 1000.0),
    ("syntax", 1000.0),
    ("grid-5x5", 1000.0),
    ("shift", 900.0),
    ("island-city", 800.0),
    ("valley-50", 2000.0),
];
pub const SEEDS: [i64; 3] = [1, 2, 3];
const SNAPSHOT_YEARS: [i64; 5] = [200, 500, 1000, 1500, 2000];

fn counts(map: BTreeMap<String, u64>) -> Value {
    Value::Object(
        map.into_iter()
            .map(|(k, v)| (k, json!(v)))
            .collect::<Map<_, _>>(),
    )
}

/// Průměr vzdáleností mezi nejbližšími sousedy mřížky.
fn neighbour_distance(simulation: &Simulation, index: usize) -> Option<f64> {
    let snapshot = &simulation.history.snapshots[index];
    let flat = snapshot.distances.as_deref()?;
    let n = snapshot.group_ids.len();
    if n < 2 || flat.len() != n * n {
        return None;
    }
    let world = &simulation.world;
    let mut positions = Vec::with_capacity(n);
    for name in &snapshot.group_ids {
        positions.push(world.position_of(group_named(world, name)?)?);
    }
    let dist = |i: usize, j: usize| {
        (positions[i].0 - positions[j].0).hypot(positions[i].1 - positions[j].1)
    };
    let step = (0..n)
        .flat_map(|i| (i + 1..n).map(move |j| (i, j)))
        .map(|(i, j)| dist(i, j))
        .filter(|&d| d > 1e-9)
        .fold(f64::INFINITY, f64::min);
    if !step.is_finite() {
        return None;
    }
    let values: Vec<f64> = (0..n)
        .flat_map(|i| (i + 1..n).map(move |j| (i, j)))
        .filter(|&(i, j)| dist(i, j) <= step * 1.001)
        .map(|(i, j)| flat[i * n + j])
        .collect();
    if values.is_empty() {
        None
    } else {
        Some(values.iter().sum::<f64>() / values.len() as f64)
    }
}

/// Souhrn jednoho doběhnutého běhu.
pub fn summarize(simulation: &Simulation) -> Value {
    let history = &simulation.history;
    let text = |e: &Map<String, Value>, key: &str| {
        e.get(key).and_then(Value::as_str).unwrap_or("").to_owned()
    };
    let mut change_of: BTreeMap<String, String> = BTreeMap::new();
    // Počet inovací = počet různých variant podle druhu změny (jako v Pythonu: stejná varianta
    // ve víc skupinách nebo po zániku znovu se počítá jednou).
    for e in history.of_kind("innovation") {
        change_of.insert(text(&e, "variant"), text(&e, "change"));
    }
    let mut innovations: BTreeMap<String, u64> = BTreeMap::new();
    for change in change_of.values() {
        *innovations.entry(change.clone()).or_default() += 1;
    }
    let by_change = |kind: &str| {
        let mut found: BTreeMap<String, u64> = BTreeMap::new();
        for e in history.of_kind(kind) {
            if let Some(change) = change_of.get(&text(&e, "variant")) {
                *found.entry(change.clone()).or_default() += 1;
            }
        }
        found
    };
    let mut kinds: BTreeMap<String, u64> = BTreeMap::new();
    for e in history.events.iter() {
        let kind = text(&e, "kind");
        if kind != "milestone" {
            *kinds.entry(kind).or_default() += 1;
        }
    }
    let words: u64 = history
        .of_kind("phonologized")
        .map(|e| e.get("words").and_then(Value::as_u64).unwrap_or(0))
        .sum();
    let kept: Vec<f64> = history
        .snapshots
        .last()
        .map(|last| {
            last.group_ids
                .iter()
                .filter_map(|name| group_named(&simulation.world, name))
                .map(|g| retention(&simulation.world, g))
                .collect()
        })
        .unwrap_or_default();
    let snapshots: Vec<Value> = history
        .snapshots
        .iter()
        .enumerate()
        .filter(|(_, s)| SNAPSHOT_YEARS.contains(&(s.year.round() as i64)))
        .map(|(i, s)| {
            json!({
                "year": s.year.round() as i64,
                "dialects": s.dialects.len(),
                "languages": s.languages.len(),
                "neighbour_distance": neighbour_distance(simulation, i),
            })
        })
        .collect();
    json!({
        "events": counts(kinds),
        "innovations": counts(innovations),
        "established": counts(by_change("established")),
        "extinct": counts(by_change("extinct")),
        "phonologized_words": words,
        "retention": if kept.is_empty() { Value::Null } else { json!(kept.iter().sum::<f64>() / kept.len() as f64) },
        "snapshots": snapshots,
    })
}

/// Spustí vybrané scénáře a semínka; výstup má tvar referenčního souboru z Pythonu.
pub fn run(only: &[String], seeds: &[i64]) -> Result<Value, String> {
    let mut result = Map::new();
    // `valley-50-open` není v základní sadě (Python ho nemá), jen na vyžádání.
    for (name, years) in SCENARIOS.into_iter().chain([("valley-50-open", 2000.0)]) {
        let wanted = only.iter().any(|o| o == name);
        if (only.is_empty() && name == "valley-50-open") || (!only.is_empty() && !wanted) {
            continue;
        }
        let mut runs = Map::new();
        for &seed in seeds {
            let (world, events) = scenarios::by_name_seeded(name, seed)?;
            let config = SimulationConfig {
                keep_distances: true,
                ..SimulationConfig::default()
            };
            let mut simulation = Simulation::new(world, config, events)?;
            simulation.run(years)?;
            runs.insert(seed.to_string(), summarize(&simulation));
        }
        result.insert(
            name.to_owned(),
            json!({"years": years as i64, "runs": runs}),
        );
    }
    Ok(json!({"seeds": seeds, "scenarios": result}))
}

/// Čtyři regiony ve čtverci po pěti vesnicích (`SQUARE` ve `scripts/v2_region_continuum.py`).
pub fn square_world(seed: i64) -> Result<crate::world::World, String> {
    use crate::scenarios::{region_world, Region, SeedOptions};
    let region = |id: &str, position: (f64, f64), neighbours: [&str; 2]| {
        let mut r = Region::new(id, position);
        r.neighbours = neighbours.iter().map(|s| (*s).to_owned()).collect();
        r.villages = 5;
        r
    };
    let regions = [
        region("nw", (0.0, 40.0), ["ne", "sw"]),
        region("ne", (40.0, 40.0), ["nw", "se"]),
        region("sw", (0.0, 0.0), ["nw", "se"]),
        region("se", (40.0, 0.0), ["ne", "sw"]),
    ];
    let options = SeedOptions {
        syntax: true,
        semantics: true,
        ..SeedOptions::default()
    };
    region_world(
        &regions,
        seed,
        &options,
        10.0,
        25.0,
        2.0,
        crate::parameters::Parameters::default(),
        &[],
    )
}

/// Průměrné vzdálenosti kódů: sousedé v regionu, přes hranici, vzdálené regiony
/// (`_measure` ve `scripts/v2_region_continuum.py`).
fn region_measure(simulation: &Simulation) -> Value {
    use std::collections::BTreeSet;
    let world = &simulation.world;
    let ids = world.live.group_ids.clone();
    let n = ids.len();
    let distances = crate::observe::code_distances(world);
    let region: Vec<u32> = ids
        .iter()
        .map(|&g| {
            world.territories[world.groups.territory[g.index()].index()]
                .parent
                .0
        })
        .collect();
    let linked: BTreeSet<(u32, u32)> = world
        .links
        .iter()
        .map(|(&(a, b), _)| (a.0.min(b.0), a.0.max(b.0)))
        .collect();
    let adjacent: BTreeSet<(u32, u32)> = (0..n)
        .flat_map(|i| (i + 1..n).map(move |j| (i, j)))
        .filter(|&(i, j)| {
            region[i] != region[j]
                && linked.contains(&(ids[i].0.min(ids[j].0), ids[i].0.max(ids[j].0)))
        })
        .map(|(i, j)| (region[i].min(region[j]), region[i].max(region[j])))
        .collect();
    let (mut near, mut across, mut far) = (Vec::new(), Vec::new(), Vec::new());
    for i in 0..n {
        for j in i + 1..n {
            let value = distances[i * n + j];
            let is_linked = linked.contains(&(ids[i].0.min(ids[j].0), ids[i].0.max(ids[j].0)));
            if region[i] == region[j] {
                if is_linked {
                    near.push(value);
                }
            } else if is_linked {
                across.push(value);
            } else if !adjacent.contains(&(region[i].min(region[j]), region[i].max(region[j]))) {
                far.push(value);
            }
        }
    }
    let mean = |v: &[f64]| {
        if v.is_empty() {
            Value::Null
        } else {
            json!(v.iter().sum::<f64>() / v.len() as f64)
        }
    };
    json!({"near": mean(&near), "across": mean(&across), "far": mean(&far)})
}

/// Kontinuum `region_world` ve čtverci: odečty v letech 1000, 2000 a 3000 (cíl doc. 14).
pub fn run_square(seeds: &[i64]) -> Result<Value, String> {
    let mut runs = Map::new();
    for &seed in seeds {
        let mut simulation =
            Simulation::new(square_world(seed)?, SimulationConfig::default(), Vec::new())?;
        let mut frames = Vec::new();
        for year in [1000.0, 2000.0, 3000.0] {
            simulation.run(year)?;
            let languages = simulation
                .history
                .snapshots
                .last()
                .map_or(0, |s| s.languages.len());
            let mut frame = region_measure(&simulation);
            frame["year"] = json!(year as i64);
            frame["languages"] = json!(languages);
            frames.push(frame);
        }
        runs.insert(seed.to_string(), json!(frames));
    }
    Ok(json!({"region_square": runs}))
}
