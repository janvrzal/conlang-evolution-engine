//! Prozodie v běžící simulaci (zrcadlo `cee.v2.prosody`).
//!
//! Sleduje prozodické proměnné skupin:
//!
//! - `prosody:stress_rule`: pravidlo pozice přízvuku (WALS 14A),
//! - `prosody:stress_strength`: síla přízvuku (`weak` / `strong`).
//!
//! Změna převládající varianty zapíše vlastnost do kódu a zneplatní odvozené pohledy
//! (verze kódu a tvarů, podle nichž si fonologie hlídá keše).

use serde_json::json;

use crate::ids::{GroupId, VariableId};
use crate::model::code::{StressRule, StressStrength};
use crate::model::repertoire::{variable_name, VariableKind};
use crate::phases::StepContext;
use crate::world::World;

/// Podíl, od kterého převládající hodnota mění vlastnost kódu (`phases.stress_updates`).
const THRESHOLD: f64 = 0.5;

/// Proměnná pravidla přízvuku, pokud ji svět sleduje.
pub fn stress_rule_variable(world: &World) -> Option<VariableId> {
    prosody_variable(world, "stress_rule")
}

/// Proměnná síly přízvuku, pokud ji svět sleduje.
pub fn stress_strength_variable(world: &World) -> Option<VariableId> {
    prosody_variable(world, "stress_strength")
}

fn prosody_variable(world: &World, key: &str) -> Option<VariableId> {
    world
        .registry
        .variables
        .get(&variable_name(VariableKind::Prosody, key))
        .filter(|&n| (n as usize) < world.variables.len())
        .map(VariableId)
}

fn payload_text(world: &World, variable: VariableId, group: GroupId) -> Option<(String, f64)> {
    let (variant, share) = world.dominant(group, variable)?;
    match &world.variants.payload[variant.index()] {
        crate::model::repertoire::Payload::StressRule(value)
        | crate::model::repertoire::Payload::StressStrength(value) => {
            Some((value.clone(), share))
        }
        _ => None,
    }
}

/// Převládající pravidlo přízvuku skupiny (bez proměnné platí vlastnost kódu).
pub fn dominant_rule(world: &World, group: GroupId) -> StressRule {
    stress_rule_variable(world)
        .and_then(|v| payload_text(world, v, group))
        .and_then(|(value, _)| StressRule::parse(&value))
        .unwrap_or(world.groups.main_code(group).stress_rule)
}

/// Převládající síla přízvuku skupiny.
pub fn dominant_strength(world: &World, group: GroupId) -> StressStrength {
    stress_strength_variable(world)
        .and_then(|v| payload_text(world, v, group))
        .and_then(|(value, _)| StressStrength::parse(&value))
        .unwrap_or(world.groups.main_code(group).stress_strength)
}

/// Nové pravidlo a nová síla přízvuku skupiny (`None` = beze změny).
pub type StressPlan = (Option<StressRule>, Option<StressStrength>);

/// Změní se pravidlo nebo síla přízvuku skupiny? Čte jen rozdělení prozodických proměnných
/// a dnešní vlastnosti kódu (`prosody.plan`).
pub fn plan(world: &World, group: GroupId) -> Option<StressPlan> {
    let code = world.groups.main_code(group);
    let rule = stress_rule_variable(world)
        .and_then(|v| payload_text(world, v, group))
        .filter(|(_, share)| *share >= THRESHOLD)
        .and_then(|(value, _)| StressRule::parse(&value))
        .filter(|&r| r != code.stress_rule);
    let strength = stress_strength_variable(world)
        .and_then(|v| payload_text(world, v, group))
        .filter(|(_, share)| *share >= THRESHOLD)
        .and_then(|(value, _)| StressStrength::parse(&value))
        .filter(|&s| s != code.stress_strength);
    (rule.is_some() || strength.is_some()).then_some((rule, strength))
}

/// Převládající pravidlo a síla přízvuku se zapíšou do kódu (`prosody.restructure`).
pub fn restructure(ctx: &mut StepContext<'_>, group: GroupId) -> Result<(), String> {
    let Some((new_rule, new_strength)) = plan(ctx.world, group) else {
        return Ok(());
    };
    let group_name = ctx.world.group_name(group).to_owned();
    if let Some(rule) = new_rule {
        let code = ctx.world.groups.main_code_mut(group);
        let old = code.stress_rule;
        code.stress_rule = rule;
        code.phonology.version += 1;
        code.phonology.grammar.cache.clear();
        // Náhrada za `forms.token = next_token()`: zneplatní indexy odvozené z tvarů kódu.
        code.forms.version += 1;
        ctx.history.record(
            "stress_rule_changed",
            ctx.tick,
            ctx.year,
            json!({"group": group_name, "old": old.name(), "new": rule.name()}),
        );
    }
    if let Some(strength) = new_strength {
        let code = ctx.world.groups.main_code_mut(group);
        let old = code.stress_strength;
        code.stress_strength = strength;
        ctx.history.record(
            "stress_strength_changed",
            ctx.tick,
            ctx.year,
            json!({"group": group_name, "old": old.name(), "new": strength.name()}),
        );
    }
    Ok(())
}
