# Příprava na Rust (fáze A) a přepis (fáze B)

Sepsáno 2026-11-01. Rozhodnutí s uživatelem: engine v2 nejdřív v Pythonu
připravit do podoby, jakou bude mít v Rustu (fáze A), a pak ho modul po
modulu přepsat (fáze B). Načasování fáze B má sedět s ustálením modelu (M7).

## Proč ne rovnou jádra v Rustu

Měření (údolí 10 × 5, syntax a význam, 1 000 let, 25 s): čas nejde do
několika výpočtů, ale do milionů drobných volání nad slovníky s textovými
klíči (`World.usage_frequency` 1 mil., `unit_of`/`form_of` 1,7 mil.,
`lexical_index.score` 2,9 mil., synchronizace indexů). Samotná aplikace
zvukových změn a fonologizace je asi 1 s. Rust jádro volané po jednom slově
by režií hranice Python–Rust zisk spotřebovalo; Rust pomůže, až budou data
v polích a jádra budou zpracovávat celou skupinu nebo celý krok najednou.

## Fáze A: kroky

Každý krok je malý commit, po každém `scripts/v2_digests.py` beze změny
(bitová shoda), checkpointy dál fungují, veřejné API (`Simulation`,
`World.form_of/unit_of/distribution`, `export`, `scenarios`) zůstává.

| Krok | Obsah | Stav |
|---|---|---|
| A1 | horké cesty: hromadné četnosti užití, ploché pole hlásek a bitové předfiltry v bance tvarů, hromadná lexikální jasnost, fronta fonologizace naráz (`zadani-datovy-model.md`, test shody `test_v2_datamodel.py`) | hotovo 2026-11-01: otisky beze změny, valley-50 42,7 s → 34 s (−19 %), grid-5x5 v šumu; profil je teď plochý (podpora zvukových změn ~17 %, artikulace ~14 %, fronta fonologizace ~12 %, lexikální jasnost ~8 %) |
| A2 | registry číselných ID pro morfémy, varianty, proměnné, skupiny, procesy, pojmy. Pořadí zpracování se nemění: kde dnes kód řadí podle řetězců, registr drží pořadí řetězců (pořadové číslo = pozice v seřazení) | hotovo 2026-11-02 (`zadani-registry.md`): `cee.v2.registry`, číslo = pořadí vzniku, registr patří světu a kopíruje se s ním; slovníky entit světa zapisují do registru samy (`RegisteredDict`); `Numbering.ranks()` pro řazení čísel v pořadí řetězců |
| A3 | stav kódu v polích: tvary (`FormStore` → čísla tvarů do `FormBank`), slovní zásoba a převládající kořeny (`PhonologyState`), fronty fonologizace | hotovo 2026-11-02: `FormStore` = tři pole `int32` podle čísla morfému (tvar v bance, hranice koncovky, koncovka; −1 = výchozí/žádná), `PhonologyState` v `language/columns.py` (slovní zásoba a fronty jako pole příznaků, počty užití a kořeny pojmů `int32`, fronta = `float64` potřebných logitů + `int32` morfémů), sklony slov jako sloupec světa; `World.form_id_of` místo hašování tvarů. Otisky beze změny i s jiným `PYTHONHASHSEED`, celá sada 1026 prošlo; čas a paměť v šumu (valley-50 32,7 → 33,5 s, špička ~1,44 GB). Na řetězcích zůstává: shoda v řazení fronty (logit, jméno morfému; pro Rust přes `ranks()`), deníky a klíče procesů, tvary v `UnitForm`, `ContextIndex`. `DominantMap` drží pořadí vložení pojmů: Rust ho musí udržet, nebo na něm nesmí záviset |
| A4 | tabulky světa jako sloupce: morfémy (tvar, frekvence, druh, jazyk, třída slova), varianty (proměnná, payload podle typu), proměnné, vazby (matice/CSR místo slovníku dvojic) | hotovo 2026-11-02 (`zadani-sloupce.md`): `cee.v2.tables` (`MorphemeTable`, `VariantTable`, `VariableTable` plněné při uložení entity do slovníku světa; `LinkDict` + `LinkTable` = CSR po číslech skupin, přepočet jen po změně vazeb); slovníky objektů zůstávají zdrojem pravdy. Na sloupce převedeno: `mixing_matrix`, `word_bias`, tlaky nad variantami (aktuace, motivace, přítomnost morfému, přitažlivost), milníky; hlavní hot cesty zbývají na objektech (viz závěrečná zpráva). Otisky beze změny, čas a paměť v šumu, celá sada 1032 prošla |
| A5 | fáze kroku jako funkce nad poli (inovace, tlaky, přenos, fonologizace, morfologie, syntax, prozódie, kontakt); třídy zůstanou tenkou fasádou. Součástí jsou **řídké fondy podle variant** (rozhodnuto s uživatelem 2026-11-02): živé fondy (`pools.py`) dnes drží každou proměnnou jako husté pole skupiny × sloty, takže varianta ve 3 vesnicích z 50 má řádek přes všech 50, a sloty jsou řetězcová ID variant, která tlaky a přenos při každé dávce překládají na čísla (zjištění z A4). Nově: sloty jako čísla variant z registru a výskyt varianty jako řídký seznam (skupina, podíl) uložený po variantách, tedy mapa rozšíření slova přímo v datech (pro atlas v UI). Přenos potřebuje „co je u mě a u sousedů“, proto zvážit dvojí index (po variantách i po skupinách) nebo husté bloky jen pro proměnné rozšířené skoro všude. Paměť a čas pak rostou s počtem skutečných výskytů, ne se součinem vesnic a variant; rozhoduje to u velkých map. Bitová shoda jen při zachovaném pořadí sčítání (jinak vědomá změna otisků s ověřením branami)  | část hotova 2026-11-03 (`zadani-faze.md`, modul `cee.v2.phases`): inovace (klíče, tempo, míry a váhy míst, výběr místa), milníky a ustálení, přechody přes práh, aktivace, analogie, nové koncovky a pravidlo přízvuku jsou čisté funkce nad poli, třídy je jen volají. Otisky beze změny. Zbývá přenos, tlaky, kontakt a řídké fondy |
| A6 | přenositelná náhoda: model dnes vedle hashovaného šumu (`rng.stable_int`, `hash_normal`, `hash_poisson`; blake2b a splitmix64, v Rustu snadno stejné) používá i `numpy.random.Generator` (PCG64 a algoritmy `poisson`, `choice`, `uniform`, `normal` numpy). Ty v Rustu bitově zopakovat nejde rozumně; nahradit je hashovanými losy (asi 27 míst: tvorba protojazyka 11, pozadí dějin 6, lexikální změny 3, variabilita 2, syntax 2, výběr místa inovace a prozódie po 1). **Vědomá změna otisků**, ověřená branami | hotovo 2026-11-02 (`zadani-nahoda.md`): `rng.Stream` (klíč z `stable_int`, jádro SplitMix64, `random` 53 bitů, `integers` Lemire, `choice` postupné kumulativní součty + `bisect_right`, `normal` Box–Muller přes libm, `poisson` inverzí po kusech λ ≤ 30; algoritmy v docstringu, referenční tahy v `test_v2_stream.py`) nahradil numpy ve výběru místa inovace, návrzích změn, sklonech slov a velkých λ v `hash_poisson`. Tvorba světa (protojazyk, pozadí dějin, rozdání variability) zůstala na numpy, svět po `build()` je beze změny; při přechodu desktopu na čistý Rust ji bude třeba převést (jednorázová změna slov protojazyka). Nové otisky v `scripts/v2_digests.py`. Ověření: audit bran na seedech 101..120 bez významného rozdílu (nejmenší p = 0,24, Jespersenův cyklus 6/20 → 2/20), statistika inovací na 8 seedech v limitu u všech 39 typů změn, retence za 1 000 let izolovaná 0,900 → 0,899 a kontakt 0,915 → 0,913; valley-50 v šumu. Brána Fergusonovy diglosie (pevné seedy 1, 2) s novou náhodou neprošla; podíl na 20 seedech je ale 10/20 už před A6 (11/20 po) |
| A7 | zlatá data: záznam vstupů a výstupů každé funkce z A5 ze skutečných běhů pro ověření Rust implementace kus po kusu  | pro funkce z `cee.v2.phases` hotovo 2026-11-03: `scripts/v2_golden_phases.py` (grid-5x5, shift, valley-50 zkráceně a čtyři světy pro vzácné cesty), `tests/v2/data/golden_{innovation,vocabulary,grammar}.json.gz` (asi 200, 410 a 90 kB), test `test_v2_golden_phases.py`. Profil (s Rustem z B2): inovace 34 % času valley-50 a 30 % grid-5x5, z toho skoro vše ve hledání míst (`total_rate`), u valley-50 z dvou třetin ve zvukových změnách (`changes/sound.py`, 22 % celku); morfologie 2 %, syntax a prozódie pod 0,2 %, sledování slovní zásoby 5 %, čisté funkce nad poli dohromady asi 1,5 %. Zlatá data přenosu, tlaků a kontaktu zbývají |
| A8 | hranice pro události a státy (`events`, `polity`, `background`, `contact`): jsou vzácné a nejsou horké, zůstanou nejdéle v Pythonu a budou svět měnit přes API | |

## Fáze B: pořadí přepisu

Podle závislostí, každý modul za stávajícím rozhraním (PyO3, maturin),
s testem shody proti zlatým datům:

1. tabulka hlásek (s vytvářením hlásek až při prvním zápisu, viz Známé mezery), banka tvarů, tabulky procesů.
   **Banka tvarů a tabulky procesů hotovo 2026-11-02** (`zadani-rust-b1.md`):
   - crate `rust/cee_core` (PyO3 0.30, maturin, modul `cee_core`, verze
     rozhraní 1): plochá aréna tvarů, bitové předfiltry, tabulky výsledků
     a aplikace procesu se všemi sedmi operacemi;
   - `cee.v2.native` rozšíření načte. Bez něj, s `CEE_NATIVE=0` nebo při
     jiné verzi rozhraní počítá Python;
   - otisky jsou bitově stejné v obou režimech, celé sady s Rustem 1 070
     prošlo a bez něj 1 065 prošlo a 5 přeskočeno;
   - zlatá data `tests/v2/data/golden_bank.json.gz` (21 093 aplikací);
   - zisk je malý: valley-50 asi −5 % (31 proti 34 s), grid-5x5 v šumu,
     protože zbývající cena je Python obal kolem 4 milionů jednotlivých
     volání `may_apply` z `phonology.restructure`. Velký zisk přijde
     s dávkovými voláními v kroku 2;
   - operace `change` a `tone` (nejbližší hláska) počítá dál Python
     a Rustu je doplňuje mapou, o kterou si sám řekne. Tabulka hlásek
     zůstala v Pythonu;
   - překlad: čistý release asi 10 s, po drobné změně asi 2,4 s;
   - sestavení: `maturin build --release`. Do sdíleného venv se
     rozšíření neinstaluje; agent ho dal do
     `rust/cee_core/target/py` a ten přidal do `PYTHONPATH`.
2. aplikace zvukových změn a fonologizace.
   **Hotovo 2026-11-03** (`zadani-rust-b2.md`):
   - `NativeBank` umí krok fonologizace kódu po dávkách
     (`restructure_step`, `queue_morpheme`, `activate`, verze rozhraní 2).
     Vstupy jsou pole `FormStore`, sloupce světa, příznaky front a sloupce
     sklonů slov předané bez kopírování. Rust nic nezapisuje, vrací
     rozhodnutí a Python je zapíše ve stejném pořadí jako dřív;
   - logity a sklony slov počítá Python, takže bitová shoda nezávisí na
     libm. Chybějící hodnoty si Rust vyžádá (`needs`) a Python je doplní;
   - otisky jsou stejné s Rustem i bez něj. Zlatá data kontrolují 18 015
     přepisů a 9 937 zařazení do fronty bit po bitu;
   - fonologie ve valley-50 trvá 3,7 s místo 7–8 s a celek je asi
     o 8 % rychlejší (valley-50 asi 30 s). Zbytek času je v tlacích,
     přenosu a hodnocení (krok 3 a 4 až po A5);
   - zbývá: sestavování seznamů front (`_targets`, asi 2 s) a četnosti
     užití (asi 1 s) v Pythonu;
3. hodnocení (artikulace, funkční zátěž, lexikální jasnost) a tlaky;
4. přenos (míšení, výběr, drift) a živé fondy;
5. hledání míst inovací a změny;
6. hlavní smyčka `Simulation`; Python zůstane pro popis světa, export,
   kalibrační skripty a API; desktopová aplikace (Tauri) může engine volat
   přímo z Rustu bez Pythonu.

Rozdělení na více crate (tabulka hlásek, změny, přenos, události) zkrátí
překlad po malé změně; konstanty a katalogy zůstanou daty
(`Parameters`, YAML/JSON), takže kalibrace nepotřebuje překlad.

## Bitová shoda při přechodu do Rustu

Transcendentní funkce (`exp`, `log`, `sqrt` je v pořádku) počítá numpy jinou
implementací než standardní knihovna Rustu a v posledním bitu se mohou
lišit. Postup: jednotlivé funkce porovnávat s tolerancí v řádu posledního
bitu, otisky při přechodu jednou vědomě vyměnit a nový stav ověřit celou
sadou bran a statistickým srovnáním na seedech. Od té chvíle jsou
referencí otisky z Rustu.

## Nevýhody, se kterými počítat

- pomalejší experimentování s modelem (překlad, typy); proto načasovat
  fázi B s ustálením M7;
- překlad: ladicí po malé změně jednotky sekund, optimalizovaný desítky
  sekund, čistý 1–3 minuty (odhad pro ~16 tisíc řádků);
- přechodné období dvou jazyků (vazby, sestavení přes maturin);
- binárky pro každou platformu (u Tauri spíš výhoda: engine bez Pythonu).
