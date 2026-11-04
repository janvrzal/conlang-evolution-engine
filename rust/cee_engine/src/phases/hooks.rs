//! Smluvené body mezi fázemi, které plní různí agenti R1 souběžně.
//!
//! Přenos (R1a) po zápisu nových podílů zjistí, co se v kterém kódu změnilo, a předá to
//! sem; samotné důsledky (slovní zásoba, fronty fonologizace, analogie, přejetí cizího
//! tvaru) patří jiným oblastem. Podpisy a typy tady jsou pevné: vlastník funkce mění
//! **jen její tělo**, volající na ni spoléhá. Kdo potřebuje změnu podpisu, popíše ji ve
//! zprávě a sloučí ji hlavní agent.
//!
//! Pořadí volání v kroku je stejné jako v Pythonu (`simulation._transmit`):
//! 1. pro každý blok: [`record_grammar`] pro konstrukce, které se ve skupině změnily,
//!    a [`follow_vocabulary`] pro přechody prahu dominance slov;
//! 2. [`activate`] pro dvojice (skupina, proměnná) nad prahem aktivace, seřazené podle
//!    (ID skupiny, ID proměnné);
//! 3. uvolnění ustálených proměnných do repertoárů (`transmission::release`);
//! 4. fáze přestaveb (`rebuild`).

use crate::ids::{GroupId, MorphemeId, VariableId};
use crate::model::repertoire::VariableKind;
use crate::phases::StepContext;
use crate::phonology;
use crate::vocabulary::units_of;

/// Přechod prahu dominance slova v jedné skupině (`simulation._follow_vocabulary`).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Crossing {
    pub group: GroupId,
    /// Lexikální proměnná (pojem).
    pub variable: VariableId,
    /// Kořen varianty, která práh překročila.
    pub morpheme: MorphemeId,
    /// `true` = slovo se stalo dominantním, `false` = přestalo být.
    pub enter: bool,
}

/// Slovní zásoba po přenosu: dominantní kořeny, počty užití, vstup tvarů do fonologie
/// a zařazení do front živých procesů. Přechody jsou v pořadí, v jakém je Python
/// zpracuje (nejdřív všechny odchody, potom příchody).
///
/// **Vlastník: R1b.** Pro slovo, které poprvé vstupuje do kódu, volá [`adopt`].
pub fn follow_vocabulary(ctx: &mut StepContext<'_>, crossings: &[Crossing]) -> Result<(), String> {
    // Nejdřív odchody, potom příchody: kořen, který jeden pojem opouští a druhý (posunem)
    // přebírá, tak ze slovní zásoby na okamžik nevypadne.
    for enter in [false, true] {
        for crossing in crossings.iter().filter(|c| c.enter == enter) {
            follow_one(ctx, crossing)?;
        }
    }
    Ok(())
}

fn follow_one(ctx: &mut StepContext<'_>, crossing: &Crossing) -> Result<(), String> {
    let Crossing {
        group,
        variable,
        morpheme,
        enter,
    } = *crossing;
    if morpheme.is_none() {
        return Ok(());
    }
    let concept = ctx.world.variables.concept[variable.index()];
    {
        let state = &mut ctx.world.groups.main_code_mut(group).phonology;
        state.version += 1;
        state.lexicon_version += 1;
        if enter {
            state.set_dominant(concept, morpheme);
            if state.adjust_uses(morpheme, 1, 0) > 1 {
                return Ok(());
            }
        } else {
            if state.dominant_of(concept) == morpheme {
                state.set_dominant(concept, MorphemeId::NONE);
            }
            if state.adjust_uses(morpheme, -1, 1) > 0 {
                return Ok(());
            }
        }
    }
    if enter {
        adopt(ctx, group, morpheme)?;
    }
    let units = units_of(ctx.world, morpheme);
    if enter {
        phonology::enter_units(ctx.world, group, &units)
    } else {
        for unit in units {
            phonology::leave_vocabulary(ctx.world, group, unit);
        }
        Ok(())
    }
}

/// Cizí kořen vstupuje do slovní zásoby skupiny: převzetí a adaptace tvaru
/// (`contact.adopt`). **Vlastník: R1d** (kontakt).
pub fn adopt(
    _ctx: &mut StepContext<'_>,
    _group: GroupId,
    _morpheme: MorphemeId,
) -> Result<(), String> {
    Ok(())
}

/// Proces nebo analogie překročila ve skupině práh aktivace a začne působit.
/// Zvukový proces (`phonology.activate`) patří **R1b**, analogie a změna tvaru
/// (`morphology.activate`) **R1c**; rozcestí podle druhu proměnné je tady.
pub fn activate(
    ctx: &mut StepContext<'_>,
    group: GroupId,
    variable: VariableId,
) -> Result<(), String> {
    if is_sound_process(ctx, variable) {
        activate_process(ctx, group, variable)
    } else {
        activate_analogy(ctx, group, variable)
    }
}

/// Je proměnná zvukový proces (ne změna tvaru)? **Vlastník: R1b.**
pub fn is_sound_process(ctx: &StepContext<'_>, variable: VariableId) -> bool {
    ctx.world.variables.kind.get(variable.index()) == Some(&VariableKind::Process)
}

/// Aktivace zvukového procesu v kódu skupiny. **Vlastník: R1b.**
pub fn activate_process(
    ctx: &mut StepContext<'_>,
    group: GroupId,
    variable: VariableId,
) -> Result<(), String> {
    let process = ctx.world.variables.process[variable.index()];
    if process.is_none() {
        return Err(format!(
            "procesní proměnná {} nemá číslo procesu",
            ctx.world.registry.variables.name(variable.0)
        ));
    }
    phonology::activate(ctx.world, group, process)
}

/// Aktivace analogie nebo jiné změny tvaru v kódu skupiny. **Vlastník: R1c.**
pub fn activate_analogy(
    _ctx: &mut StepContext<'_>,
    _group: GroupId,
    _variable: VariableId,
) -> Result<(), String> {
    Ok(())
}

/// Rozdělení konstrukční proměnné se ve skupině změnilo (`record_grammar`), vstup
/// syntaktické přestavby. **Vlastník: R1c.**
pub fn record_grammar(
    _ctx: &mut StepContext<'_>,
    _group: GroupId,
    _variable: VariableId,
) -> Result<(), String> {
    Ok(())
}
