//! Stav přenosu a tlaků (R1a).
//!
//! Sem patří vše, co přenos a tlaky drží mezi kroky: uložená hodnocení zvukových procesů
//! (`cee_core::assess_index::AssessIndex`, platná podle verze kódu a nejvýš `STALE_TICKS`
//! ticků), morfologický index kódů pro hodnocení tvarů a slabost buněk
//! (`cee_core::morphology_index::MorphIndex`), vzorky slov, registrace procesů a analogických
//! změn a sloupce odvozené ze světa (morfémy, varianty). Do kontrolního bodu se ukládají
//! **jen uložená hodnocení procesů** (na nich závisí výsledek, protože platí několik ticků
//! i po změně kódu); zbytek je čistá funkce stavu světa a po obnově se postaví znovu.

use std::collections::{BTreeSet, HashMap};

use cee_core::assess_index::AssessIndex;
use cee_core::morphology_index::MorphIndex;
use serde::{Deserialize, Deserializer, Serialize, Serializer};

use crate::ids::VariantId;

/// Uložená hodnocení procesů podle kódu: (token, [(proměnná, verze kódu, tik, pět hodnot)]).
pub type StoredAssessments = Vec<(i64, Vec<(u32, i64, i64, [f64; 5])>)>;

/// Co o řádku proměnné drží přenos: zaregistrovaný proces, nebo analogická změna tvaru.
#[derive(Clone, Copy, Debug)]
pub enum TrackedKind {
    /// Zvukový proces: řádek v bance tvarů, snadnost a jasnost procesu, příznaky řádku.
    Process {
        row: usize,
        ease: f64,
        clarity: f64,
        flags: u8,
    },
    /// Analogická změna tvaru slova: příznaky řádku.
    Form { flags: u8 },
}

/// Sledovaná proměnná (proces nebo změna tvaru) a její varianta „změna“.
#[derive(Clone, Copy, Debug)]
pub struct Tracked {
    pub changed: VariantId,
    pub kind: TrackedKind,
}

/// Sloupce tabulky morfémů podle čísla morfému (jen čtení indexu tvarů a hodnocení).
#[derive(Default)]
pub struct MorphColumns {
    /// Klíč platnosti: (počet jmen v registru, počet uložených morfémů).
    pub key: (usize, usize),
    /// Druh morfému: 0 kořen, 1 přípona, 2 tvar slova.
    pub kind: Vec<i8>,
    pub class: Vec<i32>,
    pub cell: Vec<i32>,
    /// Lexém tvaru slova (`Morpheme.lexeme_id`: u kořene on sám).
    pub lexeme: Vec<i32>,
    pub exponent: Vec<i32>,
    pub boundary: Vec<i32>,
    /// Číslo výchozího tvaru v bance (−1 = morfém nemá tvar).
    pub default_form: Vec<i32>,
    pub frequency: Vec<f64>,
}

/// Sloupce variant podle čísla varianty (jen přibývají).
#[derive(Default)]
pub struct VariantColumns {
    /// 0 = varianta vznikla změnou (inovace), −1 = zděděná.
    pub change: Vec<i32>,
    /// Číslo morfému varianty slova, −1 = varianta slovo nenese.
    pub morpheme: Vec<i32>,
    /// Číslo původu slova v tabulce původů, −1 = neznámý.
    pub origin: Vec<i32>,
    /// Přitažlivost slova (`NaN` = varianta ji nemá).
    pub appeal: Vec<f64>,
    /// Klíč ocenění varianty (`stable_int("actuation", jméno)`).
    pub keys: Vec<u64>,
}

/// Odvozený stav přenosu (viz popis modulu).
#[derive(Default)]
pub struct Derived {
    pub assess: AssessIndex,
    pub morph: MorphIndex,
    /// Kódy (podle skupiny), pro které existují uložená hodnocení.
    pub tokens: BTreeSet<i64>,
    /// Sledované proměnné podle čísla proměnné.
    pub tracked: Vec<Option<Tracked>>,
    /// Souřadnice samohlásek a polosamohlásky jsou v bance a indexu hodnocení.
    pub ready: bool,
    /// Kolik jmen morfémů už zná index tvarů.
    pub morph_names: usize,
    /// Naposledy dorovnaný stav kódu v indexu tvarů: token → (verze, verze úložiště, počet morfémů).
    pub synced: HashMap<i64, (u64, u64, usize)>,
    pub columns: MorphColumns,
    pub variants: VariantColumns,
    /// Seřazené klíče příbuzných dvojic pojmů (lexikální jasnost).
    pub related: Option<Vec<i64>>,
}

impl Derived {
    /// Uložená hodnocení všech kódů (pro kontrolní bod a kopii).
    pub fn export(&self) -> StoredAssessments {
        self.tokens
            .iter()
            .map(|&token| (token, self.assess.export(token)))
            .collect()
    }

    /// Obnoví uložená hodnocení do čistého stavu.
    pub fn from_stored(stored: StoredAssessments) -> Derived {
        let mut derived = Derived::default();
        for (token, entries) in stored {
            derived.assess.import(token, entries);
            derived.tokens.insert(token);
        }
        derived
    }
}

impl Clone for Derived {
    fn clone(&self) -> Self {
        Derived::from_stored(self.export())
    }
}

impl std::fmt::Debug for Derived {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "Derived({} kódů s hodnocením)", self.tokens.len())
    }
}

impl Serialize for Derived {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        self.export().serialize(serializer)
    }
}

impl<'de> Deserialize<'de> for Derived {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        Ok(Derived::from_stored(StoredAssessments::deserialize(
            deserializer,
        )?))
    }
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct TransferState {
    /// Počet kroků přenosu, které svět provedl (jen pro ladění a statistiky).
    pub steps: u64,
    /// Odvozený stav a uložená hodnocení procesů.
    pub derived: Derived,
}
