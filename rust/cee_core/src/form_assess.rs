//! Hodnocení analogických změn tvarů v Rustu (B6b): zrcadlo `cee.v2.morphology._assess_reference`.
//!
//! Hodnocení změny tvaru slova (vyrovnání kmene, rozšíření vzoru, reanalýza hranice) má pět
//! hodnot: zisk (`gain`), frekvence lexému, příznak „tvar zní stejně jako citační tvar“ před
//! změnou a po ní a `None`, když změna nic nezmění. Všechno se počítá z čísel:
//!
//! - tvar slova a kořene z úložiště tvarů kódu (číslo tvaru v bance, hranice, koncovka) a z
//!   výchozích tvarů morfémů v aréně morfologického indexu (`MorphIndex::default_form`);
//! - koncovky a podoby koncovek (`class_stats`) ze stavu téhož morfologického indexu
//!   (`cell_exponents`, `dominant_ending`), takže se nic nepočítá znovu;
//! - frekvence užití lexému z dominantních kořenů (pole podle čísla pojmu), pořadí vložení pojmů
//!   do mapy (součet po pojmech v témže pořadí jako v Pythonu) a frekvencí pojmů.
//!
//! Nový tvar se do banky nezařazuje: hodnocení potřebuje jen vědět, zda se rovná citačnímu tvaru,
//! a to se porovná po hláskách.
//!
//! **Uložení.** Hodnota se drží podle (kód, pořadí proměnné tvarů) v husté tabulce kódu, dokud se
//! nezmění verze kódu; se změnou verze se tabulka zahodí a hodnoty se dopočítají znovu, když je
//! tlaky potřebují. Totéž dělal Python (`FormAssessmentIndex`), který zrušil jen hodnoty, kterých
//! se změna týká; hodnota je ale čistá funkce stavu kódu, takže dopočítaná hodnota je stejná.
//! Hledání dotčených hodnocení (dřív slovníky množin podle čísel) proto odpadá.

use crate::assess_index::{FormEntry, Inputs, Needs};
use crate::bank::Bank;
use crate::morphology_index::MorphIndex;

/// Operace analogické změny (`FormChange.operation`).
pub const LEVEL: u8 = 0;
pub const EXTEND: u8 = 1;
pub const PREPEND: u8 = 2;
pub const DROP_INITIAL: u8 = 3;

/// Kód druhu morfému „tvar slova“ (`MORPHEME_KINDS` v `cee.v2.tables`).
const KIND_WORD: i8 = 2;
const NONE: u32 = u32::MAX;

/// Analogická změna jednoho tvaru slova (`cee.v2.language.morphology.FormChange`) jako čísla.
#[derive(Clone, Copy, Debug)]
pub struct FormChange {
    pub operation: u8,
    /// Číslo morfému tvaru slova, kterého se změna týká.
    pub unit: u32,
    /// Číslo koncovky (−1 = žádná; mají ji jen rozšíření).
    pub exponent: i32,
    /// Hláska reanalýzy hranice (−1 = žádná).
    pub segment: i32,
}

/// Změny tvarů podle čísla proměnné; každá dostane pořadové číslo (řádek hustých tabulek kódů).
#[derive(Default)]
pub struct FormRegistry {
    ordinal: Vec<u32>,
    changes: Vec<FormChange>,
}

impl FormRegistry {
    pub fn register(&mut self, variable: u32, change: FormChange) {
        let at = variable as usize;
        if self.ordinal.len() <= at {
            self.ordinal.resize(at + 1, NONE);
        }
        match self.ordinal[at] {
            NONE => {
                self.ordinal[at] = self.changes.len() as u32;
                self.changes.push(change);
            }
            found => self.changes[found as usize] = change,
        }
    }

    pub fn has(&self, variable: u32) -> bool {
        self.ordinal
            .get(variable as usize)
            .is_some_and(|&found| found != NONE)
    }

    pub fn get(&self, variable: u32) -> Option<(usize, FormChange)> {
        match self.ordinal.get(variable as usize) {
            Some(&found) if found != NONE => Some((found as usize, self.changes[found as usize])),
            _ => None,
        }
    }
}

/// Uložená hodnota: 0 = nespočteno, 1 = hodnocení je `None`, 2 = hodnocení existuje.
#[derive(Clone, Copy, Default)]
struct Slot {
    state: u8,
    gain: f64,
    frequency: f64,
    before: bool,
    after: bool,
}

/// Pojmy, pro které je kořen dominantní, seřazené podle kořene a uvnitř kořene v pořadí vložení
/// pojmů do mapy dominantních kořenů (na tom stojí pořadí součtu frekvencí).
#[derive(Default)]
struct Usage {
    stamp: Option<i64>,
    pairs: Vec<(u32, u32)>,
}

/// Hodnocení tvarů jednoho kódu.
#[derive(Default)]
pub struct FormState {
    synced: Option<i64>,
    slots: Vec<Slot>,
    usage: Usage,
}

/// Pole z Pythonu, ze kterých se hodnocení tvarů počítá (podle pozice skupiny, resp. čísla morfému).
pub struct FormInputs<'a> {
    /// Úložiště tvarů kódů: hranice koncovky a číslo morfému koncovky (číslo tvaru je `Inputs::forms`).
    pub boundary: Vec<&'a [i32]>,
    pub exponent: Vec<&'a [i32]>,
    /// Čísla pojmů, které mají dominantní kořen, v pořadí vložení, a razítko jejich stavu.
    pub order: Vec<&'a [i32]>,
    pub stamps: &'a [i64],
    /// Sloupce tabulky morfémů: druh, třída slova, koncovka a hranice výchozího tvaru, frekvence.
    pub kind: &'a [i8],
    pub class: &'a [i32],
    pub unit_exponent: &'a [i32],
    pub unit_boundary: &'a [i32],
    pub frequency: &'a [f64],
    /// Váha buňky paradigmatu podle (třída, buňka), řádky po `cells` buňkách; 1 tam, kde se neváží.
    pub weights: &'a [f64],
    pub cells: usize,
    /// Frekvence pojmů podle čísla pojmu (chybějící 0,3, jako `World.concept_frequency`).
    pub concept_frequency: &'a [f64],
}

/// Co hodnocení čte; sestaví se z polí kroku.
pub struct FormCtx<'a> {
    pub bank: &'a Bank,
    pub morph: &'a MorphIndex,
    pub inp: &'a Inputs<'a>,
    pub fi: &'a FormInputs<'a>,
    /// Dominantní kořeny podle čísla pojmu, podle pozice skupiny.
    pub roots: &'a [&'a [i32]],
}

fn item<T: Copy>(values: &[T], number: usize, missing: T) -> T {
    values.get(number).copied().unwrap_or(missing)
}

/// Odkud se čtou tvary jednoho kódu: úložiště tvarů kódu (číslo tvaru v bance, hranice, koncovka),
/// výchozí tvary morfémů v aréně morfologického indexu a sloupce tabulky morfémů.
#[derive(Clone, Copy)]
pub struct UnitSource<'a> {
    pub bank: &'a Bank,
    pub morph: &'a MorphIndex,
    pub token: i64,
    pub forms: &'a [i32],
    pub boundary: &'a [i32],
    pub exponent: &'a [i32],
    pub unit_boundary: &'a [i32],
    pub unit_exponent: &'a [i32],
    pub lexeme: &'a [i32],
}

impl<'a> UnitSource<'a> {
    /// Tvar morfému v kódu (z úložiště, jinak výchozí z arény); `Err(číslo)`, chybí-li výchozí tvar.
    pub fn form_of(&self, number: u32) -> Result<&'a [i32], u32> {
        let raw = item(self.forms, number as usize, -1);
        if raw >= 0 {
            Ok(self.bank.form_of(raw as usize))
        } else {
            self.morph.default_form(number as usize).ok_or(number)
        }
    }

    /// Stav tvaru slova (`World.unit_of`): tvar, hranice koncovky (−1 = žádná) a koncovka (−1 = žádná).
    pub fn unit_of(&self, number: u32) -> Result<(&'a [i32], i32, i32), u32> {
        let at = number as usize;
        let form = self.form_of(number)?;
        Ok(if item(self.forms, at, -1) >= 0 {
            (
                form,
                item(self.boundary, at, -1),
                item(self.exponent, at, -1),
            )
        } else {
            (
                form,
                item(self.unit_boundary, at, -1),
                item(self.unit_exponent, at, -1),
            )
        })
    }
}

/// Nový tvar slova po analogické změně (`apply_form_change`) jako sled úseků: případná hláska na
/// začátku, pak `first` a `second`. Nic se nekopíruje, dokud ho nepotřebuje banka.
pub struct Rewrite<'a> {
    pub head: Option<i32>,
    pub first: &'a [i32],
    pub second: &'a [i32],
    /// Hranice koncovky nového stavu a jeho koncovka (−1 = žádná).
    pub boundary: i32,
    pub exponent: i32,
    /// Dosavadní tvar slova, jeho koncovka a citační tvar lexému.
    pub current: &'a [i32],
    pub current_exponent: i32,
    pub citation: &'a [i32],
}

impl Rewrite<'_> {
    /// Rovná se nový tvar `other`?
    pub fn equals(&self, other: &[i32]) -> bool {
        let skip = usize::from(self.head.is_some());
        self.head.is_none_or(|head| other.first() == Some(&head))
            && other.len() == skip + self.first.len() + self.second.len()
            && other[skip..skip + self.first.len()] == *self.first
            && other[skip + self.first.len()..] == *self.second
    }

    pub fn to_vec(&self) -> Vec<i32> {
        let mut form = Vec::with_capacity(self.first.len() + self.second.len() + 1);
        form.extend(self.head);
        form.extend_from_slice(self.first);
        form.extend_from_slice(self.second);
        form
    }
}

/// Přepis tvaru slova podle analogické změny; `None`, když změna nic nezmění (`apply_form_change`).
/// `Err(číslo morfému)`, chybí-li výchozí tvar v aréně.
pub fn rewrite<'a>(src: &UnitSource<'a>, change: FormChange) -> Result<Option<Rewrite<'a>>, u32> {
    let (form, boundary, exponent) = src.unit_of(change.unit)?;
    let root = item(src.lexeme, change.unit as usize, change.unit as i32) as u32;
    let citation = src.form_of(root)?;
    let cut = if boundary < 0 {
        form.len()
    } else {
        (boundary as usize).min(form.len())
    };
    let (stem, ending) = (&form[..cut], &form[cut..]);
    let made = |head, first, second, new_boundary, new_exponent| Rewrite {
        head,
        first,
        second,
        boundary: new_boundary,
        exponent: new_exponent,
        current: form,
        current_exponent: exponent,
        citation,
    };
    Ok(match change.operation {
        LEVEL => {
            if stem == citation {
                None
            } else {
                Some(made(
                    None,
                    citation,
                    ending,
                    citation.len() as i32,
                    exponent,
                ))
            }
        }
        EXTEND => match src.morph.dominant_ending(src.token, change.exponent) {
            Some(shape) if !(exponent == change.exponent && ending == shape) => {
                Some(made(None, stem, shape, stem.len() as i32, change.exponent))
            }
            _ => None,
        },
        PREPEND => Some(made(
            Some(change.segment),
            form,
            &[],
            if boundary < 0 { -1 } else { boundary + 1 },
            exponent,
        )),
        _ => {
            if form.first() != Some(&change.segment) || form.len() < 3 {
                None
            } else {
                Some(made(
                    None,
                    &form[1..],
                    &[],
                    if boundary < 0 { -1 } else { boundary - 1 },
                    exponent,
                ))
            }
        }
    })
}

impl FormCtx<'_> {
    /// Zdroj tvarů kódu skupiny `g`.
    fn source(&self, g: usize) -> UnitSource<'_> {
        UnitSource {
            bank: self.bank,
            morph: self.morph,
            token: self.inp.tokens[g],
            forms: self.inp.forms[g],
            boundary: self.fi.boundary[g],
            exponent: self.fi.exponent[g],
            unit_boundary: self.fi.unit_boundary,
            unit_exponent: self.fi.unit_exponent,
            lexeme: self.inp.lexeme,
        }
    }

    /// Frekvence užití lexému kódem (`World.usage_frequency`): součet frekvencí pojmů, pro které je
    /// kořen dominantní (nejvýš 1, u tvaru slova s buňkou vynásobený vahou buňky), jinak statická
    /// frekvence morfému.
    fn usage(&self, usage: &mut Usage, g: usize, root: u32) -> f64 {
        let stamp = self.fi.stamps[g];
        if usage.stamp != Some(stamp) {
            let roots = self.roots[g];
            usage.pairs.clear();
            for &concept in self.fi.order[g] {
                let found = item(roots, concept as usize, -1);
                if found >= 0 {
                    usage.pairs.push((found as u32, concept as u32));
                }
            }
            // Řazení je stabilní: uvnitř kořene zůstane pořadí vložení.
            usage.pairs.sort_by_key(|pair| pair.0);
            usage.stamp = Some(stamp);
        }
        let begin = usage.pairs.partition_point(|pair| pair.0 < root);
        let mut total = 0.0_f64;
        let mut any = false;
        for pair in &usage.pairs[begin..] {
            if pair.0 != root {
                break;
            }
            any = true;
            total += item(self.fi.concept_frequency, pair.1 as usize, 0.3);
        }
        let at = root as usize;
        if !any {
            return item(self.fi.frequency, at, f64::NAN);
        }
        let mut total = if total < 1.0 { total } else { 1.0 };
        let (class, cell) = (item(self.fi.class, at, -1), item(self.inp.cell, at, -1));
        if item(self.fi.kind, at, -1) == KIND_WORD && class >= 0 && cell >= 0 {
            let weight = self
                .fi
                .weights
                .get(class as usize * self.fi.cells + cell as usize)
                .copied()
                .unwrap_or(1.0);
            total *= weight;
        }
        total
    }

    /// Podíl koncovky mezi tvary buňky (`ClassStats.share`).
    fn share(&self, token: i64, class: i32, cell: i32, exponent: i32) -> f64 {
        match self.morph.cell_exponents(token, class, cell) {
            Some(counts) if exponent >= 0 => {
                let sum: u32 = counts.iter().map(|&(_, count)| count).sum();
                let mine = counts
                    .iter()
                    .find(|&&(e, _)| e == exponent)
                    .map_or(0, |&(_, count)| count);
                f64::from(mine) / f64::from(sum)
            }
            _ => 0.0,
        }
    }
}

/// Hodnocení změny kódu `g`; `Err(číslo morfému)`, chybí-li jeho výchozí tvar v aréně.
fn evaluate(
    ctx: &FormCtx<'_>,
    usage: &mut Usage,
    g: usize,
    change: FormChange,
) -> Result<Option<FormEntry>, u32> {
    let token = ctx.inp.tokens[g];
    let Some(new) = rewrite(&ctx.source(g), change)? else {
        return Ok(None);
    };
    let root = item(ctx.inp.lexeme, change.unit as usize, change.unit as i32) as u32;
    let gain = match change.operation {
        LEVEL => 1.0,
        EXTEND => {
            let (class, cell) = (
                item(ctx.fi.class, change.unit as usize, -1),
                item(ctx.inp.cell, change.unit as usize, -1),
            );
            ctx.share(token, class, cell, change.exponent)
                - ctx.share(token, class, cell, new.current_exponent)
        }
        _ => 0.0,
    };
    Ok(Some(FormEntry {
        present: true,
        gain,
        frequency: ctx.usage(usage, g, root),
        before: new.current == new.citation,
        after: new.equals(new.citation),
    }))
}

/// Hodnocení změny tvaru `variable` v kódu skupiny `g`: uložená hodnota, nebo spočtená teď.
/// `Ok(None)`, když výpočet čeká na výchozí tvar morfému (zapsáno do `needs`); chyba, když změna
/// tvaru není zaregistrovaná (rukojeť indexu se nahradila a popis řádků zůstal).
pub fn lookup(
    registry: &FormRegistry,
    state: &mut FormState,
    ctx: &FormCtx<'_>,
    g: usize,
    variable: u32,
    needs: &mut Needs,
) -> Result<Option<FormEntry>, String> {
    let (ordinal, change) = registry
        .get(variable)
        .ok_or_else(|| format!("změna tvaru č. {variable} není zaregistrovaná"))?;
    let version = ctx.inp.versions[g];
    if state.synced != Some(version) {
        state.slots.clear();
        state.synced = Some(version);
    }
    if state.slots.len() <= ordinal {
        state.slots.resize(ordinal + 1, Slot::default());
    }
    let slot = state.slots[ordinal];
    if slot.state == 0 {
        match evaluate(ctx, &mut state.usage, g, change) {
            Ok(found) => {
                state.slots[ordinal] = match found {
                    Some(value) => Slot {
                        state: 2,
                        gain: value.gain,
                        frequency: value.frequency,
                        before: value.before,
                        after: value.after,
                    },
                    None => Slot {
                        state: 1,
                        ..Slot::default()
                    },
                };
            }
            Err(morpheme) => {
                needs.morph_defaults.insert(morpheme);
                return Ok(None);
            }
        }
    }
    let slot = state.slots[ordinal];
    Ok(Some(FormEntry {
        present: slot.state == 2,
        gain: slot.gain,
        frequency: slot.frequency,
        before: slot.before,
        after: slot.after,
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::morphology_index::{CodeInput, Columns, Store};

    /// Morfémy: 0 kořen, 1 a 2 tvary slova téhož lexému v buňce 1, 3 a 4 koncovky.
    struct Table {
        kind: Vec<i8>,
        class: Vec<i32>,
        cell: Vec<i32>,
        lexeme: Vec<i32>,
        exponent: Vec<i32>,
        boundary: Vec<i32>,
        frequency: Vec<f64>,
    }

    fn table() -> Table {
        Table {
            kind: vec![2, 2, 2, 1, 1],
            class: vec![0, 0, 0, -1, -1],
            cell: vec![0, 1, 1, -1, -1],
            lexeme: vec![0, 0, 0, 3, 4],
            exponent: vec![-1, 3, 3, -1, -1],
            boundary: vec![-1, 2, 2, -1, -1],
            frequency: vec![0.5, 0.25, 0.25, 0.1, 0.1],
        }
    }

    fn fixture<R>(
        store: [&[i32]; 3],
        change: FormChange,
        usage_order: &[i32],
        roots: &[i32],
        run: impl FnOnce(&FormCtx<'_>, &mut Usage, FormChange) -> R,
    ) -> R {
        let mut bank = Bank::new(10, vec![false; 11]).expect("banka");
        bank.push(&[3, 2]).expect("tvar 0");
        let t = table();
        let mut morph = MorphIndex::new();
        morph.names.extend(&["a", "b", "c", "x", "y"]);
        morph.defaults.set(0, &[1, 2]);
        morph.defaults.set(1, &[1, 2, 5]);
        morph.defaults.set(2, &[1, 2, 5]);
        let cols = Columns {
            kind: &t.kind,
            class: &t.class,
            cell: &t.cell,
            lexeme: &t.lexeme,
            exponent: &t.exponent,
            boundary: &t.boundary,
        };
        let input = CodeInput {
            token: 7,
            flags: &[0, 1, 1, 0, 0],
            store: Store {
                form: store[0],
                boundary: store[1],
                exponent: store[2],
            },
        };
        assert!(morph.sync(&bank, &cols, &input).expect("sync").is_empty());
        let (tokens, versions, rules) = ([7_i64], [0_i64], [0_u8]);
        let inp = Inputs {
            tokens: &tokens,
            versions: &versions,
            rules: &rules,
            forms: vec![store[0]],
            defaults: &[],
            lexeme: &t.lexeme,
            cell: &t.cell,
            paradigm_weight: 1.0,
            redundant_weight: 1.0,
        };
        let fi = FormInputs {
            boundary: vec![store[1]],
            exponent: vec![store[2]],
            order: vec![usage_order],
            stamps: &[1],
            kind: &t.kind,
            class: &t.class,
            unit_exponent: &t.exponent,
            unit_boundary: &t.boundary,
            frequency: &t.frequency,
            weights: &[1.0, 0.5],
            cells: 2,
            concept_frequency: &[0.25, 0.5, 0.125],
        };
        let rows: Vec<&[i32]> = vec![roots];
        let ctx = FormCtx {
            bank: &bank,
            morph: &morph,
            inp: &inp,
            fi: &fi,
            roots: &rows,
        };
        run(&ctx, &mut Usage::default(), change)
    }

    #[test]
    fn rozsireni_dava_zisk_z_podilu_koncovek_a_frekvenci_ze_souctu_pojmu() {
        let none = [-1_i32; 5];
        let change = FormChange {
            operation: EXTEND,
            unit: 2,
            exponent: 3,
            segment: -1,
        };
        // Tvar 2 nese koncovku 3 stejně jako tvar 1 a stejnou podobu: změna nic nemění.
        let found = fixture(
            [&none, &none, &none],
            change,
            &[],
            &[],
            |ctx, usage, change| evaluate(ctx, usage, 0, change),
        );
        assert!(found.expect("výchozí tvary jsou v aréně").is_none());
        // Tvar 2 přepsaný na [3, 2] s koncovkou 4 (podoba [2]): rozšíření na koncovku 3 (podoba [5])
        // je změna; koncovka 3 má jednu ze dvou koncovek (1/2), tvar 2 nese koncovku 4 (1/2).
        let (mut form, mut boundary, mut exponent) = (none, none, none);
        (form[2], boundary[2], exponent[2]) = (0, 1, 4);
        let found = fixture(
            [&form, &boundary, &exponent],
            change,
            &[0, 1, 2],
            &[0, 0, 5],
            |ctx, usage, change| evaluate(ctx, usage, 0, change),
        )
        .expect("výchozí tvary jsou v aréně")
        .expect("změna něco mění");
        assert_eq!(found.gain.to_bits(), (0.5_f64 - 0.5).to_bits());
        // Kořen 0 je dominantní pro pojmy 0 a 1: 0,25 + 0,5; tvar 0 je v buňce 0 s vahou 1.
        assert_eq!(found.frequency.to_bits(), (0.25_f64 + 0.5).to_bits());
        assert!(!found.before && !found.after);
    }

    #[test]
    fn vyrovnani_nahradi_kmen_citacnim_tvarem_a_bez_koncovky_splyne() {
        let none = [-1_i32; 5];
        let change = FormChange {
            operation: LEVEL,
            unit: 1,
            exponent: -1,
            segment: -1,
        };
        // Kmen [1, 2] se shoduje s citačním tvarem kořene [1, 2]: nic se nemění.
        let found = fixture(
            [&none, &none, &none],
            change,
            &[],
            &[],
            |ctx, usage, change| evaluate(ctx, usage, 0, change),
        );
        assert!(found.expect("v aréně").is_none());
        // Tvar 1 má jiný kmen (tvar v bance 0 = [3, 2], hranice 1): vyrovnání dá [1, 2] + [2].
        let (mut form, mut boundary, mut exponent) = (none, none, none);
        (form[1], boundary[1], exponent[1]) = (0, 1, 3);
        let found = fixture(
            [&form, &boundary, &exponent],
            change,
            &[],
            &[],
            |ctx, usage, change| evaluate(ctx, usage, 0, change),
        )
        .expect("v aréně")
        .expect("změna něco mění");
        assert_eq!(found.gain, 1.0);
        // Bez dominantních pojmů platí statická frekvence kořene.
        assert_eq!(found.frequency.to_bits(), 0.5_f64.to_bits());
        assert!(!found.before && !found.after);
    }

    #[test]
    fn reanalyza_hranice_zna_odebrani_pocatecni_hlasky_jen_u_dostatecne_dlouheho_tvaru() {
        let none = [-1_i32; 5];
        let drop = FormChange {
            operation: DROP_INITIAL,
            unit: 1,
            exponent: -1,
            segment: 1,
        };
        let found = fixture(
            [&none, &none, &none],
            drop,
            &[],
            &[],
            |ctx, usage, change| evaluate(ctx, usage, 0, change),
        )
        .expect("v aréně")
        .expect("tvar [1, 2, 5] začíná na hlásku 1");
        assert_eq!(found.gain, 0.0);
        assert!(!found.after);
        let other = FormChange { segment: 9, ..drop };
        let found = fixture(
            [&none, &none, &none],
            other,
            &[],
            &[],
            |ctx, usage, change| evaluate(ctx, usage, 0, change),
        );
        assert!(found.expect("v aréně").is_none());
    }

    #[test]
    fn chybejici_vychozi_tvar_se_vyzada_a_hodnota_se_uklada_po_verzi() {
        let none = [-1_i32; 5];
        let change = FormChange {
            operation: PREPEND,
            unit: 2,
            exponent: -1,
            segment: 4,
        };
        let mut registry = FormRegistry::default();
        registry.register(12, change);
        assert!(registry.has(12) && !registry.has(3));
        let mut state = FormState::default();
        let mut needs = Needs::default();
        let first = fixture([&none, &none, &none], change, &[], &[], |ctx, _, _| {
            lookup(&registry, &mut state, ctx, 0, 12, &mut needs)
        })
        .expect("zaregistrováno")
        .expect("hodnota");
        assert!(first.present && !first.after);
        assert!(needs.morph_defaults.is_empty());
        assert_eq!(state.slots.len(), 1);
        // Stejná verze: hodnota zůstává; jiná verze: tabulka kódu se zahodí.
        assert_eq!(state.synced, Some(0));
    }
}
