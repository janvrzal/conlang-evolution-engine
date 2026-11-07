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
pub fn phonology(ctx: &mut StepContext<'_>, groups: &[GroupId]) -> Result<(), String> {
    crate::phonology::restructure_groups(ctx, groups)
}

/// Analogické přestavby tvarů skupiny (R1c).
pub fn morphology(ctx: &mut StepContext<'_>, group: GroupId) -> Result<(), String> {
    crate::morphology::restructure(ctx, group)
}

/// Zapsání nových koncovek a konstrukcí skupiny (R1c).
pub fn syntax(ctx: &mut StepContext<'_>, group: GroupId) -> Result<(), String> {
    crate::syntax::restructure(ctx, group)
}

/// Posun přízvuku skupiny (R1c).
pub fn prosody(ctx: &mut StepContext<'_>, group: GroupId) -> Result<(), String> {
    crate::prosody::restructure(ctx, group)
}

/// Spustí všechny podfáze přestaveb v pořadí kroku.
pub fn run(ctx: &mut StepContext<'_>) -> Result<(), String> {
    let groups: Vec<GroupId> = ctx
        .world
        .group_ids()
        .into_iter()
        .filter(|g| !ctx.world.groups.written[g.index()])
        .collect();
    {
        let _t = crate::timing::scope("rebuild/phonology");
        phonology(ctx, &groups)?;
    }
    {
        let _t = crate::timing::scope("rebuild/release");
        release_tables(ctx.world);
        if ctx.tick.is_multiple_of(RETAIN_EVERY) {
            retain_forms(ctx.world);
        }
    }
    for group in groups {
        {
            let _t = crate::timing::scope("rebuild/morphology");
            morphology(ctx, group)?;
        }
        {
            let _t = crate::timing::scope("rebuild/syntax");
            syntax(ctx, group)?;
        }
        {
            let _t = crate::timing::scope("rebuild/prosody");
            prosody(ctx, group)?;
        }
    }
    Ok(())
}

/// Uvolní z banky tabulky výsledků procesů, které nežijí v žádné skupině (uzavřené všude).
/// Jsou to keše, se kterými se už nepracuje; kdyby se proces znovu rozběhl, dopočítají se.
fn release_tables(world: &mut crate::world::World) {
    let rows = world.bank.bank.proc_count();
    let mut keep = vec![false; rows];
    for group in world.group_ids() {
        for code in &world.groups.codes[group.index()] {
            for proc in &code.phonology.sound.queues.state.procs {
                if !proc.live {
                    continue;
                }
                for row in [proc.own_row, proc.row].into_iter().flatten() {
                    if row < rows {
                        keep[row] = true;
                    }
                }
            }
        }
    }
    world.bank.bank.release_tables(&keep);
}

/// Po kolika krocích se z tabulek výsledků vyřadí zastaralé tvary.
const RETAIN_EVERY: u32 = 8;

/// Vyřadí z tabulek výsledků procesů tvary, které už žádný kód nepoužívá (podkladové tvary
/// kódů a výchozí tvary morfémů jsou živé, ostatní jsou zastaralé podoby slov).
fn retain_forms(world: &mut crate::world::World) {
    let count = world.bank.bank.len();
    let mut alive = vec![false; count];
    let mut mark = |form: i32| {
        if form >= 0 && (form as usize) < count {
            alive[form as usize] = true;
        }
    };
    for &form in &world.sound.runtime.columns.default_form {
        mark(form);
    }
    for group in world.group_ids() {
        for code in &world.groups.codes[group.index()] {
            let (forms, _, _) = code.forms.raw();
            for &form in forms {
                mark(form);
            }
        }
    }
    world.bank.bank.retain_forms(&alive);
}
