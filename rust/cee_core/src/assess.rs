//! Hodnocení zvukového procesu nad slovní zásobou: zrcadlo dávkové části
//! `cee.v2.assessment._assess_batch`.
//!
//! Vstupem je matice (skupiny × slova vzorku) daná čísly tvarů a váhami
//! (frekvencemi), výstupem pro každou skupinu:
//!
//! - zasažená hmota (`mass`), hmota slov zkrácených na dvě hlásky a méně
//!   (`short`) a vážený rozdíl příznakovosti (`marked`),
//! - dvojice slov, která po změně zní stejně a předtím nezněla (`pairs`),
//!   ve stejném pořadí, v jakém je prochází Python,
//! - samohlásky slovní zásoby před změnou a po ní (jen když se chtějí).
//!
//! Součty plovoucích čísel musí být bit po bitu stejné jako `numpy`. `np.sum`
//! po řádcích sčítá párově (`pairwise_sum` níže), proto se tu sčítá stejně,
//! po celé šířce matice včetně nul, kterými se doplňují kratší řádky. Rust tu
//! nepočítá žádnou transcendentní funkci, jen součty, součiny a rozdíly.

use std::collections::BTreeMap;

use crate::bank::{Bank, Outcome};

/// Délka bloku, do které `numpy` sčítá párově jedním průchodem po osmi.
const BLOCK: usize = 128;

/// Párový součet jako `np.add.reduce` nad souvislým polem `double`: pro méně
/// než osm prvků postupně, do 128 prvků osmi částečnými součty a nad to
/// rekurzivně po půlkách zarovnaných na násobek osmi. Výsledek se (jako v
/// `numpy`) přičte k nule.
pub fn pairwise_sum(values: &[f64]) -> f64 {
    0.0 + pairwise(values)
}

fn pairwise(values: &[f64]) -> f64 {
    let n = values.len();
    if n < 8 {
        let mut result = 0.0;
        for &value in values {
            result += value;
        }
        result
    } else if n <= BLOCK {
        let mut r = [0.0; 8];
        r.copy_from_slice(&values[..8]);
        let mut i = 8;
        while i < n - (n % 8) {
            for (j, part) in r.iter_mut().enumerate() {
                *part += values[i + j];
            }
            i += 8;
        }
        let mut result = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]));
        while i < n {
            result += values[i];
            i += 1;
        }
        result
    } else {
        let mut half = n / 2;
        half -= half % 8;
        pairwise(&values[..half]) + pairwise(&values[half..])
    }
}

/// Příznakovost slabičné stavby tvaru (`cee.v2.assessment.markedness`):
/// shluky, koncové souhlásky, hiát. Polosamohláska vedle samohlásky patří
/// k jádru slabiky.
pub fn markedness(form: &[i32], vowel: &[bool], glide: &[bool]) -> f64 {
    let n = form.len();
    let is_vowel = |index: usize| vowel[form[index] as usize];
    let vocalic = |index: usize| {
        is_vowel(index)
            || (glide[form[index] as usize]
                && ((index > 0 && is_vowel(index - 1)) || (index + 1 < n && is_vowel(index + 1))))
    };
    let mut score = 0.0_f64;
    let mut run: i64 = 0;
    let mut seen = false;
    for index in 0..n {
        if vocalic(index) {
            if run != 0 {
                let skip = if seen { 2 } else { 1 };
                score += (run - skip).max(0) as f64;
            } else if seen && is_vowel(index) && index > 0 && is_vowel(index - 1) {
                score += 0.5; // hiát
            }
            run = 0;
            seen = true;
        } else {
            run += 1;
        }
    }
    if run != 0 {
        score += 0.4 * run as f64 + (run - 1).max(0) as f64;
    }
    score
}

/// Vstup: řádky matice za sebou (`ids`, `weights`), kde řádek `r` zabírá
/// `offsets[r]..offsets[r + 1]`; `width` je šířka matice v Pythonu (nejdelší řádek).
pub struct Matrix<'a> {
    pub ids: &'a [i64],
    pub weights: &'a [f64],
    pub offsets: &'a [i64],
    pub width: usize,
}

/// Hodnocení jedné skupiny (řádku matice).
#[derive(Default, Debug)]
pub struct RowAssessment {
    pub mass: f64,
    pub short: f64,
    pub marked: f64,
    /// Dvojice pozic ve vzorku (první < druhá), jejichž tvary po změně splynou
    /// a předtím různé byly; v pořadí hodnot, pak pozic.
    pub pairs: Vec<(u32, u32)>,
    /// Samohlásky s kladným počtem před změnou a po ní, vzestupně.
    pub before: Vec<i32>,
    pub after: Vec<i32>,
}

pub enum Assessed {
    /// Hlásky, jejichž výstup změny musí napřed spočítat Python.
    Needs(Vec<i32>),
    Done(Vec<RowAssessment>),
}

fn vowel_counts(
    bank: &Bank,
    forms: impl Iterator<Item = usize>,
    counts: &mut BTreeMap<i32, i64>,
    sign: i64,
) {
    for id in forms {
        for &segment in bank.form(id) {
            if bank.vowel[segment as usize] {
                *counts.entry(segment).or_insert(0) += sign;
            }
        }
    }
}

fn positive(counts: &BTreeMap<i32, i64>) -> Vec<i32> {
    counts
        .iter()
        .filter(|(_, &count)| count > 0)
        .map(|(&segment, _)| segment)
        .collect()
}

impl Bank {
    /// Příznakovost tvaru, spočítaná jednou (NaN v poli = zatím neznámá).
    fn marked_of(&mut self, id: usize) -> f64 {
        if self.marked.len() < self.len() {
            self.marked
                .resize(self.len().max(64).max(2 * self.marked.len()), f64::NAN);
        }
        let found = self.marked[id];
        if !found.is_nan() {
            return found;
        }
        let value = markedness(self.form(id), &self.vowel, &self.glide);
        self.marked[id] = value;
        value
    }

    /// Příznakovost tvaru č. `id` (s kontrolou čísla), spočítaná jednou.
    pub fn markedness_of(&mut self, id: usize) -> Result<f64, String> {
        if id >= self.len() {
            return Err(format!("tvar č. {id} neexistuje"));
        }
        Ok(self.marked_of(id))
    }

    /// Hodnocení změny `row` s pravidlem přízvuku `rule` nad maticí slovních
    /// zásob. Chybí-li mapa hlásek, vrátí `Needs` a nic neudělá.
    pub fn assess_rows(
        &mut self,
        row: usize,
        rule: u8,
        matrix: &Matrix<'_>,
        want_vowels: bool,
    ) -> Result<Assessed, String> {
        let rows = matrix.offsets.len().saturating_sub(1);
        let valid = |position: usize| -> Result<std::ops::Range<usize>, String> {
            let (begin, end) = (matrix.offsets[position], matrix.offsets[position + 1]);
            if begin < 0
                || end < begin
                || end as usize > matrix.ids.len()
                || (end - begin) as usize > matrix.width
            {
                return Err("řádky matice mají špatné meze".into());
            }
            Ok(begin as usize..end as usize)
        };
        if matrix.weights.len() != matrix.ids.len() {
            return Err("váhy a tvary mají různou délku".into());
        }
        let changed = match self.results(row, rule, matrix.ids)? {
            Outcome::Needs(needs) => return Ok(Assessed::Needs(needs)),
            Outcome::Done(found) => found,
        };
        let width = matrix.width;
        let mut mass_terms = vec![0.0_f64; width];
        let mut short_terms = vec![0.0_f64; width];
        let mut marked_terms = vec![0.0_f64; width];
        let mut out = Vec::with_capacity(rows);
        for position in 0..rows {
            let range = valid(position)?;
            let length = range.len();
            mass_terms.iter_mut().for_each(|term| *term = 0.0);
            short_terms.iter_mut().for_each(|term| *term = 0.0);
            marked_terms.iter_mut().for_each(|term| *term = 0.0);
            let mut any = false;
            for k in 0..length {
                let at = range.start + k;
                let after = changed[at];
                if after < 0 {
                    continue;
                }
                any = true;
                let (old, new) = (matrix.ids[at] as usize, after as usize);
                let weight = matrix.weights[at];
                mass_terms[k] = weight;
                let (old_length, new_length) = (self.form(old).len(), self.form(new).len());
                if new_length <= 2 && new_length < old_length {
                    short_terms[k] = weight;
                }
                marked_terms[k] = weight * (self.marked_of(new) - self.marked_of(old));
            }
            let mut result = RowAssessment::default();
            if any {
                result.mass = pairwise_sum(&mass_terms);
                result.short = pairwise_sum(&short_terms);
                result.marked = pairwise_sum(&marked_terms);
            }
            if result.mass > 0.0 {
                // Nový homofon: dvojice, která po změně zní stejně a předtím nezněla.
                let mut final_ids: Vec<(i64, u32)> = (0..length)
                    .map(|k| {
                        let at = range.start + k;
                        (
                            if changed[at] >= 0 {
                                changed[at]
                            } else {
                                matrix.ids[at]
                            },
                            k as u32,
                        )
                    })
                    .collect();
                final_ids.sort_unstable();
                let mut begin = 0;
                while begin < final_ids.len() {
                    let mut end = begin + 1;
                    while end < final_ids.len() && final_ids[end].0 == final_ids[begin].0 {
                        end += 1;
                    }
                    for first in begin..end {
                        for second in first + 1..end {
                            let (a, b) = (final_ids[first].1, final_ids[second].1);
                            if matrix.ids[range.start + a as usize]
                                != matrix.ids[range.start + b as usize]
                            {
                                result.pairs.push((a, b));
                            }
                        }
                    }
                    begin = end;
                }
                if want_vowels {
                    let mut counts = BTreeMap::new();
                    vowel_counts(
                        self,
                        (range.clone()).map(|at| matrix.ids[at] as usize),
                        &mut counts,
                        1,
                    );
                    result.before = positive(&counts);
                    let hit = range.clone().filter(|&at| changed[at] >= 0);
                    vowel_counts(
                        self,
                        hit.clone().map(|at| matrix.ids[at] as usize),
                        &mut counts,
                        -1,
                    );
                    vowel_counts(self, hit.map(|at| changed[at] as usize), &mut counts, 1);
                    result.after = positive(&counts);
                }
            }
            out.push(result);
        }
        Ok(Assessed::Done(out))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Pro méně než osm prvků se sčítá postupně. Shodu s `np.sum` pro všechny
    /// délky ověřuje `tests/v2/test_v2_native_assess.py`.
    #[test]
    fn parovy_soucet_sedi_s_postupnym_pro_male_pole() {
        let values = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7];
        let mut sequential = 0.0;
        for value in values {
            sequential += value;
        }
        assert_eq!(pairwise_sum(&values).to_bits(), sequential.to_bits());
    }

    #[test]
    fn parovy_soucet_osm_prvku_pouziva_osm_castecnych_souctu() {
        let values = [1e16, 1.0, -1e16, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0];
        // 9 prvků: osm částečných součtů, pak zbytek.
        let blocks = ((1e16 + 1.0) + (-1e16 + 1.0)) + ((1.0 + 1.0) + (1.0 + 1.0));
        assert_eq!(pairwise_sum(&values), blocks + 1.0);
        assert_eq!(pairwise_sum(&[]), 0.0);
    }

    #[test]
    fn priznakovost_zna_shluk_koncovku_a_hiat() {
        // Hlásky: 0 = a (samohláska), 1 = k, 2 = j (polosamohláska); hranice = 3.
        let vowel = [true, false, false, false];
        let glide = [false, false, true, false];
        assert_eq!(markedness(&[1, 0, 1, 0], &vowel, &glide), 0.0);
        // kak: počáteční souhláska před prvním jádrem nic nestojí, koncová stojí 0,4.
        assert_eq!(markedness(&[1, 0, 1], &vowel, &glide), 0.4);
        // Hiát: aa = 0,5.
        assert_eq!(markedness(&[0, 0], &vowel, &glide), 0.5);
        // Polosamohláska vedle samohlásky je jádro (aj), ne shluk.
        assert_eq!(markedness(&[0, 2], &vowel, &glide), 0.0);
        assert_eq!(markedness(&[], &vowel, &glide), 0.0);
    }
}
