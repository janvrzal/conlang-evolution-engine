//! Tabulka hlásek nad rysy PanPhon: zrcadlo `cee.v2.language.segments`.
//!
//! Každý rozlišený vektor rysů je jedna hláska s číslem (index řádku); tvar
//! slova je posloupnost čísel (`Form`). Tabulku vyrábí `scripts/export_v2_data.py`
//! (PanPhon, MIT) a tady se jen čte. Změna rysů vždy skončí na *skutečné* hlásce
//! ([`SegmentTable::changed`]), nikdy na neexistující matici.
//!
//! **Rozbor zápisu IPA** ([`SegmentTable::parse`]) nepoužívá PanPhon, ale
//! slovník symbolů z exportu (každý zápis, který PanPhon zná, a jeho hláska)
//! s nejdelší shodou zleva a s tóny jako samostatnou vrstvou (diakritika nebo
//! tónové značky patří předchozí samohlásce). Pro zápisy, které engine
//! používá, dává stejná čísla jako Python (ověřeno na slovech protojazyků);
//! pro vzácné nezvyklé kombinace značek vrací chybu místo hádání.

use std::collections::{BTreeSet, HashMap};
use std::sync::{Arc, Mutex, OnceLock};

use serde::{Deserialize, Serialize};
use unicode_normalization::UnicodeNormalization;

use crate::ids::Form;

const TONE_LETTERS: &str = "˥˦˧˨˩";

/// Diakritika za hláskou: rysy, které nastaví, a znaky, které spotřebuje.
type Diacritic = (&'static [(&'static str, &'static str)], &'static [char]);

/// Značky, které se při změně rysů dědí jako sekundární artikulace (jen pro popis).
const PLAIN_MARKS: [char; 2] = ['\u{0361}', 'ː'];

#[derive(Deserialize)]
struct Raw {
    features: Vec<String>,
    old_count: usize,
    ipa: Vec<String>,
    vectors: Vec<String>,
    plain: Vec<u8>,
    secondary: Vec<Vec<String>>,
    needs: Vec<Vec<String>>,
    tone_base: Vec<[u32; 3]>,
    tones: Vec<String>,
    tone_marks: HashMap<String, String>,
    symbols: HashMap<String, u32>,
}

/// Množina hlásek (přirozená třída) a případně hranice slova; poslední prvek masky je hranice.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Pattern {
    pub key: String,
    pub mask: Vec<bool>,
}

impl Pattern {
    pub fn contains(&self, segment: i32) -> bool {
        self.mask[segment as usize]
    }
}

type ClosestKey = (u32, Vec<(usize, i8)>, Vec<char>);

/// Tabulka hlásek (neměnná po načtení; jen keš nejbližších hlásek se doplňuje).
pub struct SegmentTable {
    pub features: Vec<String>,
    feature_index: HashMap<String, usize>,
    pub ipa: Vec<String>,
    width: usize,
    vectors: Vec<i8>,
    /// Počet původních řádků (před vlastními rozlišovacími rysy).
    pub old_count: usize,
    pub plain: Vec<bool>,
    secondary: Vec<BTreeSet<char>>,
    needs: Vec<BTreeSet<char>>,
    /// Maska samohlásek podle čísla hlásky; poslední prvek (hranice slova) je `false`.
    pub vowel: Vec<bool>,
    tone_base: HashMap<u32, (u32, u32)>,
    toned: HashMap<(u32, u32), u32>,
    tone_codes: HashMap<String, u32>,
    tone_marks: HashMap<char, String>,
    symbols: HashMap<String, u32>,
    longest_symbol: usize,
    closest_cache: Mutex<HashMap<ClosestKey, Option<u32>>>,
    index_syl: usize,
}

/// Sekundární značky, které kóduje rys: přídech, nosovost, ejektivnost, délka, zaokrouhlení
/// (u souhlásek ʷ).
fn marks_of_feature(name: &str) -> &'static [char] {
    match name {
        "sg" => &['ʰ', 'ʱ'],
        "nas" => &['\u{303}'],
        "cg" => &['ʼ'],
        "long" => &['ː'],
        "round" => &['ʷ'],
        _ => &[],
    }
}

fn value_of(text: &str) -> Result<i8, String> {
    match text {
        "+" => Ok(1),
        "-" => Ok(-1),
        "0" => Ok(0),
        other => other
            .parse::<i8>()
            .map_err(|_| format!("Neznámá hodnota rysu '{other}'.")),
    }
}

/// Jednotný zápis: rozložené znaky, IPA ɡ, oblouček nad písmeny, ̥ místo ̊.
pub fn normalized(ipa: &str) -> String {
    ipa.nfd()
        .collect::<String>()
        .replace('g', "ɡ")
        .replace('\u{035c}', "\u{0361}")
        .replace('\u{030a}', "\u{0325}")
}

impl SegmentTable {
    pub fn from_json(text: &str) -> Result<SegmentTable, String> {
        let raw: Raw = serde_json::from_str(text).map_err(|e| format!("tabulka hlásek: {e}"))?;
        let count = raw.ipa.len();
        let width = raw.features.len();
        let mut vectors = Vec::with_capacity(count * width);
        for row in &raw.vectors {
            let before = vectors.len();
            vectors.extend(row.bytes().map(|b| b as i8 - 49));
            if vectors.len() - before != width {
                return Err("řádek rysů má špatnou délku".into());
            }
        }
        let feature_index: HashMap<String, usize> = raw
            .features
            .iter()
            .enumerate()
            .map(|(i, n)| (n.clone(), i))
            .collect();
        let index_syl = *feature_index.get("syl").ok_or("chybí rys syl")?;
        let mut vowel: Vec<bool> = (0..count)
            .map(|r| vectors[r * width + index_syl] == 1)
            .collect();
        vowel.push(false);
        let chars = |sets: &Vec<Vec<String>>| -> Vec<BTreeSet<char>> {
            sets.iter()
                .map(|set| set.iter().filter_map(|s| s.chars().next()).collect())
                .collect()
        };
        let tone_base: HashMap<u32, (u32, u32)> = raw
            .tone_base
            .iter()
            .map(|[s, b, c]| (*s, (*b, *c)))
            .collect();
        let toned = tone_base
            .iter()
            .map(|(&segment, &(base, code))| ((base, code), segment))
            .collect();
        let tone_codes = raw
            .tones
            .iter()
            .enumerate()
            .map(|(i, t)| (t.clone(), i as u32 + 1))
            .collect();
        let tone_marks = raw
            .tone_marks
            .iter()
            .filter_map(|(k, v)| k.chars().next().map(|c| (c, v.clone())))
            .collect();
        let longest_symbol = raw
            .symbols
            .keys()
            .map(|k| k.chars().count())
            .max()
            .unwrap_or(1);
        Ok(SegmentTable {
            features: raw.features,
            feature_index,
            ipa: raw.ipa,
            width,
            vectors,
            old_count: raw.old_count,
            plain: raw.plain.iter().map(|&v| v != 0).collect(),
            secondary: chars(&raw.secondary),
            needs: chars(&raw.needs),
            vowel,
            tone_base,
            toned,
            tone_codes,
            tone_marks,
            symbols: raw.symbols,
            longest_symbol,
            closest_cache: Mutex::new(HashMap::new()),
            index_syl,
        })
    }

    /// Sdílená tabulka vložená do binárky.
    pub fn default_table() -> Arc<SegmentTable> {
        static TABLE: OnceLock<Arc<SegmentTable>> = OnceLock::new();
        TABLE
            .get_or_init(|| {
                Arc::new(
                    SegmentTable::from_json(crate::data::SEGMENTS_JSON)
                        .expect("vložená tabulka hlásek"),
                )
            })
            .clone()
    }

    pub fn len(&self) -> usize {
        self.ipa.len()
    }

    pub fn is_empty(&self) -> bool {
        self.ipa.is_empty()
    }

    /// Číslo hranice slova (počet hlásek).
    pub fn boundary(&self) -> i32 {
        self.ipa.len() as i32
    }

    /// Všechny řádky rysů za sebou (`len() × width()`), pro editační vzdálenost tvarů.
    pub fn vectors(&self) -> &[i8] {
        &self.vectors
    }

    /// Počet rysů v řádku.
    pub fn width(&self) -> usize {
        self.width
    }

    pub fn row(&self, segment: usize) -> &[i8] {
        &self.vectors[segment * self.width..(segment + 1) * self.width]
    }

    pub fn feature_index(&self, name: &str) -> Result<usize, String> {
        self.feature_index
            .get(name)
            .copied()
            .ok_or_else(|| format!("Neznámý rys '{name}'."))
    }

    pub fn feature(&self, segment: i32, name: &str) -> i8 {
        self.row(segment as usize)[self.feature_index[name]]
    }

    pub fn is_vowel(&self, segment: i32) -> bool {
        self.vowel[segment as usize]
    }

    pub fn render(&self, form: &[i32]) -> String {
        form.iter()
            .map(|&s| self.ipa[s as usize].as_str())
            .collect()
    }

    /// Zápisy tónů podle kódu (kód 1 je na pozici 0), jak je dává `TONES` v Pythonu.
    pub fn tone_symbols(&self) -> Vec<String> {
        let mut found: Vec<(&u32, &String)> = self.tone_codes.iter().map(|(k, v)| (v, k)).collect();
        found.sort();
        found
            .into_iter()
            .map(|(_, symbol)| symbol.clone())
            .collect()
    }

    /// Tónové značky, kterými se tón zapisuje diakritikou (kombinující znak → tónová písmena).
    pub fn tone_mark_letters(&self, mark: char) -> Option<&str> {
        self.tone_marks.get(&mark).map(String::as_str)
    }

    /// Zapíše se tvar zpět beze ztráty? Tóny diakritikou se počítají jako tónové značky;
    /// přízvuk a hranice slabik (`ˈ ˌ .`) určuje jazyk, ne zápis. Neznámá hláska je chyba.
    pub fn lossless(&self, ipa: &str) -> Result<Option<String>, String> {
        let form = self.parse(ipa)?;
        let signature = |text: &str| {
            let mut chars: Vec<char> = normalized(text).chars().collect();
            chars.sort_unstable();
            chars
        };
        let expected: String = normalized(ipa)
            .chars()
            .filter(|c| !"ˈˌ.‿|‖".contains(*c))
            .map(|c| {
                self.tone_mark_letters(c)
                    .map_or_else(|| c.to_string(), str::to_owned)
            })
            .collect();
        let rendered = self.render(&form);
        Ok((signature(&rendered) != signature(&expected)).then_some(rendered))
    }

    /// Kód tónu samohlásky (0 = bez tónu).
    pub fn tone_of(&self, segment: i32) -> u32 {
        self.tone_base
            .get(&(segment as u32))
            .map_or(0, |&(_, code)| code)
    }

    /// Táž samohláska s tónem `code` (0 = bez tónu); `None`, když ji tabulka nemá.
    pub fn with_tone(&self, segment: i32, code: u32) -> Option<i32> {
        let base = self
            .tone_base
            .get(&(segment as u32))
            .map_or(segment as u32, |&(b, _)| b);
        if code == 0 {
            return Some(base as i32);
        }
        self.toned.get(&(base, code)).map(|&s| s as i32)
    }

    /// Hrubá škála sonority: vokál 4, aproximanta 3, likvida 2, nazála 1, obstruent 0.
    pub fn sonority(&self, segment: i32) -> u8 {
        if self.vowel[segment as usize] {
            return 4;
        }
        if self.feature(segment, "son") != 1 {
            return 0;
        }
        if self.feature(segment, "cons") != 1 {
            return 3;
        }
        if self.feature(segment, "nas") == 1 {
            1
        } else {
            2
        }
    }

    /// (výška, zadnost, zaokrouhlení) v hrubé mřížce pro posuny a disperzi.
    pub fn vowel_coordinates(&self, segment: i32) -> (f64, f64, f64) {
        let (hi, lo) = (self.feature(segment, "hi"), self.feature(segment, "lo"));
        let mut height = if hi == 1 {
            2.0
        } else if lo == 1 {
            0.0
        } else {
            1.0
        };
        if height == 1.0 && self.feature(segment, "tense") == -1 {
            height = 0.6;
        }
        let mut back = if self.feature(segment, "back") == 1 {
            1.0
        } else {
            0.0
        };
        let symbol = self.ipa[segment as usize].as_str();
        if symbol == "ə" || symbol == "ɨ" {
            back = 0.5;
        }
        let rounded = if self.feature(segment, "round") == 1 {
            1.0
        } else {
            0.0
        };
        (height, back, rounded)
    }

    // --- rozbor zápisu ------------------------------------------------------------

    /// Rozbor zápisu IPA na tvar (viz popis modulu).
    pub fn parse(&self, ipa: &str) -> Result<Form, String> {
        let chars: Vec<char> = normalized(ipa).chars().collect();
        let mut out: Form = Vec::new();
        let mut index = 0;
        while index < chars.len() {
            let current = chars[index];
            if let Some(letters) = self.tone_marks.get(&current) {
                self.attach_tone(&mut out, letters)?;
                index += 1;
                continue;
            }
            if TONE_LETTERS.contains(current) {
                let mut end = index;
                while end < chars.len() && TONE_LETTERS.contains(chars[end]) {
                    end += 1;
                }
                let letters: String = chars[index..end].iter().collect();
                self.attach_tone(&mut out, &letters)?;
                index = end;
                continue;
            }
            // Nejdelší shoda; symbol nesmí v sobě nést tón (ten je vlastní vrstva).
            let mut limit = index + 1;
            while limit < chars.len()
                && !self.tone_marks.contains_key(&chars[limit])
                && !TONE_LETTERS.contains(chars[limit])
            {
                limit += 1;
            }
            let longest = (limit - index).min(self.longest_symbol);
            let mut found = None;
            for length in (1..=longest).rev() {
                let candidate: String = chars[index..index + length].iter().collect();
                if let Some(&segment) = self.symbols.get(&candidate) {
                    found = Some((segment as i32, length));
                    break;
                }
            }
            match found {
                Some((segment, length)) => {
                    out.push(segment);
                    index += length;
                }
                None => {
                    if let Some(&last) = out.last() {
                        let diacritic: Option<Diacritic> = match chars[index] {
                            'ʰ' => Some((&[("sg", "+")][..], &['ʰ'])),
                            'ʱ' => Some((&[("sg", "+"), ("voi", "+")][..], &['ʱ'])),
                            '\u{0303}' => Some((&[("nas", "+")][..], &['\u{0303}'])),
                            'ʼ' => Some((&[("cg", "+")][..], &['ʼ'])),
                            'ː' => Some((&[("long", "+")][..], &['ː'])),
                            'ʷ' => Some((&[("round", "+")][..], &['ʷ'])),
                            'ʲ' => Some((&[("hi", "+"), ("back", "-")][..], &['ʲ'])),
                            'ˠ' => Some((&[("hi", "+"), ("back", "+")][..], &['ˠ'])),
                            '\u{0325}' => Some((&[("voi", "-")][..], &['\u{0325}'])),
                            '\u{032c}' => Some((&[("voi", "+")][..], &['\u{032c}'])),
                            _ => None,
                        };
                        if let Some((changes, allow)) = diacritic {
                            if let Ok(Some(modified)) = self.changed(last, changes, allow) {
                                *out.last_mut().expect("neprázdné") = modified;
                                index += 1;
                                continue;
                            }
                        }
                    }
                    return Err(format!(
                        "Tvar '{ipa}' obsahuje hlásku '{}', kterou engine zatím neumí zapsat.",
                        chars[index]
                    ));
                }
            }
        }
        if out.is_empty() {
            return Err(format!("Tvar '{ipa}' neobsahuje žádnou známou hlásku."));
        }
        Ok(out)
    }

    /// Tón patří předchozí samohlásce; kde ji tabulka nemá, zůstane tónová značka hláskou.
    fn attach_tone(&self, out: &mut Form, letters: &str) -> Result<(), String> {
        if let (Some(&last), Some(&code)) = (out.last(), self.tone_codes.get(letters)) {
            if self.is_vowel(last) && self.tone_of(last) == 0 {
                if let Some(toned) = self.with_tone(last, code) {
                    *out.last_mut().expect("neprázdné") = toned;
                    return Ok(());
                }
            }
        }
        for letter in letters.chars() {
            let segment = self
                .symbols
                .get(&letter.to_string())
                .ok_or_else(|| format!("neznámý tón '{letter}'"))?;
            out.push(*segment as i32);
        }
        Ok(())
    }

    /// Číslo jedné hlásky podle zápisu.
    pub fn id_of(&self, ipa: &str) -> Result<i32, String> {
        let form = self.parse(ipa)?;
        if form.len() != 1 {
            return Err(format!("'{ipa}' není jedna hláska."));
        }
        Ok(form[0])
    }

    // --- dotazy -------------------------------------------------------------------

    /// Hlásky s danými hodnotami rysů; hranice slova do třídy nepatří.
    pub fn pattern(&self, features: &[(&str, &str)]) -> Result<Pattern, String> {
        let mut items: Vec<(&str, &str)> = features.to_vec();
        items.sort();
        let mut mask = vec![true; self.len()];
        for &(name, value) in &items {
            let column = self.feature_index(name)?;
            let wanted = value_of(value)?;
            for (segment, keep) in mask.iter_mut().enumerate() {
                *keep &= self.row(segment)[column] == wanted;
            }
        }
        mask.push(false);
        let key = if items.is_empty() {
            "*".to_owned()
        } else {
            items
                .iter()
                .map(|(name, value)| format!("{value}{name}"))
                .collect::<Vec<_>>()
                .join(",")
        };
        Ok(Pattern { key, mask })
    }

    /// Výčtová třída konkrétních hlásek.
    pub fn segments(&self, ipa: &[&str]) -> Result<Pattern, String> {
        let mut ids: Vec<i32> = ipa
            .iter()
            .map(|s| self.id_of(s))
            .collect::<Result<_, _>>()?;
        ids.sort_unstable();
        let mut mask = vec![false; self.len() + 1];
        for &id in &ids {
            mask[id as usize] = true;
        }
        let key = format!(
            "{{{}}}",
            ids.iter()
                .map(|&i| self.ipa[i as usize].as_str())
                .collect::<Vec<_>>()
                .join(",")
        );
        Ok(Pattern { key, mask })
    }

    /// Jen hranice slova.
    pub fn boundary_pattern(&self) -> Pattern {
        let mut mask = vec![false; self.len() + 1];
        mask[self.len()] = true;
        Pattern {
            key: "#".into(),
            mask,
        }
    }

    /// Hláska po změně rysů: nejbližší skutečná hláska s požadovanými rysy, nebo `None`.
    ///
    /// Sekundární artikulace vstupu se zachová (změna rysu ji nesmí potichu odstranit);
    /// `allow` jsou značky, které smí mít výstup navíc.
    pub fn changed(
        &self,
        segment: i32,
        changes: &[(&str, &str)],
        allow: &[char],
    ) -> Result<Option<i32>, String> {
        let mut allowed: BTreeSet<char> = self.secondary[segment as usize].clone();
        // Značka, kterou kóduje měněný rys, se nezachovává: ztráta přídechu musí smět odstranit
        // ʰ, ztráta nosovosti ◌̃ a podobně (jinak změna skončí u nesmyslné hlásky jako ɓʰ).
        for &(name, _) in changes {
            for &mark in marks_of_feature(name) {
                allowed.remove(&mark);
            }
        }
        allowed.extend(allow.iter().copied());
        let mut wanted: Vec<(usize, i8)> = Vec::with_capacity(changes.len());
        for &(name, value) in changes {
            wanted.push((self.feature_index(name)?, value_of(value)?));
        }
        let key: ClosestKey = (
            segment as u32,
            wanted.clone(),
            allowed.iter().copied().collect(),
        );
        if let Some(found) = self.closest_cache.lock().expect("zámek").get(&key) {
            return Ok(found.map(|s| s as i32));
        }
        let found = self.closest(segment as usize, &wanted, &allowed);
        self.closest_cache
            .lock()
            .expect("zámek")
            .insert(key, found.map(|s| s as u32));
        Ok(found)
    }

    fn closest(
        &self,
        segment: usize,
        wanted: &[(usize, i8)],
        allowed: &BTreeSet<char>,
    ) -> Option<i32> {
        let source = self.row(segment);
        let mut best: Option<(usize, usize)> = None; // (vzdálenost, řádek)
        for row in 0..self.len() {
            let candidate = if allowed.is_empty() {
                self.plain[row]
            } else {
                allowed.is_subset(&self.secondary[row]) && self.needs[row].is_subset(allowed)
            };
            if !candidate {
                continue;
            }
            let vector = self.row(row);
            if wanted
                .iter()
                .any(|&(column, value)| vector[column] != value)
            {
                continue;
            }
            let distance = vector.iter().zip(source).filter(|(a, b)| a != b).count();
            // Při stejné vzdálenosti vyhraje hláska s kratším zápisem (tʰ před tʰʰ).
            let better = best.is_none_or(|(d, at)| {
                distance < d
                    || (distance == d
                        && self.ipa[row].chars().count() < self.ipa[at].chars().count())
            });
            if better {
                best = Some((distance, row));
            }
        }
        let (distance, row) = best?;
        let required = wanted
            .iter()
            .filter(|&&(column, value)| source[column] != value)
            .count();
        if row == segment || distance > required + 2 {
            return None;
        }
        Some(row as i32)
    }

    /// Hodnoty vybraných rysů hlásky jako požadavek pro změnu (`features_of`).
    pub fn features_of(&self, ipa: &str, names: &[&str]) -> Result<Vec<(String, String)>, String> {
        let segment = self.id_of(ipa)?;
        let mut out: Vec<(String, String)> = names
            .iter()
            .map(|&name| {
                let symbol = match self.feature(segment, name) {
                    1 => "+",
                    -1 => "-",
                    _ => "0",
                };
                (name.to_owned(), symbol.to_owned())
            })
            .collect();
        out.sort();
        Ok(out)
    }

    /// Je v zápisu hláska „prostá“ (bez sekundární artikulace)?
    pub fn is_plain(&self, segment: i32) -> bool {
        self.plain[segment as usize]
    }

    /// Sloupec rysu slabičnosti (pro jádra).
    pub fn syllabic_column(&self) -> usize {
        self.index_syl
    }

    /// Znaky, které jsou prosté (pro popis modulu; sdílí `PLAIN_MARKS`).
    pub fn plain_marks() -> &'static [char] {
        &PLAIN_MARKS
    }
}

impl std::fmt::Debug for SegmentTable {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "SegmentTable({} hlásek, {} rysů)",
            self.ipa.len(),
            self.width
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn kompozicni_rozbor_diakritik() {
        let table = SegmentTable::default_table();
        let normal = table.parse("a\u{0303}ː").unwrap();
        let reversed = table.parse("aː\u{0303}").unwrap();
        assert_eq!(normal, reversed);
    }
}
