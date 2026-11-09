//! Skládání nového jména z dobových slov: tradice podle podmínek a vzory jmen.
//!
//! Skládání čte slova přes [`Lexicon`]: buď živý svět (dnešní povrchové tvary skupiny,
//! [`Live`]), nebo uložený dobový snímek ([`Stored`], generátor jmen podle epochy). Vzory
//! a zásoby pojmů jsou v katalogu `v2_onomastics.json`; tady se jen vybírá podle podmínek
//! v roce vzniku, ne podle letopočtu.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

use crate::ids::{ConceptId, GroupId};
use crate::naming::syllables;
use crate::onomastics::{catalog, smooth_compound, smooth_seam};
use crate::rng::{stable_int, Part as HashPart};
use crate::world::World;

/// Slova, ze kterých se jméno skládá.
pub trait Lexicon {
    /// Tvar pojmu (prázdný, když ho jazyk nemá).
    fn form(&self, concept: &str) -> Vec<i32>;
    /// Řídící člen před závislým (VO jazyky): „Hora Bílá“ místo „Bílá Hora“.
    fn head_initial(&self) -> bool;
}

/// Dnešní povrchové tvary skupiny ve světě.
pub struct Live<'a> {
    pub world: &'a World,
    pub group: GroupId,
}

impl Lexicon for Live<'_> {
    fn form(&self, concept: &str) -> Vec<i32> {
        surface_concept(self.world, self.group, concept)
    }

    fn head_initial(&self) -> bool {
        head_initial(self.world, self.group)
    }
}

/// Uložená dobová slova (pojem → tvar).
pub struct Stored<'a> {
    pub forms: &'a BTreeMap<String, Vec<i32>>,
    pub head_initial: bool,
}

impl Lexicon for Stored<'_> {
    fn form(&self, concept: &str) -> Vec<i32> {
        self.forms.get(concept).cloned().unwrap_or_default()
    }

    fn head_initial(&self) -> bool {
        self.head_initial
    }
}

/// Slova cizího (prestižního) jazyka přejatá do domácí řeči: adaptace na domácí hlásky.
pub struct Adapted<'a> {
    pub inner: &'a dyn Lexicon,
    pub world: &'a World,
    pub inventory: Vec<i32>,
}

impl Lexicon for Adapted<'_> {
    fn form(&self, concept: &str) -> Vec<i32> {
        let form = self.inner.form(concept);
        if self.inventory.is_empty() {
            form
        } else {
            crate::contact::adapt(self.world, &self.inventory, &form)
        }
    }

    fn head_initial(&self) -> bool {
        self.inner.head_initial()
    }
}

/// Povrchové tvary pojmů skupiny najednou (dobový snímek); prázdný tvar = pojem chybí.
pub fn surface_concepts(world: &World, group: GroupId, concepts: &[String]) -> Vec<Vec<i32>> {
    let code = world.groups.main_code(group);
    let roots: Vec<crate::ids::MorphemeId> = concepts
        .iter()
        .map(|c| {
            world
                .registry
                .concepts
                .get(c)
                .map_or(crate::ids::MorphemeId::NONE, |id| {
                    world.dominant_or_plural_root(group, ConceptId(id))
                })
        })
        .collect();
    let native: Vec<crate::ids::MorphemeId> = roots
        .iter()
        .copied()
        .filter(|&r| {
            !r.is_none()
                && (code.forms.get(r).is_some()
                    || world.morphemes.language[r.index()] == code.language)
        })
        .collect();
    let mut surfaced: BTreeMap<crate::ids::MorphemeId, Vec<i32>> = BTreeMap::new();
    if let Ok(forms) = crate::phonology::surface::surface_many(world, group, &native) {
        surfaced = native.into_iter().zip(forms).collect();
    }
    roots
        .into_iter()
        .map(|r| {
            if r.is_none() {
                Vec::new()
            } else if let Some(form) = surfaced.get(&r) {
                form.clone()
            } else {
                world.adapted_form_of(group, r)
            }
        })
        .collect()
}

/// Povrchový tvar převládajícího slova pojmu ve skupině (jak ho dnes vyslovuje).
pub fn surface_concept(world: &World, group: GroupId, concept: &str) -> Vec<i32> {
    let Some(id) = world.registry.concepts.get(concept).map(ConceptId) else {
        return Vec::new();
    };
    let root = world.dominant_or_plural_root(group, id);
    if root.is_none() {
        return Vec::new();
    }
    let code = world.groups.main_code(group);
    if code.forms.get(root).is_some() || world.morphemes.language[root.index()] == code.language {
        if let Ok(form) = crate::phonology::surface::surface(world, group, root) {
            return form;
        }
    }
    world.adapted_form_of(group, root)
}

/// Má skupina převládající slovosled s přísudkem před předmětem (VO)?
pub fn head_initial(world: &World, group: GroupId) -> bool {
    use crate::model::repertoire::Payload;
    let Some(number) = world.registry.variables.get("construction:ORDER") else {
        return false;
    };
    let variable = crate::ids::VariableId(number);
    if variable.index() >= world.variables.len() {
        return false;
    }
    let Some((variant, _)) = world.dominant(group, variable) else {
        return false;
    };
    match &world.variants.payload[variant.index()] {
        Payload::Construction(c) => c
            .order
            .as_deref()
            .is_some_and(|o| matches!(o, "SVO" | "VSO" | "VOS")),
        _ => false,
    }
}

/// Všechny pojmy, ze kterých modul jmen skládá (zásoby katalogu a pomocná slova).
pub fn naming_concepts() -> Vec<String> {
    let mut found: Vec<String> = catalog()
        .semantic_pools
        .values()
        .flatten()
        .cloned()
        .collect();
    found.extend(
        [
            "person", "language", "people", "earth", "land", "new", "house", "town", "child",
            "king", "law", "trade", "village",
        ]
        .map(str::to_owned),
    );
    found.sort();
    found.dedup();
    found
}

/// Česká glosa pojmu pro čtenáře.
pub fn gloss(concept: &str) -> String {
    catalog()
        .glosses_cs
        .get(concept)
        .cloned()
        .unwrap_or_else(|| concept.to_owned())
}

/// Část receptu jména: pojem, jiné jméno, nebo osobní jméno.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct RecipePart {
    /// Pojem (`river`); `None` u části převzaté z jiného jména.
    pub concept: Option<String>,
    /// Česká glosa nebo popis části.
    pub gloss: String,
    /// Tvar části v roce vzniku (IPA, před zkrácením ve složenině).
    pub ipa: String,
    /// Záznam jména, ze kterého část pochází (ID).
    pub name: Option<String>,
}

/// Výsledek skládání: tvar, vzor, význam pro čtenáře a recept.
#[derive(Clone, Debug, Default)]
pub struct Composed {
    pub form: Vec<i32>,
    pub pattern: String,
    pub meaning: String,
    pub recipe: Vec<RecipePart>,
}

/// Tradice pojmenování podle podmínek v roce vzniku (ne podle letopočtu).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Tradition {
    /// Bez státu a písma: jména podle krajiny, vody a cest.
    Archaic,
    /// Ve státě: sídelní formanty, zakladatelé, vladaři.
    State,
    /// Ve státě s písmem nebo školou: posvátná a úřední jména, upomínky na stát.
    Literate,
}

impl Tradition {
    pub fn name(self) -> &'static str {
        match self {
            Tradition::Archaic => "archaic",
            Tradition::State => "state",
            Tradition::Literate => "literate",
        }
    }
}

/// Podmínky vzniku jména místa.
#[derive(Clone, Debug, Default)]
pub struct PlaceConditions {
    pub region: bool,
    pub urban: bool,
    pub terrain: String,
    /// Jméno státu v řeči zakladatelů (pro upomínková jména) a jeho ID záznamu.
    pub state: Option<(Vec<i32>, String, String)>,
    pub literate: bool,
    /// Sídlo založené přesídlením: jméno mateřského sídla v řeči osadníků, gloss, ID záznamu.
    pub origin: Option<(Vec<i32>, String, String)>,
    /// Zakladatel podle tradice osobních jmen komunity: rodné jméno a celé jméno (latinkou).
    pub founder: Option<(Vec<i32>, String)>,
}

impl PlaceConditions {
    pub fn tradition(&self) -> Tradition {
        match (&self.state, self.literate) {
            (Some(_), true) => Tradition::Literate,
            (Some(_), false) => Tradition::State,
            (None, true) => Tradition::Literate,
            (None, false) => Tradition::Archaic,
        }
    }
}

/// Vážený výběr podle čísla z hashe.
pub fn choose<'a>(hash: u64, options: &[(&'a str, f64)]) -> &'a str {
    let total: f64 = options.iter().map(|o| o.1.max(0.0)).sum();
    if total <= 0.0 {
        return options.first().map_or("", |o| o.0);
    }
    let mut point = (hash % 1_000_000) as f64 / 1_000_000.0 * total;
    for (name, weight) in options {
        let weight = weight.max(0.0);
        if point < weight {
            return name;
        }
        point -= weight;
    }
    options.last().map_or("", |o| o.0)
}

/// Číslo pro rozhodnutí: semínko světa a klíč.
pub fn hash(seed: i64, parts: &[&str], extra: u64) -> u64 {
    let mut all = vec![HashPart::Str("names"), HashPart::Int(seed)];
    all.extend(parts.iter().map(|p| HashPart::Str(p)));
    all.push(HashPart::Uint(extra));
    stable_int(&all)
}

fn pick(pool: &str, hash: u64, salt: u64) -> String {
    let Some(items) = catalog().semantic_pools.get(pool) else {
        return "stone".into();
    };
    if items.is_empty() {
        return "stone".into();
    }
    let at = (hash.wrapping_add(salt.wrapping_mul(0x9E37_79B9_7F4A_7C15)) as usize) % items.len();
    items[at].clone()
}

fn first_syllable(form: &[i32], is_vowel: &dyn Fn(i32) -> bool) -> Vec<i32> {
    syllables(form, is_vowel)
        .into_iter()
        .next()
        .unwrap_or_else(|| form.to_vec())
}

/// Část receptu z pojmu.
fn part(
    lexicon: &dyn Lexicon,
    concept: &str,
    render: &dyn Fn(&[i32]) -> String,
) -> (Vec<i32>, RecipePart) {
    let form = lexicon.form(concept);
    let recipe = RecipePart {
        concept: Some(concept.to_owned()),
        gloss: gloss(concept),
        ipa: render(&form),
        name: None,
    };
    (form, recipe)
}

/// Složí závislý a řídící člen v pořadí jazyka.
fn pair(
    lexicon: &dyn Lexicon,
    modifier: Vec<i32>,
    head: Vec<i32>,
    is_vowel: &dyn Fn(i32) -> bool,
) -> Vec<i32> {
    if lexicon.head_initial() {
        smooth_compound(&[head, modifier], is_vowel)
    } else {
        smooth_compound(&[modifier, head], is_vowel)
    }
}

/// Osobní jméno ze dvou členů (dvoučlenné jméno jako Bolemír, Sigurd).
pub fn person(
    lexicon: &dyn Lexicon,
    hash: u64,
    is_vowel: &dyn Fn(i32) -> bool,
    render: &dyn Fn(&[i32]) -> String,
) -> Composed {
    let first = pick("heroic_first", hash, 11);
    let second = pick("heroic_second", hash, 12);
    let (a, ra) = part(lexicon, &first, render);
    let (b, rb) = part(lexicon, &second, render);
    let form = smooth_compound(&[a, b], is_vowel);
    Composed {
        form,
        pattern: "dithematic".into(),
        meaning: format!("{}-{}", gloss(&first), gloss(&second)),
        recipe: vec![ra, rb],
    }
}

/// Nové jméno místa podle tradice v roce vzniku. `attempt` mění volbu při kolizi jmen.
pub fn place(
    lexicon: &dyn Lexicon,
    conditions: &PlaceConditions,
    hash: u64,
    is_vowel: &dyn Fn(i32) -> bool,
    render: &dyn Fn(&[i32]) -> String,
) -> Composed {
    let tradition = conditions.tradition();
    let watery = conditions.urban || matches!(conditions.terrain.as_str(), "plain" | "island");
    let state = conditions.state.is_some();
    let mut options: Vec<(&str, f64)> = match tradition {
        Tradition::Archaic => vec![
            ("descriptive_terrain", 4.0),
            ("hydro_crossing", if watery { 2.0 } else { 0.5 }),
            ("habitative_formant", 1.0),
            ("eponymous_founder", 0.7),
        ],
        Tradition::State => vec![
            ("descriptive_terrain", 2.0),
            ("hydro_crossing", if watery { 1.5 } else { 0.3 }),
            ("habitative_formant", 3.0),
            ("eponymous_founder", 2.5),
            ("sacred_civic", if conditions.urban { 1.0 } else { 0.2 }),
        ],
        Tradition::Literate => vec![
            ("descriptive_terrain", 1.0),
            ("hydro_crossing", if watery { 1.0 } else { 0.2 }),
            ("habitative_formant", 2.0),
            ("eponymous_founder", 2.0),
            ("sacred_civic", 2.0),
            ("commemorative", if state { 1.5 } else { 0.0 }),
        ],
    };
    if conditions.origin.is_some() {
        options.push(("transfer", 4.0));
    }
    let pattern = choose(hash, &options).to_owned();
    let terrain_pool = if conditions.region {
        match conditions.terrain.as_str() {
            "hills" => "terrain_hills",
            "mountains" => "terrain_mountains",
            "island" => "terrain_island",
            _ => "terrain_plain",
        }
    } else if conditions.urban {
        "urban_heads"
    } else {
        "rural_heads"
    };
    let settlement_pool = if conditions.urban {
        "urban_heads"
    } else {
        "rural_heads"
    };
    let mut composed = match pattern.as_str() {
        "hydro_crossing" => {
            let head = pick("crossing_heads", hash, 1);
            let modifier = pick("hydro_heads", hash, 2);
            let (h, rh) = part(lexicon, &head, render);
            let (m, rm) = part(lexicon, &modifier, render);
            Composed {
                form: pair(lexicon, m, h, is_vowel),
                pattern: pattern.clone(),
                meaning: format!("{} {}", gloss(&modifier), gloss(&head)),
                recipe: vec![rm, rh],
            }
        }
        "habitative_formant" | "sacred_civic" => {
            let head = pick(settlement_pool, hash, 1);
            let pool = if pattern == "sacred_civic" {
                "sacred_civic"
            } else if tradition == Tradition::Archaic {
                "nature_stems"
            } else {
                "heroic_first"
            };
            let modifier = pick(pool, hash, 2);
            let (h, rh) = part(lexicon, &head, render);
            let (m, rm) = part(lexicon, &modifier, render);
            let h = first_syllable(&h, is_vowel);
            Composed {
                form: pair(lexicon, m, h, is_vowel),
                pattern: pattern.clone(),
                meaning: format!("{} {}", gloss(&modifier), gloss(&head)),
                recipe: vec![rm, rh],
            }
        }
        "eponymous_founder" => {
            let founder = match &conditions.founder {
                Some((form, full)) => Composed {
                    form: form.clone(),
                    pattern: "person".into(),
                    meaning: full.clone(),
                    recipe: Vec::new(),
                },
                None => person(lexicon, hash ^ 0x5151, is_vowel, render),
            };
            let head = pick(settlement_pool, hash, 1);
            let (h, rh) = part(lexicon, &head, render);
            let h = first_syllable(&h, is_vowel);
            let form = if lexicon.head_initial() {
                smooth_seam(&h, &founder.form, is_vowel)
            } else {
                smooth_seam(&founder.form, &h, is_vowel)
            };
            let founder_part = RecipePart {
                concept: None,
                gloss: format!("zakladatel „{}“", founder.meaning),
                ipa: render(&founder.form),
                name: None,
            };
            Composed {
                form,
                pattern: pattern.clone(),
                meaning: format!("{} zakladatele „{}“", gloss(&head), founder.meaning),
                recipe: vec![founder_part, rh],
            }
        }
        "commemorative" => {
            let (state_form, state_gloss, state_id) = conditions.state.clone().unwrap_or_default();
            let head = pick("urban_heads", hash, 1);
            let (h, rh) = part(lexicon, &head, render);
            let short = syllables(&state_form, is_vowel)
                .into_iter()
                .take(2)
                .flatten()
                .collect::<Vec<i32>>();
            let h = first_syllable(&h, is_vowel);
            Composed {
                form: pair(lexicon, short, h, is_vowel),
                pattern: pattern.clone(),
                meaning: format!("{} státu {}", gloss(&head), state_gloss),
                recipe: vec![
                    RecipePart {
                        concept: None,
                        gloss: format!("stát {state_gloss}"),
                        ipa: render(&state_form),
                        name: Some(state_id),
                    },
                    rh,
                ],
            }
        }
        "transfer" => {
            let (origin, origin_gloss, origin_id) = conditions.origin.clone().unwrap_or_default();
            let origin_part = RecipePart {
                concept: None,
                gloss: format!("mateřské sídlo {origin_gloss}"),
                ipa: render(&origin),
                name: Some(origin_id),
            };
            if hash % 2 == 0 {
                let (n, rn) = part(lexicon, "new", render);
                let n = first_syllable(&n, is_vowel);
                Composed {
                    form: pair(lexicon, n, origin, is_vowel),
                    pattern: "transfer_new".into(),
                    meaning: format!("Nový {origin_gloss}"),
                    recipe: vec![rn, origin_part],
                }
            } else {
                Composed {
                    form: origin,
                    pattern: "transfer".into(),
                    meaning: format!("přenesené jméno {origin_gloss}"),
                    recipe: vec![origin_part],
                }
            }
        }
        _ => {
            let head = pick(terrain_pool, hash, 1);
            let modifier = pick("modifiers", hash, 2);
            let (h, rh) = part(lexicon, &head, render);
            let (m, rm) = part(lexicon, &modifier, render);
            Composed {
                form: pair(lexicon, m, h, is_vowel),
                pattern: "descriptive_terrain".into(),
                meaning: format!("{} {}", gloss(&modifier), gloss(&head)),
                recipe: vec![rm, rh],
            }
        }
    };
    if composed.form.is_empty() {
        // Jazyk nemá některé slovo: jednoduché jméno podle krajiny.
        let head = pick(terrain_pool, hash, 7);
        let (h, rh) = part(lexicon, &head, render);
        composed = Composed {
            form: h,
            pattern: "descriptive_terrain".into(),
            meaning: gloss(&head),
            recipe: vec![rh],
        };
    }
    composed
}

/// Vlastní jméno lidí a jazyka ze slov receptu (`["person", "language"]`).
pub fn people(
    lexicon: &dyn Lexicon,
    concepts: &[String],
    is_vowel: &dyn Fn(i32) -> bool,
    render: &dyn Fn(&[i32]) -> String,
) -> Composed {
    let mut parts = Vec::new();
    let mut recipe = Vec::new();
    for concept in concepts {
        let (form, item) = part(lexicon, concept, render);
        if !form.is_empty() {
            parts.push(form);
            recipe.push(item);
        }
    }
    Composed {
        form: smooth_compound(&parts, is_vowel),
        pattern: "compound".into(),
        meaning: recipe
            .iter()
            .map(|r| r.gloss.as_str())
            .collect::<Vec<_>>()
            .join(" + "),
        recipe,
    }
}
