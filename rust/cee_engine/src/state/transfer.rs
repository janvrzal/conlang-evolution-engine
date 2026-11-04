//! Stav přenosu a tlaků (R1a).
//!
//! Sem patří vše, co přenos a tlaky drží mezi kroky. Do kontrolního bodu se ukládá jen
//! počítadlo kroků; zbytek ([`Derived`]) je odvozený ze stavu světa a po obnově nebo kopii se
//! staví znovu (sloupce variant se dorovnají z tabulky variant, mapa proměnná → varianta
//! „změna“ se doplní při prvním použití). Co se ukládá, aby výsledek nezávisel na kopii
//! (uložená hodnocení procesů), přibude do [`TransferState`] s hodnocením zvukových procesů.

use serde::{Deserialize, Serialize};

use crate::ids::VariantId;
use crate::model::repertoire::{Payload, Variants};
use crate::rng::{stable_int, Part};

/// Váha původu slova v tlaku `Motivation` (`pressures.lexical._MOTIVATION`); neznámý původ 0.
pub fn motivation_of(origin: &str) -> f64 {
    match origin {
        "derivation" | "compound" => 0.15,
        "circumlocution" => 0.1,
        "shift" | "conversion" => 0.05,
        "contamination" => -0.05,
        "coinage" => -0.15,
        _ => 0.0,
    }
}

/// Sloupce variant podle čísla varianty (jen přibývají); čtou je tlaky na slova.
#[derive(Clone, Debug, Default)]
pub struct VariantColumns {
    /// Číslo morfému varianty slova, −1 = varianta slovo nenese.
    pub morpheme: Vec<i32>,
    /// Váha původu slova (`Motivation`); 0 u variant, které slovo nenesou.
    pub motivation: Vec<f64>,
    /// Přitažlivost slova (`NaN` = varianta ji nemá).
    pub appeal: Vec<f64>,
    /// Klíč ocenění varianty (`stable_int("actuation", jméno)`).
    pub key: Vec<u64>,
}

impl VariantColumns {
    /// Dorovná sloupce o nové varianty tabulky `variants` (jména z `names`).
    pub fn sync(&mut self, variants: &Variants, names: &crate::ids::Numbering) {
        for at in self.morpheme.len()..variants.len() {
            let (morpheme, motivation, appeal) = match &variants.payload[at] {
                Payload::Lexical {
                    morpheme,
                    origin,
                    appeal,
                    ..
                } => (
                    if morpheme.is_none() {
                        -1
                    } else {
                        morpheme.0 as i32
                    },
                    motivation_of(origin),
                    *appeal,
                ),
                _ => (-1, 0.0, f64::NAN),
            };
            self.morpheme.push(morpheme);
            self.motivation.push(motivation);
            self.appeal.push(appeal);
            self.key.push(stable_int(&[
                Part::Str("actuation"),
                Part::Str(names.name(at as u32)),
            ]));
        }
    }

    pub fn is_word(&self, variant: VariantId) -> bool {
        self.morpheme.get(variant.index()).is_some_and(|&m| m >= 0)
    }
}

/// Odvozený stav přenosu (viz popis modulu).
#[derive(Clone, Debug, Default)]
pub struct Derived {
    pub variants: VariantColumns,
    /// Proměnná → číslo varianty „změna“ procesu či analogie (`u32::MAX` = neznámé / žádná).
    pub changed: Vec<u32>,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct TransferState {
    /// Počet kroků přenosu, které svět provedl (jen pro ladění a statistiky).
    pub steps: u64,
    /// Odvozený stav; neukládá se.
    #[serde(skip)]
    pub derived: Derived,
}
