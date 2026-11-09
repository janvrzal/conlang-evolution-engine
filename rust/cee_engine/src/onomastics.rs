//! Modulární diachronní onomastika: názvy měst, vesnic, regionů, států (toponyma,
//! substrátová jména, exonyma) a vlastních osobních jmen (antroponyma — reálná
//! historická i fiktivní paradigmata).
//!
//! Všechna jména se stavějí ze skutečných fonologických tvarů morfémů v `World`
//! (které prošly hláskovými změnami daného jazyka nebo byly adaptovány přes
//! `World::adapted_form_of`) a z katalogu `v2_onomastics.json`.

use std::collections::{BTreeMap, BTreeSet};
use std::sync::OnceLock;

use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};

use crate::ids::{ConceptId, GroupId, LanguageId, TerritoryId};
use crate::model::group::Domain;
use crate::model::repertoire::Payload;
use crate::model::territory::TerritoryLevel;
use crate::naming::syllables;
use crate::rng::{stable_int, Part};
use crate::world::World;

const ONOMASTICS_JSON: &str = include_str!("../../../src/cee/data/v2_onomastics.json");

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct OnomasticsCatalog {
    pub version: u32,
    pub glosses_cs: BTreeMap<String, String>,
    pub semantic_pools: BTreeMap<String, Vec<String>>,
    pub toponym_paradigms: BTreeMap<String, ToponymParadigmSpec>,
    pub anthroponym_paradigms: BTreeMap<String, AnthroponymParadigmSpec>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ToponymParadigmSpec {
    pub description: String,
    pub head_pool: String,
    pub modifier_pool: String,
    pub reduce_head: bool,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct AnthroponymParadigmSpec {
    pub kind: String,
    pub label_cs: String,
    pub slots: Vec<String>,
}

pub fn catalog() -> &'static OnomasticsCatalog {
    static CATALOG: OnceLock<OnomasticsCatalog> = OnceLock::new();
    CATALOG.get_or_init(|| {
        serde_json::from_str(ONOMASTICS_JSON).expect("platný v2_onomastics.json")
    })
}

/// Vyhladí šev mezi dvěma částmi složeniny: zabrání nahromadění 3+ souhlásek
/// na hranici morfémů (např. `pʒn` → `ʒn`, `ʃjm` → `ʃm`) a zdvojení totožné hlásky.
pub fn smooth_seam(
    first: &[i32],
    second: &[i32],
    is_vowel: &dyn Fn(i32) -> bool,
) -> Vec<i32> {
    if first.is_empty() {
        return second.to_vec();
    }
    if second.is_empty() {
        return first.to_vec();
    }
    let mut left = first.to_vec();
    let right = second;

    // Kolik souhlásek je na konci první části a na začátku druhé části?
    let trailing_c = left.iter().rev().take_while(|&&s| !is_vowel(s)).count();
    let leading_c = right.iter().take_while(|&&s| !is_vowel(s)).count();

    // Pokud by na švu vznikl shluk >= 3 souhlásek, zjednodušíme koncovou souhlásku první části
    // (pokud první část obsahuje aspoň jednu samohlásku).
    let left_has_vowel = left.iter().any(|&s| is_vowel(s));
    if left_has_vowel && trailing_c + leading_c >= 3 && trailing_c >= 1 {
        let drop = (trailing_c + leading_c - 2).min(trailing_c);
        for _ in 0..drop {
            if left.len() > 1 {
                left.pop();
            }
        }
    }
    // Odstranění bezprostředního zdvojení stejného segmentu na švu.
    if left.last() == right.first() && left.len() > 1 {
        left.pop();
    }
    left.extend_from_slice(right);
    left
}

/// Spojí části složeniny se zkrácením předních členů na první slabiku a vyhlazením švů.
pub fn smooth_compound(parts: &[Vec<i32>], is_vowel: &dyn Fn(i32) -> bool) -> Vec<i32> {
    let split: Vec<Vec<Vec<i32>>> = parts
        .iter()
        .filter(|p| !p.is_empty())
        .map(|p| syllables(p, is_vowel))
        .collect();
    let Some((tail, heads)) = split.split_last() else {
        return Vec::new();
    };
    let mut pieces: Vec<Vec<i32>> = Vec::new();
    for head in heads {
        if let Some(first_syl) = head.first() {
            pieces.push(first_syl.clone());
        }
    }
    let limit = 2.max(pieces.len() + 2);
    for syl in tail {
        if pieces.len() < limit {
            pieces.push(syl.clone());
        }
    }
    let mut acc: Vec<i32> = Vec::new();
    for piece in pieces {
        acc = smooth_seam(&acc, &piece, is_vowel);
    }
    acc
}

/// Převede IPA řetězec na čitelný latinkový přepis s velkým počátečním písmenem.
pub fn romanize(ipa: &str) -> String {
    let mut s = ipa.to_owned();
    let replacements = [
        ("t͡ʃʲ", "č"),
        ("d͡ʒʲ", "dž"),
        ("t͡ʃ", "č"),
        ("d͡ʒ", "dž"),
        ("c", "ť"),
        ("ɟ", "ď"),
        ("t͡s", "c"),
        ("d͡z", "dz"),
        ("kʷ", "kv"),
        ("ɡʷ", "gv"),
        ("gʷ", "gv"),
        ("nʲ", "ň"),
        ("lʲ", "ľ"),
        ("rʲ", "ř"),
        ("tʲ", "ť"),
        ("dʲ", "ď"),
        ("sʲ", "ś"),
        ("zʲ", "ź"),
        ("pʲ", "pj"),
        ("bʲ", "bj"),
        ("mʲ", "mj"),
        ("kʲ", "kj"),
        ("ɡʲ", "gj"),
        ("xʲ", "chj"),
        ("ʃ", "š"),
        ("ʒ", "ž"),
        ("ɲ", "ň"),
        ("ʎ", "ľ"),
        ("ŋ", "ng"),
        ("θ", "th"),
        ("ð", "dh"),
        ("x", "ch"),
        ("χ", "ch"),
        ("ɣ", "gh"),
        ("ʁ", "r"),
        ("β", "v"),
        ("ɸ", "f"),
        ("ʋ", "v"),
        ("ɹ", "r"),
        ("ɰ", "g"),
        ("ʝ", "j"),
        ("ɦ", "h"),
        ("ħ", "h"),
        ("ʔ", ""),
        ("ɡ", "g"),
        ("ɢ", "g"),
        ("ɬ", "hl"),
        ("ə", "e"),
        ("ɛ", "e"),
        ("æ", "ä"),
        ("ø", "ö"),
        ("œ", "ö"),
        ("ɔ", "o"),
        ("ɒ", "o"),
        ("ɑ", "a"),
        ("ʌ", "a"),
        ("ʊ", "u"),
        ("ɯ", "u"),
        ("ʉ", "u"),
        ("ɪ", "i"),
        ("ʏ", "ü"),
        ("y", "ü"),
        ("ɨ", "y"),
    ];
    for (from, to) in replacements {
        s = s.replace(from, to);
    }
    // Odstranění kombinujících diakritik (nosovost, délka, tóny, přízvuk) pro čitelnou ortografii.
    let mut clean = String::with_capacity(s.len());
    for ch in s.chars() {
        if matches!(
            ch,
            '\u{0300}'..='\u{036F}'
                | 'ː'
                | 'ˑ'
                | 'ˈ'
                | 'ˌ'
                | 'ʰ'
                | 'ʷ'
                | 'ʲ'
                | 'ˠ'
                | 'ˤ'
                | '˥'
                | '˦'
                | '˧'
                | '˨'
                | '˩'
        ) {
            continue;
        }
        clean.push(ch);
    }
    // Zjednodušení případných trojitých souhlásek nebo zdvojených spřežek v přepisu.
    clean = clean
        .replace("dždž", "dž")
        .replace("čč", "č")
        .replace("šš", "š")
        .replace("žž", "ž")
        .replace("chch", "ch")
        .replace("ngng", "ng")
        .replace("jj", "j")
        .replace("ww", "v")
        .replace("w", "v");

    let mut chars = clean.chars();
    match chars.next() {
        Some(first) => first.to_uppercase().collect::<String>() + chars.as_str(),
        None => String::new(),
    }
}

fn gloss_cs(concept: &str) -> &str {
    catalog()
        .glosses_cs
        .get(concept)
        .map(String::as_str)
        .unwrap_or(concept)
}

/// Zjistí, zda má skupina ve slovosledu (`ORDER`) převládající head-initial pořadí (`VO` / `VSO` / `VOS`).
fn is_head_initial(world: &World, group: GroupId) -> bool {
    let Some(var_num) = world.registry.variables.get("construction:ORDER") else {
        return false;
    };
    let variable = crate::ids::VariableId(var_num);
    if variable.index() >= world.variables.len() {
        return false;
    }
    let Some((variant, _)) = world.dominant(group, variable) else {
        return false;
    };
    if let Payload::Construction(c) = &world.variants.payload[variant.index()] {
        if let Some(order) = &c.order {
            return matches!(order.as_str(), "SVO" | "VSO" | "VOS");
        }
    }
    false
}

/// Vezme dnešní tvar pojmu `concept_name` ve skupině `group` (nebo adaptovaný z `donor_group`).
fn form_for_concept(
    world: &World,
    group: GroupId,
    donor_group: Option<GroupId>,
    concept_name: &str,
) -> Vec<i32> {
    let Some(cid) = world.registry.concepts.get(concept_name).map(ConceptId) else {
        return Vec::new();
    };
    let source = donor_group.unwrap_or(group);
    let root = world.dominant_or_plural_root(source, cid);
    if root.is_none() {
        return Vec::new();
    }
    if donor_group.is_some() && source != group {
        // Substrátové nebo přejaté slovo: vezmeme dnešní tvar u dárce a adaptujeme ho
        // do fonologie cílové skupiny.
        let raw = world.adapted_form_of(source, root);
        let inventory = crate::contact::inventory(world, group);
        if inventory.is_empty() {
            raw
        } else {
            crate::contact::adapt(world, &inventory, &raw)
        }
    } else {
        world.adapted_form_of(group, root)
    }
}

fn first_syllable(segments: &[i32], is_vowel: &dyn Fn(i32) -> bool) -> Vec<i32> {
    syllables(segments, is_vowel)
        .into_iter()
        .next()
        .unwrap_or_else(|| segments.to_vec())
}

fn pick<'a>(pool: &'a [String], hash: u64, salt: u64) -> &'a str {
    if pool.is_empty() {
        return "stone";
    }
    let idx = (hash.wrapping_add(salt.wrapping_mul(0x9E37_79B9_7F4A_7C15)) as usize) % pool.len();
    pool[idx].as_str()
}

/// Najde reprezentativní domácí mluvenou skupinu daného jazyka `lang` (pro substrát nebo exonyma).
fn representative_of_language(world: &World, lang: LanguageId) -> Option<GroupId> {
    world
        .group_ids()
        .into_iter()
        .filter(|&g| {
            let at = g.index();
            !world.groups.written[at]
                && world.groups.domain[at] == Domain::Home
                && world.groups.main_code(g).language == lang
        })
        .max_by_key(|&g| world.groups.population[g.index()])
}

/// Najde hlavní domácí skupinu území (pro osadu přímo její skupinu, pro region jeho sídlo).
fn territory_group(world: &World, tid: TerritoryId) -> Option<GroupId> {
    let node = &world.territories[tid.index()];
    if node.level == TerritoryLevel::Region {
        crate::polity::seat_of(world, tid).ok()
    } else {
        world
            .group_ids()
            .into_iter()
            .filter(|&g| {
                let at = g.index();
                !world.groups.written[at]
                    && world.groups.domain[at] == Domain::Home
                    && world.groups.territory[at] == tid
            })
            .max_by_key(|&g| world.groups.population[g.index()])
    }
}

/// Vygeneruje diachronní toponymum pro území `tid` (region, město nebo vesnici).
pub fn territory_toponym(
    world: &World,
    tid: TerritoryId,
    used_names: &mut BTreeSet<String>,
) -> Value {
    let Some(table) = world.segments() else {
        return Value::Null;
    };
    let cat = catalog();
    let t_name = world.registry.territories.name(tid.0);
    let node = &world.territories[tid.index()];
    let Some(group) = territory_group(world, tid) else {
        return Value::Null;
    };
    let current_lang = world.groups.main_code(group).language;
    let region_id = if node.level == TerritoryLevel::Region {
        tid
    } else if !node.parent.is_none() {
        node.parent
    } else {
        tid
    };
    let reg_node = &world.territories[region_id.index()];
    let origin_lang = if !reg_node.native_language.is_none() {
        reg_node.native_language
    } else {
        current_lang
    };
    let has_substrate = origin_lang != current_lang;
    let donor_group = if has_substrate {
        representative_of_language(world, origin_lang)
    } else {
        None
    };

    let terrain_pool_key = match reg_node.terrain.as_str() {
        "hills" => "terrain_hills",
        "mountains" => "terrain_mountains",
        "island" => "terrain_island",
        _ => "terrain_plain",
    };
    let is_urban = node.urban > 0.0
        || (node.level == TerritoryLevel::Region
            && node
                .children
                .first()
                .is_some_and(|&c| world.territories[c.index()].urban > 0.0));
    let is_vowel = |s: i32| table.is_vowel(s);
    let head_init = is_head_initial(world, donor_group.unwrap_or(group));

    let mut chosen_ipa = String::new();
    let mut chosen_name = String::new();
    let mut chosen_meaning = String::new();
    let mut chosen_pattern = String::new();

    for attempt in 0..32_u64 {
        let h = stable_int(&[
            Part::Str("toponym"),
            Part::Int(world.seed),
            Part::Str(t_name),
            Part::Uint(attempt),
        ]);
        let mode = h % 100;
        let (pattern, head_concept, mod_concept, reduce_head, pleonastic_concept) = if has_substrate
        {
            let t_pool = &cat.semantic_pools[terrain_pool_key];
            let m_pool = &cat.semantic_pools["modifiers"];
            let hc = pick(t_pool, h, 1);
            let mc = pick(m_pool, h, 2);
            if mode < 35 {
                let extra = if is_urban { "town" } else { hc };
                ("pleonastic_substrate", hc, mc, false, Some(extra))
            } else {
                ("substrate_survival", hc, mc, true, None)
            }
        } else if is_urban {
            match mode % 4 {
                0 => (
                    "habitative_formant",
                    pick(&cat.semantic_pools["urban_heads"], h, 1),
                    pick(&cat.semantic_pools["heroic_first"], h, 2),
                    true,
                    None,
                ),
                1 => (
                    "hydro_crossing",
                    pick(&cat.semantic_pools["crossing_heads"], h, 1),
                    pick(&cat.semantic_pools["hydro_heads"], h, 2),
                    false,
                    None,
                ),
                2 => (
                    "sacred_civic",
                    pick(&cat.semantic_pools["urban_heads"], h, 1),
                    pick(&cat.semantic_pools["sacred_civic"], h, 2),
                    true,
                    None,
                ),
                _ => (
                    "eponymous_founder",
                    pick(&cat.semantic_pools["urban_heads"], h, 1),
                    pick(&cat.semantic_pools["nature_stems"], h, 2),
                    true,
                    None,
                ),
            }
        } else if node.level == TerritoryLevel::Region {
            if mode < 65 {
                (
                    "descriptive_terrain",
                    pick(&cat.semantic_pools[terrain_pool_key], h, 1),
                    pick(&cat.semantic_pools["modifiers"], h, 2),
                    false,
                    None,
                )
            } else {
                (
                    "habitative_formant",
                    pick(&cat.semantic_pools[terrain_pool_key], h, 1),
                    pick(&cat.semantic_pools["nature_stems"], h, 2),
                    true,
                    None,
                )
            }
        } else if mode < 55 {
            (
                "descriptive_terrain",
                pick(&cat.semantic_pools["rural_heads"], h, 1),
                pick(&cat.semantic_pools["modifiers"], h, 2),
                false,
                None,
            )
        } else {
            (
                "eponymous_founder",
                pick(&cat.semantic_pools["rural_heads"], h, 1),
                pick(&cat.semantic_pools["nature_stems"], h, 2),
                true,
                None,
            )
        };

        let mut head_segs = form_for_concept(world, group, donor_group, head_concept);
        let mod_segs = form_for_concept(world, group, donor_group, mod_concept);
        if reduce_head && !head_segs.is_empty() {
            head_segs = first_syllable(&head_segs, &is_vowel);
        }
        let base_segs = if head_init {
            smooth_compound(&[head_segs, mod_segs], &is_vowel)
        } else {
            smooth_compound(&[mod_segs, head_segs], &is_vowel)
        };
        let final_segs = if let Some(pleo) = pleonastic_concept {
            let local_head = first_syllable(&form_for_concept(world, group, None, pleo), &is_vowel);
            let sub_short = first_syllable(&base_segs, &is_vowel);
            smooth_seam(&sub_short, &local_head, &is_vowel)
        } else {
            base_segs
        };

        let ipa = table.render(&final_segs);
        let rom = romanize(&ipa);
        chosen_ipa = ipa;
        chosen_name = rom.clone();
        chosen_pattern = pattern.to_owned();
        chosen_meaning = if let Some(pleo) = pleonastic_concept {
            format!(
                "{} (substrát: {} {})",
                gloss_cs(pleo),
                gloss_cs(mod_concept),
                gloss_cs(head_concept)
            )
        } else {
            format!("{} {}", gloss_cs(mod_concept), gloss_cs(head_concept))
        };
        if !rom.is_empty() && !used_names.contains(&rom) {
            used_names.insert(rom);
            break;
        }
    }

    // U měst vygenerujeme i exonyma ve spisovných normách světa.
    let mut exonyms = Map::new();
    if is_urban && !chosen_ipa.is_empty() {
        if let Ok(segs) = table.parse(&chosen_ipa) {
            for (std_id, &std_group) in &world.society.standards {
                if !world.groups.contains(std_group) {
                    continue;
                }
                let inv = crate::contact::inventory(world, std_group);
                let adapted: Vec<i32> = if inv.is_empty() {
                    segs.clone()
                } else {
                    crate::contact::adapt(world, &inv, &segs)
                };
                let ex_ipa = table.render(&adapted);
                let ex_rom = romanize(&ex_ipa);
                if !ex_rom.is_empty() && ex_rom != chosen_name {
                    exonyms.insert(
                        std_id.clone(),
                        json!({
                            "name": ex_rom,
                            "ipa": ex_ipa,
                        }),
                    );
                }
            }
        }
    }

    json!({
        "name": chosen_name,
        "ipa": chosen_ipa,
        "meaning": chosen_meaning,
        "pattern": chosen_pattern,
        "urban": is_urban,
        "substrate": has_substrate,
        "origin_language": world.registry.languages.name(origin_lang.0),
        "current_language": world.registry.languages.name(current_lang.0),
        "exonyms": exonyms,
    })
}

/// Vybere paradigma osobních jmen pro danou skupinu / jazyk (podporuje jak přímé zadání,
/// tak deterministický výběr z reálných i fiktivních paradigmat).
pub fn select_paradigm(world: &World, group: GroupId) -> &'static str {
    let at = group.index();
    let code = world.groups.main_code(group);
    let lang_name = world.registry.languages.name(code.language.0);
    let has_liturgy_or_std = !world.groups.liturgy[at].is_none()
        || (!world.groups.standard[at].is_none() && world.groups.schooling[at] > 0.3);
    let is_urban = !world.groups.territory[at].is_none()
        && world.territories[world.groups.territory[at].index()].urban > 0.0;

    let h = stable_int(&[
        Part::Str("paradigm"),
        Part::Int(world.seed),
        Part::Str(lang_name),
    ]);

    if has_liturgy_or_std && (h % 5 == 0) {
        return "liturgical_vernacular";
    }
    if is_urban && (h % 7 == 0) {
        return "caste_guild_matrix";
    }
    const PARADIGMS: [&str; 8] = [
        "dithematic_ie",
        "genealogical_nisba",
        "tria_nomina",
        "clan_generational",
        "liturgical_vernacular",
        "caste_guild_matrix",
        "chrononymic_deed",
        "polyglossic_court",
    ];
    PARADIGMS[(h as usize) % PARADIGMS.len()]
}

/// Vygeneruje sadu vlastních osobních jmen pro danou skupinu a zadané paradigma
/// (skládá `names::persons::person_name` z dnešních slov skupiny; jen vzorník pro export).
pub fn personal_names_for_group(
    world: &World,
    group: GroupId,
    paradigm: &str,
    settlement_toponym: Option<&str>,
    count: usize,
) -> Vec<Value> {
    use crate::names::compose::{Adapted, Live};
    let Some(table) = world.segments() else {
        return Vec::new();
    };
    let is_vowel = |s: i32| table.is_vowel(s);
    let render = |f: &[i32]| table.render(f);
    let g_name = world.group_name(group);
    let at = group.index();
    let prestige_donor = if !world.groups.liturgy[at].is_none() {
        Some(world.groups.liturgy[at])
    } else if !world.groups.standard[at].is_none() {
        Some(world.groups.standard[at])
    } else {
        None
    };
    let lexicon = Live { world, group };
    let donor = prestige_donor.map(|g| Live { world, group: g });
    let adapted = donor.as_ref().map(|d| Adapted {
        inner: d,
        world,
        inventory: crate::contact::inventory(world, group),
    });
    let origin = settlement_toponym.unwrap_or("Varad");
    (0..count)
        .map(|idx| {
            let h = stable_int(&[
                Part::Str("anthroponym"),
                Part::Int(world.seed),
                Part::Str(g_name),
                Part::Str(paradigm),
                Part::Uint(idx as u64),
            ]);
            let name = crate::names::persons::person_name(
                paradigm,
                &lexicon,
                adapted.as_ref().map(|a| a as &dyn crate::names::compose::Lexicon),
                Some(origin),
                h,
                &is_vowel,
                &render,
            );
            let given = name.parts.first().map_or(String::new(), |p| romanize(&render(&p.form)));
            let byname: Vec<String> = name.parts[1..]
                .iter()
                .map(|p| p.text.clone().unwrap_or_else(|| romanize(&render(&p.form))))
                .collect();
            json!({
                "full_name": name.full(&render),
                "ipa": name.ipa(&render),
                "given": given,
                "byname": byname.join(" "),
                "meaning": name.meaning,
                "paradigm": name.paradigm,
            })
        })
        .collect()
}

/// Vygeneruje kompletní onomastický přehled světa pro export:
/// - `toponyms`: všechna území (regiony, města, vesnice) s IPA, ortografií, významem, substrátem a exonymy,
/// - `states`: domácí úřední jména států v jejich úředním jazyce,
/// - `paradigms`: přehled aktivních paradigmat a vzorník osobních jmen pro spisovné normy i příklady všech paradigmat.
pub fn export_world_onomastics(world: &World) -> Value {
    let cat = catalog();
    let mut used_names = BTreeSet::new();
    let mut toponyms = Map::new();
    let mut names: Vec<(&str, usize)> = (0..world.territories.len())
        .map(|i| (world.registry.territories.name(i as u32), i))
        .collect();
    names.sort();
    for (name, idx) in names {
        let tid = TerritoryId(idx as u32);
        let top = territory_toponym(world, tid, &mut used_names);
        if !top.is_null() {
            toponyms.insert(name.to_owned(), top);
        }
    }

    // Domácí názvy států (odvozené ze jména hlavního města + pojmu pro obec/zemi/zákon).
    let mut state_names = Map::new();
    if let Some(table) = world.segments() {
        let is_vowel = |s: i32| table.is_vowel(s);
        for (sid, polity) in &world.society.states {
            let cap_id = world.registry.territories.name(polity.capital.0);
            let city_key = format!("{cap_id}-v0");
            let cap_top = toponyms.get(&city_key).or_else(|| toponyms.get(cap_id));
            let cap_ipa = cap_top
                .and_then(|v| v.get("ipa"))
                .and_then(Value::as_str)
                .unwrap_or("");
            let cap_name = cap_top
                .and_then(|v| v.get("name"))
                .and_then(Value::as_str)
                .unwrap_or(cap_id);
            let civic_concept = match polity.centralization.as_str() {
                "high" | "strong" => "king",
                "low" | "weak" => "trade",
                _ => "law",
            };
            let civic_segs = form_for_concept(world, polity.seat, None, civic_concept);
            let cap_segs = table.parse(cap_ipa).unwrap_or_default();
            let state_segs = smooth_compound(&[cap_segs, civic_segs], &is_vowel);
            let st_ipa = table.render(&state_segs);
            let st_rom = romanize(&st_ipa);
            state_names.insert(
                sid.clone(),
                json!({
                    "endonym": st_rom,
                    "ipa": st_ipa,
                    "capital_name": cap_name,
                    "meaning": format!("{} ({})", cap_name, gloss_cs(civic_concept)),
                }),
            );
        }
    }

    // Osobní jména podle spisovných norem a jednotlivých paradigmat.
    let mut by_standard = Map::new();
    let all_paradigms: Vec<&str> = cat.anthroponym_paradigms.keys().map(String::as_str).collect();
    for (idx, (sid, &std_group)) in world.society.standards.iter().enumerate() {
        if !world.groups.contains(std_group) {
            continue;
        }
        let base_name = world.group_name(std_group).trim_start_matches("written:");
        let spoken_group = world
            .registry
            .groups
            .get(base_name)
            .map(GroupId)
            .unwrap_or(std_group);
        let tid = world.groups.territory[spoken_group.index()];
        let city_toponym = (!tid.is_none())
            .then(|| world.registry.territories.name(tid.0))
            .and_then(|n| toponyms.get(n))
            .and_then(|v| v.get("name"))
            .and_then(Value::as_str);

        let primary_paradigm = if !all_paradigms.is_empty() {
            all_paradigms[idx % all_paradigms.len()]
        } else {
            select_paradigm(world, spoken_group)
        };
        let p_spec = cat.anthroponym_paradigms.get(primary_paradigm);
        let roster = personal_names_for_group(world, spoken_group, primary_paradigm, city_toponym, 5);
        by_standard.insert(
            sid.clone(),
            json!({
                "paradigm": primary_paradigm,
                "paradigm_kind": p_spec.map(|p| p.kind.as_str()).unwrap_or("real_world"),
                "paradigm_label": p_spec.map(|p| p.label_cs.as_str()).unwrap_or(""),
                "city_toponym": city_toponym,
                "names": roster,
            }),
        );
    }

    // Ukázkový katalog všech paradigmat (reálných i fiktivních) nad nejsilnější skupinou světa.
    let mut paradigm_showcase = Map::new();
    if let Some(rep_group) = world
        .group_ids()
        .into_iter()
        .filter(|&g| !world.groups.written[g.index()] && world.groups.domain[g.index()] == Domain::Home)
        .max_by_key(|&g| world.groups.population[g.index()])
    {
        for (p_id, p_spec) in &cat.anthroponym_paradigms {
            let samples = personal_names_for_group(world, rep_group, p_id, Some("Varad"), 3);
            paradigm_showcase.insert(
                p_id.clone(),
                json!({
                    "kind": p_spec.kind,
                    "label_cs": p_spec.label_cs,
                    "slots": p_spec.slots,
                    "samples": samples,
                }),
            );
        }
    }

    json!({
        "toponyms": toponyms,
        "states": state_names,
        "standards_personal_names": by_standard,
        "paradigm_catalog": paradigm_showcase,
    })
}
