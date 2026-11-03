//! Morfémy, paradigmata, analogické změny tvarů a zvukové procesy.
//!
//! Zrcadlo `cee.v2.language.lexicon` (část `Morpheme`), `morphology` a `processes`.
//! Od M3 je jednotkou slovní zásoby *tvar slova*: kořen v citačním tvaru, nebo
//! jedna buňka paradigmatu (kmen + koncovka). Morfémy jsou sloupce podle čísla
//! ([`Morphemes`]); výchozí podoba tvaru (jaká byla při vzniku) je v sloupcích
//! `form`/`boundary`/`exponent`, aktuální podobu v kódu drží `FormStore` kódu.

use serde::{Deserialize, Serialize};

use crate::ids::{
    CellId, FormId, GroupId, LanguageId, MorphemeId, Numbering, Registry, WordClassId,
};
use crate::segments::Pattern;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum MorphemeKind {
    Root,
    Affix,
    Word,
}

/// Údaje o původu kořene vzniklého za běhu (chladné pole).
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct MorphemeMeta {
    pub etymology: Option<String>,
    pub sources: Vec<String>,
    pub base: Option<MorphemeId>,
    /// Anglický význam; u koncovky `třída.buňka`.
    pub meaning: String,
}

/// Vstup pro vložení morfému do tabulky.
#[derive(Clone, Debug)]
pub struct MorphemeInit {
    pub meaning: String,
    /// Číslo výchozího tvaru v bance tvarů.
    pub form: FormId,
    pub frequency: f64,
    pub kind: MorphemeKind,
    pub origin_group: GroupId,
    pub origin_tick: u32,
    pub word_class: WordClassId,
    pub lexeme: MorphemeId,
    pub cell: CellId,
    pub exponent: MorphemeId,
    /// Kde začíná koncovka (−1 = bez koncovky).
    pub boundary: i32,
    pub language: LanguageId,
    pub meta: MorphemeMeta,
}

/// Sloupce morfémů podle čísla morfému z registru.
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct Morphemes {
    /// Je číslo obsazené? (číslo přiděluje registr; morfém se do tabulky ukládá později)
    pub present: Vec<bool>,
    pub kind: Vec<MorphemeKind>,
    pub form: Vec<FormId>,
    pub boundary: Vec<i32>,
    pub exponent: Vec<MorphemeId>,
    /// Lexém tvaru slova; `NONE` u kořene (kořen je lexémem sám).
    pub lexeme: Vec<MorphemeId>,
    pub cell: Vec<CellId>,
    pub word_class: Vec<WordClassId>,
    /// Tokenová frekvence užití (0 až 1).
    pub frequency: Vec<f64>,
    pub language: Vec<LanguageId>,
    pub origin_group: Vec<GroupId>,
    pub origin_tick: Vec<u32>,
    pub meta: Vec<MorphemeMeta>,
}

impl Morphemes {
    pub fn len(&self) -> usize {
        self.present.len()
    }

    pub fn is_empty(&self) -> bool {
        self.present.is_empty()
    }

    pub fn contains(&self, id: MorphemeId) -> bool {
        self.present.get(id.index()).copied().unwrap_or(false)
    }

    pub fn store(&mut self, id: MorphemeId, init: MorphemeInit) {
        let at = id.index();
        while self.present.len() <= at {
            self.present.push(false);
            self.kind.push(MorphemeKind::Root);
            self.form.push(u32::MAX);
            self.boundary.push(-1);
            self.exponent.push(MorphemeId::NONE);
            self.lexeme.push(MorphemeId::NONE);
            self.cell.push(CellId::NONE);
            self.word_class.push(WordClassId::NONE);
            self.frequency.push(0.5);
            self.language.push(LanguageId::NONE);
            self.origin_group.push(GroupId::NONE);
            self.origin_tick.push(0);
            self.meta.push(MorphemeMeta::default());
        }
        self.present[at] = true;
        self.kind[at] = init.kind;
        self.form[at] = init.form;
        self.boundary[at] = init.boundary;
        self.exponent[at] = init.exponent;
        self.lexeme[at] = init.lexeme;
        self.cell[at] = init.cell;
        self.word_class[at] = init.word_class;
        self.frequency[at] = init.frequency;
        self.language[at] = init.language;
        self.origin_group[at] = init.origin_group;
        self.origin_tick[at] = init.origin_tick;
        let mut meta = init.meta;
        meta.meaning = init.meaning;
        self.meta[at] = meta;
    }

    /// Lexém, ke kterému tvar patří; citační tvar je lexémem sám.
    pub fn lexeme_id(&self, id: MorphemeId) -> MorphemeId {
        let lexeme = self.lexeme[id.index()];
        if lexeme.is_none() { id } else { lexeme }
    }
}

/// Buňky jedné třídy slov; první buňka je citační tvar bez koncovky.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Paradigm {
    pub word_class: WordClassId,
    pub cells: Vec<CellId>,
    /// Váha buňky v užívání: frekvence tvaru = frekvence lexému × váha.
    pub weights: Vec<f64>,
}

impl Paradigm {
    pub fn citation(&self) -> CellId {
        self.cells[0]
    }

    pub fn weight(&self, cell: CellId) -> Option<f64> {
        self.cells.iter().position(|&c| c == cell).map(|i| self.weights[i])
    }
}

/// ID tvaru slova: citační tvar sdílí ID s lexémem, ostatní `lexém#buňka`.
pub fn unit_name(lexeme: &str, cell: &str, citation: &str) -> String {
    if cell == citation { lexeme.to_owned() } else { format!("{lexeme}#{cell}") }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum FormOperation {
    Level,
    Extend,
    Prepend,
    DropInitial,
}

impl FormOperation {
    pub fn name(self) -> &'static str {
        match self {
            FormOperation::Level => "level",
            FormOperation::Extend => "extend",
            FormOperation::Prepend => "prepend",
            FormOperation::DropInitial => "drop_initial",
        }
    }

    /// Týká se změna všech tvarů lexému?
    pub fn lexeme_wide(self) -> bool {
        matches!(self, FormOperation::Prepend | FormOperation::DropInitial)
    }
}

/// Analogická změna jednoho tvaru slova (hodnota formové proměnné).
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct FormChange {
    pub operation: FormOperation,
    pub unit: MorphemeId,
    pub exponent: MorphemeId,
    pub segment: Option<i32>,
}

impl FormChange {
    /// Kanonický klíč `operace|tvar|koncovka[|hláska]`.
    pub fn key(&self, names: &Numbering) -> String {
        let exponent = if self.exponent.is_none() { "" } else { names.name(self.exponent.0) };
        let key = format!("{}|{}|{}", self.operation.name(), names.name(self.unit.0), exponent);
        match self.segment {
            None => key,
            Some(segment) => format!("{key}|{segment}"),
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum Operation {
    Change,
    Replace,
    Delete,
    InsertBefore,
    InsertAfter,
    MergeNext,
    Tone,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum Stress {
    Any,
    Stressed,
    Unstressed,
}

/// Zvukový proces: jedna konkrétní změna v jednom prostředí (hodnota procesní proměnné).
///
/// Sám nic neukládá; aplikaci na tvar a bankovní tabulky dělá `cee_core::process`
/// a `cee_core::bank` (fáze fonologie, R1b).
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ProcessDef {
    pub family: String,
    pub target: Pattern,
    pub operation: Operation,
    /// Požadované rysy výstupu u operace `Change`.
    pub changes: Vec<(String, String)>,
    pub segment: Option<i32>,
    pub left: Option<Pattern>,
    pub right: Option<Pattern>,
    pub right2: Option<Pattern>,
    pub stress: Stress,
    /// Jen uvnitř slova (synkopa).
    pub medial: bool,
    pub ease: f64,
    pub clarity: f64,
    pub reductive: bool,
    pub label: String,
    pub allow: Vec<char>,
    pub tone: Option<u32>,
}

impl Registry {
    /// Číslo třídy slova podle jména (`noun`, `verb`).
    pub fn word_class_of(&self, name: &str) -> Option<WordClassId> {
        self.word_classes.get(name).map(WordClassId)
    }
}
