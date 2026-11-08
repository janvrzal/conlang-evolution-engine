//! Podklady pro jména jazyků a nářečí (zrcadlo `naming.py`, jen pro export UI).
//!
//! Engine jména nevymýšlí v češtině ani v jiném jazyce UI. Dodává fakta, ze kterých UI
//! jméno složí:
//!
//! * **vlastní jméno jazyka** (endonym): složenina slov protojazyka (`SocietyState::endonyms`,
//!   např. „lidé“ + „řeč“), kterou si každá linie nese a mění s ostatními slovy;
//! * **kde jazyk vznikl**: region, ve kterém ležela většina jeho vesnic při rozštěpení;
//! * **poloha nářečí**: směr od středu jazyka (osm směrů nebo střed), regiony, terén.
//!
//! Nic z toho neovlivňuje dynamiku ani otisk historie. Poloha je v km; osa *y* roste k jihu.

use std::collections::BTreeMap;

use serde_json::{json, Value};

use crate::ids::{ConceptId, GroupId, TerritoryId};
use crate::model::group::Domain;
use crate::model::territory::TerritoryLevel;
use crate::world::World;

/// Směry od středu jazyka po 45° (osa y k jihu).
pub const DIRECTIONS: [&str; 8] = [
    "east",
    "southeast",
    "south",
    "southwest",
    "west",
    "northwest",
    "north",
    "northeast",
];

/// Nářečí blíž ke středu jazyka než tento podíl jeho poloměru je `center`.
pub const CENTER_SHARE: f64 = 0.35;

/// Slabiky tvaru: souhláska před samohláskou začíná novou slabiku.
pub fn syllables(segments: &[i32], is_vowel: &dyn Fn(i32) -> bool) -> Vec<Vec<i32>> {
    let mut out: Vec<Vec<i32>> = vec![Vec::new()];
    for (index, &segment) in segments.iter().enumerate() {
        let current = out.last().expect("slabika");
        let has_vowel = current.iter().any(|&s| is_vowel(s));
        let next_vowel = segments.get(index + 1).is_some_and(|&s| is_vowel(s));
        if has_vowel && (is_vowel(segment) || next_vowel) {
            out.push(vec![segment]);
        } else {
            out.last_mut().expect("slabika").push(segment);
        }
    }
    out.retain(|s| !s.is_empty());
    out
}

/// Složenina jako u místních jmen: první části na slabiku, celek nejvýš o dvě slabiky delší.
pub fn compound(parts: &[Vec<i32>], is_vowel: &dyn Fn(i32) -> bool) -> Vec<i32> {
    let split: Vec<Vec<Vec<i32>>> = parts
        .iter()
        .filter(|p| !p.is_empty())
        .map(|p| syllables(p, is_vowel))
        .collect();
    let Some((tail, heads)) = split.split_last() else {
        return Vec::new();
    };
    let mut kept: Vec<&Vec<i32>> = heads.iter().filter_map(|part| part.first()).collect();
    let limit = 2.max(kept.len() + 2);
    kept.extend(tail.iter());
    kept.into_iter().take(limit).flatten().copied().collect()
}

/// Mluvená domácí skupina s nejvíc lidmi (při shodě první podle jména).
pub fn representative(world: &World, groups: &[String]) -> Option<GroupId> {
    let mut names: Vec<&String> = groups.iter().collect();
    names.sort();
    let mut best: Option<GroupId> = None;
    for name in names {
        let Some(id) = world
            .registry
            .groups
            .get(name)
            .map(GroupId)
            .filter(|g| world.groups.contains(*g))
        else {
            continue;
        };
        let g = id.index();
        if world.groups.written[g] || world.groups.domain[g] != Domain::Home {
            continue;
        }
        if best.is_none_or(|b| world.groups.population[g] > world.groups.population[b.index()]) {
            best = Some(id);
        }
    }
    best
}

/// Vlastní jméno jazyka, jak ho dnes vyslovují jeho mluvčí (IPA).
pub fn endonym(world: &World, groups: &[String]) -> Option<String> {
    let group = representative(world, groups)?;
    let table = world.table.as_ref()?;
    let code = world.groups.main_code(group);
    let default = [ConceptId(
        world.registry.concepts.get("language").unwrap_or(u32::MAX),
    )];
    let concepts = world
        .society
        .endonyms
        .get(&code.language)
        .map_or(&default[..], Vec::as_slice);
    let mut parts: Vec<Vec<i32>> = Vec::new();
    for concept in concepts {
        let root = world.dominant_or_plural_root(group, *concept);
        if root.is_none() {
            continue;
        }
        parts.push(world.adapted_form_of(group, root));
    }
    let form = crate::onomastics::smooth_compound(&parts, &|s| table.is_vowel(s));
    let rendered: String = form.iter().map(|&s| table.render(&[s])).collect();
    (!rendered.is_empty()).then_some(rendered)
}

fn region_of(world: &World, group: GroupId) -> Option<TerritoryId> {
    if !world.groups.contains(group) {
        return None;
    }
    let mut territory = world.groups.territory[group.index()];
    while !territory.is_none() {
        let node = &world.territories[territory.index()];
        if node.level == TerritoryLevel::Region {
            return Some(territory);
        }
        territory = node.parent;
    }
    None
}

fn group_id(world: &World, name: &str) -> Option<GroupId> {
    world
        .registry
        .groups
        .get(name)
        .map(GroupId)
        .filter(|g| world.groups.contains(*g))
}

/// Seřazené regiony podle počtu skupin (sestupně) a jména.
fn region_counts(world: &World, groups: &[String]) -> Vec<(String, usize)> {
    let mut counts: BTreeMap<String, usize> = BTreeMap::new();
    for name in groups {
        if let Some(region) = group_id(world, name).and_then(|g| region_of(world, g)) {
            *counts
                .entry(world.registry.territories.name(region.0).to_owned())
                .or_default() += 1;
        }
    }
    let mut found: Vec<(String, usize)> = counts.into_iter().collect();
    found.sort_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(&b.0)));
    found
}

/// Region, ve kterém leží většina vesnic (při shodě první podle jména).
pub fn origin_region(world: &World, groups: &[String]) -> Option<String> {
    region_counts(world, groups).into_iter().next().map(|r| r.0)
}

/// Směr posunu od středu (osa y k jihu), nebo `center`.
pub fn direction(offset: (f64, f64), radius: f64) -> &'static str {
    let (dx, dy) = offset;
    if radius <= 0.0 || dx.hypot(dy) < CENTER_SHARE * radius {
        return "center";
    }
    let angle = dy.atan2(dx).to_degrees().rem_euclid(360.0);
    DIRECTIONS[(((angle + 22.5).rem_euclid(360.0)) / 45.0).floor() as usize]
}

fn centre(world: &World, groups: &[String]) -> (f64, f64) {
    let points: Vec<(f64, f64)> = groups
        .iter()
        .filter_map(|n| group_id(world, n).and_then(|g| world.position_of(g)))
        .collect();
    if points.is_empty() {
        return (0.0, 0.0);
    }
    let n = points.len() as f64;
    (
        points.iter().map(|p| p.0).sum::<f64>() / n,
        points.iter().map(|p| p.1).sum::<f64>() / n,
    )
}

/// Fakta pro jméno každého nářečí: jazyk, regiony, směr od středu jazyka, terén.
pub fn dialects(
    world: &World,
    clusters: &[Vec<String>],
    lineage_of: &BTreeMap<String, String>,
) -> Vec<Value> {
    let mut members: BTreeMap<&str, Vec<String>> = BTreeMap::new();
    for cluster in clusters {
        for name in cluster {
            if let Some(lineage) = lineage_of.get(name) {
                members.entry(lineage).or_default().push(name.clone());
            }
        }
    }
    let centres: BTreeMap<&str, (f64, f64)> = members
        .iter()
        .map(|(l, g)| (*l, centre(world, g)))
        .collect();
    let radius: BTreeMap<&str, f64> = members
        .iter()
        .map(|(l, groups)| {
            let c = centres[l];
            let r = groups
                .iter()
                .filter_map(|n| group_id(world, n).and_then(|g| world.position_of(g)))
                .map(|p| (c.0 - p.0).hypot(c.1 - p.1))
                .fold(0.0, f64::max);
            (*l, r)
        })
        .collect();
    clusters
        .iter()
        .map(|cluster| {
            let mut groups = cluster.clone();
            groups.sort();
            let mut lineages: BTreeMap<&str, usize> = BTreeMap::new();
            for name in &groups {
                if let Some(l) = lineage_of.get(name) {
                    *lineages.entry(l).or_default() += 1;
                }
            }
            let lineage = lineages
                .iter()
                .max_by(|a, b| a.1.cmp(b.1).then(b.0.cmp(a.0)))
                .map(|(l, _)| *l);
            let regions = region_counts(world, &groups);
            let mut terrains: Vec<&str> = regions
                .iter()
                .filter_map(|(r, _)| world.registry.territories.get(r))
                .map(|n| world.territories[n as usize].terrain.as_str())
                .collect();
            terrains.sort_unstable();
            terrains.dedup();
            let sole = lineage.is_some_and(|l| members[l].len() == groups.len());
            let here = centre(world, &groups);
            let direction = match lineage {
                Some(l) if !sole => {
                    let c = centres[l];
                    direction((here.0 - c.0, here.1 - c.1), radius[l])
                }
                _ => "center",
            };
            json!({
                "groups": groups,
                "lineage": lineage,
                "regions": regions.iter().map(|r| r.0.clone()).collect::<Vec<_>>(),
                "direction": direction,
                "terrain": if terrains.len() == 1 { json!(terrains[0]) } else { Value::Null },
                "sole": sole,
            })
        })
        .collect()
}
