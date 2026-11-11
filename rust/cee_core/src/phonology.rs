//! Krok fonologizace v Rustu: zrcadlo `cee.v2.phonology` (`restructure`,
//! `_queue`, `activate`, `enter_vocabulary`).
//!
//! Jádro nezná Python ani jeho slovníky. Dostane pole, která už existují
//! (podkladové tvary kódu, výchozí sloupce morfémů světa, bitové sady front
//! a přepsaných morfémů, sklony slov), a vrátí rozhodnutí: co se přepsalo,
//! co se zařadí do kterých front a které nové tvary vznikly. Zapisuje až
//! Python, a to ve stejném pořadí jako dřív (deník tvarů, verze stavu,
//! historie).
//!
//! **Co zůstalo v Pythonu a proč.** Sklon slova (`word_bias`) losuje
//! seedovaný `Stream` a četnost užití (`usage_frequency`) čte paměť světa,
//! obojí je čistá funkce, kterou jádro nemá znovu psát. Když hodnota chybí,
//! jádro **nic nezapíše** a vrátí `Needs` (co má Python spočítat: sklony,
//! četnosti, výchozí tvary, mapy hlásek); Python to doplní a zavolá znovu.
//! Logity (`log`, `exp`) se tu nepočítají vůbec: Python předá hotový základ
//! `log(p / (1 − p))` a práh `level`, jádro jen odečítá, takže bitová shoda
//! nezávisí na libm.
//!
//! Pořadí fronty (potřebný logit, jméno morfému) drží Python: jádro vrací
//! vkládané dvojice a Python je vloží (`ProcessQueue.insert`), při shodě
//! logitů rozhoduje jméno. Jméno jádro nezná, proto aktivace vrací dvojice
//! seřazené podle (logit, číslo) a Python srovná jen úseky shodných logitů.

use crate::flags::Flags;
#[cfg(test)]
use crate::flags::EMPTY;
use std::collections::BTreeMap;
use std::collections::BTreeSet;

use crate::bank::{Applied, Bank, MapNeeds, Outcome, UNCHANGED};

/// V polích: položka není nastavena.
pub const UNSET: i32 = -1;

/// `Target::row`: fronta se přeskočí.
pub const SKIP: i64 = -1;
/// `Target::row`: tabulka procesu s tímto pravidlem přízvuku v bance ještě není.
/// Založí ji Python (`FormBank.process_table`), ale až když na frontu dojde:
/// morfém, který se už zapsal nebo čeká, tabulku nezakládá (kdo má tabulku,
/// rozhoduje u přepsaných slov předfiltr, viz `restructure`).
pub const NO_TABLE: i64 = -2;

/// Podkladové tvary kódu (`FormStore`) a výchozí sloupce morfémů světa.
pub struct Units<'a> {
    pub form: &'a [i32],
    pub cut: &'a [i32],
    pub exponent: &'a [i32],
    pub default_form: &'a [i32],
    pub default_cut: &'a [i32],
    pub default_exponent: &'a [i32],
    /// Číslo lexému každého morfému (u kořene a koncovky on sám).
    pub lexeme: &'a [i32],
    /// Tvary přepsané v průběhu volání, které Python do `form`, `cut` a `exponent`
    /// ještě nezapsal (dávka víc procesů a skupin v jednom volání); mají přednost.
    pub overlay: &'a BTreeMap<usize, Unit>,
}

/// Prázdné přepsané tvary.
pub static NO_OVERLAY: BTreeMap<usize, Unit> = BTreeMap::new();

/// Aktuální stav tvaru slova: číslo tvaru v bance, hranice kmen | koncovka
/// (−1 = žádná) a číslo morfému koncovky (−1 = žádná).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Unit {
    pub form: usize,
    pub cut: i32,
    pub exponent: i32,
}

impl Units<'_> {
    /// Tvar morfému v kódu: uložený, jinak výchozí. `None`, když výchozí tvar
    /// ještě není v bance (Python ho zařadí přes `World.form_id_of`).
    pub fn get(&self, morpheme: usize) -> Option<Unit> {
        if let Some(&unit) = self.overlay.get(&morpheme) {
            return Some(unit);
        }
        if let Some(&form) = self.form.get(morpheme).filter(|&&form| form >= 0) {
            return Some(Unit {
                form: form as usize,
                cut: self.cut[morpheme],
                exponent: self.exponent[morpheme],
            });
        }
        let form = *self.default_form.get(morpheme).filter(|&&form| form >= 0)?;
        Some(Unit {
            form: form as usize,
            cut: self.default_cut[morpheme],
            exponent: self.default_exponent[morpheme],
        })
    }

    fn lexeme_of(&self, morpheme: usize) -> Result<usize, String> {
        match self.lexeme.get(morpheme) {
            Some(&lexeme) if lexeme >= 0 => Ok(lexeme as usize),
            _ => Err(format!(
                "morfém č. {morpheme} nemá lexém ve sloupcích světa"
            )),
        }
    }
}

/// Jedna fronta, do které se může zařadit: živý proces kódu.
#[derive(Clone, Copy)]
pub struct Target<'a> {
    /// Řádek změny v bance. `SKIP` = fronta se přeskočí (tabulka s tímto
    /// pravidlem přízvuku neexistuje a nemá se zakládat); `NO_TABLE` = tabulka
    /// neexistuje a založí se, až na ni dojde (viz `Needs::tables`).
    pub row: i64,
    /// Morfémy, které v frontě čekají, a které si změnu už zapsaly (příznaky).
    pub queued: &'a Flags,
    pub restructured: &'a Flags,
    /// Sklon slov vůči změně podle čísla lexému; NaN = ještě nelosováno.
    pub bias: &'a [f64],
    pub reductive: bool,
}

/// Společné číslo pravidla přízvuku a konstanty logitů.
#[derive(Clone, Copy)]
pub struct Params {
    pub rule: u8,
    /// `log(práh / (1 − práh))`.
    pub base: f64,
    /// `frequency_lead`.
    pub lead_scale: f64,
}

/// Četnosti užití lexémů, které Python už spočítal (podle čísla lexému).
pub type Frequencies = BTreeMap<usize, f64>;

/// Zdroj četností užití lexémů (`usage_frequency` kořene): hotová mapa od Pythonu,
/// nebo výpočet z dominantních kořenů kódu (`code_state::LiveUsage`). `None` =
/// četnost nejde určit, volající ji vyžádá jako `Needs::freq`.
pub trait Frequency {
    fn of(&self, lexeme: usize) -> Option<f64>;
}

impl Frequency for Frequencies {
    fn of(&self, lexeme: usize) -> Option<f64> {
        self.get(&lexeme).copied()
    }
}

/// Co musí Python doplnit, než se výpočet dokončí.
#[derive(Default, Debug)]
pub struct Needs {
    /// Sklon slova: (číslo fronty, morfém, který ho vyžádal).
    pub bias: BTreeSet<(usize, usize)>,
    /// Četnost užití lexému.
    pub freq: BTreeSet<usize>,
    /// Morfém, jehož výchozí tvar ještě není v bance.
    pub forms: BTreeSet<usize>,
    /// Mapy hlásek pro operace `change` a `tone`.
    pub maps: MapNeeds,
    /// Fronty (podle čísla), jejichž tabulka procesu se má v bance založit.
    pub tables: BTreeSet<usize>,
}

impl Needs {
    pub fn is_empty(&self) -> bool {
        self.bias.is_empty()
            && self.freq.is_empty()
            && self.forms.is_empty()
            && self.maps.is_empty()
    }
}

/// Morfém, který se má zařadit do fronty č. `target`, s potřebným logitem.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Insert {
    pub target: usize,
    pub morpheme: usize,
    pub needed: f64,
}

/// Morfém přepsaný novým tvarem.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Rewrite {
    pub morpheme: usize,
    pub form: usize,
    pub cut: i32,
    pub exponent: i32,
}

fn flagged(flags: &Flags, morpheme: usize) -> bool {
    flags.get(morpheme)
}

/// Logit, při kterém si slovo změnu zapíše (`_needed`, `activate`):
/// `základ − náskok − sklon`, v tomto pořadí odčítání jako v Pythonu.
/// `None`, když chybí četnost či sklon (zapíše se do `needs`).
fn needed(
    params: &Params,
    target: &Target,
    index: usize,
    morpheme: usize,
    lexeme: usize,
    freq: &dyn Frequency,
    needs: &mut Needs,
) -> Option<f64> {
    let mut lead = 0.0;
    let mut complete = true;
    if target.reductive {
        match freq.of(lexeme) {
            Some(frequency) => lead = params.lead_scale * (2.0 * frequency - 1.0),
            None => {
                needs.freq.insert(lexeme);
                complete = false;
            }
        }
    }
    let bias = target
        .bias
        .get(lexeme)
        .copied()
        .filter(|bias| !bias.is_nan());
    if bias.is_none() {
        needs.bias.insert((index, morpheme));
        complete = false;
    }
    match (complete, bias) {
        (true, Some(bias)) => Some(params.base - lead - bias),
        _ => None,
    }
}

/// Fronty rozdělené podle řádku změny v bance: zařazení morfému pak nemusí projít všechny
/// živé procesy, jen ty, jejichž změna na tvar podle předfiltru banky sedí, a fronty bez
/// tabulky (ty o ni žádají každý morfém). Staví se jednou na dávku zařazení, ne na morfém.
#[derive(Default)]
pub struct RowIndex {
    /// Řádek změny → čísla front s touto tabulkou (vzestupně).
    by_row: BTreeMap<usize, Vec<usize>>,
    /// Fronty, jejichž tabulka v bance ještě není (`NO_TABLE`), vzestupně.
    no_table: Vec<usize>,
}

impl RowIndex {
    /// Index front `0..count`, `row(i)` je `Target::row` fronty `i`.
    pub fn new(count: usize, row: impl Fn(usize) -> i64) -> RowIndex {
        let mut index = RowIndex::default();
        for at in 0..count {
            match row(at) {
                SKIP => {}
                NO_TABLE => index.no_table.push(at),
                found => index.by_row.entry(found as usize).or_default().push(at),
            }
        }
        index
    }

    /// Index nad polem front.
    pub fn of(targets: &[Target]) -> RowIndex {
        RowIndex::new(targets.len(), |at| targets[at].row)
    }
}

/// `_queue` pro jeden morfém s tvarem `form_id` a všechny fronty (kromě `skip`): kdo se
/// nezapsal, nečeká a proces na tvar dopadne, ten se zařadí. `at(i)` dá frontu č. `i`;
/// `index` musí být postavený nad týmiž frontami. Prochází se jen fronty bez tabulky a ty,
/// jejichž řádek je v předfiltru tvaru, ve vzestupném pořadí čísel front (pořadí určuje
/// čísla nových tvarů v bance). Vrací zařazení; chybí-li něco, zapíše to do `needs`.
#[allow(clippy::too_many_arguments)]
fn queue_into<'t>(
    bank: &mut Bank,
    params: &Params,
    units: &Units,
    index: &RowIndex,
    at: &impl Fn(usize) -> Target<'t>,
    skip: &[usize],
    morpheme: usize,
    form_id: usize,
    freq: &dyn Frequency,
    needs: &mut Needs,
) -> Result<Vec<Insert>, String> {
    let lexeme = units.lexeme_of(morpheme)?;
    // Kandidáti: fronty bez tabulky a fronty, jejichž změna může tvar zasáhnout.
    let mut candidates: Vec<usize> = index.no_table.clone();
    if !index.by_row.is_empty() {
        let bits = bank.rows_of(form_id)?;
        for (word, &value) in bits.iter().enumerate() {
            let mut rest = value;
            while rest != 0 {
                let row = word * 64 + rest.trailing_zeros() as usize;
                rest &= rest - 1;
                if let Some(list) = index.by_row.get(&row) {
                    candidates.extend_from_slice(list);
                }
            }
        }
        candidates.sort_unstable();
    }
    let mut found = Vec::new();
    for position in candidates {
        let target = at(position);
        if skip.contains(&position) {
            continue;
        }
        if flagged(target.restructured, morpheme) || flagged(target.queued, morpheme) {
            continue;
        }
        if target.row == NO_TABLE {
            needs.tables.insert(position);
            continue;
        }
        let row = target.row as usize;
        match bank.hypo_lookup(row, params.rule, form_id, &mut needs.maps)? {
            Some(result) if result != UNCHANGED => {}
            _ => continue,
        }
        if let Some(value) = needed(params, &target, position, morpheme, lexeme, freq, needs) {
            found.push(Insert {
                target: position,
                morpheme,
                needed: value,
            });
        }
    }
    Ok(found)
}

/// `enter_vocabulary` a `requeue` pro všechny živé procesy: zařazení jednoho
/// morfému do front (`at(i)` dá frontu č. `i`, `index` je nad týmiž frontami). Při
/// chybějících údajích vrací prázdný seznam a `needs`.
pub fn queue_morpheme_with<'t>(
    bank: &mut Bank,
    params: &Params,
    units: &Units,
    index: &RowIndex,
    at: &impl Fn(usize) -> Target<'t>,
    morpheme: usize,
    freq: &dyn Frequency,
) -> Result<(Vec<Insert>, Needs), String> {
    let mut needs = Needs::default();
    let Some(unit) = units.get(morpheme) else {
        needs.forms.insert(morpheme);
        return Ok((Vec::new(), needs));
    };
    let found = queue_into(
        bank,
        params,
        units,
        index,
        at,
        &[],
        morpheme,
        unit.form,
        freq,
        &mut needs,
    )?;
    Ok(if needs.is_empty() {
        (found, needs)
    } else {
        (Vec::new(), needs)
    })
}

/// [`queue_morpheme_with`] nad polem front.
pub fn queue_morpheme(
    bank: &mut Bank,
    params: &Params,
    units: &Units,
    targets: &[Target],
    morpheme: usize,
    freq: &dyn Frequency,
) -> Result<(Vec<Insert>, Needs), String> {
    let index = RowIndex::of(targets);
    queue_morpheme_with(
        bank,
        params,
        units,
        &index,
        &|at| targets[at],
        morpheme,
        freq,
    )
}

/// Výsledek kroku jednoho procesu.
#[derive(Default, Debug)]
pub struct StepOut {
    /// Kolik morfémů z čela fronty se odebralo (přepsaných i nepřepsaných).
    pub popped: usize,
    pub rewrites: Vec<Rewrite>,
    pub inserts: Vec<Insert>,
    /// Co zastavilo krok; prázdné = fronta došla na práh `level`.
    pub needs: Needs,
}

/// Cyklus `while queue and queue.needed[0] < level` z `restructure` pro proces
/// na řádku `row`: odebírá z čela fronty, přepisuje tvar a zařazuje přepsaný
/// morfém do front ostatních procesů (`targets` bez `skip`). Když něco chybí,
/// skončí **před** dalším odebráním a vrátí, co se do té doby stalo.
#[allow(clippy::too_many_arguments)]
pub fn step(
    bank: &mut Bank,
    params: &Params,
    units: &Units,
    row: usize,
    queue_needed: &[f64],
    queue_morphemes: &[i32],
    level: f64,
    targets: &[Target],
    skip: usize,
    no_feed: &[usize],
    freq: &dyn Frequency,
) -> Result<StepOut, String> {
    let mut out = StepOut::default();
    let index = RowIndex::of(targets);
    while out.popped < queue_needed.len() && queue_needed[out.popped] < level {
        let morpheme = queue_morphemes[out.popped] as usize;
        let mut needs = Needs::default();
        let Some(unit) = units.get(morpheme) else {
            needs.forms.insert(morpheme);
            out.needs = needs;
            break;
        };
        let (form, cut) =
            match bank.apply_tracked(row, params.rule, unit.form, unit.cut, &mut needs.maps)? {
                Applied::Blocked => {
                    out.needs = needs;
                    break;
                }
                Applied::Unchanged => {
                    // Dřívější přepis jinou změnou mu vzal půdu.
                    out.popped += 1;
                    continue;
                }
                Applied::Changed { form, cut } => (form as usize, cut),
            };
        // Nový tvar posoudí jen ostatní živé procesy; sám sebe nikdy, ani procesy, po kterých
        // zaplňuje mezeru a které už převládly (protikrmení řetězového posunu, Kiparsky 1968).
        let mut skips = Vec::with_capacity(no_feed.len() + 1);
        skips.push(skip);
        skips.extend_from_slice(no_feed);
        let inserts = queue_into(
            bank,
            params,
            units,
            &index,
            &|at| targets[at],
            &skips,
            morpheme,
            form,
            freq,
            &mut needs,
        )?;
        if !needs.is_empty() {
            out.needs = needs;
            break;
        }
        out.popped += 1;
        out.rewrites.push(Rewrite {
            morpheme,
            form,
            cut,
            exponent: unit.exponent,
        });
        out.inserts.extend(inserts);
    }
    Ok(out)
}

/// Výsledek aktivace procesu.
#[derive(Default, Debug)]
pub struct ActivateOut {
    /// Čekající morfémy seřazené podle (logit, číslo morfému) a jejich logity.
    pub morphemes: Vec<usize>,
    pub needed: Vec<f64>,
    pub needs: Needs,
}

/// `activate`: fronta procesu na řádku `row` ze slovní zásoby (příznaky
/// `vocabulary`). Do fronty jdou slova, kterých se změna týká a která si ji
/// ještě nezapsala (`target.restructured`).
#[allow(clippy::too_many_arguments)]
pub fn activate(
    bank: &mut Bank,
    params: &Params,
    units: &Units,
    row: usize,
    vocabulary: &[u8],
    target: &Target,
    freq: &dyn Frequency,
    names: Option<&[String]>,
) -> Result<ActivateOut, String> {
    let mut out = ActivateOut::default();
    let words: Vec<usize> = (0..vocabulary.len())
        .filter(|&word| vocabulary[word] == 1)
        .collect();
    let mut form_ids = Vec::with_capacity(words.len());
    for &word in &words {
        match units.get(word) {
            Some(unit) => form_ids.push(unit.form as i64),
            None => {
                out.needs.forms.insert(word);
            }
        }
    }
    if !out.needs.is_empty() {
        return Ok(out);
    }
    let found = match bank.hypo_results(row, params.rule, &form_ids)? {
        Outcome::Needs(segments) => {
            out.needs.maps.entry(row).or_default().extend(segments);
            return Ok(out);
        }
        Outcome::Done(found) => found,
    };
    let mut pairs = Vec::new();
    for (&word, &result) in words.iter().zip(&found) {
        if result < 0 || flagged(target.restructured, word) {
            continue;
        }
        let lexeme = units.lexeme_of(word)?;
        if let Some(value) = needed(params, target, 0, word, lexeme, freq, &mut out.needs) {
            pairs.push((value, word));
        }
    }
    if !out.needs.is_empty() {
        return Ok(out);
    }
    // Shodné logity (buňky téhož lexému) řadí jméno morfému, jako `ProcessQueue`;
    // bez jmen (testy jádra) číslo.
    pairs.sort_by(|left, right| {
        let tie = match names {
            Some(names) => names[left.1].as_bytes().cmp(names[right.1].as_bytes()),
            None => left.1.cmp(&right.1),
        };
        left.0
            .partial_cmp(&right.0)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then(tie)
    });
    out.needed = pairs.iter().map(|pair| pair.0).collect();
    out.morphemes = pairs.iter().map(|pair| pair.1).collect();
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::process::{Proc, OP_DELETE, OP_REPLACE, STRESS_NONE};

    /// Hlásky: 0 = a, 1 = k, 2 = t, 3 = d; hranice = 4. Změna 0: t → d mezi
    /// samohláskami; změna 1: k se maže.
    fn bank() -> Bank {
        let mut bank = Bank::new(4, vec![true, false, false, false, false]).unwrap();
        let everything = vec![true; 5];
        let mut target = vec![false; 5];
        target[2] = true;
        let mut vowels = vec![false; 5];
        vowels[0] = true;
        let replace = Proc {
            operation: OP_REPLACE,
            stress: STRESS_NONE,
            medial: false,
            segment: 3,
            target,
            left: vowels.clone(),
            right: vowels,
            right2: everything.clone(),
            map: vec![-3; 4],
        };
        bank.register_proc(0, replace).unwrap();
        let mut target = vec![false; 5];
        target[1] = true;
        let delete = Proc {
            operation: OP_DELETE,
            stress: STRESS_NONE,
            medial: false,
            segment: -1,
            target,
            left: everything.clone(),
            right: everything.clone(),
            right2: everything,
            map: vec![-3; 4],
        };
        bank.register_proc(1, delete).unwrap();
        bank
    }

    const PARAMS: Params = Params {
        rule: 3,
        base: -1.5,
        lead_scale: 0.5,
    };

    fn target<'a>(row: i64, queued: &'a Flags, bias: &'a [f64], reductive: bool) -> Target<'a> {
        Target {
            row,
            queued,
            restructured: &EMPTY,
            bias,
            reductive,
        }
    }

    /// Morfémy 0 až 2 s výchozími tvary 0 až 2; morfém č. = lexém č.
    fn units<'a>(forms: &'a [i32], lexeme: &'a [i32], none: &'a [i32]) -> Units<'a> {
        Units {
            form: &[],
            cut: &[],
            exponent: &[],
            default_form: forms,
            default_cut: none,
            default_exponent: none,
            lexeme,
            overlay: &NO_OVERLAY,
        }
    }

    #[test]
    fn krok_prepise_tvar_zaradi_ho_jinam_a_pocita_hranici_kmene() {
        let mut bank = bank();
        let kata = bank.push(&[1, 0, 2, 0]).unwrap() as i32; // kata
        let (forms, lexeme, none) = ([kata], [0], [-1]);
        let mut units = units(&forms, &lexeme, &none);
        let cuts = [2];
        units.default_cut = &cuts; // kata|… hranice za druhou hláskou
                                   // Fronta procesu 0 (t → d): morfém 0 čeká na -0.5; proces 1 (mazání k)
                                   // je cíl, do kterého se přepsaný tvar zařadí, ale jeho řádek nesedí
                                   // (v „kada“ už k není jinde než na začátku), takže ano.
        let bias = [0.25];
        let targets = [
            target(0, &EMPTY, &bias, false),
            target(1, &EMPTY, &bias, false),
        ];
        let out = step(
            &mut bank,
            &PARAMS,
            &units,
            0,
            &[-0.5],
            &[0],
            0.0,
            &targets,
            0,
            &[],
            &Frequencies::new(),
        )
        .unwrap();
        assert_eq!(out.popped, 1);
        assert!(out.needs.is_empty());
        // Vznikl jen „kada“ (posouzení cílem používá has_site bez zápisu do banky).
        let (first, flat, lengths) = bank.take_created();
        assert_eq!((first, flat, lengths), (1, vec![1, 0, 3, 0], vec![4]));
        assert_eq!(
            out.rewrites,
            vec![Rewrite {
                morpheme: 0,
                form: 1,
                cut: 2,
                exponent: -1
            }]
        );
        // k na začátku „kada“ proces 1 zasáhne: zařazení s logitem základ − sklon.
        assert_eq!(
            out.inserts,
            vec![Insert {
                target: 1,
                morpheme: 0,
                needed: -1.5 - 0.25
            }]
        );
    }

    #[test]
    fn chybi_li_sklon_krok_se_zastavi_pred_odebranim() {
        let mut bank = bank();
        let kata = bank.push(&[1, 0, 2, 0]).unwrap() as i32;
        let (forms, lexeme, none) = ([kata], [0], [-1]);
        let units = units(&forms, &lexeme, &none);
        let bias = [f64::NAN];
        let targets = [
            target(0, &EMPTY, &bias, false),
            target(1, &EMPTY, &bias, false),
        ];
        let out = step(
            &mut bank,
            &PARAMS,
            &units,
            0,
            &[-0.5],
            &[0],
            0.0,
            &targets,
            0,
            &[],
            &Frequencies::new(),
        )
        .unwrap();
        assert_eq!(
            (out.popped, out.rewrites.len(), out.inserts.len()),
            (0, 0, 0)
        );
        assert_eq!(
            out.needs.bias.iter().copied().collect::<Vec<_>>(),
            vec![(1, 0)]
        );
        // S doplněným sklonem krok doběhne a četnost se použije jen u redukčních změn.
        let bias = [0.0];
        let targets = [
            target(0, &EMPTY, &bias, false),
            target(1, &EMPTY, &bias, true),
        ];
        let out = step(
            &mut bank,
            &PARAMS,
            &units,
            0,
            &[-0.5],
            &[0],
            0.0,
            &targets,
            0,
            &[],
            &Frequencies::new(),
        )
        .unwrap();
        assert_eq!(out.needs.freq.iter().copied().collect::<Vec<_>>(), vec![0]);
        let freq = Frequencies::from([(0, 0.75)]);
        let out = step(
            &mut bank,
            &PARAMS,
            &units,
            0,
            &[-0.5],
            &[0],
            0.0,
            &targets,
            0,
            &[],
            &freq,
        )
        .unwrap();
        assert_eq!(out.inserts[0].needed, -1.5 - 0.5 * (2.0 * 0.75 - 1.0) - 0.0);
    }

    #[test]
    fn zarazeni_preskoci_cekajici_prepsane_a_morfem_bez_mista() {
        let mut bank = bank();
        let kata = bank.push(&[1, 0, 2, 0]).unwrap() as i32;
        let ta = bank.push(&[2, 0]).unwrap() as i32; // žádná změna nemá místo
        let (forms, lexeme, none) = ([kata, ta], [0, 1], [-1, -1]);
        let units = units(&forms, &lexeme, &none);
        let bias = [0.0, 0.0];
        let waiting = Flags::from_bytes(&[1u8]);
        let targets = [
            target(0, &waiting, &bias, false),
            target(1, &EMPTY, &bias, false),
        ];
        let (found, needs) =
            queue_morpheme(&mut bank, &PARAMS, &units, &targets, 0, &Frequencies::new()).unwrap();
        assert!(needs.is_empty());
        // Proces 0 má morfém 0 ve frontě; k se maže jen procesem 1.
        assert_eq!(
            found,
            vec![Insert {
                target: 1,
                morpheme: 0,
                needed: -1.5
            }]
        );
        let (found, _) =
            queue_morpheme(&mut bank, &PARAMS, &units, &targets, 1, &Frequencies::new()).unwrap();
        assert!(found.is_empty());
    }

    #[test]
    fn tabulka_se_zaklada_az_kdyz_na_frontu_dojde() {
        let mut bank = bank();
        let kata = bank.push(&[1, 0, 2, 0]).unwrap() as i32;
        let (forms, lexeme, none) = ([kata], [0], [-1]);
        let units = units(&forms, &lexeme, &none);
        let bias = [0.0];
        let waiting = Flags::from_bytes(&[1u8]);
        // Fronta bez tabulky a morfém, který v ní už čeká: tabulka se nezakládá.
        let targets = [target(NO_TABLE, &waiting, &bias, false)];
        let (found, needs) =
            queue_morpheme(&mut bank, &PARAMS, &units, &targets, 0, &Frequencies::new()).unwrap();
        assert!(found.is_empty() && needs.is_empty());
        // Nečeká-li, Rust o tabulku požádá a nic nezařadí.
        let targets = [target(NO_TABLE, &EMPTY, &bias, false)];
        let (found, needs) =
            queue_morpheme(&mut bank, &PARAMS, &units, &targets, 0, &Frequencies::new()).unwrap();
        assert!(found.is_empty());
        assert_eq!(needs.tables.iter().copied().collect::<Vec<_>>(), vec![0]);
        // Přeskočená fronta (strict) nezakládá nic.
        let targets = [target(SKIP, &EMPTY, &bias, false)];
        let (found, needs) =
            queue_morpheme(&mut bank, &PARAMS, &units, &targets, 0, &Frequencies::new()).unwrap();
        assert!(found.is_empty() && needs.is_empty());
    }

    #[test]
    fn aktivace_radi_podle_logitu_a_cisla_a_vynechava_prepsane() {
        let mut bank = bank();
        let kata = bank.push(&[1, 0, 2, 0]).unwrap() as i32;
        let pata = bank.push(&[1, 0, 2, 0, 0, 2, 0]).unwrap() as i32;
        let ta = bank.push(&[2, 0]).unwrap() as i32;
        let (forms, lexeme, none) = ([kata, pata, ta], [0, 1, 2], [-1; 3]);
        let units = units(&forms, &lexeme, &none);
        let bias = [0.5, 0.5, 0.25];
        let restructured = Flags::from_bytes(&[0u8, 1]);
        let mut target = target(0, &EMPTY, &bias, false);
        target.restructured = &restructured;
        let out = activate(
            &mut bank,
            &PARAMS,
            &units,
            0,
            &[1, 1, 1],
            &target,
            &Frequencies::new(),
            None,
        )
        .unwrap();
        assert!(out.needs.is_empty());
        // Morfém 1 se už zapsal, morfém 2 („ta“) nemá místo; zbývá morfém 0.
        assert_eq!((out.morphemes, out.needed), (vec![0], vec![-1.5 - 0.5]));
        let target = Target {
            restructured: &EMPTY,
            ..target
        };
        let out = activate(
            &mut bank,
            &PARAMS,
            &units,
            0,
            &[1, 1, 0],
            &target,
            &Frequencies::new(),
            None,
        )
        .unwrap();
        assert_eq!(out.morphemes, vec![0, 1]); // shodné logity: podle čísla
    }
}
