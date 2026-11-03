//! Jádro enginu CEE v2 v Rustu.
//!
//! Čistá logika (``bank``, ``process``, ``phonology``) nezná Python; vazba na něj je
//! v ``python.rs`` a sestavuje se jen s vlastností ``python``.

pub mod assess;
pub mod bank;
pub mod phonology;
pub mod pools;
pub mod process;
pub mod support;
pub mod transmission;

#[cfg(feature = "python")]
mod python;
#[cfg(feature = "python")]
mod python_pools;

/// Verze rozhraní mezi Pythonem a Rustem. Python rozšíření nepoužije, když se
/// číslo liší od toho, které čeká (jiný worktree, starší sestavení).
pub const INTERFACE_VERSION: u32 = 4;
