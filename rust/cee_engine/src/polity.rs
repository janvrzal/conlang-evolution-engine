//! Státy, jazyková politika, lingua franca a spisovné jazyky (zrcadlo `polity.py`).
//!
//! Stát svůj jazyk nešíří přímo. Mění tři věci a jazyk se pak šíří sám mechanismy,
//! které engine už má: **prestiž** (vesnice hlavního města), **sítě** (centralizace
//! spojí vesnice státu se sídlem) a **domény** (regiony jiného jazyka užívají úřední
//! jazyk mimo domov; politika určuje, jak silně se tlačí i domů).
//!
//! Hranice se nezadávají: vznikají tam, kde sousedí regiony různých států
//! ([`refresh`]). Prestiž se po každé události státu spočítá znovu ze stavu světa:
//! základ × hlavní město existujícího státu × vlastní spisovná norma.
//!
//! Čísla jsou v `Parameters` (`policy_levels`, `centralization_levels`, …); autor zadává
//! jen slovní úrovně. Všechny změny jdou přes [`Edits`].

use std::collections::BTreeMap;

use serde_json::{json, Value};

use crate::edits::{group_named, neighbors, py_round, territory_named, Edits, Field, StateChange};
use crate::events::{
    codification, language_shift, printing, schooling_event, Params, ShiftOptions,
};
use crate::history::History;
use crate::ids::{GroupId, LanguageId, TerritoryId};
use crate::model::group::Domain;
use crate::model::links::LinkKind;
use crate::model::territory::TerritoryLevel;
use crate::parameters::{Table, Table2};
use crate::state::society::Polity;
use crate::world::World;

/// Rozebraná událost státu a politiky.
#[derive(Clone, Debug)]
pub enum PolityAction {
    State(StateSpec),
    LanguagePolicy {
        state: String,
        policy: String,
    },
    Annexation {
        state: String,
        regions: Vec<String>,
    },
    LinguaFranca {
        source: String,
        regions: Vec<String>,
        spread: String,
        nativize: bool,
    },
    Secession(StateSpec),
    Collapse {
        state: String,
    },
    BorderPolicy {
        state: String,
        border: String,
    },
    Preserve {
        regions: Vec<String>,
        language: Option<String>,
        preserved: bool,
    },
    Identity {
        regions: Vec<String>,
        identity: String,
    },
    Immigration {
        regions: Vec<String>,
        immigration: f64,
    },
    Revival {
        regions: Vec<String>,
        language: Option<String>,
        strength: String,
    },
    Standard {
        of: String,
        literacy: String,
    },
    Schools {
        of: String,
        coverage: String,
        printing: bool,
        diglossic: bool,
    },
}

/// Parametry vzniku státu (`State`, `Secession`).
#[derive(Clone, Debug)]
pub struct StateSpec {
    pub id: String,
    pub regions: Vec<String>,
    pub capital: String,
    pub centralization: String,
    pub policy: String,
    pub border: String,
    pub name: Option<String>,
    /// Úřední jazyk (jméno linie); `None` = jazyk největší vesnice hlavního regionu. Sídlem je
    /// pak největší skupina hlavního regionu, která tímto jazykem mluví (franská říše úřadovala
    /// latinsky, i když venkov ještě mluvil galsky).
    pub language: Option<String>,
}

/// Rozebere druh události státu; `None`, když druh sem nepatří.
pub fn parse(kind: &str, p: &Params<'_>) -> Result<Option<PolityAction>, String> {
    let state_spec = || -> Result<StateSpec, String> {
        Ok(StateSpec {
            id: p.string(&["id"])?,
            regions: p.strings(&["regions"])?,
            capital: p.string(&["capital"])?,
            centralization: p
                .opt_string(&["centralization"])?
                .unwrap_or_else(|| "moderate".into()),
            policy: p
                .opt_string(&["policy"])?
                .unwrap_or_else(|| "tolerant".into()),
            border: p
                .opt_string(&["border"])?
                .unwrap_or_else(|| "normal".into()),
            name: p.opt_string(&["name"])?,
            language: p.opt_string(&["language"])?,
        })
    };
    Ok(Some(match kind {
        "state" => PolityAction::State(state_spec()?),
        "secession" => PolityAction::Secession(state_spec()?),
        "language_policy" => PolityAction::LanguagePolicy {
            state: p.string(&["state"])?,
            policy: p.string(&["policy"])?,
        },
        "annexation" => PolityAction::Annexation {
            state: p.string(&["state"])?,
            regions: p.strings(&["regions"])?,
        },
        "lingua_franca" => PolityAction::LinguaFranca {
            source: p.string(&["source"])?,
            regions: p.strings(&["regions"])?,
            spread: p
                .opt_string(&["spread"])?
                .unwrap_or_else(|| "common".into()),
            nativize: p.flag(&["nativize"], false)?,
        },
        "collapse" => PolityAction::Collapse {
            state: p.string(&["state"])?,
        },
        "border_policy" => PolityAction::BorderPolicy {
            state: p.string(&["state"])?,
            border: p.string(&["border"])?,
        },
        "preserve" => PolityAction::Preserve {
            regions: p.strings(&["regions"])?,
            language: p.opt_string(&["language"])?,
            preserved: p.flag(&["preserved"], true)?,
        },
        "identity" => PolityAction::Identity {
            regions: p.strings(&["regions"])?,
            identity: p.string(&["identity"])?,
        },
        "immigration" => PolityAction::Immigration {
            regions: p.strings(&["regions"])?,
            immigration: p.number(&["immigration"], 0.0)?,
        },
        "revival" => PolityAction::Revival {
            regions: p.strings(&["regions"])?,
            language: p.opt_string(&["language"])?,
            strength: p
                .opt_string(&["strength"])?
                .unwrap_or_else(|| "movement".into()),
        },
        "standard" => PolityAction::Standard {
            of: p.string(&["of"])?,
            literacy: p
                .opt_string(&["literacy"])?
                .unwrap_or_else(|| "elite".into()),
        },
        "schools" => PolityAction::Schools {
            of: p.string(&["of"])?,
            coverage: p
                .opt_string(&["coverage"])?
                .unwrap_or_else(|| "mass".into()),
            printing: p.flag(&["printing"], true)?,
            diglossic: p.flag(&["diglossic"], false)?,
        },
        _ => return Ok(None),
    }))
}

/// Provede událost státu.
pub fn apply(
    action: &PolityAction,
    year: f64,
    world: &mut World,
    history: &mut History,
    tick: u32,
) -> Result<(), String> {
    match action {
        PolityAction::State(spec) => found_state(world, history, tick, year, spec),
        PolityAction::LanguagePolicy { state, policy } => {
            language_policy(world, history, tick, year, state, policy)
        }
        PolityAction::Annexation { state, regions } => {
            annexation(world, history, tick, year, state, regions)
        }
        PolityAction::LinguaFranca {
            source,
            regions,
            spread,
            nativize,
        } => lingua_franca(
            world, history, tick, year, source, regions, spread, *nativize,
        ),
        PolityAction::Secession(spec) => {
            let ids = check_regions(world, &spec.regions)?;
            take(world, tick, &ids, None)?;
            history.record(
                "secession",
                tick,
                year,
                json!({"state": spec.id, "regions": sorted(&spec.regions)}),
            );
            found_state(world, history, tick, year, spec)
        }
        PolityAction::Collapse { state } => {
            let polity = polity_of(world, state)?;
            release(world, tick, &polity, &polity.regions)?;
            Edits::new(tick).remove_state(world, state)?;
            refresh(world, tick)?;
            history.record(
                "collapse",
                tick,
                year,
                json!({"state": state, "regions": sorted_names(world, &polity.regions)}),
            );
            Ok(())
        }
        PolityAction::BorderPolicy { state, border } => {
            let polity = polity_of(world, state)?;
            level_of(&world.params.border_levels, border, "propustnost hranice")?;
            Edits::new(tick).set_state(world, &polity.id, StateChange::Border(border.clone()))?;
            refresh(world, tick)?;
            history.record(
                "border_policy",
                tick,
                year,
                json!({"state": state, "border": border}),
            );
            Ok(())
        }
        PolityAction::Preserve {
            regions,
            language,
            preserved,
        } => preserve(
            world,
            history,
            tick,
            year,
            regions,
            language.as_deref(),
            *preserved,
        ),
        PolityAction::Identity { regions, identity } => {
            identity_event(world, history, tick, year, regions, identity)
        }
        PolityAction::Immigration {
            regions,
            immigration,
        } => immigration_event(world, history, tick, year, regions, *immigration),
        PolityAction::Revival {
            regions,
            language,
            strength,
        } => revival(
            world,
            history,
            tick,
            year,
            regions,
            language.as_deref(),
            strength,
        ),
        PolityAction::Standard { of, literacy } => {
            standard(world, history, tick, year, of, literacy)
        }
        PolityAction::Schools {
            of,
            coverage,
            printing,
            diglossic,
        } => schools(
            world, history, tick, year, of, coverage, *printing, *diglossic,
        ),
    }
}

// --- pomocné funkce -------------------------------------------------------------------

fn sorted(names: &[String]) -> Vec<String> {
    crate::events::sorted(names)
}

/// Jména území seřazená (pro záznam v historii).
fn sorted_names(world: &World, regions: &[TerritoryId]) -> Vec<String> {
    let mut names: Vec<String> = regions
        .iter()
        .map(|&r| world.registry.territories.name(r.0).to_owned())
        .collect();
    names.sort();
    names
}

fn level_of(table: &Table, name: &str, what: &str) -> Result<f64, String> {
    table
        .get(name)
        .copied()
        .ok_or_else(|| format!("Neznámá hodnota '{name}' ({what})."))
}

fn level2_of<'a>(table: &'a Table2, name: &str, what: &str) -> Result<&'a Table, String> {
    table
        .get(name)
        .ok_or_else(|| format!("Neznámá hodnota '{name}' ({what})."))
}

fn polity_of(world: &World, state: &str) -> Result<Polity, String> {
    world
        .society
        .states
        .get(state)
        .cloned()
        .ok_or_else(|| format!("Stát '{state}' neexistuje; nejdřív ho založ událostí State."))
}

/// Region (území úrovně `region`), ve kterém skupina žije.
pub fn region_of(world: &World, group: GroupId) -> Option<TerritoryId> {
    let mut territory = world.groups.territory[group.index()];
    while !territory.is_none() {
        let found = &world.territories[territory.index()];
        if found.level == TerritoryLevel::Region {
            return Some(territory);
        }
        territory = found.parent;
    }
    None
}

/// Čísla regionů podle jmen; chyba, když název není region.
pub fn check_regions(world: &World, regions: &[String]) -> Result<Vec<TerritoryId>, String> {
    regions
        .iter()
        .map(|name| {
            let id =
                territory_named(world, name).map_err(|_| format!("'{name}' není region světa."))?;
            if world.territories[id.index()].level == TerritoryLevel::Region {
                Ok(id)
            } else {
                Err(format!("'{name}' není region světa."))
            }
        })
        .collect()
}

/// Domácí mluvené skupiny regionů (bez psaných kódů a veřejné domény).
pub fn groups_in(world: &World, regions: &[TerritoryId]) -> Vec<GroupId> {
    world
        .group_ids()
        .into_iter()
        .filter(|&g| {
            !world.groups.written[g.index()]
                && world.groups.domain[g.index()] == Domain::Home
                && region_of(world, g).is_some_and(|r| regions.contains(&r))
        })
        .collect()
}

/// Mluvené skupiny regionů včetně veřejné domény (čtou a chodí do školy).
fn readers_in(world: &World, regions: &[TerritoryId]) -> Vec<GroupId> {
    world
        .group_ids()
        .into_iter()
        .filter(|&g| {
            !world.groups.written[g.index()]
                && region_of(world, g).is_some_and(|r| regions.contains(&r))
        })
        .collect()
}

/// Největší vesnice regionu (při shodě první podle jména); rodilé skupiny mají přednost.
pub fn seat_of(world: &World, region: TerritoryId) -> Result<GroupId, String> {
    let found = groups_in(world, &[region]);
    found
        .into_iter()
        .min_by(|&a, &b| {
            let key = |g: GroupId| {
                (
                    !world.groups.main_code(g).l1_source.is_none(),
                    std::cmp::Reverse(world.groups.population[g.index()]),
                )
            };
            key(a)
                .cmp(&key(b))
                .then(world.group_name(a).cmp(world.group_name(b)))
        })
        .ok_or_else(|| {
            format!(
                "Region '{}' nemá žádnou vesnici.",
                world.registry.territories.name(region.0)
            )
        })
}

/// Dosah centra do skupiny: terén regionu × pokles se vzdáleností.
pub fn reach(world: &World, group: GroupId, seat: GroupId, distance: bool) -> f64 {
    let terrain = region_of(world, group)
        .map(|r| world.territories[r.index()].terrain.as_str())
        .unwrap_or("plain");
    let access = world
        .params
        .terrain_access
        .get(terrain)
        .copied()
        .unwrap_or(1.0);
    if !distance {
        return access;
    }
    match (world.position_of(group), world.position_of(seat)) {
        (Some(a), Some(b)) => {
            access * (-((a.0 - b.0).hypot(a.1 - b.1)) / world.params.capital_reach).exp()
        }
        _ => access,
    }
}

fn language_name(world: &World, group: GroupId) -> String {
    world
        .registry
        .languages
        .name(world.groups.main_code(group).language.0)
        .to_owned()
}

/// Skupina zdroje: jméno skupiny, nebo region (jeho největší vesnice).
fn source_group(world: &World, source: &str) -> Result<GroupId, String> {
    if let Ok(group) = group_named(world, source) {
        return Ok(group);
    }
    let region = check_regions(world, &[source.to_owned()])?[0];
    seat_of(world, region)
}

/// Podíl `share` dospělých skupiny užívá kód `source` mimo domov; vrací veřejnou skupinu.
#[allow(clippy::too_many_arguments)]
fn public_bilingualism(
    world: &mut World,
    history: &mut History,
    tick: u32,
    year: f64,
    group: GroupId,
    source: GroupId,
    share: f64,
    pull: f64,
    link: f64,
    replace_pull: bool,
) -> Result<Option<GroupId>, String> {
    let edit = Edits::new(tick);
    let group_name = world.group_name(group).to_owned();
    let language = language_name(world, source);
    let public_name = format!("{group_name}>{language}");
    let existing = world
        .registry
        .groups
        .get(&public_name)
        .map(GroupId)
        .filter(|g| world.groups.contains(*g));
    let public = match existing {
        Some(public) => {
            if world.groups.domain[public.index()] != Domain::Public {
                return Ok(None);
            }
            let population = world.groups.population[public.index()]
                .max(py_round(share * f64::from(world.groups.population[group.index()])) as u32);
            edit.set_group(world, public, Field::Population(population))?;
            let current = world.groups.home_pull[public.index()];
            edit.set_group(
                world,
                public,
                Field::HomePull(if replace_pull {
                    pull
                } else {
                    current.max(pull)
                }),
            )?;
            let nativized_name = format!("{group_name}>{language}:home");
            if let Some(n) = world
                .registry
                .groups
                .get(&nativized_name)
                .map(GroupId)
                .filter(|g| world.groups.contains(*g))
            {
                if world.groups.home_pull[n.index()] > 0.0 {
                    let value = world.groups.home_pull[public.index()].max(1e-6);
                    edit.set_group(world, n, Field::HomePull(value))?;
                }
            }
            public
        }
        None => {
            if share * f64::from(world.groups.population[group.index()]) < 1.0 {
                return Ok(None);
            }
            let created = language_shift(
                world,
                history,
                tick,
                year,
                group,
                source,
                &ShiftOptions {
                    initial_share: share,
                    public: true,
                    ..ShiftOptions::default()
                },
            )?;
            edit.set_group(world, created, Field::HomePull(pull))?;
            // Úřední jazyk se mimo domov užívá i psaný: veřejná skupina čte normu zdroje.
            let standard = world.groups.standard[source.index()];
            if !standard.is_none() {
                edit.set_group(world, created, Field::Standard(standard))?;
                let literacy =
                    world.groups.literacy[group.index()].max(world.groups.literacy[source.index()]);
                edit.set_group(world, created, Field::Literacy(literacy))?;
            }
            created
        }
    };
    if link > 0.0 {
        let weaker = world
            .links
            .get(public, source)
            .is_none_or(|current| current.strength < link);
        if weaker {
            edit.connect(world, public, source, link, LinkKind::Weak)?;
        }
    }
    edit.set_prestige_mirror(world, public, source)?;
    let nativized_name = format!("{group_name}>{language}:home");
    if let Some(n) = world
        .registry
        .groups
        .get(&nativized_name)
        .map(GroupId)
        .filter(|g| world.groups.contains(*g))
    {
        edit.set_prestige_mirror(world, n, source)?;
    }
    Ok(Some(public))
}

/// Politika státu: veřejná dvojjazyčnost v regionech jiného jazyka; vrací dotčené skupiny.
fn apply_policy(
    world: &mut World,
    history: &mut History,
    tick: u32,
    year: f64,
    polity: &Polity,
) -> Result<Vec<GroupId>, String> {
    let params = world.params.clone();
    let table = level2_of(&params.policy_levels, &polity.policy, "jazyková politika")?;
    let (share, pull) = (table["share"], table["pull"]);
    let language = polity.language;
    let mut touched = Vec::new();
    for group in groups_in(world, &polity.regions) {
        if world.groups.main_code(group).language == language {
            continue;
        }
        let scale = reach(world, group, polity.seat, true);
        let created = public_bilingualism(
            world,
            history,
            tick,
            year,
            group,
            polity.seat,
            share * scale,
            pull * scale,
            params.capital_link_strength * scale,
            true,
        )?;
        if created.is_some() {
            touched.push(group);
        }
    }
    Ok(touched)
}

fn names_of(world: &World, groups: &[GroupId]) -> Vec<String> {
    groups
        .iter()
        .map(|&g| world.group_name(g).to_owned())
        .collect()
}

/// Centralizace: vesnice státu se spojí se sídlem; vrací počet nových vazeb.
fn centralize(
    world: &mut World,
    tick: u32,
    polity: &Polity,
    regions: &[TerritoryId],
) -> Result<usize, String> {
    let edit = Edits::new(tick);
    let params = world.params.clone();
    let strength = params.capital_link_strength
        * level_of(
            &params.centralization_levels,
            &polity.centralization,
            "úroveň centralizace",
        )?;
    let mut linked = 0;
    if strength <= 0.0 {
        return Ok(linked);
    }
    for group in groups_in(world, regions) {
        if region_of(world, group) == Some(polity.capital) {
            continue;
        }
        let value = strength * reach(world, group, polity.seat, true);
        let weaker = world
            .links
            .get(group, polity.seat)
            .is_none_or(|current| current.strength < value);
        if weaker {
            edit.connect(world, group, polity.seat, value, LinkKind::Weak)?;
            edit.set_state_link(world, &polity.id, group, Some(value))?;
            linked += 1;
        }
    }
    Ok(linked)
}

/// Stát opustí regiony: zmizí jeho vazby k sídlu a jeho politika tam.
fn release(
    world: &mut World,
    tick: u32,
    polity: &Polity,
    regions: &[TerritoryId],
) -> Result<(), String> {
    let edit = Edits::new(tick);
    let mut linked: Vec<GroupId> = polity.links.keys().copied().collect();
    linked.sort_by(|a, b| world.group_name(*a).cmp(world.group_name(*b)));
    for group in linked {
        if world.groups.contains(group)
            && region_of(world, group).is_some_and(|r| regions.contains(&r))
        {
            for (source, target) in [(group, polity.seat), (polity.seat, group)] {
                edit.drop_link(world, source, target)?;
                edit.set_border_factor(world, source, target, None)?;
            }
            edit.set_state_link(world, &polity.id, group, None)?;
        }
    }
    let mut mirrored: Vec<(GroupId, GroupId)> = world
        .society
        .prestige_mirror
        .iter()
        .map(|(&a, &b)| (a, b))
        .collect();
    mirrored.sort_by(|a, b| world.group_name(a.0).cmp(world.group_name(b.0)));
    for (group, model) in mirrored {
        if !world.groups.contains(group)
            || model != polity.seat
            || !region_of(world, group).is_some_and(|r| regions.contains(&r))
        {
            continue;
        }
        // Lidé jazyk umějí dál, ale stát už ho domů netlačí.
        if world.groups.domain[group.index()] == Domain::Public {
            edit.set_group(world, group, Field::HomePull(0.0))?;
        } else if world.groups.home_pull[group.index()] > 0.0 {
            edit.set_group(world, group, Field::HomePull(1e-6))?;
        }
    }
    Ok(())
}

// --- události -----------------------------------------------------------------------

/// Vznik státu z regionů s hlavním městem; vesnice dostanou prestiž, sítě a politiku.
fn found_state(
    world: &mut World,
    history: &mut History,
    tick: u32,
    year: f64,
    spec: &StateSpec,
) -> Result<(), String> {
    if world.society.states.contains_key(&spec.id) {
        return Err(format!("Stát '{}' už existuje.", spec.id));
    }
    let regions = check_regions(world, &spec.regions)?;
    let capital = territory_named(world, &spec.capital)?;
    if !regions.contains(&capital) {
        return Err(format!(
            "Hlavní město '{}' musí ležet ve státě '{}'.",
            spec.capital, spec.id
        ));
    }
    let mut owned: Vec<String> = Vec::new();
    for polity in world.society.states.values() {
        for r in &polity.regions {
            if regions.contains(r) {
                owned.push(world.registry.territories.name(r.0).to_owned());
            }
        }
    }
    if !owned.is_empty() {
        owned.sort();
        return Err(format!(
            "Regiony {owned:?} už patří jinému státu; použij Annexation nebo Secession."
        ));
    }
    let params = world.params.clone();
    level_of(
        &params.centralization_levels,
        &spec.centralization,
        "úroveň centralizace",
    )?;
    level2_of(&params.policy_levels, &spec.policy, "jazyková politika")?;
    level_of(&params.border_levels, &spec.border, "propustnost hranice")?;
    let seat = match &spec.language {
        None => seat_of(world, capital)?,
        Some(name) => {
            let number = world
                .registry
                .languages
                .get(name)
                .ok_or_else(|| format!("Neznámý úřední jazyk '{name}'."))?;
            groups_in(world, &[capital])
                .into_iter()
                .filter(|&g| world.groups.main_code(g).language.0 == number)
                .max_by(|&a, &b| {
                    world.groups.population[a.index()]
                        .cmp(&world.groups.population[b.index()])
                        .then(world.group_name(b).cmp(world.group_name(a)))
                })
                .ok_or_else(|| {
                    format!(
                        "V hlavním regionu '{}' nikdo nemluví úředním jazykem '{name}'.",
                        spec.capital
                    )
                })?
        }
    };
    let polity = Polity {
        id: spec.id.clone(),
        name: spec.name.clone(),
        regions: regions.clone(),
        capital,
        seat,
        language: world.groups.main_code(seat).language,
        centralization: spec.centralization.clone(),
        policy: spec.policy.clone(),
        border: spec.border.clone(),
        links: BTreeMap::new(),
    };
    Edits::new(tick).add_state(world, polity)?;
    refresh(world, tick)?;
    let polity = polity_of(world, &spec.id)?;
    let linked = centralize(world, tick, &polity, &polity.regions)?;
    let bilingual = apply_policy(world, history, tick, year, &polity)?;
    refresh(world, tick)?;
    history.record(
        "state",
        tick,
        year,
        json!({
            "state": spec.id, "name": spec.name, "regions": sorted(&spec.regions),
            "capital": spec.capital, "seat": world.group_name(seat),
            "language": world.registry.languages.name(polity.language.0),
            "centralization": spec.centralization, "policy": spec.policy, "border": spec.border,
            "linked": linked, "bilingual": names_of(world, &bilingual),
        }),
    );
    Ok(())
}

fn language_policy(
    world: &mut World,
    history: &mut History,
    tick: u32,
    year: f64,
    state: &str,
    policy: &str,
) -> Result<(), String> {
    polity_of(world, state)?;
    level2_of(&world.params.policy_levels, policy, "jazyková politika")?;
    Edits::new(tick).set_state(world, state, StateChange::Policy(policy.to_owned()))?;
    let polity = polity_of(world, state)?;
    let bilingual = apply_policy(world, history, tick, year, &polity)?;
    history.record(
        "language_policy",
        tick,
        year,
        json!({"state": state, "policy": policy, "bilingual": names_of(world, &bilingual)}),
    );
    Ok(())
}

fn annexation(
    world: &mut World,
    history: &mut History,
    tick: u32,
    year: f64,
    state: &str,
    regions: &[String],
) -> Result<(), String> {
    let polity = polity_of(world, state)?;
    let ids = check_regions(world, regions)?;
    let fallen = take(world, tick, &ids, Some(&polity.id))?;
    let added: Vec<TerritoryId> = ids
        .iter()
        .copied()
        .filter(|r| !polity.regions.contains(r))
        .collect();
    let mut all = polity.regions.clone();
    all.extend(&added);
    Edits::new(tick).set_state(world, &polity.id, StateChange::Regions(all))?;
    refresh(world, tick)?;
    let polity = polity_of(world, state)?;
    let linked = centralize(world, tick, &polity, &added)?;
    let bilingual = apply_policy(world, history, tick, year, &polity)?;
    refresh(world, tick)?;
    history.record(
        "annexation",
        tick,
        year,
        json!({
            "state": state, "regions": sorted_names(world, &added), "linked": linked,
            "bilingual": names_of(world, &bilingual), "fallen": fallen,
        }),
    );
    Ok(())
}

/// Regiony odejdou ze všech států kromě `keep`; vrací zaniklé státy.
fn take(
    world: &mut World,
    tick: u32,
    regions: &[TerritoryId],
    keep: Option<&str>,
) -> Result<Vec<String>, String> {
    let edit = Edits::new(tick);
    let mut fallen = Vec::new();
    let others: Vec<Polity> = world.society.states.values().cloned().collect();
    for other in others {
        if Some(other.id.as_str()) == keep {
            continue;
        }
        let leaving: Vec<TerritoryId> = other
            .regions
            .iter()
            .copied()
            .filter(|r| regions.contains(r))
            .collect();
        if leaving.is_empty() {
            continue;
        }
        if leaving.contains(&other.capital) {
            if keep.is_none() {
                return Err(format!(
                    "Hlavní město státu '{}' se nemůže odtrhnout; použij Collapse.",
                    other.id
                ));
            }
            release(world, tick, &other, &other.regions)?;
            edit.remove_state(world, &other.id)?;
            fallen.push(other.id.clone());
            continue;
        }
        release(world, tick, &other, &leaving)?;
        let remaining = other
            .regions
            .iter()
            .copied()
            .filter(|r| !regions.contains(r))
            .collect();
        edit.set_state(world, &other.id, StateChange::Regions(remaining))?;
    }
    Ok(fallen)
}

#[allow(clippy::too_many_arguments)]
fn lingua_franca(
    world: &mut World,
    history: &mut History,
    tick: u32,
    year: f64,
    source: &str,
    regions: &[String],
    spread: &str,
    nativize: bool,
) -> Result<(), String> {
    let ids = check_regions(world, regions)?;
    let params = world.params.clone();
    let share = level_of(&params.lingua_franca_levels, spread, "úroveň rozšíření")?;
    let source_id = source_group(world, source)?;
    let language = world.groups.main_code(source_id).language;
    let pull = if nativize {
        params.lingua_franca_pull
    } else {
        0.0
    };
    let mut bilingual = Vec::new();
    for group in groups_in(world, &ids) {
        if world.groups.main_code(group).language == language {
            continue;
        }
        let scale = reach(world, group, source_id, false);
        let created = public_bilingualism(
            world,
            history,
            tick,
            year,
            group,
            source_id,
            share * scale,
            pull * scale,
            params.lingua_franca_link * scale,
            false,
        )?;
        if created.is_some() {
            bilingual.push(group);
        }
    }
    history.record(
        "lingua_franca",
        tick,
        year,
        json!({
            "source": world.group_name(source_id),
            "language": world.registry.languages.name(language.0),
            "regions": sorted(regions), "spread": spread, "nativize": nativize,
            "bilingual": names_of(world, &bilingual),
        }),
    );
    Ok(())
}

fn preserve(
    world: &mut World,
    history: &mut History,
    tick: u32,
    year: f64,
    regions: &[String],
    language: Option<&str>,
    preserved: bool,
) -> Result<(), String> {
    let ids = check_regions(world, regions)?;
    let edit = Edits::new(tick);
    let mut groups = Vec::new();
    for &region in &ids {
        let wanted: LanguageId = match language {
            Some(name) => LanguageId(
                world
                    .registry
                    .languages
                    .get(name)
                    .ok_or_else(|| format!("Neznámý jazyk '{name}'."))?,
            ),
            None => world.groups.main_code(seat_of(world, region)?).language,
        };
        for group in groups_in(world, &[region]) {
            if world.groups.main_code(group).language == wanted {
                edit.set_group(world, group, Field::Preserved(preserved))?;
                groups.push(group);
            }
        }
    }
    history.record(
        "preserve",
        tick,
        year,
        json!({
            "regions": sorted(regions), "language": language, "preserved": preserved,
            "groups": names_of(world, &groups),
        }),
    );
    Ok(())
}

fn identity_event(
    world: &mut World,
    history: &mut History,
    tick: u32,
    year: f64,
    regions: &[String],
    identity: &str,
) -> Result<(), String> {
    let ids = check_regions(world, regions)?;
    let loyalty = level_of(&world.params.identity_loyalty, identity, "úroveň identity")?;
    let groups = groups_in(world, &ids);
    let edit = Edits::new(tick);
    for &group in &groups {
        let value = crate::scenarios::village_loyalty(world, loyalty, world.group_name(group));
        edit.set_group(world, group, Field::Loyalty(value))?;
    }
    history.record(
        "identity",
        tick,
        year,
        json!({
            "regions": sorted(regions), "identity": identity, "groups": names_of(world, &groups),
        }),
    );
    Ok(())
}

fn immigration_event(
    world: &mut World,
    history: &mut History,
    tick: u32,
    year: f64,
    regions: &[String],
    immigration: f64,
) -> Result<(), String> {
    let ids = check_regions(world, regions)?;
    if !(0.0..=1.0).contains(&immigration) {
        return Err(format!(
            "Podíl přistěhovalců musí být mezi 0 a 1, ne {immigration}."
        ));
    }
    let groups = groups_in(world, &ids);
    let edit = Edits::new(tick);
    for &group in &groups {
        edit.set_group(world, group, Field::Immigration(immigration))?;
    }
    history.record(
        "immigration",
        tick,
        year,
        json!({
            "regions": sorted(regions), "immigration": immigration, "groups": names_of(world, &groups),
        }),
    );
    Ok(())
}

fn community_of(world: &World, group: GroupId) -> GroupId {
    let c = world.groups.community[group.index()];
    if c.is_none() {
        group
    } else {
        c
    }
}

fn revival(
    world: &mut World,
    history: &mut History,
    tick: u32,
    year: f64,
    regions: &[String],
    language: Option<&str>,
    strength: &str,
) -> Result<(), String> {
    let ids = check_regions(world, regions)?;
    let params = world.params.clone();
    let table = level2_of(&params.revival_levels, strength, "síla obrození")?;
    let (pace, seed) = (table["pace"], table["seed"]);
    let edit = Edits::new(tick);
    let (mut speakers, mut revived) = (Vec::new(), Vec::new());
    for &region in &ids {
        let wanted = match language {
            Some(name) => LanguageId(
                world
                    .registry
                    .languages
                    .get(name)
                    .ok_or_else(|| format!("Neznámý jazyk '{name}'."))?,
            ),
            None => {
                let native = world.territories[region.index()].native_language;
                if native.is_none() {
                    return Err(format!(
                        "Region '{}' nezná svůj původní jazyk; zadej language.",
                        world.registry.territories.name(region.0)
                    ));
                }
                native
            }
        };
        let home = groups_in(world, &[region]);
        for &group in &home {
            if world.groups.main_code(group).language == wanted {
                let value = world.groups.revival[group.index()].max(pace);
                edit.set_group(world, group, Field::Revival(value))?;
                speakers.push(group);
            }
        }
        for &group in &home {
            let community = community_of(world, group);
            let speaks = world.groups.main_code(group).language == wanted
                || world.group_ids().into_iter().any(|other| {
                    community_of(world, other) == community
                        && world.groups.domain[other.index()] == Domain::Home
                        && world.groups.main_code(other).language == wanted
                });
            if speaks {
                continue;
            }
            if let Some(created) = revive(world, tick, group, wanted, region, pace, seed)? {
                revived.push(created);
            }
        }
    }
    refresh(world, tick)?;
    history.record(
        "revival_movement",
        tick,
        year,
        json!({
            "regions": sorted(regions), "language": language, "strength": strength,
            "speakers": names_of(world, &speakers), "revived": names_of(world, &revived),
        }),
    );
    Ok(())
}

/// Odkud se ztracený jazyk naučit: soused, který ho mluví, jinak jeho písmo.
fn donor(
    world: &World,
    group: GroupId,
    language: LanguageId,
    region: TerritoryId,
) -> Option<GroupId> {
    let mut links = neighbors(world, group);
    links.sort_by(|a, b| {
        b.1.strength
            .partial_cmp(&a.1.strength)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then(world.group_name(a.0).cmp(world.group_name(b.0)))
    });
    for (target, _) in links {
        let i = target.index();
        if !world.groups.written[i]
            && world.groups.domain[i] == Domain::Home
            && world.groups.main_code(target).language == language
        {
            return Some(target);
        }
    }
    let region_name = world.registry.territories.name(region.0);
    if let Some(&written) = world.society.standards.get(region_name) {
        if world.groups.contains(written) && world.groups.main_code(written).language == language {
            return Some(written);
        }
    }
    world.group_ids().into_iter().find(|&candidate| {
        world.groups.written[candidate.index()]
            && world.groups.main_code(candidate).language == language
    })
}

fn revive(
    world: &mut World,
    tick: u32,
    group: GroupId,
    language: LanguageId,
    region: TerritoryId,
    pace: f64,
    seed: f64,
) -> Result<Option<GroupId>, String> {
    let edit = Edits::new(tick);
    let Some(donor) = donor(world, group, language, region) else {
        return Ok(None);
    };
    let language_name = world.registry.languages.name(language.0).to_owned();
    let new_name = format!("{}>{language_name}:revived", world.group_name(group));
    if world
        .registry
        .groups
        .get(&new_name)
        .is_some_and(|g| world.groups.contains(GroupId(g)))
    {
        return Ok(None);
    }
    let community = community_of(world, group);
    edit.set_group(world, group, Field::Community(community))?;
    let written = if world.groups.written[donor.index()] {
        donor
    } else {
        world.groups.standard[donor.index()]
    };
    let g = group.index();
    let prestige = world
        .society
        .base_prestige
        .get(&group)
        .copied()
        .unwrap_or(world.groups.prestige[g]);
    let population = 1.max(py_round(f64::from(world.groups.population[g]) * seed)) as u32;
    let fields = [
        Field::GenerationYears(world.groups.generation_years[g]),
        Field::Prestige(prestige),
        Field::Openness(world.groups.openness[g]),
        Field::Community(community),
        Field::HomePull(pace),
        Field::Loyalty(world.groups.loyalty[g]),
        Field::Revival(pace),
        Field::Standard(written),
        Field::Literacy(world.groups.literacy[g].max(if written.is_none() { 0.0 } else { 0.5 })),
    ];
    let territory = world.groups.territory[g];
    let created = edit.add_group(
        world, &new_name, territory, population, donor, false, &fields,
    )?;
    edit.set_code(
        world,
        created,
        crate::edits::CodeChange::learned_from(group, 1.0),
    )?;
    edit.set_base_prestige(world, created, Some(world.groups.prestige[created.index()]))?;
    edit.connect(world, created, group, 0.8, LinkKind::Strong)?;
    for (target, link) in neighbors(world, group) {
        let neighbourhood = community_of(world, target);
        for other in world.group_ids() {
            let o = other.index();
            if other == created
                || world.groups.written[o]
                || world.groups.main_code(other).language != language
            {
                continue;
            }
            if other == target || community_of(world, other) == neighbourhood {
                edit.connect(world, created, other, link.strength, link.kind)?;
            }
        }
    }
    Ok(Some(created))
}

/// Hranice a prestiž ze stavu světa (po každé události státu).
///
/// Vazba mezi regiony různých států (nebo státu a regionu mimo státy) má sílu základ ×
/// propustnost méně propustné hranice; základ si vazba drží v `border_factors`, takže
/// připojení hranici zase zruší. Prestiž domácí skupiny je základ × `capital_prestige`
/// (hlavní město existujícího státu) × `standard_prestige` (čte normu svého jazyka);
/// skupiny v `prestige_mirror` přebírají prestiž své předlohy.
pub fn refresh(world: &mut World, tick: u32) -> Result<(), String> {
    let edit = Edits::new(tick);
    let params = world.params.clone();
    let owner: BTreeMap<TerritoryId, String> = world
        .society
        .states
        .values()
        .flat_map(|p| p.regions.iter().map(|&r| (r, p.id.clone())))
        .collect();
    let mut openness: BTreeMap<&str, f64> = BTreeMap::new();
    for polity in world.society.states.values() {
        openness.insert(
            &polity.id,
            level_of(&params.border_levels, &polity.border, "propustnost hranice")?,
        );
    }
    let regions: BTreeMap<GroupId, Option<TerritoryId>> = world
        .group_ids()
        .into_iter()
        .map(|g| (g, region_of(world, g)))
        .collect();
    let mut keys: Vec<(GroupId, GroupId)> = world.links.iter().map(|(k, _)| *k).collect();
    keys.sort_by(|a, b| {
        (world.group_name(a.0), world.group_name(a.1))
            .cmp(&(world.group_name(b.0), world.group_name(b.1)))
    });
    let mut changes: Vec<(GroupId, GroupId, f64, f64, LinkKind)> = Vec::new();
    for &(first, second) in &keys {
        if world.groups.written[first.index()] || world.groups.written[second.index()] {
            continue;
        }
        let (here, there) = (regions[&first], regions[&second]);
        let mut factor = 1.0;
        if let (Some(h), Some(t)) = (here, there) {
            let (oh, ot) = (owner.get(&h), owner.get(&t));
            if oh != ot {
                let open = |o: Option<&String>| {
                    o.and_then(|id| openness.get(id.as_str()).copied())
                        .unwrap_or(1.0)
                };
                factor = open(oh).min(open(ot));
            }
        }
        let old = world
            .society
            .border_factors
            .get(&(first, second))
            .copied()
            .unwrap_or(1.0);
        if factor == old {
            continue;
        }
        let link = world
            .links
            .get(first, second)
            .copied()
            .ok_or("vazba zmizela")?;
        changes.push((first, second, old, factor, link.kind));
    }
    for (first, second, old, factor, kind) in changes {
        let strength = world.links.get(first, second).map_or(0.0, |l| l.strength);
        edit.set_link(
            world,
            first,
            second,
            (strength / old).min(1.0) * factor,
            kind,
        )?;
        edit.set_border_factor(world, first, second, (factor != 1.0).then_some(factor))?;
    }
    let stale: Vec<(GroupId, GroupId)> = world
        .society
        .border_factors
        .keys()
        .filter(|k| world.links.get(k.0, k.1).is_none())
        .copied()
        .collect();
    for (source, target) in stale {
        edit.set_border_factor(world, source, target, None)?;
    }

    let capitals: Vec<TerritoryId> = world.society.states.values().map(|p| p.capital).collect();
    for group in world.group_ids() {
        let g = group.index();
        if world.groups.written[g]
            || world.groups.domain[g] != Domain::Home
            || world.society.prestige_mirror.contains_key(&group)
        {
            continue;
        }
        if !world.society.base_prestige.contains_key(&group) {
            let value = world.groups.prestige[g];
            edit.set_base_prestige(world, group, Some(value))?;
        }
        let base = world.society.base_prestige[&group];
        let mut factor = if regions[&group].is_some_and(|r| capitals.contains(&r)) {
            params.capital_prestige
        } else {
            1.0
        };
        let standard = world.groups.standard[g];
        if !standard.is_none()
            && world.groups.contains(standard)
            && world.groups.main_code(standard).language == world.groups.main_code(group).language
        {
            factor *= params.standard_prestige;
        }
        edit.set_group(world, group, Field::Prestige(base * factor))?;
    }
    let mut mirrored: Vec<(GroupId, GroupId)> = world
        .society
        .prestige_mirror
        .iter()
        .map(|(&a, &b)| (a, b))
        .collect();
    mirrored.sort_by(|a, b| world.group_name(a.0).cmp(world.group_name(b.0)));
    for (group, model) in &mirrored {
        if world.groups.contains(*group) && world.groups.contains(*model) {
            let value = world.groups.prestige[model.index()];
            edit.set_group(world, *group, Field::Prestige(value))?;
        }
    }
    let stale: Vec<GroupId> = world
        .society
        .base_prestige
        .keys()
        .filter(|g| !world.groups.contains(**g))
        .copied()
        .collect();
    for group in stale {
        edit.set_base_prestige(world, group, None)?;
    }
    for (group, _) in mirrored {
        if !world.groups.contains(group) {
            edit.set_prestige_mirror(world, group, GroupId::NONE)?;
        }
    }
    Ok(())
}

// --- spisovný jazyk a školy ------------------------------------------------------------

/// Regiony, sídlo a zda jde o stát pro `of` (jméno státu, nebo regionu).
fn scope(world: &World, of: &str) -> Result<(Vec<TerritoryId>, GroupId, bool), String> {
    if let Some(polity) = world.society.states.get(of) {
        return Ok((polity.regions.clone(), polity.seat, true));
    }
    let region = check_regions(world, &[of.to_owned()])
        .map_err(|_| format!("'{of}' není stát ani region světa."))?[0];
    Ok((vec![region], seat_of(world, region)?, false))
}

fn standard(
    world: &mut World,
    history: &mut History,
    tick: u32,
    year: f64,
    of: &str,
    literacy: &str,
) -> Result<(), String> {
    let (regions, seat, is_state) = scope(world, of)?;
    let share = level_of(
        &world.params.literacy_levels,
        literacy,
        "úroveň gramotnosti",
    )?;
    let seat_name = world.group_name(seat).to_owned();
    let written_name = format!("written:{seat_name}");
    let exists = world
        .registry
        .groups
        .get(&written_name)
        .is_some_and(|g| world.groups.contains(GroupId(g)));
    if world.society.standards.contains_key(of) || exists {
        return Err(format!(
            "'{of}' už spisovný jazyk má; školu přidá událost Schools."
        ));
    }
    let written = codification(world, history, tick, year, &seat_name, &[], 0.0)?;
    let edit = Edits::new(tick);
    edit.set_standard(world, of, written)?;
    let language = world.groups.main_code(written).language;
    let mut readers = Vec::new();
    for group in readers_in(world, &regions) {
        let g = group.index();
        let own = world.groups.main_code(group).language == language;
        let current = world.groups.standard[g];
        let has_current = !current.is_none() && world.groups.contains(current);
        if has_current
            && (!own
                || world.groups.main_code(current).language
                    == world.groups.main_code(group).language)
        {
            continue;
        }
        edit.set_group(world, group, Field::Standard(written))?;
        let value = share * reach(world, group, seat, is_state);
        edit.set_group(
            world,
            group,
            Field::Literacy(world.groups.literacy[g].max(value)),
        )?;
        readers.push(group);
    }
    refresh(world, tick)?;
    history.record(
        "standard",
        tick,
        year,
        json!({
            "of": of, "written": written_name, "language": world.registry.languages.name(language.0),
            "literacy": literacy, "readers": names_of(world, &readers),
        }),
    );
    Ok(())
}

#[allow(clippy::too_many_arguments)]
fn schools(
    world: &mut World,
    history: &mut History,
    tick: u32,
    year: f64,
    of: &str,
    coverage: &str,
    use_printing: bool,
    diglossic: bool,
) -> Result<(), String> {
    let (regions, state_seat, is_state) = scope(world, of)?;
    let written = world
        .society
        .standards
        .get(of)
        .copied()
        .ok_or_else(|| format!("'{of}' nemá spisovný jazyk; nejdřív událost Standard."))?;
    let written_name = world.group_name(written).to_owned();
    let source = written_name
        .strip_prefix("written:")
        .unwrap_or(&written_name);
    // Dosah se měří od sídla normy.
    let seat = group_named(world, source).unwrap_or(state_seat);
    let share = level_of(&world.params.schooling_levels, coverage, "úroveň školství")?;
    let language = world.groups.main_code(written).language;
    let edit = Edits::new(tick);
    let mut pupils = Vec::new();
    for group in readers_in(world, &regions) {
        let g = group.index();
        let standard = world.groups.standard[g];
        if standard != written && !standard.is_none() && world.groups.contains(standard) {
            continue; // chodí do školy vlastní normy
        }
        edit.set_group(world, group, Field::Standard(written))?;
        let value = share * reach(world, group, seat, is_state);
        edit.set_group(
            world,
            group,
            Field::Literacy(world.groups.literacy[g].max(value)),
        )?;
        if world.groups.main_code(group).language != language {
            continue;
        }
        if diglossic && world.groups.domain[g] == Domain::Home {
            let name = world.group_name(group).to_owned();
            schooling_event(world, history, tick, year, &[name], value, value, true)?;
        } else {
            edit.set_group(
                world,
                group,
                Field::Schooling(world.groups.schooling[g].max(value)),
            )?;
        }
        pupils.push(group);
    }
    if use_printing && !diglossic {
        printing(world, history, tick, year, &written_name, 0.3)?;
    }
    history.record(
        "schools",
        tick,
        year,
        json!({
            "of": of, "coverage": coverage, "printing": use_printing,
            "diglossic": diglossic, "pupils": names_of(world, &pupils),
        }),
    );
    Ok(())
}

// --- export ----------------------------------------------------------------------------

/// Hranice států pro mapu: dvojice sousedních regionů různých států.
pub fn borders(world: &World) -> Vec<Value> {
    let owner: BTreeMap<TerritoryId, &str> = world
        .society
        .states
        .values()
        .flat_map(|p| p.regions.iter().map(move |&r| (r, p.id.as_str())))
        .collect();
    let regions: BTreeMap<GroupId, Option<TerritoryId>> = world
        .group_ids()
        .into_iter()
        .map(|g| (g, region_of(world, g)))
        .collect();
    let region_name = |r: TerritoryId| world.registry.territories.name(r.0);
    let mut found: BTreeMap<(&str, &str), f64> = BTreeMap::new();
    for (&(first, second), _) in world.links.iter() {
        let (Some(Some(here)), Some(Some(there))) = (regions.get(&first), regions.get(&second))
        else {
            continue;
        };
        let (h, t) = (region_name(*here), region_name(*there));
        if h >= t || owner.get(here) == owner.get(there) {
            continue;
        }
        let factor = world
            .society
            .border_factors
            .get(&(first, second))
            .copied()
            .unwrap_or(1.0);
        let entry = found.entry((h, t)).or_insert(factor);
        *entry = entry.min(factor);
    }
    found
        .into_iter()
        .map(|((here, there), factor)| {
            let state = |name: &str| {
                world
                    .registry
                    .territories
                    .get(name)
                    .and_then(|n| owner.get(&TerritoryId(n)).copied())
            };
            json!({
                "regions": [here, there],
                "states": [state(here), state(there)],
                "factor": factor,
            })
        })
        .collect()
}

/// Státy pro export: území, sídlo, úřední jazyk, úrovně a spisovná norma.
pub fn states(world: &World) -> Vec<Value> {
    world
        .society
        .states
        .values()
        .map(|polity| {
            json!({
                "id": polity.id, "name": polity.name,
                "regions": polity.regions.iter().map(|r| world.registry.territories.name(r.0)).collect::<Vec<_>>(),
                "capital": world.registry.territories.name(polity.capital.0),
                "seat": world.group_name(polity.seat),
                "language": world.registry.languages.name(polity.language.0),
                "centralization": polity.centralization, "policy": polity.policy,
                "border": polity.border,
                "standard": world.society.standards.get(&polity.id).map(|&g| world.group_name(g)),
            })
        })
        .collect()
}

/// Jazyky regionů: podíl lidí podle jazyka doma a mimo domov.
pub fn language_census(world: &World) -> Value {
    let owner: BTreeMap<TerritoryId, &str> = world
        .society
        .states
        .values()
        .flat_map(|p| p.regions.iter().map(move |&r| (r, p.id.as_str())))
        .collect();
    #[derive(Default)]
    struct Entry {
        home: BTreeMap<String, f64>,
        public: BTreeMap<String, f64>,
        people: f64,
    }
    let mut census: BTreeMap<&str, (Entry, Option<&str>)> = BTreeMap::new();
    for group in world.group_ids() {
        let g = group.index();
        let Some(region) = region_of(world, group) else {
            continue;
        };
        if world.groups.written[g] {
            continue;
        }
        let name = world.registry.territories.name(region.0);
        let (entry, _) = census
            .entry(name)
            .or_insert_with(|| (Entry::default(), owner.get(&region).copied()));
        let language = language_name(world, group);
        let people = f64::from(world.groups.population[g]);
        if world.groups.domain[g] == Domain::Home {
            *entry.home.entry(language).or_default() += people;
            entry.people += people;
        } else {
            *entry.public.entry(language).or_default() += people;
        }
    }
    let mut out = serde_json::Map::new();
    for (region, (entry, state)) in census {
        let people = if entry.people == 0.0 {
            1.0
        } else {
            entry.people
        };
        let share = |m: &BTreeMap<String, f64>| {
            Value::Object(
                m.iter()
                    .map(|(k, v)| (k.clone(), json!(v / people)))
                    .collect(),
            )
        };
        out.insert(
            region.to_owned(),
            json!({"home": share(&entry.home), "public": share(&entry.public), "state": state}),
        );
    }
    Value::Object(out)
}
