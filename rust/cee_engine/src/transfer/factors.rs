//! Faktory kanálů po proměnných bloku: filtr přenositelnosti pro vazby mezi jazyky
//! (`contact.borrowing_factors`), interferenci prvního jazyka, čtení, školu a liturgii
//! (`institutions.*_factors`). Faktor závisí jen na druhu proměnné, u slov na frekvenci
//! a doméně pojmu; počítá se jednou za blok a krok.

use crate::contact;
use crate::model::pools::PoolBlock;
use crate::model::repertoire::VariableKind;
use crate::transfer::network::{FlowChannel, SideKind, StepInputs};
use crate::world::World;

/// Faktory všech kanálů pro řádky bloku: po vazbách mezi jazyky (v pořadí `StepInputs::cross`)
/// a po kanálech mimo síť (v pořadí `StepInputs::sides`).
pub struct BlockFactors {
    pub flows: Vec<Vec<f64>>,
    pub sides: Vec<Vec<f64>>,
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
                FlowChannel::Neighbor => contact::NEIGHBOR,
                FlowChannel::Elite => contact::ELITE,
                FlowChannel::Trade => contact::TRADE,
            };
            // Filtr výpůjček podle rozhraní kontaktu (R1d).
            block
                .variables
                .iter()
                .map(|&variable| inputs.borrow.factor(world, variable, channel))
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
                    SideKind::Interference => contact::interference_factor(kind),
                    SideKind::Reading => {
                        if kind != VariableKind::Lexical {
                            return 0.0;
                        }
                        let frequency = world.concept_frequency(concept);
                        let mut factor = 1.0 - params.reading_core_resistance * frequency;
                        let weight = inputs.borrow.domain(contact::READING, concept);
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
                            let weight = inputs.borrow.domain(contact::SCHOOL, concept);
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
                        let weight = inputs.borrow.domain(contact::LITURGY, concept);
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
