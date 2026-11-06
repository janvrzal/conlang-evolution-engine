//! Pozadí dějin: drobné události, které svět generuje sám vedle událostí autora
//! (zrcadlo `background.py`).
//!
//! Mor, přesídlení, obchodní cesty, změny prestiže a cizí elity hýbou jazykem: přinášejí
//! výpůjčky a míšení, v malých populacích zesilují drift. Autor volí jen míru
//! (`Parameters::background_levels`); četnosti druhů jsou v `background_rates`, rozsahy
//! veličin v `background_spans`. Generátor je deterministický podle semínka světa a
//! vlastního proudu náhody (`Stream`), takže stejný svět dá stejné dějiny a na ostatní
//! náhodu enginu nesahá. Události pracují s kraji; vesnice si najdou až při provedení.
//!
//! Python bere náhodu z numpy; Rust z `Stream`, takže dějiny jsou jiné (bitová shoda
//! se neudržuje), mají ale stejné rozdělení.

use serde_json::json;

use crate::edits::{py_round, Edits, Field};
use crate::events::{conquest, migration, sorted, Action, Params, Scripted};
use crate::history::History;
use crate::ids::{GroupId, TerritoryId};
use crate::parameters::Parameters;
use crate::polity::{check_regions, groups_in, refresh, region_of, seat_of};
use crate::rng::{Part, Stream};
use crate::world::World;

/// Krok generátoru v letech (jako krok simulace).
pub const STEP: f64 = 25.0;

/// Druhy událostí pozadí.
#[derive(Clone, Debug)]
pub enum BackgroundAction {
    Plague {
        regions: Vec<String>,
        mortality: f64,
    },
    Recovery {
        regions: Vec<String>,
        factor: f64,
    },
    Resettlement {
        source: String,
        target: String,
        share: f64,
    },
    TradeShift {
        first: String,
        second: String,
        factor: f64,
    },
    PrestigeShift {
        region: String,
        factor: f64,
    },
    ForeignElite {
        conqueror: String,
        region: String,
    },
    EliteAssimilation {
        conqueror: String,
        region: String,
    },
}

impl BackgroundAction {
    pub fn kind(&self) -> &'static str {
        match self {
            BackgroundAction::Plague { .. } => "plague",
            BackgroundAction::Recovery { .. } => "recovery",
            BackgroundAction::Resettlement { .. } => "resettlement",
            BackgroundAction::TradeShift { .. } => "trade",
            BackgroundAction::PrestigeShift { .. } => "prestige",
            BackgroundAction::ForeignElite { .. } => "foreign_elite",
            BackgroundAction::EliteAssimilation { .. } => "elite_assimilation",
        }
    }

    fn params(&self) -> serde_json::Value {
        match self {
            BackgroundAction::Plague { regions, mortality } => {
                json!({"regions": regions, "mortality": mortality})
            }
            BackgroundAction::Recovery { regions, factor } => {
                json!({"regions": regions, "factor": factor})
            }
            BackgroundAction::Resettlement {
                source,
                target,
                share,
            } => {
                json!({"source": source, "target": target, "share": share})
            }
            BackgroundAction::TradeShift {
                first,
                second,
                factor,
            } => {
                json!({"regions": [first, second], "factor": factor})
            }
            BackgroundAction::PrestigeShift { region, factor } => {
                json!({"region": region, "factor": factor})
            }
            BackgroundAction::ForeignElite { conqueror, region }
            | BackgroundAction::EliteAssimilation { conqueror, region } => {
                json!({"conqueror": conqueror, "region": region})
            }
        }
    }
}

/// Rozebere událost pozadí; `None`, když druh sem nepatří.
pub fn parse(kind: &str, p: &Params<'_>) -> Result<Option<BackgroundAction>, String> {
    Ok(Some(match kind {
        "plague" => BackgroundAction::Plague {
            regions: p.strings(&["regions"])?,
            mortality: p.number(&["mortality"], 0.3)?,
        },
        "recovery" => BackgroundAction::Recovery {
            regions: p.strings(&["regions"])?,
            factor: p.number(&["factor"], 1.0)?,
        },
        "resettlement" => BackgroundAction::Resettlement {
            source: p.string(&["source"])?,
            target: p.string(&["target"])?,
            share: p.number(&["share"], 0.1)?,
        },
        "trade" => {
            let regions = p.strings(&["regions"])?;
            if regions.len() != 2 {
                return Err("obchodní cesta spojuje dva kraje".into());
            }
            BackgroundAction::TradeShift {
                first: regions[0].clone(),
                second: regions[1].clone(),
                factor: p.number(&["factor"], 1.0)?,
            }
        }
        "prestige" => BackgroundAction::PrestigeShift {
            region: p.string(&["region"])?,
            factor: p.number(&["factor"], 1.0)?,
        },
        "foreign_elite" => BackgroundAction::ForeignElite {
            conqueror: p.string(&["conqueror"])?,
            region: p.string(&["region"])?,
        },
        "elite_assimilation" => BackgroundAction::EliteAssimilation {
            conqueror: p.string(&["conqueror"])?,
            region: p.string(&["region"])?,
        },
        _ => return Ok(None),
    }))
}

fn region_ids(world: &World, names: &[String]) -> Result<Vec<TerritoryId>, String> {
    check_regions(world, names)
}

/// Provede událost pozadí.
pub fn apply(
    action: &BackgroundAction,
    year: f64,
    world: &mut World,
    history: &mut History,
    tick: u32,
) -> Result<(), String> {
    let edit = Edits::new(tick);
    match action {
        BackgroundAction::Plague { regions, mortality } => {
            let groups = groups_in(world, &region_ids(world, regions)?);
            for &group in &groups {
                let people = f64::from(world.groups.population[group.index()]);
                edit.set_group(
                    world,
                    group,
                    Field::Population(1.max(py_round(people * (1.0 - mortality))) as u32),
                )?;
            }
            history.record(
                "plague",
                tick,
                year,
                json!({
                    "regions": sorted(regions), "mortality": mortality,
                    "groups": groups.iter().map(|&g| world.group_name(g)).collect::<Vec<_>>(),
                    "background": true,
                }),
            );
        }
        BackgroundAction::Recovery { regions, factor } => {
            for group in groups_in(world, &region_ids(world, regions)?) {
                let people = f64::from(world.groups.population[group.index()]);
                edit.set_group(
                    world,
                    group,
                    Field::Population(1.max(py_round(people * factor)) as u32),
                )?;
            }
            history.record(
                "recovery",
                tick,
                year,
                json!({"regions": sorted(regions), "factor": factor, "background": true}),
            );
        }
        BackgroundAction::Resettlement {
            source,
            target,
            share,
        } => {
            let source_regions = region_ids(world, std::slice::from_ref(source))?;
            let target_regions = region_ids(world, std::slice::from_ref(target))?;
            let sources: Vec<(String, f64)> = groups_in(world, &source_regions)
                .into_iter()
                .map(|g| (world.group_name(g).to_owned(), *share))
                .collect();
            if sources.is_empty() || groups_in(world, &target_regions).is_empty() {
                return Ok(());
            }
            let seat = world
                .group_name(seat_of(world, target_regions[0])?)
                .to_owned();
            migration(
                world,
                &mut History::default(),
                tick,
                year,
                &sources,
                &seat,
                None,
                25.0,
                None,
                None,
            )?;
            history.record(
                "resettlement",
                tick,
                year,
                json!({"source": source, "target": target, "share": share, "background": true}),
            );
        }
        BackgroundAction::TradeShift {
            first,
            second,
            factor,
        } => {
            let (a_region, b_region) = (
                region_ids(world, std::slice::from_ref(first))?[0],
                region_ids(world, std::slice::from_ref(second))?[0],
            );
            let mut keys: Vec<(GroupId, GroupId)> = world.links.iter().map(|(k, _)| *k).collect();
            keys.sort_by(|a, b| {
                (world.group_name(a.0), world.group_name(a.1))
                    .cmp(&(world.group_name(b.0), world.group_name(b.1)))
            });
            let mut changed = 0;
            for (a, b) in keys {
                if world.group_name(a) > world.group_name(b)
                    || world.groups.written[a.index()]
                    || world.groups.written[b.index()]
                {
                    continue;
                }
                let (ra, rb) = (region_of(world, a), region_of(world, b));
                let same_pair = (ra == Some(a_region) && rb == Some(b_region))
                    || (ra == Some(b_region) && rb == Some(a_region));
                if !same_pair {
                    continue;
                }
                let link = *world.links.get(a, b).ok_or("vazba zmizela")?;
                edit.connect(world, a, b, link.strength * factor, link.kind)?;
                // Co obchodní cesta přidala (nebo ubrala) ze síly vazby, patří kanálu
                // `trade`; po jejím úpadku zůstane obecný kontakt sousedů.
                let kept = world.links.get(a, b).map_or(0.0, |l| l.strength);
                let key = if a < b { (a, b) } else { (b, a) };
                let carried = world.society.trade.get(&key).copied().unwrap_or(0.0)
                    + link.strength * (factor - 1.0);
                edit.set_trade(world, a, b, (carried > 0.0).then(|| kept.min(carried)))?;
                changed += 1;
            }
            history.record(
                "trade",
                tick,
                year,
                json!({"regions": [first, second], "factor": factor, "links": changed, "background": true}),
            );
        }
        BackgroundAction::PrestigeShift { region, factor } => {
            for group in groups_in(world, &region_ids(world, std::slice::from_ref(region))?) {
                let base = world
                    .society
                    .base_prestige
                    .get(&group)
                    .copied()
                    .unwrap_or(world.groups.prestige[group.index()]);
                edit.set_base_prestige(world, group, Some(base * factor))?;
                edit.set_group(world, group, Field::Prestige(base * factor))?;
            }
            refresh(world, tick)?;
            history.record(
                "prestige",
                tick,
                year,
                json!({"region": region, "factor": factor, "background": true}),
            );
        }
        BackgroundAction::ForeignElite { conqueror, region } => {
            let region_id = region_ids(world, std::slice::from_ref(region))?[0];
            let conqueror_id = region_ids(world, std::slice::from_ref(conqueror))?[0];
            let subjects: Vec<String> = groups_in(world, &[region_id])
                .into_iter()
                .map(|g| world.group_name(g).to_owned())
                .collect();
            if subjects.is_empty() || groups_in(world, &[conqueror_id]).is_empty() {
                return Ok(());
            }
            let seat = seat_of(world, region_id)?;
            let ruler = world.group_name(seat_of(world, conqueror_id)?).to_owned();
            let territory = world.groups.territory[seat.index()];
            let territory_name = world.registry.territories.name(territory.0).to_owned();
            let elite_name = format!("{territory_name}+{ruler}");
            if world
                .registry
                .groups
                .get(&elite_name)
                .is_some_and(|g| world.groups.contains(GroupId(g)))
            {
                return Ok(());
            }
            let params = world.params.clone();
            let population = 20.max(py_round(
                f64::from(world.groups.population[seat.index()]) * params.background_elite_share,
            )) as u32;
            conquest(
                world,
                &mut History::default(),
                tick,
                year,
                &ruler,
                &territory_name,
                &subjects,
                population,
                params.background_elite_prestige,
                params.background_elite_link,
            )?;
            history.record(
                "foreign_elite",
                tick,
                year,
                json!({"conqueror": conqueror, "region": region, "background": true}),
            );
        }
        BackgroundAction::EliteAssimilation { conqueror, region } => {
            let rulers = groups_in(world, &region_ids(world, std::slice::from_ref(conqueror))?);
            let Some(&first) = rulers.first() else {
                return Ok(());
            };
            let language = world.groups.main_code(first).language;
            let ended: Vec<GroupId> =
                groups_in(world, &region_ids(world, std::slice::from_ref(region))?)
                    .into_iter()
                    .filter(|&g| {
                        world.group_name(g).contains('+')
                            && world.groups.main_code(g).language == language
                    })
                    .collect();
            let names: Vec<String> = ended
                .iter()
                .map(|&g| world.group_name(g).to_owned())
                .collect();
            for group in ended {
                edit.remove_group(world, group)?;
            }
            if !names.is_empty() {
                history.record(
                    "elite_assimilation",
                    tick,
                    year,
                    json!({"conqueror": conqueror, "region": region, "groups": names, "background": true}),
                );
            }
        }
    }
    Ok(())
}

/// Kraj pro generátor: jméno, sousedé a protojazyk.
pub struct BackgroundRegion {
    pub id: String,
    pub neighbours: Vec<String>,
    pub language: String,
}

fn span(rng: &mut Stream, params: &Parameters, name: &str) -> Result<f64, String> {
    let table = params
        .background_spans
        .get(name)
        .ok_or_else(|| format!("chybí rozsah pozadí '{name}'"))?;
    Ok(table["low"] + (table["high"] - table["low"]) * rng.random())
}

fn steps(rng: &mut Stream, params: &Parameters, name: &str) -> Result<u32, String> {
    let table = params
        .background_spans
        .get(name)
        .ok_or_else(|| format!("chybí rozsah pozadí '{name}'"))?;
    let (low, high) = (table["low"] as u64, table["high"] as u64);
    Ok((low + rng.integers(high - low + 1)) as u32)
}

fn round_to(value: f64, places: i32) -> f64 {
    let scale = 10f64.powi(places);
    (value * scale).round_ties_even() / scale
}

/// Události pozadí pro kraje mezi `start` a `end` (po událostech autora ve stejném roce).
pub fn generate(
    regions: &[BackgroundRegion],
    start: f64,
    end: f64,
    level_name: &str,
    seed: i64,
    params: &Parameters,
) -> Result<Vec<Box<dyn crate::events::WorldEvent>>, String> {
    let scale = *params
        .background_levels
        .get(level_name)
        .ok_or_else(|| format!("Neznámá míra pozadí dějin '{level_name}'."))?;
    if scale <= 0.0 {
        return Ok(Vec::new());
    }
    let mut rng = Stream::new(seed as u64, &[Part::Str("background")]);
    let mut order: Vec<&BackgroundRegion> = regions.iter().collect();
    order.sort_by(|a, b| a.id.cmp(&b.id));
    let mut events: Vec<Box<dyn crate::events::WorldEvent>> = Vec::new();
    let mut push = |year: f64, action: BackgroundAction| {
        events.push(Box::new(Scripted {
            year,
            kind: action.kind().to_owned(),
            params: action.params(),
            action: Action::Background(action),
        }));
    };
    let mut year = start + STEP;
    while year < end {
        for region in &order {
            let mut near = region.neighbours.clone();
            near.sort();
            near.dedup();
            for kind in [
                "plague",
                "resettlement",
                "trade",
                "prestige",
                "foreign_elite",
            ] {
                let rate = params.background_rates.get(kind).copied().unwrap_or(0.0);
                let expected = rate * scale * STEP / 100.0;
                if expected <= 0.0 || rng.poisson(expected) == 0 {
                    continue;
                }
                match kind {
                    "plague" => {
                        let mortality = round_to(span(&mut rng, params, "plague_mortality")?, 2);
                        push(
                            year,
                            BackgroundAction::Plague {
                                regions: vec![region.id.clone()],
                                mortality,
                            },
                        );
                        let later =
                            year + STEP * f64::from(steps(&mut rng, params, "recovery_steps")?);
                        if later < end {
                            push(
                                later,
                                BackgroundAction::Recovery {
                                    regions: vec![region.id.clone()],
                                    factor: round_to(1.0 / (1.0 - mortality), 3),
                                },
                            );
                        }
                    }
                    "resettlement" if !near.is_empty() => {
                        let target = near[rng.integers(near.len() as u64) as usize].clone();
                        let share = round_to(span(&mut rng, params, "resettlement_share")?, 2);
                        push(
                            year,
                            BackgroundAction::Resettlement {
                                source: region.id.clone(),
                                target,
                                share,
                            },
                        );
                    }
                    "trade" if !near.is_empty() => {
                        let other = near[rng.integers(near.len() as u64) as usize].clone();
                        let (first, second) = if region.id <= other {
                            (region.id.clone(), other)
                        } else {
                            (other, region.id.clone())
                        };
                        let factor = round_to(span(&mut rng, params, "trade_factor")?, 2);
                        push(
                            year,
                            BackgroundAction::TradeShift {
                                first: first.clone(),
                                second: second.clone(),
                                factor,
                            },
                        );
                        let later =
                            year + STEP * f64::from(steps(&mut rng, params, "trade_steps")?);
                        if later < end {
                            push(
                                later,
                                BackgroundAction::TradeShift {
                                    first,
                                    second,
                                    factor: round_to(1.0 / factor, 3),
                                },
                            );
                        }
                    }
                    "prestige" => {
                        let factor = round_to(span(&mut rng, params, "prestige_factor")?, 2);
                        push(
                            year,
                            BackgroundAction::PrestigeShift {
                                region: region.id.clone(),
                                factor,
                            },
                        );
                    }
                    "foreign_elite" => {
                        let foreign: Vec<&String> = near
                            .iter()
                            .filter(|other| {
                                regions
                                    .iter()
                                    .find(|r| &r.id == *other)
                                    .is_none_or(|r| r.language != region.language)
                            })
                            .collect();
                        if !foreign.is_empty() {
                            let conqueror =
                                foreign[rng.integers(foreign.len() as u64) as usize].clone();
                            push(
                                year,
                                BackgroundAction::ForeignElite {
                                    conqueror: conqueror.clone(),
                                    region: region.id.clone(),
                                },
                            );
                            let later =
                                year + STEP * f64::from(steps(&mut rng, params, "elite_steps")?);
                            if later < end {
                                push(
                                    later,
                                    BackgroundAction::EliteAssimilation {
                                        conqueror,
                                        region: region.id.clone(),
                                    },
                                );
                            }
                        }
                    }
                    _ => {}
                }
            }
        }
        year += STEP;
    }
    Ok(events)
}
