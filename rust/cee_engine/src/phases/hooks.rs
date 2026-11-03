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
use crate::phases::StepContext;

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
pub fn follow_vocabulary(
    _ctx: &mut StepContext<'_>,
    _crossings: &[Crossing],
) -> Result<(), String> {
    Ok(())
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
pub fn is_sound_process(_ctx: &StepContext<'_>, _variable: VariableId) -> bool {
    false
}

/// Aktivace zvukového procesu v kódu skupiny. **Vlastník: R1b.**
pub fn activate_process(
    _ctx: &mut StepContext<'_>,
    _group: GroupId,
    _variable: VariableId,
) -> Result<(), String> {
    Ok(())
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
