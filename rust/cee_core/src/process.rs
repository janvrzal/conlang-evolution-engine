//! Zvukový proces nad jedním tvarem: zrcadlo `cee.v2.language.processes.Process`.
//!
//! Aplikace je dvoufázová jako v Pythonu: nejdřív se na původním tvaru najdou
//! všechna místa (`find_sites`), teprve potom se změní najednou (`apply`),
//! takže změna nemůže živit sama sebe. Pořadí podmínek i významy hodnot se
//! shodují s Pythonem, protože výsledek musí být bitově stejný.

/// Operace procesu, čísla odpovídají `OPERATIONS` v `cee.v2.native`.
pub const OP_CHANGE: u8 = 0;
pub const OP_REPLACE: u8 = 1;
pub const OP_DELETE: u8 = 2;
pub const OP_INSERT_BEFORE: u8 = 3;
pub const OP_INSERT_AFTER: u8 = 4;
pub const OP_MERGE_NEXT: u8 = 5;
pub const OP_TONE: u8 = 6;

/// Podmínka přízvuku.
pub const STRESS_NONE: u8 = 0;
pub const STRESS_STRESSED: u8 = 1;
pub const STRESS_UNSTRESSED: u8 = 2;

/// Pravidla přízvuku (`StressRule`), čísla odpovídají `RULES` v `cee.v2.native`.
pub const RULE_INITIAL: u8 = 0;
pub const RULE_SECOND: u8 = 1;
pub const RULE_ANTEPENULT: u8 = 2;
pub const RULE_PENULT: u8 = 3;
pub const RULE_FINAL: u8 = 4;
pub const RULE_COUNT: usize = 5;

/// V mapě hlásek: výstup ještě není znám (Python ho teprve dopočítá).
pub const MAP_UNRESOLVED: i32 = -3;
/// V mapě hlásek: tabulka hlásek nenašla náhradu (`None`), hláska zůstane.
pub const MAP_NONE: i32 = -1;

/// Jeden zvukový proces: masky hlásek a parametry operace.
///
/// Masky mají délku „počet hlásek + 1“, poslední prvek je hranice slova.
pub struct Proc {
    pub operation: u8,
    pub stress: u8,
    pub medial: bool,
    /// Výstupní hláska u `replace`, vkládaná u `insert_*`, výsledek `merge_next`.
    pub segment: i32,
    pub target: Vec<bool>,
    pub left: Vec<bool>,
    pub right: Vec<bool>,
    pub right2: Vec<bool>,
    /// Hláska → výstup operací `change` a `tone`; počítá je Python (tabulka
    /// hlásek má složitou logiku nejbližší hlásky), Rust si je jen pamatuje.
    pub map: Vec<i32>,
}

impl Proc {
    /// Výstup operace `change` a `tone` pro hlásku (`None`, když ještě není znám).
    fn mapped(&self, segment: i32) -> Option<i32> {
        match self.map[segment as usize] {
            MAP_UNRESOLVED => None,
            MAP_NONE => Some(segment),
            output => Some(output),
        }
    }

    fn uses_map(&self) -> bool {
        self.operation == OP_CHANGE || self.operation == OP_TONE
    }
}

/// Indexy samohlásek (jader) tvaru.
pub(crate) fn nuclei(form: &[i32], vowel: &[bool], out: &mut Vec<usize>) {
    out.clear();
    for (index, &segment) in form.iter().enumerate() {
        if vowel[segment as usize] {
            out.push(index);
        }
    }
}

/// Přízvučné jádro podle pravidla (`None`, když tvar nemá samohlásku).
pub(crate) fn stressed_nucleus(found: &[usize], rule: u8) -> Option<usize> {
    let count = found.len();
    if count == 0 {
        return None;
    }
    Some(match rule {
        RULE_INITIAL => found[0],
        RULE_SECOND => found[count.min(2) - 1],
        RULE_ANTEPENULT => found[count.saturating_sub(3)],
        RULE_PENULT => found[count.saturating_sub(2)],
        _ => found[count - 1],
    })
}

/// Opakovaně použitelné vyrovnávací paměti, ať aplikace nealokuje po každém tvaru.
#[derive(Default)]
pub struct Scratch {
    nuclei: Vec<usize>,
    sites: Vec<bool>,
    result: Vec<i32>,
}

/// Má v tvaru proces vůbec místo? Totéž co `FormBank.has_site` pro jeden tvar:
/// cílová hláska se správným levým a pravým sousedem (bez přízvuku a pozice).
pub fn has_site(proc: &Proc, form: &[i32], boundary: i32) -> bool {
    let last = form.len().wrapping_sub(1);
    for (index, &segment) in form.iter().enumerate() {
        if !proc.target[segment as usize] {
            continue;
        }
        let previous = if index > 0 { form[index - 1] } else { boundary };
        let following = if index < last {
            form[index + 1]
        } else {
            boundary
        };
        if proc.left[previous as usize] && proc.right[following as usize] {
            return true;
        }
    }
    false
}

/// Označí v `scratch.sites` místa, na která proces v tvaru dopadne
/// (`Process.sites`), a vrátí, zda je aspoň jedno.
fn find_sites(
    proc: &Proc,
    form: &[i32],
    vowel: &[bool],
    boundary: i32,
    rule: u8,
    scratch: &mut Scratch,
) -> bool {
    let size = form.len();
    scratch.sites.clear();
    scratch.sites.resize(size, false);
    if size == 0 {
        return false;
    }
    let need_nuclei = proc.stress != STRESS_NONE || proc.medial;
    if need_nuclei {
        nuclei(form, vowel, &mut scratch.nuclei);
    }
    let stressed = if proc.stress != STRESS_NONE {
        stressed_nucleus(&scratch.nuclei, rule)
    } else {
        None
    };
    let last = size - 1;
    let mut any = false;
    for (index, &segment) in form.iter().enumerate() {
        if !proc.target[segment as usize] {
            continue;
        }
        let previous = if index > 0 { form[index - 1] } else { boundary };
        if !proc.left[previous as usize] {
            continue;
        }
        let following = if index < last {
            form[index + 1]
        } else {
            boundary
        };
        if !proc.right[following as usize] {
            continue;
        }
        let second = if index + 2 <= last {
            form[index + 2]
        } else {
            boundary
        };
        if !proc.right2[second as usize] {
            continue;
        }
        if proc.stress == STRESS_STRESSED && stressed != Some(index) {
            continue;
        }
        if proc.stress == STRESS_UNSTRESSED && (stressed == Some(index) || !vowel[segment as usize])
        {
            continue;
        }
        if proc.operation == OP_MERGE_NEXT && index == last {
            continue;
        }
        if proc.medial {
            let inside = match (scratch.nuclei.first(), scratch.nuclei.last()) {
                (Some(&first), Some(&top)) => first < index && index < top,
                _ => false,
            };
            if !inside {
                continue;
            }
        }
        // Vložení vedle stejné hlásky by jen zdvojilo, co už tam je (jje).
        if proc.operation == OP_INSERT_BEFORE && index > 0 && form[index - 1] == proc.segment {
            continue;
        }
        if proc.operation == OP_INSERT_AFTER && index < last && form[index + 1] == proc.segment {
            continue;
        }
        scratch.sites[index] = true;
        any = true;
    }
    any
}

/// Hlásky, jejichž výstup operace `change` či `tone` ještě Python nespočítal.
pub fn missing_map(
    proc: &Proc,
    form: &[i32],
    vowel: &[bool],
    boundary: i32,
    rule: u8,
    scratch: &mut Scratch,
    out: &mut std::collections::BTreeSet<i32>,
) {
    if !proc.uses_map() || !find_sites(proc, form, vowel, boundary, rule, scratch) {
        return;
    }
    for (index, &segment) in form.iter().enumerate() {
        if scratch.sites[index] && proc.map[segment as usize] == MAP_UNRESOLVED {
            out.insert(segment);
        }
    }
}

/// Nový tvar, nebo `None`, když se nic nezmění či by slovo zaniklo
/// (`Process._apply` bez hranice kmen | koncovka). Mapa hlásek musí být
/// u míst operací `change` a `tone` doplněná (`missing_map`).
pub fn apply(
    proc: &Proc,
    form: &[i32],
    vowel: &[bool],
    boundary: i32,
    rule: u8,
    scratch: &mut Scratch,
) -> Option<Vec<i32>> {
    apply_cut(proc, form, vowel, boundary, rule, NO_CUT, scratch).map(|(form, _)| form)
}

/// Bez hranice kmen | koncovka (`None` v Pythonu).
pub const NO_CUT: i32 = -1;

/// `Process._apply` i s hranicí kmen | koncovka: nový tvar a kolik jeho hlásek
/// vzniklo z kmene (`NO_CUT`, když tvar koncovku nemá). Vložená hláska na
/// hranici patří ke koncovce, splynutí přes hranici ke kmeni.
pub fn apply_cut(
    proc: &Proc,
    form: &[i32],
    vowel: &[bool],
    boundary: i32,
    rule: u8,
    cut: i32,
    scratch: &mut Scratch,
) -> Option<(Vec<i32>, i32)> {
    if !find_sites(proc, form, vowel, boundary, rule, scratch) {
        return None;
    }
    let mut result = std::mem::take(&mut scratch.result);
    result.clear();
    let mut skip: Option<usize> = None;
    let mut new_cut = cut;
    for (index, &segment) in form.iter().enumerate() {
        if cut != NO_CUT && index as i32 == cut {
            new_cut = result.len() as i32;
        }
        if skip == Some(index) {
            continue;
        }
        if !scratch.sites[index] {
            result.push(segment);
            continue;
        }
        match proc.operation {
            OP_CHANGE | OP_TONE => {
                result.push(proc.mapped(segment).expect("mapa hlásek není doplněná"))
            }
            OP_REPLACE => result.push(proc.segment),
            OP_DELETE => {}
            OP_INSERT_BEFORE => {
                result.push(proc.segment);
                result.push(segment);
            }
            OP_INSERT_AFTER => {
                result.push(segment);
                result.push(proc.segment);
            }
            _ => {
                result.push(proc.segment);
                skip = Some(index + 1);
            }
        }
    }
    if cut != NO_CUT && cut as usize >= form.len() {
        new_cut = result.len() as i32;
    }
    let alive = result.len() >= 2 && result.iter().any(|&segment| vowel[segment as usize]);
    let output = if alive && result.as_slice() != form {
        Some((result.clone(), new_cut))
    } else {
        None
    };
    scratch.result = result;
    output
}
