//! Kalibrační konstanty dynamiky jako data světa: zrcadlo `cee.v2.parameters`.
//!
//! Stejná pole, stejné výchozí hodnoty a stejné slovní úrovně (`*_levels`).
//! Dokumentace jednotlivých konstant je v Pythonu (`parameters.py`) a platí
//! beze změny; tady jsou jen tabulky a krátké poznámky. Parametry patří světu
//! a sdílí se neměnně (`Arc<Parameters>`), takže fáze je čtou bez zámků.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

/// Mapování jméno → hodnota (řazené podle klíče jako `FrozenMapping`).
pub type Table = BTreeMap<String, f64>;
/// Mapování jméno → (jméno → hodnota).
pub type Table2 = BTreeMap<String, Table>;

/// Pole katalogu gramatických funkcí, která lze přepsat v `Parameters::grammar`.
pub const GRAMMAR_FIELDS: [&str; 3] = ["need", "context", "coverage"];
/// Domény slov a kanály, kterými slova přicházejí z jiného kódu.
pub const DOMAINS: [&str; 5] = ["core", "learned", "culture", "religion", "power"];
pub const CHANNELS: [&str; 6] = ["neighbor", "elite", "trade", "liturgy", "reading", "school"];

fn table(items: &[(&str, f64)]) -> Table {
    items.iter().map(|&(k, v)| (k.to_owned(), v)).collect()
}

fn table2(items: &[(&str, &[(&str, f64)])]) -> Table2 {
    items
        .iter()
        .map(|&(k, v)| (k.to_owned(), table(v)))
        .collect()
}

/// Výchozí váhy domén v kanálech (`DEFAULT_CHANNEL_DOMAINS`).
pub fn default_channel_domains() -> Table2 {
    let mut out = Table2::new();
    for channel in CHANNELS {
        let mut row: Table = DOMAINS.iter().map(|d| ((*d).to_owned(), 1.0)).collect();
        let boost = match channel {
            "elite" => Some(("power", 3.0)),
            "trade" => Some(("culture", 3.0)),
            "liturgy" => Some(("religion", 3.0)),
            "reading" | "school" => Some(("learned", 2.0)),
            _ => None,
        };
        if let Some((domain, weight)) = boost {
            row.insert(domain.to_owned(), weight);
        }
        out.insert(channel.to_owned(), row);
    }
    out
}

/// Kalibrační konstanty dynamiky jazyka; patří světu, ne modulu.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Parameters {
    pub functional_load_scale: f64,
    pub stress_strength_multiplier: f64,
    pub coda_tolerance_scale: f64,
    pub learnability_strength: f64,
    pub economy_word_cost: f64,
    pub fusion_bonus: f64,
    pub order_rigidity: f64,
    pub emergence_need_scale: f64,
    pub population_per_density: f64,
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
    pub change_rates: Table,
    pub grammar: Table2,
}

impl Default for Parameters {
    fn default() -> Self {
        Parameters {
            functional_load_scale: 5.0,
            stress_strength_multiplier: 1.5,
            coda_tolerance_scale: 0.0,
            learnability_strength: 1.0,
            economy_word_cost: 0.15,
            fusion_bonus: 0.25,
            order_rigidity: 0.05,
            emergence_need_scale: 0.6,
            population_per_density: 500.0,
            village_openness: 0.5,
            border_link_scale: 1.0,
            category_loss_l2_boost: 4.0,
            analogy_l2_boost: 4.0,
            clarity_short_factor: 1.5,
            dispersion_factor: 4.0,
            entrenchment_strength: 0.3,
            entrenchment_frequency_exponent: 1.0,
            entrenchment_base: 0.0,
            lexical_appeal_sd: 0.03,
            standing_variation: 1.0,
            variation_cap: 0.4,
            interference_weight: 0.5,
            school_correction: 0.8,
            shift_rate: 1.0,
            shift_exponent: 1.31,
            child_threshold: 0.2,
            reading_weight: 0.1,
            reading_core_resistance: 1.0,
            school_weight: 0.3,
            liturgy_weight: 0.1,
            channel_domains: default_channel_domains(),
            borrowability_strength: 3.0,
            grammar_threshold: 0.85,
            conserved_frequency: 0.7,
            analogy_threshold: 0.85,
            restructure_threshold: 0.85,
            word_bias_sd: 1.5,
            frequency_lead: 1.0,
            closure_generations: 2.0,
            activation_share: 0.05,
            paradigm_merge_weight: 1.0,
            redundant_merge_weight: 0.3,
            capital_prestige: 2.0,
            capital_link_strength: 0.3,
            capital_reach: 150.0,
            centralization_levels: table(&[
                ("none", 0.0),
                ("weak", 0.5),
                ("moderate", 1.0),
                ("strong", 2.0),
            ]),
            policy_levels: table2(&[
                ("tolerant", &[("share", 0.1), ("pull", 0.0)]),
                ("promoted", &[("share", 0.3), ("pull", 0.1)]),
                ("enforced", &[("share", 0.6), ("pull", 1.0)]),
            ]),
            lingua_franca_levels: table(&[("rare", 0.1), ("common", 0.3), ("universal", 0.6)]),
            lingua_franca_link: 0.3,
            lingua_franca_pull: 0.1,
            revival_levels: table2(&[
                ("movement", &[("pace", 0.3), ("seed", 0.02)]),
                ("national", &[("pace", 1.0), ("seed", 0.05)]),
            ]),
            border_levels: table(&[("open", 1.0), ("normal", 0.5), ("closed", 0.1)]),
            background_levels: table(&[
                ("none", 0.0),
                ("calm", 0.3),
                ("normal", 1.0),
                ("turbulent", 2.5),
            ]),
            background_spans: table2(&[
                ("plague_mortality", &[("low", 0.15), ("high", 0.4)]),
                ("recovery_steps", &[("low", 2.0), ("high", 4.0)]),
                ("resettlement_share", &[("low", 0.05), ("high", 0.15)]),
                ("trade_factor", &[("low", 1.5), ("high", 3.0)]),
                ("trade_steps", &[("low", 4.0), ("high", 12.0)]),
                ("prestige_factor", &[("low", 0.7), ("high", 1.4)]),
                ("elite_steps", &[("low", 4.0), ("high", 12.0)]),
            ]),
            background_elite_prestige: 2.0,
            background_elite_link: 0.1,
            background_elite_share: 0.1,
            background_rates: table(&[
                ("plague", 0.08),
                ("resettlement", 0.12),
                ("trade", 0.12),
                ("prestige", 0.08),
                ("foreign_elite", 0.02),
            ]),
            literacy_levels: table(&[("elite", 0.05), ("towns", 0.2), ("mass", 0.8)]),
            schooling_levels: table(&[("towns", 0.3), ("mass", 0.8)]),
            standard_prestige: 1.5,
            terrain_access: table(&[
                ("plain", 1.0),
                ("hills", 0.6),
                ("mountains", 0.3),
                ("island", 0.2),
            ]),
            identity_loyalty: table(&[("shared", 0.0), ("distinct", 0.5), ("strong", 0.8)]),
            pressure_weights: Table::new(),
            change_rates: Table::new(),
            grammar: Table2::new(),
        }
    }
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
    /// Parametry z přepisů polí (`WorldSpec.parameters`): neznámé pole je chyba,
    /// `channel_domains` se doplní výchozími váhami (jako `_channel_domains`).
    pub fn from_overrides(
        overrides: &serde_json::Map<String, serde_json::Value>,
    ) -> Result<Parameters, String> {
        let mut base = serde_json::to_value(Parameters::default()).map_err(|e| e.to_string())?;
        let known = base.as_object_mut().expect("objekt");
        for (key, value) in overrides {
            if !known.contains_key(key) {
                return Err(format!("{key}: neznámý parametr"));
            }
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
        let mut merged = default_channel_domains();
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
