//! Kalibrační konstanty dynamiky jako data světa: zrcadlo `cee.v2.parameters`.
//!
//! Stejná pole a stejné slovní úrovně (`*_levels`). **Výchozí hodnoty, popisy,
//! skupiny pro UI a meze nejsou v kódu**, jsou v `src/cee/data/v2_parameters.json`
//! (jediný zdroj, čte ho i Python a server); tady se soubor vkládá přes
//! `include_str!` (`data::PARAMETERS_JSON`) a ověřují se podle něj přepisy
//! z popisu světa. Parametry patří světu, převezmou se jednou při stavbě světa
//! a sdílí se neměnně (`Arc<Parameters>`), takže fáze je čtou bez zámků.

use std::collections::BTreeMap;
use std::sync::OnceLock;

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::data::PARAMETERS_JSON;

/// Mapování jméno → hodnota (řazené podle klíče jako `FrozenMapping`).
pub type Table = BTreeMap<String, f64>;
/// Mapování jméno → (jméno → hodnota).
pub type Table2 = BTreeMap<String, Table>;

/// Pole katalogu gramatických funkcí, která lze přepsat v `Parameters::grammar`.
pub const GRAMMAR_FIELDS: [&str; 3] = ["need", "context", "coverage"];
/// Domény slov a kanály, kterými slova přicházejí z jiného kódu.
pub const DOMAINS: [&str; 5] = ["core", "learned", "culture", "religion", "power"];
pub const CHANNELS: [&str; 6] = ["neighbor", "elite", "trade", "liturgy", "reading", "school"];

/// Druh parametru v `v2_parameters.json`.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Kind {
    /// Jedno číslo.
    Number,
    /// Jméno → číslo.
    Table,
    /// Jméno → (jméno → číslo).
    Table2,
    /// Slovní úrovně: jméno úrovně → číslo (autor světa zadává jméno).
    LevelTable,
    /// Slovní úrovně s víc hodnotami: jméno úrovně → (jméno → číslo).
    LevelTable2,
}

/// Skupina parametrů pro UI.
#[derive(Clone, Debug, Deserialize)]
pub struct Group {
    pub id: String,
    pub title: String,
}

/// Jeden parametr: výchozí hodnota, druh, popis, skupina a meze (jen kde je kód vynucuje).
#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ParameterSpec {
    pub name: String,
    pub kind: Kind,
    pub default: Value,
    pub description: String,
    pub group: String,
    /// Povolená jména (vnější klíče tabulky), když jsou omezená.
    #[serde(default)]
    pub keys: Option<Vec<String>>,
    /// Povolená jména vnitřních klíčů (`table2`), když jsou omezená.
    #[serde(default)]
    pub inner_keys: Option<Vec<String>>,
    /// Nejmenší a největší povolená hodnota čísla, když je kód vynucuje.
    #[serde(default)]
    pub min: Option<f64>,
    #[serde(default)]
    pub max: Option<f64>,
}

/// Celý soubor `v2_parameters.json`.
#[derive(Clone, Debug, Deserialize)]
pub struct ParameterFile {
    pub format: String,
    pub groups: Vec<Group>,
    pub parameters: Vec<ParameterSpec>,
}

/// Soubor metaparametrů (načte se jednou).
pub fn parameter_file() -> &'static ParameterFile {
    static FILE: OnceLock<ParameterFile> = OnceLock::new();
    FILE.get_or_init(|| serde_json::from_str(PARAMETERS_JSON).expect("v2_parameters.json"))
}

fn number(value: &Value, path: &str, spec: &ParameterSpec) -> Result<(), String> {
    let Some(x) = value.as_f64().filter(|_| value.is_number()) else {
        return Err(format!("{path}: očekáváno číslo"));
    };
    if spec.min.is_some_and(|min| x < min) {
        return Err(format!(
            "{path}: nesmí být menší než {}",
            spec.min.unwrap_or_default()
        ));
    }
    if spec.max.is_some_and(|max| x > max) {
        return Err(format!(
            "{path}: nesmí být větší než {}",
            spec.max.unwrap_or_default()
        ));
    }
    Ok(())
}

fn check_keys(
    object: &serde_json::Map<String, Value>,
    allowed: &Option<Vec<String>>,
    path: &str,
) -> Result<(), String> {
    if let Some(allowed) = allowed {
        if let Some(key) = object.keys().find(|k| !allowed.contains(k)) {
            return Err(format!(
                "{path}.{key}: neznámé jméno; možnosti: {}",
                allowed.join(", ")
            ));
        }
    }
    Ok(())
}

impl ParameterSpec {
    /// Ověří přepis podle druhu a mezí souboru; chyba nese cestu `parameters.<jméno>…`.
    pub fn check(&self, value: &Value) -> Result<(), String> {
        let path = format!("parameters.{}", self.name);
        match self.kind {
            Kind::Number => number(value, &path, self),
            Kind::Table | Kind::LevelTable => {
                let object = value
                    .as_object()
                    .ok_or_else(|| format!("{path}: očekávána tabulka jméno → číslo"))?;
                check_keys(object, &self.keys, &path)?;
                object
                    .iter()
                    .try_for_each(|(k, v)| number(v, &format!("{path}.{k}"), self))
            }
            Kind::Table2 | Kind::LevelTable2 => {
                let object = value
                    .as_object()
                    .ok_or_else(|| format!("{path}: očekávána tabulka jméno → jméno → číslo"))?;
                check_keys(object, &self.keys, &path)?;
                for (k, inner) in object {
                    let inner_path = format!("{path}.{k}");
                    let inner = inner
                        .as_object()
                        .ok_or_else(|| format!("{inner_path}: očekávána tabulka jméno → číslo"))?;
                    check_keys(inner, &self.inner_keys, &inner_path)?;
                    inner
                        .iter()
                        .try_for_each(|(n, v)| number(v, &format!("{inner_path}.{n}"), self))?;
                }
                Ok(())
            }
        }
    }
}

thread_local! {
    /// Výchozí parametry podstrčené kalibrací (`with_defaults`); `None` = soubor.
    static OVERRIDE: std::cell::RefCell<Option<Parameters>> = const { std::cell::RefCell::new(None) };
}

/// Spustí `run` tak, že `Parameters::default()` na tomto vlákně vrací `params` (varianta
/// kalibrace `cee calibrate`). Scénáře berou výchozí parametry při stavbě světa; běh pak čte
/// jen parametry světa, takže vnořená vlákna simulace přepis nepotřebují. Po návratu (i při
/// panice) platí předchozí stav, takže vnoření a kradení práce rayonem jsou bezpečné.
pub fn with_defaults<T>(params: Option<&Parameters>, run: impl FnOnce() -> T) -> T {
    struct Restore(Option<Parameters>);
    impl Drop for Restore {
        fn drop(&mut self) {
            let previous = self.0.take();
            OVERRIDE.with(|cell| *cell.borrow_mut() = previous);
        }
    }
    let previous = OVERRIDE.with(|cell| cell.replace(params.cloned()));
    let _restore = Restore(previous);
    run()
}

impl Parameters {
    /// Výchozí hodnoty ze souboru `v2_parameters.json` bez přepisu kalibrace.
    pub fn file_default() -> Parameters {
        static DEFAULT: OnceLock<Parameters> = OnceLock::new();
        DEFAULT
            .get_or_init(|| {
                let map: serde_json::Map<String, Value> = parameter_file()
                    .parameters
                    .iter()
                    .map(|p| (p.name.clone(), p.default.clone()))
                    .collect();
                serde_json::from_value(Value::Object(map))
                    .expect("výchozí hodnoty v2_parameters.json odpovídají Parameters")
            })
            .clone()
    }
}

impl Default for Parameters {
    /// Výchozí hodnoty ze souboru `v2_parameters.json` (sestaví se jednou), nebo varianta
    /// kalibrace nastavená [`with_defaults`] na tomto vlákně.
    fn default() -> Self {
        OVERRIDE
            .with(|cell| cell.borrow().clone())
            .unwrap_or_else(Parameters::file_default)
    }
}

/// Kalibrační konstanty dynamiky jazyka; patří světu, ne modulu.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Parameters {
    pub functional_load_scale: f64,
    pub stress_strength_multiplier: f64,
    pub coda_tolerance_scale: f64,
    pub learnability_strength: f64,
    pub economy_word_cost: f64,
    pub fusion_bonus: f64,
    pub order_rigidity: f64,
    pub emergence_need_scale: f64,
    pub extravagance: f64,
    pub population_per_density: f64,
    pub loyalty_spread: f64,
    pub semantic_recurrence: f64,
    pub village_openness: f64,
    pub border_link_scale: f64,
    pub category_loss_l2_boost: f64,
    pub analogy_l2_boost: f64,
    pub clarity_short_factor: f64,
    pub dispersion_factor: f64,
    pub entrenchment_strength: f64,
    pub entrenchment_frequency_exponent: f64,
    pub entrenchment_base: f64,
    pub lexical_appeal_sd: f64,
    pub standing_variation: f64,
    pub variation_cap: f64,
    pub interference_weight: f64,
    pub school_correction: f64,
    pub shift_rate: f64,
    pub shift_exponent: f64,
    pub child_threshold: f64,
    pub reading_weight: f64,
    pub reading_core_resistance: f64,
    pub school_weight: f64,
    pub liturgy_weight: f64,
    pub channel_domains: Table2,
    pub borrowability_strength: f64,
    pub grammar_threshold: f64,
    pub conserved_frequency: f64,
    pub analogy_threshold: f64,
    pub restructure_threshold: f64,
    pub word_bias_sd: f64,
    pub frequency_lead: f64,
    pub closure_generations: f64,
    pub activation_share: f64,
    pub paradigm_merge_weight: f64,
    pub redundant_merge_weight: f64,
    pub capital_prestige: f64,
    pub capital_link_strength: f64,
    pub capital_reach: f64,
    pub centralization_levels: Table,
    pub policy_levels: Table2,
    pub lingua_franca_levels: Table,
    pub lingua_franca_link: f64,
    pub lingua_franca_pull: f64,
    pub revival_levels: Table2,
    pub border_levels: Table,
    pub background_levels: Table,
    pub background_spans: Table2,
    pub background_elite_prestige: f64,
    pub background_elite_link: f64,
    pub background_elite_share: f64,
    pub background_rates: Table,
    pub literacy_levels: Table,
    pub schooling_levels: Table,
    pub standard_prestige: f64,
    pub terrain_access: Table,
    pub identity_loyalty: Table,
    pub pressure_weights: Table,
    pub population_pressure_exponents: Table,
    pub change_rates: Table,
    pub grammar: Table2,
}

/// Tabulky slovních úrovní, které autor světa zadává jménem.
pub const LEVEL_TABLES: [&str; 10] = [
    "centralization_levels",
    "policy_levels",
    "lingua_franca_levels",
    "terrain_access",
    "identity_loyalty",
    "literacy_levels",
    "schooling_levels",
    "border_levels",
    "revival_levels",
    "background_levels",
];

impl Parameters {
    /// Parametry z přepisů polí (`WorldSpec.parameters`): neznámé pole, špatný druh nebo hodnota
    /// mimo meze souboru je chyba s cestou `parameters.<jméno>`;
    /// `channel_domains` se doplní výchozími váhami (jako `_channel_domains`).
    pub fn from_overrides(
        overrides: &serde_json::Map<String, serde_json::Value>,
    ) -> Result<Parameters, String> {
        let mut base = serde_json::to_value(Parameters::default()).map_err(|e| e.to_string())?;
        let known = base.as_object_mut().expect("objekt");
        for (key, value) in overrides {
            let Some(spec) = parameter_file().parameters.iter().find(|p| &p.name == key) else {
                return Err(format!("parameters.{key}: neznámý parametr"));
            };
            spec.check(value)?;
            known.insert(key.clone(), value.clone());
        }
        let mut params: Parameters = serde_json::from_value(base).map_err(|e| e.to_string())?;
        params.normalize()?;
        Ok(params)
    }

    /// Doplní `channel_domains` výchozími váhami a ověří přepisy gramatiky a kanálů.
    pub fn normalize(&mut self) -> Result<(), String> {
        for (function, fields) in &self.grammar {
            let unknown: Vec<&String> = fields
                .keys()
                .filter(|k| !GRAMMAR_FIELDS.contains(&k.as_str()))
                .collect();
            if !unknown.is_empty() {
                return Err(format!(
                    "Funkci '{function}' lze přepsat jen v polích {GRAMMAR_FIELDS:?}, ne {unknown:?}."
                ));
            }
        }
        let given = std::mem::take(&mut self.channel_domains);
        if let Some(channel) = given.keys().find(|c| !CHANNELS.contains(&c.as_str())) {
            return Err(format!(
                "Neznámý kanál [{channel}]; možnosti: {}.",
                CHANNELS.join(", ")
            ));
        }
        let mut merged = Parameters::default().channel_domains;
        for (channel, extra) in given {
            let row = merged.get_mut(&channel).expect("kanál");
            for (domain, value) in extra {
                if !DOMAINS.contains(&domain.as_str()) {
                    return Err(format!(
                        "Neznámá doména [{domain}] v kanálu '{channel}'; možnosti: {}.",
                        DOMAINS.join(", ")
                    ));
                }
                if value < 0.0 {
                    return Err(format!(
                        "Váha domény [{domain}] v kanálu '{channel}' nesmí být záporná."
                    ));
                }
                row.insert(domain, value);
            }
        }
        self.channel_domains = merged;
        Ok(())
    }

    /// Hodnota slovní úrovně; neznámou odmítne s výčtem možností (`parameters.level`).
    pub fn level(table: &Table, name: &str, what: &str) -> Result<f64, String> {
        table.get(name).copied().ok_or_else(|| {
            let options: Vec<&str> = table.keys().map(String::as_str).collect();
            format!("Neznámá {what} '{name}'; možnosti: {}.", options.join(", "))
        })
    }

    /// Možnosti slovních úrovní pro UI (`spec.levels`): tabulka → seřazená jména.
    pub fn levels(&self) -> BTreeMap<&'static str, Vec<String>> {
        let tables: [(&'static str, Vec<String>); 10] = [
            (
                "centralization_levels",
                self.centralization_levels.keys().cloned().collect(),
            ),
            (
                "policy_levels",
                self.policy_levels.keys().cloned().collect(),
            ),
            (
                "lingua_franca_levels",
                self.lingua_franca_levels.keys().cloned().collect(),
            ),
            (
                "terrain_access",
                self.terrain_access.keys().cloned().collect(),
            ),
            (
                "identity_loyalty",
                self.identity_loyalty.keys().cloned().collect(),
            ),
            (
                "literacy_levels",
                self.literacy_levels.keys().cloned().collect(),
            ),
            (
                "schooling_levels",
                self.schooling_levels.keys().cloned().collect(),
            ),
            (
                "border_levels",
                self.border_levels.keys().cloned().collect(),
            ),
            (
                "revival_levels",
                self.revival_levels.keys().cloned().collect(),
            ),
            (
                "background_levels",
                self.background_levels.keys().cloned().collect(),
            ),
        ];
        tables.into_iter().collect()
    }
}
