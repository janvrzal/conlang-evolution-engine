//! Jádro enginu CEE v2 v Rustu.
//!
//! Čistá logika (``bank``, ``process``, ``phonology``) nezná Python; vazba na něj je
//! v ``python.rs`` a sestavuje se jen s vlastností ``python``.

pub mod assess;
pub mod assess_index;
pub mod bank;
pub mod clarity;
pub mod code_state;
pub mod index;
pub mod morphology_index;
pub mod phonology;
pub mod pools;
pub mod pressures;
pub mod process;
pub mod semantic_index;
pub mod sites;
pub mod support;
pub mod transmission;

#[cfg(feature = "python")]
mod code_state_python;
#[cfg(feature = "python")]
mod index_python;
#[cfg(feature = "python")]
mod pressures_python;
#[cfg(feature = "python")]
mod python;
#[cfg(feature = "python")]
mod python_pools;
#[cfg(feature = "python")]
mod sites_python;

/// Verze rozhraní mezi Pythonem a Rustem. Python rozšíření nepoužije, když se
/// číslo liší od toho, které čeká (jiný worktree, starší sestavení).
pub const INTERFACE_VERSION: u32 = 12;
