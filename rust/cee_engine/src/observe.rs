//! Pozorování: linie jazyků mezi snímky (zrcadlo `observe.LineageTracker`).
//!
//! Shluky skupin počítá `cee_core::observe` (průměrná vazba s omezením sousedství);
//! tady se párují shluky mezi snímky a zapisují rozštěpení jazyků. Členové linie se
//! drží jako **jména** skupin (jména se nemění, pořadí podle jmen jako v Pythonu).

use std::collections::{BTreeMap, BTreeSet, HashMap};

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

use crate::rng::{stable_id, stable_int, Part};

/// Páruje shluky jazyků mezi snímky a zapisuje jejich rozštěpení.
///
/// Nový shluk zdědí linii toho předchozího, s nímž sdílí nejvíc skupin. Když z jedné
/// linie vzejde víc shluků, největší pokračuje a ostatní jsou nové linie odštěpené od
/// ní. Z těchto záznamů vzniká emergentní strom jazyků.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct LineageTracker {
    /// ID linie → členové (seřazená jména skupin).
    pub lineages: BTreeMap<String, Vec<String>>,
}

/// Výsledek `update`: linie → členové a události (`language_emerged`, `language_split`,
/// `language_ended`).
pub struct LineageUpdate {
    pub languages: BTreeMap<String, Vec<String>>,
    pub events: Vec<Value>,
}

impl LineageTracker {
    /// Linie, do které skupina (jméno) patří.
    pub fn member_of(&self) -> HashMap<&str, &str> {
        let mut map = HashMap::new();
        for (lineage, members) in &self.lineages {
            for member in members {
                map.insert(member.as_str(), lineage.as_str());
            }
        }
        map
    }

    pub fn update(&mut self, clusters: &[Vec<String>], tick: u32) -> LineageUpdate {
        let member_of = self.member_of();
        // Rodič každého shluku: linie s největším překryvem (při shodě menší ID).
        let mut claims: BTreeMap<Option<String>, Vec<BTreeSet<&str>>> = BTreeMap::new();
        for cluster in clusters {
            let members: BTreeSet<&str> = cluster.iter().map(String::as_str).collect();
            let mut overlap: BTreeMap<&str, usize> = BTreeMap::new();
            for name in &members {
                if let Some(&lineage) = member_of.get(name) {
                    *overlap.entry(lineage).or_default() += 1;
                }
            }
            let parent = overlap
                .iter()
                .max_by(|a, b| a.1.cmp(b.1).then(b.0.cmp(a.0)))
                .map(|(&lineage, _)| lineage.to_owned());
            claims.entry(parent).or_default().push(members);
        }
        let mut events = Vec::new();
        let mut assigned: BTreeMap<String, Vec<String>> = BTreeMap::new();
        // Pořadí rodičů: nejdřív pojmenovaní podle ID, nakonec „žádný“.
        let mut parents: Vec<&Option<String>> = claims.keys().collect();
        parents.sort_by(|a, b| (a.is_none(), a.as_deref()).cmp(&(b.is_none(), b.as_deref())));
        for parent in parents {
            let previous: BTreeSet<&str> = parent
                .as_deref()
                .and_then(|p| self.lineages.get(p))
                .map(|v| v.iter().map(String::as_str).collect())
                .unwrap_or_default();
            let mut successors: Vec<&BTreeSet<&str>> = claims[parent].iter().collect();
            successors.sort_by(|a, b| {
                let overlap_a = a.intersection(&previous).count();
                let overlap_b = b.intersection(&previous).count();
                overlap_b
                    .cmp(&overlap_a)
                    .then(b.len().cmp(&a.len()))
                    .then(a.iter().next().cmp(&b.iter().next()))
            });
            for (position, members) in successors.into_iter().enumerate() {
                let sorted: Vec<String> = members.iter().map(|s| (*s).to_owned()).collect();
                if let (Some(parent), 0) = (parent, position) {
                    assigned.insert(parent.clone(), sorted);
                    continue;
                }
                let first = members.iter().next().copied().unwrap_or("");
                let lineage = stable_id(
                    "lineage",
                    &[
                        Part::from(parent.as_deref().unwrap_or("None")),
                        Part::from(tick),
                        Part::from(first),
                    ],
                );
                events.push(json!({
                    "kind": if parent.is_some() { "language_split" } else { "language_emerged" },
                    "lineage": lineage,
                    "parent": parent,
                    "groups": sorted,
                }));
                assigned.insert(lineage, sorted);
            }
        }
        for lineage in self.lineages.keys() {
            if !assigned.contains_key(lineage) {
                events.push(json!({"kind": "language_ended", "lineage": lineage}));
            }
        }
        self.lineages = assigned.clone();
        LineageUpdate {
            languages: assigned,
            events,
        }
    }
}

// --- pozorování světa ----------------------------------------------------------------
//
// Jádro (`cee_core::observe`) počítá nad poli; tady se pole skládají z modelu světa:
// pohledy na bloky živých fondů, dominantní kořeny a tvary skupin (jen tvary, které skupiny
// opravdu užívají, ne celá banka), vazby a polohy mluvených skupin. Čas i paměť rostou
// s počtem skupin lineárně (krát počet živých proměnných): shlukují se jen sousedící shluky
// a průměrná vazba se bere ze součtů za shluk, nikdy z matice všech dvojic. Matice
// vzdáleností kódů (`code_distances`) je čtvercová a staví se jen na vyžádání
// (`SimulationConfig::keep_distances`).

use cee_core::observe::{
    candidates, categories, cognate_totals, continua, distance_totals, embedded_features, linkage,
    Costs, Dominant, FormTable, Hysteresis, PoolView, DISTANCE_CHUNK, FORM_WEIGHT,
};

use crate::ids::GroupId;
use crate::model::repertoire::VariableKind;
use crate::world::World;

/// Cena záměny hlásky je podíl odlišných rysů dělený tímto počtem (nejvýš 1).
pub const FEATURE_SCALE: f64 = 6.0;
/// Hystereze rozpoznání jazyků jako podíl prahu: dvojice, která byla jedním jazykem, se
/// rozdělí až nad prahem + rezerva, oddělená se spojí až pod prahem − rezerva.
pub const HYSTERESIS: f64 = 0.1;

/// Vlastněné buffery vstupu pozorování; pohledy pro jádro dává [`ObserveInput::views`].
pub struct ObserveInput {
    /// Počet živých skupin (osa fondů).
    pub live: usize,
    /// Počet lexikálních proměnných světa.
    pub lexical: usize,
    freqs: Vec<Vec<f64>>,
    present: Vec<Vec<bool>>,
    capacity: Vec<usize>,
    rows: Vec<Vec<i64>>,
    ranks: Vec<Vec<i64>>,
    forms: Option<FormsInput>,
}

struct FormsInput {
    ptr: Vec<i64>,
    concept: Vec<i32>,
    root: Vec<i32>,
    form: Vec<i32>,
    form_ptr: Vec<i64>,
    form_flat: Vec<i32>,
    concept_rank: Vec<i32>,
}

impl ObserveInput {
    /// Vstup z živých fondů světa: proměnné slov a konstrukcí, dominantní kořeny a tvary.
    pub fn gather(world: &World) -> ObserveInput {
        let live = world.live.group_ids.len();
        let lexical = world
            .variables
            .kind
            .iter()
            .filter(|&&k| k == VariableKind::Lexical)
            .count();
        // Pořadí proměnných při výběru vzorku sloupců: stabilní hash jména, při shodě jméno.
        let mut chosen: Vec<(usize, Vec<usize>)> = Vec::new();
        let mut keyed: Vec<(u64, String)> = Vec::new();
        for (index, block) in world.live.blocks.values().enumerate() {
            let rows: Vec<usize> = (0..block.len())
                .filter(|&row| {
                    matches!(
                        world.variables.kind[block.variables[row].index()],
                        VariableKind::Lexical | VariableKind::Construction
                    )
                })
                .collect();
            for &row in &rows {
                let name = world.registry.variables.name(block.variables[row].0);
                keyed.push((
                    stable_int(&[Part::Str("observe"), Part::Str(name)]),
                    name.to_owned(),
                ));
            }
            chosen.push((index, rows));
        }
        let mut order: Vec<usize> = (0..keyed.len()).collect();
        order.sort_by(|&a, &b| keyed[a].cmp(&keyed[b]));
        let mut rank_of = vec![0_i64; keyed.len()];
        for (rank, &at) in order.iter().enumerate() {
            rank_of[at] = rank as i64;
        }
        let mut input = ObserveInput {
            live,
            lexical,
            freqs: Vec::new(),
            present: Vec::new(),
            capacity: Vec::new(),
            rows: Vec::new(),
            ranks: Vec::new(),
            forms: None,
        };
        let mut start = 0;
        for ((_, rows), block) in chosen.iter().zip(world.live.blocks.values()) {
            if rows.is_empty() {
                continue;
            }
            let (freqs, present) = block.dense_selected(rows);
            input.freqs.push(freqs);
            input.present.push(present);
            input.capacity.push(block.capacity);
            input.rows.push((0..rows.len() as i64).collect());
            input
                .ranks
                .push(rank_of[start..start + rows.len()].to_vec());
            start += rows.len();
        }
        input.forms = FormsInput::gather(world);
        input
    }

    /// Pohledy na bloky pro jádro.
    pub fn views(&self) -> Vec<PoolView<'_>> {
        (0..self.freqs.len())
            .map(|at| PoolView {
                freqs: &self.freqs[at],
                present: &self.present[at],
                groups: self.live,
                capacity: self.capacity[at],
                rows: &self.rows[at],
                ranks: &self.ranks[at],
            })
            .collect()
    }
}

impl FormsInput {
    fn gather(world: &World) -> Option<FormsInput> {
        world.table.as_ref()?;
        let mut local = vec![-1_i32; world.bank.len()];
        let (mut form_ptr, mut form_flat) = (vec![0_i64], Vec::new());
        let (mut ptr, mut concept, mut root, mut form) =
            (vec![0_i64], Vec::new(), Vec::new(), Vec::new());
        for &group in &world.live.group_ids {
            let dominant = &world.groups.main_code(group).phonology.dominant;
            for (number, &morpheme) in dominant.iter().enumerate() {
                if morpheme.is_none() {
                    continue;
                }
                let id = world.unit_of(group, morpheme).form as usize;
                if local[id] < 0 {
                    local[id] = (form_ptr.len() - 1) as i32;
                    form_flat.extend_from_slice(world.bank.form(id as u32));
                    form_ptr.push(form_flat.len() as i64);
                }
                concept.push(number as i32);
                root.push(morpheme.0 as i32);
                form.push(local[id]);
            }
            ptr.push(concept.len() as i64);
        }
        Some(FormsInput {
            ptr,
            concept,
            root,
            form,
            form_ptr,
            form_flat,
            concept_rank: world
                .registry
                .concepts
                .ranks()
                .into_iter()
                .map(|r| r as i32)
                .collect(),
        })
    }

    fn dominant(&self) -> Dominant<'_> {
        Dominant {
            ptr: &self.ptr,
            concept: &self.concept,
            root: &self.root,
            form: &self.form,
        }
    }

    fn table(&self) -> FormTable<'_> {
        FormTable {
            ptr: &self.form_ptr,
            flat: &self.form_flat,
        }
    }
}

/// Matice `(živé skupiny)²` vzdáleností kódů: rozdíl rozdělení variant slov a konstrukcí,
/// plus rozdíl tvarů příbuzných slov, dělené počtem lexikálních proměnných (`code_distances`).
/// Čtvercová, jen na vyžádání.
pub fn code_distances(world: &World) -> Vec<f64> {
    let input = ObserveInput::gather(world);
    let live = input.live;
    let count = input.lexical.max(1) as f64;
    let mut total = distance_totals(
        &input.views(),
        live,
        DISTANCE_CHUNK,
        rayon::current_num_threads(),
    );
    for value in &mut total {
        *value /= count;
    }
    if let (Some(forms), Some(table)) = (&input.forms, world.table.as_ref()) {
        let mut costs = Costs::new(table.vectors(), table.width(), FEATURE_SCALE);
        let cognate = cognate_totals(
            &forms.dominant(),
            live,
            &forms.concept_rank,
            &forms.table(),
            &mut costs,
        );
        for (value, add) in total.iter_mut().zip(&cognate) {
            *value += FORM_WEIGHT * add / count;
        }
    }
    total
}

/// Brána tvarů u jazyků (`Hysteresis::form_gate`, dok. 34): rozdíl výslovnosti příbuzných slov
/// se do vzdálenosti jazyků započte celý až od takového rozdílu slov a konstrukcí (na jednu
/// proměnnou slova). Skupina po přechodu jazyka mluví stejným slovníkem s cizí výslovností
/// (talmurština se serenským přízvukem, irská angličtina): je nářečím cílového jazyka. Mezi
/// skutečně oddělenými jazyky (španělština a portugalština) se slovník liší dost na plnou váhu.
pub const LANGUAGE_FORM_GATE: f64 = 0.3;

/// Výsledek pozorování: shluky dialektů a jazyků jako seznamy pozic mezi mluvenými skupinami.
pub struct Observed {
    /// Mluvené domácí skupiny (psaný kód nemá mluvčí, kód trhu či školy je druhý jazyk).
    pub spoken: Vec<GroupId>,
    pub dialects: Vec<Vec<usize>>,
    pub languages: Vec<Vec<usize>>,
}

/// Shluky dialektů a jazyků mluvených skupin světa (průměrná vazba mezi sousedícími shluky).
pub fn observe_world(
    world: &World,
    tracker: &LineageTracker,
    dialect_threshold: f64,
    language_threshold: f64,
) -> Observed {
    let input = ObserveInput::gather(world);
    let live = &world.live.group_ids;
    let cols: Vec<usize> = (0..live.len())
        .filter(|&at| {
            let g = live[at].index();
            !world.groups.written[g] && world.groups.domain[g] == crate::model::group::Domain::Home
        })
        .collect();
    let spoken: Vec<GroupId> = cols.iter().map(|&at| live[at]).collect();
    // Dosavadní linie skupin jako čísla (podle seřazených ID linií).
    let member_of = tracker.member_of();
    let numbers: std::collections::BTreeMap<&str, i64> = tracker
        .lineages
        .keys()
        .enumerate()
        .map(|(n, id)| (id.as_str(), n as i64))
        .collect();
    let labels: Vec<i64> = spoken
        .iter()
        .map(|&g| {
            member_of
                .get(world.group_name(g))
                .map_or(-1, |lineage| numbers[lineage])
        })
        .collect();
    let mut features = embedded_features(
        &input.views(),
        &cols,
        input.lexical,
        rayon::current_num_threads(),
    );
    if let (Some(forms), Some(table)) = (&input.forms, world.table.as_ref()) {
        let mut costs = Costs::new(table.vectors(), table.width(), FEATURE_SCALE);
        let found = categories(&forms.dominant(), &cols, &forms.table(), &mut costs);
        features.forms = found.forms;
        features.spread = found.spread;
    }
    // Vazby mezi mluvenými skupinami (dvojice pozic) a polohy.
    let mut position = vec![-1_i64; world.groups.len()];
    for (at, g) in spoken.iter().enumerate() {
        position[g.index()] = at as i64;
    }
    let linked: Vec<(u32, u32)> = world
        .links
        .iter()
        .filter_map(|(&(a, b), _)| {
            let (pa, pb) = (position[a.index()], position[b.index()]);
            (pa >= 0 && pb >= 0 && pa != pb).then_some((pa as u32, pb as u32))
        })
        .collect();
    let (mut slots, mut xs, mut ys) = (Vec::new(), Vec::new(), Vec::new());
    for (at, &g) in spoken.iter().enumerate() {
        if let Some((x, y)) = world.position_of(g) {
            slots.push(at as u32);
            xs.push(x);
            ys.push(y);
        }
    }
    let pairs = candidates(&linked, &slots, &xs, &ys);
    let hysteresis = Hysteresis {
        labels: &labels,
        margin: HYSTERESIS * language_threshold,
        form_gate: LANGUAGE_FORM_GATE,
    };
    // Střecha skupiny: spisovná norma vlastního jazyka, kterou skupina čte (dok. 37).
    let roofs: Vec<i64> = spoken
        .iter()
        .map(|&g| {
            let standard = world.groups.standard[g.index()];
            let own = !standard.is_none()
                && world.groups.contains(standard)
                && world.groups.literacy[g.index()] > 0.0
                && world.groups.main_code(standard).language == world.groups.main_code(g).language;
            if own {
                i64::from(standard.0)
            } else {
                -1
            }
        })
        .collect();
    // Shlukování dialektů a jazyků je nezávislé (každé čte jen rysy a kandidáty): souběžně.
    let (dialects, languages) = rayon::join(
        || linkage(&features, &pairs, dialect_threshold, None),
        || {
            continua(
                &features,
                &pairs,
                language_threshold,
                Some(&hysteresis),
                &roofs,
            )
        },
    );
    Observed {
        spoken,
        dialects,
        languages,
    }
}
