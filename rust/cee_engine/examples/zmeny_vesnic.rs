//! Kolik hláskových změn právě probíhá ve skupinách uvnitř nářečí a na hranicích.
//!
//! Ve zvolených letech rozdělí skupiny podle sousedství (vazby míšení `transfer::network::mixing`):
//! osamocené, s vazbou na jiný jazyk a jen s vlastním jazykem podle počtu izoglos se sousedy
//! (změna v jedné skupině dokončená, ve druhé nezačatá). Pro každou třídu vypíše průměr živých
//! procesů na skupinu podle podílu změny: čekající na uzavření jako odumřelé (pod 5 %),
//! probíhající (5–95 %) a dokončené čekající na uzavření (aspoň 95 %).
//!
//! `cargo run --release --example zmeny_vesnic -- <spec.json> [roky oddělené čárkou]`

use std::collections::{BTreeMap, BTreeSet};

use cee_engine::ids::{GroupId, ProcessId};
use cee_engine::spec::{self, WorldSpec};
use cee_engine::{Simulation, SimulationConfig, World};

const LOW: f64 = 0.05;
const HIGH: f64 = 0.95;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let text = std::fs::read_to_string(&args[0]).unwrap();
    let ws = WorldSpec::from_json(&text).unwrap();
    let years: Vec<f64> = args
        .get(1)
        .map_or("500,1000,1500,1800", String::as_str)
        .split(',')
        .map(|y| y.trim().parse().unwrap())
        .collect();
    cee_engine::parallel::init_default(0);
    let (w, events) = spec::build(&ws).unwrap();
    let mut sim = Simulation::new(w, SimulationConfig::default(), events).unwrap();
    for &year in &years {
        while sim.year() + sim.config.dt <= year + 1e-9 {
            sim.step().unwrap();
        }
        let (alpha, now) = (sim.config.alpha, sim.year());
        report(&mut sim.world, alpha, now);
    }
}

/// Podíl změny každého procesu, který kterákoli skupina zná, v každé skupině.
fn shares(world: &mut World, groups: &[GroupId]) -> BTreeMap<(GroupId, usize), f64> {
    let mut numbers: BTreeSet<usize> = BTreeSet::new();
    for &g in groups {
        for p in &world.groups.main_code(g).phonology.sound.queues.state.procs {
            numbers.insert(p.number);
        }
    }
    let mut info = BTreeMap::new();
    for &number in &numbers {
        info.insert(
            number,
            cee_engine::phonology::rows::info_of(world, ProcessId::new(number)).unwrap(),
        );
    }
    let mut out = BTreeMap::new();
    for &g in groups {
        for (&number, &(variable, changed)) in &info {
            let share = cee_engine::phonology::rows::changed_share(world, g, variable, changed);
            out.insert((g, number), share);
        }
    }
    out
}

fn report(world: &mut World, alpha: f64, year: f64) {
    let axis: Vec<GroupId> = world.live.group_ids.clone();
    let matrix = cee_engine::transfer::network::mixing(world, &axis, alpha);
    let shares = shares(world, &axis);
    let numbers: BTreeSet<usize> = shares.keys().map(|&(_, n)| n).collect();
    let status = |g: GroupId, n: usize| -> i8 {
        let s = shares.get(&(g, n)).copied().unwrap_or(0.0);
        if s >= HIGH {
            1
        } else if s < LOW {
            0
        } else {
            -1
        }
    };
    // Třída skupiny a počty živých procesů podle podílu.
    struct Row {
        class: &'static str,
        isoglosses: f64,
        fading: usize,
        running: usize,
        done: usize,
        population: f64,
    }
    let mut rows: Vec<Row> = Vec::new();
    for (column, &g) in axis.iter().enumerate() {
        let language = world.groups.main_code(g).language;
        let partners: Vec<(usize, f64)> = matrix[column]
            .iter()
            .copied()
            .filter(|&(other, w)| other != column && w > 0.0)
            .collect();
        let foreign: f64 = partners
            .iter()
            .filter(|&&(other, _)| world.groups.main_code(axis[other]).language != language)
            .map(|&(_, w)| w)
            .sum();
        let total: f64 = partners.iter().map(|&(_, w)| w).sum();
        // Izoglosy: průměr přes sousedy vlastního jazyka (vážený vazbou), kolik změn je v jedné
        // skupině dokončených a ve druhé nezačatých.
        let (mut iso, mut weight) = (0.0, 0.0);
        for &(other, w) in &partners {
            let h = axis[other];
            if world.groups.main_code(h).language != language {
                continue;
            }
            let count = numbers
                .iter()
                .filter(|&&n| {
                    let (a, b) = (status(g, n), status(h, n));
                    (a == 1 && b == 0) || (a == 0 && b == 1)
                })
                .count();
            iso += w * count as f64;
            weight += w;
        }
        let isoglosses = if weight > 0.0 { iso / weight } else { 0.0 };
        let class = if partners.is_empty() {
            // V Talveře jen psané normy (`written:…`): jazyk se nemění, procesy zdědí při vzniku.
            "osamocená"
        } else if foreign > 0.0 && foreign >= 0.1 * total {
            "hranice jazyka (≥ 10 % vazeb)"
        } else if foreign > 0.0 {
            "hranice jazyka (< 10 % vazeb)"
        } else {
            "jen vlastní jazyk"
        };
        let state = &world.groups.main_code(g).phonology.sound.queues.state;
        let (mut fading, mut running, mut done) = (0, 0, 0);
        for p in state.procs.iter().filter(|p| p.live) {
            let s = shares.get(&(g, p.number)).copied().unwrap_or(0.0);
            if s < LOW {
                fading += 1;
            } else if s >= HIGH {
                done += 1;
            } else {
                running += 1;
            }
        }
        rows.push(Row {
            class,
            isoglosses,
            fading,
            running,
            done,
            population: f64::from(world.groups.population[g.index()]),
        });
    }
    // Skupiny jen s vlastním jazykem se dělí na třetiny podle izoglos se sousedy.
    let mut own: Vec<f64> = rows
        .iter()
        .filter(|r| r.class == "jen vlastní jazyk")
        .map(|r| r.isoglosses)
        .collect();
    own.sort_by(f64::total_cmp);
    let cut = |q: f64| {
        own.get(((own.len() as f64 - 1.0) * q) as usize)
            .copied()
            .unwrap_or(0.0)
    };
    let (t1, t2) = (cut(1.0 / 3.0), cut(2.0 / 3.0));
    for r in &mut rows {
        if r.class == "jen vlastní jazyk" {
            r.class = if r.isoglosses <= t1 {
                "vlastní jazyk, málo izoglos"
            } else if r.isoglosses <= t2 {
                "vlastní jazyk, středně izoglos"
            } else {
                "vlastní jazyk, hodně izoglos"
            };
        }
    }
    println!(
        "== rok {year:.0}: {} skupin (třetiny izoglos ≤ {t1:.1}, ≤ {t2:.1})",
        rows.len()
    );
    println!(
        "{:<32} {:>6} {:>10} {:>9} {:>11} {:>10} {:>10}",
        "třída", "skupin", "izoglos", "probíhá", "medián prob.", "odumírá", "dokončeno"
    );
    let classes = [
        "vlastní jazyk, málo izoglos",
        "vlastní jazyk, středně izoglos",
        "vlastní jazyk, hodně izoglos",
        "hranice jazyka (< 10 % vazeb)",
        "hranice jazyka (≥ 10 % vazeb)",
        "osamocená",
    ];
    for class in classes {
        let members: Vec<&Row> = rows.iter().filter(|r| r.class == class).collect();
        if members.is_empty() {
            continue;
        }
        let n = members.len() as f64;
        let mean = |f: &dyn Fn(&Row) -> f64| members.iter().map(|r| f(r)).sum::<f64>() / n;
        let mut running: Vec<usize> = members.iter().map(|r| r.running).collect();
        running.sort_unstable();
        println!(
            "{:<32} {:>6} {:>10.1} {:>9.1} {:>11} {:>10.1} {:>10.1}",
            class,
            members.len(),
            mean(&|r| r.isoglosses),
            mean(&|r| r.running as f64),
            running[running.len() / 2],
            mean(&|r| r.fading as f64),
            mean(&|r| r.done as f64),
        );
    }
    // Souvislost s velikostí: probíhající změny podle populace (třetiny).
    let mut by_size: Vec<(f64, usize)> = rows.iter().map(|r| (r.population, r.running)).collect();
    by_size.sort_by(|a, b| a.0.total_cmp(&b.0));
    let third = by_size.len() / 3;
    for (label, part) in [
        ("nejmenší třetina", &by_size[..third]),
        ("prostřední třetina", &by_size[third..2 * third]),
        ("největší třetina", &by_size[2 * third..]),
    ] {
        if part.is_empty() {
            continue;
        }
        let mean = part.iter().map(|&(_, r)| r as f64).sum::<f64>() / part.len() as f64;
        println!(
            "  populace {label} ({:.0}–{:.0}): probíhá {mean:.1}",
            part[0].0,
            part[part.len() - 1].0
        );
    }
}
