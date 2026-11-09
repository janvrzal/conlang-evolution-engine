# 36. Data běhu pro UI a ukládání běhů do souborů

Stav: **zapsáno na větvi `export-data`** (9. 11. 2026).

Podnět: seznam z UI („Data, která engine nedává“) a „Udělej ta data a ukládání běhů“;
o databázi rozhodl uživatel: „Ano, soubory“.

## Data v exportu (`export::export`)

| pole | co nese |
|---|---|
| `proto_lexicon` | slovník protojazyků na startu: jazyk popisu → `{group, forms: {pojem: IPA}}` (`History::proto`, počítá `Simulation::new`) |
| `lexicon_by_language` | dnešní slovník každého pozorovaného jazyka (linie posledního snímku) podle největší domácí skupiny |
| `change_history` | po jazycích: zvukové změny (`kind: sound`: rodina, cíl, operace, rysy, okolí, rok, vesnice s rokem ustálení, rokem uzavření a relikty) a analogie (`kind: analogy`: proměnná, operace, pojem, buňka, vesnice s rokem); skupiny, které už nežijí, jsou pod `language: null` |
| událost `study_case` | studijní případ na časové ose: `label`, `event_kind`, `spec_event` (pořadí v zadání) |

Slovník v čase (každý snímek pozorování, tj. po 100 letech) nejde do exportu ani do snímků
(byl by stovky MB); ukládá se do souboru běhu jen jako změny tvarů (níže).

## Zadání

- `events[].study_case`: volitelný štítek („Lingua franca v přístavu“). U události po
  regionech (`settlement`, `elite`) nese štítek první událost enginu.
- Hlášky `spec::check` mají `code` (stálý kód: `tone_unknown`, `concept_unknown`,
  `word_unknown_segment`, `word_rewritten`, `event_year_outside`, `event_kind_unknown`,
  `event_field_invalid`, `event_failed`, `event_language_later`, `semantics_off`,
  `parameter_invalid`, `concept_invalid`, `vocabulary_invalid`, `vocabulary_warning`,
  `world_invalid`, `world_failed`, `background_unknown`, `tones_repeated`, `syllables_unknown`,
  `word_empty`) a `args` (dosazované hodnoty). `message` zůstává česky jako výchozí text.
  Zprávy, které engine skládá hluboko (selhání události), mají jen obecný kód s druhem události.

## „Co kdyby“ z kontrolního bodu

- `spec::branch_year(původní, změněné)`: rok, od kterého se zadání liší. Liší-li se cokoli mimo
  události (regiony, jazyky, parametry, semínko), `None` = počítat od začátku.
- `spec::resume(zadání, kontrolní bod, config)`: svět a historie z bodu, události ze zadání po
  roku bodu. Bez změny dá pokračování **stejný běh** jako výpočet od začátku (otisk historie);
  se změnou stejný běh jako změněný svět od začátku (test `co_kdyby_z_kontrolniho_bodu`).
- `CHECKPOINT_VERSION` 2 (historie nese protojazyk).

## Běhy v souborech (`cee_store`)

Projekt `svet.cee.json` má běhy ve složce `svet.cee.behy/`, každý v podsložce pojmenované
časem spuštění (UTC, `20261109-153012`):

```text
beh.json                 stav, rok, doba, rodič a rok větvení, počet snímků, proces
zadani.json              zadání, ze kterého běh vznikl
snimky.jsonl.gz          snímky (export::frame), řádek po řádku
slovnik.jsonl.gz         slovník v čase: řádek = rok + jazyk + skupina + změněné tvary (null = zmizel)
vysledek.json.gz         výsledek (export), u hotového běhu
body/t00040_y300.bin.gz  kontrolní body (po 100 letech)
```

- Zápis do `.jsonl.gz` je samostatný člen gzipu připsaný na konec: pád nechá zapsané čitelné
  (useknutý konec se zahodí). `beh.json` a výsledek jdou přes dočasný soubor a přejmenování.
- `running` po jiném procesu se čte jako `interrupted`.
- Čtení: `list`, `info`, `spec`, `result`, `frames(since)`, `lexicon(jazyk, rok)`,
  `lexicon_years`, `word_history(jazyk, pojem)`, `checkpoint_before(rok)`, `size`; úpravy
  `rename`, `delete`, `drop_checkpoints`.
- Zápis: `RunWriter::create`, `Recorder` (po kroku `collect` → `Batch::write`), `copy_prefix`
  (co kdyby převezme snímky, slovník a body rodiče do roku bodu), `finish`.
- Slovník protojazyka leží v roce začátku pod jménem jazyka popisu; od prvního pozorování
  pod jmény linií (strom linií v exportu je spojuje).

Databázi (SQLite) jsme zvážili a nechali: běhů na projekt je pár, slovník v čase má jednotky
MB a soubory jdou poslat se světem.

## Ověření

- `cargo test --release --no-fail-fast` pro `cee_engine`, `cee_core`, `cee_store`: vše prošlo
  kromě `spec_check::scenare_evropa_a_romania_nemaji_chyby` (padá už před touto změnou,
  varování z commitu `25a177f`).
- nové testy: `tests/export_data.rs` (3), `cee_store` (3)
