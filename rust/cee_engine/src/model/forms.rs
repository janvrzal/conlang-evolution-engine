//! Banka tvarů a podkladové tvary kódu.
//!
//! [`FormBank`] obaluje `cee_core::bank::Bank` (tvary jako posloupnosti hlásek se
//! stabilními čísly a tabulky procesů); jen přibývá, takže ji smí sdílet všechny
//! kódy světa. [`FormStore`] je zrcadlo `cee.v2.language.lexicon.FormStore`:
//! tři pole podle čísla morfému (číslo tvaru v bance, hranice koncovky, koncovka),
//! −1 = morfém nemá vlastní tvar a platí výchozí z tabulky morfémů.

use std::sync::Arc;

use cee_core::bank::Bank;
use serde::{Deserialize, Serialize};

use crate::ids::{Form, FormId, MorphemeId};
use crate::segments::SegmentTable;

/// V polích úložiště tvarů: morfém nemá vlastní tvar.
pub const UNSET: i32 = -1;

#[derive(Serialize, Deserialize)]
struct FormBankRepr {
    forms: Vec<Form>,
}

/// Banka různých tvarů světa (obal `cee_core::bank::Bank`).
///
/// Procesní tabulky a příznakovost uvnitř banky jsou odvozená keš a do kontrolního bodu
/// se neukládají: kontrolní bod nese jen tvary v pořadí čísel, procesy se zaregistrují
/// znovu (`cee_core::bank::Bank::register_proc`, fáze fonologie).
#[derive(Serialize, Deserialize)]
#[serde(from = "FormBankRepr", into = "FormBankRepr")]
pub struct FormBank {
    pub bank: Bank,
    table: Arc<SegmentTable>,
}

impl From<FormBankRepr> for FormBank {
    fn from(repr: FormBankRepr) -> Self {
        let mut bank = FormBank::new(SegmentTable::default_table());
        for form in &repr.forms {
            bank.id_of(form);
        }
        bank
    }
}

impl From<FormBank> for FormBankRepr {
    fn from(bank: FormBank) -> Self {
        FormBankRepr {
            forms: (0..bank.len())
                .map(|id| bank.form(id as FormId).to_vec())
                .collect(),
        }
    }
}

impl Clone for FormBank {
    fn clone(&self) -> Self {
        let mut copy = FormBank::new(self.table.clone());
        for id in 0..self.len() {
            copy.id_of(self.form(id as FormId));
        }
        copy
    }
}

impl std::fmt::Debug for FormBank {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "FormBank({} tvarů)", self.len())
    }
}

impl FormBank {
    pub fn new(table: Arc<SegmentTable>) -> FormBank {
        let mut bank = Bank::new(table.boundary(), table.vowel.clone()).expect("maska samohlásek");
        // Polosamohlásky (sonorita 3) patří k jádru slabiky v příznakovosti tvarů; hranice slova ne.
        let mut glide: Vec<bool> = (0..table.len())
            .map(|segment| table.sonority(segment as i32) == 3)
            .collect();
        glide.push(false);
        bank.set_glide(glide).expect("maska polosamohlásek");
        FormBank { bank, table }
    }

    pub fn table(&self) -> &Arc<SegmentTable> {
        &self.table
    }

    pub fn len(&self) -> usize {
        self.bank.len()
    }

    pub fn is_empty(&self) -> bool {
        self.bank.is_empty()
    }

    /// Číslo tvaru v bance; nový tvar dostane další číslo.
    pub fn id_of(&mut self, form: &[i32]) -> FormId {
        self.bank
            .intern_form(form)
            .expect("hlásky tvaru jsou v tabulce")
    }

    pub fn form(&self, id: FormId) -> &[i32] {
        self.bank.form_of(id as usize)
    }
}

/// Aktuální stav tvaru slova v jednom kódu.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct UnitForm {
    pub form: FormId,
    /// Kde začíná koncovka (−1 = bez koncovky).
    pub boundary: i32,
    pub exponent: MorphemeId,
}

/// Podkladové tvary kódu v polích podle čísla morfému.
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct FormStore {
    form: Vec<i32>,
    boundary: Vec<i32>,
    exponent: Vec<i32>,
    /// Identita úložiště pro zneplatnění indexů (roste při každém zápisu).
    pub version: u64,
    /// Deník přepsaných morfémů v pořadí zápisů.
    pub log: Vec<MorphemeId>,
}

impl FormStore {
    pub fn new() -> FormStore {
        FormStore::default()
    }

    pub fn get(&self, morpheme: MorphemeId) -> Option<UnitForm> {
        let at = morpheme.index();
        let form = *self.form.get(at)?;
        if form == UNSET {
            return None;
        }
        let exponent = self.exponent[at];
        Some(UnitForm {
            form: form as FormId,
            boundary: self.boundary[at],
            exponent: if exponent == UNSET {
                MorphemeId::NONE
            } else {
                MorphemeId(exponent as u32)
            },
        })
    }

    /// Číslo tvaru v bance, nebo −1 (výchozí tvar).
    pub fn form_id(&self, morpheme: MorphemeId) -> i32 {
        self.form.get(morpheme.index()).copied().unwrap_or(UNSET)
    }

    pub fn set(&mut self, morpheme: MorphemeId, unit: UnitForm) {
        let at = morpheme.index();
        if self.form.len() <= at {
            self.form.resize(at + 1, UNSET);
            self.boundary.resize(at + 1, UNSET);
            self.exponent.resize(at + 1, UNSET);
        }
        self.form[at] = unit.form as i32;
        self.boundary[at] = unit.boundary;
        self.exponent[at] = if unit.exponent.is_none() {
            UNSET
        } else {
            unit.exponent.0 as i32
        };
        self.version += 1;
        self.log.push(morpheme);
    }

    /// Živá pole (tvar, hranice koncovky, koncovka) podle čísla morfému; jen ke čtení.
    pub fn raw(&self) -> (&[i32], &[i32], &[i32]) {
        (&self.form, &self.boundary, &self.exponent)
    }

    /// Počet morfémů s vlastním tvarem.
    pub fn overridden(&self) -> usize {
        self.form.iter().filter(|&&f| f != UNSET).count()
    }
}
