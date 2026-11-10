//! Osobní jména podle tradice pojmenování (paradigmata katalogu `v2_onomastics.json`).
//!
//! Tradice určuje, z jakých částí se jméno skládá (jméno při narození, jméno otce, rod, obřadní
//! jméno, přezdívka…); jazyk určuje slova a výslovnost ([`Lexicon`]). Jedna implementace slouží
//! záznamům osob v modulu jmen, generátoru osob podle epochy i vzorníku v `onomastics`.

use serde::{Deserialize, Serialize};

use super::compose::{gloss, Lexicon, RecipePart};
use crate::naming::syllables;
use crate::onomastics::{catalog, romanize, smooth_compound, smooth_seam};

/// Tradice bez institucí, ze kterých si prajazyk vybere, když ji autor nezadá.
pub const BASE_TRADITIONS: [&str; 5] = [
    "dithematic_ie",
    "genealogical_nisba",
    "clan_generational",
    "chrononymic_deed",
    "tria_nomina",
];

/// Část osobního jména: role (`given`, `byname`, `house`, `nisba`), tvar a oddělovače při zápisu.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct NamePart {
    pub role: String,
    pub form: Vec<i32>,
    pub prefix: String,
    pub suffix: String,
    /// Hotový zápis (část převzatá z jiného jména, třeba místo původu).
    pub text: Option<String>,
}

/// Osobní jméno: tradice, části, význam pro čtenáře a recept.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct PersonName {
    pub paradigm: String,
    pub parts: Vec<NamePart>,
    pub meaning: String,
    pub recipe: Vec<RecipePart>,
}

impl PersonName {
    /// Vlastní (rodné) jméno.
    pub fn given(&self) -> &[i32] {
        self.parts
            .iter()
            .find(|p| p.role == "given")
            .map_or(&[][..], |p| p.form.as_slice())
    }

    /// Jméno rodu nebo domu, pokud ho tradice má.
    pub fn house(&self) -> Option<&[i32]> {
        self.parts
            .iter()
            .find(|p| p.role == "house")
            .map(|p| p.form.as_slice())
    }

    /// Celé jméno v latince (`romanize` po částech).
    pub fn full(&self, render: &dyn Fn(&[i32]) -> String) -> String {
        self.parts
            .iter()
            .map(|p| {
                let text = p.text.clone().unwrap_or_else(|| romanize(&render(&p.form)));
                format!("{}{text}{}", p.prefix, p.suffix)
            })
            .collect::<String>()
            .trim()
            .to_owned()
    }

    /// Celé jméno v IPA (části oddělené mezerou).
    pub fn ipa(&self, render: &dyn Fn(&[i32]) -> String) -> String {
        self.parts
            .iter()
            .filter(|p| p.text.is_none())
            .map(|p| render(&p.form))
            .collect::<Vec<_>>()
            .join(" ")
    }
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

/// Skladatel jednoho jména: slova, zkracování a recept.
struct Builder<'a> {
    lexicon: &'a dyn Lexicon,
    prestige: &'a dyn Lexicon,
    is_vowel: &'a dyn Fn(i32) -> bool,
    render: &'a dyn Fn(&[i32]) -> String,
    recipe: Vec<RecipePart>,
}

impl Builder<'_> {
    fn word(&mut self, concept: &str, prestige: bool) -> Vec<i32> {
        let form = if prestige {
            self.prestige.form(concept)
        } else {
            self.lexicon.form(concept)
        };
        self.recipe.push(RecipePart {
            concept: Some(concept.to_owned()),
            gloss: if prestige {
                format!("{} (prestižní jazyk)", gloss(concept))
            } else {
                gloss(concept)
            },
            ipa: (self.render)(&form),
            name: None,
        });
        form
    }

    fn short(&mut self, concept: &str) -> Vec<i32> {
        let form = self.word(concept, false);
        syllables(&form, self.is_vowel)
            .into_iter()
            .next()
            .unwrap_or(form)
    }

    fn compound(&self, parts: &[Vec<i32>]) -> Vec<i32> {
        smooth_compound(parts, self.is_vowel)
    }

    fn seam(&self, a: &[i32], b: &[i32]) -> Vec<i32> {
        smooth_seam(a, b, self.is_vowel)
    }
}

fn part(role: &str, form: Vec<i32>, prefix: &str, suffix: &str) -> NamePart {
    NamePart {
        role: role.into(),
        form,
        prefix: prefix.into(),
        suffix: suffix.into(),
        text: None,
    }
}

/// Jméno osoby podle tradice `paradigm`. `prestige` je slovník prestižního jazyka (liturgie,
/// úřad), `origin` jméno místa původu (zápis latinkou) pro tradice, které ho užívají.
#[allow(clippy::too_many_arguments)]
pub fn person_name(
    paradigm: &str,
    lexicon: &dyn Lexicon,
    prestige: Option<&dyn Lexicon>,
    origin: Option<&str>,
    hash: u64,
    is_vowel: &dyn Fn(i32) -> bool,
    render: &dyn Fn(&[i32]) -> String,
) -> PersonName {
    let mut b = Builder {
        lexicon,
        prestige: prestige.unwrap_or(lexicon),
        is_vowel,
        render,
        recipe: Vec::new(),
    };
    let h = hash;
    let (parts, meaning, paradigm) = match paradigm {
        "tria_nomina" => {
            let (pc, cc, gc) = (
                pick("generational_markers", h, 1),
                pick("heroic_first", h, 2),
                pick("modifiers", h, 3),
            );
            let prae = b.short(&pc);
            let clan = b.word(&cc, false);
            let family = b.short("family");
            let nomen = b.compound(&[clan, family]);
            let cognomen = b.word(&gc, false);
            (
                vec![
                    part("given", prae, "", " "),
                    part("house", nomen, "", " "),
                    part("byname", cognomen, "", ""),
                ],
                format!(
                    "{}, rod {}, přezdívka „{}“",
                    gloss(&pc),
                    gloss(&cc),
                    gloss(&gc)
                ),
                "tria_nomina",
            )
        }
        "genealogical_nisba" => {
            let (gc, pc) = (pick("heroic_second", h, 1), pick("heroic_first", h, 2));
            let given = b.word(&gc, false);
            let child = b.short("child");
            let father = b.word(&pc, false);
            let filiation = b.seam(&child, &father);
            let mut parts = vec![
                part("given", given, "", " "),
                part("byname", filiation, "", ""),
            ];
            if let Some(place) = origin {
                parts.push(NamePart {
                    role: "nisba".into(),
                    prefix: " (".into(),
                    suffix: ")".into(),
                    text: Some(place.into()),
                    form: Vec::new(),
                });
            }
            let from = origin
                .map(|p| format!(" • původem z {p}"))
                .unwrap_or_default();
            (
                parts,
                format!("{} • potomek {}{from}", gloss(&gc), gloss(&pc)),
                "genealogical_nisba",
            )
        }
        "clan_generational" => {
            let (cc, gc, pc) = (
                pick("clan_emblems", h, 1),
                pick("generational_markers", h, 2),
                pick("heroic_second", h, 3),
            );
            let clan = b.short(&cc);
            let generation = b.short(&gc);
            let personal = b.short(&pc);
            let given = b.seam(&generation, &personal);
            (
                vec![part("house", clan, "", " "), part("given", given, "", "")],
                format!(
                    "klan {} • generace {} + {}",
                    gloss(&cc),
                    gloss(&gc),
                    gloss(&pc)
                ),
                "clan_generational",
            )
        }
        "liturgical_vernacular" => {
            let (sc, s2, nc) = (
                pick("sacred_civic", h, 1),
                pick("heroic_second", h, 2),
                pick("nature_stems", h, 3),
            );
            let first = b.word(&sc, true);
            let second = b.word(&s2, true);
            let given = b.compound(&[first, second]);
            let stem = b.word(&nc, false);
            let child = b.short("child");
            let surname = b.compound(&[stem, child]);
            (
                vec![
                    part("given", given, "", " "),
                    part("house", surname, "", ""),
                ],
                format!(
                    "kalendářní „{}-{}“, domácí rod „{}“",
                    gloss(&sc),
                    gloss(&s2),
                    gloss(&nc)
                ),
                "liturgical_vernacular",
            )
        }
        "caste_guild_matrix" => {
            let (kc, sc, hc) = (
                pick("caste_markers", h, 1),
                pick("heroic_second", h, 2),
                pick("urban_heads", h, 3),
            );
            let caste = b.short(&kc);
            let stem = b.word(&sc, false);
            let given = b.seam(&caste, &stem);
            let head = b.word(&hc, false);
            let house = b.short("house");
            let surname = b.compound(&[head, house]);
            (
                vec![
                    part("given", given, "", "-"),
                    part("house", surname, "", ""),
                ],
                format!(
                    "cech/živel [{}] + {} • dům {}",
                    gloss(&kc),
                    gloss(&sc),
                    gloss(&hc)
                ),
                "caste_guild_matrix",
            )
        }
        "chrononymic_deed" => {
            let (vc, oc, mc) = (
                pick("deed_verbs", h, 1),
                pick("deed_objects", h, 2),
                pick("nature_stems", h, 3),
            );
            let verb = b.word(&vc, false);
            let object = b.word(&oc, false);
            let deed = b.compound(&[verb, object]);
            let small = b.short("small");
            let milk_stem = b.word(&mc, false);
            let milk = b.compound(&[small, milk_stem]);
            (
                vec![part("given", deed, "", " "), part("byname", milk, "(", ")")],
                format!(
                    "jméno činu „{}-{}“ (dětské jméno „malý {}“)",
                    gloss(&vc),
                    gloss(&oc),
                    gloss(&mc)
                ),
                "chrononymic_deed",
            )
        }
        "polyglossic_court" => {
            let (c1, c2, lc) = (
                pick("heroic_first", h, 1),
                pick("heroic_second", h, 2),
                pick("nature_stems", h, 3),
            );
            let first = b.word(&c1, true);
            let second = b.word(&c2, true);
            let high = b.compound(&[first, second]);
            let low = b.short(&lc);
            (
                vec![part("given", high, "", " / "), part("byname", low, "", "")],
                format!(
                    "dvorské „{}-{}“ / domácí „{}“",
                    gloss(&c1),
                    gloss(&c2),
                    gloss(&lc)
                ),
                "polyglossic_court",
            )
        }
        "house_surety" => {
            let (c1, c2, hc) = (
                pick("heroic_first", h, 1),
                pick("heroic_second", h, 2),
                pick("clan_emblems", h, 3),
            );
            let first = b.word(&c1, false);
            let second = b.word(&c2, false);
            let given = b.compound(&[first, second]);
            let emblem = b.word(&hc, false);
            let house_word = b.short("house");
            let house = b.compound(&[emblem, house_word]);
            (
                vec![part("given", given, "", " "), part("house", house, "", "")],
                format!(
                    "jméno při narození „{}-{}“ • ručí za něj dům „{}“",
                    gloss(&c1),
                    gloss(&c2),
                    gloss(&hc)
                ),
                "house_surety",
            )
        }
        "journey_name" => {
            let (fc, vc, oc) = (
                pick("nature_stems", h, 1),
                pick("deed_verbs", h, 2),
                pick("deed_objects", h, 3),
            );
            let given = b.word(&fc, false);
            let verb = b.word(&vc, false);
            let object = b.word(&oc, false);
            let journey = b.compound(&[verb, object]);
            (
                vec![
                    part("given", given, "", ", "),
                    part("byname", journey, "", ""),
                ],
                format!(
                    "rodinné jméno „{}“ • po první cestě „{}-{}“",
                    gloss(&fc),
                    gloss(&vc),
                    gloss(&oc)
                ),
                "journey_name",
            )
        }
        "crew_byname" => {
            let (gc, mc) = (pick("heroic_second", h, 1), pick("modifiers", h, 2));
            let given = b.word(&gc, false);
            let modifier = b.word(&mc, false);
            let boat = b.short("boat");
            let crew = b.compound(&[modifier, boat]);
            (
                vec![
                    part("given", given, "", " "),
                    part("byname", crew, "„", "“"),
                ],
                format!(
                    "domácí jméno „{}“ • na palubě „{} loď“",
                    gloss(&gc),
                    gloss(&mc)
                ),
                "crew_byname",
            )
        }
        "birth_rite" => {
            let (ec, rc, sc) = (
                pick("deed_objects", h, 1),
                pick("sacred_civic", h, 2),
                pick("heroic_second", h, 3),
            );
            let event = b.word(&ec, false);
            let child = b.short("child");
            let given = b.compound(&[event, child]);
            let rite = b.word(&rc, false);
            let second = b.word(&sc, false);
            let ritual = b.compound(&[rite, second]);
            (
                vec![
                    part("given", given, "", " / "),
                    part("byname", ritual, "", ""),
                ],
                format!(
                    "narozen při „{}“ • obřadní jméno „{}-{}“",
                    gloss(&ec),
                    gloss(&rc),
                    gloss(&sc)
                ),
                "birth_rite",
            )
        }
        _ => {
            let (c1, c2, fc) = (
                pick("heroic_first", h, 1),
                pick("heroic_second", h, 2),
                pick("heroic_first", h, 3),
            );
            let first = b.word(&c1, false);
            let second = b.word(&c2, false);
            let given = b.compound(&[first, second]);
            let father = b.word(&fc, false);
            let child = b.short("child");
            let patronymic = b.compound(&[father, child]);
            (
                vec![
                    part("given", given, "", " "),
                    part("byname", patronymic, "", ""),
                ],
                format!("{}-{}, potomek {}", gloss(&c1), gloss(&c2), gloss(&fc)),
                "dithematic_ie",
            )
        }
    };
    PersonName {
        paradigm: paradigm.into(),
        parts,
        meaning,
        recipe: b.recipe,
    }
}
