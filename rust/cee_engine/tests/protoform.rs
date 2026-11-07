//! Generátor protojazyka (dok. 25): determinismus, přednost zadaných slov, slabičná stavba,
//! Zipfovo zkracování, dětská slova a zvuková symbolika.

use std::collections::{HashMap, HashSet};

use cee_engine::concepts::{ConceptData, Defaults};
use cee_engine::protoform::{protolanguage, syllable_type, ProtoSpec, SyllableType};
use cee_engine::scenarios::default_concepts;

struct Language {
    forms: HashMap<String, String>,
    frequencies: HashMap<String, f64>,
    kind: SyllableType,
}

fn inventory(list: &[&str]) -> Vec<String> {
    list.iter().map(|s| (*s).to_owned()).collect()
}

fn generate(
    seed: u64,
    concepts: &[String],
    consonants: &[String],
    fixed: &HashMap<String, String>,
    syllables: Option<SyllableType>,
) -> Language {
    let vowels = &Defaults::shared().default_vowels;
    let spec = ProtoSpec {
        concepts,
        seed,
        consonants,
        vowels,
        fixed,
        tones: &[],
        known_frequencies: None,
        syllables,
    };
    let kind = syllable_type(&spec);
    let (forms, frequencies) = protolanguage(&spec, ConceptData::shared()).unwrap();
    Language {
        forms,
        frequencies,
        kind,
    }
}

fn default_language(seed: u64, syllables: Option<SyllableType>) -> Language {
    generate(
        seed,
        &default_concepts(),
        &Defaults::shared().default_consonants,
        &HashMap::new(),
        syllables,
    )
}

fn is_vowel(c: char) -> bool {
    Defaults::shared()
        .default_vowels
        .iter()
        .any(|v| v.starts_with(c))
}

#[test]
fn stejne_seminko_stejny_jazyk() {
    let a = default_language(7, None);
    let b = default_language(7, None);
    assert_eq!(a.forms, b.forms);
    assert_eq!(a.frequencies, b.frequencies);
    let c = default_language(8, None);
    let same = a.forms.iter().filter(|(k, v)| c.forms[*k] == **v).count();
    assert!(
        same < a.forms.len() / 5,
        "jiné semínko, {same} stejných slov"
    );
}

#[test]
fn slova_jsou_jedinecna_a_z_inventare() {
    let consonants = &Defaults::shared().default_consonants;
    for seed in 1..=20 {
        let language = default_language(seed, None);
        let unique: HashSet<&String> = language.forms.values().collect();
        assert_eq!(
            unique.len(),
            language.forms.len(),
            "semínko {seed}: homonyma"
        );
        for word in language.forms.values() {
            assert!(
                word.chars().count() >= 2,
                "semínko {seed}: krátké slovo {word}"
            );
            for c in word.chars() {
                assert!(
                    is_vowel(c) || consonants.iter().any(|s| s.contains(c)),
                    "semínko {seed}: hláska {c} mimo inventář ve slově {word}"
                );
            }
        }
    }
}

#[test]
fn zadana_slova_maji_prednost() {
    let fixed: HashMap<String, String> = [("water", "akwa"), ("mother", "maːtɛr")]
        .iter()
        .map(|(k, v)| ((*k).to_owned(), (*v).to_owned()))
        .collect();
    let concepts = default_concepts();
    let consonants = &Defaults::shared().default_consonants;
    let free = generate(3, &concepts, consonants, &HashMap::new(), None);
    let given = generate(3, &concepts, consonants, &fixed, None);
    assert_eq!(given.forms["water"], "akwa");
    assert_eq!(given.forms["mother"], "maːtɛr");
    assert!(!given.forms.iter().any(|(k, v)| v == "akwa" && k != "water"));
    // Zadaná slova nemění slova ostatních pojmů (vlastní proud náhody každého pojmu).
    let changed = concepts
        .iter()
        .filter(|c| !fixed.contains_key(*c) && free.forms[*c] != given.forms[*c])
        .count();
    assert!(
        changed <= 2,
        "zadání dvou slov změnilo {changed} jiných slov"
    );
}

#[test]
fn pridany_pojem_nemeni_ostatni() {
    let mut concepts = default_concepts();
    let consonants = &Defaults::shared().default_consonants;
    let before = generate(11, &concepts, consonants, &HashMap::new(), None);
    concepts.push("grandmother".to_owned());
    let after = generate(11, &concepts, consonants, &HashMap::new(), None);
    let changed = before
        .forms
        .iter()
        .filter(|(k, v)| after.forms[*k] != **v)
        .count();
    assert!(changed <= 1, "přidaný pojem změnil {changed} slov");
}

#[test]
fn slabicna_stavba() {
    for seed in 1..=10 {
        let simple = default_language(seed, Some(SyllableType::Simple));
        assert_eq!(simple.kind, SyllableType::Simple);
        for word in simple.forms.values() {
            let chars: Vec<char> = word.chars().collect();
            assert!(
                is_vowel(*chars.last().unwrap()),
                "jednoduchá slabika: {word}"
            );
            assert!(
                !chars.windows(2).any(|w| !is_vowel(w[0]) && !is_vowel(w[1])),
                "jednoduchá slabika bez skupin souhlásek: {word}"
            );
        }
    }
    let share = |kind: SyllableType| -> f64 {
        let (mut closed, mut total) = (0, 0);
        for seed in 1..=30 {
            for word in default_language(seed, Some(kind)).forms.values() {
                closed += usize::from(!is_vowel(word.chars().last().unwrap()));
                total += 1;
            }
        }
        closed as f64 / total as f64
    };
    // WALS 12A × ASJP: na souhlásku končí 36 % (středně složitá) a 54 % slov (složitá).
    let (moderate, complex) = (share(SyllableType::Moderate), share(SyllableType::Complex));
    assert!(
        (0.28..0.46).contains(&moderate),
        "středně složitá: {moderate}"
    );
    assert!((0.45..0.65).contains(&complex), "složitá: {complex}");
}

#[test]
fn typy_slabik_se_losuji_podle_wals() {
    let mut counts = HashMap::new();
    for seed in 1..=300 {
        let spec = ProtoSpec {
            concepts: &[],
            seed,
            consonants: &[],
            vowels: &[],
            fixed: &HashMap::new(),
            tones: &[],
            known_frequencies: None,
            syllables: None,
        };
        *counts.entry(syllable_type(&spec)).or_insert(0) += 1;
    }
    // WALS 12A: 61 / 274 / 151 jazyků (13 / 56 / 31 %).
    assert!(
        (15..65).contains(&counts[&SyllableType::Simple]),
        "{counts:?}"
    );
    assert!(
        (140..200).contains(&counts[&SyllableType::Moderate]),
        "{counts:?}"
    );
    assert!(
        (65..125).contains(&counts[&SyllableType::Complex]),
        "{counts:?}"
    );
}

#[test]
fn caste_pojmy_jsou_kratsi() {
    // Zipfův zákon zkracování: ASJP dává ρ(frekvence, délka) průměrně −0,135.
    let concepts = default_concepts();
    let mut total = 0.0;
    let seeds = 40;
    for seed in 1..=seeds {
        let language = default_language(seed, None);
        let mut pairs: Vec<(f64, usize)> = concepts
            .iter()
            .map(|c| (language.frequencies[c], language.forms[c].chars().count()))
            .collect();
        pairs.sort_by(|a, b| a.0.total_cmp(&b.0));
        let half = pairs.len() / 2;
        let rare: f64 = pairs[..half].iter().map(|p| p.1 as f64).sum::<f64>() / half as f64;
        let common: f64 =
            pairs[half..].iter().map(|p| p.1 as f64).sum::<f64>() / (pairs.len() - half) as f64;
        total += rare - common;
    }
    let mean = total / seeds as f64;
    assert!(
        mean > 0.2,
        "častější polovina pojmů má být kratší, rozdíl {mean}"
    );
}

#[test]
fn detska_slova_pro_rodice() {
    let nasal = |w: &str| w.contains('m') || w.contains('n');
    let stop = |w: &str| w.chars().any(|c| "pbtd".contains(c));
    let (mut mother_nasal, mut father_nasal, mut father_stop, mut mother_stop) = (0, 0, 0, 0);
    for seed in 1..=100 {
        let language = default_language(seed, None);
        let (mother, father) = (&language.forms["mother"], &language.forms["father"]);
        mother_nasal += usize::from(nasal(mother));
        father_nasal += usize::from(nasal(father));
        father_stop += usize::from(stop(father));
        mother_stop += usize::from(stop(mother));
    }
    // WOLD: nosovka ve slově „matka“ 71 %, „otec“ 15 %; ražená p/b/t/d u otce 73 %, u matky 22 %.
    assert!(
        mother_nasal >= 60 && father_nasal <= 35,
        "{mother_nasal} / {father_nasal}"
    );
    assert!(
        father_stop >= 60 && mother_stop <= 35,
        "{father_stop} / {mother_stop}"
    );
}

#[test]
fn detska_slova_bez_nosovek() {
    let consonants = inventory(&["p", "t", "k", "s", "l", "r", "w", "j"]);
    for seed in 1..=10 {
        let language = generate(
            seed,
            &default_concepts(),
            &consonants,
            &HashMap::new(),
            None,
        );
        assert!(!language.forms["mother"].contains('m'));
    }
}

#[test]
fn zvukova_symbolika() {
    // Blasi a kol. 2016: jazyk–l RR 2,77, já–l 0,19.
    let concepts = default_concepts();
    let (mut tongue, mut i, mut other, mut other_total) = (0, 0, 0, 0);
    let seeds = 150;
    for seed in 1..=seeds {
        let language = default_language(seed, None);
        tongue += usize::from(language.forms["tongue"].contains('l'));
        i += usize::from(language.forms["i"].contains('l'));
        for concept in &concepts {
            other += usize::from(language.forms[concept].contains('l'));
            other_total += 1;
        }
    }
    let base = other as f64 / other_total as f64;
    let tongue = tongue as f64 / seeds as f64 / base;
    let i = i as f64 / seeds as f64 / base;
    assert!(tongue > 1.5, "jazyk–l: RR {tongue}");
    assert!(i < 0.6, "já–l: RR {i}");
}

#[test]
fn inventar_z_phoible() {
    use cee_engine::protoform::inventory;
    let table = cee_engine::segments::SegmentTable::default_table();
    let (mut consonants, mut vowels, mut with_b, mut b_and_g) = (0, 0, 0, 0);
    for seed in 1..=300 {
        let (c, v) = inventory(seed);
        assert_eq!((c.clone(), v.clone()), inventory(seed), "determinismus");
        assert!(c.len() >= 6 && v.len() >= 2, "semínko {seed}: {c:?} {v:?}");
        for segment in c.iter().chain(&v) {
            assert!(
                table.parse(segment).is_ok(),
                "hláska {segment} mimo tabulku"
            );
        }
        // Dlouhá nebo nosová samohláska předpokládá krátkou ústní.
        for vowel in &v {
            let base: String = vowel
                .chars()
                .filter(|c| !matches!(c, 'ː' | '\u{303}'))
                .collect();
            let known = cee_engine::protoform::InventoryData::shared().contains(1, &base);
            assert!(
                base == *vowel || v.contains(&base) || !known,
                "{vowel} bez {base}: {v:?}"
            );
        }
        consonants += c.len();
        vowels += v.len();
        if c.iter().any(|s| s == "b") {
            with_b += 1;
            b_and_g += usize::from(c.iter().any(|s| s == "ɡ"));
        }
    }
    // PHOIBLE: průměr asi 18 souhlásek a 7,5 samohlásky; P(ɡ | b) = 0,86.
    let (c, v) = (consonants as f64 / 300.0, vowels as f64 / 300.0);
    assert!(
        (14.0..23.0).contains(&c) && (5.5..10.0).contains(&v),
        "{c} / {v}"
    );
    assert!(
        b_and_g as f64 / with_b as f64 > 0.6,
        "P(ɡ | b) = {b_and_g}/{with_b}"
    );
}

#[test]
fn koncovky_a_pripony_z_fonologie() {
    use cee_engine::protoform::{morphemes, ENDING_CELLS};
    let consonants = &Defaults::shared().default_consonants;
    let vowels = &Defaults::shared().default_vowels;
    let fixed = HashMap::new();
    let mut distinct = HashSet::new();
    for seed in 1..=30 {
        for kind in SyllableType::ALL {
            let spec = ProtoSpec {
                concepts: &[],
                seed,
                consonants,
                vowels,
                fixed: &fixed,
                tones: &[],
                known_frequencies: None,
                syllables: Some(kind),
            };
            let found = morphemes(&spec, 3).unwrap();
            assert_eq!(found.endings.len(), ENDING_CELLS.len());
            assert_eq!(found.suffixes.len(), 3);
            let mains: HashSet<&String> = found.endings.values().map(|o| &o[0].0).collect();
            assert_eq!(
                mains.len(),
                ENDING_CELLS.len(),
                "hlavní koncovky buněk se liší"
            );
            for options in found.endings.values() {
                for (ending, _) in options {
                    assert!(ending.chars().count() <= 3, "krátká koncovka: {ending}");
                    if kind == SyllableType::Simple {
                        assert!(is_vowel(ending.chars().last().unwrap()), "(C)V: {ending}");
                    }
                }
                distinct.insert(options[0].0.clone());
            }
        }
    }
    // Jazyky nemají všechny stejné koncovky.
    assert!(
        distinct.len() > 30,
        "jen {} různých koncovek",
        distinct.len()
    );
}
