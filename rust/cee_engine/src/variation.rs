//! Souběžná variabilita slovní zásoby protojazyka (zrcadlo `cee.v2.variation`).
//!
//! Protojazyk má pro každý pojem jediné slovo, živý jazyk ale žije s rozpracovanými
//! změnami: synonyma, nová slova u části mluvčích, posuny významu na půli cesty, a to jako
//! nářeční kontinuum, kde menšinové varianty vesnice jsou z velké části slova sousedů. Engine
//! ji proto rozdá při tvorbě světa bez simulace, podle statistiky naměřené na ustálených
//! sítích vesnic (`v2_standing_variation.json`, `data::STANDING_VARIATION_JSON`):
//!
//! - **tvar** variability podle frekvence pojmu (hustota přeživších variant každého druhu
//!   změny, kvantily vrcholového podílu, dosah k sousedům),
//! - **množství** variability vesnice podle naměřeného modelu (otevřenost, populace,
//!   efektivní počet zdrojů řeči).
//!
//! Síť se čte jako graf: vesnice `j` přejímá od souseda `k` podíl `o_j · w_jk` a
//! `G = (I − γ·B)⁻¹` sečte všechny cesty s útlumem [`GRAPH_DECAY`]. Pro každou vesnici se
//! z modelu spočte cíl a dopočtou činitele hustoty a vrcholového podílu původců (z
//! očekávaných hodnot, bez losování); potom se pro každý pojem, vesnici a druh změny vylosuje
//! počet variant a skutečná změna navrhne skutečné slovo. Slovo autora zůstane převládající:
//! součet menšin u pojmu je nanejvýš `Parameters::variation_cap`.
//!
//! **Odchylka od Pythonu:** náhoda je z proudu `Stream` (klíč semínko, `variation`, proměnná,
//! skupina), ne z numpy; shodu s Pythonem engine v Rustu nepřebírá. Matici `G` počítá
//! Gaussova eliminace s výběrem pivota.

use std::collections::{BTreeMap, HashSet};

use serde::Deserialize;

use crate::changes::InnovationContext;
use crate::data::STANDING_VARIATION_JSON;
use crate::ids::{GroupId, VariableId, VariantId};
use crate::model::repertoire::{Distribution, VariableKind};
use crate::rng::{Part, Stream};
use crate::world::World;

/// Nejvzdálenější soused (počet vazeb), kam varianta z vesnice sahá.
const REACH: usize = 3;
/// Útlum cesty grafem vazeb na jeden krok.
const GRAPH_DECAY: f64 = 0.9;
/// Body rovnoměrné náhody pro očekávané hodnoty vrcholového podílu.
const GRID: usize = 400;
/// Kola dopočtu činitelů vesnic.
const ROUNDS: usize = 8;
const DENSITY_BOUNDS: (f64, f64) = (1e-3, 1e3);
const SHARE_BOUNDS: (f64, f64) = (0.05, 20.0);

#[derive(Deserialize)]
struct Bin {
    density: BTreeMap<String, f64>,
    peak: Vec<f64>,
    graph_scale: f64,
}

#[derive(Deserialize)]
struct Knots {
    openness: Vec<f64>,
    population: Vec<f64>,
}

#[derive(Deserialize)]
struct Ranges {
    sources: Vec<f64>,
}

#[derive(Deserialize)]
struct Delivery {
    count: f64,
    mass: f64,
}

#[derive(Deserialize)]
struct Model {
    knots: Knots,
    ranges: Ranges,
    count: Vec<f64>,
    mass: Vec<f64>,
    delivery: Option<Delivery>,
}

#[derive(Deserialize)]
struct Measured {
    edges: Vec<f64>,
    quantiles: Vec<f64>,
    min_share: f64,
    bins: Vec<Bin>,
    village_model: Model,
}

fn measured() -> Result<Measured, String> {
    serde_json::from_str(STANDING_VARIATION_JSON)
        .map_err(|e| format!("v2_standing_variation.json: {e}"))
}

/// Lineární interpolace jako `np.interp` (mimo rozsah platí krajní hodnota).
fn interp(x: f64, xs: &[f64], ys: &[f64]) -> f64 {
    if x <= xs[0] {
        return ys[0];
    }
    let last = xs.len() - 1;
    if x >= xs[last] {
        return ys[last];
    }
    let at = xs.partition_point(|&v| v <= x) - 1;
    let part = (x - xs[at]) / (xs[at + 1] - xs[at]);
    ys[at] + part * (ys[at + 1] - ys[at])
}

/// Matice `G = (I − γ·B)⁻¹`: kolik řeči vesnice (řádek) pochází z vesnice (sloupec).
///
/// `B[j, k] = o_j · w_jk` (otevřenost `j` krát síla vazby `j → k` poměrně k součtu vazeb `j`).
fn source_graph(world: &World, groups: &[GroupId]) -> Vec<f64> {
    let n = groups.len();
    let mut weights = vec![0.0; n * n];
    for (&(first, second), link) in world.links.iter() {
        let (Some(a), Some(b)) = (
            groups.iter().position(|&g| g == first),
            groups.iter().position(|&g| g == second),
        ) else {
            continue;
        };
        if link.strength > 0.0 {
            weights[a * n + b] = link.strength;
        }
    }
    let mut matrix = vec![0.0; n * n];
    for j in 0..n {
        let total: f64 = weights[j * n..(j + 1) * n].iter().sum();
        let openness = world.groups.openness[groups[j].index()];
        for k in 0..n {
            let b = if total > 0.0 {
                weights[j * n + k] / total
            } else {
                0.0
            };
            matrix[j * n + k] = f64::from(u8::from(j == k)) - GRAPH_DECAY * openness * b;
        }
    }
    invert(matrix, n)
}

/// Inverze matice Gaussovou eliminací s částečným výběrem pivota.
fn invert(mut a: Vec<f64>, n: usize) -> Vec<f64> {
    let mut inverse = vec![0.0; n * n];
    for i in 0..n {
        inverse[i * n + i] = 1.0;
    }
    for column in 0..n {
        let mut pivot = column;
        for row in column + 1..n {
            if a[row * n + column].abs() > a[pivot * n + column].abs() {
                pivot = row;
            }
        }
        if pivot != column {
            for k in 0..n {
                a.swap(column * n + k, pivot * n + k);
                inverse.swap(column * n + k, pivot * n + k);
            }
        }
        let diagonal = a[column * n + column];
        for k in 0..n {
            a[column * n + k] /= diagonal;
            inverse[column * n + k] /= diagonal;
        }
        for row in 0..n {
            if row == column {
                continue;
            }
            let factor = a[row * n + column];
            if factor == 0.0 {
                continue;
            }
            for k in 0..n {
                a[row * n + k] -= factor * a[column * n + k];
                inverse[row * n + k] -= factor * inverse[column * n + k];
            }
        }
    }
    inverse
}

/// Otevřenost, populace a efektivní počet zdrojů každé vesnice (inverzní Simpsonův index
/// řádku grafu bez vesnice samotné; vesnice bez vazeb má nulový).
fn village_features(world: &World, groups: &[GroupId], graph: &[f64]) -> Vec<(f64, f64, f64)> {
    let n = groups.len();
    (0..n)
        .map(|j| {
            let (mut total, mut squares) = (0.0, 0.0);
            for k in (0..n).filter(|&k| k != j) {
                total += graph[j * n + k];
                squares += graph[j * n + k] * graph[j * n + k];
            }
            let sources = if squares > 0.0 {
                total * total / squares
            } else {
                0.0
            };
            (
                world.groups.openness[groups[j].index()],
                f64::from(world.groups.population[groups[j].index()]),
                sources,
            )
        })
        .collect()
}

/// Váhy uzlů pro lineární interpolaci (dva sousední uzly, jinak nula).
fn tent(knots: &[f64], value: f64) -> Vec<f64> {
    let value = value.clamp(knots[0], knots[knots.len() - 1]);
    let at = (knots.partition_point(|&k| k <= value) - 1).min(knots.len() - 2);
    let part = (value - knots[at]) / (knots[at + 1] - knots[at]);
    let mut weights = vec![0.0; knots.len()];
    weights[at] = 1.0 - part;
    weights[at + 1] = part;
    weights
}

/// Členy modelu množství variability vesnice: tabulka nad uzly otevřenosti a populace
/// (bilineární interpolace v logaritmech) a člen `ln max(zdroje, 1)`.
fn model_terms(model: &Model, features: (f64, f64, f64)) -> Vec<f64> {
    let (openness, population, sources) = features;
    let range = &model.ranges.sources;
    let sources = sources.clamp(range[0], range[1]);
    let logs = |values: &[f64]| values.iter().map(|v| v.ln()).collect::<Vec<f64>>();
    let across = tent(&logs(&model.knots.openness), openness.max(1e-9).ln());
    let down = tent(&logs(&model.knots.population), population.max(1.0).ln());
    let mut terms = Vec::new();
    for a in &across {
        for b in &down {
            terms.push(a * b);
        }
    }
    terms.push(sources.max(1.0).ln());
    terms
}

/// Ustálený počet menšinových variant a jejich masa ve vesnici podle modelu.
fn target(model: &Model, features: (f64, f64, f64)) -> (f64, f64) {
    let terms = model_terms(model, features);
    let linear = |coefficients: &[f64]| -> f64 {
        coefficients
            .iter()
            .zip(&terms)
            .map(|(c, t)| c * t)
            .sum::<f64>()
            .exp()
            - 1.0
    };
    (linear(&model.count).max(0.0), linear(&model.mass).max(0.0))
}

/// Vesnice do `REACH` vazeb od každé vesnice: pozice vesnice → (pozice, počet vazeb) v pořadí objevení.
fn distances(world: &World, groups: &[GroupId]) -> Vec<Vec<(usize, usize)>> {
    let n = groups.len();
    let mut near: Vec<Vec<usize>> = vec![Vec::new(); n];
    for (a, &first) in groups.iter().enumerate() {
        let mut targets: Vec<(usize, GroupId)> = world
            .links
            .from(first)
            .filter(|(_, link)| link.strength > 0.0)
            .filter_map(|(second, _)| {
                groups
                    .iter()
                    .position(|&g| g == second)
                    .map(|b| (b, second))
            })
            .collect();
        targets.sort_by(|x, y| {
            world
                .registry
                .groups
                .name(x.1 .0)
                .cmp(world.registry.groups.name(y.1 .0))
        });
        near[a] = targets.into_iter().map(|t| t.0).collect();
    }
    (0..n)
        .map(|start| {
            let mut depth = vec![(start, 0_usize)];
            let mut seen: HashSet<usize> = HashSet::from([start]);
            let mut frontier = vec![start];
            for level in 1..=REACH {
                let mut following = Vec::new();
                for &group in &frontier {
                    for &other in &near[group] {
                        if seen.insert(other) {
                            depth.push((other, level));
                            following.push(other);
                        }
                    }
                }
                frontier = following;
            }
            depth
        })
        .collect()
}

/// Kam varianta z původce sahá: vesnice stejného jazyka do `REACH` vazeb a `G[j, i] / G[i, i]`;
/// původce sám je první s poměrem 1.
fn spread(world: &World, groups: &[GroupId], graph: &[f64]) -> Vec<Vec<(usize, f64)>> {
    let n = groups.len();
    distances(world, groups)
        .into_iter()
        .enumerate()
        .map(|(origin, near)| {
            let language = world.groups.main_code(groups[origin]).language;
            let own = graph[origin * n + origin];
            let mut found = vec![(origin, 1.0)];
            for (other, _) in near {
                if other != origin && world.groups.main_code(groups[other]).language == language {
                    found.push((other, graph[other * n + origin] / own));
                }
            }
            found
        })
        .collect()
}

fn bounded(value: f64, bounds: (f64, f64)) -> f64 {
    value.clamp(bounds.0, bounds.1)
}

/// Činitele hustoty a vrcholového podílu původců, aby vesnice dostaly cílové množství.
///
/// Očekávaný příspěvek původce `i` do vesnice `j`: pro každý koš frekvence součet hustot druhů
/// přes pojmy, u kterých druh v `i` jde navrhnout, krát pravděpodobnost, že podíl dosáhne prahu
/// (počet), resp. jeho střední hodnota nad prahem (masa). Činitele se dopočtou v několika kolech.
fn factors(
    data: &Measured,
    features: &[(f64, f64, f64)],
    rates: &[Vec<f64>],
    spread: &[Vec<(usize, f64)>],
) -> (Vec<f64>, Vec<f64>) {
    let model = &data.village_model;
    let delivery = model
        .delivery
        .as_ref()
        .map_or((1.0, 1.0), |d| (d.count, d.mass));
    let targets: Vec<(f64, f64)> = features
        .iter()
        .map(|&f| {
            let (count, mass) = target(model, f);
            (count / delivery.0, mass / delivery.1)
        })
        .collect();
    let grid: Vec<f64> = (0..GRID).map(|i| (i as f64 + 0.5) / GRID as f64).collect();
    let shape: Vec<Vec<f64>> = data
        .bins
        .iter()
        .map(|bin| {
            grid.iter()
                .map(|&u| interp(u, &data.quantiles, &bin.peak))
                .collect()
        })
        .collect();
    let n = features.len();
    let mut density = vec![1.0; n];
    let mut share = vec![1.0; n];
    let floor = data.min_share;
    for _ in 0..ROUNDS {
        let mut count = vec![0.0; n];
        let mut mass = vec![0.0; n];
        for origin in 0..n {
            for (index, values) in shape.iter().enumerate() {
                let rate = rates[origin][index] * density[origin];
                if rate <= 0.0 {
                    continue;
                }
                let reach = data.bins[index].graph_scale;
                for &(other, relative) in &spread[origin] {
                    let (mut above_count, mut above_mass) = (0.0, 0.0);
                    for &value in values {
                        let peak = (share[origin] * value).min(1.0);
                        let found = if other == origin {
                            peak
                        } else {
                            (peak * reach * relative).min(1.0)
                        };
                        if found >= floor {
                            above_count += 1.0;
                            above_mass += found;
                        }
                    }
                    count[other] += rate * above_count / values.len() as f64;
                    mass[other] += rate * above_mass / values.len() as f64;
                }
            }
        }
        for g in 0..n {
            let (wanted_count, wanted_mass) = targets[g];
            if count[g] <= 0.0 || mass[g] <= 0.0 || wanted_count <= 0.0 {
                continue;
            }
            density[g] = bounded(density[g] * wanted_count / count[g], DENSITY_BOUNDS);
            let per_variant = (wanted_mass / wanted_count) / (mass[g] / count[g]);
            share[g] = bounded(share[g] * per_variant, SHARE_BOUNDS);
        }
    }
    (density, share)
}

/// Dá výchozím vesnicím souběžnou variabilitu slovní zásoby.
pub fn seed(world: &mut World) -> Result<(), String> {
    let scale = world.params.standing_variation;
    if scale <= 0.0 || world.semantics.is_none() || world.table.is_none() {
        return Ok(());
    }
    let mut lexical: Vec<VariableId> = (0..world.variables.len())
        .map(VariableId::new)
        .filter(|v| world.variables.kind[v.index()] == VariableKind::Lexical)
        .collect();
    lexical.sort_by(|a, b| {
        world
            .registry
            .variables
            .name(a.0)
            .cmp(world.registry.variables.name(b.0))
    });
    let groups: Vec<GroupId> = world
        .group_ids()
        .into_iter()
        .filter(|g| !world.groups.written[g.index()])
        .collect();
    if lexical.is_empty() || groups.is_empty() {
        return Ok(());
    }
    let data = measured()?;
    let changes = crate::changes::lexicon::changes();
    let kinds: Vec<&str> = {
        let mut all: Vec<&str> = data
            .bins
            .iter()
            .flat_map(|b| b.density.keys().map(String::as_str))
            .collect();
        all.sort_unstable();
        all.dedup();
        all
    };
    let find = |kind: &str| changes.iter().find(|c| c.kind() == kind);
    let graph = source_graph(world, &groups);
    let spread = spread(world, &groups, &graph);
    let features = village_features(world, &groups, &graph);
    let start_year = world.start_year;
    let contexts: Vec<InnovationContext> = groups
        .iter()
        .map(|&group| InnovationContext {
            group,
            tick: 0,
            year: start_year,
        })
        .collect();
    // Místa každého druhu změny ve vesnicích.
    let mut sites: BTreeMap<(usize, &str), HashSet<VariableId>> = BTreeMap::new();
    for (g, context) in contexts.iter().enumerate() {
        for &kind in &kinds {
            if let Some(change) = find(kind) {
                let found = change.weighted_sites(world, context).sites;
                sites.insert((g, kind), found.into_iter().collect());
            }
        }
    }
    let bin_of: Vec<usize> = lexical
        .iter()
        .map(|&variable| {
            let concept = world.variables.concept[variable.index()];
            let frequency = world.concept_frequency(concept);
            data.edges.partition_point(|&e| e <= frequency)
        })
        .collect();
    // Hustota druhů změn podle koše a vesnice (součet přes pojmy, kde druh jde navrhnout).
    let mut rates = vec![vec![0.0; data.bins.len()]; groups.len()];
    for (v, &variable) in lexical.iter().enumerate() {
        let entry = &data.bins[bin_of[v]];
        for (g, row) in rates.iter_mut().enumerate() {
            for (kind, rate) in &entry.density {
                if sites
                    .get(&(g, kind.as_str()))
                    .is_some_and(|set| set.contains(&variable))
                {
                    row[bin_of[v]] += rate;
                }
            }
        }
    }
    let (density, share) = factors(&data, &features, &rates, &spread);

    let mut minorities: BTreeMap<(usize, usize), BTreeMap<VariantId, f64>> = BTreeMap::new();
    for (v, &variable) in lexical.iter().enumerate() {
        let entry = &data.bins[bin_of[v]];
        let variable_name = world.registry.variables.name(variable.0).to_owned();
        for (g, &group) in groups.iter().enumerate() {
            let group_name = world.group_name(group).to_owned();
            let mut rng = Stream::new(
                world.seed as u64,
                &[
                    Part::Str("variation"),
                    Part::Str(&variable_name),
                    Part::Str(&group_name),
                ],
            );
            let mut index = 0;
            for (kind, &rate) in &entry.density {
                let Some(change) = find(kind) else { continue };
                if !sites
                    .get(&(g, kind.as_str()))
                    .is_some_and(|set| set.contains(&variable))
                {
                    continue;
                }
                let drawn = rng.poisson(rate * scale * density[g]);
                for _ in 0..drawn {
                    index += 1;
                    let peak =
                        (share[g] * interp(rng.random(), &data.quantiles, &entry.peak)).min(1.0);
                    let Some(proposed) =
                        change.propose(world, &contexts[g], variable, &mut rng, index)
                    else {
                        continue;
                    };
                    let known = world
                        .registry
                        .variants
                        .get(&proposed.name)
                        .is_some_and(|n| (n as usize) < world.variants.len());
                    if known {
                        continue;
                    }
                    let id = world.store_variant(
                        &proposed.name,
                        proposed.variable,
                        proposed.payload,
                        proposed.origin,
                    );
                    for &(other, relative) in &spread[g] {
                        let found_share = if other == g {
                            peak
                        } else {
                            (peak * entry.graph_scale * relative).min(1.0)
                        };
                        if found_share >= data.min_share {
                            *minorities
                                .entry((other, v))
                                .or_default()
                                .entry(id)
                                .or_insert(0.0) += found_share;
                        }
                    }
                }
            }
        }
    }
    // Odvozené pohledy se postaví znovu z aktuálního stavu.
    for &group in &groups {
        world
            .groups
            .main_code_mut(group)
            .phonology
            .grammar
            .cache
            .clear();
    }
    let cap = world.params.variation_cap;
    for ((g, v), minority) in minorities {
        let (group, variable) = (groups[g], lexical[v]);
        let Some(before) = world.distribution(group, variable) else {
            continue;
        };
        if !before.is_fixed() {
            continue;
        }
        let total: f64 = minority.values().sum();
        let factor = (cap / total).min(1.0);
        let mut pairs: Vec<(VariantId, f64)> = minority
            .into_iter()
            .map(|(id, value)| (id, value * factor))
            .collect();
        let rest = 1.0 - pairs.iter().map(|p| p.1).sum::<f64>();
        pairs.push((before.variants[0], rest));
        let distribution = Distribution::from_pairs(pairs, &world.registry.variants);
        world
            .groups
            .main_code_mut(group)
            .repertoire
            .set(variable, distribution);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn inverze_nasobena_puvodni_je_jednotkova() {
        let a = vec![4.0, 1.0, 0.5, 1.0, 3.0, 0.2, 0.0, 0.5, 2.0];
        let inverse = invert(a.clone(), 3);
        for i in 0..3 {
            for j in 0..3 {
                let value: f64 = (0..3).map(|k| a[i * 3 + k] * inverse[k * 3 + j]).sum();
                assert!((value - f64::from(u8::from(i == j))).abs() < 1e-12);
            }
        }
    }

    #[test]
    fn interpolace_jako_numpy() {
        let xs = [0.0, 0.5, 1.0];
        let ys = [0.0, 1.0, 3.0];
        assert_eq!(interp(-1.0, &xs, &ys), 0.0);
        assert_eq!(interp(2.0, &xs, &ys), 3.0);
        assert!((interp(0.75, &xs, &ys) - 2.0).abs() < 1e-12);
    }

    #[test]
    fn stan_uzlu_je_rozdeleni_vahy() {
        let weights = tent(&[1.0, 2.0, 4.0], 3.0);
        assert_eq!(weights, vec![0.0, 0.5, 0.5]);
        assert_eq!(tent(&[1.0, 2.0, 4.0], 0.0), vec![1.0, 0.0, 0.0]);
    }
}
