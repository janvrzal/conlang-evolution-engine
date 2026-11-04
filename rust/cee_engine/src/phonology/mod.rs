//! Fonologie v běžící simulaci (zrcadlo `cee.v2.phonology` a části `changes.sound`).
//!
//! Životní cyklus zvukové změny:
//!
//! 1. **Inovace** (`changes::sound`) vytvoří procesní proměnnou s variantami „žádná změna“
//!    a „změna“ ([`register`]); varianta se šíří jako každá jiná.
//! 2. **Aktivace** ([`activate`]): proces poprvé zasáhl kód (podíl nad `activation_share`),
//!    do jeho fronty se zařadí slova slovní zásoby, kterých se změna týká.
//! 3. **Fonologizace** ([`restructure_groups`]): fronta je seřazená podle logitu sdíleného
//!    podílu, při kterém si slovo změnu zapíše (`prah − náskok frekvence − sklon slova`);
//!    když podíl změny na práh dosáhne, slovo si přepíše podkladový tvar a znovu se
//!    zařadí do front ostatních živých procesů (feeding a bleeding).
//! 4. **Uzavření**: po dvou generacích na 100 % proces přestane být živý.
//!
//! Jádro front a četností užití je `cee_core::code_state`; tady je napojení na model světa:
//! řádky procesů v bance tvarů ([`rows`]), sloupce morfémů a četnosti užití ([`columns`]),
//! index prostředí a opor ([`index`]) a samotné kroky ([`queues`]).
//!
//! **Co z toho je odvozené.** Všechno v `state::sound::Runtime` (index, sklony slov, řádky
//! procesů, sloupce) je čistá funkce stavu světa a po kopii či obnově se postaví znovu.
//! Fronty kódů se ukládají.
//!
//! **Pro ostatní oblasti.** `requeue_all` zařadí morfém, jehož tvar se změnil (analogie),
//! do front živých procesů (R1c); `row_of` dá řádek procesu v bance pro hodnocení tlaků
//! (R1a); `changed_share` je podíl změněné varianty ve skupině.

pub mod columns;
pub mod index;
pub mod queues;
pub mod rows;

pub use queues::{activate, enter_units, leave_vocabulary, requeue_all, restructure_groups};
pub use rows::{changed_share, register, row_of, Registered};
