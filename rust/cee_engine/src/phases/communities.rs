//! Fáze 5: komunity, přechod jazyka a dvojjazyčnost (R1d).
//!
//! **Vstup:** `World` (skupiny, kódy, vazby, prestiž), `dt`, tik, rok, historie.
//! **Výstup:** změněné populace a podíly kódů (přechod na jiný jazyk, přistěhovalci,
//! migrace), nové či zaniklé skupiny; vrací `true`, když se změnila osa skupin
//! (pak kostra přepočte živé fondy `World::sync_live_groups`). Zrcadlo
//! `contact.community_step`.
//!
//! Vícejazyčná komunita je víc skupin (jedna na kód) se společným `community`. Přechod na
//! jiný jazyk je přesun mluvčích mezi nimi podle modelu Abramse a Strogatze (2003); kód,
//! kterému se přestanou učit děti, vymře a v novém jazyce po něm zůstane substrát.
//! Svět se mění jen přes `Edits::community` (deník změn); běžné každokrokové úpravy
//! (populace, `l2_share`, přistěhovalci) se ve výchozím režimu deníku nezapisují.

use serde_json::json;

use crate::edits::{neighbors, py_round, CodeChange, Edits, Field};
use crate::history::History;
use crate::ids::GroupId;
use crate::model::group::Domain;
use crate::model::links::LinkKind;
use crate::phases::StepContext;
use crate::world::World;

/// Tah politiky, pod kterým stát přechod už netáhne (po odchodu státu zůstane 10⁻⁶).
const POLICY_ACTIVE: f64 = 1e-3;
/// Ochranná doba nové osady před přechodem na jazyk okolí (`contact_shift`, dok. 35).
const SETTLER_GRACE_YEARS: f64 = 200.0;

/// Skupina s menší populací zaniká (poslední mluvčí).
pub const LAST_SPEAKERS: f64 = 1.0;

/// Provede fázi komunit; `true`, když nějaká skupina zanikla nebo vznikla.
pub fn run(ctx: &mut StepContext<'_>) -> Result<bool, String> {
    community_step(ctx.world, ctx.config.dt, ctx.tick, ctx.year, ctx.history)
}

/// Jeden krok demografie kódů.
pub fn community_step(
    world: &mut World,
    dt: f64,
    tick: u32,
    year: f64,
    history: &mut History,
) -> Result<bool, String> {
    let edit = Edits::community(tick);
    if world.society.migration > 0.0 {
        migrate(world, &edit)?;
    }
    urban_inflow(world, &edit)?;
    if world.params.settlement_growth > 0.0 {
        settlement_growth(world, dt, &edit)?;
    }
    let mut removed = false;
    for group in world.group_ids() {
        if !world.groups.contains(group) {
            continue;
        }
        let g = group.index();
        if world.groups.written[g] {
            continue;
        }
        let renewal = (dt / world.groups.generation_years[g]).min(1.0);
        let code = world.groups.main_code(group);
        let l2_share = code.l2_share;
        let source = Some(code.l1_source).filter(|s| !s.is_none() && world.groups.contains(*s));
        if world.groups.domain[g] == Domain::Public {
            // Veřejný kód se každou generaci učí znovu v dospělosti.
            edit.set_code(world, group, CodeChange::l2_share(1.0))?;
            if let Some(source) = source {
                let pull = world.groups.home_pull[g].max(pocket_pull(world, group, source));
                if pull > 0.0 {
                    removed |= nativize(
                        world, group, source, pull, renewal, tick, year, history, &edit,
                    )?;
                }
            }
            continue;
        }
        let Some(source) = source else {
            // Stárnoucí L2 mluvčí nahradí děti, které se kód učí od narození;
            // přistěhovalci podíl drží.
            let share = l2_share + renewal * (world.groups.immigration[g] - l2_share);
            edit.set_code(world, group, CodeChange::l2_share(share))?;
            continue;
        };
        removed |= shift(world, group, source, renewal, tick, year, history, &edit)?;
    }
    if world.params.contact_shift_threshold > 0.0 {
        removed |= contact_shift(world, tick, year, history)?;
    }
    if world.params.leveling_rate > 0.0 && world.table.is_some() {
        level_forms(world, dt, tick)?;
    }
    Ok(removed)
}

/// Mluví skupina úředním jazykem státu, do kterého patří její region?
fn speaks_state_language(world: &World, group: GroupId, language: crate::ids::LanguageId) -> bool {
    let Some(region) = crate::polity::region_of(world, group) else {
        return false;
    };
    world
        .society
        .states
        .values()
        .any(|state| state.language == language && state.regions.contains(&region))
}

/// Přechod menšiny na jazyk okolí bez politiky (dok. 35): domácí skupina, jejíž jazyk má mezi
/// lidmi, se kterými mluví (vazby × populace, sama skupina plnou vahou), podíl pod
/// `contact_shift_threshold`, začne přecházet na jazyk, který mezi nimi převažuje (`language_shift`
/// s podílem 5 %; dál ho vede `shift` podle Abramse a Strogatze). Hrstky osadníků a zbytky po
/// přechodu se tak přizpůsobí okolí. Soudržná komunita (Milroy 1987: husté vazby uvnitř vlastního
/// jazyka, ostrov, horské údolí, dvě vesnice regionu spolu) má vlastních lidí mezi kontakty dost
/// a nepřejde; skupina se silnou identitou (loajalita ≥ 0,5) také ne, ani mluvčí úředního
/// jazyka státu, ve kterém žijí (dobyvatelé se státem; státní jazyk táhne opačně), ani elita
/// (přechází vlastním modelem M13).
fn contact_shift(
    world: &mut World,
    tick: u32,
    year: f64,
    history: &mut History,
) -> Result<bool, String> {
    let threshold = world.params.contact_shift_threshold;
    // Skupiny, od kterých se už některá domácí skupina jiného jazyka učí (přechod běží).
    let learned_from: std::collections::BTreeSet<GroupId> = world
        .group_ids()
        .into_iter()
        .filter(|&g| world.groups.contains(g) && world.groups.domain[g.index()] == Domain::Home)
        .map(|g| world.groups.main_code(g).l1_source)
        .filter(|s| !s.is_none())
        .collect();
    let mut starts: Vec<(GroupId, GroupId)> = Vec::new();
    for group in world.group_ids() {
        let g = group.index();
        if !world.groups.contains(group)
            || world.groups.written[g]
            || world.groups.preserved[g]
            || world.groups.domain[g] != Domain::Home
            || world.groups.loyalty[g] >= 0.5
            || world.groups.population[g] < 20
            // elita přechází vlastním modelem (M13: `polity::release`, `pocket_pull`)
            || world.groups.elite[g]
        {
            continue;
        }
        // Osadníci první generace jazyk drží (přechod trvá asi tři generace, Fishman 1966;
        // Anglosasové z roku 450 se dožijí vlastního státu): ochranná doba od založení osady.
        let territory = world.groups.territory[g];
        if world
            .territories
            .get(territory.index())
            .and_then(|t| t.settled)
            .is_some_and(|founded| year - founded < SETTLER_GRACE_YEARS)
        {
            continue;
        }
        let code = world.groups.main_code(group);
        if !code.l1_source.is_none() {
            continue; // skupina sama teprve přechází
        }
        let language = code.language;
        if learned_from.contains(&group) {
            continue; // už přechází
        }
        let own_people = f64::from(world.groups.population[g]);
        let (mut own, mut total) = (own_people, own_people);
        let mut by_language: std::collections::BTreeMap<u32, (f64, Option<(f64, GroupId)>)> =
            std::collections::BTreeMap::new();
        for (other, link) in neighbors(world, group) {
            let o = other.index();
            if world.groups.written[o] || world.groups.domain[o] != Domain::Home {
                continue;
            }
            let weight = link.strength * f64::from(world.groups.population[o]);
            total += weight;
            let other_language = world.groups.main_code(other).language;
            if other_language == language {
                own += weight;
                continue;
            }
            let entry = by_language.entry(other_language.0).or_insert((0.0, None));
            entry.0 += weight;
            if entry.1.is_none_or(|(best, _)| weight > best) {
                entry.1 = Some((weight, other));
            }
        }
        if total <= 0.0 || own / total >= threshold {
            continue;
        }
        let majority = by_language
            .values()
            .filter_map(|(weight, best)| best.map(|(_, target)| (*weight, target)))
            .max_by(|a, b| {
                a.0.partial_cmp(&b.0)
                    .unwrap_or(std::cmp::Ordering::Equal)
                    .then_with(|| world.group_name(b.1).cmp(world.group_name(a.1)))
            });
        // Prestižnější menšina (dobyvatelé, osadníci s mocí) jazyk okolí nepřebírá.
        if let Some((_, target)) = majority {
            // Přešlá odnož `X>jazyk` už někdy vznikla (přechod doběhl, odkaz na zdroj zmizel,
            // případně odnož zanikla): druhý přechod na týž jazyk nezačíná (jméno je obsazené).
            let learners = format!(
                "{}>{}",
                world.group_name(group),
                world
                    .registry
                    .languages
                    .name(world.groups.main_code(target).language.0)
            );
            let exists = world.registry.groups.contains(&learners);
            if !exists && !speaks_state_language(world, group, language) {
                starts.push((group, target));
            }
        }
    }
    let started = !starts.is_empty();
    for (group, target) in starts {
        if world.groups.contains(group) && world.groups.contains(target) {
            crate::events::language_shift(
                world,
                history,
                tick,
                year,
                group,
                target,
                &crate::events::ShiftOptions {
                    initial_share: 0.05,
                    ..Default::default()
                },
            )?;
        }
    }
    Ok(started)
}

/// Vyrovnávání nářečí podle centra (dok. 27; Trudgill 1986, Dialects in Contact): skupina
/// převezme u části slov výslovnost téhož slova od propojené skupiny stejné linie s vyšší
/// přitažlivostí (prestiž × √populace) ve stejném regionu (vesnice od města). Za generaci
/// podíl `leveling_rate` × síla vazby × (A_dárce − A) / A_dárce slov, která
/// dárce vyslovuje jinak; dárcem je soused s největší silou × rozdílem přitažlivosti. Slova se vybírají
/// stabilní náhodou; změněné slovo znovu posoudí živé hláskové změny (`requeue_all`).
fn level_forms(world: &mut World, dt: f64, tick: u32) -> Result<(), String> {
    use crate::rng::{Part, Stream};
    let rate = world.params.leveling_rate;
    let is_primary_group = |world: &World, group: GroupId| -> bool {
        crate::polity::region_of(world, group)
            .and_then(|r| world.territories.get(r.index()))
            .and_then(|t| t.children.first())
            .is_some_and(|&c| world.groups.territory[group.index()] == c)
    };
    let mut groups = world.group_ids();
    if world.params.leveling_beyond_region > 0.0 {
        // Při nadregionálním vyrovnávání nejprve srovnáme střediskové obce (`-v0`) od
        // nejsilnějších center k periferii a teprve poté podřízené osady (`-v1`, `+`) uvnitř regionu.
        groups.sort_by(|&a, &b| {
            let pa = is_primary_group(world, a);
            let pb = is_primary_group(world, b);
            pb.cmp(&pa).then_with(|| {
                let pull_a = world.groups.prestige[a.index()]
                    * f64::from(world.groups.population[a.index()]).sqrt();
                let pull_b = world.groups.prestige[b.index()]
                    * f64::from(world.groups.population[b.index()]).sqrt();
                pull_b
                    .partial_cmp(&pull_a)
                    .unwrap_or(std::cmp::Ordering::Equal)
                    .then_with(|| a.index().cmp(&b.index()))
            })
        });
    }
    for group in groups {
        if !world.groups.contains(group) {
            continue;
        }
        let g = group.index();
        if world.groups.written[g] || world.groups.domain[g] != Domain::Home {
            continue;
        }
        let language = world.groups.main_code(group).language;
        // Přitažlivost centra = prestiž × √populace (gravitační model šíření, Trudgill 1974):
        // město táhne i tam, kde mají všechny skupiny prestiž zrcadlenou od sídla státu.
        let region = crate::polity::region_of(world, group);
        let is_primary = is_primary_group(world, group);
        let rural_center = region.and_then(|r| {
            let first = *world.territories.get(r.index())?.children.first()?;
            (world.territories.get(first.index())?.urban == 0.0).then_some(first)
        });
        let base_pull =
            |at: usize| world.groups.prestige[at] * f64::from(world.groups.population[at]).sqrt();
        let pull_of = |at: usize| {
            let base = base_pull(at);
            if rural_center
                .is_some_and(|c| world.groups.territory[at] == c && world.groups.territory[g] != c)
            {
                // Ve venkovském regionu bez města (`city: 0`) působí středová vesnice (`-v0`)
                // jako místní tržiště pro ostatní osady téhož regionu.
                base * 2.5
            } else {
                base
            }
        };
        let prestige = pull_of(g);
        // Jen uvnitř regionu: město je hegemonem svého regionu (vesnice ↔ město), ne provincie
        // sídla státu (srovnání provincií podle Říma by zastavilo vývoj románských větví).
        let mut candidates = neighbors(world, group);
        if is_primary && world.params.leveling_beyond_region > 0.0 {
            if let Some(r) = region {
                for member in crate::polity::groups_in(world, &[r]) {
                    for (nb, link) in neighbors(world, member) {
                        if let Some(other_reg) = crate::polity::region_of(world, nb) {
                            if other_reg != r {
                                candidates.push((nb, link));
                                if let Ok(seat) = crate::polity::seat_of(world, other_reg) {
                                    if seat != nb {
                                        candidates.push((seat, link));
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        let donor = candidates
            .into_iter()
            .filter(|(d, _)| {
                let at = d.index();
                world.groups.contains(*d)
                    && !world.groups.written[at]
                    && world.groups.domain[at] == Domain::Home
                    && world.groups.main_code(*d).language == language
                    && ((is_primary && world.params.leveling_beyond_region > 0.0)
                        || crate::polity::region_of(world, *d) == region)
                    && pull_of(at) > prestige
            })
            .map(|(d, link)| {
                let pd = pull_of(d.index());
                let same_region = crate::polity::region_of(world, d) == region;
                // Dárce mimo region (sídlo sousedního regionu / státu) táhne podle `leveling_beyond_region`.
                let reach = if same_region {
                    1.0
                } else {
                    world.params.leveling_beyond_region
                };
                let grad = if same_region {
                    (pd - prestige) / pd
                } else {
                    ((pd - prestige) / pd).sqrt()
                };
                (d, reach * link.strength * grad)
            })
            .max_by(|a, b| {
                a.1.partial_cmp(&b.1)
                    .unwrap_or(std::cmp::Ordering::Equal)
                    .then_with(|| world.group_name(b.0).cmp(world.group_name(a.0)))
            });
        let Some((donor, pull)) = donor else { continue };
        let renewal = (dt / world.groups.generation_years[g]).min(1.0);
        // Loajalita platí vlastnímu jazyku proti cizímu, ne místní výslovnosti proti centru
        // téhož jazyka: vyrovnávání nebrzdí.
        let share = (rate * pull * renewal).clamp(0.0, 1.0);
        if share <= 0.0 {
            continue;
        }
        let differing: Vec<crate::ids::MorphemeId> = world
            .groups
            .main_code(group)
            .phonology
            .vocabulary
            .iter()
            .filter(|&unit| {
                world
                    .groups
                    .main_code(donor)
                    .phonology
                    .vocabulary
                    .contains(unit)
                    && world.unit_of(group, unit) != world.unit_of(donor, unit)
            })
            .collect();
        if differing.is_empty() {
            continue;
        }
        let mut rng = Stream::new(
            world.seed as u64,
            &[
                Part::Str("leveling"),
                Part::Uint(u64::from(tick)),
                Part::Str(world.group_name(group)),
            ],
        );
        for unit in differing {
            if rng.random() >= share {
                continue;
            }
            let form = world.unit_of(donor, unit);
            crate::views::set_form(world, group, unit, form);
            crate::phonology::requeue_all(world, group, unit)?;
        }
        world.groups.main_code_mut(group).phonology.version += 1;
    }
    Ok(())
}

/// Růst nových sídel (dok. 30): sídlo založené migrací (`Territory::settled`), menší, než je
/// obvyklá velikost vesnice v jeho regionu (medián součtu mluvčích sídel), roste logisticky
/// k ní, `settlement_growth` za generaci (předindustriální kolonizace kolem 1 % ročně;
/// Livi-Bacci 2017). Osadníci (Slované v Čechách, Sasové v Británii) tak po příchodu nezůstanou
/// navždy malou skupinou. Sídel scénáře (i záměrně malých vesnic) a měst se to netýká.
fn settlement_growth(world: &mut World, dt: f64, edit: &Edits) -> Result<(), String> {
    use crate::model::territory::TerritoryLevel;
    let rate = world.params.settlement_growth;
    let mut total: std::collections::BTreeMap<usize, f64> = std::collections::BTreeMap::new();
    for group in world.group_ids() {
        let g = group.index();
        if !world.groups.contains(group) || world.groups.written[g] || world.groups.aggregate[g] {
            continue;
        }
        if world.groups.domain[g] != Domain::Home {
            continue;
        }
        *total.entry(world.groups.territory[g].index()).or_default() +=
            f64::from(world.groups.population[g]);
    }
    // Obvyklá velikost vesnice podle regionu (rodiče sídla).
    let mut by_region: std::collections::BTreeMap<usize, Vec<f64>> =
        std::collections::BTreeMap::new();
    for (&at, &people) in &total {
        let place = &world.territories[at];
        if place.level != TerritoryLevel::Settlement || place.urban > 0.0 {
            continue;
        }
        by_region
            .entry(place.parent.index())
            .or_default()
            .push(people);
    }
    let typical: std::collections::BTreeMap<usize, f64> = by_region
        .into_iter()
        .map(|(region, mut sizes)| {
            sizes.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
            (region, sizes[sizes.len() / 2])
        })
        .collect();
    for group in world.group_ids() {
        let g = group.index();
        if !world.groups.contains(group) || world.groups.written[g] || world.groups.aggregate[g] {
            continue;
        }
        if world.groups.domain[g] != Domain::Home {
            continue;
        }
        let at = world.groups.territory[g].index();
        let place = &world.territories[at];
        if place.level != TerritoryLevel::Settlement || place.urban > 0.0 || place.settled.is_none()
        {
            continue;
        }
        let (Some(&size), Some(&target)) = (total.get(&at), typical.get(&place.parent.index()))
        else {
            continue;
        };
        if size >= target || size <= 0.0 {
            continue;
        }
        let renewal = (dt / world.groups.generation_years[g]).min(1.0);
        let factor = 1.0 + rate * renewal * (1.0 - size / target);
        let grown = (f64::from(world.groups.population[g]) * factor).round() as u32;
        if grown > world.groups.population[g] {
            edit.set_group(world, group, Field::Population(grown))?;
        }
    }
    Ok(())
}

/// Města jako hřbitovy (Wrigley 1967; de Vries 1984): ve městě umírá víc lidí, než se rodí,
/// a úbytek `Territory::urban` za generaci doplňuje příliv z venkova. Populace města se
/// nemění, ale podíl přistěhovalců (dospělých, kteří se městskou řeč učí až ve městě) drží
/// aspoň na úrovni úmrtnosti: městská řeč vyrovnává nářečí venkova (koiné; Trudgill 1986;
/// Kerswill a Williams 2000). Vazby k vesnicím regionu vznikají při stavbě města.
fn urban_inflow(world: &mut World, edit: &Edits) -> Result<(), String> {
    for group in world.group_ids() {
        let g = group.index();
        if world.groups.written[g] || world.groups.domain[g] != Domain::Home {
            continue;
        }
        let territory = world.groups.territory[g];
        let urban = world
            .territories
            .get(territory.index())
            .map_or(0.0, |t| t.urban);
        if urban > 0.0 && world.groups.immigration[g] < urban {
            edit.set_group(world, group, Field::Immigration(urban))?;
        }
    }
    Ok(())
}

/// Gravitační migrace: podíl přistěhovalců každé skupiny za generaci.
///
/// Ze skupiny odchází podíl `migration` lidí za generaci k sousedům, úměrně síle vazby,
/// velikosti a prestiži cíle (Ravenstein 1885). Populace se nemění: úbytek doplní přirozený
/// přírůstek. Přistěhovalci se místní řeč učí v dospělosti.
fn migrate(world: &mut World, edit: &Edits) -> Result<(), String> {
    let mut inflow = vec![0.0; world.groups.len()];
    for group in world.group_ids() {
        let g = group.index();
        if world.groups.written[g] || world.groups.domain[g] == Domain::Public {
            continue;
        }
        let targets: Vec<(GroupId, f64)> = neighbors(world, group)
            .into_iter()
            .filter(|(t, _)| {
                !world.groups.written[t.index()] && world.groups.domain[t.index()] == Domain::Home
            })
            .map(|(t, link)| {
                (
                    t,
                    link.strength
                        * f64::from(world.groups.population[t.index()])
                        * world.groups.prestige[t.index()],
                )
            })
            .collect();
        let total: f64 = targets.iter().map(|t| t.1).sum();
        if total <= 0.0 {
            continue;
        }
        let leaving = world.society.migration * f64::from(world.groups.population[g]);
        for (target, weight) in targets {
            inflow[target.index()] += leaving * weight / total;
        }
    }
    for group in world.group_ids() {
        let g = group.index();
        if !world.groups.written[g] && world.groups.domain[g] == Domain::Home {
            let value = (inflow[g] / f64::from(world.groups.population[g])).min(1.0);
            edit.set_group(world, group, Field::Immigration(value))?;
        }
    }
    Ok(())
}

/// Podíl mluvčích cílového jazyka mezi lidmi, se kterými komunita mluví.
///
/// Počítá se komunita sama a její sousedé vážení silou vazby. Elita uprostřed poddaných
/// tak slyší jazyk většiny, i když ho v ní zatím mluví málokdo.
pub fn demographic_share(world: &World, source: GroupId, target: GroupId) -> f64 {
    let language = world.groups.main_code(target).language;
    let mut weights: Vec<(GroupId, f64)> = vec![(source, 1.0), (target, 1.0)];
    for member in [source, target] {
        for (other, link) in neighbors(world, member) {
            if other != source && other != target {
                weights.push((other, link.strength));
            }
        }
    }
    // Podle jména skupiny, při shodě větší váha dřív (první výskyt vyhrává).
    weights.sort_by(|a, b| {
        world
            .group_name(a.0)
            .cmp(world.group_name(b.0))
            .then(b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal))
    });
    let (mut speakers, mut total) = (0.0, 0.0);
    let mut previous: Option<GroupId> = None;
    for (group, weight) in weights {
        if previous == Some(group) {
            continue;
        }
        previous = Some(group);
        if world.groups.written[group.index()] {
            continue;
        }
        let people = weight * f64::from(world.groups.population[group.index()]);
        total += people;
        if world.groups.main_code(group).language == language {
            speakers += people;
        }
    }
    if total > 0.0 {
        speakers / total
    } else {
        0.0
    }
}

/// Školní docházka skupiny v jejím vlastním jazyce (0, když škola učí cizí normu).
pub fn own_schooling(world: &World, group: GroupId) -> f64 {
    let g = group.index();
    let standard = world.groups.standard[g];
    if standard.is_none()
        || !world.groups.contains(standard)
        || world.groups.main_code(standard).language != world.groups.main_code(group).language
    {
        return 0.0;
    }
    world.groups.schooling[g]
}

fn alive_named(world: &World, name: &str) -> Option<GroupId> {
    world
        .registry
        .groups
        .get(name)
        .map(GroupId)
        .filter(|g| world.groups.contains(*g))
}

fn community_of(world: &World, group: GroupId) -> GroupId {
    let c = world.groups.community[group.index()];
    if c.is_none() {
        group
    } else {
        c
    }
}

/// Přirozený tah veřejného jazyka domů u elity bez patrona (dok. 33): domácí jazyk elity má mezi
/// lidmi, se kterými mluví, podíl pod `child_threshold` a elita není prestižnější než veřejný
/// jazyk okolí (prestiž ztratí v `polity::release`). Přejde i bez politiky státu (zrcadlo pravidla
/// ostrůvku v `shift`); jinak 0.
fn pocket_pull(world: &World, public: GroupId, home: GroupId) -> f64 {
    let (p, h) = (public.index(), home.index());
    // Jen elita (posádka, šlechta): ostrůvky starousedlíků i enklávy osadníků přežívají staletí
    // (bretonština, lužická srbština, sedmihradští Sasové); plné pohlcení všech menšin pod
    // `child_threshold` smetlo i ostrůvky (`m8::ostruvky` 0).
    if !world.groups.elite[h]
        || world.groups.preserved[h]
        || world.groups.domain[h] != Domain::Home
        || world.groups.main_code(public).language == world.groups.main_code(home).language
    {
        // Vysoká varieta téhož jazyka (diglosie) domácí řeč nenahrazuje.
        return 0.0;
    }
    let status = world.groups.prestige[p] / (world.groups.prestige[p] + world.groups.prestige[h]);
    let own = 1.0 - demographic_share(world, home, public);
    if own < world.params.child_threshold && status >= 0.5 - 1e-12 {
        1.0
    } else {
        0.0
    }
}

/// Veřejný kód proniká domů: dvojjazyčné rodiny s ním vychovávají děti.
///
/// Za generaci přejde podíl `home_pull × status × dvojjazyčnost^1,31` domácnosti, zpomalený
/// loajalitou komunity a školou ve vlastním jazyce. Přešlé rodiny tvoří domácí skupinu
/// cílového jazyka, kterou pak dál vede [`shift`].
#[allow(clippy::too_many_arguments)]
fn nativize(
    world: &mut World,
    public: GroupId,
    home: GroupId,
    pull: f64,
    renewal: f64,
    tick: u32,
    year: f64,
    history: &mut History,
    edit: &Edits,
) -> Result<bool, String> {
    let params = world.params.clone();
    let (p, h) = (public.index(), home.index());
    if world.groups.preserved[h] {
        return Ok(false);
    }
    let status = world.groups.prestige[p] / (world.groups.prestige[p] + world.groups.prestige[h]);
    let bilingual =
        (f64::from(world.groups.population[p]) / f64::from(world.groups.population[h])).min(1.0);
    let home_population = f64::from(world.groups.population[h]);
    let mut moving = home_population
        * renewal
        * params.shift_rate
        * pull
        * (1.0 - world.groups.loyalty[h])
        * status
        * bilingual.powf(params.shift_exponent)
        * (1.0 - own_schooling(world, home));
    moving = moving.min(home_population - 1.0);
    let language = world.groups.main_code(public).language;
    let language_name = world.registry.languages.name(language.0).to_owned();
    let community = community_of(world, home);
    // Domácí skupina cílového jazyka v komunitě vzniká jen jako přechod (`>jazyk`) nebo
    // pronikáním domů (`:home`).
    let home_name = world.group_name(home).to_owned();
    let existing = [
        format!("{home_name}>{language_name}"),
        format!("{home_name}>{language_name}:home"),
    ]
    .iter()
    .filter_map(|name| alive_named(world, name))
    .find(|&other| {
        let o = other.index();
        world.groups.community[o] == community
            && world.groups.domain[o] == Domain::Home
            && world.groups.main_code(other).language == language
            && world.groups.main_code(other).l1_source == home
    });
    if let Some(target) = existing {
        let population = f64::from(world.groups.population[target.index()]) + moving;
        edit.set_group(
            world,
            target,
            Field::Population(1.max(py_round(population)) as u32),
        )?;
        edit.set_group(
            world,
            home,
            Field::Population(1.max(py_round(home_population - moving)) as u32),
        )?;
        return Ok(false);
    }
    if moving < LAST_SPEAKERS {
        return Ok(false);
    }
    let created_name = format!("{home_name}>{language_name}:home");
    // Kód nové skupiny je větev hlavního kódu veřejné skupiny.
    let fields = [
        Field::GenerationYears(world.groups.generation_years[h]),
        Field::Prestige(world.groups.prestige[p]),
        Field::Openness(world.groups.openness[p]),
        Field::Community(community),
        Field::Loyalty(world.groups.loyalty[h]),
        Field::HomePull(world.groups.home_pull[p]),
        Field::Standard(world.groups.standard[p]),
        Field::Literacy(world.groups.literacy[p]),
        Field::Schooling(world.groups.schooling[p]),
    ];
    let territory = world.groups.territory[h];
    let created = edit.add_group(
        world,
        &created_name,
        territory,
        1.max(py_round(moving)) as u32,
        public,
        false,
        &fields,
    )?;
    edit.set_code(world, created, CodeChange::learned_from(home, 1.0))?;
    edit.set_group(
        world,
        home,
        Field::Population(1.max(py_round(home_population - moving)) as u32),
    )?;
    for (target, link) in neighbors(world, public) {
        if target == home {
            continue;
        }
        edit.connect(world, created, target, link.strength, link.kind)?;
        // Vazba převzala sílu oslabenou hranicí; zapamatuje si i násobek.
        if let Some(&factor) = world.society.border_factors.get(&(public, target)) {
            edit.set_border_factor(world, created, target, Some(factor))?;
            edit.set_border_factor(world, target, created, Some(factor))?;
        }
    }
    if let Some(&model) = world.society.prestige_mirror.get(&public) {
        edit.set_prestige_mirror(world, created, model)?;
    }
    edit.connect(world, created, public, 0.8, LinkKind::Strong)?;
    edit.connect(world, created, home, 0.8, LinkKind::Strong)?;
    history.record(
        "nativization",
        tick,
        year,
        json!({
            "group": home_name, "into": created_name, "language": language_name,
            "population": world.groups.population[created.index()],
        }),
    );
    Ok(true)
}

/// Mluvčí skupiny `source` přecházejí na kód skupiny `target`.
///
/// Abrams & Strogatz (2003): za generaci přejde podíl `status × podíl^1,31`, kde status plyne
/// z prestiže a podíl je demografie ([`demographic_share`]). Loajalita komunity přechod
/// zpomalí. Přechod, který začal tlakem státu nebo obrozením (`home_pull` > 0), je
/// obousměrný: rodiny se vracejí ke starému jazyku podle jeho statusu a demografie,
/// tempem obrozeneckého hnutí (`revival`) a školy ve vlastním jazyce.
#[allow(clippy::too_many_arguments)]
fn shift(
    world: &mut World,
    target: GroupId,
    source: GroupId,
    renewal: f64,
    tick: u32,
    year: f64,
    history: &mut History,
    edit: &Edits,
) -> Result<bool, String> {
    let params = world.params.clone();
    let (s, t) = (source.index(), target.index());
    let source_population = f64::from(world.groups.population[s]);
    let target_population_now = f64::from(world.groups.population[t]);
    let total = source_population + target_population_now;
    let status = world.groups.prestige[t] / (world.groups.prestige[t] + world.groups.prestige[s]);
    let driven = world.groups.home_pull[t] > 0.0;
    let resist = if driven {
        (world.groups.revival[s] + own_schooling(world, source)).min(1.0)
    } else {
        0.0
    };
    let source_language = world
        .registry
        .languages
        .name(world.groups.main_code(source).language.0)
        .to_owned();
    let target_language = world
        .registry
        .languages
        .name(world.groups.main_code(target).language.0)
        .to_owned();
    let (mut moving, mut births, mut back) = (0.0f64, 0.0f64, 0.0f64);
    if !world.groups.preserved[s] {
        let share = demographic_share(world, source, target);
        // Přechod začatý tlakem státu nebo obrozením jde tempem politiky či hnutí; škola ve
        // vlastním jazyce ho brzdí, škola v cílovém jazyce urychlí.
        let pace = if driven {
            world.groups.home_pull[t]
                * (1.0 - own_schooling(world, source))
                * (1.0 + own_schooling(world, target))
        } else {
            1.0
        };
        // Loajalita brzdí odchod od jazyka, ne návrat k němu (obrozený kód).
        let brake = if world.groups.revival[t] == 0.0 {
            1.0 - world.groups.loyalty[s]
        } else {
            1.0
        };
        moving = source_population
            * renewal
            * params.shift_rate
            * pace
            * brake
            * status
            * share.powf(params.shift_exponent);
        if source_population / total < params.child_threshold && resist == 0.0 {
            // Děti se starý kód už neučí: rodí se do nového.
            if world.groups.transmitted[s] {
                edit.set_group(world, source, Field::Transmitted(false))?;
                history.record(
                    "transmission_stopped",
                    tick,
                    year,
                    json!({"group": world.group_name(source), "language": source_language}),
                );
            }
            births = source_population * renewal;
        }
        moving = moving.min(source_population - births);
    }
    // Ostrůvek (dok. 27): novým jazykem mluví mezi lidmi, se kterými skupina mluví (i sousedé),
    // jen malá menšina (pod `child_threshold`), netáhne ho žádná politika a není prestižnější
    // než jazyk okolí: děti se rodí do jazyka většiny (zrcadlo pravidla pro mizející starý
    // jazyk výše). Elita uprostřed poddaných ostrůvkem není: jazyk poddaných ji obklopuje.
    if resist == 0.0
        && !world.groups.preserved[t]
        && world.groups.home_pull[t] < POLICY_ACTIVE
        && status <= 0.5 + 1e-12
        && demographic_share(world, source, target) < params.child_threshold
    {
        back =
            (back + target_population_now * renewal).min(target_population_now + moving + births);
    }
    // Zpětný tok podle Abramse a Strogatze (2003): děti mluvčích nového jazyka uprostřed
    // většiny starého převezmou starý, tempem politiky, dokud ji stát táhne (dok. 27). Bez něj
    // drobné ostrůvky (latinské rodiny v řecké vesnici) vydrží věčně.
    if resist == 0.0 && params.shift_return > 0.0 && world.groups.transmitted[s] {
        let pace = if driven {
            world.groups.home_pull[t]
        } else {
            1.0
        };
        back = target_population_now
            * renewal
            * params.shift_rate
            * pace
            * params.shift_return
            * (1.0 - status)
            * demographic_share(world, target, source).powf(params.shift_exponent);
        back = back.min(target_population_now + moving + births);
    }
    if resist > 0.0 {
        if !world.groups.transmitted[s] {
            edit.set_group(world, source, Field::Transmitted(true))?;
            history.record(
                "transmission_resumed",
                tick,
                year,
                json!({"group": world.group_name(source), "language": source_language}),
            );
        }
        back = target_population_now
            * renewal
            * params.shift_rate
            * resist
            * (1.0 - status)
            * demographic_share(world, target, source).powf(params.shift_exponent);
        back = back.min(target_population_now + moving + births);
    }
    let learners =
        world.groups.main_code(target).l2_share * target_population_now * (1.0 - renewal) + moving;
    let remaining = source_population - moving - births + back;
    let target_population = target_population_now + moving + births - back;
    if target_population < LAST_SPEAKERS {
        // Všichni se vrátili ke starému jazyku.
        edit.set_group(
            world,
            source,
            Field::Population(1.max(py_round(remaining + target_population)) as u32),
        )?;
        let target_name = world.group_name(target).to_owned();
        let source_name = world.group_name(source).to_owned();
        edit.remove_group(world, target)?;
        history.record(
            "revival",
            tick,
            year,
            json!({
                "group": source_name, "left": target_name,
                "language": source_language, "from_language": target_language,
            }),
        );
        return Ok(true);
    }
    edit.set_code(
        world,
        target,
        CodeChange::l2_share((learners / target_population).min(1.0)),
    )?;
    edit.set_group(
        world,
        target,
        Field::Population(1.max(py_round(target_population)) as u32),
    )?;
    if remaining < LAST_SPEAKERS {
        let source_name = world.group_name(source).to_owned();
        let target_name = world.group_name(target).to_owned();
        let source_openness = world.groups.openness[s];
        edit.remove_group(world, source)?;
        // Veřejná dvojjazyčnost zaniká se starým jazykem: jeho mluvčí už cílový kód mají doma.
        for other in world.group_ids() {
            let o = other.index();
            if world.groups.domain[o] == Domain::Public
                && world.groups.main_code(other).l1_source == source
                && world.groups.home_pull[o] > 0.0
            {
                edit.remove_group(world, other)?;
            }
        }
        edit.set_code(
            world,
            target,
            CodeChange {
                l1_source: Some(GroupId::NONE),
                ..CodeChange::default()
            },
        )?;
        // Komunita už mluví novým kódem od dětství: je to obyčejná skupina se svou dřívější
        // otevřeností.
        edit.set_group(world, target, Field::Openness(source_openness))?;
        history.record(
            "language_shift",
            tick,
            year,
            json!({
                "group": source_name, "into": target_name,
                "language": source_language, "target_language": target_language,
            }),
        );
        return Ok(true);
    }
    edit.set_group(
        world,
        source,
        Field::Population(1.max(py_round(remaining)) as u32),
    )?;
    Ok(false)
}
