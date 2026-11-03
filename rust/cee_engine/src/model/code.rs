//! Kód (jazyková varieta skupiny): repertoár, podkladové tvary a stav slovní zásoby.
//!
//! Zrcadlo `world.Code` a `lexicon.PhonologyState`. Slovní zásoba, počty užití,
//! dominantní kořeny a deníky změn jsou v polích podle čísel; fronty fonologizace
//! a morfologické změny mají vlastní struktury v `state::sound` a `state::grammar`
//! (každou plní jiný agent R1).

use serde::{Deserialize, Serialize};

use crate::ids::{ConceptId, GroupId, LanguageId, MorphemeId, VariableId, VariantId};
use crate::model::forms::FormStore;
use crate::model::repertoire::Repertoire;
use crate::state::grammar::GrammarCodeState;
use crate::state::sound::SoundCodeState;

/// Pravidlo přízvuku (`StressRule`).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum StressRule {
    Initial,
    Second,
    Antepenult,
    Penult,
    Final,
}

impl StressRule {
    pub fn parse(name: &str) -> Option<StressRule> {
        Some(match name {
            "initial" => StressRule::Initial,
            "second" => StressRule::Second,
            "antepenult" => StressRule::Antepenult,
            "penult" => StressRule::Penult,
            "final" => StressRule::Final,
            _ => return None,
        })
    }

    pub fn name(self) -> &'static str {
        match self {
            StressRule::Initial => "initial",
            StressRule::Second => "second",
            StressRule::Antepenult => "antepenult",
            StressRule::Penult => "penult",
            StressRule::Final => "final",
        }
    }

    /// Číslo pravidla, jak ho zná `cee_core::process` (`RULE_*`).
    pub fn as_rule(self) -> u8 {
        match self {
            StressRule::Initial => cee_core::process::RULE_INITIAL,
            StressRule::Second => cee_core::process::RULE_SECOND,
            StressRule::Antepenult => cee_core::process::RULE_ANTEPENULT,
            StressRule::Penult => cee_core::process::RULE_PENULT,
            StressRule::Final => cee_core::process::RULE_FINAL,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum StressStrength {
    Weak,
    Strong,
}

impl StressStrength {
    pub fn parse(name: &str) -> Option<StressStrength> {
        match name {
            "weak" => Some(StressStrength::Weak),
            "strong" => Some(StressStrength::Strong),
            _ => None,
        }
    }

    pub fn name(self) -> &'static str {
        match self {
            StressStrength::Weak => "weak",
            StressStrength::Strong => "strong",
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum Acquisition {
    L1,
    L2,
}

/// Množina morfémů jako příznaky podle čísla (rychlé „je v zásobě?“).
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct MorphemeSet {
    present: Vec<bool>,
    count: usize,
}

impl MorphemeSet {
    pub fn contains(&self, id: MorphemeId) -> bool {
        self.present.get(id.index()).copied().unwrap_or(false)
    }

    pub fn insert(&mut self, id: MorphemeId) -> bool {
        if self.present.len() <= id.index() {
            self.present.resize(id.index() + 1, false);
        }
        let added = !self.present[id.index()];
        self.present[id.index()] = true;
        self.count += usize::from(added);
        added
    }

    pub fn remove(&mut self, id: MorphemeId) -> bool {
        let removed = self.contains(id);
        if removed {
            self.present[id.index()] = false;
            self.count -= 1;
        }
        removed
    }

    pub fn len(&self) -> usize {
        self.count
    }

    pub fn is_empty(&self) -> bool {
        self.count == 0
    }

    /// Prvky vzestupně podle čísla (pro pořadí jmen je seřadí volající).
    pub fn iter(&self) -> impl Iterator<Item = MorphemeId> + '_ {
        self.present
            .iter()
            .enumerate()
            .filter(|(_, &p)| p)
            .map(|(i, _)| MorphemeId::new(i))
    }
}

/// Co kód udělal se slovní zásobou a zvukovými procesy.
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct PhonologyState {
    /// Morfémy, které kód právě užívá jako dominantní slova pro své pojmy (a jejich tvary).
    pub vocabulary: MorphemeSet,
    /// Pojem → jeho dominantní kořen (`NONE` = žádný), pole podle čísla pojmu.
    pub dominant: Vec<MorphemeId>,
    /// Morfém → pro kolik pojmů je dominantní kořenem, pole podle čísla morfému.
    pub uses: Vec<u32>,
    /// Append-only vstupy pro inkrementální konzumenty (jen stabilní čísla).
    pub dominant_log: Vec<(ConceptId, MorphemeId, MorphemeId)>,
    pub usage_log: Vec<(MorphemeId, u32, u32)>,
    pub vocabulary_log: Vec<(bool, MorphemeId)>,
    pub grammar_log: Vec<VariableId>,
    pub grammar_applied_log: Vec<VariantId>,
    /// Roste s každou změnou slovní zásoby nebo podkladových tvarů.
    pub version: u64,
    /// Roste jen se změnou, které slovo je pro který pojem dominantní.
    pub lexicon_version: u64,
    /// Stav zvukových změn (R1b) a gramatiky (R1c).
    pub sound: SoundCodeState,
    pub grammar: GrammarCodeState,
}

impl PhonologyState {
    pub fn dominant_of(&self, concept: ConceptId) -> MorphemeId {
        self.dominant
            .get(concept.index())
            .copied()
            .unwrap_or(MorphemeId::NONE)
    }

    /// Změní dominantní kořen a zaznamená i přechodný stav bez kořene; `false`, když se nic nemění.
    pub fn set_dominant(&mut self, concept: ConceptId, root: MorphemeId) -> bool {
        if self.dominant.len() <= concept.index() {
            self.dominant.resize(concept.index() + 1, MorphemeId::NONE);
        }
        let old = self.dominant[concept.index()];
        if old == root {
            return false;
        }
        self.dominant[concept.index()] = root;
        self.dominant_log.push((concept, old, root));
        true
    }

    pub fn uses_of(&self, root: MorphemeId) -> u32 {
        self.uses.get(root.index()).copied().unwrap_or(0)
    }

    /// Upraví počet pojmů kořene a zaznamená změnu pro frekvenční indexy; vrací nový počet.
    pub fn adjust_uses(&mut self, root: MorphemeId, delta: i64, missing: u32) -> u32 {
        if self.uses.len() <= root.index() {
            self.uses.resize(root.index() + 1, 0);
        }
        let held = self.uses[root.index()];
        let old = if held == 0 { missing } else { held };
        let new = (i64::from(old) + delta).max(0) as u32;
        self.uses[root.index()] = new;
        if new != old {
            self.usage_log.push((root, old, new));
        }
        new
    }

    pub fn enter_vocabulary(&mut self, unit: MorphemeId) -> bool {
        let added = self.vocabulary.insert(unit);
        if added {
            self.vocabulary_log.push((true, unit));
        }
        added
    }

    pub fn leave_vocabulary(&mut self, unit: MorphemeId) -> bool {
        let removed = self.vocabulary.remove(unit);
        if removed {
            self.vocabulary_log.push((false, unit));
        }
        removed
    }

    pub fn record_grammar(&mut self, variable: VariableId) {
        self.grammar_log.push(variable);
    }

    pub fn mark_grammar_applied(&mut self, variant: VariantId) -> bool {
        let added = self.grammar.grammar_applied.insert(variant);
        if added {
            self.grammar_applied_log.push(variant);
        }
        added
    }
}

/// Jedna jazyková varieta, kterou skupina užívá.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Code {
    /// Jméno kódu v rámci skupiny (`main`, …); vstupuje do klíčů náhody.
    pub id: String,
    pub repertoire: Repertoire,
    pub usage_share: f64,
    pub acquisition: Acquisition,
    pub l1_source: GroupId,
    /// Podkladové tvary morfémů, které se od výchozích liší.
    pub forms: FormStore,
    pub phonology: PhonologyState,
    pub stress_rule: StressRule,
    /// Linie jazyka; kontakt mezi liniemi prochází filtrem přenositelnosti.
    pub language: LanguageId,
    /// Podíl mluvčích, kteří se kód naučili až v dospělosti (0 až 1).
    pub l2_share: f64,
    pub stress_strength: StressStrength,
}

impl Code {
    pub fn new(id: &str, repertoire: Repertoire, language: LanguageId) -> Code {
        Code {
            id: id.to_owned(),
            repertoire,
            usage_share: 1.0,
            acquisition: Acquisition::L1,
            l1_source: GroupId::NONE,
            forms: FormStore::new(),
            phonology: PhonologyState::default(),
            stress_rule: StressRule::Penult,
            language,
            l2_share: 0.0,
            stress_strength: StressStrength::Weak,
        }
    }

    /// Nezávislá kopie kódu (zjemnění, odštěpení); repertoár sdílí zmrazený základ.
    pub fn branch(&mut self) -> Code {
        Code {
            id: self.id.clone(),
            repertoire: self.repertoire.branch(),
            usage_share: self.usage_share,
            acquisition: self.acquisition,
            l1_source: self.l1_source,
            forms: self.forms.clone(),
            phonology: self.phonology.clone(),
            stress_rule: self.stress_rule,
            language: self.language,
            l2_share: self.l2_share,
            stress_strength: self.stress_strength,
        }
    }
}
