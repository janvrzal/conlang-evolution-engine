//! Přestavba tvarů kódu po analogii (B6b): zrcadlo smyčky v `cee.v2.morphology.restructure`.
//!
//! Analogie, která ve skupině převážila, se zapíše do tvaru slova: nový tvar vznikne z dnešního stavu
//! kódu (`form_assess::rewrite`) a další analogie téhož kódu už počítá se stavem po předchozím zápisu
//! (koncovky tříd a jejich podoby se mění s každým přepsaným tvarem). Rust proto zapisuje do vlastní
//! kopie úložiště tvarů (`overlay`) a po každém zápisu dorovná morfologický index kódu, aby další
//! analogie viděla totéž, co by viděla po skutečném zápisu v Pythonu. Nový tvar zařadí do banky
//! (`Bank::intern_form`; číslo převezme Python, `take_created`).
//!
//! Vrací zápisy v pořadí vstupu, nic jiného nemění. Python je provede (`FormStore.put`, fronty
//! fonologizace, verze kódu, historie) ve stejném pořadí jako dřív, takže po návratu je úložiště kódu
//! stejné jako kopie, kterou index zrovna dorovnal. Chybí-li výchozí tvar morfému v aréně indexu,
//! vrátí jeho číslo a nic nepředpokládá: volající ho dodá a zavolá znovu (zařazení tvarů do banky je
//! idempotentní).

use crate::bank::Bank;
use crate::form_assess::{rewrite, FormRegistry, UnitSource};
use crate::morphology_index::{CodeInput, Columns, MorphIndex, Store};

/// Zápis nového stavu tvaru slova do úložiště kódu: číslo morfému, číslo tvaru v bance, hranice
/// koncovky a koncovka (−1 = žádná).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Write {
    pub unit: u32,
    pub form: u32,
    pub boundary: i32,
    pub exponent: i32,
}

/// Výsledek: čísla morfémů, jejichž výchozí tvar chybí v aréně, nebo zápis (nebo `None`, když
/// změna nic nezmění) pro každou proměnnou vstupu.
#[derive(Debug, PartialEq, Eq)]
pub enum Applied {
    Needs(Vec<u32>),
    Done(Vec<Option<Write>>),
}

/// Kód, kterého se přestavba týká: vzorec `FormStore.raw()` a příznaky slovní zásoby.
pub struct Code<'a> {
    pub token: i64,
    pub flags: &'a [u8],
    pub store: Store<'a>,
}

/// Úložiště tvarů kódu s přepsanými stavy (kopie, dokud se nic nezapíše).
struct Overlay {
    form: Vec<i32>,
    boundary: Vec<i32>,
    exponent: Vec<i32>,
}

impl Overlay {
    fn new(store: &Store<'_>) -> Overlay {
        Overlay {
            form: store.form.to_vec(),
            boundary: store.boundary.to_vec(),
            exponent: store.exponent.to_vec(),
        }
    }

    fn put(&mut self, write: &Write) {
        let at = write.unit as usize;
        if self.form.len() <= at {
            self.form.resize(at + 1, -1);
            self.boundary.resize(at + 1, -1);
            self.exponent.resize(at + 1, -1);
        }
        self.form[at] = write.form as i32;
        self.boundary[at] = write.boundary;
        self.exponent[at] = write.exponent;
    }

    fn store(&self) -> Store<'_> {
        Store {
            form: &self.form,
            boundary: &self.boundary,
            exponent: &self.exponent,
        }
    }
}

/// Zapíše analogie `variables` (čísla proměnných tvarů, jen vyrovnání a rozšíření) do kódu v daném
/// pořadí. Morfologický index kódu zůstane ve stavu po všech zápisech.
pub fn apply_changes(
    registry: &FormRegistry,
    morph: &mut MorphIndex,
    bank: &mut Bank,
    cols: &Columns<'_>,
    code: &Code<'_>,
    variables: &[u32],
) -> Result<Applied, String> {
    let real = Store {
        form: code.store.form,
        boundary: code.store.boundary,
        exponent: code.store.exponent,
    };
    // Index nejdřív na skutečný stav kódu: po přerušeném volání může nést stav po zápisech, které
    // Python neprovedl.
    let needs = morph.sync(
        bank,
        cols,
        &CodeInput {
            token: code.token,
            flags: code.flags,
            store: Store {
                form: real.form,
                boundary: real.boundary,
                exponent: real.exponent,
            },
        },
    )?;
    if !needs.is_empty() {
        return Ok(Applied::Needs(needs));
    }
    let mut overlay: Option<Overlay> = None;
    let mut done = Vec::with_capacity(variables.len());
    for &variable in variables {
        let (_, change) = registry
            .get(variable)
            .ok_or_else(|| format!("změna tvaru č. {variable} není zaregistrovaná"))?;
        let made = {
            let current = overlay.as_ref().map_or_else(
                || Store {
                    form: real.form,
                    boundary: real.boundary,
                    exponent: real.exponent,
                },
                Overlay::store,
            );
            let source = UnitSource {
                bank: &*bank,
                morph: &*morph,
                token: code.token,
                forms: current.form,
                boundary: current.boundary,
                exponent: current.exponent,
                unit_boundary: cols.boundary,
                unit_exponent: cols.exponent,
                lexeme: cols.lexeme,
            };
            match rewrite(&source, change) {
                Err(morpheme) => return Ok(Applied::Needs(vec![morpheme])),
                Ok(found) => found.map(|new| (new.to_vec(), new.boundary, new.exponent)),
            }
        };
        let Some((form, boundary, exponent)) = made else {
            done.push(None);
            continue;
        };
        let write = Write {
            unit: change.unit,
            form: bank.intern_form(&form)?,
            boundary,
            exponent,
        };
        let held = overlay.get_or_insert_with(|| Overlay::new(&real));
        held.put(&write);
        let needs = morph.sync(
            bank,
            cols,
            &CodeInput {
                token: code.token,
                flags: code.flags,
                store: held.store(),
            },
        )?;
        if !needs.is_empty() {
            return Ok(Applied::Needs(needs));
        }
        done.push(Some(write));
    }
    Ok(Applied::Done(done))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::form_assess::{FormChange, EXTEND, LEVEL};

    /// Morfémy: 0 kořen, 1 až 3 tvary slova téhož lexému v buňkách 1 až 3 (třída 0), 4 a 5 koncovky.
    struct Table {
        kind: Vec<i8>,
        class: Vec<i32>,
        cell: Vec<i32>,
        lexeme: Vec<i32>,
        exponent: Vec<i32>,
        boundary: Vec<i32>,
    }

    fn table() -> Table {
        Table {
            kind: vec![2, 2, 2, 2, 1, 1],
            class: vec![0, 0, 0, 0, -1, -1],
            cell: vec![0, 1, 2, 3, -1, -1],
            lexeme: vec![0, 0, 0, 0, 4, 5],
            exponent: vec![-1, 4, 4, 5, -1, -1],
            boundary: vec![-1, 2, 2, 2, -1, -1],
        }
    }

    fn columns(t: &Table) -> Columns<'_> {
        Columns {
            kind: &t.kind,
            class: &t.class,
            cell: &t.cell,
            lexeme: &t.lexeme,
            exponent: &t.exponent,
            boundary: &t.boundary,
        }
    }

    fn start(second: &[i32]) -> (Bank, MorphIndex) {
        let mut bank = Bank::new(10, vec![false; 11]).expect("banka");
        // Tvar 0: [3, 2] (jiný kmen než citační tvar kořene).
        bank.push(&[3, 2]).expect("tvar 0");
        let mut morph = MorphIndex::new();
        morph.names.extend(&["a", "b", "c", "d", "x", "y"]);
        morph.defaults.set(0, &[1, 2]);
        morph.defaults.set(1, &[1, 2, 5]);
        morph.defaults.set(2, second);
        morph.defaults.set(3, &[1, 2, 7]);
        (bank, morph)
    }

    fn change(operation: u8, unit: u32, exponent: i32) -> FormChange {
        FormChange {
            operation,
            unit,
            exponent,
            segment: -1,
        }
    }

    #[test]
    fn vyrovnani_a_rozsireni_zapise_novy_tvar_do_banky() {
        let t = table();
        let cols = columns(&t);
        let (mut bank, mut morph) = start(&[1, 2, 5]);
        let mut registry = FormRegistry::default();
        registry.register(10, change(LEVEL, 1, -1));
        registry.register(11, change(EXTEND, 3, 4));
        let flags = [0_u8, 1, 1, 1, 0, 0];
        // Tvar 1 má jiný kmen ([3] místo [1, 2]), tvary 2 a 3 jsou výchozí.
        let mut form = [-1_i32; 6];
        let (mut boundary, mut exponent) = ([-1_i32; 6], [-1_i32; 6]);
        (form[1], boundary[1], exponent[1]) = (0, 1, 4);
        let code = Code {
            token: 7,
            flags: &flags,
            store: Store {
                form: &form,
                boundary: &boundary,
                exponent: &exponent,
            },
        };
        let found = apply_changes(&registry, &mut morph, &mut bank, &cols, &code, &[10, 11])
            .expect("zápis");
        let Applied::Done(done) = found else {
            panic!("výchozí tvary jsou v aréně");
        };
        // Vyrovnání: citační tvar [1, 2] + koncovka [2] s hranicí 2 a koncovkou 4.
        let first = done[0].expect("vyrovnání něco mění");
        assert_eq!(bank.form_of(first.form as usize), &[1, 2, 2]);
        assert_eq!((first.unit, first.boundary, first.exponent), (1, 2, 4));
        // Rozšíření tvaru 3 na koncovku 4 (dominantní podoba [2]): kmen [1, 2] + [2].
        let second = done[1].expect("rozšíření něco mění");
        assert_eq!(bank.form_of(second.form as usize), &[1, 2, 2]);
        assert_eq!((second.unit, second.boundary, second.exponent), (3, 2, 4));
        // Nové tvary vznikly tady a čekají na převzetí Pythonem.
        let (first_created, _, lengths) = bank.take_created();
        assert_eq!(first_created, 1);
        assert_eq!(lengths, vec![3]);
    }

    #[test]
    fn dalsi_analogie_pocita_se_stavem_po_predchozim_zapisu() {
        // Koncovka 4 (podoba [5]) patří tvaru 1, koncovka 5 (podoba [7]) tvaru 2.
        let mut t = table();
        t.exponent = vec![-1, 4, 5, 5, -1, -1];
        let cols = columns(&t);
        let (mut bank, mut morph) = start(&[1, 2, 7]);
        let mut registry = FormRegistry::default();
        registry.register(10, change(EXTEND, 2, 4));
        registry.register(11, change(EXTEND, 1, 5));
        let flags = [0_u8, 1, 1, 0, 0, 0];
        let none = [-1_i32; 6];
        let code = Code {
            token: 7,
            flags: &flags,
            store: Store {
                form: &none,
                boundary: &none,
                exponent: &none,
            },
        };
        let found = apply_changes(&registry, &mut morph, &mut bank, &cols, &code, &[10, 11])
            .expect("zápis");
        let Applied::Done(done) = found else {
            panic!("výchozí tvary jsou v aréně");
        };
        // Tvar 2 přejde na koncovku 4. Tím koncovku 5 nenese žádný tvar, takže ji tvar 1 už přijmout
        // nemůže (bez zápisu v kopii úložiště by dostal podobu [7]).
        let first = done[0].expect("tvar 2 přejde na koncovku 4");
        assert_eq!(bank.form_of(first.form as usize), &[1, 2, 5]);
        assert_eq!((first.unit, first.boundary, first.exponent), (2, 2, 4));
        assert_eq!(done[1], None);
        // Skutečný stav kódu se nezměnil: znovu od začátku dá totéž (index se vrátil na skutečný stav).
        let again =
            apply_changes(&registry, &mut morph, &mut bank, &cols, &code, &[11]).expect("zápis");
        let Applied::Done(items) = again else {
            panic!("výchozí tvary jsou v aréně");
        };
        let second = items[0].expect("bez zápisu tvaru 2 koncovku 5 nese tvar 2");
        assert_eq!(bank.form_of(second.form as usize), &[1, 2, 7]);
    }

    #[test]
    fn chybejici_vychozi_tvar_se_vyzada_a_nic_se_nezmeni() {
        let t = table();
        let cols = columns(&t);
        let mut bank = Bank::new(10, vec![false; 11]).expect("banka");
        bank.push(&[3, 2]).expect("tvar 0");
        let mut morph = MorphIndex::new();
        morph.names.extend(&["a", "b", "c", "d", "x", "y"]);
        let registry = FormRegistry::default();
        let flags = [0_u8, 1, 0, 0, 0, 0];
        let none = [-1_i32; 6];
        let code = Code {
            token: 1,
            flags: &flags,
            store: Store {
                form: &none,
                boundary: &none,
                exponent: &none,
            },
        };
        let found =
            apply_changes(&registry, &mut morph, &mut bank, &cols, &code, &[]).expect("zápis");
        assert_eq!(found, Applied::Needs(vec![0, 1]));
    }
}
