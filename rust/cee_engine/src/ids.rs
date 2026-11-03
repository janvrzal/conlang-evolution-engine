//! Číselné identifikátory entit světa a jejich jména (registr).
//!
//! Zrcadlo `cee.v2.registry`: každý druh entity má vlastní číslování přidělované
//! v pořadí vzniku, které se po celý běh nemění. V horkých cestách se pracuje jen
//! s čísly (`GroupId(u32)` atd., pole podle čísla), textová jména jsou pro export,
//! stabilní klíče náhody a ladění.
//!
//! **Čísla nikdy neurčují pořadí.** Kde Python řadí podle řetězcových ID, řadí
//! se i tady podle jmen; pole jen uchovává hodnoty pod číslem. Pořadí jmen dá
//! [`Numbering::ranks`].

use std::collections::HashMap;

use serde::{Deserialize, Serialize};

macro_rules! id_type {
    ($(#[$meta:meta])* $name:ident) => {
        $(#[$meta])*
        #[derive(Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Debug, Serialize, Deserialize)]
        #[serde(transparent)]
        pub struct $name(pub u32);

        impl $name {
            /// Hodnota „žádná entita“ (v polích podle čísla).
            pub const NONE: $name = $name(u32::MAX);

            pub fn new(index: usize) -> Self {
                $name(index as u32)
            }

            pub fn index(self) -> usize {
                self.0 as usize
            }

            pub fn is_none(self) -> bool {
                self.0 == u32::MAX
            }

            pub fn option(self) -> Option<Self> {
                if self.is_none() { None } else { Some(self) }
            }
        }
    };
}

id_type!(
    /// Území (uzel stromu území).
    TerritoryId
);
id_type!(
    /// Skupina mluvčích.
    GroupId
);
id_type!(
    /// Morfém nebo tvar slova.
    MorphemeId
);
id_type!(
    /// Varianta proměnné.
    VariantId
);
id_type!(
    /// Proměnná (místo variace: slovo, proces, tvar, konstrukce, prozodie).
    VariableId
);
id_type!(
    /// Pojem (význam).
    ConceptId
);
id_type!(
    /// Zvukový proces (procesní proměnná).
    ProcessId
);
id_type!(
    /// Linie jazyka (protojazyk a jeho potomci).
    LanguageId
);
id_type!(
    /// Třída slova (`noun`, `verb`).
    WordClassId
);
id_type!(
    /// Buňka paradigmatu (`SG`, `PL`, …).
    CellId
);
id_type!(
    /// Kód (jazyková varieta) – jméno kódu v rámci skupiny (`main`, `written:…`).
    CodeId
);

/// Tvar v bance tvarů (`cee_core::bank::Bank`).
pub type FormId = u32;
/// Tvar slova jako posloupnost čísel hlásek (typ je shodný s `cee_core`).
pub type Form = Vec<i32>;

/// Přidávací číslování jednoho druhu entity: jméno ↔ číslo od nuly.
#[derive(Clone, Default, Debug, Serialize, Deserialize)]
#[serde(from = "Vec<String>", into = "Vec<String>")]
pub struct Numbering {
    names: Vec<String>,
    numbers: HashMap<String, u32>,
}

impl From<Vec<String>> for Numbering {
    fn from(names: Vec<String>) -> Self {
        let numbers = names
            .iter()
            .enumerate()
            .map(|(i, n)| (n.clone(), i as u32))
            .collect();
        Numbering { names, numbers }
    }
}

impl From<Numbering> for Vec<String> {
    fn from(value: Numbering) -> Self {
        value.names
    }
}

impl Numbering {
    pub fn len(&self) -> usize {
        self.names.len()
    }

    pub fn is_empty(&self) -> bool {
        self.names.is_empty()
    }

    /// Číslo jména; neznámé jméno dostane další číslo.
    pub fn intern(&mut self, name: &str) -> u32 {
        if let Some(&found) = self.numbers.get(name) {
            return found;
        }
        let number = self.names.len() as u32;
        self.names.push(name.to_owned());
        self.numbers.insert(name.to_owned(), number);
        number
    }

    /// Číslo jména, nebo `None`, když ho registr nezná.
    pub fn get(&self, name: &str) -> Option<u32> {
        self.numbers.get(name).copied()
    }

    pub fn contains(&self, name: &str) -> bool {
        self.numbers.contains_key(name)
    }

    pub fn name(&self, number: u32) -> &str {
        &self.names[number as usize]
    }

    pub fn names(&self) -> &[String] {
        &self.names
    }

    /// Pozice každého čísla v seřazení jmen (`ranks()[n]` = pořadí `name(n)`).
    pub fn ranks(&self) -> Vec<u32> {
        let mut order: Vec<u32> = (0..self.names.len() as u32).collect();
        order.sort_by(|&a, &b| self.names[a as usize].cmp(&self.names[b as usize]));
        let mut ranks = vec![0_u32; order.len()];
        for (rank, &number) in order.iter().enumerate() {
            ranks[number as usize] = rank as u32;
        }
        ranks
    }

    /// Čísla seřazená podle jmen (kanonické pořadí průchodu).
    pub fn sorted(&self) -> Vec<u32> {
        let mut order: Vec<u32> = (0..self.names.len() as u32).collect();
        order.sort_by(|&a, &b| self.names[a as usize].cmp(&self.names[b as usize]));
        order
    }
}

/// Číslování všech druhů entit jednoho světa.
#[derive(Clone, Default, Debug, Serialize, Deserialize)]
pub struct Registry {
    pub morphemes: Numbering,
    pub variants: Numbering,
    pub variables: Numbering,
    pub concepts: Numbering,
    pub groups: Numbering,
    pub processes: Numbering,
    pub territories: Numbering,
    pub languages: Numbering,
    pub word_classes: Numbering,
    pub cells: Numbering,
}

macro_rules! typed {
    ($($method:ident, $field:ident, $id:ident;)*) => {
        impl Registry {
            $(
                pub fn $method(&mut self, name: &str) -> $id {
                    $id(self.$field.intern(name))
                }
            )*
        }
    };
}

typed! {
    morpheme, morphemes, MorphemeId;
    variant, variants, VariantId;
    variable, variables, VariableId;
    concept, concepts, ConceptId;
    group, groups, GroupId;
    process, processes, ProcessId;
    territory, territories, TerritoryId;
    language, languages, LanguageId;
    word_class, word_classes, WordClassId;
    cell, cells, CellId;
}
