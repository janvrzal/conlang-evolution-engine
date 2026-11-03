//! Lexikální jasnost: zrcadlo `cee.v2.language.lexical_index.clarity_scores`.
//!
//! Skóre dvojice (morfém, pojem) u jedné skupiny je `-0,5` pro erodovaný tvar
//! (nejvýš dvě hlásky a kratší než výchozí tvar morfému) a dalších `-0,4`, když
//! stejný tvar má jako dominantní kořen jiný morfém pro jiný, doloženě
//! nepříbuzný pojem. Tabulka vlastníků tvarů (tvar → pojem, kořen) se staví
//! z dominantních kořenů skupiny při každém volání: je to stovka položek,
//! seřazených podle tvaru; dotaz je binární hledání. Nic se neukládá po řetězcích.
//! Rust tu počítá jen součet dvou konstant, takže je výsledek bit po bitu
//! stejný jako v Pythonu.

use crate::bank::Bank;

/// Pokuta za erodovaný tvar a za homofonii s nepříbuzným pojmem.
const ERODED: f64 = -0.5;
const HOMOPHONE: f64 = -0.4;

/// Sloupce jedné skupiny: dominantní kořeny podle čísla pojmu (−1 = žádný)
/// a tvary kódu podle čísla morfému (−1 = výchozí).
pub struct GroupColumns<'a> {
    pub roots: &'a [i32],
    pub forms: &'a [i32],
}

/// Výsledek dávky: skóre, nebo čísla morfémů, jejichž výchozí tvar ještě není v bance.
#[derive(Debug, PartialEq)]
pub enum Outcome {
    Scores(Vec<f64>),
    Needs(Vec<u32>),
}

/// Tvar morfému v kódu (uložený, jinak výchozí); −1, když výchozí tvar není v bance.
fn effective(columns: &GroupColumns<'_>, defaults: &[i32], morpheme: usize) -> i32 {
    match columns.forms.get(morpheme) {
        Some(&form) if form >= 0 => form,
        _ => defaults.get(morpheme).copied().unwrap_or(-1),
    }
}

fn is_related(related: &[i64], first: i64, second: i64) -> bool {
    let key = (first.min(second) << 32) | first.max(second);
    related.binary_search(&key).is_ok()
}

/// Skóre dvojic (skupina, morfém, pojem); `related` jsou seřazené klíče příbuzných dvojic.
pub fn scores(
    bank: &Bank,
    groups: &[GroupColumns<'_>],
    defaults: &[i32],
    related: &[i64],
    queries: &[(usize, i64, i64)],
) -> Result<Outcome, String> {
    let mut missing: Vec<u32> = Vec::new();
    // Vlastníci tvarů (tvar, pojem, kořen) pro každou použitou skupinu, seřazení podle tvaru.
    let mut owners: Vec<Option<Vec<(i32, i64, i64)>>> = vec![None; groups.len()];
    for &(group, _, _) in queries {
        if group >= groups.len() {
            return Err("skupina mimo dávku".into());
        }
        if owners[group].is_some() {
            continue;
        }
        let columns = &groups[group];
        let mut list = Vec::new();
        for (concept, &root) in columns.roots.iter().enumerate() {
            if root < 0 {
                continue;
            }
            let form = effective(columns, defaults, root as usize);
            if form < 0 {
                missing.push(root as u32);
            } else {
                list.push((form, concept as i64, i64::from(root)));
            }
        }
        list.sort_unstable();
        owners[group] = Some(list);
    }
    let length = |form: i32| -> Result<usize, String> {
        if form < 0 || form as usize >= bank.len() {
            return Err(format!("tvar č. {form} není v bance"));
        }
        Ok(bank.form_of(form as usize).len())
    };
    let mut out = Vec::with_capacity(queries.len());
    for &(group, morpheme, concept) in queries {
        let form = effective(&groups[group], defaults, morpheme as usize);
        let default = defaults.get(morpheme as usize).copied().unwrap_or(-1);
        if form < 0 || default < 0 {
            missing.push(morpheme as u32);
            continue;
        }
        let size = length(form)?;
        let eroded = size <= 2 && size < length(default)?;
        let mut value = if eroded { ERODED } else { 0.0 };
        let list = owners[group].as_ref().ok_or("chybí vlastníci tvarů")?;
        let first = list.partition_point(|&(f, _, _)| f < form);
        let homophone = list[first..]
            .iter()
            .take_while(|&&(f, _, _)| f == form)
            .any(|&(_, other, root)| {
                root != morpheme && other != concept && !is_related(related, concept, other)
            });
        if homophone {
            value += HOMOPHONE;
        }
        out.push(value);
    }
    if missing.is_empty() {
        Ok(Outcome::Scores(out))
    } else {
        missing.sort_unstable();
        missing.dedup();
        Ok(Outcome::Needs(missing))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn bank() -> Bank {
        // pata = 0, pa = 1, ta = 2, pa (znovu jako výchozí kratší) – tvary: 0 „pata“, 1 „pa“, 2 „ta“.
        let mut bank = Bank::new(3, vec![false, true, false, false]).unwrap();
        bank.push(&[0, 1, 2, 1]).unwrap();
        bank.push(&[0, 1]).unwrap();
        bank.push(&[2, 1]).unwrap();
        bank
    }

    #[test]
    fn eroze_a_homofonie_se_secte() {
        let bank = bank();
        // Morfémy: 0 (výchozí pata), 1 (výchozí ta), 2 (výchozí pata, v kódu zkrácený na „pa“).
        let defaults = [0, 2, 0];
        let roots = [0, 2, 1, -1];
        let forms = [-1, -1, 1];
        let columns = [GroupColumns {
            roots: &roots,
            forms: &forms,
        }];
        // Pojmy: 0 → kořen 0 („pata“), 1 → kořen 2 („pa“), 2 → kořen 1 („ta“).
        let queries = [(0, 2, 1), (0, 0, 0), (0, 1, 2)];
        let found = scores(&bank, &columns, &defaults, &[], &queries).unwrap();
        // Kořen 2: erodovaný („pa“ kratší než „pata“), žádný jiný vlastník tvaru „pa“.
        assert_eq!(found, Outcome::Scores(vec![-0.5, 0.0, 0.0]));
        // Kdyby tvar kořene 1 byl také „pa“, vznikne homofonie a pokuta se sečte (−0,5 − 0,4).
        let forms = [-1, 1, 1];
        let columns = [GroupColumns {
            roots: &roots,
            forms: &forms,
        }];
        let found = scores(&bank, &columns, &defaults, &[], &[(0, 2, 1)]).unwrap();
        assert_eq!(found, Outcome::Scores(vec![-0.5 + -0.4]));
        // Příbuzné pojmy 1 a 2 homofonii zruší.
        let related = [(1_i64 << 32) | 2];
        let found = scores(&bank, &columns, &defaults, &related, &[(0, 2, 1)]).unwrap();
        assert_eq!(found, Outcome::Scores(vec![-0.5]));
    }

    #[test]
    fn chybejici_vychozi_tvar_se_vyzada() {
        let bank = bank();
        let roots = [0];
        let columns = [GroupColumns {
            roots: &roots,
            forms: &[],
        }];
        let found = scores(&bank, &columns, &[-1], &[], &[(0, 0, 0)]).unwrap();
        assert_eq!(found, Outcome::Needs(vec![0]));
    }
}
