# 19. Engine v2 v Rustu (základ R0)

Rozhodnutí z 3. 11. 2026: engine v2 (`src/cee/v2`, asi 24 500 řádků) se přepíše celý do
Rustu a Python engine se po přijetí smaže. Bitová shoda s Pythonem se opouští; přijímá se
podle **chování** (brány milníků, audit bran na semínkách, determinismus téhož semínka,
kontrolní body). HTTP server, projekty, úložiště a engine v1 zůstávají v Pythonu a server
bude Rust volat přes tenkou vazbu; UI se nemění (stejný JSON exportu).

Tento dokument popisuje **základ R0** (crate `rust/cee_engine`), na kterém staví čtyři souběžní
agenti R1. Co je hotové a co patří komu, je v [posledním oddíle](#stav-co-je-hotové-a-komu-co-patří).

## 1. Architektura

```
rust/                      pracovní prostor Cargo (Cargo.toml, Cargo.lock, profil release)
├── cee_core/              jádra výpočtů, čistá knihovna (vazba na Python byla smazána, viz konec dokumentu)
├── cee_engine/            čistý Rust, žádné PyO3; závisí na cee_core
│   ├── src/lib.rs         moduly (viz níže)
│   ├── src/bin/cee.rs     CLI `cee`
│   └── tests/             vectors.rs (vektory z Pythonu), engine.rs (kostra), fixtures/
└── cee_py/                tenká vazba PyO3 nad cee_engine pro server (modul `cee_engine_py`)
```

- **`cee_core`** (dnes bez vazby na Python) poskytuje jádra, která `cee_engine` volá:
  banka tvarů a tabulky procesů (`bank`, `process`), řídké fondy (`pools::Cells` je uložení
  bloků živých proměnných), součty jako `np.sum` (`assess::pairwise_sum`), SplitMix
  (`transmission::splitmix64`, `hash_normal`). Další jádra (`transmission`, `pressures`, `index`,
  `candidates`, `sites`, `form_assess` …) napojí agenti R1 na model světa.
- **`default-members = ["cee_engine"]`**: `cargo test` a `cargo clippy` v `rust/` stavějí čistý Rust.
  Vazba pro server se staví z `rust/cee_py` přes maturin (wheel pak leží v `rust/target/wheels`).

### Moduly `cee_engine`

| modul | obsah | zrcadlí |
|---|---|---|
| `ids` | newtypy `GroupId(u32)` …, `Numbering`, `Registry` | `registry.py` |
| `rng`, `legacy_numpy` | `stable_int` (BLAKE2b), `Stream`, hashované Poissonovy tahy; zrcadlo numpy PCG64 pro stavbu světa | `rng.py` |
| `parameters` | `Parameters` (66 polí, `serde`, úrovně) | `parameters.py` |
| `data`, `segments` | vložená data; tabulka hlásek, rozbor IPA, `changed`, vzory | `language/segments.py` |
| `concepts`, `grammar` | data pojmů, graf pojmů, katalog funkcí, konstrukce a profily | `concept_data.py`, `semantics.py`, `constructions.py` |
| `model/*` | území, skupiny (sloupce), kódy, repertoár, morfémy, banka tvarů, vazby (CSR), živé fondy | `world.py`, `repertoire.py`, `language/*.py`, `pools.py` |
| `world` | `World`, `seed_lexicon`, gravitační vazby | `world.py` |
| `protoform`, `scenarios`, `spec` | tvary protojazyka, scénáře, `WorldSpec` | `protoforms.py`, `scenarios.py`, `spec.py` |
| `events`, `history`, `export` | rozhraní událostí, log + snímky, export `cee-v2/1` | `events.py`, `history.py`, `export.py` |
| `simulation`, `phases/*`, `changes/*` | smyčka, fáze kroku, rozhraní změn | `simulation.py` |
| `phonology/*`, `changes/sound` | zvukové změny, index prostředí, fronty fonologizace (R1b) | `phonology.py`, `changes/sound.py` |
| `checkpoint`, `parallel`, `state/*` | kontrolní body, vlákna, stavy oblastí R1 | – |

## 2. Datový model

Zásady: čísla místo řetězců (každý druh entity má v `Registry` číslování v pořadí vzniku, které se
nemění), sloupce podle čísla (SoA), vazby jako CSR, žádné hashovací mapy a řetězce v horkých cestách.
**Čísla nikdy neurčují pořadí**: kde Python řadí podle ID, řadí se podle jmen (`Numbering::ranks`,
`Groups::sorted`, `Distribution` řazená podle jmen variant).

| struktura | obsah |
|---|---|
| `World` | semínko (`i64`), `start_year`, `Arc<Parameters>`, `Registry`, `ConceptColumns`, graf pojmů, `Vec<Territory>`, `Groups`, `Links`, `Variables`, `Variants`, `Morphemes`, procesy, paradigmata, `FormBank`, `LivePools`, stavy oblastí R1 |
| `Groups` | sloupce `alive`, `population`, `prestige`, `openness`, … (24 polí jako `SpeechGroup`) a `codes: Vec<Vec<Code>>`; skupina se neodebírá z polí, jen `alive = false` |
| `Code` | `Repertoire` (copy-on-write přes `Arc` základ), `FormStore` (tři pole podle čísla morfému), `PhonologyState` (slovní zásoba, dominantní kořeny, počty užití, deníky), `StressRule`, `LanguageId`, `l2_share` |
| `Morphemes` | sloupce `kind`, `form` (číslo v bance), `boundary`, `exponent`, `lexeme`, `cell`, `word_class`, `frequency`, `language`, `origin_*`, chladná `meta` |
| `Variables`, `Variants` | druh/klíč/výchozí varianta/pojem; proměnná varianty, příznak inovace, `Origin`, `Payload` (`Lexical`, `Process`, `Construction`, `StressRule`, `StressStrength`, `Other(JSON)`) |
| `LivePools` | bloky podle kapacity slotů nad `cee_core::pools::Cells` (řídké buňky slot × skupina), `present`, klíče variant pro drift; `load`, `innovate`, `release`, `get`, `dominant`, `holds`, `range_of` |
| `Links` | `BTreeMap<(GroupId, GroupId), Link>` + CSR `LinkCsr` přepočítané jen po změně |
| `FormBank` | obal `cee_core::bank::Bank` (tvary jen přibývají, čísla se nemění) |
| `ConceptColumns` | frekvence (s verzí a deníkem změn jako `FrequencyMap`), třída slova, doména, půjčitelnost |

**Pravidlo rozšiřování.** Agent R1 přidává pole **jen do struktury své oblasti** ve `src/state/`
(`TransferState`, `SoundWorldState`/`SoundCodeState`, `GrammarWorldState`/`GrammarCodeState`,
`SocietyState`) a nové soubory ve své složce (`phases/…`, `changes/…`). Společné struktury
(`World`, `Code`, `Groups`, …) se nemění jinak než přidáním pole s výchozí hodnotou. Všechny
stavy mají `Default`, `Clone` a `serde`.

## 3. Rozhraní fází pro R1

`Simulation::step` volá fáze v tomto pořadí (zrcadlo `simulation.py`). Každá fáze je modul
`phases/<jméno>.rs` s funkcí `run(&mut StepContext, …)`; `StepContext` nese `&mut World`,
`&mut History`, `&SimulationConfig`, tik a rok.

| # | fáze | čte | zapisuje | kdo |
|---|---|---|---|---|
| 1 | `phases::events` | fronta `Box<dyn WorldEvent>`, `World` | svět, historie, `society` | R1d |
| 2 | `phases::innovation` | `World`, `Vec<Box<dyn Change>>`, config | nové varianty (`World.variants`), `live.innovate`, záznamy `innovation` | rámec R0; změny R1b/R1c |
| 3 | `phases::transmission` | `World.live`, `links` (CSR), skupiny, tlaky | podíly ve fondech, záznamy `milestone`/`established`/`extinct`, aktivace procesů, slovní zásoba | R1a |
| 4 | `phases::rebuild` | fondy, banka tvarů, procesy, paradigmata | `Code.forms`, slovní zásoba, záznamy | R1b (`phonology`), R1c (`morphology`, `syntax`, `prosody`) |
| 5 | `phases::communities` | `World` | skupiny, kódy, osa fondů; vrací `true` při změně osy | R1d |
| 6 | `phases::observe` | `World`, prahy | `History.snapshots`, události pozorování | R1d |
| 7 | kontrolní bod | `Simulation` | `checkpoints` | R0 |

### Co dostane který agent R1

- **(a) přenos, fondy, tlaky.** `phases/transmission.rs` (dnes jen `release` a počítadlo),
  `state/transfer.rs`. Vstupy: `World.live` (`PoolBlock::cells`, hustý pohled `dense()` jen na dobu
  kroku), `World.links.csr(n)`, `Groups` (populace, prestiž, otevřenost, `renewal`), `Parameters`.
  Jádra: `cee_core::transmission`, `cee_core::pressures`, `cee_core::pools`. Podíly se zapisují zpět
  přes `Cells::stage`/`commit`.
- **(b) fonologie.** `phases/rebuild.rs::phonology`, `changes/sound.rs`, `state/sound.rs`. `ProcessDef`
  (`model::lexicon`) je datová podoba procesu; aplikaci na tvar dělá `cee_core::process` +
  `World.bank.bank` (`register_proc`, `apply_tracked`). `SegmentTable::changed` (nejbližší hláska)
  je hotové a otestované proti Pythonu. Index prostředí je `cee_core::index::SoundIndex` v
  `SoundWorldState`. `vocabulary::units_of` a `PhonologyState` (slovní zásoba, deníky) čte i ji.
- **(c) morfologie, syntax, prozodie, sémantika, lexikální změny, místa, návrh inovací.**
  `phases/rebuild.rs::{morphology,syntax,prosody}`, `changes/{lexicon,morphology,syntax,prosody}.rs`,
  `state/grammar.rs`, `variation.rs` (souběžná variabilita protojazyka), `vocabulary.rs` (`units_of`
  pro výpůjčky a nové lexémy). Vstupy: `World.semantics` (`ConceptGraph`: `into`, `compounds_of`),
  `Paradigm`, `FormChange`, `Catalog`, `Construction`, `Payload::Construction`; jádro
  `cee_core::sites`. Větší slovník a vlastní pojmy (`cee.v2.vocabulary`) patří sem (R1c/R2).
- **(d) události, kontakt a komunity, politika, pozadí, instituce, pozorování, historie.**
  `events.rs` (rozhraní `WorldEvent`, nosič `PendingEvent`, převodník `from_pending`),
  `phases/{events,communities,observe}.rs`, `state/society.rs`, `export.rs` (`states`, `borders`,
  `census`, `lineages`, `dialect_facts`, `endonym`). Scénáře a `WorldSpec` už vytvářejí
  `PendingEvent` se správným druhem a parametry; skutečné provedení (`Scripted`, `State`, `Conquest`, …) přidala R1d.

### Smluvené body mezi fázemi (`phases/hooks.rs`)

Přenos (R1a) předává důsledky do jiných oblastí přes pevné funkce v `phases/hooks.rs`: `follow_vocabulary`
(R1b), `adopt` (R1d), `activate` → `activate_process` (R1b) nebo `activate_analogy` (R1c), `record_grammar` (R1c),
`is_sound_process` (R1b). Vlastník mění jen tělo funkce, podpisy jsou pevné; změnu podpisu sloučí hlavní agent.

### Změny (`Change`)

`changes::Change` je jediné rozhraní, kterým fáze inovací zná druhy změn: `kind`, `weighted_sites`,
`rate_sum` (obojí `&World`, souběžně přes skupiny), `propose` (`&mut World`, sekvenčně). Zaregistrují se v
`changes::default_changes()`; pořadí v seznamu určuje sloupec náhody (`stable_int("innovation-change", kind)`).
`tests/engine.rs` obsahuje zkušební změnu `Toy` jako vzor.

## 4. Náhoda

Port `rng.py` bit po bitu, vektory z Pythonu v `tests/fixtures/rng.json`:

- `stable_int(&[Part])`: BLAKE2b s 8bajtovým výstupem nad `\x1f` + `str(část)`; `Part::Float` se píše jako
  `repr(float)` v Pythonu (`py_float_repr`). `stable_id(prefix, …)` dává `prefix:hash16`.
- `Stream` (SplitMix64): `new(seed, &[…])`, `from_key`, `next_u64`, `random`, `integers` (Lemire),
  `choice`, `normal` (Box–Muller), `poisson` (kusy po 30); `cumulative`/`pick`; `hash_poisson`
  (klíč řádku × klíč sloupce).
- **Princip:** tah závisí jen na semínku a stabilních ID toho, čeho se týká (skupina, kód, změna, tik),
  ne na pořadí ostatních objektů. Fáze si proud tvoří z klíče, žádný sdílený generátor neexistuje.
- `legacy_numpy::Pcg64` zrcadlí `numpy.random.Generator(PCG64(SeedSequence(...)))` (`random`, `uniform`,
  `integers`, `choice`) a slouží **jen** stavbě světa (`protoform`), aby šel svět porovnat s Pythonem v ticku
  0. `uniform` používá `fma` (numpy z arm64 macOS ho tak překládá).

## 5. Vlákna (`rayon`, MIT/Apache-2.0)

Pravidla souběhu (`parallel.rs`): souběh jen ve čtení nebo do vlastního výstupu každé úlohy (výsledky v pořadí
vstupu), zápis do sdíleného stavu sekvenčně v kanonickém pořadí, náhoda z klíče (`Stream::new`), součty po
blocích pevné velikosti (`ordered_sum`). Výsledek je stejný pro libovolný počet vláken: otisk historie
(`History::digest`) i export shodují testy `tests/threads.rs` (1, 2, 3, 4 a 8 vláken; valley-50, grid-5x5,
shift, island-city a příklad `WorldSpec`, s prahem rozdělení nastaveným na nulu, aby se souběh zkoušel i na
malých světech) a `vysledek_nezavisi_na_poctu_vlaken` v `tests/engine.rs`. Jednovláknový výsledek se proti stavu
před touto změnou nezměnil ani o bit (stejné otisky na všech scénářích `cee scenarios` a na příkladu), takže
brány nebylo třeba přepočítávat.

### Měření po fázích

`cee … --phase-times` (nebo `CEE_PHASE_TIMES=1`) vypíše na konci běhu skutečný čas (ne čas procesoru) po fázích
kroku a podfázích; v běžném běhu stojí fáze jedno čtení atomického příznaku (`timing.rs`). Měří se jen v hlavním
vlákně, uvnitř souběžných částí se neměří.

Valley-50 do roku 1500, **jedno vlákno, před úpravou** (ms z celkových 3272): inovace 732 (míry 641, zápis 84),
přenos 2228 (příprava 6, hodnocení procesů `assess` 233, bloky 1589, zápis 397), přestavby 182 (fonologie 77,
morfologie 97), pozorování 130. Uvnitř bloků: **tlaky 925**, výběr a drift (`settle`) 488, míšení (`hear`) 78,
události řádků 85. Z tlaků 597 ms spolkla hodnocení analogií (`assess_row`), která pro každý řádek a skupinu
znovu stavěla úhrn pojmů (`concept_totals`). V příkladu `WorldSpec` je poměr podobný (z 1825 ms: inovace 408,
přenos 1269 [bloky 765, zápis 390, hodnocení 107], přestavby 58, komunity 37, pozorování 37).

### Co běží souběžně

| část | jak | poznámka |
|---|---|---|
| míry inovací (`rate_sum`) a místa (`weighted_sites`) | `par_iter` přes skupiny | zvukové změny čtou index pod `RwLock` (už dorovnané skupiny souběžně) |
| přenos: míšení, tlaky, výběr a drift, události řádků | **úlohy po kusech řádků** (`transfer::block::jobs`, `transmit_rows`), `par_iter` přes úlohy všech bloků najednou | jedna úloha = `hear` + tlaky + `settle` + události; výsledky se skládají v pořadí bloků a řádků |
| pomocné tabulky tlaků (vlastníci tvarů, slabost buněk, dominantní konstrukce, úhrny pojmů) | `OnceLock` sdílený úlohami | čisté funkce stavu, takže nezáleží, která úloha je postaví |
| uvolnění ustálených řádků (`LivePools::release`, hledání jednotných řádků) | `par_iter` přes řádky | |
| pozorování (příznaky skupin, vzdálenosti) | `std::thread::scope` v jádře (už dřív) | shlukování (`linkage`) zůstává sériové |

Úlohy mají cílovou velikost 4096 buněk (`JOB_CELLS`), uvnitř úlohy je vše na jednom vlákně (dřívější vnořené
`std::thread::scope` v `hear` a `settle` se pro úlohy nepoužívá, je to jedna fork-join hranice na krok místo
~30). Svět s méně než `MIN_PARALLEL_CELLS` (16384) buňkami bloků v kroku se nedělí (grid 4×1 a podobné běží
jako dřív; práh jde pro test změnit `parallel::set_min_parallel_cells`).

Zůstává sériové, protože zapisuje do sdílené banky tvarů nebo sdíleného indexu, kde na pořadí záleží (čísla
nových tvarů a prostředí se přidělují v pořadí zápisu): dorovnání indexu zvukových změn (`SoundIndex::sync`),
hodnocení procesů (`transfer/assess.rs::refresh`: `Bank::results` mění banku), návrh a zápis inovací
(`propose` s `&mut World`), sledování slovní zásoby (`follow_vocabulary`, `contact::adopt`), aktivace, fonologizace
a přestavby (`rebuild`), komunity, shlukování při pozorování. Souběh v nich by chtěl bankou sdílenou po
skupinách (vlastní arény s pozdějším sloučením v kanonickém pořadí) nebo dvouprůchodový návrh (čtení souběžně,
zápis sekvenčně); to je další krok.

### Výsledky (Apple M2, 4 výkonná + 4 úsporná jádra; medián ze 3 běhů, střídavě, s; stroj bez další zátěže kromě samotných měření)

Před = `engine-v2-dynamika` (e4112ea; u village-400 s tímto jediným scénářem navíc), po = tato větev. Otisky
historie jsou stejné ve všech 3 během i pro všechny počty vláken.

| scénář | před 1 | 2 | 4 | 8 | po 1 | 2 | 4 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|---|
| valley-50 (do 1500) | 3,64 | 3,23 | 3,00 | 3,00 | 2,84 | 2,17 | 1,83 | 1,87 | 1,90 |
| příklad `WorldSpec` | 2,00 | 1,73 | 1,58 | 1,60 | 1,74 | 1,34 | 1,11 | 1,15 | 1,16 |
| grid-5x5 (do 1500) | 1,18 | 1,07 | 1,02 | 1,04 | 0,98 | 0,80 | 0,71 | 0,72 | 0,73 |
| village-400 (do 400) | 12,25 | 10,20 | 9,28 | 8,98 | 10,42 | 6,49 | 4,75 | 4,31 | 4,35 |

Zrychlení proti jednomu vláknu před úpravou: valley-50 1,9×, příklad 1,7×, grid-5x5 1,6×, village-400 2,8×
(při 8 vláknech); jednovláknový běh je rychlejší o 15 až 20 % (úhrny pojmů se staví jednou na sloupec).
Nad čtyři vlákna výkon neroste (Apple M2 má jen 4 výkonná jádra; 7 a 8 vláken jsou stejně rychlé) a podíl
sériových částí (viz výše) roste: u valley-50 při 8 vláknech zbývá z 1702 ms asi 350 ms na míry inovací (z toho
~300 ms sériové dorovnání indexu), 240 ms na hodnocení procesů, 370 ms na zápis přenosu, 190 ms na přestavby,
125 ms na pozorování a 90 ms na zápis inovací; bloky přenosu spadly z 1589 ms na 329 ms.

### Počet vláken

`parallel::default_threads(reserve)`: všechna dostupná jádra mínus `reserve`, aspoň jedno; `RAYON_NUM_THREADS`
má přednost, `cee --threads N` také. CLI používá `reserve = 0` (běh je jediná úloha stroje), vazba pro server
`cee_py` `reserve = 1` při importu modulu: jedno jádro zůstane UI, prohlížeči a serveru, které by jinak
soupeřily s vlákny enginu o čas (měřili jsme jen vlákna enginu na volném stroji; nad 4 výkonná jádra stejně
zrychlení neroste, takže jádro navíc pro UI nestojí skoro nic). Doporučení: na stroji s ≥ 8 jádry nechat
výchozí hodnotu; na zatíženém stroji nebo při běhu vedle UI použít počet výkonných jader (zde 4).

## 6. Export a historie

`export::export` a `export::frame` dávají stejné schéma `cee-v2/1` jako Python (`territories`, `groups`,
`links`, `snapshots`, `lineages`, `lexicon`, `grammar`, `states`, `borders`, `standards`, `dialect_facts`,
`census`, `events`), takže `runner.py` a UI fungují beze změny. `History` zapisuje události jako JSON
objekty a zaokrouhluje čísla na 6 míst; `digest()` je SHA-256 nad řádky. **Otisk Rustu se neshoduje s
otiskem Pythonu** (jiné oddělovače JSON, jiný běh) a slouží k porovnání běhů Rustu mezi sebou.

## 7. Kontrolní body

`Simulation::checkpoint()` je kopie stavu; `Checkpoint::to_bytes`/`from_bytes` ukládají `World` a `History`
přes `serde` ve formátu **postcard** (kompaktní, stabilní specifikace, MIT/Apache-2.0; nepopisuje typy, proto
se volný JSON ukládá jako text, `json_string`). Banka tvarů se ukládá jako tvary v pořadí čísel, tabulka
hlásek jako příznak (je vložená). `Simulation::resume(checkpoint, config, events, changes)` pokračuje se
stejným výsledkem jako souvislý běh (test `kontrolni_bod_a_pokracovani`). Fronta událostí se neukládá.

## 8. Data

Rust čte `v2_concepts.json`, `v2_concept_frequencies.json`, `v2_core_semantics.json`,
`v2_catalog_semantics.json` a `v2_standing_variation.json` ze `src/cee/data/` a nově vyrobené
`v2_segments.json`, `v2_grammar.json`, `v2_defaults.json` (skript `scripts/export_v2_data.py`). Metaparametry
(`v2_parameters.json`) mají vlastní oddíl níže („Metaparametry“).
**Volba: vložení do binárky (`include_str!`)**: binárka a vazba pro server jsou samostatné, bez cesty k datům
za běhu a bez rozjetí verze dat a kódu; cena je velikost (asi 3 MB) a sestavení po změně dat.

Atribuce: tabulka hlásek je odvozena z **PanPhon** (David R. Mortensen a kol.,
<https://github.com/dmort27/panphon>, licence MIT; Mortensen, Littell, Bharadwaj, Goyal, Dyer, Levin 2016,
*PanPhon: A Resource for Mapping IPA Segments to Articulatory Feature Vectors*, COLING 2016) a z vlastních
rozlišovacích rysů `language/segments.py`. Ostatní data mají původ a licence uvedené v hlavičkách souborů.

## 9. Závislosti a licence

Nové crates, všechny **MIT nebo Apache-2.0**: `serde`, `serde_json` (s `float_roundtrip`), `blake2`, `sha2`,
`rayon`, `unicode-normalization`, `postcard`. Pro Python vazbu dál `pyo3` a `numpy` (Apache-2.0/MIT).

## 10. Příkazy

```
cee run <spec.json> -o export.json [--threads N] [--phase-times]
cee scenario <jméno> --until <rok> [-o export.json] [--checkpoint stav.bin] [--threads N] [--phase-times]
cee export-tick0 <scénář|spec.json> [-o tick0.json]
cee scenarios
cee gates [--seeds 101..120] [--only m4b,m5::s3_substrat] [--metrics] [--list] [-o audit.jsonl]
```

`cee gates` je audit bran na semínkách (viz [R2b](#r2b-brány-milníků-v-rustu)).

Porovnání ticku 0 s Pythonem (`scripts/v2_compare_tick0.py`) a vektory z Pythonu pro testy
(`scripts/export_v2_rust_vectors.py`) zmizely se smazáním Pythonu; uložené vektory zůstaly v
`rust/cee_engine/tests/fixtures/` jako zmrazená reference.

## 11. Stav: co je hotové a komu co patří

**Hotové v R0 (s testy):** pracovní prostor, registr a newtypy, náhoda (včetně numpy zrcadla), parametry,
tabulka hlásek (rozbor, `changed`, vzory), pojmy a graf, katalog gramatiky, `World` a model (skupiny,
kódy, repertoár, morfémy, tvary, vazby CSR, živé fondy), stavba světa (`village_grid`, `region_world`,
`contact_world`, `island_and_city`, `language_shift`, `diglossia`, `conquest`, `market_town`,
`migration_region`, `conversion`, `known_tree`, `kingdom`, `WorldSpec`), historie a export `cee-v2/1`,
kostra smyčky s fázemi, fáze inovací (rámec), kontrolní body, vlákna, CLI. Tick 0 všech scénářů a
příkladu `WorldSpec` je **shodný s Pythonem** (viz výsledek v zprávě R0).

| patří | co chybí |
|---|---|
| **R1a** | hotovo; tlaky nad hodnocením a `closed` doplnila R2a (viz [R2a](#r2a-integrace-oblastí)) |
| **R1b** | hotovo, viz [R1b](#r1b-fonologie-a-zvukové-změny); hodnocení procesů a `surface` doplnila R2a |
| **R1c** | **hotovo** (viz [oddíl R1c](#r1c-morfologie-syntax-prozodie-sémantika-a-lexikon)): morfologie, syntax, prozodie, sémantické a lexikální změny, místa a návrh inovací, souběžná variabilita, větší slovník a vlastní pojmy; napojení na fonologii a slovní zásobu doplnila R2a |
| **R1d** | hotovo (viz [R1d](#r1d-události-kontakt-společnost-a-pozorování)); přenos i výpůjčky čtou rozhraní `contact` (R2a) |
| **R2** | integrace (R2a): **hotovo, viz [R2a](#r2a-integrace-oblastí)**, vazba pro server: hotovo (R2c), **brány v Rustu a audit na semínkách: hotovo, viz [R2b](#r2b-brány-milníků-v-rustu)**, porovnání chování s Pythonem, vazba pro server (`runner.py` → Rust), smazání Pythonu v2, `Simulation::branch` |

### Známá omezení a odchylky od Pythonu

- `Parameters` má **66 polí** (zadání uvádělo 68; počet odpovídá `dataclasses.fields(Parameters)` v tomto
  stavu repozitáře, test `vychozi_parametry` porovnává názvy i hodnoty s Pythonem).
- Rozbor IPA je slovník symbolů + nejdelší shoda (ne PanPhon). Na slovech všech protojazyků scénářů a ve
  vektorech sedí; vzácné nezvyklé kombinace značek vrací chybu.
- `gravity_pairs` používá `f64::hypot` místo `math.dist` (rozdíl v posledním bitu možný; porovnání ticku 0
  používá toleranci 1e-12).
- Souběžná variabilita se v Rustu rozdává z proudu `Stream` (ne z numpy), takže po rozdání nesedí s Pythonem bit po bitu; tik 0 bez variability (`standing_variation = 0`) ano.
- `WorldSpec` s `background` ≠ `none` se odmítne chybou (R1d); větší slovník a vlastní pojmy se staví (R1c).
- Události jsou nosiče bez provedení: běh, který na událost narazí, skončí chybou.


## R1b: fonologie a zvukové změny

Hotovo: 33 rodin zvukových změn jako `Change`, index prostředí a opor, fonologizace s frontami,
uzavření procesu, sledování slovní zásoby po přenosu a aktivace procesu. Python se nespouštěl.

### Návrh

| část | soubor | obsah |
|---|---|---|
| změny | `changes/sound.rs` | `SoundChange { family }` pro každou z 33 rodin (`cee_core::candidates::FAMILIES`), priory a rozpočet (`scales`: 0,6 inovace na generaci pro netónové rodiny, tóny mimo), registrace v `default_changes()` |
| index | `phonology/index.rs` | `with_group(world, skupina, čtení)`: dorovná `cee_core::index::SoundIndex` na stav kódu (razítko = verze fonologie, verze tvarů, délka deníku slovní zásoby, počet morfémů, pravidlo přízvuku) a předá ho čtení; index je za zámkem v `World.sound.runtime`, takže míry se počítají souběžně přes skupiny a výsledek nezávisí na pořadí (opory jsou celá čísla); snímek tabulky hlásek pro stavbu kandidátů je vložený a staví se jednou (`snapshot`) |
| procesy | `phonology/rows.rs` | `register` (z kandidáta založí procesní proměnnou `process:klíč`, variantu „žádná změna“ a „změna“, `ProcessDef` a číslo procesu; tatáž změna je tatáž proměnná), `row_of` (řádek procesu v bance tvarů, registruje se líně), `resolve_maps` (výstupy `change`/`tone` počítá tabulka hlásek), `changed_share` |
| sloupce | `phonology/columns.rs` | sloupce morfémů ve tvaru pro jádro (váha buňky, lexém, výchozí tvar, hranice, koncovka), četnosti pojmů, `sync_usage` (dominantní kořeny kódu z deníku `dominant_log`), sklon slova `draw_bias`/`word_bias` |
| fronty | `phonology/queues.rs` | `activate`, `enter_units`, `leave_vocabulary`, `requeue_all`, `restructure_groups` nad `cee_core::code_state::CodeState`; chybějící sklony slov a mapy hlásek jádro vyžádá a doplní se v cyklu |
| hooky | `phases/hooks.rs` | `follow_vocabulary` (odchody před příchody, dominantní kořeny, počty užití, `adopt`, `units_of`, vstup a odchod ze slovní zásoby), `is_sound_process` (druh proměnné `Process`), `activate_process` |
| stav | `state/sound.rs` | `SoundCodeState { order, queues, lifecycle_log }` (uložené), `Runtime` (odvozené: index, sklony slov, řádky procesů, sloupce) |

**Místa zvukových změn.** V Pythonu je místem ID procesní proměnné, která vzniká až při návrhu. V Rustu je
místem pořadí kandidáta v rodině (`VariableId` jako nosič pořadí). `propose` ho přeloží na kandidáta,
zaregistruje proměnnou a vrátí ji v `NewVariant::variable`; fáze inovací pak dál používá tuto proměnnou
(`site = variant.variable`, jediná změna ve společném souboru `phases/innovation.rs`).

**Odvozený stav a kontrolní body.** `Runtime` se při kopii světa a po načtení zahodí; banka tvarů se kopíruje
bez procesů a zaregistrují se znovu (`ensure_rows`, přesně v pořadí čísel procesů). Fronty (`Queues`) se ukládají
(bez řádků banky a paměti četností); paměť četností užití se po obnově doplní z `dominant_log`. Test
`kontrolni_bod_uprostred_fonologizace_da_stejny_beh` dává po obnově stejný běh.

**Zjednodušení proti Pythonu.** Řádek procesu v bance je jeden pro všechna pravidla přízvuku (tabulky výsledků se
zakládají líně v jádru), takže odpadá `NO_TABLE` a „tabulka pro pravidlo“. Výchozí tvary morfémů jsou vždy
v bance (`Morphemes.form`), proto odpadá aréna výchozích tvarů indexu. Záznamy `phonologized` a
`process_closed` se píšou po skupinách v pořadí průchodu fonologie (ne proloženě s morfologií skupiny).

### Pro ostatní oblasti

- **R1a:** `phonology::row_of(world, proces)` dá řádek procesu v bance pro hodnocení tlaků; procesy se do banky
  smí registrovat jen přes něj (`ensure_rows` jinak hlásí rozpor). `phonology::changed_share` je podíl změny
  ve skupině. Tlaky zvukových změn (`SOUND_PRESSURES` v Pythonu: Articulation 1,0; Clarity 0,6; FunctionalLoad 1,0;
  Dispersion 0,5; Phonotactics 0,4; Conformity 0,1; Actuation 1,0) patří přenosu, ne sem.
- **R1c:** po přepsání tvaru analogií volej `phonology::requeue_all(world, skupina, morfém)`; nové tvary slov
  (`units_of` pro nové lexémy a výpůjčky) vstupují přes `phonology::enter_units`. `surface` (povrchový tvar
  slova pro export) zatím není; export čte podkladové tvary.
- **R1d:** `hooks::adopt` volá `follow_vocabulary` jen při prvním vstupu slova do kódu.

### Brány milníků, kterých se oblast týká

Brány M2 až M7 měří zvukové změny přes `innovation` (change ∈ rodiny), `phonologized` (slova), `process_closed`
a rozdělení procesních proměnných; po sloučení s přenosem (R1a) je k tomu potřeba jen to, co je tu hotové.

## R1a: přenos, živé fondy a tlaky (`transfer/`, `phases/transmission.rs`)

Fáze 3 kroku (`phases::transmission::run`) je napsaná celá a běží v pořadí Pythonu:
příprava kroku → přenos všech bloků ze **starého** stavu → zápis po blocích (smluvené body
`record_grammar`, `follow_vocabulary`, uložení nových podílů) → aktivace (`hooks::activate`) seřazené
podle jmen (skupina, proměnná) → záznamy → `release`.

| modul | obsah |
|---|---|
| `transfer::network` | `prepare`: míšení po řádcích řídce (`mixing`, hustá matice se nestaví nikdy), komponenty, osamocené skupiny, vazby mezi jazyky po kanálech `neighbor`/`elite`/`trade` (`FlowChannel`), kanály mimo síť (`SideKind`: interference, čtení, škola, liturgie), kohorty (rozsah driftu, práh zániku), klíče driftu, váhy domén a normalizace půjčitelnosti |
| `transfer::factors` | filtry kanálů podle druhu proměnné, frekvence a domény pojmu, po řádcích bloku |
| `transfer::block` | `transmit_block`: po kusech řádků (nejvýš 2^20 buněk) `cee_core::transmission::{hear, settle}` nad hustým výřezem, tlaky, a z před/po milníky 0,1 / 0,5 / 0,9, ustálení, zánik, přechody prahu dominance slov, aktivace, dráhy; nový stav hned jako řídké `Row` |
| `transfer::pressures` | plán tlaků podle druhu proměnné (zrcadlo `pressures_by_kind`, přepis `pressure_weights`, `Norm` všude) a všech 23 tlaků: `conformity`, `appeal`, `entrenchment`, `motivation`, `actuation`, `lexical_actuation`, `lexical_clarity`, `taboo`, `norm`, pět konstrukčních (`expressivity`, `economy`, `fusion`, `learnability`, `ambiguity`) a devět nad hodnocením |
| `transfer::assessed` | skóre procesů a analogií z pěti hodnot hodnocení (čisté funkce, testované proti vzorcům Pythonu) |
| `transfer::seams` | to, co přenos čte z cizích oblastí a ve společném modelu zatím není |
| `state::transfer` | `TransferState { steps, derived }`; `Derived` (sloupce variant podle čísla varianty, mapa proměnná → varianta „změna“) se neukládá a po kopii či obnově se staví znovu |

**Datový model.** Sloupce variant (`morpheme`, `motivation`, `appeal`, `key`) jsou odvozené z tabulky variant
a jen přibývají; tlaky čtou čísla, ne řetězce. Plán tlaků a stav tlaků (vlastníci tvarů pro lexikální jasnost,
slabost buněk, dominantní konstrukce) se staví jednou za krok a líně. Hustá pole žijí jen po dobu jednoho kusu
bloku; `compact` z Pythonu v Rustu nemá co dělat (hustý pohled se nikde nedrží).

**Chování oproti Pythonu.** Všechny bloky se počítají ze starého stavu. Šum driftu a ocenění změn jsou hashované
z klíčů (semínko, tik či epocha, jméno skupiny a varianty), takže výsledek nezávisí na pořadí ani na počtu vláken
(`tests/transfer.rs`). Bitová shoda s Pythonem se nehlídá. Plán tlaků je pevný (výchozí změny); až se změny
zaregistrují v `default_changes()`, může se plán skládat z jejich deklarací jako v Pythonu.

**Metriky bran, kterých se oblast týká.** Brány M2 až M7 čtou záznamy `milestone`, `established` a `extinct`
(jména `variable`, `variant`, `group`, `level`, seřazené stejně jako v Pythonu), dráhy inovací
(`record_trajectories`), podíly ve skupinách (`World::distribution`) a šíření slov, procesů a konstrukcí.
Tlaky nad hodnocením (zvukové procesy, analogie) jsou nulové, dokud R1b a R1c nedodají `seams::assess_cells`.

## R1c: morfologie, syntax, prozodie, sémantika a lexikon

Návrh stavu: `state/grammar.rs` (`GrammarWorldState`, `GrammarCodeState`) drží živé analogie
(`morph_active`, `morph_closed`), zapsané konstrukce (`grammar_applied`) a **keš pohledů** (`ViewCache`):
odvozené údaje kódu (kandidáti vyrovnání a rozšíření, koncovky tříd, místa sémantických změn, odvozeniny)
se drží podle verze stavu kódu (`morphology::code_version`, `lexicon_version` a délka deníku dominantních
kořenů), čtou je souběžné fáze (`rate_sum`, `weighted_sites`), proto jsou neměnné (`Arc`) za zámkem. Keš
se do kontrolního bodu neukládá a kopie stavu začíná prázdná.

| modul | obsah | zrcadlí |
|---|---|---|
| `morphology` | koncovky tříd (`class_stats`), slabost buněk, kandidáti vyrovnání, rozšíření a reanalýzy hranice, `register`, `apply_form_change`, `analogy_plan`, `restructure`, `units_of` | `morphology.py` |
| `syntax` | katalog funkcí s přepisy, dominantní konstrukce, slabost a síla vyjádření, kompenzace, `new_affix`, `ready_constructions`, `restructure` | `syntax.py` |
| `prosody` | pravidlo a síla přízvuku, `plan`, `restructure` | `prosody.py` |
| `changes/lexicon` | expresivní tvoření, 7 sémantických změn (posun, konverze, odvození, složenina, opis za tabu, kontaminace, zpětné tvoření), výpůjčky | `changes/lexicon.py` |
| `changes/morphology` | vyrovnání, rozšíření, reanalýza hranice | `changes/morphology.py` |
| `changes/syntax` | deset syntaktických změn včetně zániku kategorie | `changes/syntax.py` |
| `changes/prosody` | posun a síla přízvuku | `changes/prosody.py` |
| `variation` | souběžná variabilita slovní zásoby protojazyka (graf vazeb, naměřený model vesnice, činitele hustoty a podílu) | `variation.py` |
| `vocabulary` | větší slovník, vlastní pojmy, graf pojmů z katalogu (`resolve`, `Vocabulary::graph`), `units_in` | `vocabulary.py` |

**Změny a místa.** `default_changes()` vrací změny v pořadí Pythonu (lexikální, *zvukové – místo pro R1b*,
morfologické, syntaktické, prozodické). Sedm sémantických změn je jedna struktura `SemanticChange`
s druhem; míra místa je `base × součet vah cest` (cesty jsou v grafu pojmů, dominantní kořeny z kódu),
váhy výběru místa jsou míry dělené součtem. **Formové změny (analogie) vznikají až při návrhu**, protože
jejich proměnná se zakládá při `register`; místa jsou proto pořadová čísla kandidátů a po návrhu platí
`NewVariant::variable` (fáze inovací používá `variant.variable`, viz „Změny společných souborů“).
Návrhy zaregistrovaných variant (analogie, konstrukce, prozodie) vracejí obsah a původ **první**
registrace.

**Přestavby.** `phases::rebuild::{morphology, syntax, prosody}` volají `morphology::restructure`,
`syntax::restructure`, `prosody::restructure`; hooky `activate_analogy` (`morphology::activate`) a
`record_grammar` (deník konstrukcí kódu). Jádra `cee_core::form_restructure` a `form_assess` se nepoužila:
jsou psaná pro Python a drží vlastní index kódu přes deníky; přestavby jsou řídké, takže stačí počítat
přímo nad stavem kódu. `cee_core::sites`, `morphology_index` a `semantic_index` se také nepoužily z
téhož důvodu (místa se počítají nad čísly morfémů, pojmů a tříd s keší podle verze kódu).

**Výpůjčky a kontakt.** Dárce čte `changes::lexicon::donors` přímo z vazeb a skupin (otevřenost × síla
vazby × prestiž dárce, jen jiný jazyk, jen negramotné kódy), kanály `elite` a `trade` z
`Parameters::channel_domains` a `World::trade_share`. Přenositelnost pojmu (`transfer`) má vlastní kopii
vzorce s normalizací z dat (`ConceptData::borrowing_normalizer`, ověřeno proti Pythonu). Až R1d dodá stav
kontaktu, stačí zaměnit `donors` a `channel_exposures`.

**Větší slovník a vlastní pojmy.** `ConceptData` zná katalog WOLD (`catalog_ids`, `catalog_order`, `find`,
průměry); `vocabulary::resolve(size, custom)` dá pojmy v pořadí Pythonu, `Vocabulary::graph` staví graf z
jádra, z `v2_catalog_semantics.json` a z vlastních vztahů. `SeedOptions::vocabulary` ho předá stavbě světa
(pojmy, třídy slov, známé frekvence, graf, doména a půjčitelnost vlastních pojmů). `WorldSpec` ho staví.

**Změny společných souborů:** `phases/innovation.rs` (po `propose` platí `variant.variable` místo místa),
`changes/mod.rs` (moduly a `default_changes`), `lib.rs` (moduly `morphology`, `syntax`, `prosody`),
`scenarios.rs` (`SeedOptions::vocabulary`, parametr `seed_lineages`, třídy a graf z vocabulary),
`spec.rs` (stavba slovníku místo odmítnutí), `concepts.rs` (katalog, `with_relations`), `phases/{rebuild,hooks}.rs`
(jen těla R1c).

**Co čekám od ostatních:** R1a: v `transmission` volat `hooks::record_grammar` pro konstrukce, které se
ve skupině změnily, a `hooks::activate` pro dvojice nad prahem; tlaky potřebují od změn jen druh proměnné
(cílový typ a váhy tlaků jednotlivých změn jsou v `changes::*` zatím nezapsané, přidá R1a/R2 do
`Change`, stejně jako Python `target` a `pressures`). R1b: ve `follow_vocabulary` pro nové slovo volat
`vocabulary::units_in` (tvary buněk nového lexému a výpůjčky) a místo mých náhrad `morphology::requeue_all`
a `morphology::enter_vocabulary` použít fronty fonologizace; zvukové změny zaregistrovat v
`default_changes()` mezi lexikální a morfologické.

**Brány milníků a R1c.** Týkají se jí metriky M3b (lexikální změny: obměna slovníku, podíl cest vzniku
slov), M4 a M4b (gramatikalizace: cykly opis, přiklonka, koncovka, zánik kategorie, zápor, slovosled),
analogie (vyrovnání a rozšíření ve `morphology`) a prozodie. Pro R2 jsou připravené: `history` záznamy
`innovation`, `analogy`, `stress_rule_changed`, `stress_strength_changed`, stavy `grammar_applied` a
`morph_closed`, `Vocabulary` s pořadím pojmů a zkoušky v `tests/r1c.rs`. Nebyly spuštěné scénáře
`v2_digests.py` v Pythonu; porovnání chování je na R2.

- Svět v Rustu nemá souběžnou variabilitu slovní zásoby (viz `variation.rs`); export ticku 0 jí není dotčen.
- `WorldSpec` s větším slovníkem nebo vlastními pojmy se odmítne chybou (R1c/R2).
- Pozadí dějin (`background`) generuje Rust z vlastního proudu náhody (`Stream`), ne z numpy: dějiny téhož semínka jsou jiné než v Pythonu, mají ale stejné rozdělení.

## R1d: události, kontakt, společnost a pozorování

Oblast R1d přepisuje `events.py`, `edits.py`, `polity.py`, `background.py`, `contact.py`
(komunity, kanály, výpůjčky), `observe.py`, `naming.py` a část `export.py`.

### Moduly a datový model

| modul | obsah |
|---|---|
| `edits` | **jediná cesta, kterou se mění svět mimo přenos**: `Op` (`AddTerritory`, `AddGroup`, `RemoveGroup`, `SetGroup(Field)`, `SetCode`, `FixCode`, `Connect`, `SetLink`, `DropLink`, `SetTrade`, `SetBorderFactor`, `SetBasePrestige`, `SetPrestigeMirror`, `AddState`, `SetState`, `SetStateLink`, `RemoveState`, `SetStandard`), `apply(world, op)` a `Edits` (tik + fáze `Event`/`Community`). Operace nese čísla entit (`GroupId`, `TerritoryId`); jména jen u nových entit a států. Totéž `apply` se používá při běhu i při přehrání deníku (`Edits::replay`), takže deník nemůže popsat něco jiného, než co se stalo. |
| `events` | `WorldEvent` (rozhraní beze změny), `PendingEvent` (nosič; teď se rozebere až při provedení), `Scripted` (rok, druh, původní popis, rozebraná `Action`). `from_pending` rozebere JSON parametry (přijímá i podoby scénářů: `first`/`second`, `elite`/`seat`/`regions`, `groups`). Druhy: `border`, `contact`, `language_shift`, `codification`, `printing`, `schooling`, `religious_change`, `refinement`, `migration`, `conquest`, `war`, `epidemic`, `state_collapse`. Neplatný popis vrátí chybu až při provedení. |
| `polity` | `state`, `language_policy`, `annexation`, `secession`, `collapse`, `border_policy`, `lingua_franca`, `standard`, `schools`, `revival`, `preserve`, `identity`, `immigration`; `refresh` (hranice z `border_factors` a prestiž z `base_prestige`, hlavního města a normy); exporty `states`, `borders`, `language_census`. |
| `background` | `Plague`, `Recovery`, `Resettlement`, `TradeShift`, `PrestigeShift`, `ForeignElite`, `EliteAssimilation` a generátor `generate` (z `Stream::new(seed, ["background"])`); `spec::build` ho volá a odmítnutí `background` zrušilo. |
| `contact` | filtry výpůjček a interference, kanály, dárci a adaptace cizích slov (viz níže). |
| `phases::communities` | `community_step`: přechod jazyka (`shift`, Abrams–Strogatz, obousměrný při `home_pull`/`revival`), pronikání veřejného kódu domů (`nativize`), druhý jazyk (`l2_share`), gravitační migrace (`migrate`). |
| `observe`, `phases::observe` | skládání vstupu pro `cee_core::observe` z modelu světa, `observe_world` (shluky dialektů a jazyků), `code_distances`, `LineageTracker`. |
| `naming` | endonym, původ jazyka, poloha nářečí (jen export). |
| `state::society` | `SocietyState`: `Polity` (stát), `states`, `standards`, `endonyms`, `border_factors`, `base_prestige`, `prestige_mirror`, `trade`, `migration`, `journal` (`JournalMode`), `edit_log`, `lineages`. |

**Deník změn.** `JournalMode::Structure` (výchozí) zapisuje všechny změny událostí, států a pozadí a ve fázi komunit jen změny
struktury (vznik a zánik skupin, vazby, obchod, hranice, prestiž, předávání jazyka); každokrokové úpravy populace, `l2_share`
a přistěhovalců se nezapisují, aby deník nerostl úměrně počtu skupin krát počet kroků. `All` zapisuje jako Python, `Off` nic.
Deník na dynamiku nemá vliv. Změna, která nic nezměnila (stejná hodnota), se nezapíše.

**Pozorování.** `ObserveInput::gather` skládá pohledy na bloky živých fondů (jen proměnné slov a konstrukcí), dominantní kořeny
skupin a **jen tvary, které skupiny opravdu užívají** (tabulka tvarů se staví z použitých tvarů, ne z celé banky), vazby a polohy
mluvených skupin. Nikde se nestaví tabulka dvojic hlásek ani matice všech dvojic skupin: `Costs` počítá cenu záměny hlásek z řádků
rysů při každém dotazu a shlukování bere průměrnou vazbu ze součtů za shluk, takže čas i paměť rostou s počtem skupin lineárně.
Čtvercová matice vzdáleností (`code_distances`) vzniká jen s `SimulationConfig::keep_distances` (do `Snapshot::distances`).

### Rozhraní `contact` pro přenos (R1a) a morfologii (R1c)

Pro výpůjčky a interferenci čtou přenos a změny tyto funkce (nic z nich nedrží stav, vše je čisté čtení světa):

* `BorrowTable::build(&World)` jednou za krok spočítá přenositelnost každého pojmu; `table.factor(&world, variable, channel)` je
  filtr výpůjček proměnné v kanálu (`NEIGHBOR`, `ELITE`, `TRADE`, `LITURGY`, `READING`, `SCHOOL` jsou čísla kanálů v pořadí
  `parameters::CHANNELS`). Slova: `0,5 × přenositelnost pojmu × váha domény v kanálu`; procesy a konstrukce 0,1; tvary a prozodie 0.
* `interference_factor(kind)`: slova 0,05, procesy a konstrukce 1, tvary a prozodie 0.
* `distinct_channels(&params)`: které z `ELITE`, `TRADE` mají jiné váhy domén než obecný kontakt sousedů (jen ty se v přenosu
  počítají zvlášť; kanál s týmiž vahami splyne se sousedy).
* `channel_split(&world, učící_se, zdroj, &distinct)` → `ChannelSplit { neighbor, elite, trade }` se součtem 1: zdroj-elita je celý
  kanál `elite`, z ostatních vazeb patří `trade` podíl síly z obchodní cesty (`World::trade_share`). Je **řídké po vazbě**; Python měl
  čtvercové matice kanálů, tady se nestaví.
* `adopt(&mut world, skupina, morfém)` (tělo `phases::hooks::adopt`): cizí kořen vstupuje do slovní zásoby; tvar se vezme od
  nejbližšího dárce (`donor_form`: sousedé podle síly, pak `l1_source`, `standard`, `liturgy`) a cizí hlásky se nahradí
  nejbližší hláskou příjemce podle rysů (`adapt`, `inventory`). Tvary buněk paradigmatu výpůjčky (podle produktivních koncovek
  příjemce, `morphology.units_of`) dodá R1c.

Filtry se zkoušejí proti Pythonu (`reference()`, `normalizer(s)`: hodnoty z `cee.v2.contact`).

### Odchylky od Pythonu

* **Pozadí dějin** má jiný generátor náhody (viz výše); `PendingEvent` se rozebírá při provedení, ne při sestavení.
* **Pořadí sčítání** (`demographic_share`, migrace) je podle jmen skupin; součty se mohou lišit v posledním bitu.
* `ReplayEdits` (přehrání deníku jako událost) není; `Edits::replay` a `edits::by_tick` ano (test `denik_zmen_se_prehraje_na_novem_svete`).
* Matice vzdáleností a `group_ids` jsou ve `Snapshot` jen s `keep_distances`.
* Vlastní jméno jazyka čte `SocietyState::endonyms`; scénáře ho zatím nenastavují (platí výchozí složenina pojmu `language`).

### Brány milníků

Oblasti R1d se týkají metriky bran, které čtou: **snímky dialektů a jazyků** (`History::snapshots`, `language_split`/`language_emerged`/
`language_ended`, M4–M6, M7 strom jazyků), **přechod jazyka a dvojjazyčnost** (`bilingualism`, `language_shift`, `nativization`,
`revival`, M5, M6f), **populace a podíly L2** (`Groups`, `l2_share`) a **státy, normy a školy** (`state`, `standard`, `schools`, `census`, M6f).
Pro R2 je připraveno: `SocietyState::edit_log` pro porovnání změn světa, `code_distances` pro metriky kontinua (M7), `export::{lineages,
dialect_facts}`, a rozhraní `contact` pro přenos výpůjček. Brány samotné (jejich prahy, audit na semínkách) převede R2 po sloučení s přenosem.

## R2c: vazba enginu pro server

Crate `rust/cee_py` (PyO3, maturin, modul `cee_engine_py`, licence MIT) je tenká vazba nad `cee_engine`. Člen pracovního
prostoru, ale ne `default-members`, takže `cargo test` a `clippy` v `rust/` ji nestaví (jako `cee_core`). Rozhraní:

* `Run(spec_json)`: postaví svět z `WorldSpec` (text JSON); neplatný popis vyhodí `ValueError` se zprávou enginu.
* `advance(steps=1) -> bool`: provede nejvýš `steps` kroků **bez GIL** (`Python::detach`), vrátí, zda je co krokovat;
  chyba enginu je `RuntimeError`. `cancel()` nastaví příznak mimo zámek běhu (nečeká na rozpracovaný krok), `advance` se pak
  zastaví; `cancelled`, `finished`.
* Čtení: `start_year`, `end_year`, `year`, `tick`, `snapshots`, `frame()` (lehký snímek, text JSON), `export(timeline=True)`
  (úplný export `cee-v2/1`, text JSON). Čtení jde mezi kroky, protože simulace je za `Mutex`.
* `check_spec(spec_json) -> list[{path, message, severity}]`: ověření popisu (slovník, slova, stavba světa, zkušební
  provedení událostí); prázdný seznam = bez problémů, chyby jdou před varováními. `vocabulary_max_size() -> int`.

`src/cee/v2/runner.py` už Python engine nepoužívá: `prepare` ověří schéma pydanticem (`spec.parse`), zbytek (neznámé regiony,
slova, parametry, pořadí událostí) ohlásí stavba světa v Rustu a vrátí se jako `SpecError` s cestou `(svět)`. Vlákno běhu volá
`advance(1)`, po každém pozorování uloží `frame()` a na konci `export()`. Zrušení nastaví `Event` i příznak v Rustu. Rozhraní
`Run` (`status_view`, `frames`, `result`, `cancel`) a odpovědi `/api/v2` se nezměnily; testy `tests/test_api_v2.py` procházejí.

**Odchylky (stav v době R2c).** Chyby ze zkušebního provedení událostí měl Python (`spec.check`), Rust hlásil jen jednu
zprávu s cestou `(svět)`. Od smazání Pythonu v2 dává všechny chyby s cestou Rust (viz poslední oddíl).

### Co ze `src/cee/v2` server po přepnutí ještě importoval (návrh před smazáním)

Server (`cee.api.v2`) importuje `cee.v2.runner`, `cee.v2.parameters` a `cee.v2.spec`. `runner` bere ze `spec` jen `WorldSpec`,
`parse`, `Issue`, `SpecError`, `errors`. Jenže `spec.py` na úrovni modulu importuje `concept_data`, `vocabulary`, `events`,
`history`, `parameters`, `polity`, `scenarios`, `world`, a tedy tahá celý Python engine (`world`, `language/*`, `phonology`,
`transfer` …). `check` navíc staví svět a zkouší události v Pythonu (`_world`, `item.event().apply`), `_words` importuje
`language.constructions` a `language.segments`, `build` a `background_events` jsou jen pro Python engine.

**Návrh, co zůstane a co se smaže** (po přijetí bran, kód zatím nemažu a `spec.py` neměním):

* **Zůstane** (jen schéma a validace, bez enginu): z `spec.py` modely pydantic (`WorldSpec`, `LanguageSpec`, `RegionSpec`, události,
  `ConceptSpec`), `Issue`, `SpecError`, `parse`, `levels`, `EVENT_KINDS`, `FORMAT`, `errors`/`warnings`, `vocabulary_options`;
  dále `parameters.py` (čistý dataclass s tabulkami úrovní), `concept_data.py` a `vocabulary.py` (data a `validate`), `runner.py`.
  Z modelů událostí se musí odstranit metody `.event()` a `.custom()` (ty vytvářejí objekty Python enginu), `GRAMMARS` se nahradí
  seznamem jmen profilů.
* **Přesune se do Rustu:** sémantická část `check` (stavba světa, zkušební události, slova a hlásky). `check_spec` ji dnes vrací
  jako jednu zprávu; pro `/validate` je potřeba vracet seznam `{path, message, severity}` (rozšíření R2 nebo následný krok),
  tabulku hlásek a tóny pro `_words` už Rust má (`segments`).
* **Smaže se:** `world`, `simulation`, `export`, `history`, `events`, `polity`, `scenarios`, `background`, `naming`, `checkpoint`,
  `language/*`, `phonology`, `transfer`, `pressures` a ostatní moduly enginu, `build`, `background_events`, `_world`.

## R2a: integrace oblastí

Hotovo: tlaky nad hodnocením, švy mezi oblastmi, plán tlaků ze změn, `surface`. Python se nespouštěl.

- **Kontrolní bod uprostřed fonologizace.** Příčina nebyla v odvozeném stavu, ale v testu: proces byl pevný jen v
  první skupině, takže proměnná se lišila mezi skupinami, aniž byla živá; obnovený běh ji načetl do fondů a přenos
  ji rozmíchal. Test teď nastaví změnu ve všech skupinách. Nový test kontrolního bodu běží s přirozenými inovacemi.
- **Hodnocení procesů** (`transfer/assess.rs`): dvouprůchodový návrh. `assess::refresh` (má `&mut World`, volá se
  v `phases::transmission::run` před přenosem) pro každý sledovaný proces spočítá hodnocení ve skupinách, které
  změnu mají nebo ji mohou slyšet (zdroje v síti, mezi jazyky i kanálech mimo síť), nad vzorkem 120 nejčastějších
  slov kódu (banka tvarů, ceny nových homofonů, rozptyl samohlásek). Platí do změny verze kódu, nejvýš 8 ticků;
  ukládá se do `TransferState::assessments` (i v kontrolním bodu). Vzorek je odvozený (`Derived::samples`).
  Tlaky čtou uložené hodnoty ze `&World` (`seams::assess_cells`). Hodnocení analogií (`form_cells`) se počítá rovnou
  z pohledů morfologie. `seams::closed` je uzavřený proces kódu. `FormBank` nově nastavuje polosamohlásky
  (příznakovost slabik).
- **Švy.** Morfologie a syntax volají `phonology::requeue_all` a `enter_units` (náhrady R1c odpadly);
  `follow_vocabulary` bere tvary buněk přes `vocabulary::units_in`; přenos (`BorrowTable`, `channel_split`,
  `interference_factor`, `distinct_channels`) i `LexicalBorrowing` používají rozhraní `contact`, vlastní kopie zmizely.
- **`Change::target` a `Change::pressures`.** Plán tlaků se skládá z deklarací změn (`pressures::plan_for`,
  zrcadlo `pressures_by_kind`, tlaky seřazené podle jména); `plan(params)` je plán výchozích změn.
  `phases::transmission::run` bere seznam změn.
- **`phonology::surface` / `surface_lexicon`** (nad `&World`, banka se nemění): povrchový tvar slova s živými procesy;
  bránové metriky (`gates::metrics`) ho čtou. Export jazyka dál čte podkladové tvary jako Python.
  `Snapshot::group_ids` se plní vždy. `cee scenario --history log.jsonl` zapíše log jako JSON řádky.
- **Chování.** Po integraci procházejí všechny brány R2b (62 testů), viz tabulka v závěrečné zprávě. Scénář valley-50
  do 2000 let dává 41 jazyků z 50 vesnic (vzdálenost sousedů 0,35); Python (`village_grid`, otevřenost 0,1) uvádí
  0,29 po 3000 letech. Šlo o srovnání různých věcí (3000 let a mřížka 5×5 proti 2000 let a údolí 10×5); při stejném
  scénáři Python dává totéž, viz [Kalibrace proti Pythonu](#kalibrace-proti-pythonu).

## R2b: brány milníků v Rustu

Hotovo: všech 10 souborů bran M1 až M6c je převedených (52 stochastických bran auditu a deterministické
zkoušky), nad nimi nástroj `cee gates` pro audit míry průchodu na semínkách. Python se nespouštěl.

### Návrh

| část | soubor | obsah |
|---|---|---|
| kontroly a běhy | `src/gates/m1.rs` … `m6c.rs` | `run_*` (scénář, semínko, délka jako v Pythonu), `check_*` (metriky a prahy Pythonu) a `batches()` (dávky pro audit) |
| metriky | `src/gates/metrics.rs` | zrcadlo `cee.v2.metrics`: `logistic_r2`, `establishment_fraction`, `isolation_by_distance`, `lexicon_profile`, `retention`, `morphology_profile`, `morphological_complexity`, `spearman`, `distinctive_variants`, `trace_shares`, `code_distance`, `hellinger`, … z historie, snímků a stavu světa |
| statistika | `src/gates/stats.rs` | `wilson_interval`, `binomial_cdf_lt`, `threshold_k`, `classify_rate`, `evaluate_seeds` (zrcadlo `tests/v2/gate_checks.py`, jednotkové testy proti tabulce z dokumentu 09) |
| report | `src/gates/mod.rs` | `Report` je seznam metrik (jméno, hodnota, `Cmp`, práh, prošla); kontroly nevrací první neúspěšné tvrzení, ale všechny metriky, takže vznikne tabulka „brána, metrika, hodnota, práh, prošla“ |
| audit | `src/gates/audit.rs`, `cee gates` | dávka = jeden běh scénáře a vyhodnocení bran, které z něj plynou (jako `BATCHES` v `scripts/v2_gate_rates.py`); tabulka průchodu, Wilsonův interval, zařazení, `k` pro `N = 10` a `N = 5`; chyba či pád enginu se počítá jako neúspěch semínka |
| testy | `tests/gates/main.rs`, `m1.rs` … `m6c.rs`, `common.rs` | jeden soubor na milník, semínka a pravidla k z N jednotlivých testů, sdílené běhy (`OnceLock`) |

Brány jsou v knihovně (ne v testech), aby je mohl spouštět i `cee gates`; testy mají semínka a pravidla k z N.
Všechny testy bran jsou `#[ignore]` (jsou stochastické a dlouhé), `cargo test --release` je tedy nespouští:

```
cargo test --release --test gates -- --ignored --test-threads=1            # všechny brány
cargo test --release --test gates -- --ignored --test-threads=1 m3b::      # jeden milník
cargo run --release --bin cee -- gates --seeds 101..120 -o audit.jsonl     # audit jako v dokumentu 09
cargo run --release --bin cee -- gates --seeds 1 --only m5 --metrics       # všechny metriky jednoho semínka
cargo run --release --bin cee -- gates --list                              # registr 52 bran
```

`--only` bere milník (`m4b`), dávku (`m4b_no_case`) nebo bránu (`m4b::exaptace`). Dávky `m2_phonology_triplet`
(`m2::metrika_6`, `m2::ruznost_seedu`) potřebují trojice semínek; audit je dělí na disjunktní trojice po sobě jdoucích semínek.
Brána `m4b::clen_vznikne` se v auditu počítá jako „člen na tomto semínku vznikl“ (v testu 1 až N−1 z 50 semínek).

### Odchylky od Pythonu

- **Povrchový tvar** (`phonology::surface`) metriky `lexicon_profile` a `lexicon_forms` už používají (R2a).
- **Počet mluvených skupin snímku** bez `keep_distances` Snapshot nemá (`group_ids` je prázdné); M6a a M6b ho berou ze součtu
  velikostí nářečí.
- **Přepsané zvukové změny** (`phonology.restructured`, M5 substrát) se čtou z příznaků `done` ve frontách kódu
  (`SoundCodeState::queues`), proces se hledá podle `world.variables.process`.
- **Dráhy inovací** mají čas v tiků, ne v letech; `logistic_r2` je na lineárním přeškálování času nezávislé.
- **Jména a klíče**: `world.processes[v].key` v Pythonu je `world.variables.key[v]`; kategorie jazyků M6c jsou první písmena
  jmen skupin jako v Pythonu.
- **Výkonový test** `test_vykon_rezimu_udoli` (údolí do 5 s) se nepřevádí (zadání: nic neměřit).
- **Negativní kontroly z dokumentu 09** (krok 5) se nepřevádějí kromě `bez_opisu_a_exaptace_clen_nevznikne`, která je
  ve zdrojovém souboru testů. Mají být jednorázové měření vypnutého mechanismu; `Parameters` už má `interference_weight`,
  `change_rates` a `taboo` jde nastavit na skupinách, takže převod je možný.
- Kontroly vracejí všechny metriky, ne první neúspěšnou: u pole hodnot (inventáře, délky slov) je to minimum a maximum
  přes skupiny; mezní tvrzení `a <= x <= b` je jedna metrika `Between`.
- `m1::two_regions` staví svět zkoušky přiblížení (M1 a M2) a zkouška porovnává proměnné, které existují v obou světech
  (zjemnění západu v Pythonu mohlo zakládat proměnné jen v jednom).

### Stav bran na této větvi (R2a ještě neintegrovala)

Jedno spuštění všech testů bran (`--ignored`, semínka dnešních testů): **50 prošlo, 12 neprošlo** (z 62 testů bran).
Neprošlé a jejich metriky (hodnota v Rustu, práh):

| test | metrika | Rust | práh |
|---|---|---:|---|
| `m1::velka_souhrnna_skupina_driftuje_mene_nez_mala_vesnice` | drift skupiny 1 000 000 (malá vesnice 200: 0,49) | 0,19 | < 0,01 |
| `m2::metrika_6` | počet ustálených změn (3 semínka dohromady) | 13 | >= 30 |
| `m2::zvukove_zmeny_se_siri` | medián počtu skupin na změnu / podíl reliktů | 1 až 1,5 / 0 až prázdný | >= 2 / 0,01 až 0,15 |
| `m3::sturtevantuv_paradox` | alternace bez vyrovnání / bez − s vyrovnáním | 0,28 / 0,001 | > 0,3 / > 0,1 |
| `m3::morfologizace` (k z 10) | prošla semínka 2/10 | 2 | >= 4 |
| `m3::produktivni_vzor` | nejnižší podíl produktivní koncovky / častá − vzácná nepravidelnost | 0,68 / −0,04 | > 0,8 / > 0 |
| `m3::analogie` | frekvence slov s analogií / průměr slovníku (semínko 1) | 1,10 | < 1 |
| `m5::s2_mesto` | produktivní podíl město − ostrov / nepravidelnost vzácných slov město / (ostrov/2) | 0,02 až 0,03 / 1,8 | > 0,1 / < 1 |
| `m5::s2_l2` | složitost města s L2 / (bez L2 / 2) | 2,0 (shodná) | < 1 |
| `m5::metrika_11` | korelace složitosti s podílem L2 / s populací | −0,12 až 0,08 / −0,45 až 0,35 | < −0,6 |
| `m6a::skola_zmrazena` | ustálení bez tisku / (s tiskem / 3), semínko 2 | 2,6 | < 1 |
| `m6b::ferguson` | rozdíl lidové řeči od psané − rozdíl v roce 1475 | −0,034 | >= 0 |

Ostatní brány (M1 kontinuum, hranice, metriky 7 a 8; M2 metriky 3 až 5; M3 zvukové metriky; celé M3b; M4 a M4b včetně
exaptace a členu; M5 přechod, substrát a výpůjčky; M6a škola; M6b migrace, superstrát, trh, loajalita, náboženství; M6c)
na semínkách dnešních testů prošly. Brány s `k` z `N` (exaptace, substrát S3, tabu) na jediném semínku někdy neprojdou
(audit jednoho semínka `1`: tabu, člen, exaptace, substrát), což je podle pravidla k z N v pořádku.

Co z toho plyne pro R2a (zjištěno čtením metrik, v enginu se nic neměnilo):

- **Drift**: malá vesnice (200) se za 1 000 let skoro ustálí (0,49) a velká skupina (1 000 000) driftuje 0,19 místo méně než
  0,01. Drift velké skupiny by měl být o dva řády nižší; podezření na zesílení šumu tlakem `conformity` nebo na škálu
  driftu (`sigma / sqrt(kohorta)`).
- **L2 nezjednodušuje morfologii**: složitost města s přistěhovalci je přesně stejná jako bez nich (poměr 2,0) a metrika 11
  nekoreluje s podílem L2. Chybí zjednodušení tvarů dospělými učícími se (interference ve tvarech a koncovkách).
- **Zvukové změny se ustalují málo a málo se šíří**: 13 ustálených změn na 3 jazyky (Python aspoň 30), medián 1 až 1,5 skupiny
  na změnu (aspoň 2), podíl reliktů je 0 (semínko 1) a u semínka 2 se neuzavřel žádný proces.
- **Alternace a analogie**: bez vyrovnání je alternací málo (0,28 místo > 0,3) a vyrovnání je nemění (rozdíl 0,001);
  podíl produktivní koncovky 0,68 (aspoň 0,8); zmorfologizovaných buněk skoro nevzniká (2 z 10 semínek).
- **Škola bez tisku** (semínko 2) zastavuje změnu méně než v Pythonu; diglosie (Ferguson) nechává lidovou řeč blíž psané
  než před zavedením školy.

### Co Rust zatím nemá v datech

| metrika | co chybí | co doplnit |
|---|---|---|
| délka slov, inventáře, homofonie (M2, M3, M3b, M4) | povrchový tvar slova (`surface`) | funkce `phonology::surface(world, group, root)` (podkladový tvar + živé procesy s pravděpodobností slova >= 0,5, analogický tvar) a volání v `gates::metrics::lexicon_profile` / `lexicon_forms` |
| počet mluvených skupin snímku (M6a, M6b) | `Snapshot::group_ids` bez `keep_distances` | vyplnit `group_ids` vždy (levné) nebo pole `spoken` |
| čas drah inovací | tiky místo let | jen poznámka, metrika 7 to nepotřebuje |
| negativní kontroly dokumentu 09 | přepínač `INTERFERENCE_WEIGHT` je v `Parameters`, ostatní (`SoundChange`, `Clarity`, `FunctionalLoad`) jde vynechat ze seznamu změn | jen převod měření, data jsou |

Vlastnost, která v Pythonu je a v Rustu se v bránách nepoužívá: `World.concept_frequencies` jako slovník je v Rustu sloupec
`ConceptColumns::frequency` s `NaN` pro nenastavené; brány berou pojmy s nenastavenou frekvencí za neexistující.

## Metaparametry: jeden zdroj pravdy

Metaparametry (`Parameters`, 66 polí: konstanty dynamiky, tabulky slovních úrovní, váhy tlaků, kanály a domény) se převezmou
**jednou při stavbě světa** a během běhu se nemění; později se budou nastavovat v UI. Výchozí hodnoty, druhy, popisy, skupiny
a meze jsou **jen v jednom souboru**, `src/cee/data/v2_parameters.json`. Skript `scripts/export_v2_parameters.py` ho vyrobil
jednorázově z dřívějšího `parameters.py` (hodnoty a komentáře `#:`); od té doby je soubor zdroj a upravuje se přímo,
skript už nemá co číst.

**Kdo ho čte.** Rust: `Parameters::default()` ho sestaví z vloženého textu (`data::PARAMETERS_JSON`, `include_str!`, jednou
a pak kopíruje), v kódu nezůstaly žádné opsané hodnoty. `Parameters::from_overrides` (přepisy z `WorldSpec.parameters`)
ověří každý přepis podle souboru a vrátí chybu s cestou `parameters.<jméno>[.<klíč>…]`: neznámé jméno, špatný druh (`očekáváno
číslo`, `očekávána tabulka …`), jméno mimo `keys`/`inner_keys`, hodnota mimo `min`/`max`; pak `normalize` doplní `channel_domains`
výchozími váhami a ověří pole gramatiky. Python: `cee.v2.parameters` bere výchozí hodnoty dataclassu z téhož souboru
(`_number`, `_table`; dataclass zůstane, dokud existuje Python engine), `check_override(jméno, hodnota)` dělá stejnou kontrolu
jako Rust a `spec._parameters` z ní skládá `Issue` s cestou `parameters.<jméno>`. Server: `GET /api/v2/schema` vrací navíc
`parameters` (`groups` a `items`).

**Formát souboru** (`"format": "cee-v2-parameters/1"`):

```json
{
 "format": "cee-v2-parameters/1",
 "groups": [{"id": "sound", "title": "Zvukové změny"}, …],
 "parameters": [
  {"name": "capital_prestige", "kind": "number", "default": 2.0, "description": "…", "group": "society"},
  {"name": "channel_domains", "kind": "table2", "default": {"elite": {"power": 3.0, …}, …}, "description": "…",
   "group": "contact", "keys": ["neighbor", …], "inner_keys": ["core", …], "min": 0.0}
 ]
}
```

* `name`: jméno pole `Parameters` (i klíč v `WorldSpec.parameters`); `description`: český popis; `group`: `id` ze `groups`
  (pro řazení a nadpisy v UI); `default`: výchozí hodnota podle druhu.
* `kind`: `number` (číslo), `table` (jméno → číslo), `table2` (jméno → jméno → číslo), `level_table` a `level_table2`
  (totéž, ale jména jsou slovní úrovně, které autor světa zadává jménem, např. `centralization_levels`; UI z nich nabízí výběr).
  Přepis tabulky nahradí celou tabulku (kromě `channel_domains`, kde se chybějící položky doplní výchozími).
* Meze, jen kde je dosavadní kód vynucuje (jinde klíč chybí): `keys` (povolená vnější jména), `inner_keys` (povolená vnitřní
  jména), `min`/`max` (číselné meze všech hodnot). Dnes: `channel_domains` (kanály, domény, váha nejméně 0) a `grammar`
  (`inner_keys` = `need`, `context`, `coverage`).

**`GET /api/v2/schema`**, klíč `parameters`: `{"groups": [...], "items": [...]}`; každá položka je záznam ze souboru plus
`levels` (seřazená jména úrovní) u `level_table`/`level_table2`. UI zobrazí položky podle skupin, upravené hodnoty pošle
v `WorldSpec.parameters` jako dřív; `POST /api/v2/validate` vrátí chyby s cestou `parameters.<jméno>`.

**Testy.** Rust `tests/parameters.rs` (soubor pokrývá všech 66 polí, výchozí hodnoty, přepis, chyby jména a druhu, meze,
shoda `keys`/`inner_keys` s konstantami), `tests/vectors.rs::vychozi_parametry` (shoda s hodnotami Pythonu). Python
`tests/v2/test_v2_parameters.py`, `test_v2_spec.py` (přepisy), `tests/test_api_v2.py` (schéma). Jednorázově se před smazáním
opsaných hodnot ověřilo, že všech 66 výchozích hodnot souboru shoduje s dřívějším Pythonem i s Rustem.


## Kalibrace proti Pythonu

Podle chování, ne bitově. Referenci spočítal `scripts/v2_reference_behavior.py` jedním během Pythonu (`CEE_NATIVE=0`, semínka 1 až 3,
sedm scénářů z `scripts/v2_digests.py`; výsledek `tests/v2/data/reference_behavior.json`). Rust počítá totéž příkazem
`cee behavior [scénář ...] [--seeds 1..3] [-o soubor.json]` (`src/behavior.rs`, stejný tvar výstupu); `cee behavior region-square
--seeds 101..104` měří kontinuum čtyř regionů z dokumentu 14 a scénář `valley-50-open` je údolí s otevřeností 0,5.
Souhrn: inovace (různé varianty) a ustálení/zánik podle druhu změny, fonologizovaná slova, retence slovní zásoby na konci, počty
nářečí a jazyků a vzdálenost nejbližších sousedů ve snímcích (roky 200, 500, 1000, 1500, 2000), přechody jazyka (počty událostí).

### Metriky Rust / Python (průměr ze semínek 1 až 3)

| scénář | inovací (varianty) | ustálení | zánik | fonologizovaná slova | retence | nářečí / jazyků na konci | sousedé na konci |
|---|---|---|---|---|---|---|---|
| phonology (1000 let) | 274 / 274 | 0,3 / 0,3 | 221 / 221 | 11 / 11 | 1,00 / 1,00 | 1 / 1 | 0,003 / 0,003 |
| morphology (1000) | 366 / 368 | 47 / 56 | 293 / 287 | 63 / 66 | 0,877 / 0,860 | 2,0 / 1 | 0,051 / 0,056 |
| syntax (1000) | 398 / 399 | 105 / 89 | 306 / 305 | 157 / 149 | 0,883 / 0,868 | 2,0 / 1 | 0,050 / 0,055 |
| grid-5x5 (1000) | 1149 / 1163 | 971 / 1035 | 490 / 489 | 3531 / 3537 | 0,744 / 0,740 | 25 / 1 | 0,210 / 0,214 |
| shift (900) | 715 / 716 | 145 / 146 | 614 / 613 | 358 / 353 | 0,903 / 0,908 | 3,3 / 1 | 0,061 / 0,055 |
| island-city (800) | 723 / 729 | 333 / 320 | 776 / 771 | 528 / 554 | 0,901 / 0,907 | 3,3 / 1 | 0,047 / 0,044 |
| valley-50 (2000) | 3601 / 3635 | 24253 / 24500 | 2171 / 2192 | 78543 / 78743 | 0,552 / 0,548 | 50 / 41,3 vs 39 jazyků | 0,328 / 0,333 |

(Ve sloupci nářečí / jazyků je pro Rust i Python totéž číslo, kde se shodují; u phonology až shift se liší jen počtem nářečí
v rámci rozptylu semínek 1 až 3: Rust 2,0 / 2,0 / 3,3 / 3,3, Python 2,7 / 2,3 / 3,7 / 2,7.) Všechny rozdíly jsou v rozptylu
semínek (do 10 %); u nejmenších počtů (ustálení v morphology a syntax) kolísá i Python mezi semínky o víc než rozdíl enginů.

**Před** opravou (první běh `cee behavior`) vycházelo u inovací 1,3 až 2,6krát víc než v Pythonu (grid-5x5 2502 proti 1187,
valley-50 9513 proti 3625). Nebyla to chyba enginu: Rust počítal události `innovation`, referenční skript různé varianty
(stejná varianta ve víc skupinách nebo po zániku znovu je jedna). Ustálení, zánik, retence i vzdálenosti se shodovaly už tehdy,
takže dynamika byla stejná. Po sjednocení definice (Rust počítá různé varianty) jsou čísla v tabulce.

### Příčiny rozdílů

- **Rychlost rozrůzňování: v enginu žádná odchylka od Pythonu.** Valley-50 dává v Pythonu na semínkách 1 až 3 39 jazyků a sousedy
  0,333, v Rustu 41 a 0,328. Rozdíl, který zadání uvádělo (0,35 proti 0,29), vznikl srovnáním různých běhů: 0,29 platí pro mřížku
  5×5 po 3000 letech (doc. 05), kdežto údolí 10×5 po 2000 letech dává 0,33 v obou enginech. Rozdíl po 1000 letech 5×5
  (0,210 Rust / 0,214 Python) je nulový.
- **Příčina 41 jazyků je scénář, ne engine.** `village_grid` má otevřenost 0,1; kalibrace kontinua (doc. 14) ukázala, že s ní
  se sousedé rozcházejí příliš a 80 km se rozpadne na čtyři jazyky, a zvolila 0,5 jen pro `region_world`
  (`Parameters.village_openness`). `village_grid` zůstal na 0,1, protože na něm stojí brány M1 až M6 a otisky; je to stresový
  scénář, ne model reálné krajiny. Při otevřenosti 0,5 (`valley-50-open`, 2000 let, semínka 1 až 3): jeden jazyk, sousedé
  0,098 (pásmo atlasů 0,05 až 0,15), 47 až 50 nářečí (pozorovatel dělí už od 0,05), retence 0,73 za 2000 let, tedy
  0,86 za tisíciletí (cíl ze Swadeshe asi 0,86 až 0,88).
- **Kontinuum čtyř regionů** (`region_world`, otevřenost 0,5, `cee behavior region-square --seeds 101..104`, sousedé v roce
  1000 / 2000 / 3000; přes hranici a vzdálené v roce 3000; jazyků vždy 1):

| | sousedé 1000 | 2000 | 3000 | přes hranici 3000 | vzdálené 3000 |
|---|---:|---:|---:|---:|---:|
| Rust (101..104, průměr) | 0,059 | 0,061 | 0,076 | 0,197 | 0,243 |
| cíl doc. 14 (pásmo 0,05 až 0,15; pořadí; 1 jazyk) | | pásmo | pásmo | | |
| doc. 14 (Python z 31. 10., před stálou variabilitou) | 0,025 | 0,048 | 0,061 | 0,153 | 0,194 |

  Pásmo atlasů, pořadí sousedé < přes hranici < vzdálené a jeden jazyk na 80 km platí. Od doc. 14 přibyla stálá variabilita
  protojazyka (už v roce 200 jsou sousedé 0,05 v Rustu i Pythonu), proto je rok 1000 vyšší než tehdejších 0,025; růst 2000 → 3000
  je 24 % (doc. 14: 27 %, kritérium rovnováhy +10 % se nesplňuje v žádném z nich, doc. 14 to uvádí jako otevřenou otázku).
- **Drobnosti bez zásahu:** `shift` a `island-city` nemají u skupin bez území (přistěhovalci) polohu, vzdálenost sousedů se tam
  nepočítá (u shift 0 v roce 200).

Změny enginu proto nejsou žádné; konstanty v `v2_parameters.json` se neměnily (nic nenasvědčuje, že by odchylka byla v konstantě,
a doporučení změnit `village_openness` pro `village_grid` by rozbilo prahy bran M1 až M6, které se měnit nesmějí).

### Audit bran na semínkách 101 až 120 (`cee gates`)

Míra průchodu Rust / Python (`09-zpevneni-bran.md`, 20 semínek). Stejná (rozdíl nejvýš 2 z 20) je 44 z 52 bran; plný výpis je
v `cee gates --seeds 101..120`. Odlišné:

| brána | Rust | Python | poznámka |
|---|---:|---:|---|
| `m4b::exaptace` | 7/20 | 15/20 | **nižší**: skupin s exaptací 0 až 3 (práh 4 z 6) |
| `m5::s3_substrat` | 4/20 | 11/20 | **nižší** |
| `m4::jespersen` | 4/20 | 8/20 | **nižší** (v obou slabá brána, ochrana proti regresi) |
| `m6b::migrace` | 12/20 | 15/20 | nižší, v pásmu křehkých |
| `m3b::tabu` | 9/20 | 11/20 | v rozptylu |
| `m4b::clen_vznikne` | 4/20 | (20/20 ve starém znění „2 ze 3“) | dnešní znění „1 až N−1 z 50“ čeká asi 20 % (doc. 05 řádek o členu); 20 % odpovídá |
| `m6b::superstrat` / `jazyk_trhu` | 19 / 20 | 16 / 16 | vyšší |
| `m4::velky_cyklus` | 17/20 | 15/20 | vyšší |
| `m2::metrika_6`, `ruznost_seedu` | 6/6 trojic | 20/20 | Rust audit dělí 20 semínek na 6 trojic |

Všech 62 testů bran (`cargo test --release --test gates -- --ignored --test-threads=1`) prošlo.

### Co zbývá

- **Exaptace, substrát S3 a Jespersen** mají v Rustu znatelně nižší míru průchodu než v Pythonu, i když souhrnné metriky
  výše sedí a kód `strength`, `residual_exponent`, `compensation` je přepis bez zjevné odchylky. Příčina nenalezena; podezření:
  jiný proud náhody u stálé variability (`variation.rs` místo numpy) mění startovní stav těchto malých světů o šesti vesnicích
  a dolní okraj brány (4 skupiny z 6) je citlivý, nebo odchylka v tlaku na konstrukce. Pro dohledání je potřeba referenční
  běh Pythonu na `exaptace` (události `exapted` po skupinách) a `grammaticalized`, což tato kalibrace (jediný běh) neobsahovala.
- Referenční skript Pythonu počítá různé varianty, ne události `innovation`; počty událostí z Pythonu se tedy nedají srovnat.
- `village_grid` s otevřeností 0,5 (nebo kalibrace kontinua na `village_grid`) by vyžadovala nový audit bran M1 a nová semínka;
  neděláno (prahy a semínka se nemění).


## Smazání Pythonu v2

Uživatel schválil smazání Python enginu v2 (větev `engine-v2-remove-python`). Server, projekty, úložiště a engine v1
(`src/cee/engine`, `pipeline.py` …) zůstávají v Pythonu a nezměnily se.

### Co zmizelo

| oblast | rozsah |
|---|---|
| `src/cee/v2` (simulace, svět, změny, tlaky, přenos, fonologie, morfologie, syntax, pozorování, export, scénáře, události, polity, pozadí, `native.py`, `concept_data.py`, `vocabulary.py` …) | 68 souborů, asi 24 600 řádků |
| `tests/v2` (brány M1 až M6c, zlatá data, jádra, otisky, kontrolní body …) | 95 souborů, asi 14 750 řádků, deset `golden_*.json.gz` (3,2 MB) |
| `scripts/` (otisky, zlatá data, profily, kalibrace, audit, export dat z Pythonu) | 35 skriptů, asi 7 000 řádků |
| `rust/cee_core`: vazba PyO3 (`python.rs`, `*_python.rs`, `python_pools.rs`, feature `python`, `pyproject.toml`) a nepoužitá jádra `clarity`, `sites`, `semantic_index`, `support` | 12 souborů, asi 6 900 řádků |

### Co zůstalo v Pythonu a proč

| soubor | obsah |
|---|---|
| `src/cee/v2/spec.py` | schéma popisu světa (pydantic `WorldSpec` a události bez `.event()`/`.custom()`), `Issue`, `SpecError`, `errors`, `warnings`, `parse` (české zprávy pydanticu), `levels`, `EVENT_KINDS`, `FORMAT`, `check_parameters`, `vocabulary_options`; UI z něj bere JSON schéma formuláře |
| `src/cee/v2/parameters.py` | čtení `v2_parameters.json` (`parameter_schema`, `check_override`, `default_levels`): schéma pro UI a ověření přepisů s cestou k poli i u vnořených tabulek. Rust má vlastní ověření téhož souboru (první chyba), Python vrací všechny |
| `src/cee/v2/runner.py` | vlákno běhu, snímky, zrušení nad vazbou `cee_engine_py`; `check` = schéma a přepisy v Pythonu, zbytek v Rustu |
| `src/cee/api/v2.py` | endpointy `/api/v2` (schema, validate, runs); `validate` volá `runner.check` |
| `src/cee/data/v2_*.json` | data jsou v Rustu vložená přes `include_str!`, takže zůstávají; `v2_segments.json` je odvozen z PanPhon (David R. Mortensen a kol., MIT) a atribuce v dokumentu 19, oddíl Data, platí dál |

Sémantické ověření (`spec.check`) je v Rustu: `cee_engine::spec::check` vrací všechny chyby s cestou (`events.3.year`,
`regions`, `languages.0.words.hand`, `concepts.1.related.0.concept`, `parameters.x` …) a varování, vazba ho nabízí jako
`check_spec`. Slova se ověřují rozborem IPA v Rustu, takže zprávy o hláskách jsou stručnější než dřív (slovo s neznámou
hláskou je „engine nezná některou hlásku ve slově“; zpráva „zapsalo by se jako …“ zůstala jen pro zápisy, které rozbor
zkrátí). Zkušební provedení událostí běží na světě po `Simulation::new`, tedy ve stavu, ve kterém začíná běh.

`cee_core` zůstal samostatným crate: i bez Pythonu má 15 modulů (asi 11 700 řádků) a `cee_engine` z něj volá banku tvarů,
procesy, přenos, tlaky a indexy. Sloučení by jen přesunulo soubory, proto se neprovedlo.

### Závislosti

`numpy` odešel z hlavních závislostí `pyproject.toml` (používá ho už jen datový skript
`build_v2_concept_frequencies.py`, který má extra `data`). `panphon` zůstává, protože ho importuje engine v1
(`cee.engine.phonology`). `networkx`, `lingpy`, `pydantic`, `pyyaml` používá v1 nebo server. Značka `slow` v pytestu zanikla
s Python branami.

### Náhrady smazaných testů a skriptů

| smazáno | náhrada |
|---|---|
| `tests/v2/test_v2_m*_gate.py`, `gate_checks.py`, `scripts/v2_gate_rates.py` | `cargo test --release --test gates -- --ignored --test-threads=1`, `cee gates` (audit na semínkách) |
| zlatá data, `v2_golden_*.py`, `test_v2_golden_*.py`, `test_v2_native_*.py`, otisky `v2_digests.py`, kontrolní body Pythonu | Rust testy `vectors.rs`, `engine.rs`, `r1c.rs`, `r2a.rs`, `sound.rs`, `transfer.rs`, `society.rs` a determinismus téhož semínka; uložené vektory jsou ve `rust/cee_engine/tests/fixtures/` |
| `v2_reference_behavior.py`, `v2_calibrate*.py`, `v2_region_continuum.py`, `v2_measure_variation.py`, `v2_innovation_stats.py` | `cee behavior [scénář] [--seeds 1..3]`, `cee behavior region-square`; výsledek Pythonu zůstal jako `tests/v2/data/reference_behavior.json` |
| `v2_kingdom.py`, `v2_revival.py`, `v2_state_border.py`, `v2_typology.py`, `v2_reachability.py`, `v2_erosion_chain.py`, `v2_ending_erosion.py`, `v2_prosody_sensitivity.py` | `cee scenario <jméno> --until <rok>` a `cee run <spec.json>`; ruční pokusy se dělají nad scénáři a `WorldSpec`, žádná jednotlivá náhrada |
| `v2_timing.py`, `v2_profile_*.py`, `v2_spec_timing.py` | žádná náhrada (profilování Python enginu); měření času v Rustu dělá `cargo test --release` a `cee run` s `time` |
| `v2_compare_tick0.py`, `export_v2_rust_vectors.py` | žádná náhrada (porovnání Rustu s Pythonem už nemá s čím) |
| `export_v2_data.py`, `export_v2_parameters.py` | žádná náhrada; `v2_segments.json`, `v2_defaults.json`, `v2_grammar.json`, `v2_parameters.json` jsou teď primární data a upravují se ručně (parametry podle formátu v oddíle Metaparametry) |
| `tests/v2/test_v2_spec.py` (ověření popisu světa) | `tests/test_v2_spec.py` (přes vazbu) a `rust/cee_engine/tests/spec_check.rs` |
| `tests/v2/test_v2_parameters.py` | `rust/cee_engine/tests/parameters.rs` a test přepisů v `tests/test_v2_spec.py` |

Skripty `build_v2_*.py` zůstaly (data z otevřených zdrojů); `build_v2_concepts.py` a `build_v2_core_semantics.py` čtou výchozí
pojmy z `v2_defaults.json` místo z `cee.v2.scenarios`.

### Poznámka k historii

Komentáře v `cee_core` a ostatní dokumenty `docs/engine-v2/` dál popisují Python jako zdroj chování (porovnání, kalibrace).
Je to historie; Python engine najdeš v gitu před commitem „Delete the Python engine v2“.
