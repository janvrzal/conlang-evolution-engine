# Rozhraní enginu v2 pro UI

Datum: 31. 10. 2026. Větev `engine-v2-dynamika`. Příprava před stavbou
UI: popis světa jako data, běh s průběhem přes HTTP a export nových vrstev
(státy, hranice, jazyky regionů, normy).

## Popis světa (`cee.v2.spec`)

UI posílá JSON `WorldSpec` (formát `cee-v2-world/1`, mění se jen
přidáváním polí). Popis obsahuje jen to, co autor zná. Čísla dynamiky jsou
v `Parameters` a dají se přepsat v `parameters`. Úplný příklad je
v `src/cee/data/v2_example_world.json`.

```json
{
  "format": "cee-v2-world/1", "seed": 1, "start_year": 0, "end_year": 1500,
  "languages": [{"id": "a"}, {"id": "c", "grammar": "substrate", "consonants": ["p", "t", "k"]}],
  "regions": [
    {"id": "capital", "position": [0, 0], "density": 2.0, "neighbours": ["mountains"], "language": "a"},
    {"id": "mountains", "position": [0, 60], "density": 0.5, "neighbours": ["capital"], "language": "c",
     "terrain": "mountains", "identity": "strong"}
  ],
  "events": [
    {"kind": "state", "year": 100, "id": "kingdom", "regions": ["capital", "mountains"], "capital": "capital"},
    {"kind": "standard", "year": 300, "of": "kingdom"}
  ]
}
```

- **Jazyky:**
  - `id` a jméno;
  - inventář souhlásek a samohlásek;
  - profil gramatiky: `default`, `substrate` nebo `full`;
  - přízvuk: `initial`, `second`, `antepenult`, `penult`, `final` a jeho
    síla.
- **Regiony:**
  - poloha v km, relativní hustota, sousedé, počet vesnic (1–12) a
    prestiž;
  - jazyk, terén a identita;
  - konzervace jazyka a přistěhovalectví.
- **Události** (pole `kind`): `state`, `language_policy`, `annexation`,
  `secession`, `collapse`, `border_policy`, `lingua_franca`, `standard`,
  `schools`, `revival`, `preserve`. Význam polí je
  v [`15-staty-lingua-franca.md`](15-staty-lingua-franca.md).
- **Svět:** `seed`, `semantics` (posun významu; vypnutí běh zrychlí asi
  o třetinu), rozestup vesnic, délka generace a `parameters`.

`WorldSpec.model_json_schema()` dává UI schéma formuláře a `levels()`
možnosti slovních úrovní (terén, identita, politika…) podle tabulek
`Parameters`.

**Ověření** (`check`) vrací seznam chyb s cestou k poli a českou zprávou.
Například `events.1`: „Stát 'nikdo' neexistuje; nejdřív ho založ událostí
State.“, nebo `regions.0.foo`: „neznámé pole“. Události se ověří zkušebním
provedením na kopii světa v pořadí roků. Tím se odhalí odkazy na
neexistující státy a regiony, neznámé úrovně i chybné pořadí (rozpad
před vznikem). `build` postaví svět a události, nebo vyhodí `SpecError`
se všemi chybami.

## Běh s průběhem (`cee.v2.runner`, `/api/v2`)

| Endpoint | Co dělá |
|---|---|
| `GET /api/v2/schema` | JSON schéma popisu, možnosti úrovní, druhy událostí |
| `POST /api/v2/validate` | `{"ok", "issues": [{"path", "message"}]}` |
| `POST /api/v2/runs` | spustí běh na pozadí, vrátí `run_id` (202); neplatný popis vrátí 422 se seznamem chyb |
| `GET /api/v2/runs/{id}?since=N` | stav, rok, průběh 0–1, čas a nové snímky od indexu `N` |
| `GET /api/v2/runs/{id}/result` | úplný export (409, dokud běh neskončil) |
| `DELETE /api/v2/runs/{id}` | zruší běh po dokončení rozpracovaného kroku |

Revize API je 8; UI vyžaduje aspoň svou revizi, takže starší UI dál
funguje. Běhy žijí v paměti serveru, drží se posledních osm dokončených.
Běh je deterministický: stejný popis dá bitově stejný export.

**Snímek** (`export.frame`) vzniká po každém pozorování (každé 4 kroky,
tedy 100 let) a má pár kB. Obsahuje:
- populace skupin a podíl L2;
- dialekty a jazyky;
- sčítání jazyků po regionech doma a mimo domov;
- území států.

**Export** (`export.export`) má navíc:
- `states`: území, sídlo, úřední jazyk, úrovně a norma;
- `borders`: dvojice sousedních regionů různých států s propustností;
- `standards`;
- `census`;
- teren a původní jazyk území;
- loajalita, tlak domů, konzervace a obrození skupin;
- události států na časové ose.

## Výkon

`scripts/v2_spec_timing.py` (mřížka regionů 40 km od sebe, tři jazyky,
stát s politikou `promoted`, od poloviny norma a škola; běh přes `runner`):

| svět | let | čas | skupin na konci | export |
|---|---:|---:|---:|---:|
| 12 regionů × 4 vesnice | 2 000 | 50 s | 61 | 1,7 MB |
| totéž bez sémantiky | 2 000 | 35 s | 61 | 1,7 MB |
| 12 regionů × 2 vesnice | 2 000 | 16 s | 31 | 0,9 MB |
| 24 regionů × 3 vesnice | 3 000 | 153 s | 109 | 3,1 MB |

Tabulka je před zrychlením popsaným níže.

Čas roste rychleji než počet vesnic (skupin přibývá i s dvojjazyčností).
Pro UI to znamená:

- **Náhled s hrubou sítí.** Region po dvou vesnicích dá výsledek zhruba
  třikrát rychleji. Plnou síť pustit až na požádání. Jestli hrubší síť
  dává podobné výsledky, ukáže kontrola měřítka (otevřená).
- **Průběžné kreslení.** Snímek každých 100 let, takže uživatel vidí
  mapu po vteřinách, ne po minutě.
- **Zrychlení** bude potřeba pro světy nad zhruba 50 vesnic (viz níže).

### Zrychlení bez změny výsledku

Profil světa se státem je plochý: žádná funkce nebere víc než pár procent.
Za nadlineárním růstem stojí dvojjazyčné skupiny. Stejný svět
(12 regionů × 4 vesnice, 800 let) běží bez státu 4,3 s a se státem 11,5 s,
při 48 a 85 skupinách. Veřejné skupiny mají slovník, který se mění skoro
každý krok, protože přejímají slova z místního jazyka. Každá změna dřív
spustila přepočet. Navíc každá skupina vymýšlí zvukové změny, které se
pak hodnotí ve všech skupinách, kam dorazí (zhruba skupiny × procesy).

Opravy (všechny bitově stejné: otisky `v2_digests.py` včetně `valley-50`
a otisky světů se státem ze `spec` se nezměnily):

| oprava | kde |
|---|---|
| úložiště tvarů se při mnoha větveních sloučí do jedné vrstvy (sídlo státu větvené pro každou veřejnou skupinu mělo desítky vrstev a každé čtení tvaru je procházelo) | `FormStore.branch` |
| inventář hlásek pro adaptaci výpůjček se čte z průběžného indexu prostředí místo přepočtu celé slovní zásoby při každé výpůjčce | `contact.inventory`, `adapt` |
| frekvence užití tvarů se pamatuje po kořenech a zneplatní ji jen deník dominantních kořenů | `World.usage_frequency` |
| vzorek slov pro hodnocení zvukových změn se po změně slovníku staví znovu jen tehdy, když se změní výběr | `AssessmentVocabularyIndex.sync` |
| dominantní varianta a podíl varianty se čtou ze skladu bez stavby celého rozdělení | `World.dominant`, `LivePools.frequency` |
| pronikání domů hledá domácí skupinu podle ID, ne průchodem všech skupin | `contact._nativize` |

Výsledek: procesorový čas, nejlepší ze tří běhů pro 12 regionů a z jednoho
běhu pro 24 regionů:

| svět | let | před | po |
|---|---:|---:|---:|
| 12 regionů × 4 vesnice | 800 | 13,1 s | 10,9 s (−17 %) |
| 24 regionů × 3 vesnice | 1 500 | 51,6 s | 45,2 s (−12 %) |
| údolí 50 vesnic bez státu (`valley-50`) | — | 30,4 s | 29,2 s |

Víc už bez změny modelu nejde. Další možnosti:

- **Hrubý náhled** (dvě vesnice na region): asi 3× rychlejší, model
  stejný. Chybí ověření, že dává podobné výsledky (kontrola měřítka).
- **Lehčí veřejné skupiny**: dvojjazyčná varieta úředního jazyka by
  nevymýšlela vlastní zvukové změny, jen by přejímala od zdroje
  a z interference. Pokus dal −15 % ve světě se státem. Mění to model
  a otisky světů se státem, proto čeká na rozhodnutí.
- **Paralelní běh**: bloky proměnných jsou v kroku nezávislé, ale sdílejí
  odvozené keše se zastaráváním po krocích (`STALE_TICKS`). Paralelní
  výpočet by je musel vracet, aby výsledek zůstal stejný. Je to větší
  přestavba. Přeložený kód (Numba) uživatel dřív odmítl.

### Složitost a paralelní běh (pokus)

Měření růstu s počtem skupin (procesorový čas, 400 let, mřížka regionů po
čtyřech vesnicích):

| skupin | bez státu | se státem (víc skupin díky dvojjazyčnosti) |
|---:|---:|---:|
| 12 / 25 | 0,9 s | 3,5 s |
| 24 / 49 | 1,7 s | 7,1 s |
| 48 / 85 | 3,1 s | 12,4 s |
| 96 / 180 | 6,3 s | 30,6 s |

Engine roste **lineárně** s počtem skupin. Za 1 500 let roste mírně
nadlineárně (24 → 96 skupin: 9,3 → 44,4 s), protože přibývá živých
proměnných (250 → 450). Čtvercově rostlo jen pozorování dialektů, které
porovnávalo všechny dvojice skupin (1–3 % času); od té doby je lineární,
viz níže. Drahá je konstanta
na buňku skupina × živá proměnná, asi 30 µs Pythonu. Buněk, kde se
nic neděje (jedna varianta na 100 % i u sousedů), je jen 15–24 %, takže
jejich přeskakování by dalo nejvýš kolem 20 %.

**Pokus s paralelním během** (`cee.v2.parallel`):
- Každý proces drží celý svět a dělá celý krok sám.
- Čisté dotazy na stav na začátku kroku počítá jen pro své skupiny a
  výsledky si procesy vymění: tlaky (`transmission.fitness_of`), tempo
  inovací (`total_rate`) a místa inovací (`weighted_sites`).
- Skupinu vlastní vždy týž proces (stabilní hash ID).

Výsledek je bitově stejný jako v jednom procesu (`tests/v2/test_v2_parallel.py`).
Jedinou překážkou bylo dědění zastaralých hodnocení zvukových procesů při
větvení kódu; nový kód je už nedědí (`PhonologyState.branch`). Klasické
otisky se nezměnily. Otisky světů se státem ano, protože v nich skupiny
vznikají větvením během běhu. Tabulky v `15-staty-lingua-franca.md` se
nezměnily.

**Zrychlení nepřineslo:**

| svět | 1 proces | 2 procesy | 4 procesy |
|---|---:|---:|---:|
| 12 regionů × 4 vesnice, 1 600 let | 29,6 s | 29,9 s | 36,9 s |
| 24 regionů × 3 vesnice, 1 500 let | 55,8 s | 56,1 s | 55,1 s |

Rozdělené dotazy jsou jen asi třetina až polovina času. Zbytek musí každý
proces dělat celý, aby stav kopií zůstal stejný: uplatnění inovací, vstup
slov do slovníku, aktivace a fonologizace, míšení, demografie a pozorování.
Navíc se v kopiích přesouvá práce, kterou dřív levně udělaly tlaky:
indexy cizích skupin se synchronizují až v těchto krocích. K tomu se
přidává čekání na nejpomalejší proces a start procesů.

**Co by zrychlilo:**

- **Dělení po vlastnících i pro kroky, které mění stav.** Vlastník by
  sám uplatňoval inovace své skupiny, slovník a fonologizaci. Ostatní by
  dostávali jen změny skladu proměnných (nové varianty a podíly) a
  záznamy historie. Tvary a slovník cizí skupiny by se posílaly jen
  tehdy, když je potřebuje větvení kódu (události), pozorování nebo export.
  Je to velká přestavba: každý krok se musí projít, co čte z cizích skupin.
- **Paralelismus na úrovni běhů**, jaký už používají kalibrační skripty
  (víc seedů, náhled a plná síť souběžně), je triviální a využije všechna
  jádra.
- **Menší konstanta na buňku**: tlaky jako hromadné operace v numpy.

### Lineární pozorování dialektů a jazyků

Dřívější pozorovatel spočítal matici vzdáleností všech dvojic skupin
(čtvercová) a shlukoval ji naivní průměrnou vazbou, která při každém
sloučení hledala minimum v celé matici (kubická). Teď
(`observe.constrained_average_linkage`):

- **Stejná vzdálenost dvou skupin**: rozdíl rozdělení variant plus rozdíl
  tvarů příbuzných slov. Rozdíl rozdělení ½ Σ |p − q| se ale počítá jako
  ½‖φ(p) − φ(q)‖² ve vložení podílů do prahových intervalů (`EDGES`,
  jemných u 0 a 1). Vychází v průměru o 5–10 % nižší, s korelací 0,999.
- **Průměrná vazba mezi shluky ze součtů**: díky vložení je průměr přes
  všechny dvojice členů přesně dán součty za shluk (počet, součet vložení,
  součet čtverců, četnosti tvarů a hystereze linií). Dvojice členů se
  neprocházejí. Dlouhé kontinuum se proto rozpadá podle nahromaděného
  rozdílu jako dřív, ne jen podle rozdílu na hranici.
- **Slučují se jen sousedící shluky**: sousedí spolu skupiny spojené
  vazbou nebo jedna ze čtyř zeměpisně nejbližších (mřížka, bez dvojic).
  Ostrov tak pořád může patřit k jazyku pevniny.
- **Paměť**: nejvýš 2 000 proměnlivých sloupců (proměnná × slot); víc se
  odhadne výběrem proměnných podle stabilního hashe a přeškáluje. To dává
  asi 100 kB na skupinu.
- Celá matice vzdáleností se do snímku ukládá jen na požádání
  (`SimulationConfig.keep_distances`). Potřebují ji brány kontinua (M1,
  metrika 9) a `scripts/v2_innovation_stats.py`. Funkce `code_distances`
  zůstala pro metriky a skripty.

Shoda se starým pozorovatelem (stejné běhy, každý snímek):

| scénář | stejný počet jazyků | stejný počet dialektů | Randův index dialektů |
|---|---:|---:|---:|
| mřížka 5 × 5 vesnic, 2 000 let | 100 % | 80 % | 0,975 |
| čtverec regionů, otevřenost 0,1 | 100 % | 83 % | 0,983 |
| čtverec regionů, otevřenost 0,5 | 100 % | 47 % (8,2 → 3,1) | 0,904 |
| království (stát, vynucování) | 100 % | 40 % (9,2 → 7,6) | 0,982 |
| ostrov a město, přechod jazyka, známý strom | 100 % | 55–80 % | 0,95–0,99 |

Jazyky vycházejí stejně. Dialektů je o něco méně tam, kde se sousedé liší
těsně kolem hranice dialektu (0,05), protože nižší vzdálenost je pod hranici
posune. Na přesném počtu dialektů žádná brána nestojí.

Čas jednoho pozorování (mřížka regionů po čtyřech vesnicích, 300 let):

| skupin | dřív | teď |
|---:|---:|---:|
| 100 | 0,05 s | 0,03 s |
| 400 | 1,3 s | 0,17 s |
| 784 | 9,6 s | 0,40 s |
| 1 600 | 102 s | 1,0 s |

Růst je teď zhruba lineární, mírně rychlejší kvůli hranici rostoucích shluků.

### Vlastnický režim (rozpracováno, odloženo)

Navazující pokus: kroky, které mění stav skupiny (uplatnění inovací,
slovník, aktivace a přestavba), dělá jen vlastník skupiny. Ostatním
procesům posílá jen to, co potřebují:
- nové položky registrů světa;
- operace nad skladem (vrácené a přehrané ve stejném pořadí skupin, aby
  bloky a sloty byly všude stejné);
- slovník skupiny (tvary, dominantní kořeny, slovní zásoba, přízvuk).

Před událostmi a při vzniku skupiny z cizího kódu si procesy vyžádají
úplné kódy od vlastníků.

Zjištění:

- **Engine nezávisí na pořadí skupin v kroku** (`tests/v2/test_v2_order.py`,
  `Simulation.reverse_groups`): stav i záznamy historie jsou stejné,
  i když se skupiny projdou pozpátku. To je podmínka každého paralelního
  běhu.
- **Keše jsou při větvení kódu čistou funkcí stavu**: kód bez keší i bez
  deníků dává bitově stejné otisky. Nový kód proto keš nedědí
  (`PhonologyState.branch`).
- Na malém světě byl vlastnický režim bitově shodný s jedním procesem.
  Na světě 12 regionů × 4 vesnice se rozešel v roce 400, kdy nastoupí
  spisovný jazyk a školy: u dvojjazyčné skupiny dal tlak `Uniformity`
  jiný součet (4,4534 proti 4,3756). Ostatní tlaky a vstupy (slyšené
  rozdělení, podíl L2, docházka) byly stejné. Příčina zatím nalezena není.
- Zrychlení se zatím neprokázalo (1,0× se dvěma procesy). Režii tvořily
  výměny přes koordinátora, přenos celých kódů (zmenšený vynecháním keší
  a deníků) a kopie skladu v každém kroku.

**Rozhodnutí uživatele: odloženo, nejdřív model.** Konstanta na buňku
(~30 µs) je cena Pythonu. Přeložené jádro (Rust pod Pythonem, PyO3) by ji
srazilo zhruba 30–100× a paralelismus by šel ve vláknech bez kopií světa.
Model se ale ještě mění (kalibrace M7), takže přepis má smysl, až se ustálí.
Rozpracovaný vlastnický režim je na větvi `engine-v2-parallel-owner`.

## Co zbývá pro UI

1. **Převod projektu na `WorldSpec`.** Projekt (`project_schema.py`, V3)
   popisuje legacy model: jazykové uzly, hrany, polygony států. Pro v2
   bude potřeba editor regionů (body, sousedé, hustota, terén, identita,
   jazyk) a časové osy událostí. Je to návrh UI, ne enginu.
2. Stránky UI nad endpointy `/api/v2`: editor světa s ověřením, běh
   s průběhem a mapa ze snímků (regiony obarvené jazykem doma, hranice
   států), časová osa a detail regionu (sčítání, slovník, gramatika).
3. Událostí po skupinách (`Contact`, `Migration`, `Conquest`…) zatím ve
   `WorldSpec` nejsou. Do popisu po regionech je přidat, až je UI bude
   potřebovat.
4. Ukládání výsledků běhu na disk (dnes jen v paměti serveru).
