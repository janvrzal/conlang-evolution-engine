//! Generátor jmen míst podle kraje a epochy (pro aplikaci).
//!
//! Jméno vznikne v kraji v zadaném roce: složí se z tehdejších slov převládající linie kraje
//! (dobový snímek [`Epoch`](super::Epoch) z nejbližšího předchozího pozorování) podle tradice,
//! kterou určují tehdejší podmínky kraje (stát, písmo, město). Pak se vede do pozdějšího roku:
//! projde hláskovými změnami, které od té doby převládly v řeči nositele, a když kraj přejde
//! na jiný jazyk, noví obyvatelé ho převezmou ve své podobě (substrát). Sídlo založené před
//! tisíci lety je proto kratší a méně průhledné než sídlo z minulého století a obvykle má
//! i jiný vzor.

use std::collections::BTreeSet;

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

use super::compose::{self, Adapted, Lexicon, PlaceConditions, Stored};
use super::{Epoch, NameState};
use crate::ids::ProcessId;
use crate::onomastics::romanize;
use crate::phonology::surface::{apply_local, ProcCache};
use crate::world::World;

/// Dotaz na generátor: kraj, rok vzniku, počet návrhů, do kterého roku jméno vést.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Query {
    pub region: String,
    pub year: f64,
    #[serde(default = "default_count")]
    pub count: usize,
    /// Do kterého roku jméno vést (`None` = poslední pozorování).
    #[serde(default)]
    pub until: Option<f64>,
    /// Město (jinak vesnice).
    #[serde(default = "default_urban")]
    pub urban: bool,
    /// Číslo pokusu: jiný pokus dá jiné návrhy (stejný pokus vždy stejné).
    #[serde(default)]
    pub attempt: u64,
    /// `place` (výchozí, jména sídel), nebo `person` (jména osob podle tradice té doby).
    #[serde(default = "default_kind")]
    pub kind: String,
}

fn default_kind() -> String {
    "place".into()
}

fn default_count() -> usize {
    5
}

fn default_urban() -> bool {
    true
}

struct Track {
    form: Vec<i32>,
    language: String,
    lineage: String,
    carrier: String,
    rule: u8,
    applied: BTreeSet<u32>,
    timeline: Vec<Value>,
}

impl NameState {
    fn year_of(&self, tick: u32) -> f64 {
        self.start_year + f64::from(tick) * self.dt
    }

    /// Hláskové změny nositele s tikem do `until_tick`, které jméno ještě nemá.
    fn evolve(
        &self,
        world: &World,
        track: &mut Track,
        until_tick: u32,
        not_before: f64,
        cache: &mut ProcCache,
    ) {
        let Some(table) = world.table.as_ref() else {
            return;
        };
        let Some(log) = self.logs.get(&track.carrier) else {
            return;
        };
        for &(tick, process) in &log.entries {
            if tick > until_tick || track.applied.contains(&process) {
                continue;
            }
            track.applied.insert(process);
            let Some(changed) =
                apply_local(world, cache, ProcessId(process), &track.form, track.rule)
            else {
                continue;
            };
            if changed.is_empty() || changed == track.form {
                continue;
            }
            track.form = changed;
            let ipa = table.render(&track.form);
            let label = world
                .process(ProcessId(process))
                .map_or_else(String::new, |d| d.label.clone());
            track.timeline.push(json!({
                "year": self.year_of(tick).max(not_before), "ipa": ipa, "name": romanize(&ipa),
                "cause": format!("sound: {label}"), "language": track.language,
            }));
        }
    }

    fn epoch_at(&self, year: f64) -> Option<usize> {
        let index = self.epochs.iter().rposition(|e| e.year <= year + 1e-9);
        index.or(if self.epochs.is_empty() {
            None
        } else {
            Some(0)
        })
    }

    /// Návrhy jmen sídla založeného v kraji `query.region` v roce `query.year` a jejich vývoj.
    pub fn generate(&self, world: &World, query: &Query) -> Result<Value, String> {
        match query.kind.as_str() {
            "place" => {}
            "person" => return self.generate_people(world, query),
            other => return Err(format!("neznámý druh jména '{other}' (place, person)")),
        }
        let table = world.table.as_ref().ok_or("svět nemá tabulku hlásek")?;
        let is_vowel = |s: i32| table.is_vowel(s);
        let render = |f: &[i32]| table.render(f);
        let start = self
            .epoch_at(query.year)
            .ok_or("běh zatím nemá žádné pozorování (generátor potřebuje dobová slova)")?;
        let epoch: &Epoch = &self.epochs[start];
        let region = epoch
            .regions
            .get(&query.region)
            .ok_or_else(|| format!("neznámý kraj '{}'", query.region))?;
        let lineage = region.lineage.clone().ok_or_else(|| {
            format!(
                "v kraji '{}' v roce {} nikdo nežil",
                query.region, epoch.year
            )
        })?;
        let speech = &epoch.lineages[&lineage];
        let until = query
            .until
            .unwrap_or_else(|| self.epochs.last().map_or(query.year, |e| e.year));
        let until_tick = ((until - self.start_year) / self.dt).floor().max(0.0) as u32;
        let state = region.state.as_ref().and_then(|id| {
            let index = *self.current.get(&format!("state:{id}"))?;
            let record = &self.records[index];
            let ipa = record.ipa_at(query.year)?;
            let form = table.parse(ipa).ok()?;
            let form = if record.language == speech.language {
                form
            } else {
                crate::contact::adapt(world, &speech.inventory, &form)
            };
            Some((form, romanize(ipa), record.id.clone()))
        });
        let conditions = PlaceConditions {
            region: false,
            urban: query.urban,
            terrain: region.terrain.clone(),
            state,
            literate: region.literate,
            origin: None,
            founder: None,
        };
        let tradition = conditions.tradition().name();
        let lexicon = Stored {
            forms: &speech.forms,
            head_initial: speech.head_initial,
        };
        let mut cache = ProcCache::new();
        let mut out = Vec::new();
        let mut seen: BTreeSet<String> = BTreeSet::new();
        let mut index = 0_u64;
        while out.len() < query.count && index < 8 * query.count as u64 + 8 {
            let h = compose::hash(
                world.seed,
                &[
                    "generate",
                    &query.region,
                    &format!("{}", query.year),
                    if query.urban { "town" } else { "village" },
                ],
                index + 1000 * query.attempt,
            );
            index += 1;
            let composed = compose::place(&lexicon, &conditions, h, &is_vowel, &render);
            if composed.form.is_empty() {
                continue;
            }
            let founded_ipa = render(&composed.form);
            let mut track = Track {
                form: composed.form.clone(),
                language: speech.language.clone(),
                lineage: lineage.clone(),
                carrier: speech.carrier.clone(),
                rule: speech.rule,
                applied: self
                    .logs
                    .get(&speech.carrier)
                    .map(|l| {
                        l.entries
                            .iter()
                            .filter(|e| e.0 <= epoch.tick)
                            .map(|e| e.1)
                            .collect()
                    })
                    .unwrap_or_default(),
                timeline: vec![json!({
                    "year": query.year, "ipa": founded_ipa, "name": romanize(&founded_ipa),
                    "cause": "founded", "language": speech.language,
                })],
            };
            let mut previous_tick = epoch.tick;
            for later in &self.epochs[start + 1..] {
                if later.year > until + 1e-9 {
                    break;
                }
                self.evolve(world, &mut track, later.tick, query.year, &mut cache);
                previous_tick = later.tick;
                let Some(now) = later
                    .regions
                    .get(&query.region)
                    .and_then(|r| r.lineage.clone())
                else {
                    continue;
                };
                let Some(speakers) = later.lineages.get(&now) else {
                    continue;
                };
                if speakers.language != track.language {
                    // Kraj přešel na jiný jazyk: noví obyvatelé jméno převezmou po svém.
                    track.form = crate::contact::adapt(world, &speakers.inventory, &track.form);
                    let ipa = render(&track.form);
                    track.timeline.push(json!({
                        "year": later.year.max(query.year), "ipa": ipa, "name": romanize(&ipa),
                        "cause": format!("borrowed: {} → {}", track.language, speakers.language),
                        "language": speakers.language,
                    }));
                    track.language = speakers.language.clone();
                    track.applied = self
                        .logs
                        .get(&speakers.carrier)
                        .map(|l| {
                            l.entries
                                .iter()
                                .filter(|e| e.0 <= later.tick)
                                .map(|e| e.1)
                                .collect()
                        })
                        .unwrap_or_default();
                }
                track.lineage = now;
                track.carrier = speakers.carrier.clone();
                track.rule = speakers.rule;
            }
            if until_tick > previous_tick {
                self.evolve(world, &mut track, until_tick, query.year, &mut cache);
            }
            let ipa = render(&track.form);
            let name = romanize(&ipa);
            if !seen.insert(name.clone()) {
                continue;
            }
            out.push(json!({
                "name": name,
                "ipa": ipa,
                "language": track.language,
                "lineage": track.lineage,
                "founded": {
                    "year": query.year, "name": romanize(&founded_ipa), "ipa": founded_ipa,
                    "language": speech.language, "lineage": lineage, "tradition": tradition,
                    "pattern": composed.pattern, "meaning": composed.meaning, "recipe": composed.recipe,
                    "words_from": epoch.year,
                },
                "timeline": track.timeline,
            }));
        }
        Ok(json!({
            "region": query.region,
            "year": query.year,
            "until": until,
            "urban": query.urban,
            "tradition": tradition,
            "names": out,
        }))
    }

    /// Jména osob narozených v kraji v roce `query.year`: tradice komunity v tom roce, tehdejší
    /// slova a u dvorských a kalendářních jmen slova úředního (liturgického) jazyka státu.
    pub fn generate_people(&self, world: &World, query: &Query) -> Result<Value, String> {
        let table = world.table.as_ref().ok_or("svět nemá tabulku hlásek")?;
        let is_vowel = |s: i32| table.is_vowel(s);
        let render = |f: &[i32]| table.render(f);
        let start = self
            .epoch_at(query.year)
            .ok_or("běh zatím nemá žádné pozorování (generátor potřebuje dobová slova)")?;
        let epoch = &self.epochs[start];
        let region = epoch
            .regions
            .get(&query.region)
            .ok_or_else(|| format!("neznámý kraj '{}'", query.region))?;
        let lineage = region.lineage.clone().ok_or_else(|| {
            format!(
                "v kraji '{}' v roce {} nikdo nežil",
                query.region, epoch.year
            )
        })?;
        let speech = &epoch.lineages[&lineage];
        let community = super::lineage_object(&lineage);
        let step = self
            .tradition_at(&community, query.year)
            .or_else(|| self.tradition_at(&format!("language:{}", speech.language), query.year))
            .cloned();
        let paradigm = step
            .as_ref()
            .map_or_else(|| "dithematic_ie".to_owned(), |s| s.paradigm.clone());
        let lexicon = Stored {
            forms: &speech.forms,
            head_initial: speech.head_initial,
        };
        let ruling = region
            .ruling
            .as_ref()
            .filter(|r| **r != lineage)
            .and_then(|r| epoch.lineages.get(r))
            .map(|l| Stored {
                forms: &l.forms,
                head_initial: l.head_initial,
            });
        let prestige = ruling.as_ref().map(|r| Adapted {
            inner: r,
            world,
            inventory: speech.inventory.clone(),
        });
        let origin = self
            .current
            .get(&format!("territory:{}", query.region))
            .and_then(|&i| self.records[i].ipa_at(query.year))
            .map(romanize);
        let mut out = Vec::new();
        let mut seen: BTreeSet<String> = BTreeSet::new();
        let mut index = 0_u64;
        while out.len() < query.count && index < 8 * query.count as u64 + 8 {
            let h = compose::hash(
                world.seed,
                &["generate-person", &query.region, &format!("{}", query.year)],
                index + 1000 * query.attempt,
            );
            index += 1;
            let name = super::persons::person_name(
                &paradigm,
                &lexicon,
                prestige.as_ref().map(|p| p as &dyn Lexicon),
                origin.as_deref(),
                h,
                &is_vowel,
                &render,
            );
            let full = name.full(&render);
            if name.given().is_empty() || !seen.insert(full.clone()) {
                continue;
            }
            out.push(json!({
                "name": full,
                "ipa": name.ipa(&render),
                "given": romanize(&render(name.given())),
                "house": name.house().map(|h| romanize(&render(h))),
                "paradigm": name.paradigm,
                "meaning": name.meaning,
                "recipe": name.recipe,
            }));
        }
        let label = crate::onomastics::catalog()
            .anthroponym_paradigms
            .get(&paradigm)
            .map(|p| p.label_cs.clone());
        Ok(json!({
            "region": query.region,
            "year": query.year,
            "kind": "person",
            "language": speech.language,
            "lineage": lineage,
            "tradition": paradigm,
            "tradition_label": label,
            "tradition_since": step.as_ref().map(|s| s.year),
            "tradition_cause": step.as_ref().map(|s| s.cause.clone()),
            "tradition_source": step.as_ref().and_then(|s| s.source.clone()),
            "words_from": epoch.year,
            "names": out,
        }))
    }
}
