//! Fáze 4: přestavby podkladových tvarů po přenosu (R1b a R1c).
//!
//! Po přenosu skupina přepíše podkladové tvary slov podle toho, co se v jejím jazyce
//! ustálilo. Čtyři podfáze, každá s vlastním souborem agenta:
//!
//! | podfáze | funkce | čte | zapisuje | agent |
//! |---|---|---|---|---|
//! | fonologie | [`phonology`] | fronty fonologizace kódu, banka tvarů, procesy | `Code.forms`, slovní zásoba, historie (`restructured`, …) | R1b |
//! | morfologie | [`morphology`] | živé analogie (`GrammarCodeState`), paradigmata | tvary buněk, historie | R1c |
//! | syntax | [`syntax`] | konstrukční proměnné, hotové konstrukce | nové koncovky, historie | R1c |
//! | prozodie | [`prosody`] | rozdělení pravidel přízvuku | `Code.stress_rule`, historie | R1c |
//!
//! Pořadí v kroku: fonologie všech skupin naráz, potom po skupinách morfologie, syntax
//! a prozodie (záznamy se řadí po skupinách). R0 dodává jen prázdné funkce.

use crate::ids::GroupId;
use crate::phases::StepContext;

/// Fonologizace skupin (R1b).
pub fn phonology(_ctx: &mut StepContext<'_>, _groups: &[GroupId]) -> Result<(), String> {
    Ok(()) // TODO(R1b)
}

/// Analogické přestavby tvarů skupiny (R1c).
pub fn morphology(_ctx: &mut StepContext<'_>, _group: GroupId) -> Result<(), String> {
    Ok(()) // TODO(R1c)
}

/// Zapsání nových koncovek a konstrukcí skupiny (R1c).
pub fn syntax(_ctx: &mut StepContext<'_>, _group: GroupId) -> Result<(), String> {
    Ok(()) // TODO(R1c)
}

/// Posun přízvuku skupiny (R1c).
pub fn prosody(_ctx: &mut StepContext<'_>, _group: GroupId) -> Result<(), String> {
    Ok(()) // TODO(R1c)
}

/// Spustí všechny podfáze přestaveb v pořadí kroku.
pub fn run(ctx: &mut StepContext<'_>) -> Result<(), String> {
    let groups: Vec<GroupId> =
        ctx.world.group_ids().into_iter().filter(|g| !ctx.world.groups.written[g.index()]).collect();
    phonology(ctx, &groups)?;
    for group in groups {
        morphology(ctx, group)?;
        syntax(ctx, group)?;
        prosody(ctx, group)?;
    }
    Ok(())
}
