//! Index prostředí a opor zvukových změn nad kódy skupin (`cee_core::index::SoundIndex`).
//!
//! Index drží pro každou skupinu počty prostředí hlásek ve slovní zásobě a opory všech
//! kandidátů; míry rodin a místa z nich čtou změny (`changes::sound`). Dorovnání je
//! diferenční (přepočítají se jen morfémy, jejichž tvar se změnil), a protože se u skupiny
//! zapamatuje stav kódu, ze kterého byl počítán, další dotaz v témže stavu nestojí nic.

use cee_core::candidates::{self, SegTable};
use cee_core::index::{GroupInput, SoundIndex};

use crate::changes::sound::scales;
use crate::ids::GroupId;
use crate::segments::SegmentTable;
use crate::state::sound::{IndexState, Stamp};
use crate::world::World;

/// Snímek tabulky hlásek pro stavbu kandidátů; tabulka je vložená data, snímek se staví jednou.
pub fn snapshot() -> &'static SegTable {
    static SNAPSHOT: std::sync::OnceLock<SegTable> = std::sync::OnceLock::new();
    SNAPSHOT.get_or_init(|| {
        let table = SegmentTable::default_table();
        let count = table.len();
        let tone = (0..count)
            .map(|segment| table.tone_of(segment as i32) as i32)
            .collect();
        let canon = (0..count)
            .map(|segment| table.id_of(&table.ipa[segment]).unwrap_or(-1))
            .collect();
        let symbols: Vec<i64> = candidates::symbol_list()
            .iter()
            .map(|symbol| table.id_of(symbol).map_or(-1, i64::from))
            .collect();
        SegTable::new(
            table.features.clone(),
            table.vectors().to_vec(),
            table.ipa.clone(),
            table.vowel.clone(),
            tone,
            canon,
            &symbols,
            table.tone_symbols(),
        )
        .expect("snímek tabulky hlásek")
    })
}

/// Stav kódu skupiny, pro který platí dorovnání indexu.
fn stamp_of(world: &World, group: GroupId) -> Stamp {
    let code = world.groups.main_code(group);
    let state = &code.phonology;
    (
        state.version,
        code.forms.version,
        state.vocabulary_log.len(),
        world.morphemes.len(),
        code.stress_rule.as_rule(),
    )
}

/// Dorovná index na stav kódu skupiny, pokud se změnil, a předá ho funkci `read`
/// (index a číslo skupiny v něm). Index je za zámkem: souběžné dotazy skupin se řadí
/// za sebe, výsledek na pořadí nezávisí (opory jsou celá čísla).
pub fn with_group<R>(
    world: &World,
    group: GroupId,
    read: impl FnOnce(&SoundIndex, i64) -> R,
) -> Result<R, String> {
    let stamp = stamp_of(world, group);
    let mut guard = world
        .sound
        .runtime
        .index
        .lock()
        .map_err(|_| "zámek indexu zvukových změn je poškozený".to_owned())?;
    let IndexState { index, synced } = &mut *guard;
    let index = index.get_or_insert_with(|| {
        let mut index = SoundIndex::new(scales());
        index.set_table(snapshot().clone());
        index
    });
    let at = group.index();
    if synced.len() <= at {
        synced.resize(at + 1, None);
    }
    let token = i64::from(group.0);
    if synced[at] != Some(stamp) {
        let code = world.groups.main_code(group);
        let count = world.morphemes.len();
        let mut flags = vec![0_u8; count];
        let mut forms = vec![-1_i32; count];
        for member in code.phonology.vocabulary.iter() {
            let number = member.index();
            if number >= count {
                continue;
            }
            flags[number] = 1;
            let own = code.forms.form_id(member);
            forms[number] = if own >= 0 {
                own
            } else {
                world.morphemes.form[number] as i32
            };
        }
        let needs = index.sync(
            &world.bank.bank,
            &[GroupInput {
                token,
                rule: code.stress_rule.as_rule(),
                flags: &flags,
                forms: &forms,
            }],
        )?;
        if !needs.is_empty() {
            return Err(format!(
                "index zvukových změn si vyžádal údaje, které svět má mít v bance: {needs:?}"
            ));
        }
        synced[at] = Some(stamp);
    }
    Ok(read(index, token))
}
