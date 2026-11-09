//! Metaparametry ze souboru `v2_parameters.json`: výchozí hodnoty, přepisy, chyby, meze.

use cee_engine::parameters::{
    parameter_file, Kind, Parameters, Role, CHANNELS, DOMAINS, GRAMMAR_FIELDS, LEVEL_TABLES,
};
use serde_json::{json, Value};

fn overrides(value: Value) -> Result<Parameters, String> {
    Parameters::from_overrides(value.as_object().unwrap())
}

#[test]
fn soubor_pokryva_vsechna_pole_a_hodnoty_sedi() {
    let file = parameter_file();
    assert_eq!(file.format, "cee-v2-parameters/1");
    let value = serde_json::to_value(Parameters::default()).unwrap();
    let fields = value.as_object().unwrap();
    assert_eq!(file.parameters.len(), 88);
    assert_eq!(fields.len(), file.parameters.len());
    let world_count = file.by_role(Role::World).count();
    let active_count = file.by_role(Role::Active).count();
    let fixed_count = file.by_role(Role::Fixed).count();
    assert_eq!(world_count, 12);
    assert_eq!(active_count, 26);
    assert_eq!(fixed_count, 50);
    assert_eq!(world_count + active_count + fixed_count, file.parameters.len());
    for spec in &file.parameters {
        assert_eq!(fields[&spec.name], spec.default, "{}", spec.name);
        assert!(
            file.groups.iter().any(|g| g.id == spec.group),
            "{}",
            spec.name
        );
        assert!(!spec.description.is_empty(), "{}", spec.name);
        assert_eq!(
            LEVEL_TABLES.contains(&spec.name.as_str()),
            matches!(spec.kind, Kind::LevelTable | Kind::LevelTable2),
            "{}",
            spec.name
        );
    }
}

#[test]
fn vychozi_hodnoty_jsou_ze_souboru() {
    let params = Parameters::default();
    assert_eq!(params.functional_load_scale, 5.0);
    assert_eq!(params.shift_exponent, 1.31);
    assert_eq!(params.centralization_levels["strong"], 2.0);
    assert_eq!(params.policy_levels["enforced"]["pull"], 1.0);
    assert_eq!(params.channel_domains["elite"]["power"], 3.0);
    assert_eq!(params.channel_domains["neighbor"]["power"], 1.0);
    assert!(params.pressure_weights.is_empty() && params.grammar.is_empty());
}

#[test]
fn meze_a_jmena_v_souboru_odpovidaji_kodu() {
    let file = parameter_file();
    let channels = file
        .parameters
        .iter()
        .find(|p| p.name == "channel_domains")
        .unwrap();
    assert_eq!(channels.keys.as_deref().unwrap(), CHANNELS);
    assert_eq!(channels.inner_keys.as_deref().unwrap(), DOMAINS);
    assert_eq!(channels.min, Some(0.0));
    let grammar = file
        .parameters
        .iter()
        .find(|p| p.name == "grammar")
        .unwrap();
    let mut fields: Vec<&str> = grammar
        .inner_keys
        .as_ref()
        .unwrap()
        .iter()
        .map(String::as_str)
        .collect();
    fields.sort_unstable();
    let mut expected = GRAMMAR_FIELDS.to_vec();
    expected.sort_unstable();
    assert_eq!(fields, expected);
}

#[test]
fn prepis_cisla_tabulky_a_urovne() {
    let params = overrides(json!({
        "village_openness": 0.2,
        "channel_domains": {"trade": {"power": 2.0}},
        "border_levels": {"open": 1.0, "wall": 0.0},
        "pressure_weights": {"clarity": 2.0},
        "grammar": {"DEFINITE": {"context": 0.4}},
    }))
    .unwrap();
    assert_eq!(params.village_openness, 0.2);
    assert_eq!(params.channel_domains["trade"]["power"], 2.0);
    assert_eq!(params.channel_domains["trade"]["culture"], 3.0);
    assert_eq!(params.border_levels["wall"], 0.0);
    assert!(!params.border_levels.contains_key("normal"));
    assert_eq!(params.pressure_weights["clarity"], 2.0);
    assert_eq!(params.grammar["DEFINITE"]["context"], 0.4);
    assert_eq!(overrides(json!({})).unwrap(), Parameters::default());
}

#[test]
fn chyby_maji_cestu() {
    let error = |value: Value| overrides(value).unwrap_err();
    assert_eq!(
        error(json!({"nesmysl": 1})),
        "parameters.nesmysl: neznámý parametr"
    );
    assert!(error(json!({"village_openness": "x"})).starts_with("parameters.village_openness:"));
    assert!(error(json!({"village_openness": true})).contains("očekáváno číslo"));
    assert!(error(json!({"border_levels": 1})).starts_with("parameters.border_levels:"));
    assert!(error(json!({"border_levels": {"open": "a"}}))
        .starts_with("parameters.border_levels.open:"));
    assert!(error(json!({"policy_levels": {"x": 1}})).starts_with("parameters.policy_levels.x:"));
    assert!(error(json!({"channel_domains": {"nikde": {}}}))
        .starts_with("parameters.channel_domains.nikde:"));
    assert!(error(json!({"channel_domains": {"trade": {"nic": 1.0}}}))
        .starts_with("parameters.channel_domains.trade.nic:"));
    assert!(
        error(json!({"channel_domains": {"trade": {"power": -1.0}}}))
            .starts_with("parameters.channel_domains.trade.power:")
    );
    assert!(error(json!({"grammar": {"DEFINITE": {"nic": 1.0}}}))
        .starts_with("parameters.grammar.DEFINITE.nic:"));
}

#[test]
fn automaticke_svazani_fixovanych_dvojniku() {
    // 1. Přepis aktivních pák sveze fixované dvojníky
    let params = overrides(json!({
        "capital_prestige": 3.5,
        "capital_link_strength": 0.5,
        "analogy_l2_boost": 6.0,
        "restructure_threshold": 0.9,
        "actuation_coherence": 0.6,
    }))
    .unwrap();
    assert_eq!(params.capital_prestige, 3.5);
    assert_eq!(params.background_elite_prestige, 3.5);
    assert_eq!(params.capital_link_strength, 0.5);
    assert_eq!(params.lingua_franca_link, 0.5);
    assert_eq!(params.analogy_l2_boost, 6.0);
    assert_eq!(params.category_loss_l2_boost, 6.0);
    assert_eq!(params.restructure_threshold, 0.9);
    assert_eq!(params.grammar_threshold, 0.9);
    assert_eq!(params.analogy_threshold, 0.9);
    assert_eq!(params.actuation_coherence, 0.6);
    assert_eq!(params.actuation_coherence_other, 0.3);

    // 2. Explicitní přepis fixovaného dvojníka má přednost
    let params_explicit = overrides(json!({
        "capital_prestige": 3.5,
        "background_elite_prestige": 1.5,
        "capital_link_strength": 0.5,
        "lingua_franca_link": 0.2,
        "analogy_l2_boost": 6.0,
        "category_loss_l2_boost": 2.0,
        "restructure_threshold": 0.9,
        "grammar_threshold": 0.75,
        "analogy_threshold": 0.8,
        "actuation_coherence": 0.6,
        "actuation_coherence_other": 0.1,
    }))
    .unwrap();
    assert_eq!(params_explicit.capital_prestige, 3.5);
    assert_eq!(params_explicit.background_elite_prestige, 1.5);
    assert_eq!(params_explicit.capital_link_strength, 0.5);
    assert_eq!(params_explicit.lingua_franca_link, 0.2);
    assert_eq!(params_explicit.analogy_l2_boost, 6.0);
    assert_eq!(params_explicit.category_loss_l2_boost, 2.0);
    assert_eq!(params_explicit.restructure_threshold, 0.9);
    assert_eq!(params_explicit.grammar_threshold, 0.75);
    assert_eq!(params_explicit.analogy_threshold, 0.8);
    assert_eq!(params_explicit.actuation_coherence, 0.6);
    assert_eq!(params_explicit.actuation_coherence_other, 0.1);
}
