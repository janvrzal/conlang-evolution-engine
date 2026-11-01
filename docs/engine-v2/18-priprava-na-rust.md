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
| A2 | registry číselných ID pro morfémy, varianty, proměnné, skupiny, procesy, pojmy. Pořadí zpracování se nemění: kde dnes kód řadí podle řetězců, registr drží pořadí řetězců (pořadové číslo = pozice v seřazení) | |
| A3 | stav kódu v polích: tvary (`FormStore` → čísla tvarů do `FormBank`), slovní zásoba a převládající kořeny (`PhonologyState`), fronty fonologizace | |
| A4 | tabulky světa jako sloupce: morfémy (tvar, frekvence, druh, jazyk, třída slova), varianty (proměnná, payload podle typu), proměnné, vazby (matice/CSR místo slovníku dvojic) | |
| A5 | fáze kroku jako funkce nad poli (inovace, tlaky, přenos, fonologizace, morfologie, syntax, prozódie, kontakt); třídy zůstanou tenkou fasádou | |
| A6 | přenositelná náhoda: model dnes vedle hashovaného šumu (`rng.stable_int`, `hash_normal`, `hash_poisson`; blake2b a splitmix64, v Rustu snadno stejné) používá i `numpy.random.Generator` (PCG64 a algoritmy `poisson`, `choice`, `uniform`, `normal` numpy). Ty v Rustu bitově zopakovat nejde rozumně; nahradit je hashovanými losy (asi 27 míst: tvorba protojazyka 11, pozadí dějin 6, lexikální změny 3, variabilita 2, syntax 2, výběr místa inovace a prozódie po 1). **Vědomá změna otisků**, ověřená branami | |
| A7 | zlatá data: záznam vstupů a výstupů každé funkce z A5 ze skutečných běhů pro ověření Rust implementace kus po kusu | |
| A8 | hranice pro události a státy (`events`, `polity`, `background`, `contact`): jsou vzácné a nejsou horké, zůstanou nejdéle v Pythonu a budou svět měnit přes API | |

## Fáze B: pořadí přepisu

Podle závislostí, každý modul za stávajícím rozhraním (PyO3, maturin),
s testem shody proti zlatým datům:

1. tabulka hlásek (s vytvářením hlásek až při prvním zápisu, viz Známé mezery), banka tvarů, tabulky procesů;
2. aplikace zvukových změn a fonologizace;
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
