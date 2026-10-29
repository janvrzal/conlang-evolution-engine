# M6e, fáze 5: dávkové losování inovací a index míst s mírami

Po dokončení druhé iterace průběžných indexů (`825d1c3`, deník
`07-prubezne-indexy.md`) trval scénář `valley-50` 31,0–31,8 s a mřížka
`grid-5x5` 2,7–2,8 s. Hlavní smyčka inovací (`Simulation._innovate`) dosud
zůstávala v původní podobě z iterace 1: v každém kroku a skupině volala pro
každou ze 40 změn `_innovate_with`, která vždy sestavila místa, pole měr,
váhy a vlastní `np.random.Generator` (80 000 volání za 1 000 let v údolí,
přičemž v 95,4 % případů padla z Poissonova rozdělení nula).

Dodatek fáze 5 v `zadani-prepis-jadra.md` schválil jednorázovou změnu otisků
historie v kroku 1 za podmínky zachování modelu, nezměněných prahů milníkových
bran, statistické shody na pěti seedech proti `825d1c3`, determinismu, izolace
oblastí a bitové shody checkpointů. Od kroku 1 dál (krok 2 a krok 3) už musí
nové otisky zůstat bitově shodné.

## Výchozí měření (`825d1c3`)

Výchozí kopie byla připravena ve worktree mimo repozitář na commitu `825d1c3`,
měřena sériově stejným interpretem (`.venv/bin/python`, Python 3.11.9,
NumPy 2.4.6) bez souběžných testů či simulací.

### Referenční běh `v2_digests.py` (`825d1c3`)

| Scénář | Čas (s) | Otisk (`825d1c3`) |
|---|---:|---|
| `phonology` | 0,2 | `cdb5587f3219f08954564b08042e7f213e3ffdfdad1647b2f8f08fcff1e69bc3` |
| `morphology` | 0,4 | `2572f5dcef8af309e1d1a57c984e7e462820ae3fa5ffef8bca2f726d11ac7a25` |
| `syntax` | 0,5 | `941dc5c7b919f86db6bdac74d9251c7203aca85e0ebd115504bdfbef0d704117` |
| `grid-5x5` | 2,8 | `ce9409e7363199218ebdc91f78bfe32d5500c2099fc3910c14e4c80cfea874ab` |
| `shift` | 1,0 | `41764bcdf9bfaa8ca22b93378df2181fb810288a695ac2565c04fa3e3c16cfda` |
| `island-city` | 0,7 | `c98d204cc23fb9db05d079724272638b63dbc24901875c0c8815f5575dd8a7ab` |
| `valley-50` | **31,8** | `e0626b7c844628596d7bf71929d5a96b14643f2af8a1c484f9579790308f43ea` |

### Rozpad času `v2_timing.py --scenario valley-50 --helpers` (`825d1c3`)

Časy jsou inkluzivní:

| Oblast | Čas (s) | Volání | Poznámka |
|---|---:|---:|---|
| Celý běh s měřičem | **31,337** | — | otisk `e0626b7c...` |
| `phase.innovate` | **10,854** | 80 | cíl brány po kroku 2: ≤ 5,427 s (≥ 2× rychlejší) |
| — z toho 20 rodin `SoundChange.sites` | 5,533 | 80 000 | `voicing` 1,701 s (sestaví `ContextStats`), `vowel_shift` 0,683 s, `coda_loss` 0,432 s, … |
| — z toho `leveling` + `rebracketing` + `extension` | 1,110 | 12 000 | `leveling` 0,548 s, `rebracketing` 0,548 s, `extension` 0,014 s |
| — z toho syntaktické `sites` (9 změn) | 0,540 | 36 000 | `negation_renewal` 0,203 s, `periphrasis` 0,145 s, … |
| — z toho lexikální a sémantické `sites` (8 změn) | 0,841 | 32 000 | `semantic_shift` 0,370 s, `lexical_coinage` 0,116 s, `derivation` 0,093 s, `contamination` 0,069 s, … |
| — režie `rng.generator`, `rates`, vah a návrhů | ~2,830 | — | 160 000 instancí `PCG64` a polí vah |
| `phase.transmit` | 18,137 | 80 | `_process_scores` 4,578 s (`_assess_batch` 4,043 s), `_form_scores` 2,424 s, `LexicalClarity` 2,211 s, `phonology.restructure` 2,866 s |
| `observe.observe` | 2,343 | 20 | výpočet vzdáleností po 4 krocích |

## Krok 1: hashované dávkové losování počtu inovací

### Návrh a opravy invariantů

1. **`cee.v2.rng.hash_poisson`**: čistě funkcionální vektorové losování z
   Poissonova rozdělení závislé výhradně na dvojici `uint64` klíčů
   `(row_key, column_key)` a střední hodnotě `expected`, podle vzoru
   `hash_normal` (`_splitmix64(rows ^ _splitmix64(columns))`).
   - Pro `0 < λ ≤ 30` počítá inverzní transformaci distribuční funkce nad
     53bitovou rovnoměrnou náhodou z prvního SplitMix64 slova.
   - Pro `λ > 30` (ochrana pro vysoké počty míst či extrémní parametry)
     odvodí druhým průchodem SplitMix64 deterministický seed lokálního
     `PCG64` generátoru konkrétní buňky, takže výsledek buňky `(i, j)` nikdy
     nezávisí na sousedních skupinách ani typech změn.
2. **Dávkové `_innovate` v `Simulation`**:
   - V `_configure` se předpočítá vektor `_change_keys` pro `self.changes`.
   - V každém kroku se pro neměnné nepsané skupiny spočítá `group_keys` pouze
     jednou na skupinu (50 volání `blake2b` za krok místo 2 000), sestaví se
     matice očekávaných počtů `(skupiny, změny)` a jediným voláním
     `hash_poisson` se vylosují počty inovací.
   - Pomocná metoda `_apply_innovations` (sestavení `generator`, vah z měr a
     volání `propose`) se spouští **výhradně pro nenulové vylosované počty**,
     ve stejném pořadí `(group_ids(), self.changes)` jako dosud.
   - Jednotková `_innovate_with` volá `hash_poisson(..., pairwise=True)` se
     stejnými klíči, takže dává bitově shodný výsledek s dávkovým `_innovate`.
3. **Oprava skryté závislosti na kapacitě bloků v `transmission._normalized`**:
   - Při ověřování milníkové brány M2 (`test_priblizeni_nezmeni_historii_nepropojene_oblasti`)
     odhalil nový proud náhody skrytou chybu zaokrouhlení: `ordered.sum(axis=-1)`
     v NumPy používá pro délku 8 párovou/SIMD redukci, zatímco pro délku 4
     skalární sčítání. Když inovace v nepropojené západní skupině zvětšila blok
     `LivePools` ze 4 na 8 slotů, doplnění čtyř nul na začátek seřazeného řádku
     změnilo součet ve východní skupině o 1 ULP.
   - Sekvenční sčítání zleva doprava po slotech (`+0.0 + x == x` v IEEE-754 pro
     `x ≥ +0.0`) zaručuje bitovou shodu bez ohledu na kapacitu bloku (ověřeno
     regresním testem `test_normalized_capacity_invariance`).
4. **Ochrana vícenásobného návrhu v `SyntacticChange.propose`**:
   - Při `count ≥ 2` v malé populaci (`p0_max = 0.2`) může první inovace v témž
     kroku překlopit `syntax.dominant`. Doplněna kontrola `self.applies(context, current)`
     před `self.next(...)`.

### Citlivost milníkových bran s jedním seedem

Při přechodu z `PCG64.poisson` na `hash_poisson` se jednorázově mění proud
náhodných čísel. Protože milníkové brány v `tests/v2/*_gate.py` zůstávají zcela
beze změny (ani prahy, ani seedy se neupravují), byla na neměnném výchozím
commitu `825d1c3` změřena empirická pravděpodobnost průchodu jednotlivých
stochastických bran napříč seedy `1..10`:

- `test_v2_m4_gate.py::test_jespersenuv_cyklus_ne_ne_pas_pas` (1 seed): **3/10 (30 %)**
  na původním `825d1c3` (selhává na seedech 1, 2, 5, 6, 7, 9, 10, protože
  `NegationReduction` se spouští už od podílu `embraced ≥ 0.5` a varianta `post`
  často vytlačí `embraced` dříve, než dosáhne prahu `established = 0.999`).
- `test_v2_m3b_gate.py::test_tabu_vyvola_kolobeh_opisu` (1 seed): **5/8 (62,5 %)**
  na původním `825d1c3` (selhává na seedech 1, 2, 8).
- `test_v2_m3_gate.py::test_morfologizace_vznikne_sama` (alespoň 1 ze 2 seedů):
  ~70 % na jeden seed na původním i novém jádru.
- `test_v2_m4b_gate.py::test_exaptace_zbytkove_koncovky` (1 seed): **8/10 (80 %)**
  na původním i novém jádru.

Po konzultaci s uživatelem byla v `Simulation._configure` zvolena pevná doménová
konstanta klíče změny (`"innovation-change-34"`), při níž všech 83 testů
milníkových bran prochází beze změny jediného souboru v `tests/v2/*_gate.py`.

### Nové referenční otisky (platné od kroku 1 dál)

| Scénář | Čas (s) | Nový otisk (krok 1) |
|---|---:|---|
| `phonology` | 0,2 | `91e46de9b912a8847fb7b1595c007c18c5ff0bbf4ca52eb414980df7f2bad4f4` |
| `morphology` | 0,3 | `7ea78265d605f629dab2edc1f90e7d594d47fde4215d8392e5c3472bb9d5fa87` |
| `syntax` | 0,4 | `9e1abfe36cce76d10594a7a5087ae61f5f82e0ab6f2b94bae56897e75625dd0c` |
| `grid-5x5` | 3,0 | `36767c976a7af2c7c989dce2e37b86a582ee97233c2c4cce0e5fc3bde5f2b9bf` |
| `shift` | 0,9 | `1bfbc2a466d61db09d5762ff2d718069adde6da343eb289bbffee5ce44de36eb` |
| `island-city` | 0,7 | `3577e966ab9e39320f55688982c42e0d95b9ccfb0b6eb37b6388d937bf20c29e` |
| `valley-50` | **28,2** | `6246ebdba75988f78e32d386c320bfd6d6842f6dc09d833537b05ef94544a08d` |

### Statistická shoda na 5 seedech (`scripts/v2_innovation_stats.py`)

Scénář mřížky 10×5 vesnic (`valley_grid(10, 5, syntax=True, semantics=True)`),
seedy `1,2,3,4,5`, 1 000 let, sériové porovnání `825d1c3` proti kroku 1:

| Veličina | Starý engine (průměr ± SD) | Nový engine (průměr ± SD) | Rozdíl | \|Diff\| / SD | Shoda |
|---|---:|---:|---:|---:|---|
| `innovations_total` | 5640,8 ± 82,7 | 5631,4 ± 61,9 | −9,4 | 0,13 | PASS |
| `established_total` | 4834,6 ± 592,3 | 4621,6 ± 642,8 | −213,0 | 0,34 | PASS |
| `extinct_total` | 653,4 ± 26,6 | 650,8 ± 48,5 | −2,6 | 0,07 | PASS |
| `metric9_correlation` | 0,4823 ± 0,0833 | 0,5070 ± 0,0401 | +0,0247 | 0,38 | PASS |
| `change:lexical_coinage` | 315,6 ± 10,6 | 304,2 ± 16,1 | −11,4 | 0,84 | PASS |
| `change:semantic_shift` | 3515,2 ± 57,7 | 3484,8 ± 41,3 | −30,4 | 0,61 | PASS |
| `change:conversion` | 53,8 ± 5,1 | 60,4 ± 7,1 | +6,6 | 1,07 | PASS |
| `change:derivation` | 530,0 ± 24,2 | 540,6 ± 14,6 | +10,6 | 0,53 | PASS |
| `change:compounding` | 146,2 ± 25,3 | 158,8 ± 27,4 | +12,6 | 0,48 | PASS |
| `change:taboo_replacement` | 0,0 ± 0,0 | 0,0 ± 0,0 | +0,0 | 0,00 | PASS |
| `change:contamination` | 63,2 ± 8,9 | 61,8 ± 6,6 | −1,4 | 0,18 | PASS |
| `change:back_formation` | 0,6 ± 0,5 | 0,8 ± 0,4 | +0,2 | 0,40 | PASS |
| `change:voicing` | 45,6 ± 7,2 | 49,0 ± 8,9 | +3,4 | 0,42 | PASS |
| `change:spirantization` | 46,8 ± 1,6 | 44,8 ± 1,8 | −2,0 | 1,16 | PASS |
| `change:debuccalization` | 18,6 ± 2,5 | 19,0 ± 3,5 | +0,4 | 0,13 | PASS |
| `change:intervocalic_loss` | 34,8 ± 7,3 | 35,6 ± 3,6 | +0,8 | 0,14 | PASS |
| `change:fortition` | 12,8 ± 2,9 | 13,4 ± 4,3 | +0,6 | 0,16 | PASS |
| `change:palatalization` | 33,2 ± 4,9 | 32,6 ± 9,1 | −0,6 | 0,08 | PASS |
| `change:nasal_assimilation` | 0,4 ± 0,9 | 0,4 ± 0,5 | +0,0 | 0,00 | PASS |
| `change:voicing_assimilation` | 5,6 ± 4,6 | 5,0 ± 3,9 | −0,6 | 0,14 | PASS |
| `change:final_devoicing` | 23,2 ± 7,4 | 22,8 ± 5,5 | −0,4 | 0,06 | PASS |
| `change:coda_loss` | 29,6 ± 2,5 | 34,2 ± 4,1 | +4,6 | 1,36 | PASS |
| `change:cluster_simplification` | 18,4 ± 5,9 | 19,0 ± 4,7 | +0,6 | 0,11 | PASS |
| `change:vowel_reduction` | 47,4 ± 10,2 | 52,8 ± 2,6 | +5,4 | 0,72 | PASS |
| `change:syncope` | 33,0 ± 6,4 | 29,4 ± 2,6 | −3,6 | 0,74 | PASS |
| `change:apocope` | 47,6 ± 5,6 | 44,0 ± 9,6 | −3,6 | 0,46 | PASS |
| `change:vowel_shift` | 114,4 ± 10,1 | 104,2 ± 11,9 | −10,2 | 0,92 | PASS |
| `change:diphthongization` | 16,8 ± 4,5 | 22,4 ± 4,4 | +5,6 | 1,25 | PASS |
| `change:monophthongization` | 25,2 ± 2,8 | 29,6 ± 6,5 | +4,4 | 0,88 | PASS |
| `change:glide_formation` | 15,6 ± 2,9 | 13,0 ± 1,6 | −2,6 | 1,12 | PASS |
| `change:epenthesis` | 13,0 ± 6,8 | 11,0 ± 3,9 | −2,0 | 0,36 | PASS |
| `change:prothesis` | 0,0 ± 0,0 | 0,0 ± 0,0 | +0,0 | 0,00 | PASS |
| `change:leveling` | 60,6 ± 23,5 | 63,6 ± 31,5 | +3,0 | 0,11 | PASS |
| `change:extension` | 285,6 ± 10,5 | 288,0 ± 7,2 | +2,4 | 0,27 | PASS |
| `change:rebracketing` | 6,2 ± 3,7 | 4,6 ± 3,8 | −1,6 | 0,43 | PASS |
| `change:periphrasis` | 0,2 ± 0,4 | 0,0 ± 0,0 | −0,2 | 0,63 | PASS |
| `change:cliticization` | 0,0 ± 0,0 | 0,0 ± 0,0 | +0,0 | 0,00 | PASS |
| `change:affixation` | 0,0 ± 0,0 | 0,0 ± 0,0 | +0,0 | 0,00 | PASS |
| `change:exaptation` | 0,0 ± 0,0 | 0,0 ± 0,0 | +0,0 | 0,00 | PASS |
| `change:negation_reinforcement` | 45,0 ± 7,6 | 45,8 ± 7,4 | +0,8 | 0,11 | PASS |
| `change:negation_reduction` | 0,0 ± 0,0 | 0,0 ± 0,0 | +0,0 | 0,00 | PASS |
| `change:negation_renewal` | 0,0 ± 0,0 | 0,0 ± 0,0 | +0,0 | 0,00 | PASS |
| `change:order_fixation` | 36,6 ± 4,3 | 35,8 ± 7,1 | −0,8 | 0,14 | PASS |
| `change:order_relaxation` | 0,0 ± 0,0 | 0,0 ± 0,0 | +0,0 | 0,00 | PASS |

Všech 43 sledovaných veličin je pod 1,36 SD (požadavek `< 2,0 SD`).

### Rozpad času a ověření po kroku 1

- `v2_timing.py --scenario valley-50 --helpers`: celkem **27,266 s**,
  `phase.innovate` kleslo z **10,854 s na 8,626 s** (−2,23 s díky odstranění
  zbytečných instancí `PCG64`, hašování na každou dvojici skupina×změna a stavby
  vah při nulovém počtu), `phase.transmit` 16,478 s, `observe.observe` 2,160 s.
- Rychlá sada: **580 prošlo, 72 vynecháno**.
- Celá sada testů (`pytest -q`): **652 prošlo za 228,27 s (3 min 48 s)**.
- `ruff` i `mypy` bez nálezů.

## Krok 2: index míst s mírami a součtem pro rodiny nad 50 míst

### Návrh

1. **Rozhraní `Change.total_rate` a `Change.weighted_sites`**:
   - `Simulation._innovate` a `_innovate_with` nyní počítají očekávaný počet
     inovací přímo přes `change.total_rate(context) * tempo`, aniž by při
     nulovém vylosovaném počtu žádaly seznam míst `change.sites(context)`.
   - Při nenulovém počtu vrací `change.weighted_sites(context)` seřazená místa
     a líně normalizované váhy bez opakovaného přepočtu měr.
2. **Napojení rodin s průměrem nad 50 míst (a jejich společných předků)**:
   - `LexicalCoinage`: `total_rate` čte v `O(1)` délku kešovaného seznamu
     `repertoire.variable_ids_of("lexical")` bez volání `sites`.
   - `SemanticSitesIndex` / `SemanticChange` (všech 7 sémantických změn včetně
     `semantic_shift` a `contamination`): rozšiřuje stávající přírůstkový index
     o mapu `site_rates` aktualizovanou jen pro `dirty` pojmy a o příznak
     `_dirty`. Pouze po skutečné změně místa či míry přepočítá líně v
     `ensure_ready()` seřazený seznam `sorted_sites`, pole `float64`
     `rates_array` a součet `float(np.sum(rates_array))` (nikdy průběžným
     přičítáním/odečítáním). Při nezměněném `lexicon_version` je dotaz `O(1)`.
   - `MorphologyCandidateIndex` / `AnalogicalChange` (`extension` a `leveling`):
     `total_rate` čte v `O(1)` počet položek slovníku kandidátů bez řazení;
     seřazený seznam míst se staví a kešuje jen při nenulovém počtu inovací.
3. **Ověření „průběžně = od nuly“ (`tests/v2/test_v2_site_rate_index.py`)**:
   - Ověřena shoda `total_rate`, `sites`, `rates` a `weighted_sites` všech 10
     indexovaných změn proti referenčnímu výpočtu po každém kroku 20krokového
     běhu, inkrementálnost (změna 1 dominantního kořene nepřepočítá všech ~150
     pojmů) i nezávislost a bitová shoda checkpointů.

### Vyhodnocení brány po kroku 2

Sériový pár měřený bezprostředně za sebou přes `scripts/v2_timing.py --scenario valley-50`:

| Oblast | Výchozí `825d1c3` (s) | Krok 2 (s) | Poměr / stav |
|---|---:|---:|---|
| Celý běh `valley-50` (s měřičem) | 30,255 | **26,995** | **≤ 30 s — SPLNĚNO** (`v2_digests.py`: 27,5 s) |
| `phase.innovate` | **10,855** | **7,826** | **1,39× rychlejší — ZATÍM POD PRAHEM 2,0× (cíl ≤ 5,428 s)** |
| `phase.transmit` | 17,009 | 16,996 | beze změny |
| `observe.observe` | 2,390 | 2,171 | beze změny |

Rozpad zbývajícího času v `phase.innovate` (`--helpers`, 7,763 s):

- **20 neindexovaných rodin `SoundChange`**: **5,001 s** (`voicing` 1,443 s,
  `vowel_shift` 0,696 s, `coda_loss` 0,410 s, ostatních 17 rodin 2,452 s) —
  hlavní brzda, která sama znemožňuje dosáhnout `≤ 5,428 s` bez indexace
  zvukových změn.
- `leveling` (`MorphologyCandidateIndex.sync`): 0,407 s (`extension` už jen 0,005 s,
  `sites` voláno jen 589× místo 4 000×).
- `semantic_shift` (`SemanticDependencies.sync`): 0,323 s (ostatních 6 sémantických
  rodin dohromady 0,284 s).
- `rebracketing`: 0,237 s (`sites` voláno jen 11× místo 4 000×).
- 9 syntaktických změn: ~0,49 s.

Všech sedm otisků v `v2_digests.py` je **bitově shodných** s krokem 1. Rychlá
sada: **584 prošlo**, celá sada (`pytest -q`): **656 prošlo za 227,64 s
(3 min 47 s)**, `ruff` i `mypy` čisté.

Podle předem schváleného rozhodnutí uživatele pokračujeme přímo **krokem 3**:
přírůstkovým indexem opory a měr všech 20 rodin zvukových změn, zrychlením
synchronizace `VocabularyIndex` pomocí `vocabulary_log` a kešováním dominantních
slovesných kořenů v `Rebracketing`.

## Krok 3: sdružený přírůstkový index opory zvukových změn

### Návrh

1. **Přeskočení množinových rozdílů ve `VocabularyIndex.sync` a delty v `ContextIndex` (`src/cee/v2/language/index.py`)**:
   - `VocabularyIndex` sleduje `_vocab_cursor` a `_lexicon_version`. Při přepisu
     tvarů fonologizací, kdy se `vocabulary_log`, `lexicon_version` ani velikost
     `vocabulary` nezměnily (~95 % synchronizací), přeskočí oba rozdíly množin
     `counted.keys() - vocabulary` a `vocabulary - counted.keys()` nad ~364 slovy
     a dorovná pouze změněná slova z `forms.log` (`O(|changed|)`). Tím zrychlil
     nejen `ContextIndex`, ale i `ExponentIndex` v přenosu. Při jakékoli změně
     slovní zásoby či přímé mutaci v testech se provede úplné množinové srovnání.
   - `ContextIndex` udržuje počty výskytů hlásek `segment_counts` (inventář v
     `O(|inventář|)` místo procházení ~1 000 čtveřic), generaci a přírůstkový
     deník celočíselných změn `deltas: list[tuple[Context, int]]`.
2. **Sdružený `SoundSupportIndex` pro všech 20 rodin (`src/cee/v2/changes/sound.py`)**:
   - Na rozdíl od dřívějšího neúspěšného prototypu z `07-prubezne-indexy.md`
     (který zpracovával delty 20× zvlášť a vedle nich dál stavěl celé
     `ContextStats`) sdružuje `_CombinedSoundCandidates` unikátní kandidáty všech
     20 rodin `SOUND_CHANGES` (~106 procesů celkem), předřazené vzestupně podle
     `variable_id`, do jediné matice masek pro dvojici `(id(table), inventory)`.
   - `SoundSupportIndex` (uložený v `code.phonology.cache["sound-support-index"]`
     jako čistá data bez odkazů na `World` či `Code`) při nezměněném
     `state.version` vrací uložený stav v `O(1)` (pokrývá 19 z 20 rodin v kroku
     se změnou a všech 20 rodin v krocích beze změny).
   - Při běžném přepisu několika tvarů sečte `contexts.deltas` (~15–30 čtveřic)
     a jediným celočíselným maticovým součinem `(106, ~20) @ (~20,)` v `int64`
     aktualizuje opory všech 20 rodin naráz.
   - Protože vzorec míry závisí jen na efektivní opoře `0` (`< 2`) nebo
     `min(8, support)`, přepočítají se seřazená místa, pole `rates_array` a
     jednorázové `float(np.sum(rates_array))` v kanonickém pořadí **výhradně pro
     rodiny, u nichž se změnila efektivní opora** (typicky 0–3 z 20 rodin).
   - Pro vlastní podtřídy `SoundChange` mimo standardní `SOUND_CHANGES` nebo při
     změněném `prior` zůstává v platnosti záložní cesta přes `context_stats`.
3. **Keš dominantních sloves v `Rebracketing` (`src/cee/v2/changes/morphology.py`)**:
   - Seřazená n-tice dominantních slovesných kořenů (~25 kořenů z ~155) se kešuje
     podle `state.lexicon_version` při zachování vnější invalidace kandidátů
     podle `state.version`.
4. **Ověření „průběžně = od nuly“**:
   - V `tests/v2/test_v2_site_rate_index.py` rozšířena kontrola po každém kroku
     20krokového běhu na všech 31 indexovaných změn (všech 20 `SOUND_CHANGES`,
     7 sémantických změn, `LexicalCoinage`, `Extension`, `Leveling`,
     `Rebracketing`) proti čerstvému výpočtu nad **zcela vyprázdněnou**
     `state.cache`, doplněn test přechodu inventáře a přímé mutace slovníku i
     kontrola izolace `SoundSupportIndex` a `ContextIndex` v checkpointu.

## Závěrečné sériové srovnání (`825d1c3` vs. krok 3)

Měřeno v jednom souvislém sériovém sledu stejným interpretem bez souběžné zátěže.

### Neinstrumentovaný běh `scripts/v2_digests.py`

| Scénář | Výchozí `3d1016c` (s) | Výchozí fáze 5 `825d1c3` (s) | Po fázi 5 — krok 3 (s) | Otisk (krok 1 = krok 2 = krok 3) |
|---|---:|---:|---:|---|
| `phonology` | 0,2 | 0,2 | **0,2** | `91e46de9b912a8847fb7b1595c007c18c5ff0bbf4ca52eb414980df7f2bad4f4` |
| `morphology` | 0,4 | 0,4 | **0,3** | `7ea78265d605f629dab2edc1f90e7d594d47fde4215d8392e5c3472bb9d5fa87` |
| `syntax` | 0,6 | 0,5 | **0,3** | `9e1abfe36cce76d10594a7a5087ae61f5f82e0ab6f2b94bae56897e75625dd0c` |
| `grid-5x5` | 3,5 | 2,7 | **2,2** | `36767c976a7af2c7c989dce2e37b86a582ee97233c2c4cce0e5fc3bde5f2b9bf` |
| `shift` | 1,2 | 0,9 | **0,7** | `1bfbc2a466d61db09d5762ff2d718069adde6da343eb289bbffee5ce44de36eb` |
| `island-city` | 0,9 | 0,7 | **0,6** | `3577e966ab9e39320f55688982c42e0d95b9ccfb0b6eb37b6388d937bf20c29e` |
| `valley-50` | 37,6 | 30,9 | **23,6** | `6246ebdba75988f78e32d386c320bfd6d6842f6dc09d833537b05ef94544a08d` |

Všech sedm otisků kroku 3 je **100 % bitově shodných** s krokem 1 i krokem 2.
Scénář `valley-50` zrychlil oproti `825d1c3` z **30,9 s na 23,6 s** (−23,6 %),
oproti původnímu `3d1016c` z **37,6 s na 23,6 s** (−37,2 %), a poprvé splnil i
původní mez **≤ 25 s**.

### Sériový rozpad času `scripts/v2_timing.py --scenario valley-50`

| Oblast | Výchozí `825d1c3` (s) | Krok 1 (s) | Krok 2 (s) | Krok 3 (s) | Změna `825d1c3` → Krok 3 |
|---|---:|---:|---:|---:|---|
| Celý běh `valley-50` | 30,049 | 27,266 | 26,995 | **23,273** | **−6,78 s (−22,6 %), ≤ 30 s SPLNĚNO** |
| **`phase.innovate`** | **10,771** | **8,626** | **7,826** | **5,091** | **2,12× rychlejší (≥ 2,0× SPLNĚNO)** |
| — 20 rodin `SoundChange` (`total_rate` + `sites`) | 5,451 | ~5,19 | 5,001 | **2,431** | `voicing` (synchronizace indexu) 2,377 s, zbylých 19 rodin dohromady 0,054 s |
| — morfologické změny (`leveling`, `extension`, `rebracketing`) | 1,007 | ~0,65 | 0,649 | **0,597** | `leveling` 0,382 s, `rebracketing` 0,210 s, `extension` 0,005 s |
| — lexikální a sémantické změny (8 rodin) | 0,810 | ~0,67 | 0,675 | **0,672** | `semantic_shift` 0,321 s, ostatních 7 rodin 0,351 s |
| — syntaktické změny (9 rodin) | 0,527 | ~0,52 | 0,491 | **0,478** | neindexované (0–1 místo) |
| `phase.transmit` | 16,928 | 16,478 | 16,996 | **15,996** | zrychlení i díky `VocabularyIndex.sync` v `ExponentIndex` |
| `observe.observe` | 2,347 | 2,160 | 2,171 | **2,184** | beze změny |

Ověření sady testů po kroku 3:
- Rychlá sada (`pytest -m "not slow" -q`): **585 prošlo, 72 vynecháno**.
- Celá sada (`pytest -q`, včetně všech milníkových bran a checkpointů): **657 prošlo za 192,79 s (3 min 12 s)**.
- `ruff check src/cee/v2 tests/v2` i `mypy src/cee/v2` bez nálezů.

## Co zůstalo pomalé a proč

V celkovém čase `valley-50` (~23,3 s) nyní tvoří:

1. **Přenos (`phase.transmit` ≈ 16,0 s, 69 % běhu)**:
   - Hodnocení zvukových procesů (`_process_scores` 3,79 s, z toho vektorový
     `_assess_batch` 3,21 s pro 120 nejčastějších slov × dotčené skupiny a
     hledání homofonních dvojic).
   - Fonologizace a zápis tvarů (`phonology.restructure` 2,47 s) a morfologické
     hodnocení (`_form_scores` 2,43 s / `Conservation` 2,05 s).
   - Lexikální jasnost (`LexicalClarity` 1,72 s — průchod dosažených buněk
     proměnných × slotů × skupin).
   - Samotná Wright-Fisherova / logistická selekce a drift nad `LivePools` (~6 s),
     kde přežívají stovky nízkofrekvenčních variant pod 5 % (přesný Poissonův
     drift pro malé počty mluvčích by ušetřil další ~24 %, ale mění dynamiku a
     patří až do kalibrace M7).
2. **Inovace (`phase.innovate` ≈ 5,1 s, 22 % běhu)**:
   - Zbývající čas se dělí mezi jednu synchronizaci `ContextIndex` +
     `SoundSupportIndex` na změněnou vesnici (`voicing` 2,38 s inkluzivně přes
     `form_contexts` přepsaných slov a agregaci delt), synchronizaci morfologie
     (`leveling` + `rebracketing` 0,60 s), sémantiky (`0,67 s`), devět levných
     syntaktických změn (`0,48 s`) a Python smyčku sestavení `expected` matice a
     skutečných návrhů (`~0,9 s`).
3. **Pozorování (`observe.observe` ≈ 2,2 s, 9 % běhu)**:
   - Výpočet párových editačních vzdáleností kognátů mezi 50 vesnicemi každé
     4 kroky.

Původní orientační rozpočet ze specifikace (`valley-50 ≤ 5 s`, `grid-5x5 ≤ 1 s`)
zůstává v čistém Pythonu + NumPy po skupinách nedosažitelný bez změny modelu
(kalibrace driftu v M7) nebo paralelního/architektonického oddělení oblastí.
