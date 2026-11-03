//! Jádro enginu CEE v2 v Rustu.
//!
//! Čistá logika (``bank``, ``process``, ``phonology``) nezná Python; vazba na něj je
//! v ``python.rs`` a sestavuje se jen s vlastností ``python``.

pub mod assess;
pub mod bank;
pub mod index;
pub mod phonology;
pub mod process;
pub mod support;

#[cfg(feature = "python")]
mod index_python;
#[cfg(feature = "python")]
mod python;

/// Verze rozhraní mezi Pythonem a Rustem. Python rozšíření nepoužije, když se
/// číslo liší od toho, které čeká (jiný worktree, starší sestavení).
pub const INTERFACE_VERSION: u32 = 5;
