//! Příprava kroku přenosu: míšení z vazeb, komponenty sítě, kanály vazeb mezi jazyky,
//! kanály mimo síť (interference, čtení, škola, liturgie), kohorty a klíče driftu
//! (zrcadlo `transmission.prepare` a `phases_transmission.py`).
//!
//! Matice míšení je řídká po řádcích: řádek učící se skupiny drží jen nenulové zdroje
//! seřazené podle sloupce osy. Hustá matice skupiny × skupiny se nestaví nikdy.

use cee_core::transmission::{Component, Links};

use crate::contact::{self, BorrowTable};
use crate::ids::GroupId;
use crate::rng::{stable_int, Part};
use crate::world::World;

/// Konstanty přenosu z konfigurace běhu (`TransmissionParams`).
#[derive(Clone, Copy, Debug)]
pub struct TransmissionParams {
    pub dt: f64,
    pub alpha: f64,
    pub selection: f64,
    pub kappa: f64,
    pub sigma: f64,
    pub adult_rate: f64,
    pub loss_threshold: f64,
    pub establish_threshold: f64,
}

/// Kanál vazeb mezi jazyky (filtr přenositelnosti se liší podle domén pojmů).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FlowChannel {
    Neighbor,
    Elite,
    Trade,
}

impl FlowChannel {
    /// Jméno kanálu v `Parameters::channel_domains`.
    pub fn name(self) -> &'static str {
        match self {
            FlowChannel::Neighbor => "neighbor",
            FlowChannel::Elite => "elite",
            FlowChannel::Trade => "trade",
        }
    }
}

/// Kanál mimo vazby sítě v pořadí, v jakém se uplatňují.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SideKind {
    Interference,
    Reading,
    School,
    Liturgy,
}

/// Vazby mezi jazyky jednoho kanálu po komponentách sítě.
pub struct CrossFlow {
    pub channel: FlowChannel,
    pub components: Vec<Component>,
}

/// Vstup mimo vazby sítě: učící se skupina přebírá podíl `váha × faktor` od zdroje.
pub struct Side {
    pub kind: SideKind,
    pub learners: Vec<usize>,
    pub sources: Vec<usize>,
    pub weights: Vec<f64>,
}

/// Vstupy kroku sdílené všemi bloky živých proměnných.
pub struct StepInputs {
    /// Osa skupin (sloupec → skupina), kanonické pořadí podle jmen.
    pub axis: Vec<GroupId>,
    pub components: Vec<Component>,
    pub alone: Vec<usize>,
    pub alone_weight: Vec<f64>,
    pub cross: Vec<CrossFlow>,
    pub sides: Vec<Side>,
    pub renewal: Vec<f64>,
    pub drift_scale: Vec<f64>,
    pub loss_floor: Vec<f64>,
    pub row_keys: Vec<u64>,
    pub tick: u32,
    /// Filtry výpůjček a domén kanálů (rozhraní kontaktu R1d), spočtené jednou za krok.
    pub borrow: BorrowTable,
}

/// Řídké míšení: pro každého učícího se (řádek) nenulové zdroje vzestupně podle sloupce.
pub type Mixing = Vec<Vec<(usize, f64)>>;

/// Od koho se která skupina učí (`mixing_matrix`): vlastní skupina s vahou `1 − otevřenost`,
/// zbytek mezi sousedy úměrně síle vazby a prestiži zdroje (`prestiž ** alpha`).
pub fn mixing(world: &World, axis: &[GroupId], alpha: f64) -> Mixing {
    let n = axis.len();
    let mut place = vec![usize::MAX; world.groups.len()];
    for (column, group) in axis.iter().enumerate() {
        place[group.index()] = column;
    }
    let power: Vec<f64> = axis
        .iter()
        .map(|g| world.groups.prestige[g.index()].powf(alpha))
        .collect();
    let mut rows: Mixing = Vec::with_capacity(n);
    for (row, &group) in axis.iter().enumerate() {
        let mut weights: Vec<(usize, f64)> = Vec::new();
        for (target, link) in world.links.from(group) {
            let column = place.get(target.index()).copied().unwrap_or(usize::MAX);
            if column != usize::MAX {
                weights.push((column, link.strength * power[column]));
            }
        }
        weights.sort_by_key(|&(column, _)| column);
        let total: f64 = weights.iter().map(|&(_, w)| w).sum();
        let openness = if total > 0.0 {
            world.groups.openness[group.index()]
        } else {
            0.0
        };
        let safe = if total > 0.0 { total } else { 1.0 };
        let mut entries: Vec<(usize, f64)> = Vec::with_capacity(weights.len() + 1);
        let mut own = (1.0 - openness) * 1.0;
        for (column, weight) in weights {
            let value = openness * (weight / safe);
            if column == row {
                own += value;
            } else if value != 0.0 {
                entries.push((column, value));
            }
        }
        if own != 0.0 {
            entries.push((row, own));
        }
        entries.sort_by_key(|&(column, _)| column);
        rows.push(entries);
    }
    rows
}

/// Propojené komponenty sítě seřazené podle nejmenšího člena; členové vzestupně.
pub fn components(mixing: &Mixing) -> Vec<Vec<usize>> {
    let n = mixing.len();
    let mut parent: Vec<usize> = (0..n).collect();
    fn root(parent: &mut [usize], mut index: usize) -> usize {
        while parent[index] != index {
            parent[index] = parent[parent[index]];
            index = parent[index];
        }
        index
    }
    for (row, entries) in mixing.iter().enumerate() {
        for &(column, _) in entries {
            let (a, b) = (root(&mut parent, row), root(&mut parent, column));
            if a != b {
                parent[a.max(b)] = a.min(b);
            }
        }
    }
    let mut members: std::collections::BTreeMap<usize, Vec<usize>> =
        std::collections::BTreeMap::new();
    for index in 0..n {
        let r = root(&mut parent, index);
        members.entry(r).or_default().push(index);
    }
    members.into_values().collect()
}

/// Bloky matice komponenty: vybrané buňky `(učící se, zdroj)` s hodnotou `value`
/// (`None` = buňka se vynechá), seřazené podle zdroje.
fn component_links(
    mixing: &Mixing,
    members: &[usize],
    local: &[usize],
    mut value: impl FnMut(usize, usize, f64) -> Option<f64>,
) -> Component {
    let mut links = Links {
        start: Vec::with_capacity(members.len() + 1),
        ..Links::default()
    };
    links.start.push(0);
    for &row in members {
        for &(column, weight) in &mixing[row] {
            if let Some(found) = value(row, column, weight) {
                if found != 0.0 {
                    links.source.push(local[column]);
                    links.weight.push(found);
                }
            }
        }
        links.start.push(links.source.len());
    }
    Component {
        members: members.to_vec(),
        links,
    }
}

/// Vstupy kroku pro osu živých fondů světa.
pub fn prepare(world: &World, params: &TransmissionParams, tick: u32) -> StepInputs {
    let axis: Vec<GroupId> = world.live.group_ids.clone();
    let n = axis.len();
    let groups = &world.groups;
    let renewal: Vec<f64> = axis.iter().map(|&g| groups.renewal(g, params.dt)).collect();
    let (mut drift_scale, mut loss_floor) = (Vec::with_capacity(n), Vec::with_capacity(n));
    for (column, &group) in axis.iter().enumerate() {
        // Kohorta je podíl obnovené populace (nejméně jeden mluvčí). Město je síť čtvrtí: náhodný
        // posun v něm má velikost vesnice, jinak by se ve velkém městě změny skoro nehnuly
        // (Řím by si navždy držel koncové -m; dok. 27).
        let mut people = f64::from(groups.population[group.index()]);
        let territory = groups.territory[group.index()];
        if world
            .territories
            .get(territory.index())
            .is_some_and(|t| t.urban > 0.0)
        {
            people /= world.params.city_size.max(1.0);
        }
        let cohort = (renewal[column] * people).max(1.0);
        drift_scale.push(params.sigma / cohort.sqrt());
        loss_floor.push(params.loss_threshold.max(0.5 / cohort));
    }
    let matrix = mixing(world, &axis, params.alpha);
    let found = components(&matrix);
    let mut local = vec![0_usize; n];
    for members in &found {
        for (position, &member) in members.iter().enumerate() {
            local[member] = position;
        }
    }
    let linked: Vec<&Vec<usize>> = found.iter().filter(|m| m.len() > 1).collect();
    let mut alone = Vec::new();
    let mut alone_weight = Vec::new();
    for members in found.iter().filter(|m| m.len() == 1) {
        let at = members[0];
        alone.push(at);
        alone_weight.push(
            matrix[at]
                .iter()
                .find(|&&(column, _)| column == at)
                .map_or(0.0, |&(_, w)| w),
        );
    }
    let languages: Vec<_> = axis.iter().map(|&g| groups.main_code(g).language).collect();
    let foreign = |row: usize, column: usize| languages[row] != languages[column];
    let mut cross: Vec<CrossFlow> = Vec::new();
    let any_foreign = matrix
        .iter()
        .enumerate()
        .any(|(row, entries)| entries.iter().any(|&(column, _)| foreign(row, column)));
    if any_foreign {
        // Rozdělení vazby mezi kanály dává rozhraní kontaktu (`contact::channel_split`); vazby
        // se nepočítají do čtvercových matic, jen po řádcích míšení.
        let distinct = contact::distinct_channels(&world.params);
        let elite_on = distinct.contains(&contact::ELITE);
        let trade_on = distinct.contains(&contact::TRADE) && !world.society.trade.is_empty();
        let split = |row: usize, column: usize| {
            contact::channel_split(world, axis[row], axis[column], &distinct)
        };
        let separate = elite_on || trade_on;
        let mut channels = vec![FlowChannel::Neighbor];
        if elite_on {
            channels.push(FlowChannel::Elite);
        }
        if trade_on {
            channels.push(FlowChannel::Trade);
        }
        for channel in channels {
            let components: Vec<Component> = linked
                .iter()
                .map(|members| {
                    component_links(&matrix, members, &local, |row, column, weight| {
                        if !foreign(row, column) {
                            return None;
                        }
                        if channel == FlowChannel::Neighbor && !separate {
                            return Some(weight);
                        }
                        let share = split(row, column);
                        let fraction = match channel {
                            FlowChannel::Neighbor => share.neighbor,
                            FlowChannel::Elite => share.elite,
                            FlowChannel::Trade => share.trade,
                        };
                        Some(weight * fraction)
                    })
                })
                .collect();
            if components.iter().any(|c| !c.links.is_empty()) {
                cross.push(CrossFlow {
                    channel,
                    components,
                });
            }
        }
    }
    let components: Vec<Component> = linked
        .iter()
        .map(|members| {
            component_links(&matrix, members, &local, |row, column, weight| {
                (!foreign(row, column)).then_some(weight)
            })
        })
        .collect();
    let sides = sides(world, &axis);
    let row_keys = axis
        .iter()
        .map(|&g| {
            stable_int(&[
                Part::Int(world.seed),
                Part::Str("drift"),
                Part::Int(i64::from(tick)),
                Part::Str(world.group_name(g)),
            ])
        })
        .collect();
    let borrow = BorrowTable::build(world);
    StepInputs {
        axis,
        components,
        alone,
        alone_weight,
        cross,
        sides,
        renewal,
        drift_scale,
        loss_floor,
        row_keys,
        tick,
        borrow,
    }
}

/// Kanály mimo vazby sítě v pořadí interference, čtení, škola, liturgie; jen neprázdné.
fn sides(world: &World, axis: &[GroupId]) -> Vec<Side> {
    let params = &world.params;
    let groups = &world.groups;
    let mut place = vec![usize::MAX; groups.len().max(1)];
    for (column, group) in axis.iter().enumerate() {
        place[group.index()] = column;
    }
    let column_of = |group: GroupId| -> Option<usize> {
        if group.is_none() {
            return None;
        }
        place
            .get(group.index())
            .copied()
            .filter(|&c| c != usize::MAX)
    };
    let mut interference = Side::new(SideKind::Interference);
    let mut reading = Side::new(SideKind::Reading);
    let mut school = Side::new(SideKind::School);
    let mut liturgy = Side::new(SideKind::Liturgy);
    for (learner, &group) in axis.iter().enumerate() {
        let at = group.index();
        let code = groups.main_code(group);
        if let Some(source) = column_of(code.l1_source) {
            if code.l2_share > 0.0 {
                let correction = params.school_correction * groups.schooling[at];
                interference.push(
                    learner,
                    source,
                    params.interference_weight * code.l2_share * (1.0 - correction),
                );
            }
        }
        if let Some(source) = column_of(groups.standard[at]) {
            if groups.literacy[at] > 0.0 {
                reading.push(learner, source, params.reading_weight * groups.literacy[at]);
            }
            if groups.schooling[at] > 0.0 {
                school.push(learner, source, params.school_weight * groups.schooling[at]);
            }
        }
        if let Some(source) = column_of(groups.liturgy[at]) {
            if groups.devotion[at] > 0.0 {
                liturgy.push(learner, source, params.liturgy_weight * groups.devotion[at]);
            }
        }
    }
    [interference, reading, school, liturgy]
        .into_iter()
        .filter(|side| !side.learners.is_empty())
        .collect()
}

impl Side {
    fn new(kind: SideKind) -> Side {
        Side {
            kind,
            learners: Vec::new(),
            sources: Vec::new(),
            weights: Vec::new(),
        }
    }

    fn push(&mut self, learner: usize, source: usize, weight: f64) {
        self.learners.push(learner);
        self.sources.push(source);
        self.weights.push(weight);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn komponenty_jsou_serazene_podle_nejmensiho_clena() {
        // 0 – 2 a 1 osamělá, 3 – 4.
        let matrix: Mixing = vec![
            vec![(0, 0.5), (2, 0.5)],
            vec![(1, 1.0)],
            vec![(0, 0.4), (2, 0.6)],
            vec![(3, 0.5), (4, 0.5)],
            vec![(3, 0.5), (4, 0.5)],
        ];
        assert_eq!(components(&matrix), vec![vec![0, 2], vec![1], vec![3, 4]]);
    }

    #[test]
    fn blok_komponenty_ma_zdroje_vzestupne_a_vynechava_nuly() {
        let matrix: Mixing = vec![vec![(0, 0.5), (1, 0.5)], vec![(0, 0.25), (1, 0.75)]];
        let local = vec![0, 1];
        let component = component_links(&matrix, &[0, 1], &local, |row, column, weight| {
            (row != column).then_some(weight)
        });
        assert_eq!(component.links.start, vec![0, 1, 2]);
        assert_eq!(component.links.source, vec![1, 0]);
        assert_eq!(component.links.weight, vec![0.5, 0.25]);
    }
}
