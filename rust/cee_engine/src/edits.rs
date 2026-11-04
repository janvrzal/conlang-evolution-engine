//! API změn světa: jediná cesta, kterou události, státy, pozadí dějin a komunity mění
//! svět (zrcadlo `cee.v2.edits`).
//!
//! Operace je hodnota typu [`Op`] s čísly entit (`GroupId`, `TerritoryId`); žádné řetězce
//! kromě jmen nových entit (`AddGroup`, `AddTerritory`) a států. Stejná funkce [`apply`]
//! operaci provede při běhu i při přehrání deníku ([`Edits::replay`]), takže deník nemůže
//! popsat něco jiného, než co se stalo.
//!
//! | operace | účinek |
//! |---|---|
//! | `AddTerritory` | nové území (jméno, úroveň, rodič, poloha, rok zjemnění) |
//! | `AddGroup` | nová skupina s jedním kódem, nebo se všemi kódy skupiny `code_from` (větve `Code::branch`); živé proměnné dárce se nejdřív zapíšou do jeho repertoáru |
//! | `RemoveGroup` | skupina zmizí, s ní vazby a obchodní podíly |
//! | `SetGroup` | jedno skalární pole skupiny ([`Field`]) |
//! | `SetCode` | `acquisition`, `l1_source`, `l2_share` hlavního kódu |
//! | `FixCode` | hlavní kód má v každé proměnné jen dominantní variantu (zmrazení psaného kódu) |
//! | `Connect`, `SetLink`, `DropLink` | oboustranná vazba (s ořezem), jednosměrná vazba, zrušení |
//! | `SetTrade`, `SetBorderFactor` | obchodní podíl vazby, násobek oslabení hranicí |
//! | `SetBasePrestige`, `SetPrestigeMirror` | základní prestiž, převzetí prestiže jiné skupiny |
//! | `AddState`, `SetState`, `SetStateLink`, `RemoveState`, `SetStandard` | státy a spisovné jazyky |
//!
//! Operace, která nic nezměnila (zrušení neexistující vazby, nastavení stejné hodnoty), se
//! nezapíše. Pořadí operací je pořadí volání; `Edits` nic neřadí.
//!
//! **Deník.** Zapsaná operace je [`Edit`] (tik, fáze kroku, operace) v `SocietyState::edit_log`.
//! Co se zapisuje, určuje [`JournalMode`]; výchozí `Structure` vynechává každokrokové úpravy
//! komunit (populace, podíl L2, přistěhovalci), aby deník nerostl úměrně počtu skupin krát
//! počet kroků. `All` zapisuje jako Python. Deník na dynamiku nemá vliv.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

use crate::ids::{GroupId, Registry, TerritoryId};
use crate::model::code::{Acquisition, Code};
use crate::model::group::{Domain, GroupInit};
use crate::model::links::{Link, LinkKind};
use crate::model::repertoire::Distribution;
use crate::model::territory::{Territory, TerritoryLevel};
use crate::state::society::{JournalMode, Polity};
use crate::world::{gravity_pairs, World};

/// Python `round()`: zaokrouhlení poloviny k sudému.
pub fn py_round(value: f64) -> i64 {
    value.round_ties_even() as i64
}

/// Číslo existující skupiny podle jména.
pub fn group_named(world: &World, name: &str) -> Result<GroupId, String> {
    match world.registry.groups.get(name) {
        Some(found) if world.groups.contains(GroupId(found)) => Ok(GroupId(found)),
        _ => Err(format!("Skupina '{name}' neexistuje.")),
    }
}

/// Číslo existujícího území podle jména.
pub fn territory_named(world: &World, name: &str) -> Result<TerritoryId, String> {
    match world.registry.territories.get(name) {
        Some(found) if (found as usize) < world.territories.len() => Ok(TerritoryId(found)),
        _ => Err(format!("Území '{name}' neexistuje.")),
    }
}

/// Sousedé skupiny (vazby, které z ní vedou) seřazení podle jména cíle (`World.neighbors`).
pub fn neighbors(world: &World, group: GroupId) -> Vec<(GroupId, Link)> {
    let mut found: Vec<(GroupId, Link)> = world.links.from(group).map(|(t, l)| (t, *l)).collect();
    found.sort_by(|a, b| world.group_name(a.0).cmp(world.group_name(b.0)));
    found
}

/// Fáze kroku, ve které operace vznikla (kvůli přehrání na správném místě kroku).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum Phase {
    Event,
    Community,
}

impl Phase {
    pub fn name(self) -> &'static str {
        match self {
            Phase::Event => "event",
            Phase::Community => "community",
        }
    }
}

/// Skalární pole skupiny s novou hodnotou (`edits.GROUP_FIELDS`).
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub enum Field {
    Population(u32),
    GenerationYears(f64),
    Prestige(f64),
    Openness(f64),
    Literacy(f64),
    Schooling(f64),
    /// `GroupId::NONE` = skupina je komunitou sama.
    Community(GroupId),
    Immigration(f64),
    Written(bool),
    Standard(GroupId),
    Liturgy(GroupId),
    Devotion(f64),
    Loyalty(f64),
    Domain(Domain),
    HomePull(f64),
    Preserved(bool),
    Revival(f64),
    Elite(bool),
    Transmitted(bool),
}

impl Field {
    pub fn name(&self) -> &'static str {
        match self {
            Field::Population(_) => "population",
            Field::GenerationYears(_) => "generation_years",
            Field::Prestige(_) => "prestige",
            Field::Openness(_) => "openness",
            Field::Literacy(_) => "literacy",
            Field::Schooling(_) => "schooling",
            Field::Community(_) => "community",
            Field::Immigration(_) => "immigration",
            Field::Written(_) => "written",
            Field::Standard(_) => "standard",
            Field::Liturgy(_) => "liturgy",
            Field::Devotion(_) => "devotion",
            Field::Loyalty(_) => "loyalty",
            Field::Domain(_) => "domain",
            Field::HomePull(_) => "home_pull",
            Field::Preserved(_) => "preserved",
            Field::Revival(_) => "revival",
            Field::Elite(_) => "elite",
            Field::Transmitted(_) => "transmitted",
        }
    }

    fn value(&self, registry: &Registry) -> Value {
        let group = |id: &GroupId| -> Value {
            if id.is_none() {
                Value::Null
            } else {
                registry.groups.name(id.0).into()
            }
        };
        match self {
            Field::Population(v) => json!(v),
            Field::GenerationYears(v)
            | Field::Prestige(v)
            | Field::Openness(v)
            | Field::Literacy(v)
            | Field::Schooling(v)
            | Field::Immigration(v)
            | Field::Devotion(v)
            | Field::Loyalty(v)
            | Field::HomePull(v)
            | Field::Revival(v) => json!(v),
            Field::Community(id) | Field::Standard(id) | Field::Liturgy(id) => group(id),
            Field::Written(v) | Field::Preserved(v) | Field::Elite(v) | Field::Transmitted(v) => {
                json!(v)
            }
            Field::Domain(d) => json!(d.name()),
        }
    }

    /// Nastaví pole nové skupiny (`GroupInit`).
    fn init(&self, init: &mut GroupInit) {
        match *self {
            Field::Population(v) => init.population = v,
            Field::GenerationYears(v) => init.generation_years = v,
            Field::Prestige(v) => init.prestige = v,
            Field::Openness(v) => init.openness = v,
            Field::Literacy(v) => init.literacy = v,
            Field::Schooling(v) => init.schooling = v,
            Field::Community(v) => init.community = v,
            Field::Immigration(v) => init.immigration = v,
            Field::Written(v) => init.written = v,
            Field::Standard(v) => init.standard = v,
            Field::Liturgy(v) => init.liturgy = v,
            Field::Devotion(v) => init.devotion = v,
            Field::Loyalty(v) => init.loyalty = v,
            Field::Domain(v) => init.domain = v,
            Field::HomePull(v) => init.home_pull = v,
            Field::Preserved(v) => init.preserved = v,
            Field::Revival(v) => init.revival = v,
            Field::Elite(v) => init.elite = v,
            Field::Transmitted(v) => init.transmitted = v,
        }
    }

    /// Zapíše hodnotu do sloupce; vrací, zda se změnila.
    fn set(&self, groups: &mut crate::model::group::Groups, at: usize) -> bool {
        fn put<T: PartialEq + Copy>(slot: &mut T, value: T) -> bool {
            if *slot == value {
                false
            } else {
                *slot = value;
                true
            }
        }
        match *self {
            Field::Population(v) => put(&mut groups.population[at], v),
            Field::GenerationYears(v) => put(&mut groups.generation_years[at], v),
            Field::Prestige(v) => put(&mut groups.prestige[at], v),
            Field::Openness(v) => put(&mut groups.openness[at], v),
            Field::Literacy(v) => put(&mut groups.literacy[at], v),
            Field::Schooling(v) => put(&mut groups.schooling[at], v),
            Field::Community(v) => put(&mut groups.community[at], v),
            Field::Immigration(v) => put(&mut groups.immigration[at], v),
            Field::Written(v) => put(&mut groups.written[at], v),
            Field::Standard(v) => put(&mut groups.standard[at], v),
            Field::Liturgy(v) => put(&mut groups.liturgy[at], v),
            Field::Devotion(v) => put(&mut groups.devotion[at], v),
            Field::Loyalty(v) => put(&mut groups.loyalty[at], v),
            Field::Domain(v) => put(&mut groups.domain[at], v),
            Field::HomePull(v) => put(&mut groups.home_pull[at], v),
            Field::Preserved(v) => put(&mut groups.preserved[at], v),
            Field::Revival(v) => put(&mut groups.revival[at], v),
            Field::Elite(v) => put(&mut groups.elite[at], v),
            Field::Transmitted(v) => put(&mut groups.transmitted[at], v),
        }
    }
}

/// Změna polí hlavního kódu (`set_code`); `None` = pole se nemění.
#[derive(Clone, Copy, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct CodeChange {
    pub acquisition: Option<Acquisition>,
    /// `Some(GroupId::NONE)` zruší zdroj prvního jazyka.
    pub l1_source: Option<GroupId>,
    pub l2_share: Option<f64>,
}

impl CodeChange {
    pub fn l2_share(value: f64) -> CodeChange {
        CodeChange {
            l2_share: Some(value),
            ..CodeChange::default()
        }
    }

    /// Druhý jazyk naučený od `l1_source` s podílem `l2_share` (nové skupiny přechodu).
    pub fn learned_from(l1_source: GroupId, l2_share: f64) -> CodeChange {
        CodeChange {
            acquisition: Some(Acquisition::L2),
            l1_source: Some(l1_source),
            l2_share: Some(l2_share),
        }
    }

    fn only_l2_share(&self) -> bool {
        self.acquisition.is_none() && self.l1_source.is_none()
    }
}

/// Pole státu, která smí `SetState` změnit.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub enum StateChange {
    Regions(Vec<TerritoryId>),
    Policy(String),
    Border(String),
}

/// Jedna operace nad světem.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub enum Op {
    AddTerritory {
        name: String,
        level: TerritoryLevel,
        parent: TerritoryId,
        position: Option<(f64, f64)>,
        refined_from_year: Option<f64>,
    },
    AddGroup {
        name: String,
        territory: TerritoryId,
        population: u32,
        code_from: GroupId,
        /// `false` = jen hlavní kód dárce, `true` = všechny kódy.
        all_codes: bool,
        fields: Vec<Field>,
    },
    RemoveGroup {
        group: GroupId,
    },
    SetGroup {
        group: GroupId,
        field: Field,
    },
    SetCode {
        group: GroupId,
        change: CodeChange,
    },
    FixCode {
        group: GroupId,
    },
    Connect {
        first: GroupId,
        second: GroupId,
        strength: f64,
        kind: LinkKind,
    },
    SetLink {
        source: GroupId,
        target: GroupId,
        strength: f64,
        kind: LinkKind,
    },
    DropLink {
        source: GroupId,
        target: GroupId,
    },
    SetTrade {
        first: GroupId,
        second: GroupId,
        value: Option<f64>,
    },
    SetBorderFactor {
        source: GroupId,
        target: GroupId,
        factor: Option<f64>,
    },
    SetBasePrestige {
        group: GroupId,
        value: Option<f64>,
    },
    SetPrestigeMirror {
        group: GroupId,
        /// `GroupId::NONE` = zrušit.
        model: GroupId,
    },
    AddState {
        polity: Polity,
    },
    SetState {
        state: String,
        change: StateChange,
    },
    SetStateLink {
        state: String,
        group: GroupId,
        strength: Option<f64>,
    },
    RemoveState {
        state: String,
    },
    SetStandard {
        of: String,
        /// `GroupId::NONE` = smazat.
        written: GroupId,
    },
}

/// Zapsaná operace: tik, fáze kroku a operace.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Edit {
    pub tick: u32,
    pub phase: Phase,
    pub op: Op,
}

impl Edit {
    /// Řádek deníku jako JSON s názvy entit (jako `Edit.line` v Pythonu): `tick`, `op`, `args`
    /// a `phase` (jen u fáze komunit).
    pub fn describe(&self, registry: &Registry) -> Value {
        let (op, args) = self.op.describe(registry);
        let mut found = json!({"tick": self.tick, "op": op, "args": args});
        if self.phase != Phase::Event {
            found["phase"] = self.phase.name().into();
        }
        found
    }
}

impl Op {
    /// Jméno operace a její argumenty s názvy entit.
    pub fn describe(&self, registry: &Registry) -> (&'static str, Value) {
        let group = |id: &GroupId| -> Value {
            if id.is_none() {
                Value::Null
            } else {
                registry.groups.name(id.0).into()
            }
        };
        let territory = |id: &TerritoryId| -> Value {
            if id.is_none() {
                Value::Null
            } else {
                registry.territories.name(id.0).into()
            }
        };
        match self {
            Op::AddTerritory {
                name,
                level,
                parent,
                position,
                refined_from_year,
            } => (
                "add_territory",
                json!({"territory": name, "level": level.name(), "parent": territory(parent),
                       "position": position, "refined_from_year": refined_from_year}),
            ),
            Op::AddGroup {
                name,
                territory: place,
                population,
                code_from,
                all_codes,
                fields,
            } => {
                let mut args = json!({"group": name, "territory": territory(place),
                    "population": population, "code_from": group(code_from),
                    "codes": if *all_codes { "all" } else { "main" }});
                for field in fields {
                    args[field.name()] = field.value(registry);
                }
                ("add_group", args)
            }
            Op::RemoveGroup { group: id } => ("remove_group", json!({"group": group(id)})),
            Op::SetGroup { group: id, field } => (
                "set_group",
                json!({"group": group(id), "field": field.name(), "value": field.value(registry)}),
            ),
            Op::SetCode { group: id, change } => {
                let mut args = json!({"group": group(id)});
                if let Some(acquisition) = change.acquisition {
                    args["acquisition"] = match acquisition {
                        Acquisition::L1 => "L1",
                        Acquisition::L2 => "L2",
                    }
                    .into();
                }
                if let Some(source) = change.l1_source {
                    args["l1_source"] = group(&source);
                }
                if let Some(share) = change.l2_share {
                    args["l2_share"] = json!(share);
                }
                ("set_code", args)
            }
            Op::FixCode { group: id } => ("fix_code", json!({"group": group(id)})),
            Op::Connect {
                first,
                second,
                strength,
                kind,
            } => (
                "connect",
                json!({"first": group(first), "second": group(second), "strength": strength,
                       "kind": kind.name()}),
            ),
            Op::SetLink {
                source,
                target,
                strength,
                kind,
            } => (
                "set_link",
                json!({"source": group(source), "target": group(target), "strength": strength,
                       "kind": kind.name()}),
            ),
            Op::DropLink { source, target } => (
                "drop_link",
                json!({"source": group(source), "target": group(target)}),
            ),
            Op::SetTrade {
                first,
                second,
                value,
            } => (
                "set_trade",
                json!({"first": group(first), "second": group(second), "value": value}),
            ),
            Op::SetBorderFactor {
                source,
                target,
                factor,
            } => (
                "set_border_factor",
                json!({"source": group(source), "target": group(target), "factor": factor}),
            ),
            Op::SetBasePrestige { group: id, value } => (
                "set_base_prestige",
                json!({"group": group(id), "value": value}),
            ),
            Op::SetPrestigeMirror { group: id, model } => (
                "set_prestige_mirror",
                json!({"group": group(id), "model": group(model)}),
            ),
            Op::AddState { polity } => (
                "add_state",
                json!({"state": polity.id,
                       "regions": polity.regions.iter().map(territory).collect::<Vec<_>>(),
                       "capital": territory(&polity.capital), "seat": group(&polity.seat),
                       "language": registry.languages.name(polity.language.0),
                       "centralization": polity.centralization, "policy": polity.policy,
                       "border": polity.border, "name": polity.name}),
            ),
            Op::SetState { state, change } => {
                let (field, value) = match change {
                    StateChange::Regions(regions) => (
                        "regions",
                        json!(regions.iter().map(territory).collect::<Vec<_>>()),
                    ),
                    StateChange::Policy(value) => ("policy", json!(value)),
                    StateChange::Border(value) => ("border", json!(value)),
                };
                (
                    "set_state",
                    json!({"state": state, "field": field, "value": value}),
                )
            }
            Op::SetStateLink {
                state,
                group: id,
                strength,
            } => (
                "set_state_link",
                json!({"state": state, "group": group(id), "strength": strength}),
            ),
            Op::RemoveState { state } => ("remove_state", json!({"state": state})),
            Op::SetStandard { of, written } => {
                ("set_standard", json!({"of": of, "written": group(written)}))
            }
        }
    }

    /// Je to běžná každokroková úprava komunit, kterou režim `Structure` nezapisuje?
    fn routine(&self) -> bool {
        match self {
            Op::SetGroup { field, .. } => {
                matches!(field, Field::Population(_) | Field::Immigration(_))
            }
            Op::SetCode { change, .. } => change.only_l2_share(),
            _ => false,
        }
    }
}

fn alive(world: &World, group: GroupId) -> Result<(), String> {
    if world.groups.contains(group) {
        Ok(())
    } else {
        Err(format!(
            "Skupina '{}' neexistuje.",
            if group.is_none() {
                "(žádná)"
            } else {
                world.registry.groups.name(group.0)
            }
        ))
    }
}

fn polity_mut<'a>(world: &'a mut World, state: &str) -> Result<&'a mut Polity, String> {
    world
        .society
        .states
        .get_mut(state)
        .ok_or_else(|| format!("Stát '{state}' neexistuje."))
}

fn trade_key(first: GroupId, second: GroupId) -> (GroupId, GroupId) {
    if first < second {
        (first, second)
    } else {
        (second, first)
    }
}

/// Provede jednu operaci; vrací, zda něco změnila.
pub fn apply(world: &mut World, op: &Op) -> Result<bool, String> {
    match op {
        Op::AddTerritory {
            name,
            level,
            parent,
            position,
            refined_from_year,
        } => {
            let mut territory = Territory::new(*level);
            territory.position = *position;
            territory.refined_from_year = *refined_from_year;
            let parent_name =
                (!parent.is_none()).then(|| world.registry.territories.name(parent.0).to_owned());
            world.add_territory(name, parent_name.as_deref(), territory)?;
            Ok(true)
        }
        Op::AddGroup {
            name,
            territory,
            population,
            code_from,
            all_codes,
            fields,
        } => {
            alive(world, *code_from)?;
            if territory.is_none() || territory.index() >= world.territories.len() {
                return Err(format!("Území skupiny '{name}' neexistuje."));
            }
            if let Some(found) = world.registry.groups.get(name) {
                if world.groups.contains(GroupId(found)) {
                    return Err(format!("Skupina '{name}' už existuje."));
                }
            }
            // Živé proměnné dárce se zapíšou do jeho repertoáru a kód se větví.
            world.materialize(*code_from);
            let donor = &mut world.groups.codes[code_from.index()];
            let codes: Vec<Code> = if *all_codes {
                donor.iter_mut().map(Code::branch).collect()
            } else {
                vec![donor[0].branch()]
            };
            let mut init = GroupInit::new(name, *territory, *population, codes);
            for field in fields {
                field.init(&mut init);
            }
            init.validate()?;
            // Zaniklá skupina téhož jména dostane znovu své číslo (čísla se nepřečíslovávají).
            let id = world.registry.group(name);
            world.groups.store(id, init)?;
            Ok(true)
        }
        Op::RemoveGroup { group } => {
            alive(world, *group)?;
            world.remove_group(*group);
            Ok(true)
        }
        Op::SetGroup { group, field } => {
            alive(world, *group)?;
            Ok(field.set(&mut world.groups, group.index()))
        }
        Op::SetCode { group, change } => {
            alive(world, *group)?;
            let code = world.groups.main_code_mut(*group);
            let mut changed = false;
            if let Some(acquisition) = change.acquisition {
                if code.acquisition != acquisition {
                    code.acquisition = acquisition;
                    changed = true;
                }
            }
            if let Some(source) = change.l1_source {
                if code.l1_source != source {
                    code.l1_source = source;
                    changed = true;
                }
            }
            if let Some(share) = change.l2_share {
                if code.l2_share != share {
                    code.l2_share = share;
                    changed = true;
                }
            }
            Ok(changed)
        }
        Op::FixCode { group } => {
            alive(world, *group)?;
            let code = world.groups.main_code_mut(*group);
            for variable in code.repertoire.variable_ids() {
                let fixed = match code.repertoire.get(variable) {
                    Some(found) if !found.is_fixed() => found.dominant().0,
                    _ => continue,
                };
                code.repertoire.set(variable, Distribution::fixed(fixed));
            }
            Ok(true)
        }
        Op::Connect {
            first,
            second,
            strength,
            kind,
        } => {
            world.connect(*first, *second, *strength, *kind)?;
            Ok(true)
        }
        Op::SetLink {
            source,
            target,
            strength,
            kind,
        } => {
            alive(world, *source)?;
            alive(world, *target)?;
            world.links.set(
                *source,
                *target,
                Link {
                    strength: *strength,
                    kind: *kind,
                },
            );
            Ok(true)
        }
        Op::DropLink { source, target } => Ok(world.links.remove(*source, *target)),
        Op::SetTrade {
            first,
            second,
            value,
        } => {
            let key = trade_key(*first, *second);
            match value {
                None => Ok(world.society.trade.remove(&key).is_some()),
                Some(v) => {
                    world.society.trade.insert(key, *v);
                    Ok(true)
                }
            }
        }
        Op::SetBorderFactor {
            source,
            target,
            factor,
        } => match factor {
            None => Ok(world
                .society
                .border_factors
                .remove(&(*source, *target))
                .is_some()),
            Some(v) => {
                world.society.border_factors.insert((*source, *target), *v);
                Ok(true)
            }
        },
        Op::SetBasePrestige { group, value } => match value {
            None => Ok(world.society.base_prestige.remove(group).is_some()),
            Some(v) => {
                world.society.base_prestige.insert(*group, *v);
                Ok(true)
            }
        },
        Op::SetPrestigeMirror { group, model } => {
            if model.is_none() {
                Ok(world.society.prestige_mirror.remove(group).is_some())
            } else {
                world.society.prestige_mirror.insert(*group, *model);
                Ok(true)
            }
        }
        Op::AddState { polity } => {
            if world.society.states.contains_key(&polity.id) {
                return Err(format!("Stát '{}' už existuje.", polity.id));
            }
            world
                .society
                .states
                .insert(polity.id.clone(), polity.clone());
            Ok(true)
        }
        Op::SetState { state, change } => {
            let found = polity_mut(world, state)?;
            Ok(match change {
                StateChange::Regions(regions) => {
                    if found.regions == *regions {
                        false
                    } else {
                        found.regions = regions.clone();
                        true
                    }
                }
                StateChange::Policy(value) => {
                    if found.policy == *value {
                        false
                    } else {
                        found.policy = value.clone();
                        true
                    }
                }
                StateChange::Border(value) => {
                    if found.border == *value {
                        false
                    } else {
                        found.border = value.clone();
                        true
                    }
                }
            })
        }
        Op::SetStateLink {
            state,
            group,
            strength,
        } => {
            let links = &mut polity_mut(world, state)?.links;
            match strength {
                None => Ok(links.remove(group).is_some()),
                Some(v) => {
                    links.insert(*group, *v);
                    Ok(true)
                }
            }
        }
        Op::RemoveState { state } => {
            polity_mut(world, state)?;
            world.society.states.remove(state);
            Ok(true)
        }
        Op::SetStandard { of, written } => {
            if written.is_none() {
                Ok(world.society.standards.remove(of).is_some())
            } else {
                world.society.standards.insert(of.clone(), *written);
                Ok(true)
            }
        }
    }
}

/// Změny světa v jednom ticku a fázi kroku: provede operaci a zapíše ji do deníku světa.
#[derive(Clone, Copy, Debug)]
pub struct Edits {
    pub tick: u32,
    pub phase: Phase,
}

impl Edits {
    /// Změny událostí, států a pozadí dějin na začátku ticku.
    pub fn new(tick: u32) -> Edits {
        Edits {
            tick,
            phase: Phase::Event,
        }
    }

    /// Změny demografie kódů na konci ticku (`contact.community_step`).
    pub fn community(tick: u32) -> Edits {
        Edits {
            tick,
            phase: Phase::Community,
        }
    }

    fn records(&self, mode: JournalMode, op: &Op) -> bool {
        match mode {
            JournalMode::Off => false,
            JournalMode::All => true,
            JournalMode::Structure => self.phase == Phase::Event || !op.routine(),
        }
    }

    /// Provede operaci a zapíše ji, když něco změnila; vrací, zda změnila.
    pub fn run(&self, world: &mut World, op: Op) -> Result<bool, String> {
        let changed = apply(world, &op)?;
        // `Connect`, `AddGroup` a další vždy „změní“; stejné hodnoty nezapisuje jen `apply`.
        if changed && self.records(world.society.journal, &op) {
            world.society.edit_log.push(Edit {
                tick: self.tick,
                phase: self.phase,
                op,
            });
        }
        Ok(changed)
    }

    /// Přehraje zapsanou operaci; musí patřit do tohoto ticku a fáze.
    pub fn replay(&self, world: &mut World, edit: &Edit) -> Result<bool, String> {
        if edit.tick != self.tick {
            return Err(format!(
                "Změna z ticku {} se nedá přehrát v ticku {}.",
                edit.tick, self.tick
            ));
        }
        if edit.phase != self.phase {
            return Err(format!(
                "Změna fáze '{}' se nedá přehrát ve fázi '{}'.",
                edit.phase.name(),
                self.phase.name()
            ));
        }
        self.run(world, edit.op.clone())
    }

    // --- území a skupiny ---

    pub fn add_territory(
        &self,
        world: &mut World,
        name: &str,
        level: TerritoryLevel,
        parent: TerritoryId,
        position: Option<(f64, f64)>,
        refined_from_year: Option<f64>,
    ) -> Result<TerritoryId, String> {
        self.run(
            world,
            Op::AddTerritory {
                name: name.to_owned(),
                level,
                parent,
                position,
                refined_from_year,
            },
        )?;
        territory_named(world, name)
    }

    /// Nová skupina s kódem (kódy) odvozeným z `code_from`; `fields` jsou pole skupiny.
    #[allow(clippy::too_many_arguments)]
    pub fn add_group(
        &self,
        world: &mut World,
        name: &str,
        territory: TerritoryId,
        population: u32,
        code_from: GroupId,
        all_codes: bool,
        fields: &[Field],
    ) -> Result<GroupId, String> {
        self.run(
            world,
            Op::AddGroup {
                name: name.to_owned(),
                territory,
                population,
                code_from,
                all_codes,
                fields: fields.to_vec(),
            },
        )?;
        group_named(world, name)
    }

    pub fn remove_group(&self, world: &mut World, group: GroupId) -> Result<(), String> {
        self.run(world, Op::RemoveGroup { group }).map(|_| ())
    }

    pub fn set_group(
        &self,
        world: &mut World,
        group: GroupId,
        field: Field,
    ) -> Result<bool, String> {
        self.run(world, Op::SetGroup { group, field })
    }

    pub fn set_code(
        &self,
        world: &mut World,
        group: GroupId,
        change: CodeChange,
    ) -> Result<bool, String> {
        self.run(world, Op::SetCode { group, change })
    }

    pub fn fix_code(&self, world: &mut World, group: GroupId) -> Result<(), String> {
        self.run(world, Op::FixCode { group }).map(|_| ())
    }

    // --- vazby a obchod ---

    pub fn connect(
        &self,
        world: &mut World,
        first: GroupId,
        second: GroupId,
        strength: f64,
        kind: LinkKind,
    ) -> Result<(), String> {
        self.run(
            world,
            Op::Connect {
                first,
                second,
                strength,
                kind,
            },
        )
        .map(|_| ())
    }

    /// Gravitační vazby mezi skupinami (Trudgill); zapíše se každá vazba s vypočtenou silou.
    pub fn connect_gravity(
        &self,
        world: &mut World,
        groups: &[GroupId],
        max_distance: Option<f64>,
    ) -> Result<usize, String> {
        let pairs = gravity_pairs(world, 1.0, 1_000.0, 10.0, max_distance, Some(groups));
        for &(first, second, strength) in &pairs {
            self.connect(world, first, second, strength, LinkKind::Weak)?;
        }
        Ok(pairs.len())
    }

    pub fn set_link(
        &self,
        world: &mut World,
        source: GroupId,
        target: GroupId,
        strength: f64,
        kind: LinkKind,
    ) -> Result<(), String> {
        self.run(
            world,
            Op::SetLink {
                source,
                target,
                strength,
                kind,
            },
        )
        .map(|_| ())
    }

    pub fn drop_link(
        &self,
        world: &mut World,
        source: GroupId,
        target: GroupId,
    ) -> Result<bool, String> {
        self.run(world, Op::DropLink { source, target })
    }

    pub fn set_trade(
        &self,
        world: &mut World,
        first: GroupId,
        second: GroupId,
        value: Option<f64>,
    ) -> Result<bool, String> {
        let (first, second) = trade_key(first, second);
        self.run(
            world,
            Op::SetTrade {
                first,
                second,
                value,
            },
        )
    }

    pub fn set_border_factor(
        &self,
        world: &mut World,
        source: GroupId,
        target: GroupId,
        factor: Option<f64>,
    ) -> Result<bool, String> {
        self.run(
            world,
            Op::SetBorderFactor {
                source,
                target,
                factor,
            },
        )
    }

    // --- prestiž ---

    pub fn set_base_prestige(
        &self,
        world: &mut World,
        group: GroupId,
        value: Option<f64>,
    ) -> Result<bool, String> {
        self.run(world, Op::SetBasePrestige { group, value })
    }

    pub fn set_prestige_mirror(
        &self,
        world: &mut World,
        group: GroupId,
        model: GroupId,
    ) -> Result<bool, String> {
        self.run(world, Op::SetPrestigeMirror { group, model })
    }

    // --- státy a spisovné jazyky ---

    pub fn add_state(&self, world: &mut World, polity: Polity) -> Result<(), String> {
        self.run(world, Op::AddState { polity }).map(|_| ())
    }

    pub fn set_state(
        &self,
        world: &mut World,
        state: &str,
        change: StateChange,
    ) -> Result<bool, String> {
        self.run(
            world,
            Op::SetState {
                state: state.to_owned(),
                change,
            },
        )
    }

    pub fn set_state_link(
        &self,
        world: &mut World,
        state: &str,
        group: GroupId,
        strength: Option<f64>,
    ) -> Result<bool, String> {
        self.run(
            world,
            Op::SetStateLink {
                state: state.to_owned(),
                group,
                strength,
            },
        )
    }

    pub fn remove_state(&self, world: &mut World, state: &str) -> Result<(), String> {
        self.run(
            world,
            Op::RemoveState {
                state: state.to_owned(),
            },
        )
        .map(|_| ())
    }

    pub fn set_standard(
        &self,
        world: &mut World,
        of: &str,
        written: GroupId,
    ) -> Result<bool, String> {
        self.run(
            world,
            Op::SetStandard {
                of: of.to_owned(),
                written,
            },
        )
    }
}

/// Deník změn světa jako řádky JSON (jedna operace na řádek).
pub fn journal_lines(world: &World) -> Vec<String> {
    world
        .society
        .edit_log
        .iter()
        .map(|edit| edit.describe(&world.registry).to_string())
        .collect()
}

/// Deník rozdělený po tících v pořadí zápisu (tik se v deníku nevrací zpět).
pub fn by_tick(journal: &[Edit]) -> BTreeMap<u32, Vec<Edit>> {
    let mut found: BTreeMap<u32, Vec<Edit>> = BTreeMap::new();
    for edit in journal {
        found.entry(edit.tick).or_default().push(edit.clone());
    }
    found
}
