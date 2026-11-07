//! Ukázky a měření generátoru protojazyka (dok. 25).
//!
//! `cargo run --release --example protojazyk -- ukazky 1 2 3 4` vypíše slova vybraných pojmů,
//! `cargo run --release --example protojazyk -- mereni 300` změří na N semíncích
//! Spearmanovo ρ(frekvence, délka), poměry rizik zvukové symboliky, dětská slova a stavbu
//! slov podle slabičného typu.

use std::collections::HashMap;

use cee_engine::concepts::{ConceptData, Defaults};
use cee_engine::protoform::{
    morphemes, protolanguage, syllable_type, ProtoSpec, ProtoformData, SyllableType,
};
use cee_engine::scenarios::default_concepts;

const SAMPLE: [(&str, &str); 24] = [
    ("i", "já"),
    ("you", "ty"),
    ("we", "my"),
    ("two", "dva"),
    ("mother", "matka"),
    ("father", "otec"),
    ("child", "dítě"),
    ("water", "voda"),
    ("fire", "oheň"),
    ("sun", "slunce"),
    ("moon", "měsíc"),
    ("stone", "kámen"),
    ("tree", "strom"),
    ("dog", "pes"),
    ("fish", "ryba"),
    ("eye", "oko"),
    ("nose", "nos"),
    ("tongue", "jazyk"),
    ("small", "malý"),
    ("big", "velký"),
    ("eat", "jíst"),
    ("die", "zemřít"),
    ("mountain", "hora"),
    ("village", "vesnice"),
];

fn rich_inventory() -> (Vec<String>, Vec<String>) {
    let consonants = [
        "p", "t", "k", "b", "d", "ɡ", "m", "n", "ŋ", "s", "z", "ʃ", "tʃ", "l", "r", "w", "j", "h",
    ];
    let vowels = ["a", "e", "i", "o", "u", "ɛ"];
    (
        consonants.iter().map(|s| (*s).to_owned()).collect(),
        vowels.iter().map(|s| (*s).to_owned()).collect(),
    )
}

fn segments(word: &str) -> usize {
    // Dvojznaky afrikát se počítají jako jedna hláska (jako v ASJP).
    word.replace("tʃ", "C").chars().count()
}

fn spearman(xs: &[f64], ys: &[f64]) -> f64 {
    fn ranks(values: &[f64]) -> Vec<f64> {
        let mut order: Vec<usize> = (0..values.len()).collect();
        order.sort_by(|a, b| values[*a].total_cmp(&values[*b]));
        let mut rank = vec![0.0; values.len()];
        let mut i = 0;
        while i < order.len() {
            let mut j = i;
            while j + 1 < order.len() && values[order[j + 1]] == values[order[i]] {
                j += 1;
            }
            for k in i..=j {
                rank[order[k]] = (i + j) as f64 / 2.0;
            }
            i = j + 1;
        }
        rank
    }
    let (rx, ry) = (ranks(xs), ranks(ys));
    let n = rx.len() as f64;
    let (mx, my) = (rx.iter().sum::<f64>() / n, ry.iter().sum::<f64>() / n);
    let cov: f64 = rx.iter().zip(&ry).map(|(a, b)| (a - mx) * (b - my)).sum();
    let sx: f64 = rx.iter().map(|a| (a - mx).powi(2)).sum::<f64>().sqrt();
    let sy: f64 = ry.iter().map(|b| (b - my).powi(2)).sum::<f64>().sqrt();
    if sx == 0.0 || sy == 0.0 {
        0.0
    } else {
        cov / (sx * sy)
    }
}

fn generate(
    seed: u64,
    concepts: &[String],
    consonants: &[String],
    vowels: &[String],
    syllables: Option<SyllableType>,
) -> (HashMap<String, String>, HashMap<String, f64>, SyllableType) {
    let fixed = HashMap::new();
    let spec = ProtoSpec {
        concepts,
        seed,
        consonants,
        vowels,
        fixed: &fixed,
        tones: &[],
        known_frequencies: None,
        syllables,
    };
    let kind = syllable_type(&spec);
    let (forms, freqs) = protolanguage(&spec, ConceptData::shared()).unwrap();
    (forms, freqs, kind)
}

fn samples(seeds: &[u64]) {
    let concepts = default_concepts();
    let defaults = Defaults::shared();
    let (rich_c, rich_v) = rich_inventory();
    for &seed in seeds {
        for (label, c, v) in [
            (
                "výchozí inventář",
                &defaults.default_consonants,
                &defaults.default_vowels,
            ),
            ("bohatší inventář", &rich_c, &rich_v),
        ] {
            let (forms, _, kind) = generate(seed, &concepts, c, v, None);
            let words: Vec<String> = SAMPLE
                .iter()
                .map(|(concept, gloss)| format!("{gloss} *{}*", forms[*concept]))
                .collect();
            println!(
                "semínko {seed}, {label}, slabiky {}: {}",
                kind.name(),
                words.join(", ")
            );
            let fixed = HashMap::new();
            let spec = ProtoSpec {
                concepts: &concepts,
                seed,
                consonants: c,
                vowels: v,
                fixed: &fixed,
                tones: &[],
                known_frequencies: None,
                syllables: None,
            };
            let found = morphemes(&spec, 3).unwrap();
            let endings: Vec<String> = found
                .endings
                .iter()
                .map(|((class, cell), options)| {
                    let forms: Vec<String> = options.iter().map(|(e, _)| format!("-{e}")).collect();
                    format!("{class}:{cell} {}", forms.join("/"))
                })
                .collect();
            println!(
                "    koncovky {}; přípony {}",
                endings.join(", "),
                found.suffixes.join(", ")
            );
        }
    }
}

fn measure(count: u64) {
    let concepts = default_concepts();
    let data = ProtoformData::shared();
    let (consonants, vowels) = rich_inventory();
    let classes: Vec<Option<char>> = consonants
        .iter()
        .chain(&vowels)
        .map(|s| data.asjp_class(s))
        .collect();
    let symbols: Vec<String> = consonants.iter().chain(&vowels).cloned().collect();
    let mut rhos = Vec::new();
    let mut by_type: HashMap<&str, (f64, f64, f64, f64, f64, usize)> = HashMap::new();
    // (pojem, třída) → (výskyt ve slově pojmu, počet slov pojmu, výskyt jinde, počet jinde)
    let mut presence: HashMap<(String, char), (f64, f64, f64, f64)> = HashMap::new();
    let mut nursery = (0.0, 0.0, 0.0, 0.0);
    for seed in 1..=count {
        for syllables in [None] {
            let (forms, freqs, kind) = generate(seed, &concepts, &consonants, &vowels, syllables);
            let mut xs = Vec::new();
            let mut ys = Vec::new();
            let entry = by_type.entry(kind.name()).or_default();
            for concept in &concepts {
                let word = &forms[concept];
                xs.push(freqs[concept].ln());
                ys.push(segments(word) as f64);
                let first = word.chars().next().unwrap();
                let last = word.chars().last().unwrap();
                entry.0 += f64::from(u8::from("aeiouɛ".contains(first)));
                entry.1 += f64::from(u8::from(!"aeiouɛ".contains(last)));
                entry.2 += segments(word) as f64;
                entry.5 += 1;
            }
            rhos.push(spearman(&xs, &ys));
            for concept in &concepts {
                for (class, _) in data.symbolism(concept) {
                    let has = |word: &str| {
                        let word = word.replace("tʃ", "\u{1}");
                        symbols.iter().zip(&classes).any(|(s, c)| {
                            *c == Some(*class) && word.contains(&s.replace("tʃ", "\u{1}"))
                        })
                    };
                    let e = presence.entry((concept.clone(), *class)).or_default();
                    e.0 += f64::from(u8::from(has(&forms[concept])));
                    e.1 += 1.0;
                    for other in &concepts {
                        if other != concept {
                            e.2 += f64::from(u8::from(has(&forms[other])));
                            e.3 += 1.0;
                        }
                    }
                }
            }
            let nasal = |w: &str| w.contains('m') || w.contains('n') || w.contains('ŋ');
            let stop = |w: &str| w.chars().any(|c| "pbtd".contains(c));
            nursery.0 += f64::from(u8::from(nasal(&forms["mother"])));
            nursery.1 += f64::from(u8::from(nasal(&forms["father"])));
            nursery.2 += f64::from(u8::from(stop(&forms["father"])));
            nursery.3 += f64::from(u8::from(stop(&forms["mother"])));
        }
    }
    let n = count as f64;
    rhos.sort_by(f64::total_cmp);
    println!(
        "Spearman ρ(frekvence, délka): průměr {:.3}, kvartily {:.3} {:.3} {:.3}, záporné {:.0} %",
        rhos.iter().sum::<f64>() / n,
        rhos[rhos.len() / 4],
        rhos[rhos.len() / 2],
        rhos[3 * rhos.len() / 4],
        100.0 * rhos.iter().filter(|r| **r < 0.0).count() as f64 / n
    );
    println!(
        "matka s nosovkou {:.2}, otec s nosovkou {:.2}, otec s p/b/t/d {:.2}, matka s p/b/t/d {:.2}",
        nursery.0 / n,
        nursery.1 / n,
        nursery.2 / n,
        nursery.3 / n
    );
    let mut kinds: Vec<_> = by_type.iter().collect();
    kinds.sort_by_key(|(k, _)| *k);
    for (kind, (vi, cf, len, _, _, words)) in kinds {
        let w = *words as f64;
        println!(
            "{kind}: jazyků {:.0}, na samohlásku {:.3}, na souhlásku {:.3}, hlásek {:.2}",
            w / concepts.len() as f64,
            vi / w,
            cf / w,
            len / w
        );
    }
    let mut pairs: Vec<_> = presence.iter().collect();
    pairs.sort_by(|a, b| a.0.cmp(b.0));
    for ((concept, class), (a, an, b, bn)) in pairs {
        let published = data
            .symbolism(concept)
            .iter()
            .find(|(c, _)| c == class)
            .map_or(0.0, |(_, rr)| *rr);
        let rr = (a / an) / (b / bn).max(1e-9);
        println!("RR {concept}–{class}: generované {rr:.2}, Blasi {published:.2}");
    }
}

fn inventories(count: u64) {
    let root: serde_json::Value = serde_json::from_str(cee_engine::data::PROTOFORM_JSON).unwrap();
    let generated: Vec<(Vec<String>, Vec<String>)> =
        (1..=count).map(cee_engine::protoform::inventory).collect();
    let n = count as f64;
    let mean = |k: usize| {
        generated
            .iter()
            .map(|g| if k == 0 { g.0.len() } else { g.1.len() } as f64)
            .sum::<f64>()
            / n
    };
    println!("souhlásek {:.1}, samohlásek {:.1}", mean(0), mean(1));
    for check in root["inventory"]["checks"].as_array().unwrap() {
        let kind = check["kind"].as_str().unwrap();
        let target = check["segment"].as_str().unwrap();
        let given = check["given"].as_str().unwrap();
        let pick = |g: &(Vec<String>, Vec<String>)| -> Vec<String> {
            if kind == "consonants" {
                g.0.clone()
            } else {
                g.1.clone()
            }
        };
        let having: Vec<_> = generated
            .iter()
            .filter(|g| pick(g).iter().any(|s| s == given))
            .collect();
        let share = having
            .iter()
            .filter(|g| pick(g).iter().any(|s| s == target))
            .count() as f64
            / having.len().max(1) as f64;
        println!(
            "P({target} | {given}): generováno {share:.2} (z {}), PHOIBLE {:.2}",
            having.len(),
            check["share"].as_f64().unwrap()
        );
    }
    for (k, kind) in ["consonants", "vowels"].iter().enumerate() {
        let mut line = Vec::new();
        for entry in root["inventory"][*kind].as_array().unwrap().iter().take(24) {
            let ipa = entry["ipa"].as_str().unwrap();
            let share = generated
                .iter()
                .filter(|g| if k == 0 { &g.0 } else { &g.1 }.iter().any(|s| s == ipa))
                .count() as f64
                / n;
            line.push(format!(
                "{ipa} {share:.2}/{:.2}",
                entry["share"].as_f64().unwrap()
            ));
        }
        println!("podíly {kind}: {}", line.join(", "));
    }
    for seed in 1..=6 {
        let (c, v) = &generated[seed - 1];
        println!("semínko {seed}: {} | {}", c.join(" "), v.join(" "));
    }
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match args.first().map(String::as_str) {
        Some("inventare") => inventories(args.get(1).and_then(|s| s.parse().ok()).unwrap_or(2000)),
        Some("mereni") => measure(args.get(1).and_then(|s| s.parse().ok()).unwrap_or(300)),
        _ => {
            let seeds: Vec<u64> = args.iter().skip(1).filter_map(|s| s.parse().ok()).collect();
            samples(if seeds.is_empty() {
                &[1, 2, 3, 4]
            } else {
                &seeds
            });
        }
    }
}
