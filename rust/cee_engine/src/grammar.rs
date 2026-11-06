//! Gramatické funkce a konstrukce: zrcadlo `cee.v2.language.constructions`.
//!
//! Funkce (minulý čas, plurál, určenost, zápor, slovosled…) je řádek katalogu
//! (`v2_grammar.json`, export z `v2_grammar.yaml`) a v jazyce konstrukční
//! proměnná. Varianty jsou konstrukce, které spolu soutěží. Profily gramatiky
//! protojazyků (`SYNTAX_GRAMMAR` atd.) jsou ve [`profile`].

use std::collections::BTreeMap;
use std::sync::OnceLock;

use serde::{Deserialize, Serialize};

use crate::parameters::Parameters;

/// Šablona funkce.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Template {
    Inflection,
    Negation,
    Order,
}

/// Řádek katalogu gramatických funkcí.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct GrammaticalFunction {
    #[serde(skip)]
    pub id: String,
    pub template: Template,
    pub domain: String,
    #[serde(default)]
    pub need: f64,
    #[serde(default)]
    pub context: f64,
    #[serde(default)]
    pub cell: Option<String>,
    #[serde(default = "default_weight")]
    pub weight: f64,
    #[serde(default)]
    pub sources: Vec<String>,
    #[serde(default)]
    pub compensates: Vec<String>,
    #[serde(default)]
    pub coverage: f64,
    #[serde(default)]
    pub orders: Vec<String>,
    #[serde(default)]
    pub donors: Vec<String>,
    /// Vázaný výraz funkce může vyblednout v ukazatel bez významu (člen, Greenberg 1978).
    #[serde(default)]
    pub bleaches: bool,
    /// Potřeba funkce roste se slabostí jiných funkcí: `need × (1 + Σ k × slabost)`. Člen je
    /// častější v jazycích bez pádů (WALS 37A × 49A: 0,65 proti 0,35 u 4 a víc pádů; dok. 22).
    #[serde(default)]
    pub reinforced_by: BTreeMap<String, f64>,
}

fn default_weight() -> f64 {
    0.5
}

impl GrammaticalFunction {
    /// Třída slova, ke které se funkce váže (`noun`, `verb`), nebo `None`.
    pub fn word_class(&self) -> Option<&str> {
        matches!(self.domain.as_str(), "noun" | "verb").then_some(self.domain.as_str())
    }
}

/// Katalog funkcí v pořadí souboru (pořadí řídí buňky paradigmat).
#[derive(Clone, Debug)]
pub struct Catalog {
    pub functions: Vec<GrammaticalFunction>,
}

#[derive(Deserialize)]
struct CatalogFile {
    functions: BTreeMap<String, GrammaticalFunction>,
    order: Vec<String>,
}

impl Catalog {
    pub fn from_json(text: &str) -> Result<Catalog, String> {
        // Export je řazen podle klíče, pořadí funkcí z YAML nese pole `order`.
        let file: CatalogFile =
            serde_json::from_str(text).map_err(|e| format!("v2_grammar.json: {e}"))?;
        let mut functions = Vec::with_capacity(file.order.len());
        let mut by_id = file.functions;
        for id in file.order {
            let mut entry = by_id
                .remove(&id)
                .ok_or_else(|| format!("funkce {id} chybí v katalogu"))?;
            entry.id = id;
            functions.push(entry);
        }
        Ok(Catalog { functions })
    }

    pub fn shared() -> &'static Catalog {
        static CATALOG: OnceLock<Catalog> = OnceLock::new();
        CATALOG.get_or_init(|| {
            Catalog::from_json(crate::data::GRAMMAR_JSON).expect("vložený katalog gramatiky")
        })
    }

    pub fn get(&self, id: &str) -> Option<&GrammaticalFunction> {
        self.functions.iter().find(|f| f.id == id)
    }

    /// Katalog s přepisy `need`, `context` a `coverage` z `Parameters::grammar`.
    pub fn with_overrides(&self, params: &Parameters) -> Result<Catalog, String> {
        let mut out = self.clone();
        for (function, fields) in &params.grammar {
            let entry = out
                .functions
                .iter_mut()
                .find(|f| &f.id == function)
                .ok_or_else(|| {
                    format!("Parametry přepisují neznámé gramatické funkce: [{function}].")
                })?;
            for (field, value) in fields {
                match field.as_str() {
                    "need" => entry.need = *value,
                    "context" => entry.context = *value,
                    "coverage" => entry.coverage = *value,
                    _ => {}
                }
            }
        }
        Ok(out)
    }
}

/// Pořadí funkcí profilu `syntax`/`substrate` (pořadí vložení do slovníku v Pythonu).
const PROFILE_ORDER: [&str; 5] = ["PAST", "PL", "OBJ", "NEG", "ORDER"];

/// Všechny gramatické funkce katalogu (statická jména pro profily a popis světa).
pub const FUNCTIONS: [&str; 8] = [
    "PAST", "FUTURE", "PL", "OBJ", "DEFINITE", "ASPECT", "NEG", "ORDER",
];
/// Pojmy navíc k základní slovní zásobě, aby cesty gramatikalizace existovaly.
pub const GRAMMATICAL_SOURCES: [&str; 6] = ["have", "finish", "go", "want", "thing", "step"];

/// Konstrukce jedné gramatické funkce (varianta konstrukční proměnné).
#[derive(Clone, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct Construction {
    pub function: String,
    pub kind: String,
    pub source: Option<String>,
    pub stage: Option<String>,
    pub order: Option<String>,
    pub exponent: Option<String>,
    pub reinforcer: Option<String>,
    pub donor: Option<String>,
}

impl Construction {
    pub fn new(function: &str, kind: &str) -> Construction {
        Construction {
            function: function.into(),
            kind: kind.into(),
            source: None,
            stage: None,
            order: None,
            exponent: None,
            reinforcer: None,
            donor: None,
        }
    }

    pub fn with_source(mut self, source: &str) -> Self {
        self.source = Some(source.into());
        self
    }

    pub fn with_order(mut self, order: &str) -> Self {
        self.order = Some(order.into());
        self
    }

    pub fn with_reinforcer(mut self, reinforcer: &str) -> Self {
        self.reinforcer = Some(reinforcer.into());
        self
    }

    /// Kanonický klíč (pro stabilní ID varianty).
    pub fn key(&self) -> String {
        let part = |value: &Option<String>| value.clone().unwrap_or_default();
        let key = [
            self.function.clone(),
            self.kind.clone(),
            part(&self.source),
            part(&self.stage),
            part(&self.order),
            part(&self.exponent),
            part(&self.reinforcer),
        ]
        .join("|");
        match &self.donor {
            None => key,
            Some(donor) => format!("{key}|{donor}"),
        }
    }

    /// Kolik samostatných slov konstrukce přidává.
    pub fn words(&self) -> u32 {
        match self.kind.as_str() {
            "periphrastic" => u32::from(self.stage.as_deref() == Some("free")),
            "embraced" => 2,
            "pre" | "post" => 1,
            _ => 0,
        }
    }
}

/// Profily gramatiky protojazyků (`scenarios.SYNTAX_GRAMMAR` a spol.).
pub mod profile {
    use super::{Construction, PROFILE_ORDER};

    /// Funkce → výchozí konstrukce, v pořadí vložení.
    pub type Grammar = Vec<(&'static str, Construction)>;

    /// Minulý čas, plurál a pád předmětu koncovkou, zápor částicí před slovesem, volný slovosled.
    pub fn syntax() -> Grammar {
        vec![
            ("PAST", Construction::new("PAST", "synthetic")),
            ("PL", Construction::new("PL", "synthetic")),
            ("OBJ", Construction::new("OBJ", "synthetic")),
            ("NEG", Construction::new("NEG", "pre").with_source("not")),
            ("ORDER", Construction::new("ORDER", "free")),
        ]
    }

    /// Menšinový jazyk: zápor za slovesem a pevné SOV.
    pub fn substrate() -> Grammar {
        let mut grammar: Grammar = syntax()
            .into_iter()
            .filter(|(name, _)| *name != "NEG" && *name != "ORDER")
            .collect();
        grammar.push(("NEG", Construction::new("NEG", "post").with_source("step")));
        grammar.push((
            "ORDER",
            Construction::new("ORDER", "fixed").with_order("SOV"),
        ));
        // Pořadí klíčů jako ve slovníku Pythonu: PAST, PL, OBJ, NEG, ORDER (přepis nahrazuje na místě).
        grammar.sort_by_key(|(name, _)| PROFILE_ORDER.iter().position(|id| id == name));
        grammar
    }

    /// Úplná gramatika: syntax a funkce, které jazyk může vyvinout.
    pub fn full() -> Grammar {
        let mut grammar = syntax();
        for name in ["FUTURE", "DEFINITE", "ASPECT"] {
            grammar.push((name, Construction::new(name, "zero")));
        }
        grammar
    }

    pub fn by_name(name: &str) -> Option<Grammar> {
        match name {
            "default" => Some(syntax()),
            "substrate" => Some(substrate()),
            "full" => Some(full()),
            _ => None,
        }
    }
}
