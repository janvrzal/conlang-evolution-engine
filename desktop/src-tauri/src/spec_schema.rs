//! Popis zadání světa (`cee-v2-world/1`) v Rustu: JSON schéma pro UI a ověření tvaru
//! s českými hláškami a cestou k poli.
//!
//! Odpovídá pydantic modelům v `src/cee/v2/spec.py` (pole, povinnost, typy, meze, výchozí
//! hodnoty, druhy událostí). Rustové typy enginu (`cee_engine::spec`) meze ani tvary událostí
//! nenesou, proto je popis tady jako tabulka. Test `tests::shoda_s_pydanticem` porovnává
//! výsledné schéma s výstupem pydanticu (`tests/pydantic-schema.json`, `scripts/schema.py`),
//! aby se Rust a Python nerozešly.

use serde_json::{json, Map, Value};

use crate::engine::Issue;

#[derive(Clone, Copy)]
enum Ty {
    Str,
    Int,
    Num,
    Bool,
    /// libovolná hodnota (přepisy parametrů)
    Any,
    /// jedna z možností
    Lit(&'static [&'static str]),
    /// pevný druh události
    Const(&'static str),
    List(&'static Ty),
    Map(&'static Ty),
    /// dvojice čísel (poloha)
    Point,
    /// dvojice [text, číslo] (koncovka a váha)
    Ending,
    Ref(&'static str),
    /// seznam událostí podle `kind`
    Events,
}

#[derive(Clone, Copy, Default)]
struct Bounds {
    min_len: Option<usize>,
    ge: Option<f64>,
    gt: Option<f64>,
    le: Option<f64>,
    lt: Option<f64>,
    pattern: bool,
}

struct Field {
    name: &'static str,
    ty: Ty,
    /// `None` je povolené (pydantic `X | None`)
    nullable: bool,
    /// výchozí hodnota; `None` = povinné pole
    default: Option<fn() -> Value>,
    bounds: Bounds,
}

struct Model {
    name: &'static str,
    doc: Option<&'static str>,
    fields: Vec<Field>,
}

const STR: Ty = Ty::Str;
const NUM: Ty = Ty::Num;
const INT: Ty = Ty::Int;
const STR_LIST: Ty = Ty::List(&STR);
const STR_MAP: Ty = Ty::Map(&STR);
const CONSTRUCTION: Ty = Ty::Ref("ConstructionSpec");
const ENDING: Ty = Ty::Ending;
const ENDINGS: Ty = Ty::List(&ENDING);
const PROCESS: Ty = Ty::Ref("InitialProcessSpec");
const RELATED: Ty = Ty::Ref("RelatedSpec");
const LANGUAGE: Ty = Ty::Ref("LanguageSpec");
const REGION: Ty = Ty::Ref("RegionSpec");
const CONCEPT: Ty = Ty::Ref("ConceptSpec");
const ANY: Ty = Ty::Any;

const GRAMMARS: &[&str] = &["default", "substrate", "full"];
const STRESS: &[&str] = &["initial", "second", "antepenult", "penult", "final", "weight"];
const STRENGTH: &[&str] = &["weak", "strong"];
const SYLLABLES: &[&str] = &["simple", "moderate", "complex"];
const RELATION_KINDS: &[&str] = &["polysemy", "derivation", "colexification"];
const RELATION_DIRECTIONS: &[&str] = &["to", "from", "both"];
const DOMAINS: &[&str] = &["core", "learned", "culture", "religion", "power"];
const WORD_CLASSES: &[&str] = &["noun", "verb", "uninflected"];
pub const FREQUENCY_RANGE: (f64, f64) = (0.05, 0.9);
pub const DEFAULT_VOCABULARY: u64 = 149;
pub const PRESET_SIZES: [u64; 4] = [149, 200, 500, 1000];

/// Pořadí druhů událostí jako v pydanticu (`EVENT_KINDS`).
pub const EVENT_KINDS: [&str; 16] = [
    "state", "language_policy", "annexation", "secession", "collapse", "border_policy", "lingua_franca", "standard",
    "schools", "revival", "preserve", "identity", "immigration", "settlement", "elite", "sound_shift",
];
const EVENT_MODELS: [&str; 16] = [
    "StateSpec", "LanguagePolicySpec", "AnnexationSpec", "SecessionSpec", "CollapseSpec", "BorderPolicySpec", "LinguaFrancaSpec",
    "StandardSpec", "SchoolsSpec", "RevivalSpec", "PreserveSpec", "IdentitySpec", "ImmigrationSpec", "SettlementSpec",
    "EliteSpec", "SoundShiftSpec",
];

fn req(name: &'static str, ty: Ty) -> Field {
    Field { name, ty, nullable: false, default: None, bounds: Bounds::default() }
}
fn opt(name: &'static str, ty: Ty, default: fn() -> Value) -> Field {
    Field { name, ty, nullable: false, default: Some(default), bounds: Bounds::default() }
}
fn null(name: &'static str, ty: Ty) -> Field {
    Field { name, ty, nullable: true, default: Some(|| Value::Null), bounds: Bounds::default() }
}
impl Field {
    fn b(mut self, f: impl FnOnce(&mut Bounds)) -> Field {
        f(&mut self.bounds);
        self
    }
    fn nonempty(self) -> Field {
        self.b(|b| b.min_len = Some(1))
    }
}

fn models() -> Vec<Model> {
    let year = || req("year", NUM);
    let kind = |k: &'static str| req("kind", Ty::Const(k));
    let state_like = |k: &'static str, name: &'static str| Model {
        name,
        doc: None,
        fields: vec![
            year(),
            kind(k),
            req("id", STR).nonempty(),
            null("name", STR),
            req("regions", STR_LIST).nonempty(),
            req("capital", STR),
            opt("centralization", STR, || json!("moderate")),
            opt("policy", STR, || json!("tolerant")),
            opt("border", STR, || json!("normal")),
            null("language", STR),
        ],
    };
    let mut all = vec![
        Model {
            name: "ConstructionSpec",
            doc: Some("Konstrukce gramatické funkce (druh, zdrojové slovo, stadium, pořadí, posila)."),
            fields: vec![req("kind", STR).nonempty(), null("source", STR), null("stage", STR), null("order", STR), null("reinforcer", STR)],
        },
        Model {
            name: "InitialProcessSpec",
            doc: Some("Zvuková změna rozběhnutá na startu (rodina, popis kandidáta, podíl mluvčích)."),
            fields: vec![
                req("family", STR).nonempty(),
                req("label", STR).nonempty(),
                req("share", NUM).b(|b| {
                    b.gt = Some(0.0);
                    b.lt = Some(1.0)
                }),
            ],
        },
        Model {
            name: "LanguageSpec",
            doc: Some("Protojazyk jedné linie."),
            fields: vec![
                req("id", STR).nonempty(),
                null("name", STR),
                null("consonants", STR_LIST).nonempty(),
                null("vowels", STR_LIST).nonempty(),
                opt("grammar", Ty::Lit(GRAMMARS), || json!("default")),
                opt("stress", Ty::Lit(STRESS), || json!("penult")),
                opt("stress_strength", Ty::Lit(STRENGTH), || json!("weak")),
                opt("words", STR_MAP, || json!({})),
                opt("endonym", STR_LIST, || json!([])),
                opt("tones", STR_LIST, || json!([])),
                opt("constructions", Ty::Map(&CONSTRUCTION), || json!({})),
                opt("endings", Ty::Map(&ENDINGS), || json!({})),
                opt("processes", Ty::List(&PROCESS), || json!([])),
                opt("suffixes", STR_LIST, || json!([])),
                null("syllables", Ty::Lit(SYLLABLES)),
            ],
        },
        Model {
            name: "RegionSpec",
            doc: Some("Region jako síť vesnic (``scenarios.Region``)."),
            fields: vec![
                req("id", STR).nonempty(),
                null("name", STR),
                req("position", Ty::Point),
                opt("density", NUM, || json!(1.0)).b(|b| {
                    b.gt = Some(0.0);
                    b.le = Some(100.0)
                }),
                opt("neighbours", STR_LIST, || json!([])),
                opt("villages", INT, || json!(4)).b(|b| {
                    b.ge = Some(1.0);
                    b.le = Some(12.0)
                }),
                opt("prestige", NUM, || json!(0.5)).b(|b| b.ge = Some(0.0)),
                null("language", STR),
                opt("terrain", STR, || json!("plain")),
                opt("identity", STR, || json!("shared")),
                opt("preserve", Ty::Bool, || json!(false)),
                opt("immigration", NUM, || json!(0.0)).b(|b| {
                    b.ge = Some(0.0);
                    b.le = Some(1.0)
                }),
                null("city", NUM).b(|b| b.ge = Some(0.0)),
            ],
        },
        Model {
            name: "RelatedSpec",
            doc: Some("Příbuzný pojem vlastního pojmu pro posuny významu (``vocabulary.Related``)."),
            fields: vec![
                req("concept", STR).nonempty(),
                opt("kind", Ty::Lit(RELATION_KINDS), || json!("polysemy")),
                null("direction", Ty::Lit(RELATION_DIRECTIONS)),
                null("weight", INT).b(|b| {
                    b.ge = Some(1.0);
                    b.le = Some(100000.0)
                }),
            ],
        },
        Model {
            name: "ConceptSpec",
            doc: Some("Vlastní pojem autora světa, vymyšlený nebo reálný (``vocabulary.CustomConcept``)."),
            fields: vec![
                req("id", STR).b(|b| {
                    b.min_len = Some(1);
                    b.pattern = true
                }),
                null("gloss", STR),
                null("wold", STR),
                null("concepticon", INT).b(|b| b.ge = Some(1.0)),
                null("domain", Ty::Lit(DOMAINS)),
                null("frequency", NUM).b(|b| {
                    b.ge = Some(FREQUENCY_RANGE.0);
                    b.le = Some(FREQUENCY_RANGE.1)
                }),
                null("word_class", Ty::Lit(WORD_CLASSES)),
                null("borrowed", NUM).b(|b| {
                    b.ge = Some(0.0);
                    b.le = Some(1.0)
                }),
                opt("related", Ty::List(&RELATED), || json!([])),
            ],
        },
        state_like("state", "StateSpec"),
        Model { name: "LanguagePolicySpec", doc: None, fields: vec![year(), kind("language_policy"), req("state", STR), req("policy", STR)] },
        Model { name: "AnnexationSpec", doc: None, fields: vec![year(), kind("annexation"), req("state", STR), req("regions", STR_LIST).nonempty()] },
        state_like("secession", "SecessionSpec"),
        Model { name: "CollapseSpec", doc: None, fields: vec![year(), kind("collapse"), req("state", STR)] },
        Model { name: "BorderPolicySpec", doc: None, fields: vec![year(), kind("border_policy"), req("state", STR), req("border", STR)] },
        Model {
            name: "LinguaFrancaSpec",
            doc: None,
            fields: vec![
                year(),
                kind("lingua_franca"),
                req("source", STR),
                req("regions", STR_LIST).nonempty(),
                opt("spread", STR, || json!("common")),
                opt("nativize", Ty::Bool, || json!(false)),
            ],
        },
        Model { name: "StandardSpec", doc: None, fields: vec![year(), kind("standard"), req("of", STR), opt("literacy", STR, || json!("elite"))] },
        Model {
            name: "SchoolsSpec",
            doc: None,
            fields: vec![
                year(),
                kind("schools"),
                req("of", STR),
                opt("coverage", STR, || json!("mass")),
                opt("printing", Ty::Bool, || json!(true)),
                opt("diglossic", Ty::Bool, || json!(false)),
            ],
        },
        Model {
            name: "RevivalSpec",
            doc: None,
            fields: vec![year(), kind("revival"), req("regions", STR_LIST).nonempty(), null("language", STR), opt("strength", STR, || json!("movement"))],
        },
        Model {
            name: "PreserveSpec",
            doc: None,
            fields: vec![year(), kind("preserve"), req("regions", STR_LIST).nonempty(), null("language", STR), opt("preserved", Ty::Bool, || json!(true))],
        },
        Model { name: "IdentitySpec", doc: None, fields: vec![year(), kind("identity"), req("regions", STR_LIST).nonempty(), req("identity", STR)] },
        Model {
            name: "ImmigrationSpec",
            doc: None,
            fields: vec![
                year(),
                kind("immigration"),
                req("regions", STR_LIST).nonempty(),
                req("immigration", NUM).b(|b| {
                    b.ge = Some(0.0);
                    b.le = Some(1.0)
                }),
            ],
        },
        Model {
            name: "SettlementSpec",
            doc: Some("Lidé z regionu ``from`` se usadí v regionu ``to`` (migrace, nové osady)."),
            fields: vec![
                year(),
                kind("settlement"),
                req("from", STR).nonempty(),
                req("to", STR).nonempty(),
                opt("share", NUM, || json!(0.2)).b(|b| {
                    b.gt = Some(0.0);
                    b.lt = Some(1.0)
                }),
                opt("settlements", INT, || json!(1)).b(|b| b.ge = Some(1.0)),
                null("prestige", NUM),
            ],
        },
        Model {
            name: "EliteSpec",
            doc: Some("Elita z regionu ``from`` ovládne region ``seat`` (dobytí, superstrát)."),
            fields: vec![
                year(),
                kind("elite"),
                req("from", STR).nonempty(),
                req("seat", STR).nonempty(),
                null("language", STR),
                null("subjects", STR_LIST),
                opt("population", NUM, || json!(100.0)).b(|b| b.gt = Some(0.0)),
                opt("prestige", NUM, || json!(2.0)),
                opt("strength", NUM, || json!(0.5)).b(|b| b.gt = Some(0.0)),
                null("homeland", NUM).b(|b| b.ge = Some(0.0)),
            ],
        },
        Model {
            name: "SoundShiftSpec",
            doc: Some("Zadaná hlásková změna se rozběhne u jazyka ``language`` (dok. 26)."),
            fields: vec![
                year(),
                kind("sound_shift"),
                req("language", STR).nonempty(),
                opt("regions", STR_LIST, || json!([])),
                req("family", STR).nonempty(),
                req("label", STR).nonempty(),
                opt("share", NUM, || json!(0.2)).b(|b| {
                    b.gt = Some(0.0);
                    b.lt = Some(1.0)
                }),
                opt("pull", NUM, || json!(1.0)).b(|b| b.ge = Some(0.0)),
            ],
        },
        Model {
            name: "WorldSpec",
            doc: Some("Celý svět: protojazyky, regiony, časová osa a přepisy parametrů."),
            fields: vec![
                opt("format", Ty::Const("cee-v2-world/1"), || json!("cee-v2-world/1")),
                null("name", STR),
                opt("seed", INT, || json!(1)),
                opt("start_year", NUM, || json!(0.0)),
                req("end_year", NUM),
                req("languages", Ty::List(&LANGUAGE)).nonempty(),
                req("regions", Ty::List(&REGION)).nonempty(),
                opt("events", Ty::Events, || json!([])),
                opt("vocabulary", INT, || json!(DEFAULT_VOCABULARY)).b(|b| b.ge = Some(DEFAULT_VOCABULARY as f64)),
                opt("concepts", Ty::List(&CONCEPT), || json!([])),
                opt("semantics", Ty::Bool, || json!(true)),
                opt("village_spacing", NUM, || json!(10.0)).b(|b| b.gt = Some(0.0)),
                opt("generation_years", NUM, || json!(25.0)).b(|b| {
                    b.ge = Some(25.0);
                    b.le = Some(1000.0)
                }),
                opt("parameters", Ty::Map(&ANY), || json!({})),
                opt("background", STR, || json!("none")),
            ],
        },
    ];
    // studijní případ: volitelný štítek u každé události (engine zapíše `study_case`)
    for model in all.iter_mut().filter(|m| EVENT_MODELS.contains(&m.name)) {
        model.fields.push(null("study_case", STR));
    }
    all
}

// ---------- JSON schéma (tvar jako `WorldSpec.model_json_schema()` z pydanticu) ----------

fn title(name: &str) -> String {
    name.split('_')
        .map(|w| {
            let mut c = w.chars();
            c.next().map(|f| f.to_uppercase().collect::<String>() + c.as_str()).unwrap_or_default()
        })
        .collect::<Vec<_>>()
        .join(" ")
}

fn type_schema(ty: Ty, bounds: &Bounds) -> Map<String, Value> {
    let mut s = Map::new();
    let integer = matches!(ty, Ty::Int);
    let num = |s: &mut Map<String, Value>| {
        for (k, v) in [("minimum", bounds.ge), ("exclusiveMinimum", bounds.gt), ("maximum", bounds.le), ("exclusiveMaximum", bounds.lt)] {
            if let Some(v) = v {
                // celočíselné pole má meze jako celá čísla (jako pydantic)
                s.insert(k.into(), if integer { json!(v as i64) } else { json!(v) });
            }
        }
    };
    match ty {
        Ty::Str => {
            s.insert("type".into(), json!("string"));
            if let Some(n) = bounds.min_len {
                s.insert("minLength".into(), json!(n));
            }
            if bounds.pattern {
                s.insert("pattern".into(), json!(r"^\w[\w.-]*$"));
            }
        }
        Ty::Int => {
            s.insert("type".into(), json!("integer"));
            num(&mut s);
        }
        Ty::Num => {
            s.insert("type".into(), json!("number"));
            num(&mut s);
        }
        Ty::Bool => {
            s.insert("type".into(), json!("boolean"));
        }
        Ty::Any => {}
        Ty::Lit(options) => {
            s.insert("enum".into(), json!(options));
            s.insert("type".into(), json!("string"));
        }
        Ty::Const(c) => {
            s.insert("const".into(), json!(c));
            s.insert("type".into(), json!("string"));
        }
        Ty::List(inner) => {
            s.insert("items".into(), Value::Object(type_schema(*inner, &Bounds::default())));
            if let Some(n) = bounds.min_len {
                s.insert("minItems".into(), json!(n));
            }
            s.insert("type".into(), json!("array"));
        }
        Ty::Map(inner) => {
            // slovník libovolných hodnot má v JSON schématu `true` (jako pydantic u dict[str, Any])
            let items = if matches!(inner, Ty::Any) { json!(true) } else { Value::Object(type_schema(*inner, &Bounds::default())) };
            s.insert("additionalProperties".into(), items);
            s.insert("type".into(), json!("object"));
        }
        Ty::Point => {
            s.insert("maxItems".into(), json!(2));
            s.insert("minItems".into(), json!(2));
            s.insert("prefixItems".into(), json!([{ "type": "number" }, { "type": "number" }]));
            s.insert("type".into(), json!("array"));
        }
        Ty::Ending => {
            s.insert("maxItems".into(), json!(2));
            s.insert("minItems".into(), json!(2));
            s.insert("prefixItems".into(), json!([{ "type": "string" }, { "type": "number" }]));
            s.insert("type".into(), json!("array"));
        }
        Ty::Ref(name) => {
            s.insert("$ref".into(), json!(format!("#/$defs/{name}")));
        }
        Ty::Events => {
            let mapping: Map<String, Value> =
                EVENT_KINDS.iter().zip(EVENT_MODELS).map(|(k, m)| (k.to_string(), json!(format!("#/$defs/{m}")))).collect();
            s.insert(
                "items".into(),
                json!({
                    "discriminator": { "mapping": mapping, "propertyName": "kind" },
                    "oneOf": EVENT_MODELS.iter().map(|m| json!({ "$ref": format!("#/$defs/{m}") })).collect::<Vec<_>>(),
                }),
            );
            s.insert("type".into(), json!("array"));
        }
    }
    s
}

fn model_schema(m: &Model) -> Value {
    let mut props = Map::new();
    let mut required = Vec::new();
    for f in &m.fields {
        let inner = type_schema(f.ty, &f.bounds);
        let mut p = if f.nullable {
            let mut p = Map::new();
            p.insert("anyOf".into(), json!([Value::Object(inner), { "type": "null" }]));
            p
        } else {
            inner
        };
        if let Some(d) = f.default {
            // prázdný seznam či slovník je v pydanticu `default_factory`, ten do schématu výchozí hodnotu nepíše
            let value = d();
            let factory = value.as_array().is_some_and(Vec::is_empty) || value.as_object().is_some_and(Map::is_empty);
            if !factory {
                p.insert("default".into(), value);
            }
        } else {
            required.push(f.name);
        }
        p.insert("title".into(), json!(title(f.name)));
        props.insert(f.name.into(), Value::Object(p));
    }
    let mut out = Map::new();
    out.insert("additionalProperties".into(), json!(false));
    if let Some(doc) = m.doc {
        out.insert("description".into(), json!(doc));
    }
    out.insert("properties".into(), Value::Object(props));
    if !required.is_empty() {
        out.insert("required".into(), json!(required));
    }
    out.insert("title".into(), json!(m.name));
    out.insert("type".into(), json!("object"));
    Value::Object(out)
}

/// JSON schéma zadání světa (kořen `WorldSpec`, ostatní modely v `$defs`).
pub fn json_schema() -> Value {
    let all = models();
    let mut root = Map::new();
    let mut defs = Map::new();
    for m in &all {
        if m.name == "WorldSpec" {
            if let Value::Object(o) = model_schema(m) {
                root = o;
            }
        } else {
            defs.insert(m.name.into(), model_schema(m));
        }
    }
    root.insert("$defs".into(), Value::Object(defs));
    Value::Object(root)
}

/// Volby slovníku pro UI (bez `max`, ten zná engine).
pub fn vocabulary_options() -> Value {
    json!({
        "default": DEFAULT_VOCABULARY, "presets": PRESET_SIZES, "domains": DOMAINS, "word_classes": WORD_CLASSES,
        "relation_kinds": RELATION_KINDS, "relation_directions": RELATION_DIRECTIONS,
        "default_weight": { "polysemy": 2, "derivation": 2, "colexification": 9 },
        "frequency_range": [FREQUENCY_RANGE.0, FREQUENCY_RANGE.1],
    })
}

// ---------- ověření tvaru s českými hláškami ----------

fn number_text(v: f64) -> String {
    if v.fract() == 0.0 { format!("{v:.0}") } else { v.to_string() }
}

fn options_text(options: &[&str]) -> String {
    let quoted: Vec<String> = options.iter().map(|o| format!("'{o}'")).collect();
    match quoted.split_last() {
        Some((last, rest)) if !rest.is_empty() => format!("{} nebo {last}", rest.join(", ")),
        _ => quoted.join(""),
    }
}

struct Checker<'a> {
    models: &'a [Model],
    issues: Vec<Issue>,
}

impl Checker<'_> {
    fn issue(&mut self, path: &str, message: impl Into<String>) {
        let path = if path.is_empty() { "(svět)".into() } else { path.to_owned() };
        let message: String = message.into();
        self.issues.push(Issue::error(path, message.clone(), code_of(&message)));
    }

    fn model(&mut self, name: &str, value: &Value, path: &str) {
        let Some(model) = self.models.iter().find(|m| m.name == name) else { return };
        let Some(object) = value.as_object() else {
            return self.issue(path, "musí být objekt");
        };
        for f in &model.fields {
            let at = if path.is_empty() { f.name.to_owned() } else { format!("{path}.{}", f.name) };
            match object.get(f.name) {
                None if f.default.is_none() => self.issue(&at, "chybí povinné pole"),
                None => {}
                Some(Value::Null) if f.nullable => {}
                Some(v) => self.value(f.ty, &f.bounds, v, &at),
            }
        }
        for key in object.keys() {
            if !model.fields.iter().any(|f| f.name == key) {
                let at = if path.is_empty() { key.clone() } else { format!("{path}.{key}") };
                self.issue(&at, "neznámé pole");
            }
        }
    }

    fn bounds(&mut self, b: &Bounds, v: f64, path: &str) {
        if let Some(gt) = b.gt.filter(|gt| v <= *gt) {
            self.issue(path, format!("musí být větší než {}", number_text(gt)));
        } else if let Some(ge) = b.ge.filter(|ge| v < *ge) {
            self.issue(path, format!("musí být aspoň {}", number_text(ge)));
        } else if let Some(lt) = b.lt.filter(|lt| v >= *lt) {
            self.issue(path, format!("musí být menší než {}", number_text(lt)));
        } else if let Some(le) = b.le.filter(|le| v > *le) {
            self.issue(path, format!("smí být nejvýš {}", number_text(le)));
        }
    }

    fn value(&mut self, ty: Ty, b: &Bounds, v: &Value, path: &str) {
        match ty {
            Ty::Any => {}
            Ty::Str => match v.as_str() {
                None => self.issue(path, "musí být text"),
                Some(s) if b.min_len.is_some_and(|n| s.chars().count() < n) => self.issue(path, "nesmí být prázdné"),
                Some(s) if b.pattern && !valid_id(s) => self.issue(path, "smí obsahovat jen písmena, číslice, _ . - a začít písmenem nebo číslicí"),
                Some(_) => {}
            },
            Ty::Int => match v.as_f64() {
                Some(n) if n.fract() == 0.0 && !v.is_boolean() => self.bounds(b, n, path),
                _ => self.issue(path, "musí být celé číslo"),
            },
            Ty::Num => match v.as_f64() {
                Some(n) => self.bounds(b, n, path),
                None => self.issue(path, "musí být číslo"),
            },
            Ty::Bool => {
                if !v.is_boolean() {
                    self.issue(path, "musí být true nebo false");
                }
            }
            Ty::Lit(options) => {
                if !v.as_str().is_some_and(|s| options.contains(&s)) {
                    self.issue(path, format!("musí být jedna z možností: {}", options_text(options)));
                }
            }
            Ty::Const(c) => {
                if v.as_str() != Some(c) {
                    self.issue(path, format!("musí být jedna z možností: '{c}'"));
                }
            }
            Ty::List(inner) => match v.as_array() {
                None => self.issue(path, "musí být seznam"),
                Some(items) => {
                    if let Some(n) = b.min_len.filter(|n| items.len() < *n) {
                        self.issue(path, format!("počet položek musí být aspoň {n}"));
                    }
                    for (i, item) in items.iter().enumerate() {
                        self.value(*inner, &Bounds::default(), item, &format!("{path}.{i}"));
                    }
                }
            },
            Ty::Map(inner) => match v.as_object() {
                None => self.issue(path, "musí být objekt"),
                Some(o) => {
                    for (k, item) in o {
                        self.value(*inner, &Bounds::default(), item, &format!("{path}.{k}"));
                    }
                }
            },
            Ty::Point => {
                if !v.as_array().is_some_and(|a| a.len() == 2 && a.iter().all(Value::is_number)) {
                    self.issue(path, "musí být dvojice čísel");
                }
            }
            Ty::Ending => {
                if !v.as_array().is_some_and(|a| a.len() == 2 && a[0].is_string() && a[1].is_number()) {
                    self.issue(path, "musí být dvojice [tvar, váha]");
                }
            }
            Ty::Ref(name) => self.model(name, v, path),
            Ty::Events => match v.as_array() {
                None => self.issue(path, "musí být seznam"),
                Some(items) => {
                    for (i, item) in items.iter().enumerate() {
                        let at = format!("{path}.{i}");
                        match item.get("kind").and_then(Value::as_str) {
                            None => self.issue(&at, "chybí druh události (kind)"),
                            Some(k) => match EVENT_KINDS.iter().position(|e| *e == k) {
                                None => self.issue(&at, format!("neznámý druh události '{k}'; možnosti: {}", options_text(&EVENT_KINDS))),
                                Some(n) => self.model(EVENT_MODELS[n], item, &at),
                            },
                        }
                    }
                }
            },
        }
    }
}

/// Stálý kód hlášky tvaru zadání pro překlad v UI (podle druhu chyby).
fn code_of(message: &str) -> &'static str {
    const CODES: [(&str, &str); 12] = [
        ("chybí povinné pole", "field_missing"),
        ("neznámé pole", "field_unknown"),
        ("musí být jedna z možností", "field_option"),
        ("nesmí být prázdné", "field_empty"),
        ("počet položek", "field_count"),
        ("smí obsahovat jen", "field_pattern"),
        ("chybí druh události", "event_kind_missing"),
        ("neznámý druh události", "event_kind_unknown"),
        ("end_year musí", "world_years"),
        ("musí být větší", "field_range"),
        ("musí být aspoň", "field_range"),
        ("smí být nejvýš", "field_range"),
    ];
    CODES.iter().find(|(start, _)| message.starts_with(start)).map(|(_, code)| *code).unwrap_or(if message.starts_with("musí být menší") { "field_range" } else { "field_type" })
}

fn valid_id(s: &str) -> bool {
    let mut chars = s.chars();
    chars.next().is_some_and(|c| c.is_alphanumeric() || c == '_') && chars.all(|c| c.is_alphanumeric() || matches!(c, '_' | '.' | '-'))
}

/// Ověří tvar zadání (pole, typy, meze, druhy událostí); prázdné = tvar je v pořádku.
pub fn check_shape(spec: &Value) -> Vec<Issue> {
    let all = models();
    let mut c = Checker { models: &all, issues: Vec::new() };
    c.model("WorldSpec", spec, "");
    if c.issues.is_empty() {
        let (start, end) = (spec["start_year"].as_f64().unwrap_or(0.0), spec["end_year"].as_f64().unwrap_or(0.0));
        if end <= start {
            c.issue("", "end_year musí být později než start_year");
        }
    }
    c.issues
}

#[cfg(test)]
mod tests {
    use super::*;

    fn talvera() -> Value {
        serde_json::from_str(include_str!("../../static/projects/talvera.cee.json")).unwrap()
    }

    #[test]
    fn talvera_ma_spravny_tvar() {
        assert!(check_shape(&talvera()).is_empty(), "{:?}", check_shape(&talvera()));
    }

    #[test]
    fn hlasky_s_cestou() {
        let mut w = talvera();
        w["events"][3].as_object_mut().unwrap().remove("year");
        w["regions"][0]["villages"] = json!(20);
        w["languages"][0]["stress"] = json!("middle");
        w["events"][5]["kind"] = json!("flood");
        w["neznamy"] = json!(1);
        w["concepts"] = json!([{ "id": "-x" }]);
        let issues: Vec<String> = check_shape(&w).into_iter().map(|i| format!("{}: {}", i.path, i.message)).collect();
        for expected in [
            "events.3.year: chybí povinné pole",
            "regions.0.villages: smí být nejvýš 12",
            "languages.0.stress: musí být jedna z možností: 'initial', 'second', 'antepenult', 'penult', 'final' nebo 'weight'",
            "neznamy: neznámé pole",
            "concepts.0.id: smí obsahovat jen písmena, číslice, _ . - a začít písmenem nebo číslicí",
        ] {
            assert!(issues.iter().any(|i| i == expected), "chybí „{expected}“ v {issues:#?}");
        }
        assert!(issues.iter().any(|i| i.starts_with("events.5: neznámý druh události 'flood'")));
        let mut years = talvera();
        years["end_year"] = json!(-800);
        assert_eq!(check_shape(&years)[0].message, "end_year musí být později než start_year");
    }

    /// Schéma z Rustu se shoduje s pydanticem (`tests/pydantic-schema.json`, `scripts/schema.py`):
    /// stejné modely, pole, povinnost, typy, meze, výchozí hodnoty a druhy událostí.
    #[test]
    fn shoda_s_pydanticem() {
        let py: Value = serde_json::from_str(include_str!("../tests/pydantic-schema.json")).unwrap();
        let ours = json_schema();
        let py_schema = &py["json_schema"];
        let norm = |s: &Value| -> Value {
            // porovnává se jen to, co UI a ověření potřebují (bez titulků a popisů)
            fn strip(v: &Value) -> Value {
                match v {
                    Value::Object(o) => Value::Object(
                        o.iter()
                            .filter(|(k, _)| !matches!(k.as_str(), "title" | "description"))
                            .map(|(k, v)| (k.clone(), strip(v)))
                            .collect(),
                    ),
                    Value::Array(a) => Value::Array(a.iter().map(strip).collect()),
                    other => other.clone(),
                }
            }
            strip(s)
        };
        let (a, b) = (norm(&ours), norm(py_schema));
        let defs_a = a["$defs"].as_object().unwrap();
        let defs_b = b["$defs"].as_object().unwrap();
        assert_eq!(defs_a.keys().collect::<Vec<_>>(), defs_b.keys().collect::<Vec<_>>(), "modely");
        for (name, def) in defs_b {
            assert_eq!(&defs_a[name], def, "model {name} se liší od pydanticu");
        }
        let mut root_a = a.as_object().unwrap().clone();
        let mut root_b = b.as_object().unwrap().clone();
        root_a.remove("$defs");
        root_b.remove("$defs");
        for (key, value) in root_b["properties"].as_object().unwrap() {
            assert_eq!(&root_a["properties"][key], value, "WorldSpec.{key} se liší od pydanticu");
        }
        assert_eq!(root_a, root_b, "WorldSpec se liší od pydanticu");
        assert_eq!(json!(EVENT_KINDS), py["event_kinds"]);
        let mut vocab = py["vocabulary"].clone();
        vocab.as_object_mut().unwrap().remove("max");
        assert_eq!(vocabulary_options(), vocab);
    }
}
