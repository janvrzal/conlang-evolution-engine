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
├── cee_core/              jádra výpočtů + vazba PyO3 (feature `python`, výchozí zapnutá)
└── cee_engine/            čistý Rust, žádné PyO3; závisí na cee_core bez feature `python`
    ├── src/lib.rs         moduly (viz níže)
    ├── src/bin/cee.rs     CLI `cee`
    └── tests/             vectors.rs (vektory z Pythonu), engine.rs (kostra), fixtures/
```

- **`cee_core`** zůstává a dál slouží Python enginu (maturin). `cee_engine` z něj volá jádra:
  banka tvarů a tabulky procesů (`bank`, `process`), řídké fondy (`pools::Cells` je uložení
  bloků živých proměnných), součty jako `np.sum` (`assess::pairwise_sum`), SplitMix
  (`transmission::splitmix64`, `hash_normal`). Další jádra (`transmission`, `pressures`, `index`,
  `candidates`, `sites`, `form_assess` …) napojí agenti R1 na model světa.
- **`default-members = ["cee_engine"]`**: `cargo test` a `cargo clippy` v `rust/` stavějí čistý Rust.
  Rozšíření pro Python se staví z `rust/cee_core` přes maturin (wheel pak leží v `rust/target/wheels`).

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

Návrh v `parallel.rs`; jedno použití: míry inovací přes skupiny ve fázi 2. Pravidla: souběh jen ve čtení
(výsledky v pořadí vstupu), zápis sekvenčně v kanonickém pořadí, náhoda z klíče, součty po blocích pevné
velikosti (`ordered_sum`). Výsledek je stejný pro 1 i více vláken (test `vysledek_nezavisi_na_poctu_vlaken`);
počet vláken: `RAYON_NUM_THREADS` nebo `cee … --threads N`.

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
`v2_segments.json`, `v2_grammar.json`, `v2_defaults.json` (skript `scripts/export_v2_data.py`).
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
cee run <spec.json> -o export.json [--threads N]
cee scenario <jméno> --until <rok> [-o export.json] [--checkpoint stav.bin]
cee export-tick0 <scénář|spec.json> [-o tick0.json]
cee scenarios
```

Porovnání ticku 0 s Pythonem: `PYTHONPATH=src python scripts/v2_compare_tick0.py` (volitelně
`--with-variation`, nebo cesta k `WorldSpec`). Vektory z Pythonu pro testy:
`PYTHONPATH=src python scripts/export_v2_rust_vectors.py`.

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
| **R1a** | přenos (`prepare`, `transmit`, míšení, selekce, drift), tlaky, aktivace procesů a analogií, záznamy milníků, sledování slovní zásoby po přenosu |
| **R1b** | zvukové změny a kandidáti, index prostředí, přestavba (fonologizace), sledování slovní zásoby, banka tvarů a tabulky procesů (registrace, hodnocení) |
| **R1c** | morfologie, syntax, prozodie, sémantické a lexikální změny, místa změn a návrh inovací (`Change`), souběžná variabilita protojazyka (`variation.rs`), větší slovník a vlastní pojmy (`vocabulary`) |
| **R1d** | hotovo kromě drobností v oddílu R1d (viz [R1d](#r1d-události-kontakt-společnost-a-pozorování)); chybí jen přenos výpůjček přes kanály v přenosu (R1a) a v morfologii (R1c), které čtou rozhraní `contact` |
| **R2** | integrace, brány v Rustu, porovnání chování s Pythonem, vazba pro server (`runner.py` → Rust), smazání Pythonu v2, `Simulation::branch` |

### Známá omezení a odchylky od Pythonu

- `Parameters` má **66 polí** (zadání uvádělo 68; počet odpovídá `dataclasses.fields(Parameters)` v tomto
  stavu repozitáře, test `vychozi_parametry` porovnává názvy i hodnoty s Pythonem).
- Rozbor IPA je slovník symbolů + nejdelší shoda (ne PanPhon). Na slovech všech protojazyků scénářů a ve
  vektorech sedí; vzácné nezvyklé kombinace značek vrací chybu.
- `gravity_pairs` používá `f64::hypot` místo `math.dist` (rozdíl v posledním bitu možný; porovnání ticku 0
  používá toleranci 1e-12).
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
