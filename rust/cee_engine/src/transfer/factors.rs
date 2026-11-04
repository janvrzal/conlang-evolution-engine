//! Faktory kanálů po proměnných bloku: filtr přenositelnosti pro vazby mezi jazyky
//! (`contact.borrowing_factors`), interferenci prvního jazyka, čtení, školu a liturgii
//! (`institutions.*_factors`). Faktor závisí jen na druhu proměnné, u slov na frekvenci
//! a doméně pojmu; počítá se jednou za blok a krok.

use crate::model::pools::PoolBlock;
use crate::model::repertoire::VariableKind;
use crate::transfer::network::{FlowChannel, SideKind, StepInputs};
use crate::world::World;

/// Indexy kanálů v tabulce domén (`parameters::CHANNELS`).
fn channel_index(name: &str) -> usize {
    crate::parameters::CHANNELS
        .iter()
        .position(|&c| c == name)
        .expect("známý kanál")
}

/// Faktory všech kanálů pro řádky bloku: po vazbách mezi jazyky (v pořadí `StepInputs::cross`)
/// a po kanálech mimo síť (v pořadí `StepInputs::sides`).
pub struct BlockFactors {
    pub flows: Vec<Vec<f64>>,
    pub sides: Vec<Vec<f64>>,
}

/// Váha pojmu při přenosu slova z cizího kódu (`contact.transfer`), bez kanálu a domény.
fn transfer_weight(world: &World, inputs: &StepInputs, concept: crate::ids::ConceptId) -> f64 {
    let rarity = 1.0 - world.concept_frequency(concept);
    let strength = world.params.borrowability_strength;
    if strength == 0.0 {
        return rarity;
    }
    let (reference, normalizer) = inputs.borrowing_scale;
    let borrowed = world
        .concepts
        .borrowed
        .get(concept.index())
        .copied()
        .unwrap_or(reference)
        .max(0.01);
    let mut weight = (borrowed / reference).powf(strength);
    if strength < 1.0 {
        weight *= rarity.powf(1.0 - strength);
    }
    weight / normalizer
}

/// Váha domény pojmu v kanálu; 1 u proměnných, které nejsou slova.
fn domain_weight(
    world: &World,
    inputs: &StepInputs,
    channel: usize,
    concept: crate::ids::ConceptId,
) -> f64 {
    let domain = world
        .concepts
        .domain
        .get(concept.index())
        .copied()
        .unwrap_or(0) as usize;
    inputs.domains[channel][domain]
}

pub fn block_factors(world: &World, inputs: &StepInputs, block: &PoolBlock) -> BlockFactors {
    let params = &world.params;
    let rows = block.len();
    let variables = &world.variables;
    let mut kinds = Vec::with_capacity(rows);
    for &variable in &block.variables {
        kinds.push((
            variables.kind[variable.index()],
            variables.concept[variable.index()],
        ));
    }
    let flows = inputs
        .cross
        .iter()
        .map(|flow| {
            let channel = match flow.channel {
                FlowChannel::Neighbor => 0,
                FlowChannel::Elite => 1,
                FlowChannel::Trade => 2,
            };
            kinds
                .iter()
                .map(|&(kind, concept)| match kind {
                    VariableKind::Lexical => {
                        let mut factor = 0.5 * transfer_weight(world, inputs, concept);
                        let weight = domain_weight(world, inputs, channel, concept);
                        if weight != 1.0 {
                            factor *= weight;
                        }
                        factor
                    }
                    VariableKind::Process | VariableKind::Construction => 0.1,
                    VariableKind::Form | VariableKind::Prosody => 0.0,
                })
                .collect()
        })
        .collect();
    let sides = inputs
        .sides
        .iter()
        .map(|side| {
            kinds
                .iter()
                .map(|&(kind, concept)| match side.kind {
                    SideKind::Interference => match kind {
                        VariableKind::Lexical => 0.05,
                        VariableKind::Process | VariableKind::Construction => 1.0,
                        VariableKind::Form | VariableKind::Prosody => 0.0,
                    },
                    SideKind::Reading => {
                        if kind != VariableKind::Lexical {
                            return 0.0;
                        }
                        let frequency = world.concept_frequency(concept);
                        let mut factor = 1.0 - params.reading_core_resistance * frequency;
                        let weight =
                            domain_weight(world, inputs, channel_index("reading"), concept);
                        if weight != 1.0 {
                            factor *= weight;
                        }
                        factor
                    }
                    SideKind::School => {
                        let mut factor = match kind {
                            VariableKind::Lexical
                            | VariableKind::Construction
                            | VariableKind::Form => 1.0,
                            VariableKind::Process => 0.1,
                            VariableKind::Prosody => 0.0,
                        };
                        if kind == VariableKind::Lexical {
                            let weight =
                                domain_weight(world, inputs, channel_index("school"), concept);
                            if weight != 1.0 {
                                factor *= weight;
                            }
                        }
                        factor
                    }
                    SideKind::Liturgy => {
                        if kind != VariableKind::Lexical {
                            return 0.0;
                        }
                        let factor = 1.0 - world.concept_frequency(concept);
                        let weight =
                            domain_weight(world, inputs, channel_index("liturgy"), concept);
                        if weight == 1.0 {
                            factor
                        } else {
                            factor * weight
                        }
                    }
                })
                .collect()
        })
        .collect();
    BlockFactors { flows, sides }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn kanaly_maji_pevne_indexy() {
        assert_eq!(channel_index("neighbor"), 0);
        assert_eq!(channel_index("school"), 5);
    }
}
