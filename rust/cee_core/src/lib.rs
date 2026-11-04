//! Jádro enginu CEE v2 v Rustu.
//!
//! Čistá logika bez závislostí: banka tvarů (`bank`), procesy (`process`, `phonology`), přenos
//! (`transmission`, `pools`), tlaky (`pressures`) a indexy (`index`, `assess`). Používá je
//! `cee_engine`; vazba na Python už neexistuje (server volá `cee_py` nad `cee_engine`).

pub mod assess;
pub mod assess_index;
pub mod bank;
pub mod candidates;
pub mod code_state;
pub mod form_assess;
pub mod form_restructure;
pub mod index;
pub mod morphology_index;
pub mod observe;
pub mod phonology;
pub mod pools;
pub mod pressures;
pub mod process;
pub mod transmission;
