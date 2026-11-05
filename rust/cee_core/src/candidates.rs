//! Sady kandidátů zvukových změn z rysů tabulky hlásek: zrcadlo `cee.v2.changes.sound`
//! (`candidates()` všech rodin a `_CombinedSoundCandidates`).
//!
//! Python posílá jednou za index světa **snímek tabulky hlásek** (jména rysů, matice rysů,
//! zápis IPA, samohlásky, tóny) a čísla pevného seznamu symbolů (`symbol_list`), které rodiny
//! hledají přes `id_of`. Pro inventář pak Rust sám sestaví kandidáty všech rodin: v pořadí
//! rodin, s odstraněním duplicit podle ID proměnné (první vyhrává) a seřazené podle ID, přesně
//! jako Python. Výsledkem jsou masky (`target`, `left`, `right`, `right2` přes sloupce inventáře
//! a hranici slova), řádky přízvuku, konce rodin a pro každého kandidáta jeho **popis** (`Candidate`):
//! z něj Python na požádání (jen u skutečné inovace) postaví `Process`.
//!
//! Vzory (`Pat`) jsou předpisy, ne masky přes celou tabulku (ta má přes 23 tisíc hlásek):
//! maska se vyhodnocuje jen pro hlásky inventáře a hranici slova. Klíč procesu (`Candidate::key`)
//! se skládá z týchž částí jako `Process.key`, takže ID proměnných a pořadí sedí s Pythonem.

use std::collections::HashMap;

/// Pořadí rodin (`SOUND_CHANGES`) a jejich druhy.
pub const FAMILIES: [&str; 34] = [
    "voicing",
    "spirantization",
    "debuccalization",
    "intervocalic_loss",
    "fortition",
    "palatalization",
    "nasal_assimilation",
    "voicing_assimilation",
    "final_devoicing",
    "coda_loss",
    "cluster_simplification",
    "vowel_reduction",
    "syncope",
    "apocope",
    "vowel_shift",
    "diphthongization",
    "monophthongization",
    "glide_formation",
    "epenthesis",
    "prothesis",
    "secondary_palatalization",
    "depalatalization",
    "palatal_affrication",
    "vowel_nasalization",
    "vowel_denazalization",
    "labialization",
    "delabialization",
    "labial_shift",
    "hiatus_elision",
    "tonogenesis_onset",
    "tonogenesis_coda",
    "tone_merger",
    "tone_loss",
    "tone_dissimilation",
];

/// Hlásky, jejichž čísla (`SegmentTable.id_of`) rodiny hledají podle zápisu.
const PALATALIZABLE: [&str; 11] = ["p", "t", "k", "b", "d", "ɡ", "s", "m", "n", "l", "r"];
const NASALIZABLE: [&str; 8] = ["a", "e", "i", "o", "u", "ɛ", "ɔ", "ə"];
const VOWEL_SPACE: [&str; 13] = [
    "i", "y", "ɨ", "u", "e", "ø", "ə", "o", "ɛ", "ɔ", "a", "ɑ", "æ",
];
const TILDE: &str = "\u{303}";

/// Seznam symbolů, jejichž číslo v tabulce Rust potřebuje; Python je přeloží přes `id_of`
/// (−1, když symbol tabulka nezná) a pošle ve stejném pořadí.
pub fn symbol_list() -> Vec<String> {
    let mut out: Vec<String> = [
        "h", "j", "w", "d͡ʒ", "k", "ɡ", "t", "d", "s", "t͡ʃ", "t͡s", "d͡z", "ʃ", "m", "n", "ŋ", "p",
        "b", "l", "r", "ʔ", "kʷ", "ɡʷ",
    ]
    .iter()
    .map(|s| s.to_string())
    .collect();
    out.extend(VOWEL_SPACE.iter().map(|s| s.to_string()));
    out.extend(PALATALIZABLE.iter().map(|s| format!("{s}ʲ")));
    out.extend(NASALIZABLE.iter().map(|s| format!("{s}{TILDE}")));
    out.extend(["kʲ", "ɡʲ"].iter().map(|s| s.to_string()));
    out.sort();
    out.dedup();
    out
}

/// Snímek tabulky hlásek, který Rust potřebuje k sestavení kandidátů.
#[derive(Clone)]
pub struct SegTable {
    names: Vec<String>,
    width: usize,
    vectors: Vec<i8>,
    ipa: Vec<String>,
    /// Samohlásky podle čísla hlásky; hranice slova (poslední prvek) je nepravda.
    vowel: Vec<bool>,
    /// Kód tónu samohlásky podle čísla hlásky (0 = bez tónu).
    tone: Vec<i32>,
    /// Hláska, kterou dá `id_of(ipa[hláska])` (−1 = zápis tabulka nerozebere). Výčtová třída jedné hlásky
    /// (`_single`) se v Pythonu staví ze zápisu, takže u necelistvých zápisů (`cᶣ` → `cʷ`) je to jiná hláska.
    canon: Vec<i32>,
    boundary: u32,
    symbols: HashMap<String, i64>,
    /// Tónové značky podle kódu tónu (kód 1 je na pozici 0).
    tones: Vec<Vec<char>>,
}

impl SegTable {
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        names: Vec<String>,
        vectors: Vec<i8>,
        ipa: Vec<String>,
        vowel: Vec<bool>,
        tone: Vec<i32>,
        canon: Vec<i32>,
        symbol_ids: &[i64],
        tones: Vec<String>,
    ) -> Result<SegTable, String> {
        let width = names.len();
        let count = ipa.len();
        let symbols_expected = symbol_list();
        if width == 0
            || vectors.len() != count * width
            || vowel.len() != count + 1
            || tone.len() != count
            || canon.len() != count
            || symbol_ids.len() != symbols_expected.len()
        {
            return Err("snímek tabulky hlásek má nesouhlasné rozměry".into());
        }
        let symbols = symbols_expected
            .into_iter()
            .zip(symbol_ids.iter().copied())
            .collect();
        Ok(SegTable {
            names,
            width,
            vectors,
            ipa,
            vowel,
            tone,
            canon,
            boundary: count as u32,
            symbols,
            tones: tones.iter().map(|t| t.chars().collect()).collect(),
        })
    }

    fn feature_index(&self, name: &str) -> Result<usize, String> {
        self.names
            .iter()
            .position(|n| n == name)
            .ok_or_else(|| format!("neznámý rys {name}"))
    }

    fn feature(&self, segment: u32, index: usize) -> i8 {
        self.vectors[segment as usize * self.width + index]
    }

    fn named_feature(&self, segment: u32, name: &str) -> Result<i8, String> {
        Ok(self.feature(segment, self.feature_index(name)?))
    }

    fn id(&self, symbol: &str) -> Result<u32, String> {
        match self.symbols.get(symbol) {
            Some(&id) if id >= 0 => Ok(id as u32),
            _ => Err(format!("tabulka hlásek nezná symbol {symbol}")),
        }
    }

    fn ipa(&self, segment: u32) -> &str {
        &self.ipa[segment as usize]
    }

    fn is_vowel(&self, segment: u32) -> bool {
        self.vowel[segment as usize]
    }

    /// Hrubá mřížka samohlásky pro posuny (`SegmentTable.vowel_coordinates`).
    fn vowel_coordinates(&self, segment: u32) -> Result<(f64, f64, f64), String> {
        let hi = self.named_feature(segment, "hi")?;
        let lo = self.named_feature(segment, "lo")?;
        let mut height = if hi == 1 {
            2.0
        } else if lo == 1 {
            0.0
        } else {
            1.0
        };
        if height == 1.0 && self.named_feature(segment, "tense")? == -1 {
            height = 0.6;
        }
        let mut back = if self.named_feature(segment, "back")? == 1 {
            1.0
        } else {
            0.0
        };
        let ipa = self.ipa(segment);
        if ipa == "ə" || ipa == "ɨ" {
            back = 0.5;
        }
        let rounded = if self.named_feature(segment, "round")? == 1 {
            1.0
        } else {
            0.0
        };
        Ok((height, back, rounded))
    }

    /// Rysy, ve kterých se `target` liší od `source`, jako požadavek na výsledek (seřazené podle jména).
    fn feature_delta(&self, source: u32, target: u32) -> Result<Vec<(String, String)>, String> {
        let mut out = Vec::new();
        for (index, name) in self.names.iter().enumerate() {
            if self.feature(source, index) != self.feature(target, index) {
                out.push((name.clone(), value_symbol(self.feature(target, index))?));
            }
        }
        out.sort();
        Ok(out)
    }

    /// Hodnoty vybraných rysů hlásky jako požadavek (`SegmentTable.features_of`).
    fn features_of(&self, segment: u32, names: &[&str]) -> Result<Vec<(String, String)>, String> {
        let mut out = Vec::new();
        for name in names {
            out.push((
                name.to_string(),
                value_symbol(self.named_feature(segment, name)?)?,
            ));
        }
        out.sort();
        Ok(out)
    }

    fn tone_pitch(&self, code: i32) -> Result<(i32, i32), String> {
        let letters = self
            .tones
            .get(code as usize - 1)
            .ok_or_else(|| format!("neznámý tón {code}"))?;
        let level = |letter: char| -> i32 {
            match letter {
                '˩' => 1,
                '˨' => 2,
                '˧' => 3,
                '˦' => 4,
                _ => 5,
            }
        };
        Ok((level(letters[0]), level(letters[letters.len() - 1])))
    }

    fn tone_distance(&self, first: i32, second: i32) -> Result<i32, String> {
        let (a, b) = (self.tone_pitch(first)?, self.tone_pitch(second)?);
        Ok((a.0 - b.0).abs() + (a.1 - b.1).abs())
    }

    fn tone_letters(&self, code: i32) -> String {
        self.tones[code as usize - 1].iter().collect()
    }

    /// Kód tónu značky (`TONE_CODES`).
    fn tone_code(&self, letters: &str) -> Result<i32, String> {
        let wanted: Vec<char> = letters.chars().collect();
        self.tones
            .iter()
            .position(|t| *t == wanted)
            .map(|at| at as i32 + 1)
            .ok_or_else(|| format!("neznámá tónová značka {letters}"))
    }
}

fn value_symbol(value: i8) -> Result<String, String> {
    match value {
        1 => Ok("+".into()),
        -1 => Ok("-".into()),
        0 => Ok("0".into()),
        other => Err(format!("hodnota rysu {other} nemá znaménko")),
    }
}

/// Hodnota rysu zapsaná ve vzoru (`_value`): `+ - 0`, jinak číslo (kód tónu).
fn pattern_value(text: &str) -> Result<i8, String> {
    match text {
        "+" => Ok(1),
        "-" => Ok(-1),
        "0" => Ok(0),
        other => other
            .parse::<i8>()
            .map_err(|_| format!("hodnota rysu {other} není číslo")),
    }
}

/// Vzor hlásek jako předpis (`Pattern`): maska se vyhodnotí jen pro hlásky, které se ptají.
#[derive(Clone, Debug, PartialEq)]
pub enum Pat {
    /// `table.pattern`: hlásky s danými hodnotami rysů (seřazené podle jména), hranice slova nepatří.
    Features(Vec<(String, String)>, Vec<(usize, i8)>),
    /// `table.segments`: výčet hlásek (čísla seřazená vzestupně) a zápisy, ze kterých vznikl
    /// (z nich Python vzor postaví znovu; číslo `u32::MAX` je zápis, který tabulka nerozebere).
    Segments(Vec<u32>, Vec<String>),
    Vowel,
    Consonant,
    Boundary,
    /// Souhláska nebo hranice slova (`C|#`).
    ConsonantOrBoundary,
}

impl Pat {
    fn contains(&self, t: &SegTable, segment: u32) -> bool {
        match self {
            Pat::Features(_, resolved) => {
                segment != t.boundary
                    && resolved
                        .iter()
                        .all(|&(index, value)| t.feature(segment, index) == value)
            }
            Pat::Segments(ids, _) => ids.contains(&segment),
            Pat::Vowel => t.is_vowel(segment),
            Pat::Consonant => segment != t.boundary && !t.is_vowel(segment),
            Pat::Boundary => segment == t.boundary,
            Pat::ConsonantOrBoundary => segment == t.boundary || !t.is_vowel(segment),
        }
    }

    /// Maska vzoru přes všechny hlásky tabulky; poslední prvek je hranice slova
    /// (`Pattern.mask` v Pythonu, tak ji čeká `process::Proc`).
    pub fn mask(&self, t: &SegTable) -> Vec<bool> {
        (0..=t.boundary).map(|s| self.contains(t, s)).collect()
    }

    /// Předpis vzoru pro Python: druh, dvojice (rys, hodnota) a čísla hlásek.
    #[allow(clippy::type_complexity)]
    pub fn recipe(&self) -> (&'static str, Vec<(String, String)>, Vec<String>) {
        match self {
            Pat::Features(items, _) => ("features", items.clone(), Vec::new()),
            Pat::Segments(_, symbols) => ("segments", Vec::new(), symbols.clone()),
            Pat::Vowel => ("vowel", Vec::new(), Vec::new()),
            Pat::Consonant => ("consonant", Vec::new(), Vec::new()),
            Pat::Boundary => ("boundary", Vec::new(), Vec::new()),
            Pat::ConsonantOrBoundary => ("consonant_or_boundary", Vec::new(), Vec::new()),
        }
    }

    /// Klíč vzoru (`Pattern.key`).
    pub fn key(&self, t: &SegTable) -> String {
        let mut out = String::new();
        self.write_key(t, &mut out);
        out
    }

    /// Připíše klíč vzoru za `out` (bez mezikroků v řetězcích).
    fn write_key(&self, t: &SegTable, out: &mut String) {
        use std::fmt::Write;
        match self {
            Pat::Features(items, _) => {
                if items.is_empty() {
                    out.push('*');
                } else {
                    for (at, (name, value)) in items.iter().enumerate() {
                        if at > 0 {
                            out.push(',');
                        }
                        let _ = write!(out, "{value}{name}");
                    }
                }
            }
            Pat::Segments(ids, _) => {
                out.push('{');
                for (at, &i) in ids.iter().enumerate() {
                    if at > 0 {
                        out.push(',');
                    }
                    if i != u32::MAX {
                        out.push_str(t.ipa(i));
                    }
                }
                out.push('}');
            }
            Pat::Vowel => out.push('V'),
            Pat::Consonant => out.push('C'),
            Pat::Boundary => out.push('#'),
            Pat::ConsonantOrBoundary => out.push_str("C|#"),
        }
    }
}

/// Operace procesu (`Process.operation`); čísla jako v `process::` a `cee.v2.native.OPERATIONS`.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Operation {
    Change,
    Replace,
    Delete,
    InsertBefore,
    Merge,
    Tone,
}

impl Stress {
    pub fn name(self) -> Option<&'static str> {
        match self {
            Stress::Any => None,
            Stress::Stressed => Some("stressed"),
            Stress::Unstressed => Some("unstressed"),
        }
    }
}

impl Operation {
    pub fn name(self) -> &'static str {
        match self {
            Operation::Change => "change",
            Operation::Replace => "replace",
            Operation::Delete => "delete",
            Operation::InsertBefore => "insert_before",
            Operation::Merge => "merge_next",
            Operation::Tone => "tone",
        }
    }
}

/// Podmínka přízvuku (`Process.stress`).
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Stress {
    Any,
    Stressed,
    Unstressed,
}

/// Popis kandidáta: všechna pole `Process`, ze kterých Python na požádání postaví proces.
#[derive(Clone, Debug)]
pub struct Candidate {
    pub family: usize,
    pub label: String,
    pub target: Pat,
    pub operation: Operation,
    pub changes: Vec<(String, String)>,
    pub segment: Option<u32>,
    pub left: Option<Pat>,
    pub right: Option<Pat>,
    pub stress: Stress,
    pub medial: bool,
    pub ease: f64,
    /// `ease` je v Pythonu celé číslo `0` (posun samohlásek), ne `0.0`.
    pub ease_int: bool,
    pub clarity: f64,
    pub reductive: bool,
    pub allow: Vec<String>,
    pub right2: Option<Pat>,
    pub tone: Option<i32>,
}

impl Candidate {
    fn new(family: usize, label: String, target: Pat, operation: Operation) -> Candidate {
        Candidate {
            family,
            label,
            target,
            operation,
            changes: Vec::new(),
            segment: None,
            left: None,
            right: None,
            stress: Stress::Any,
            medial: false,
            ease: 0.0,
            ease_int: false,
            clarity: 0.0,
            reductive: false,
            allow: Vec::new(),
            right2: None,
            tone: None,
        }
    }

    fn changes(mut self, changes: &[(&str, &str)]) -> Candidate {
        self.changes = changes
            .iter()
            .map(|(n, v)| (n.to_string(), v.to_string()))
            .collect();
        self
    }

    fn change_list(mut self, changes: Vec<(String, String)>) -> Candidate {
        self.changes = changes;
        self
    }

    fn segment(mut self, segment: u32) -> Candidate {
        self.segment = Some(segment);
        self
    }

    fn left(mut self, pattern: Pat) -> Candidate {
        self.left = Some(pattern);
        self
    }

    fn right(mut self, pattern: Pat) -> Candidate {
        self.right = Some(pattern);
        self
    }

    fn right2(mut self, pattern: Pat) -> Candidate {
        self.right2 = Some(pattern);
        self
    }

    fn stress(mut self, stress: Stress) -> Candidate {
        self.stress = stress;
        self
    }

    fn medial(mut self) -> Candidate {
        self.medial = true;
        self
    }

    fn ease(mut self, ease: f64) -> Candidate {
        self.ease = ease;
        self
    }

    fn clarity(mut self, clarity: f64) -> Candidate {
        self.clarity = clarity;
        self
    }

    fn reductive(mut self) -> Candidate {
        self.reductive = true;
        self
    }

    fn allow(mut self, allow: &[&str]) -> Candidate {
        self.allow = allow.iter().map(|s| s.to_string()).collect();
        self
    }

    fn tone(mut self, code: i32) -> Candidate {
        self.tone = Some(code);
        self
    }

    /// Má některý vzor výčet s hláskou, jejíž zápis tabulka nerozebere (Python by tu selhal výjimkou)?
    fn unresolved(&self) -> bool {
        [
            Some(&self.target),
            self.left.as_ref(),
            self.right.as_ref(),
            self.right2.as_ref(),
        ]
        .into_iter()
        .flatten()
        .any(|p| matches!(p, Pat::Segments(ids, _) if ids.contains(&u32::MAX)))
    }

    /// Kanonický klíč procesu (`Process.key`).
    pub fn key(&self, t: &SegTable) -> String {
        let mut out = String::new();
        self.write_key(t, &mut out);
        out
    }

    /// Připíše kanonický klíč procesu za `out`.
    fn write_key(&self, t: &SegTable, out: &mut String) {
        use std::fmt::Write;
        out.push_str(FAMILIES[self.family]);
        out.push('|');
        self.target.write_key(t, out);
        out.push('|');
        out.push_str(self.operation.name());
        out.push('|');
        for (at, (name, value)) in self.changes.iter().enumerate() {
            if at > 0 {
                out.push(',');
            }
            let _ = write!(out, "{value}{name}");
        }
        out.push('|');
        if let Some(segment) = self.segment {
            let _ = write!(out, "{segment}");
        }
        out.push('|');
        if let Some(left) = &self.left {
            left.write_key(t, out);
        }
        out.push('|');
        if let Some(right) = &self.right {
            right.write_key(t, out);
        }
        out.push('|');
        out.push_str(self.stress.name().unwrap_or(""));
        out.push('|');
        if self.medial {
            out.push_str("medial");
        }
        if !self.allow.is_empty() || self.right2.is_some() {
            let mut allow = self.allow.clone();
            allow.sort();
            allow.dedup();
            out.push('|');
            out.push_str(&allow.join(","));
            out.push('|');
            if let Some(right2) = &self.right2 {
                right2.write_key(t, out);
            }
        }
        if let Some(tone) = self.tone {
            let _ = write!(out, "|tone{tone}");
        }
    }
}

/// Sada kandidátů pro inventář: kandidáti všech rodin za sebou, konce rodin a ID proměnných.
pub struct Built {
    pub candidates: Vec<Candidate>,
    /// ID proměnné každého kandidáta (`process:` + klíč procesu).
    pub ids: Vec<String>,
    pub family_ends: Vec<usize>,
}

/// Pomocník sestavování: tabulka a inventář.
struct Maker<'a> {
    t: &'a SegTable,
    inventory: &'a [u32],
}

type Found = Result<Vec<Candidate>, String>;

impl<'a> Maker<'a> {
    fn pattern(&self, items: &[(&str, &str)]) -> Result<Pat, String> {
        let mut sorted: Vec<(String, String)> = items
            .iter()
            .map(|(n, v)| (n.to_string(), v.to_string()))
            .collect();
        sorted.sort();
        let mut resolved = Vec::new();
        for (name, value) in &sorted {
            resolved.push((self.t.feature_index(name)?, pattern_value(value)?));
        }
        Ok(Pat::Features(sorted, resolved))
    }

    fn segments(&self, symbols: &[&str]) -> Result<Pat, String> {
        let mut ids = Vec::new();
        for symbol in symbols {
            ids.push(self.t.id(symbol)?);
        }
        ids.sort_unstable();
        Ok(Pat::Segments(
            ids,
            symbols.iter().map(|s| s.to_string()).collect(),
        ))
    }

    /// Výčtová třída jedné hlásky (`_single`): z jejího zápisu, jako v Pythonu.
    fn single(&self, segment: u32) -> Pat {
        let canon = self.t.canon[segment as usize];
        let id = if canon >= 0 { canon as u32 } else { u32::MAX };
        Pat::Segments(vec![id], vec![self.t.ipa(segment).to_string()])
    }

    fn has(&self, segment: u32) -> bool {
        self.inventory.contains(&segment)
    }

    /// Hlásky inventáře, které vzor obsahuje (`_present`).
    fn present(&self, pattern: &Pat) -> Vec<u32> {
        self.inventory
            .iter()
            .copied()
            .filter(|&s| pattern.contains(self.t, s))
            .collect()
    }

    fn vowels(&self) -> Vec<u32> {
        self.inventory
            .iter()
            .copied()
            .filter(|&s| self.t.is_vowel(s))
            .collect()
    }

    fn ipa(&self, segment: u32) -> &str {
        self.t.ipa(segment)
    }

    fn epenthetic_vowel(&self) -> Result<u32, String> {
        for symbol in ["ə", "e", "i", "a"] {
            let segment = self.t.id(symbol)?;
            if self.has(segment) {
                return Ok(segment);
            }
        }
        self.t.id("e")
    }

    fn tones_present(&self) -> Vec<i32> {
        let mut found: Vec<i32> = self
            .inventory
            .iter()
            .filter(|&&s| self.t.is_vowel(s))
            .map(|&s| self.t.tone[s as usize])
            .filter(|&code| code != 0)
            .collect();
        found.sort_unstable();
        found.dedup();
        found
    }

    fn toneless(&self) -> Result<Pat, String> {
        self.pattern(&[("syl", "+"), ("x_tone", "0")])
    }

    fn with_tone(&self, code: i32) -> Result<Pat, String> {
        let text = code.to_string();
        self.pattern(&[("syl", "+"), ("x_tone", text.as_str())])
    }
}

const CONSONANT_CLASSES: [(&str, &[(&str, &str)]); 4] = [
    ("okluzivy", &[("syl", "-"), ("son", "-"), ("cont", "-")]),
    ("nazály", &[("syl", "-"), ("nas", "+")]),
    ("frikativy", &[("syl", "-"), ("son", "-"), ("cont", "+")]),
    (
        "likvidy",
        &[("syl", "-"), ("son", "+"), ("cons", "+"), ("nas", "-")],
    ),
];

fn voicing(m: &Maker<'_>, f: usize) -> Found {
    let stops = m.pattern(&[("syl", "-"), ("son", "-"), ("voi", "-")])?;
    let make = |target: Pat, label: String| {
        Candidate::new(f, label, target, Operation::Change)
            .changes(&[("voi", "+")])
            .left(Pat::Vowel)
            .right(Pat::Vowel)
            .ease(0.15)
            .clarity(-0.1)
            .reductive()
    };
    let mut found: Vec<Candidate> = m
        .present(&stops)
        .into_iter()
        .map(|s| make(m.single(s), format!("{} → zněle /V_V", m.ipa(s))))
        .collect();
    let series = m.pattern(&[("syl", "-"), ("son", "-"), ("voi", "-"), ("cont", "-")])?;
    if m.present(&series).len() >= 2 {
        found.push(make(series, "řada neznělých okluziv → zněle /V_V".into()));
    }
    Ok(found)
}

fn spirantization(m: &Maker<'_>, f: usize) -> Found {
    let stops = m.pattern(&[("syl", "-"), ("son", "-"), ("cont", "-"), ("delrel", "-")])?;
    let make = |target: Pat, label: String| {
        Candidate::new(f, label, target, Operation::Change)
            .changes(&[("cont", "+"), ("strid", "-")])
            .left(Pat::Vowel)
            .right(Pat::Vowel)
            .ease(0.15)
            .clarity(-0.15)
            .reductive()
    };
    let mut found: Vec<Candidate> = m
        .present(&stops)
        .into_iter()
        .map(|s| make(m.single(s), format!("{} → frikativa /V_V", m.ipa(s))))
        .collect();
    let voiced = m.pattern(&[
        ("syl", "-"),
        ("son", "-"),
        ("cont", "-"),
        ("delrel", "-"),
        ("voi", "+"),
    ])?;
    if m.present(&voiced).len() >= 2 {
        found.push(make(voiced, "řada znělých okluziv → frikativy /V_V".into()));
    }
    Ok(found)
}

fn debuccalization(m: &Maker<'_>, f: usize) -> Found {
    let h = m.t.id("h")?;
    let fricatives = m.pattern(&[("syl", "-"), ("son", "-"), ("cont", "+"), ("voi", "-")])?;
    let mut found = Vec::new();
    for s in m.present(&fricatives) {
        if s == h {
            continue;
        }
        for (left, right, place) in [
            (Pat::Vowel, Pat::Vowel, "V_V"),
            (Pat::Vowel, Pat::Boundary, "V_#"),
        ] {
            found.push(
                Candidate::new(
                    f,
                    format!("{} → h /{place}", m.ipa(s)),
                    m.single(s),
                    Operation::Replace,
                )
                .segment(h)
                .left(left)
                .right(right)
                .ease(0.125)
                .clarity(-0.2)
                .reductive(),
            );
        }
    }
    Ok(found)
}

fn intervocalic_loss(m: &Maker<'_>, f: usize) -> Found {
    let mut found = Vec::new();
    for &s in m.inventory {
        if m.t.is_vowel(s) {
            continue;
        }
        let ipa = m.ipa(s);
        let weak = ipa == "h"
            || ipa == "j"
            || ipa == "w"
            || (m.t.named_feature(s, "cont")? == 1
                && m.t.named_feature(s, "voi")? == 1
                && m.t.named_feature(s, "son")? != 1
                && m.t.named_feature(s, "strid")? != 1);
        if weak {
            found.push(
                Candidate::new(f, format!("{ipa} → ∅ /V_V"), m.single(s), Operation::Delete)
                    .left(Pat::Vowel)
                    .right(Pat::Vowel)
                    .ease(0.15)
                    .clarity(-0.4)
                    .reductive(),
            );
        }
    }
    Ok(found)
}

fn fortition(m: &Maker<'_>, f: usize) -> Found {
    let mut found = Vec::new();
    let fricatives = m.pattern(&[("syl", "-"), ("son", "-"), ("cont", "+"), ("voi", "+")])?;
    for s in m.present(&fricatives) {
        found.push(
            Candidate::new(
                f,
                format!("{} → okluziva /#_", m.ipa(s)),
                m.single(s),
                Operation::Change,
            )
            .changes(&[("cont", "-"), ("strid", "-"), ("delrel", "-")])
            .left(Pat::Boundary)
            .ease(-0.1)
            .clarity(0.3),
        );
    }
    if m.has(m.t.id("j")?) {
        found.push(
            Candidate::new(
                f,
                "j → d͡ʒ /#_".into(),
                m.segments(&["j"])?,
                Operation::Replace,
            )
            .segment(m.t.id("d͡ʒ")?)
            .left(Pat::Boundary)
            .ease(-0.1)
            .clarity(0.3),
        );
    }
    Ok(found)
}

fn palatalization(m: &Maker<'_>, f: usize) -> Found {
    let place = [
        "cor", "ant", "distr", "hi", "lo", "back", "delrel", "strid", "lab",
    ];
    let front = m.pattern(&[("hi", "+"), ("back", "-")])?;
    let outputs: [(&str, &str, &[&str]); 5] = [
        ("k", "t͡ʃ", &place),
        ("ɡ", "d͡ʒ", &place),
        ("t", "t͡s", &place),
        ("d", "d͡z", &place),
        ("s", "ʃ", &["ant", "distr", "cor"]),
    ];
    let mut resolved = Vec::new();
    for (symbol, output, names) in outputs {
        resolved.push((symbol, m.t.features_of(m.t.id(output)?, names)?));
    }
    let mut found = Vec::new();
    for (symbol, changes) in resolved {
        let segment = m.t.id(symbol)?;
        if m.has(segment) {
            found.push(
                Candidate::new(
                    f,
                    format!("{symbol} → palatála /_i"),
                    m.single(segment),
                    Operation::Change,
                )
                .change_list(changes)
                .right(front.clone())
                .ease(0.15)
                .clarity(0.0)
                .reductive(),
            );
        }
    }
    Ok(found)
}

fn nasal_assimilation(m: &Maker<'_>, f: usize) -> Found {
    let nasals = m.present(&m.pattern(&[("nas", "+"), ("syl", "-")])?);
    let places = [
        ("m", m.pattern(&[("syl", "-"), ("son", "-"), ("lab", "+")])?),
        ("n", m.pattern(&[("syl", "-"), ("son", "-"), ("cor", "+")])?),
        (
            "ŋ",
            m.pattern(&[("syl", "-"), ("son", "-"), ("hi", "+"), ("back", "+")])?,
        ),
    ];
    let mut found = Vec::new();
    for nasal in nasals {
        for (symbol, before) in &places {
            let output = m.t.id(symbol)?;
            if output != nasal {
                found.push(
                    Candidate::new(
                        f,
                        format!("{} → {symbol} před homorganní okluzivou", m.ipa(nasal)),
                        m.single(nasal),
                        Operation::Replace,
                    )
                    .segment(output)
                    .right(before.clone())
                    .ease(0.2)
                    .clarity(-0.05),
                );
            }
        }
    }
    Ok(found)
}

fn voicing_assimilation(m: &Maker<'_>, f: usize) -> Found {
    let mut found = Vec::new();
    for (value, opposite) in [("+", "-"), ("-", "+")] {
        let target = m.pattern(&[("syl", "-"), ("son", "-"), ("voi", opposite)])?;
        if !m.present(&target).is_empty() {
            found.push(
                Candidate::new(
                    f,
                    format!("obstruent → {value}zněle před {value}znělým"),
                    target,
                    Operation::Change,
                )
                .changes(&[("voi", value)])
                .right(m.pattern(&[("syl", "-"), ("son", "-"), ("voi", value)])?)
                .ease(0.15)
                .clarity(-0.05),
            );
        }
    }
    Ok(found)
}

fn final_devoicing(m: &Maker<'_>, f: usize) -> Found {
    let target = m.pattern(&[("syl", "-"), ("son", "-"), ("voi", "+")])?;
    if m.present(&target).is_empty() {
        return Ok(Vec::new());
    }
    Ok(vec![Candidate::new(
        f,
        "znělý obstruent → nezněle /_#".into(),
        target,
        Operation::Change,
    )
    .changes(&[("voi", "-")])
    .right(Pat::Boundary)
    .ease(0.1)
    .clarity(-0.1)])
}

fn coda_loss(m: &Maker<'_>, f: usize) -> Found {
    let mut found = Vec::new();
    for (name, features) in CONSONANT_CLASSES {
        let pattern = m.pattern(features)?;
        let present = m.present(&pattern);
        let make = |target: Pat, label: String| {
            Candidate::new(f, label, target, Operation::Delete)
                .left(Pat::Vowel)
                .right(Pat::Boundary)
                .ease(0.15)
                .clarity(-0.3)
                .reductive()
        };
        if !present.is_empty() {
            found.push(make(pattern, format!("{name} → ∅ /V_#")));
        }
        for segment in present {
            found.push(make(
                m.single(segment),
                format!("{} → ∅ /V_#", m.ipa(segment)),
            ));
        }
    }
    Ok(found)
}

fn cluster_simplification(m: &Maker<'_>, f: usize) -> Found {
    let mut found = Vec::new();
    for (name, features) in CONSONANT_CLASSES {
        let pattern = m.pattern(features)?;
        if !m.present(&pattern).is_empty() {
            found.push(
                Candidate::new(f, format!("{name} → ∅ /V_C"), pattern, Operation::Delete)
                    .left(Pat::Vowel)
                    .right(Pat::Consonant)
                    .ease(0.15)
                    .clarity(-0.2)
                    .reductive(),
            );
        }
    }
    Ok(found)
}

fn vowel_reduction(m: &Maker<'_>, f: usize) -> Found {
    let schwa = m.t.id("ə")?;
    let make = |target: Pat, label: String| {
        Candidate::new(f, label, target, Operation::Replace)
            .segment(schwa)
            .stress(Stress::Unstressed)
            .ease(0.15)
            .clarity(-0.2)
            .reductive()
    };
    let mut found: Vec<Candidate> = m
        .vowels()
        .into_iter()
        .filter(|&v| v != schwa)
        .map(|v| {
            make(
                m.single(v),
                format!("{} → ə v nepřízvučné slabice", m.ipa(v)),
            )
        })
        .collect();
    found.push(make(
        m.pattern(&[("syl", "+"), ("hi", "-")])?,
        "nevysoké vokály → ə v nepřízvučné slabice".into(),
    ));
    Ok(found)
}

/// Ztráta akustických vodítek při smazání nepřízvučného plného vokálu a šva.
const CLARITY_DELETE_FULL: f64 = -0.15;
const CLARITY_DELETE_SCHWA: f64 = -0.05;

fn syncope(m: &Maker<'_>, f: usize) -> Found {
    let schwa = m.t.id("ə")?;
    let make = |target: Pat, label: String, clarity: f64| {
        Candidate::new(f, label, target, Operation::Delete)
            .left(Pat::Consonant)
            .right(Pat::Consonant)
            .stress(Stress::Unstressed)
            .medial()
            .ease(0.15)
            .clarity(clarity)
            .reductive()
    };
    let mut found: Vec<Candidate> = m
        .vowels()
        .into_iter()
        .map(|v| {
            make(
                m.single(v),
                format!("{} → ∅ /C_C nepřízvučně", m.ipa(v)),
                if v == schwa {
                    CLARITY_DELETE_SCHWA
                } else {
                    CLARITY_DELETE_FULL
                },
            )
        })
        .collect();
    found.push(make(
        m.pattern(&[("syl", "+"), ("hi", "+")])?,
        "vysoké vokály → ∅ /C_C nepřízvučně".into(),
        CLARITY_DELETE_FULL,
    ));
    Ok(found)
}

fn apocope(m: &Maker<'_>, f: usize) -> Found {
    let schwa = m.t.id("ə")?;
    let make = |target: Pat, label: String, clarity: f64| {
        Candidate::new(f, label, target, Operation::Delete)
            .left(Pat::Consonant)
            .right(Pat::Boundary)
            .stress(Stress::Unstressed)
            .ease(0.15)
            .clarity(clarity)
            .reductive()
    };
    let mut found: Vec<Candidate> = m
        .vowels()
        .into_iter()
        .map(|v| {
            make(
                m.single(v),
                format!("{} → ∅ /C_# nepřízvučně", m.ipa(v)),
                if v == schwa {
                    CLARITY_DELETE_SCHWA
                } else {
                    CLARITY_DELETE_FULL
                },
            )
        })
        .collect();
    found.push(make(
        Pat::Vowel,
        "vokály → ∅ /C_# nepřízvučně".into(),
        CLARITY_DELETE_FULL,
    ));
    Ok(found)
}

/// Eliza v hiátu: z dvou samohlásek vedle sebe zmizí jedna nepřízvučná. Hiát řeší většina
/// jazyků a nejčastěji elizí (Casali 1997, Vowel elision in hiatus contexts, Language 73,
/// 493–533). V1 (`V → ∅ /_V`) i V2 na konci slova (`V → ∅ /V_#`); přízvučná samohláska
/// se drží, takže v `la-i` s přízvukem na `la` zmizí koncové `i`. Na rozdíl od apokopy
/// (`/C_#`) dosáhne na koncovky za samohláskou.
fn hiatus_elision(m: &Maker<'_>, f: usize) -> Found {
    let schwa = m.t.id("ə")?;
    let clarity = |v: u32| {
        if v == schwa {
            CLARITY_DELETE_SCHWA
        } else {
            CLARITY_DELETE_FULL
        }
    };
    let before = |target: Pat, label: String, clarity: f64| {
        Candidate::new(f, label, target, Operation::Delete)
            .right(Pat::Vowel)
            .stress(Stress::Unstressed)
            .ease(0.15)
            .clarity(clarity)
            .reductive()
    };
    let after = |target: Pat, label: String, clarity: f64| {
        Candidate::new(f, label, target, Operation::Delete)
            .left(Pat::Vowel)
            .right(Pat::Boundary)
            .stress(Stress::Unstressed)
            .ease(0.15)
            .clarity(clarity)
            .reductive()
    };
    let mut found = Vec::new();
    for v in m.vowels() {
        found.push(before(
            m.single(v),
            format!("{} → ∅ /_V nepřízvučně", m.ipa(v)),
            clarity(v),
        ));
        found.push(after(
            m.single(v),
            format!("{} → ∅ /V_# nepřízvučně", m.ipa(v)),
            clarity(v),
        ));
    }
    found.push(before(
        Pat::Vowel,
        "vokály → ∅ /_V nepřízvučně".into(),
        CLARITY_DELETE_FULL,
    ));
    found.push(after(
        Pat::Vowel,
        "vokály → ∅ /V_# nepřízvučně".into(),
        CLARITY_DELETE_FULL,
    ));
    Ok(found)
}

fn vowel_shift(m: &Maker<'_>, f: usize) -> Found {
    let mut space = Vec::new();
    for symbol in VOWEL_SPACE {
        space.push(m.t.id(symbol)?);
    }
    let mut found = Vec::new();
    for vowel in m.vowels() {
        if !space.contains(&vowel) {
            continue;
        }
        let origin = m.t.vowel_coordinates(vowel)?;
        for &other in &space {
            if other == vowel {
                continue;
            }
            let target = m.t.vowel_coordinates(other)?;
            let steps = [
                (origin.0 - target.0).abs(),
                (origin.1 - target.1).abs(),
                (origin.2 - target.2).abs(),
            ];
            let changed = steps.iter().filter(|&&step| step > 0.0).count();
            let largest = steps.iter().copied().fold(f64::NEG_INFINITY, f64::max);
            // Jeden krok v jediném rozměru: sousední vokál, ne skok přes systém.
            if changed != 1 || largest > 1.0 {
                continue;
            }
            for (stress, place) in [
                (Stress::Any, "všude"),
                (Stress::Stressed, "v přízvučné slabice"),
            ] {
                let mut candidate = Candidate::new(
                    f,
                    format!("{} → {} {place}", m.ipa(vowel), m.ipa(other)),
                    m.single(vowel),
                    Operation::Replace,
                )
                .segment(other)
                .stress(stress)
                .clarity(0.0);
                candidate.ease_int = true;
                found.push(candidate);
            }
        }
    }
    Ok(found)
}

fn diphthongization(m: &Maker<'_>, f: usize) -> Found {
    let mut found = Vec::new();
    for (symbol, glide) in [("e", "j"), ("ɛ", "j"), ("o", "w"), ("ɔ", "w")] {
        let segment = m.t.id(symbol)?;
        if m.has(segment) {
            found.push(
                Candidate::new(
                    f,
                    format!("{symbol} → {glide}{symbol} v přízvučné slabice"),
                    m.single(segment),
                    Operation::InsertBefore,
                )
                .segment(m.t.id(glide)?)
                .stress(Stress::Stressed)
                .ease(-0.05)
                .clarity(0.2),
            );
        }
    }
    Ok(found)
}

fn monophthongization(m: &Maker<'_>, f: usize) -> Found {
    let mut found = Vec::new();
    for (first, second, output) in [
        ("a", "i", "e"),
        ("a", "u", "o"),
        ("e", "i", "i"),
        ("o", "u", "u"),
        ("o", "i", "ø"),
        ("a", "e", "ɛ"),
    ] {
        let (a, b) = (m.t.id(first)?, m.t.id(second)?);
        if m.has(a) && m.has(b) {
            found.push(
                Candidate::new(
                    f,
                    format!("{first}{second} → {output}"),
                    m.single(a),
                    Operation::Merge,
                )
                .segment(m.t.id(output)?)
                .right(m.single(b))
                .ease(0.15)
                .clarity(-0.1),
            );
        }
    }
    Ok(found)
}

fn glide_formation(m: &Maker<'_>, f: usize) -> Found {
    let mut found = Vec::new();
    for (vowel, glide) in [("i", "j"), ("u", "w")] {
        let segment = m.t.id(vowel)?;
        if m.has(segment) {
            found.push(
                Candidate::new(
                    f,
                    format!("{vowel} → {glide} /_V"),
                    m.single(segment),
                    Operation::Replace,
                )
                .segment(m.t.id(glide)?)
                .right(Pat::Vowel)
                .ease(0.1)
                .clarity(-0.05),
            );
        }
    }
    Ok(found)
}

fn epenthesis(m: &Maker<'_>, f: usize) -> Found {
    let vowel = m.epenthetic_vowel()?;
    Ok(vec![Candidate::new(
        f,
        format!("∅ → {} /C_C#", m.ipa(vowel)),
        Pat::Consonant,
        Operation::InsertBefore,
    )
    .segment(vowel)
    .left(Pat::Consonant)
    .right(Pat::Boundary)
    .ease(-0.1)
    .clarity(0.2)])
}

fn prothesis(m: &Maker<'_>, f: usize) -> Found {
    let s = m.t.id("s")?;
    if !m.has(s) {
        return Ok(Vec::new());
    }
    let e = m.t.id("e")?;
    let vowel = if m.has(e) { e } else { m.epenthetic_vowel()? };
    Ok(vec![Candidate::new(
        f,
        format!("∅ → {} /#_sC", m.ipa(vowel)),
        m.segments(&["s"])?,
        Operation::InsertBefore,
    )
    .segment(vowel)
    .left(Pat::Boundary)
    .right(Pat::Consonant)
    .ease(-0.05)
    .clarity(0.1)])
}

fn secondary_palatalization(m: &Maker<'_>, f: usize) -> Found {
    let front = m.segments(&["i", "j"])?;
    let mut found = Vec::new();
    for symbol in PALATALIZABLE {
        let (src, dst) = (m.t.id(symbol)?, m.t.id(&format!("{symbol}ʲ"))?);
        if m.has(src) && src != dst {
            found.push(
                Candidate::new(
                    f,
                    format!("{symbol} → {symbol}ʲ /_i,j"),
                    m.single(src),
                    Operation::Change,
                )
                .change_list(m.t.feature_delta(src, dst)?)
                .allow(&["ʲ"])
                .right(front.clone())
                .ease(0.1),
            );
        }
    }
    Ok(found)
}

fn depalatalization(m: &Maker<'_>, f: usize) -> Found {
    let mut found = Vec::new();
    for symbol in PALATALIZABLE {
        let marked = m.t.id(&format!("{symbol}ʲ"))?;
        if m.has(marked) {
            found.push(
                Candidate::new(
                    f,
                    format!("{symbol}ʲ → {symbol}"),
                    m.single(marked),
                    Operation::Replace,
                )
                .segment(m.t.id(symbol)?)
                .ease(0.1),
            );
        }
    }
    Ok(found)
}

fn palatal_affrication(m: &Maker<'_>, f: usize) -> Found {
    let mut found = Vec::new();
    for (src, dst) in [("kʲ", "t͡ʃ"), ("ɡʲ", "d͡ʒ")] {
        let source = m.t.id(src)?;
        if m.has(source) {
            found.push(
                Candidate::new(
                    f,
                    format!("{src} → {dst}"),
                    m.single(source),
                    Operation::Replace,
                )
                .segment(m.t.id(dst)?)
                .ease(0.05),
            );
        }
    }
    Ok(found)
}

fn vowel_nasalization(m: &Maker<'_>, f: usize) -> Found {
    let nasal = m.pattern(&[("nas", "+"), ("syl", "-")])?;
    let mut found = Vec::new();
    for symbol in NASALIZABLE {
        let (src, dst) = (m.t.id(symbol)?, m.t.id(&format!("{symbol}{TILDE}"))?);
        if m.has(src) && src != dst {
            found.push(
                Candidate::new(
                    f,
                    format!("{symbol} → {symbol}{TILDE} /_N(C|#)"),
                    m.single(src),
                    Operation::Change,
                )
                .change_list(m.t.feature_delta(src, dst)?)
                .allow(&[TILDE])
                .right(nasal.clone())
                .right2(Pat::ConsonantOrBoundary)
                .ease(0.1)
                .reductive(),
            );
        }
    }
    Ok(found)
}

fn vowel_denazalization(m: &Maker<'_>, f: usize) -> Found {
    let mut found = Vec::new();
    for symbol in NASALIZABLE {
        let nasal = m.t.id(&format!("{symbol}{TILDE}"))?;
        if m.has(nasal) {
            found.push(
                Candidate::new(
                    f,
                    format!("{symbol}{TILDE} → {symbol}"),
                    m.single(nasal),
                    Operation::Replace,
                )
                .segment(m.t.id(symbol)?)
                .ease(0.1),
            );
        }
    }
    Ok(found)
}

fn labialization(m: &Maker<'_>, f: usize) -> Found {
    let mut found = Vec::new();
    for symbol in ["k", "ɡ"] {
        let (src, dst) = (m.t.id(symbol)?, m.t.id(&format!("{symbol}ʷ"))?);
        if m.has(src) && src != dst {
            found.push(
                Candidate::new(
                    f,
                    format!("{symbol} → {symbol}ʷ /_u,w"),
                    m.single(src),
                    Operation::Change,
                )
                .change_list(m.t.feature_delta(src, dst)?)
                .allow(&["ʷ"])
                .right(m.segments(&["u", "w"])?)
                .ease(0.1),
            );
        }
    }
    Ok(found)
}

fn delabialization(m: &Maker<'_>, f: usize) -> Found {
    let mut found = Vec::new();
    for symbol in ["k", "ɡ"] {
        let marked = m.t.id(&format!("{symbol}ʷ"))?;
        if m.has(marked) {
            found.push(
                Candidate::new(
                    f,
                    format!("{symbol}ʷ → {symbol}"),
                    m.single(marked),
                    Operation::Replace,
                )
                .segment(m.t.id(symbol)?)
                .ease(0.1),
            );
        }
    }
    Ok(found)
}

fn labial_shift(m: &Maker<'_>, f: usize) -> Found {
    let mut found = Vec::new();
    for (src, dst) in [("kʷ", "p"), ("ɡʷ", "b")] {
        let source = m.t.id(src)?;
        if m.has(source) {
            found.push(
                Candidate::new(
                    f,
                    format!("{src} → {dst}"),
                    m.single(source),
                    Operation::Replace,
                )
                .segment(m.t.id(dst)?)
                .ease(0.05),
            );
        }
    }
    Ok(found)
}

fn tone_from_onset(m: &Maker<'_>, f: usize) -> Found {
    let toneless = m.toneless()?;
    if m.present(&toneless).is_empty() {
        return Ok(Vec::new());
    }
    let mut found = Vec::new();
    for (voice, tone, name) in [("-", "˦", "T"), ("+", "˨", "D")] {
        let onset = m.pattern(&[("syl", "-"), ("son", "-"), ("voi", voice)])?;
        if !m.present(&onset).is_empty() {
            found.push(
                Candidate::new(
                    f,
                    format!("V → V{tone} /{name}_"),
                    toneless.clone(),
                    Operation::Tone,
                )
                .tone(m.t.tone_code(tone)?)
                .left(onset)
                .ease(0.0)
                .clarity(0.1),
            );
        }
    }
    Ok(found)
}

fn tone_from_coda(m: &Maker<'_>, f: usize) -> Found {
    let toneless = m.toneless()?;
    if m.present(&toneless).is_empty() {
        return Ok(Vec::new());
    }
    let mut found = Vec::new();
    for (coda, tone) in [("ʔ", "˧˥"), ("h", "˥˩"), ("s", "˥˩")] {
        let segment = m.t.id(coda)?;
        if m.has(segment) {
            found.push(
                Candidate::new(
                    f,
                    format!("V → V{tone} /_{coda}#"),
                    toneless.clone(),
                    Operation::Tone,
                )
                .tone(m.t.tone_code(tone)?)
                .right(m.single(segment))
                .right2(Pat::Boundary)
                .ease(0.0)
                .clarity(0.1),
            );
        }
    }
    Ok(found)
}

fn tone_merger(m: &Maker<'_>, f: usize) -> Found {
    let present = m.tones_present();
    let mut found = Vec::new();
    for &a in &present {
        for &b in &present {
            if a != b && m.t.tone_distance(a, b)? <= 2 {
                found.push(
                    Candidate::new(
                        f,
                        format!("{} → {}", m.t.tone_letters(a), m.t.tone_letters(b)),
                        m.with_tone(a)?,
                        Operation::Tone,
                    )
                    .tone(b)
                    .ease(0.1)
                    .clarity(-0.15),
                );
            }
        }
    }
    Ok(found)
}

fn tone_loss(m: &Maker<'_>, f: usize) -> Found {
    let mut found = Vec::new();
    for a in m.tones_present() {
        found.push(
            Candidate::new(
                f,
                format!("{} → ∅", m.t.tone_letters(a)),
                m.with_tone(a)?,
                Operation::Tone,
            )
            .tone(0)
            .ease(0.1)
            .clarity(-0.2),
        );
    }
    Ok(found)
}

fn tone_dissimilation(m: &Maker<'_>, f: usize) -> Found {
    let present = m.tones_present();
    let mut found = Vec::new();
    for &tone in &present {
        let mut nearest: Option<(i32, i32)> = None;
        for &other in present.iter().filter(|&&o| o != tone) {
            let key = (m.t.tone_distance(tone, other)?, other);
            if nearest.is_none_or(|best| key < best) {
                nearest = Some(key);
            }
        }
        let Some((_, nearest)) = nearest else {
            continue;
        };
        found.push(
            Candidate::new(
                f,
                format!(
                    "{} → {} /_C{}",
                    m.t.tone_letters(tone),
                    m.t.tone_letters(nearest),
                    m.t.tone_letters(tone)
                ),
                m.with_tone(tone)?,
                Operation::Tone,
            )
            .tone(nearest)
            .right(Pat::Consonant)
            .right2(m.with_tone(tone)?)
            .ease(0.05)
            .clarity(0.05),
        );
    }
    Ok(found)
}

type Family = for<'a> fn(&Maker<'a>, usize) -> Found;

const BUILDERS: [Family; 34] = [
    voicing,
    spirantization,
    debuccalization,
    intervocalic_loss,
    fortition,
    palatalization,
    nasal_assimilation,
    voicing_assimilation,
    final_devoicing,
    coda_loss,
    cluster_simplification,
    vowel_reduction,
    syncope,
    apocope,
    vowel_shift,
    diphthongization,
    monophthongization,
    glide_formation,
    epenthesis,
    prothesis,
    secondary_palatalization,
    depalatalization,
    palatal_affrication,
    vowel_nasalization,
    vowel_denazalization,
    labialization,
    delabialization,
    labial_shift,
    hiatus_elision,
    tone_from_onset,
    tone_from_coda,
    tone_merger,
    tone_loss,
    tone_dissimilation,
];

/// Kandidáti všech rodin pro inventář: v pořadí rodin, bez duplicit podle ID proměnné
/// (první vyhrává) a v rodině seřazení podle ID (`_CombinedSoundCandidates`).
pub fn build(t: &SegTable, inventory: &[u32]) -> Result<Built, String> {
    let maker = Maker { t, inventory };
    let mut candidates = Vec::new();
    let mut ids = Vec::new();
    let mut family_ends = Vec::with_capacity(FAMILIES.len());
    for (family, builder) in BUILDERS.iter().enumerate() {
        let mut keyed: Vec<(String, Candidate)> = Vec::new();
        let mut seen: std::collections::HashSet<String> = std::collections::HashSet::new();
        for candidate in builder(&maker, family)? {
            if candidate.unresolved() {
                return Err("zápis hlásky v inventáři tabulka nerozebere".into());
            }
            let mut id = String::from("process:");
            candidate.write_key(t, &mut id);
            // První vyhrává; duplicity se hlídají hašovací sadou, ne průchodem celého seznamu.
            if seen.insert(id.clone()) {
                keyed.push((id, candidate));
            }
        }
        keyed.sort_unstable_by(|a, b| a.0.cmp(&b.0));
        for (id, candidate) in keyed {
            ids.push(id);
            candidates.push(candidate);
        }
        family_ends.push(candidates.len());
    }
    Ok(Built {
        candidates,
        ids,
        family_ends,
    })
}

/// Masky kandidátů přes sloupce hlásek (inventář a hranice slova, seřazené) po řádcích kandidátů
/// (`_Columns` v Pythonu).
pub struct Masks {
    pub columns: Vec<u32>,
    pub target: Vec<bool>,
    pub left: Vec<bool>,
    pub right: Vec<bool>,
    /// Maska druhé následující hlásky jen pro kandidáty, které ji mají (řádky v `right2_rows`).
    pub right2: Vec<bool>,
    pub right2_rows: Vec<i64>,
    pub stressed_rows: Vec<i64>,
    pub unstressed_rows: Vec<i64>,
}

pub fn masks(t: &SegTable, inventory: &[u32], built: &Built) -> Masks {
    let mut columns: Vec<u32> = inventory.to_vec();
    columns.push(t.boundary);
    columns.sort_unstable();
    columns.dedup();
    let width = columns.len();
    let rows = built.candidates.len();
    let mut out = Masks {
        columns: columns.clone(),
        target: Vec::with_capacity(rows * width),
        left: Vec::with_capacity(rows * width),
        right: Vec::with_capacity(rows * width),
        right2: Vec::new(),
        right2_rows: Vec::new(),
        stressed_rows: Vec::new(),
        unstressed_rows: Vec::new(),
    };
    for (row, candidate) in built.candidates.iter().enumerate() {
        out.target
            .extend(columns.iter().map(|&s| candidate.target.contains(t, s)));
        for (pattern, mask) in [
            (&candidate.left, &mut out.left),
            (&candidate.right, &mut out.right),
        ] {
            match pattern {
                None => mask.extend(std::iter::repeat_n(true, width)),
                Some(pattern) => mask.extend(columns.iter().map(|&s| pattern.contains(t, s))),
            }
        }
        if let Some(pattern) = &candidate.right2 {
            out.right2_rows.push(row as i64);
            out.right2
                .extend(columns.iter().map(|&s| pattern.contains(t, s)));
        }
        match candidate.stress {
            Stress::Stressed => out.stressed_rows.push(row as i64),
            Stress::Unstressed => out.unstressed_rows.push(row as i64),
            Stress::Any => {}
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Malá tabulka: 0 = p, 1 = b, 2 = a, 3 = i, 4 = ə; rysy syl, son, voi, hi.
    fn table() -> SegTable {
        let names: Vec<String> = ["syl", "son", "voi", "hi", "cont", "x_tone"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        #[rustfmt::skip]
        let vectors: Vec<i8> = vec![
            -1, -1, -1, 0, -1, 0,
            -1, -1,  1, 0, -1, 0,
             1,  1,  1, -1, 0, 0,
             1,  1,  1,  1, 0, 0,
             1,  1,  1, -1, 0, 0,
        ];
        let ipa: Vec<String> = ["p", "b", "a", "i", "ə"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        let symbols = symbol_list();
        let ids: Vec<i64> = symbols
            .iter()
            .map(|s| ipa.iter().position(|i| i == s).map_or(-1, |at| at as i64))
            .collect();
        SegTable::new(
            names,
            vectors,
            ipa,
            vec![false, false, true, true, true, false],
            vec![0; 5],
            (0..5).collect(),
            &ids,
            vec!["˩".into(), "˨".into(), "˧".into(), "˦".into(), "˥".into()],
        )
        .unwrap()
    }

    #[test]
    fn klic_vzoru_a_procesu_sedi_s_pythonem() {
        let t = table();
        let maker = Maker {
            t: &t,
            inventory: &[0, 1, 2, 3],
        };
        let pattern = maker.pattern(&[("voi", "-"), ("syl", "-")]).unwrap();
        assert_eq!(pattern.key(&t), "-syl,-voi");
        let candidates = voicing(&maker, 0).unwrap();
        assert_eq!(candidates.len(), 1);
        assert_eq!(candidates[0].key(&t), "voicing|{p}|change|+voi||V|V||");
    }

    #[test]
    fn sada_je_serazena_a_ma_konce_rodin() {
        let t = table();
        // Chybí symboly (d͡ʒ, ɡ …): rodiny, které je potřebují, selžou chybou, ne pádem.
        assert!(build(&t, &[0, 1, 2, 3]).is_err());
        assert_eq!(FAMILIES.len(), BUILDERS.len());
    }
}
