//! Opora zvukových změn: zrcadlo `_CombinedSoundCandidates.eval_supports`
//! z `cee.v2.changes.sound`.
//!
//! Pro každý proces (kandidáta zvukové změny) je opora součet počtů výskytů
//! prostředí (předchozí hláska, hláska, následující, přízvuk, druhá následující),
//! na která proces dopadne. Počty jsou celá čísla, takže výsledek je přesný a na
//! pořadí sčítání nezáleží; Rust sčítá tak, jak to dělá maticové násobení
//! v `numpy` (jen přesně), a nic neodhaduje.

/// Podmínka přízvuku procesu (`Process.stress`).
pub const STRESS_ANY: u8 = 0;
pub const STRESS_STRESSED: u8 = 1;
pub const STRESS_UNSTRESSED: u8 = 2;

/// Masky procesů jako matice „proces × sloupec hlásky“ po řádcích za sebou.
pub struct Masks<'a> {
    pub width: usize,
    pub target: &'a [bool],
    pub left: &'a [bool],
    pub right: &'a [bool],
    /// Masky druhé následující hlásky jen pro procesy, které ji mají.
    pub right2: &'a [bool],
    /// Pro každý proces řádek v `right2`, nebo −1.
    pub right2_row: &'a [i64],
    /// Podmínka přízvuku každého procesu.
    pub stress: &'a [u8],
}

/// Prostředí: čísla hlásek, příznaky a počty. `columns` jsou seřazené hlásky,
/// které mají sloupec v maskách (inventář a hranice slova); hlásku mimo ně
/// maska nezná.
pub struct Contexts<'a> {
    pub columns: &'a [i64],
    pub segment: &'a [i64],
    pub previous: &'a [i64],
    pub following: &'a [i64],
    pub following2: &'a [i64],
    pub stressed: &'a [bool],
    /// Je hláska (číslem) samohláska? Podmínka nepřízvučného procesu.
    pub vowel: &'a [bool],
    pub count: &'a [i64],
}

/// Sloupce hlásek čtyř pozic prostředí v maskách, nebo `None`, když některá
/// hláska nemá sloupec (pak opory počítá Python z úplných masek procesů).
fn locate(contexts: &Contexts<'_>) -> Option<[Vec<usize>; 4]> {
    let find = |segments: &[i64]| -> Option<Vec<usize>> {
        segments
            .iter()
            .map(|segment| contexts.columns.binary_search(segment).ok())
            .collect()
    };
    Some([
        find(contexts.segment)?,
        find(contexts.previous)?,
        find(contexts.following)?,
        find(contexts.following2)?,
    ])
}

/// Opora každého procesu: součet počtů prostředí, na která dopadne; `None`,
/// když některé prostředí obsahuje hlásku bez sloupce v maskách.
pub fn supports(masks: &Masks<'_>, contexts: &Contexts<'_>) -> Option<Vec<i64>> {
    let [segment, previous, following, following2] = locate(contexts)?;
    let width = masks.width;
    let processes = masks.stress.len();
    let mut out = vec![0_i64; processes];
    for (process, total) in out.iter_mut().enumerate() {
        let row = process * width;
        let target = &masks.target[row..row + width];
        let left = &masks.left[row..row + width];
        let right = &masks.right[row..row + width];
        let second = usize::try_from(masks.right2_row[process])
            .ok()
            .map(|at| &masks.right2[at * width..(at + 1) * width]);
        let stress = masks.stress[process];
        let mut sum = 0_i64;
        for (index, &count) in contexts.count.iter().enumerate() {
            let hit = target[segment[index]]
                && left[previous[index]]
                && right[following[index]]
                && second.is_none_or(|mask| mask[following2[index]])
                && match stress {
                    STRESS_STRESSED => contexts.stressed[index],
                    STRESS_UNSTRESSED => {
                        !contexts.stressed[index]
                            && contexts.vowel[contexts.segment[index] as usize]
                    }
                    _ => true,
                };
            if hit {
                sum += count;
            }
        }
        *total = sum;
    }
    Some(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn opora_secte_jen_prostredi_s_vyhovujicimi_maskami_a_prizvukem() {
        // Tři sloupce hlásek (0 = a, 1 = k, 2 = hranice), dva procesy:
        // 0 = k kdekoli, 1 = a před k, jen nepřízvučně.
        let width = 3;
        let target = [false, true, false, true, false, false];
        let all = [true; 6];
        let right = [true, true, true, false, true, false];
        let second = [true, true, true];
        let masks = Masks {
            width,
            target: &target,
            left: &all,
            right: &right,
            right2: &second,
            right2_row: &[-1, 0],
            stress: &[STRESS_ANY, STRESS_UNSTRESSED],
        };
        // Hlásky 0, 1 a hranice 5 mají sloupce 0, 1 a 2; samohláska je jen hláska 0.
        let mut contexts = Contexts {
            columns: &[0, 1, 5],
            segment: &[1, 0, 0],
            previous: &[0, 5, 5],
            following: &[5, 1, 1],
            following2: &[5, 5, 5],
            stressed: &[false, false, true],
            vowel: &[true, false, false, false, false, false],
            count: &[5, 3, 7],
        };
        // Proces 0 sedí na první prostředí; proces 1 na druhé a třetí, přízvučné třetí se vylučuje.
        assert_eq!(supports(&masks, &contexts), Some(vec![5, 3]));
        // Hláska bez sloupce v maskách: jádro neodpoví, počítá Python.
        contexts.segment = &[1, 0, 4];
        assert_eq!(supports(&masks, &contexts), None);
    }
}
