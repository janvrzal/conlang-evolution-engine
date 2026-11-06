//! Události světa (zrcadlo `events.py`; státy a politika jsou v [`crate::polity`],
//! pozadí dějin v [`crate::background`]).
//!
//! Událost zasahuje do světa v kroku, ve kterém její rok nastal (`phases::events`).
//! Mění **strukturu** světa (skupiny, vazby, populace, gramotnost), nikdy repertoár
//! přímo; na jazyk působí nepřímo přes přenos. Každá změna jde přes [`Edits`]
//! (deník změn světa).
//!
//! Událost je [`Scripted`]: rok, druh, původní popis (`describe`) a rozebraná akce
//! ([`Action`]). Autor i scénáře zadávají události jako [`PendingEvent`] (druh a JSON
//! parametry); [`from_pending`] je rozebere. Neplatný popis nevrací chybu při sestavení,
//! ale při provedení (běh skončí s chybou ve svém kroku, jako výjimka v Pythonu).
//!
//! Názvy parametrů přijímají i podoby scénářů (`first`/`second` místo `side_a`/`side_b`,
//! `elite`/`seat`/`regions` u dobytí, `groups` místo `readers` u kodifikace).

use serde_json::{json, Map, Value};

use crate::edits::{group_named, neighbors, py_round, territory_named, CodeChange, Edits, Field};
use crate::history::History;
use crate::ids::{GroupId, TerritoryId};
use crate::model::group::Domain;
use crate::model::links::LinkKind;
use crate::model::territory::TerritoryLevel;
use crate::polity::PolityAction;
use crate::world::World;

/// Sídlo zjemnění: jméno, podíl a poloha.
pub type Settlement = (String, f64, Option<(f64, f64)>);

/// Jak často se psaná norma reviduje, když sleduje řeč (let).
pub const WRITTEN_GENERATION: f64 = 100.0;

/// Událost v dějinách světa.
pub trait WorldEvent: Send + Sync + std::fmt::Debug {
    /// Rok, od kterého událost působí.
    fn year(&self) -> f64;
    /// Druh události (`state`, `conquest`, …) – klíč záznamu v historii.
    fn kind(&self) -> &str;
    /// Provede událost: změní svět a zapíše záznamy do historie.
    fn apply(&self, world: &mut World, history: &mut History, tick: u32) -> Result<(), String>;
    /// Popis (druh a parametry) pro uložení a porovnání událostí.
    fn describe(&self) -> Value;
}

/// Událost, kterou ještě nikdo nerozebral: druh a parametry.
#[derive(Clone, Debug)]
pub struct PendingEvent {
    pub year: f64,
    pub kind: String,
    pub params: Value,
}

impl PendingEvent {
    pub fn new(year: f64, kind: &str, params: Value) -> PendingEvent {
        PendingEvent {
            year,
            kind: kind.to_owned(),
            params,
        }
    }
}

impl WorldEvent for PendingEvent {
    fn year(&self) -> f64 {
        self.year
    }

    fn kind(&self) -> &str {
        &self.kind
    }

    fn apply(&self, world: &mut World, history: &mut History, tick: u32) -> Result<(), String> {
        let action = parse_action(&self.kind, &self.params)?;
        apply_action(&action, self.year, world, history, tick)
    }

    fn describe(&self) -> Value {
        json!({"year": self.year, "kind": self.kind, "params": self.params})
    }
}

/// Rozebraná akce události.
#[derive(Clone, Debug)]
pub enum Action {
    Border {
        side_a: Vec<String>,
        side_b: Vec<String>,
        factor: f64,
    },
    Contact {
        pairs: Vec<(String, String)>,
        strength: f64,
        kind: LinkKind,
        trade: bool,
    },
    LanguageShift {
        group: String,
        target: String,
        options: ShiftOptions,
    },
    Codification {
        source: String,
        readers: Vec<String>,
        literacy: f64,
    },
    Printing {
        written: String,
        update: f64,
    },
    Schooling {
        groups: Vec<String>,
        schooling: f64,
        literacy: f64,
        diglossic: bool,
    },
    ReligiousChange {
        liturgy: String,
        groups: Vec<String>,
        devotion: f64,
        network: f64,
    },
    RefineTerritory {
        territory: String,
        settlements: Vec<Settlement>,
        internal_strength: f64,
        child_level: TerritoryLevel,
    },
    Migration {
        sources: Vec<(String, f64)>,
        target: String,
        position: Option<(f64, f64)>,
        reach: f64,
        prestige: Option<f64>,
        region: Option<String>,
    },
    Conquest {
        conqueror: String,
        territory: String,
        subjects: Vec<String>,
        population: u32,
        prestige: f64,
        strength: f64,
    },
    War {
        side_a: Vec<String>,
        side_b: Vec<String>,
        factor: f64,
        losses: f64,
    },
    Epidemic {
        groups: Vec<String>,
        mortality: f64,
    },
    StateCollapse {
        groups: Vec<String>,
        reach: f64,
        literacy: f64,
    },
    Polity(PolityAction),
    Background(crate::background::BackgroundAction),
    /// Popis, který se nedal rozebrat; provedení vrátí chybu.
    Invalid(String),
}

/// Rozebraná událost.
#[derive(Clone, Debug)]
pub struct Scripted {
    pub year: f64,
    pub kind: String,
    pub params: Value,
    pub action: Action,
}

impl WorldEvent for Scripted {
    fn year(&self) -> f64 {
        self.year
    }

    fn kind(&self) -> &str {
        &self.kind
    }

    fn apply(&self, world: &mut World, history: &mut History, tick: u32) -> Result<(), String> {
        apply_action(&self.action, self.year, world, history, tick)
    }

    fn describe(&self) -> Value {
        json!({"year": self.year, "kind": self.kind, "params": self.params})
    }
}

/// Provede akci (i z jiných událostí, např. `War` volá `Border`).
pub fn apply_action(
    action: &Action,
    year: f64,
    world: &mut World,
    history: &mut History,
    tick: u32,
) -> Result<(), String> {
    match action {
        Action::Border {
            side_a,
            side_b,
            factor,
        } => border(world, history, tick, year, side_a, side_b, *factor),
        Action::Contact {
            pairs,
            strength,
            kind,
            trade,
        } => contact(world, history, tick, year, pairs, *strength, *kind, *trade),
        Action::LanguageShift {
            group,
            target,
            options,
        } => {
            let source = group_named(world, group)?;
            let target = group_named(world, target)?;
            language_shift(world, history, tick, year, source, target, options).map(|_| ())
        }
        Action::Codification {
            source,
            readers,
            literacy,
        } => codification(world, history, tick, year, source, readers, *literacy).map(|_| ()),
        Action::Printing { written, update } => {
            printing(world, history, tick, year, written, *update)
        }
        Action::Schooling {
            groups,
            schooling,
            literacy,
            diglossic,
        } => schooling_event(
            world, history, tick, year, groups, *schooling, *literacy, *diglossic,
        ),
        Action::ReligiousChange {
            liturgy,
            groups,
            devotion,
            network,
        } => religious_change(
            world, history, tick, year, liturgy, groups, *devotion, *network,
        ),
        Action::RefineTerritory {
            territory,
            settlements,
            internal_strength,
            child_level,
        } => refine_territory(
            world,
            history,
            tick,
            year,
            territory,
            settlements,
            *internal_strength,
            *child_level,
        ),
        Action::Migration {
            sources,
            target,
            position,
            reach,
            prestige,
            region,
        } => migration(
            world,
            history,
            tick,
            year,
            sources,
            target,
            *position,
            *reach,
            *prestige,
            region.as_deref(),
        ),
        Action::Conquest {
            conqueror,
            territory,
            subjects,
            population,
            prestige,
            strength,
        } => conquest(
            world,
            history,
            tick,
            year,
            conqueror,
            territory,
            subjects,
            *population,
            *prestige,
            *strength,
        ),
        Action::War {
            side_a,
            side_b,
            factor,
            losses,
        } => war(world, history, tick, year, side_a, side_b, *factor, *losses),
        Action::Epidemic { groups, mortality } => {
            epidemic(world, history, tick, year, groups, *mortality)
        }
        Action::StateCollapse {
            groups,
            reach,
            literacy,
        } => state_collapse(world, history, tick, year, groups, *reach, *literacy),
        Action::Polity(action) => crate::polity::apply(action, year, world, history, tick),
        Action::Background(action) => crate::background::apply(action, year, world, history, tick),
        Action::Invalid(message) => Err(message.clone()),
    }
}

pub(crate) fn sorted(names: &[String]) -> Vec<String> {
    let mut found = names.to_vec();
    found.sort();
    found
}

// --- hranice, kontakt -------------------------------------------------------------

/// Hranice: vazby přes ni zeslábnou na `factor` původní síly.
fn border(
    world: &mut World,
    history: &mut History,
    tick: u32,
    year: f64,
    side_a: &[String],
    side_b: &[String],
    factor: f64,
) -> Result<(), String> {
    let weakened = weaken(world, tick, side_a, side_b, factor)?;
    history.record(
        "border",
        tick,
        year,
        json!({
            "side_a": sorted(side_a), "side_b": sorted(side_b),
            "factor": factor, "weakened_links": weakened,
        }),
    );
    Ok(())
}

fn weaken(
    world: &mut World,
    tick: u32,
    side_a: &[String],
    side_b: &[String],
    factor: f64,
) -> Result<usize, String> {
    let edit = Edits::new(tick);
    let mut weakened = 0;
    for first in side_a {
        for second in side_b {
            let (a, b) = (group_named(world, first)?, group_named(world, second)?);
            let Some(link) = world.links.get(a, b).copied() else {
                continue;
            };
            edit.connect(world, a, b, link.strength * factor, link.kind)?;
            weakened += 1;
        }
    }
    Ok(weakened)
}

/// Skupiny začnou spolu mluvit; s `trade` je vazba obchodní cesta.
#[allow(clippy::too_many_arguments)]
fn contact(
    world: &mut World,
    history: &mut History,
    tick: u32,
    year: f64,
    pairs: &[(String, String)],
    strength: f64,
    kind: LinkKind,
    trade: bool,
) -> Result<(), String> {
    let edit = Edits::new(tick);
    for (first, second) in pairs {
        let (a, b) = (group_named(world, first)?, group_named(world, second)?);
        edit.connect(world, a, b, strength, kind)?;
        let value = trade.then(|| world.links.get(a, b).map_or(0.0, |l| l.strength));
        edit.set_trade(world, a, b, value)?;
    }
    history.record(
        "contact",
        tick,
        year,
        json!({"pairs": pairs.iter().map(|(a, b)| [a, b]).collect::<Vec<_>>(), "strength": strength}),
    );
    Ok(())
}

// --- přechod jazyka --------------------------------------------------------------

/// Volby přechodu jazyka (`LanguageShift`).
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ShiftOptions {
    pub initial_share: f64,
    pub openness: f64,
    pub internal_strength: f64,
    /// `true` = kód se užívá jen mimo domov (stabilní dvojjazyčnost).
    pub public: bool,
}

impl Default for ShiftOptions {
    fn default() -> Self {
        ShiftOptions {
            initial_share: 0.1,
            openness: 0.2,
            internal_strength: 0.8,
            public: false,
        }
    }
}

/// Dospělí ze skupiny `source` se začnou učit kód skupiny `target`; vrací novou skupinu.
///
/// Nová skupina téže komunity mluví kódem cílového jazyka jako druhým jazykem
/// (`l2_share` = 1). Další průběh řídí `phases::communities`.
pub fn language_shift(
    world: &mut World,
    history: &mut History,
    tick: u32,
    year: f64,
    source: GroupId,
    target: GroupId,
    options: &ShiftOptions,
) -> Result<GroupId, String> {
    let edit = Edits::new(tick);
    let language = world.groups.main_code(target).language;
    let language_name = world.registry.languages.name(language.0).to_owned();
    let community = match world.groups.community[source.index()] {
        c if c.is_none() => source,
        c => c,
    };
    edit.set_group(world, source, Field::Community(community))?;
    let source_population = world.groups.population[source.index()];
    let population = 1.max(py_round(
        f64::from(source_population) * options.initial_share,
    )) as u32;
    if !options.public {
        edit.set_group(
            world,
            source,
            Field::Population(1.max(source_population.saturating_sub(population))),
        )?;
    }
    let source_name = world.group_name(source).to_owned();
    let group_name = format!("{source_name}>{language_name}");
    let fields = [
        Field::GenerationYears(world.groups.generation_years[source.index()]),
        Field::Prestige(world.groups.prestige[target.index()]),
        Field::Openness(options.openness),
        Field::Community(community),
        Field::Domain(if options.public {
            Domain::Public
        } else {
            Domain::Home
        }),
    ];
    let territory = world.groups.territory[source.index()];
    let group = edit.add_group(
        world,
        &group_name,
        territory,
        population,
        target,
        false,
        &fields,
    )?;
    edit.set_code(world, group, CodeChange::learned_from(source, 1.0))?;
    // Novým kódem mluví s těmi sousedy, kteří ho už umějí: s rodilými mluvčími
    // i se sousedními komunitami, které na něj přecházejí také.
    for (neighbor, link) in neighbors(world, source) {
        let neighbor_community = world.groups.community[neighbor.index()];
        for other in world.group_ids() {
            let peer_community = world.groups.community[other.index()];
            let same_community = other == neighbor
                || (!neighbor_community.is_none() && peer_community == neighbor_community);
            if same_community
                && other != group
                && world.groups.main_code(other).language == language
            {
                edit.connect(world, group, other, link.strength, link.kind)?;
            }
        }
    }
    edit.connect(
        world,
        group,
        source,
        options.internal_strength,
        LinkKind::Strong,
    )?;
    history.record(
        "bilingualism",
        tick,
        year,
        json!({
            "group": source_name, "learners": group_name, "language": language_name,
            "population": population, "domain": if options.public { "public" } else { "home" },
        }),
    );
    Ok(group)
}

// --- písmo, tisk, škola, náboženství -----------------------------------------------

/// Vznik písma: řeč skupiny `source` se zapíše a zmrazí; vrací psaný kód.
pub fn codification(
    world: &mut World,
    history: &mut History,
    tick: u32,
    year: f64,
    source: &str,
    readers: &[String],
    literacy: f64,
) -> Result<GroupId, String> {
    let edit = Edits::new(tick);
    let source_id = group_named(world, source)?;
    let written_name = format!("written:{source}");
    let fields = [
        Field::GenerationYears(WRITTEN_GENERATION),
        Field::Prestige(world.groups.prestige[source_id.index()]),
        Field::Openness(0.0),
        Field::Written(true),
    ];
    let territory = world.groups.territory[source_id.index()];
    let population = world.groups.population[source_id.index()];
    let written = edit.add_group(
        world,
        &written_name,
        territory,
        population,
        source_id,
        false,
        &fields,
    )?;
    edit.fix_code(world, written)?;
    edit.set_code(
        world,
        written,
        CodeChange {
            l1_source: Some(GroupId::NONE),
            l2_share: Some(0.0),
            ..CodeChange::default()
        },
    )?;
    // Jednosměrná vazba: psaný kód může sledovat řeč zdroje (viz tisk).
    edit.set_link(world, written, source_id, 1.0, LinkKind::Weak)?;
    for reader in readers {
        let id = group_named(world, reader)?;
        edit.set_group(world, id, Field::Standard(written))?;
        let current = world.groups.literacy[id.index()];
        edit.set_group(world, id, Field::Literacy(current.max(literacy)))?;
    }
    history.record(
        "codification",
        tick,
        year,
        json!({
            "source": source, "written": written_name,
            "readers": sorted(readers), "literacy": literacy,
        }),
    );
    Ok(written)
}

/// Tisk: psaná norma začne sledovat řeč zdroje (`update` = podíl při každé revizi).
pub fn printing(
    world: &mut World,
    history: &mut History,
    tick: u32,
    year: f64,
    written: &str,
    update: f64,
) -> Result<(), String> {
    let id = group_named(world, written)?;
    Edits::new(tick).set_group(world, id, Field::Openness(update))?;
    history.record(
        "printing",
        tick,
        year,
        json!({"written": written, "update": update}),
    );
    Ok(())
}

/// Školy: děti skupin se učí i z psaného kódu (s `diglossic` jako samostatná vysoká varieta).
#[allow(clippy::too_many_arguments)]
pub fn schooling_event(
    world: &mut World,
    history: &mut History,
    tick: u32,
    year: f64,
    groups: &[String],
    schooling: f64,
    literacy: f64,
    diglossic: bool,
) -> Result<(), String> {
    let edit = Edits::new(tick);
    let mut created: Vec<(GroupId, GroupId)> = Vec::new();
    for name in groups {
        let group = group_named(world, name)?;
        let current = world.groups.literacy[group.index()];
        edit.set_group(world, group, Field::Literacy(current.max(literacy)))?;
        if !diglossic {
            let current = world.groups.schooling[group.index()];
            edit.set_group(world, group, Field::Schooling(current.max(schooling)))?;
            continue;
        }
        let standard = world.groups.standard[group.index()];
        if standard.is_none() || !world.groups.contains(standard) {
            continue;
        }
        let community = match world.groups.community[group.index()] {
            c if c.is_none() => group,
            c => c,
        };
        edit.set_group(world, group, Field::Community(community))?;
        let high_name = format!("{name}>H");
        let population = 1.max(py_round(
            f64::from(world.groups.population[group.index()]) * schooling,
        )) as u32;
        let fields = [
            Field::GenerationYears(world.groups.generation_years[group.index()]),
            Field::Prestige(world.groups.prestige[standard.index()]),
            Field::Openness(world.groups.openness[group.index()]),
            Field::Schooling(1.0),
            Field::Literacy(1.0),
            Field::Standard(standard),
            Field::Community(community),
            Field::Domain(Domain::Public),
        ];
        let territory = world.groups.territory[group.index()];
        let high = edit.add_group(
            world, &high_name, territory, population, standard, false, &fields,
        )?;
        edit.set_code(world, high, CodeChange::learned_from(group, 1.0))?;
        created.push((group, high));
    }
    // Vysokou varietou spolu mluví vzdělaní lidé sousedních komunit.
    created.sort_by(|a, b| world.group_name(a.0).cmp(world.group_name(b.0)));
    for &(group, high) in &created.clone() {
        for (target, link) in neighbors(world, group) {
            if let Some(&(_, other_high)) = created.iter().find(|(g, _)| *g == target) {
                edit.connect(world, high, other_high, link.strength, link.kind)?;
            }
        }
    }
    history.record(
        "schooling",
        tick,
        year,
        json!({
            "groups": sorted(groups), "schooling": schooling,
            "literacy": literacy, "diglossic": diglossic,
        }),
    );
    Ok(())
}

/// Skupiny přijmou náboženství s liturgickým kódem (psaný kód).
#[allow(clippy::too_many_arguments)]
fn religious_change(
    world: &mut World,
    history: &mut History,
    tick: u32,
    year: f64,
    liturgy: &str,
    groups: &[String],
    devotion: f64,
    network: f64,
) -> Result<(), String> {
    let code = group_named(world, liturgy)?;
    if !world.groups.written[code.index()] {
        return Err(format!("Liturgický kód '{liturgy}' musí být psaný kód."));
    }
    let edit = Edits::new(tick);
    for name in groups {
        let group = group_named(world, name)?;
        edit.set_group(world, group, Field::Liturgy(code))?;
        edit.set_group(world, group, Field::Devotion(devotion))?;
    }
    if network > 0.0 {
        let members = sorted(groups);
        for (index, first) in members.iter().enumerate() {
            for second in &members[index + 1..] {
                let (a, b) = (group_named(world, first)?, group_named(world, second)?);
                if world.links.get(a, b).is_none() {
                    edit.connect(world, a, b, network, LinkKind::Weak)?;
                }
            }
        }
    }
    history.record(
        "religious_change",
        tick,
        year,
        json!({"liturgy": liturgy, "groups": sorted(groups), "devotion": devotion}),
    );
    Ok(())
}

// --- území a lidé -------------------------------------------------------------------

/// Zjemnění od roku X: souhrnnou skupinu nahradí skupiny jednotlivých sídel.
#[allow(clippy::too_many_arguments)]
fn refine_territory(
    world: &mut World,
    history: &mut History,
    tick: u32,
    year: f64,
    territory: &str,
    settlements: &[Settlement],
    internal_strength: f64,
    child_level: TerritoryLevel,
) -> Result<(), String> {
    let parent = territory_named(world, territory)?;
    let aggregates: Vec<GroupId> = world
        .group_ids()
        .into_iter()
        .filter(|g| {
            world.groups.territory[g.index()] == parent && world.groups.aggregate[g.index()]
        })
        .collect();
    if aggregates.len() != 1 {
        return Err(format!(
            "Území '{territory}' musí mít právě jednu souhrnnou skupinu, má {}.",
            aggregates.len()
        ));
    }
    if settlements.is_empty() {
        return Err("Zjemnění potřebuje alespoň jedno sídlo.".into());
    }
    let edit = Edits::new(tick);
    let aggregate = aggregates[0];
    let parent_position = world.territories[parent.index()].position;
    let external = neighbors(world, aggregate);
    let total_share: f64 = settlements.iter().map(|s| s.1).sum();
    let aggregate_population = f64::from(world.groups.population[aggregate.index()]);
    let mut created: Vec<GroupId> = Vec::new();
    // Sídla převezmou kódy souhrnné skupiny, ta zaniká až po nich.
    for (name, share, position) in settlements {
        let place = edit.add_territory(
            world,
            name,
            child_level,
            parent,
            position.or(parent_position),
            Some(year),
        )?;
        let population = 1.max(py_round(aggregate_population * share / total_share)) as u32;
        let a = aggregate.index();
        let fields = [
            Field::GenerationYears(world.groups.generation_years[a]),
            Field::Prestige(world.groups.prestige[a]),
            Field::Openness(world.groups.openness[a]),
            Field::Literacy(world.groups.literacy[a]),
            Field::Schooling(world.groups.schooling[a]),
        ];
        let group = edit.add_group(world, name, place, population, aggregate, true, &fields)?;
        for (target, link) in &external {
            edit.connect(world, group, *target, link.strength, link.kind)?;
        }
        created.push(group);
    }
    for (index, &first) in created.iter().enumerate() {
        for &second in &created[index + 1..] {
            edit.connect(world, first, second, internal_strength, LinkKind::Strong)?;
        }
    }
    let aggregate_name = world.group_name(aggregate).to_owned();
    edit.remove_group(world, aggregate)?;
    history.record(
        "refinement",
        tick,
        year,
        json!({
            "territory": territory, "aggregate": aggregate_name,
            "groups": created.iter().map(|&g| world.group_name(g)).collect::<Vec<_>>(),
        }),
    );
    Ok(())
}

/// Část skupin se přestěhuje do sídla `target`; když neexistuje, založí ho.
#[allow(clippy::too_many_arguments)]
pub(crate) fn migration(
    world: &mut World,
    history: &mut History,
    tick: u32,
    year: f64,
    sources: &[(String, f64)],
    target: &str,
    position: Option<(f64, f64)>,
    reach: f64,
    prestige: Option<f64>,
    region: Option<&str>,
) -> Result<(), String> {
    let edit = Edits::new(tick);
    let mut moving: Vec<(u32, GroupId)> = Vec::new();
    for (name, share) in sources {
        let group = group_named(world, name)?;
        let population = world.groups.population[group.index()];
        let people = 1.max(py_round(f64::from(population) * share)) as u32;
        edit.set_group(
            world,
            group,
            Field::Population(1.max(population.saturating_sub(people))),
        )?;
        moving.push((people, group));
    }
    let arriving: u32 = moving.iter().map(|m| m.0).sum();
    let existing = world
        .registry
        .groups
        .get(target)
        .map(GroupId)
        .filter(|g| world.groups.contains(*g));
    let founded = existing.is_none();
    match existing {
        None => {
            // Největší skupina přistěhovalců (při shodě větší jméno, jako `max` v Pythonu).
            let (_, largest) = *moving
                .iter()
                .max_by(|a, b| {
                    a.0.cmp(&b.0)
                        .then(world.group_name(a.1).cmp(world.group_name(b.1)))
                })
                .ok_or("Migrace nemá žádné zdroje.")?;
            let origin = largest.index();
            let origin_territory = world.groups.territory[origin];
            // Osada patří do cílového regionu (`region`), jinak do regionu odkud lidé přišli.
            let parent = match region {
                Some(name) => world
                    .registry
                    .territories
                    .get(name)
                    .map(TerritoryId)
                    .ok_or_else(|| format!("Neznámý cílový region '{name}'."))?,
                None => world.territories[origin_territory.index()].parent,
            };
            let place = edit.add_territory(
                world,
                target,
                TerritoryLevel::Settlement,
                parent,
                position,
                None,
            )?;
            let fields = [
                Field::GenerationYears(world.groups.generation_years[origin]),
                Field::Prestige(prestige.unwrap_or(world.groups.prestige[origin])),
                Field::Openness(world.groups.openness[origin]),
            ];
            let group = edit.add_group(world, target, place, arriving, largest, false, &fields)?;
            let mut all: Vec<GroupId> = vec![group];
            all.extend(
                world
                    .group_ids()
                    .into_iter()
                    .filter(|&o| o != group && !world.groups.written[o.index()]),
            );
            edit.connect_gravity(world, &all, Some(reach))?;
            let native = moving.iter().map(|m| m.0).max().unwrap_or(0);
            edit.set_code(
                world,
                group,
                CodeChange::l2_share(f64::from(arriving - native) / f64::from(arriving)),
            )?;
        }
        Some(group) => {
            let population = f64::from(world.groups.population[group.index()]);
            let share = world.groups.main_code(group).l2_share;
            let incoming = f64::from(arriving);
            edit.set_code(
                world,
                group,
                CodeChange::l2_share((share * population + incoming) / (population + incoming)),
            )?;
            edit.set_group(
                world,
                group,
                Field::Population(world.groups.population[group.index()] + arriving),
            )?;
        }
    }
    history.record(
        "migration",
        tick,
        year,
        json!({
            "target": target, "founded": founded,
            "sources": moving.iter().map(|&(p, g)| json!([world.group_name(g), p])).collect::<Vec<_>>(),
        }),
    );
    Ok(())
}

/// Mluvené skupiny regionu (vesnice, jejichž území má region za rodiče).
fn groups_of_region(world: &World, region: &str) -> Result<Vec<GroupId>, String> {
    if world.registry.territories.get(region).is_none() {
        return Err(format!("Neznámý region '{region}'."));
    }
    Ok(world
        .group_ids()
        .into_iter()
        .filter(|&g| {
            let territory = world.groups.territory[g.index()];
            let parent = world.territories[territory.index()].parent;
            !world.groups.written[g.index()]
                && !parent.is_none()
                && world.registry.territories.name(parent.0) == region
        })
        .collect())
}

/// Největší skupina regionu (vesnice regionu), jejíž hlavní kód je z linie `language`.
fn largest_speaking(world: &World, region: &str, language: &str) -> Result<GroupId, String> {
    let number = world
        .registry
        .languages
        .get(language)
        .ok_or_else(|| format!("Neznámý jazyk '{language}'."))?;
    world
        .group_ids()
        .into_iter()
        .filter(|&g| {
            let territory = world.groups.territory[g.index()];
            let parent = world.territories[territory.index()].parent;
            !parent.is_none()
                && world.registry.territories.name(parent.0) == region
                && world.groups.main_code(g).language.0 == number
        })
        .max_by(|&a, &b| {
            world.groups.population[a.index()]
                .cmp(&world.groups.population[b.index()])
                .then(world.group_name(b).cmp(world.group_name(a)))
        })
        .ok_or_else(|| format!("V regionu '{region}' nikdo nemluví jazykem '{language}'."))
}

/// Dobyvatelé usadí v území elitu s vysokou prestiží.
#[allow(clippy::too_many_arguments)]
pub(crate) fn conquest(
    world: &mut World,
    history: &mut History,
    tick: u32,
    year: f64,
    conqueror: &str,
    territory: &str,
    subjects: &[String],
    population: u32,
    prestige: f64,
    strength: f64,
) -> Result<(), String> {
    let edit = Edits::new(tick);
    let origin = match conqueror.split_once(':') {
        Some((region, language)) => largest_speaking(world, region, language)?,
        None => group_named(world, conqueror)?,
    };
    let elite_name = format!("{territory}+{}", conqueror.replace(':', "-"));
    // Území: ID území, nebo skupiny (její sídlo).
    let place = match world.registry.territories.get(territory) {
        Some(found) if (found as usize) < world.territories.len() => TerritoryId(found),
        _ => world.groups.territory[group_named(world, territory)?.index()],
    };
    let fields = [
        Field::GenerationYears(world.groups.generation_years[origin.index()]),
        Field::Prestige(prestige),
        Field::Openness(world.groups.openness[origin.index()]),
        Field::Elite(true),
    ];
    let elite = edit.add_group(
        world,
        &elite_name,
        place,
        population,
        origin,
        false,
        &fields,
    )?;
    // `@region` = všechny mluvené skupiny regionu v roce události (dok. 23).
    let mut targets: Vec<GroupId> = Vec::new();
    for subject in subjects {
        match subject.strip_prefix('@') {
            Some(region) => targets.extend(groups_of_region(world, region)?),
            None => targets.push(group_named(world, subject)?),
        }
    }
    for id in targets {
        if id != elite {
            edit.connect(world, elite, id, strength, LinkKind::Weak)?;
        }
    }
    edit.connect(world, elite, origin, strength / 2.0, LinkKind::Weak)?;
    history.record(
        "conquest",
        tick,
        year,
        json!({"elite": elite_name, "conqueror": conqueror, "subjects": sorted(subjects)}),
    );
    Ok(())
}

/// Válka oslabí vazby přes frontu a obě strany ztratí část lidí.
#[allow(clippy::too_many_arguments)]
fn war(
    world: &mut World,
    history: &mut History,
    tick: u32,
    year: f64,
    side_a: &[String],
    side_b: &[String],
    factor: f64,
    losses: f64,
) -> Result<(), String> {
    weaken(world, tick, side_a, side_b, factor)?;
    let edit = Edits::new(tick);
    for name in side_a.iter().chain(side_b) {
        let group = group_named(world, name)?;
        let people = f64::from(world.groups.population[group.index()]);
        edit.set_group(
            world,
            group,
            Field::Population(1.max(py_round(people * (1.0 - losses))) as u32),
        )?;
    }
    history.record(
        "war",
        tick,
        year,
        json!({
            "side_a": sorted(side_a), "side_b": sorted(side_b), "factor": factor, "losses": losses,
        }),
    );
    Ok(())
}

/// Epidemie: skupiny ztratí podíl `mortality` lidí.
fn epidemic(
    world: &mut World,
    history: &mut History,
    tick: u32,
    year: f64,
    groups: &[String],
    mortality: f64,
) -> Result<(), String> {
    let edit = Edits::new(tick);
    for name in groups {
        let group = group_named(world, name)?;
        let people = f64::from(world.groups.population[group.index()]);
        edit.set_group(
            world,
            group,
            Field::Population(1.max(py_round(people * (1.0 - mortality))) as u32),
        )?;
    }
    history.record(
        "epidemic",
        tick,
        year,
        json!({"groups": sorted(groups), "mortality": mortality}),
    );
    Ok(())
}

/// Kolaps státu: zaniknou dálkové vazby, školy a většina gramotnosti.
fn state_collapse(
    world: &mut World,
    history: &mut History,
    tick: u32,
    year: f64,
    groups: &[String],
    reach: f64,
    literacy: f64,
) -> Result<(), String> {
    let edit = Edits::new(tick);
    let members: Vec<GroupId> = groups
        .iter()
        .map(|g| group_named(world, g))
        .collect::<Result<_, _>>()?;
    let mut cut = 0;
    // Vazby podle jmen skupin (Python řadí podle ID).
    let mut keys: Vec<(GroupId, GroupId)> = world.links.iter().map(|(k, _)| *k).collect();
    keys.sort_by(|a, b| {
        (world.group_name(a.0), world.group_name(a.1))
            .cmp(&(world.group_name(b.0), world.group_name(b.1)))
    });
    for (first, second) in keys {
        if !members.contains(&first) && !members.contains(&second) {
            continue;
        }
        if let (Some(a), Some(b)) = (world.position_of(first), world.position_of(second)) {
            if (a.0 - b.0).hypot(a.1 - b.1) > reach {
                edit.drop_link(world, first, second)?;
                cut += 1;
            }
        }
    }
    for &group in &members {
        edit.set_group(world, group, Field::Schooling(0.0))?;
        let value = world.groups.literacy[group.index()] * literacy;
        edit.set_group(world, group, Field::Literacy(value))?;
    }
    history.record(
        "state_collapse",
        tick,
        year,
        json!({"groups": sorted(groups), "links_cut": cut}),
    );
    Ok(())
}

// --- rozbor popisu --------------------------------------------------------------------

/// Čtení parametrů události z JSON objektu s aliasy (sdílí ho politika a pozadí).
pub struct Params<'a> {
    pub map: &'a Map<String, Value>,
}

impl Params<'_> {
    pub fn any(&self, keys: &[&str]) -> Option<&Value> {
        keys.iter()
            .find_map(|k| self.map.get(*k))
            .filter(|v| !v.is_null())
    }

    pub fn string(&self, keys: &[&str]) -> Result<String, String> {
        self.opt_string(keys)?
            .ok_or_else(|| format!("chybí parametr '{}'", keys[0]))
    }

    pub fn opt_string(&self, keys: &[&str]) -> Result<Option<String>, String> {
        match self.any(keys) {
            None => Ok(None),
            Some(Value::String(s)) => Ok(Some(s.clone())),
            Some(_) => Err(format!("parametr '{}' musí být text", keys[0])),
        }
    }

    pub fn number(&self, keys: &[&str], default: f64) -> Result<f64, String> {
        Ok(self.opt_number(keys)?.unwrap_or(default))
    }

    pub fn opt_number(&self, keys: &[&str]) -> Result<Option<f64>, String> {
        match self.any(keys) {
            None => Ok(None),
            Some(v) => v
                .as_f64()
                .map(Some)
                .ok_or_else(|| format!("parametr '{}' musí být číslo", keys[0])),
        }
    }

    pub fn flag(&self, keys: &[&str], default: bool) -> Result<bool, String> {
        match self.any(keys) {
            None => Ok(default),
            Some(v) => v
                .as_bool()
                .ok_or_else(|| format!("parametr '{}' musí být true nebo false", keys[0])),
        }
    }

    pub fn strings(&self, keys: &[&str]) -> Result<Vec<String>, String> {
        match self.any(keys) {
            None => Ok(Vec::new()),
            Some(Value::Array(items)) => items
                .iter()
                .map(|v| {
                    v.as_str()
                        .map(str::to_owned)
                        .ok_or_else(|| format!("parametr '{}' musí být seznam textů", keys[0]))
                })
                .collect(),
            Some(_) => Err(format!("parametr '{}' musí být seznam textů", keys[0])),
        }
    }

    pub fn point(&self, keys: &[&str]) -> Result<Option<(f64, f64)>, String> {
        match self.any(keys) {
            None => Ok(None),
            Some(Value::Array(p)) if p.len() == 2 => match (p[0].as_f64(), p[1].as_f64()) {
                (Some(x), Some(y)) => Ok(Some((x, y))),
                _ => Err(format!("parametr '{}' musí být dvojice čísel", keys[0])),
            },
            Some(_) => Err(format!("parametr '{}' musí být dvojice čísel", keys[0])),
        }
    }
}

fn link_kind(text: Option<String>) -> Result<LinkKind, String> {
    match text.as_deref() {
        None | Some("weak") => Ok(LinkKind::Weak),
        Some("strong") => Ok(LinkKind::Strong),
        Some(other) => Err(format!("neznámý druh vazby '{other}'")),
    }
}

fn level_of(text: Option<String>) -> Result<TerritoryLevel, String> {
    match text.as_deref() {
        None | Some("settlement") => Ok(TerritoryLevel::Settlement),
        Some("area") => Ok(TerritoryLevel::Area),
        Some("region") => Ok(TerritoryLevel::Region),
        Some("continent") => Ok(TerritoryLevel::Continent),
        Some("world") => Ok(TerritoryLevel::World),
        Some(other) => Err(format!("neznámá úroveň území '{other}'")),
    }
}

fn pair_list(value: Option<&Value>, what: &str) -> Result<Vec<(String, Value)>, String> {
    match value {
        Some(Value::Array(items)) => items
            .iter()
            .map(|item| match item.as_array().map(Vec::as_slice) {
                Some([a, b]) => a
                    .as_str()
                    .map(|a| (a.to_owned(), b.clone()))
                    .ok_or_else(|| format!("{what} musí být dvojice")),
                _ => Err(format!("{what} musí být dvojice")),
            })
            .collect(),
        _ => Err(format!("chybí seznam dvojic ({what})")),
    }
}

pub fn parse_action(kind: &str, params: &Value) -> Result<Action, String> {
    let empty = Map::new();
    let map = match params {
        Value::Object(map) => map,
        Value::Null => &empty,
        _ => return Err("parametry události musí být objekt".into()),
    };
    let p = Params { map };
    Ok(match kind {
        "border" => Action::Border {
            side_a: p.strings(&["side_a", "first"])?,
            side_b: p.strings(&["side_b", "second"])?,
            factor: p.number(&["factor"], 0.1)?,
        },
        "war" => Action::War {
            side_a: p.strings(&["side_a", "first"])?,
            side_b: p.strings(&["side_b", "second"])?,
            factor: p.number(&["factor"], 0.2)?,
            losses: p.number(&["losses"], 0.2)?,
        },
        "contact" => Action::Contact {
            pairs: pair_list(p.any(&["pairs"]), "dvojice kontaktu")?
                .into_iter()
                .map(|(a, b)| {
                    b.as_str()
                        .map(|b| (a, b.to_owned()))
                        .ok_or_else(|| "dvojice kontaktu musí být dvojice textů".to_owned())
                })
                .collect::<Result<_, _>>()?,
            strength: p.number(&["strength"], 0.5)?,
            kind: link_kind(p.opt_string(&["kind"])?)?,
            trade: p.flag(&["trade"], false)?,
        },
        "language_shift" => {
            let defaults = ShiftOptions::default();
            Action::LanguageShift {
                group: p.string(&["group"])?,
                target: p.string(&["target"])?,
                options: ShiftOptions {
                    initial_share: p.number(&["initial_share"], defaults.initial_share)?,
                    openness: p.number(&["openness"], defaults.openness)?,
                    internal_strength: p
                        .number(&["internal_strength"], defaults.internal_strength)?,
                    public: p.opt_string(&["domain"])?.as_deref() == Some("public"),
                },
            }
        }
        "codification" => Action::Codification {
            source: p.string(&["source"])?,
            readers: p.strings(&["readers", "groups"])?,
            literacy: p.number(&["literacy"], 0.05)?,
        },
        "printing" => Action::Printing {
            written: p.string(&["written", "standard"])?,
            update: p.number(&["update"], 0.3)?,
        },
        "schooling" => Action::Schooling {
            groups: p.strings(&["groups"])?,
            schooling: p.number(&["schooling"], 0.8)?,
            literacy: p.number(&["literacy"], 0.8)?,
            diglossic: p.flag(&["diglossic"], false)?,
        },
        "religious_change" => Action::ReligiousChange {
            liturgy: p.string(&["liturgy"])?,
            groups: p.strings(&["groups"])?,
            devotion: p.number(&["devotion"], 0.3)?,
            network: p.number(&["network"], 0.0)?,
        },
        "refinement" | "refine_territory" => {
            let settlements = match p.any(&["settlements"]) {
                Some(Value::Array(items)) => items
                    .iter()
                    .map(|item| {
                        let inner = Params {
                            map: item.as_object().ok_or("sídlo musí být objekt")?,
                        };
                        Ok((
                            inner.string(&["id"])?,
                            inner.number(&["share"], 1.0)?,
                            inner.point(&["position"])?,
                        ))
                    })
                    .collect::<Result<Vec<_>, String>>()?,
                _ => Vec::new(),
            };
            Action::RefineTerritory {
                territory: p.string(&["territory"])?,
                settlements,
                internal_strength: p.number(&["internal_strength"], 0.8)?,
                child_level: level_of(p.opt_string(&["child_level"])?)?,
            }
        }
        "migration" => Action::Migration {
            sources: pair_list(p.any(&["sources"]), "zdroj migrace")?
                .into_iter()
                .map(|(a, b)| {
                    b.as_f64()
                        .map(|b| (a, b))
                        .ok_or_else(|| "podíl migrace musí být číslo".to_owned())
                })
                .collect::<Result<_, _>>()?,
            target: p.string(&["target"])?,
            position: p.point(&["position"])?,
            reach: p.number(&["reach"], 25.0)?,
            prestige: p.opt_number(&["prestige"])?,
            region: p.opt_string(&["region"])?,
        },
        "conquest" => Action::Conquest {
            // `conqueror` je jméno skupiny, nebo `region:jazyk` (největší skupina toho jazyka
            // v regionu v roce události; dok. 23).
            conqueror: p.string(&["conqueror", "elite"])?,
            territory: p.string(&["territory", "seat"])?,
            subjects: p.strings(&["subjects", "regions"])?,
            population: p.number(&["population"], 100.0)? as u32,
            prestige: p.number(&["prestige"], 2.0)?,
            strength: p.number(&["strength"], 0.5)?,
        },
        "epidemic" => Action::Epidemic {
            groups: p.strings(&["groups"])?,
            mortality: p.number(&["mortality"], 0.3)?,
        },
        "state_collapse" => Action::StateCollapse {
            groups: p.strings(&["groups"])?,
            reach: p.number(&["reach"], 30.0)?,
            literacy: p.number(&["literacy"], 0.2)?,
        },
        other => {
            if let Some(action) = crate::polity::parse(other, &p)? {
                Action::Polity(action)
            } else if let Some(action) = crate::background::parse(other, &p)? {
                Action::Background(action)
            } else {
                return Err(format!("Neznámý druh události '{other}'."));
            }
        }
    })
}

/// Rozebere popis události; neplatný popis se projeví chybou při provedení.
pub fn from_pending(pending: PendingEvent) -> Box<dyn WorldEvent> {
    let action = parse_action(&pending.kind, &pending.params).unwrap_or_else(|error| {
        Action::Invalid(format!(
            "Událost '{}' (rok {}): {error}",
            pending.kind, pending.year
        ))
    });
    Box::new(Scripted {
        year: pending.year,
        kind: pending.kind,
        params: pending.params,
        action,
    })
}
