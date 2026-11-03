//! Stav jednotlivých oblastí enginu, které si R1 agenti plní každý sám.
//!
//! `World` a `Code` nesou pro každou oblast jednu strukturu s `Default`,
//! `Clone` a `serde`. Agent R1 přidává pole **jen do své struktury** (a do
//! svého souboru), takže souběžné větve se nedotknou společného datového modelu.
//!
//! | struktura | soubor | agent | obsah |
//! |---|---|---|---|
//! | [`transfer::TransferState`] | `transfer.rs` | R1a | keše přenosu a tlaků, skladové pomocné stavy |
//! | [`sound::SoundWorldState`], [`sound::SoundCodeState`] | `sound.rs` | R1b | fronty fonologizace, index prostředí, hodnocení procesů |
//! | [`grammar::GrammarWorldState`], [`grammar::GrammarCodeState`] | `grammar.rs` | R1c | index míst změn, živé morfologické změny, nové koncovky |
//! | [`society::SocietyState`] | `society.rs` | R1d | státy, normy, hranice, obchod, deník změn, sledování linií |

pub mod grammar;
pub mod society;
pub mod sound;
pub mod transfer;
