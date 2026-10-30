# Zadání: typologická pestrost a sekundární artikulace

Datum: 30. 10. 2026. Výchozí commit: `68d4e54` (větev `engine-v2-numba`,
po zpevnění bran). Dvě části, v tomto pořadí:

- **Část A** postaví měřidlo, zda simulované jazyky zůstávají typologicky
  pestré. Jen měří, model nemění.
- **Část B** odstraní plošný zákaz sekundární artikulace ve výstupech
  zvukových změn. Mění model (doplněk M2).

Část A jde první, aby se dopad části B dal změřit stejným měřidlem.

## Proč

**Atraktory.** Na dlouhých horizontech tlačí některé tlaky všechny jazyky ke
stejnému stavu. Člen do 3 000 let vznikne všude (`05-specifikace.md`, Známé
mezery), přestože velká část jazyků ve WALS (37A) určitý člen nemá. Cesty
gramatikalizace vedou hlavně „tam“, zpětná cesta je slabá. Pro aplikaci na
tvorbu jazyků je to nejzávažnější riziko: po 5 000 letech by si všechny
jazyky byly typologicky podobné. Dnes to nemáme čím změřit.

**Sekundární artikulace.** `_is_plain` v `src/cee/v2/language/segments.py`
vylučuje z výstupů změn každou hlásku s `ʰʷʲˠˤʼ` nebo s kombinující
diakritikou (tilda nosovosti neprojde `isalpha()`). Pravidlo vzniklo kvůli
artefaktům (z /o/ se zvýšeným jazykem vznikalo /oˠ/ místo /u/), viz
`05-specifikace.md`, „Výstup změny je vždy obyčejná hláska“. Důsledek je ale
širší: engine nikdy nevytvoří nosové samohlásky (francouzština, portugalština,
polština), palatalizované souhlásky (ruština, irština), labiovelára ani
mezistupeň kʲ při palatalizaci. Jsou to jedny z nejčastějších změn v historii
jazyků. Mezi Známými mezerami to zapsané není.

## Společná pravidla

- Pracuj ve vlastním worktree na nové větvi `engine-v2-typologie` z `68d4e54`
  (např. `git worktree add ../CEE-typologie -b engine-v2-typologie 68d4e54`).
  Ve sdíleném checkoutu nic neměň: jsou tam necommitnuté soubory uživatele
  (`ui/`, `src/cee/project_schema.py`, `tests/test_projects.py`).
  Žádný `git stash`, push ani sloučení.
- Determinismus: žádné `uuid4`, `hash()`, pořadí množin; náhoda jen přes
  `cee.v2.rng`.
- Data jen s licencí CC0, CC BY, MIT nebo BSD. Přibalený výřez má citaci,
  licenci a SHA-256 vstupů uvnitř, jako `v2_core_semantics.json`. Index
  Diachronica (CC BY-SA) použít nelze.
- Stochastické brány: pravidlo v `AGENT.md`. Když změna modelu shodí bránu,
  nezkoušej jiné seedy ani konstanty, změř míru průchodu
  (`scripts/v2_gate_rates.py`) před a po a nahlas ji.
- Prahy uvnitř existujících bran se nemění.
- Měření a simulace sériově. Deník `docs/engine-v2/10-typologie.md`.
- Commit po krocích, jen po potvrzení uživatele.

## Část A: měřidlo typologické pestrosti

Bez změny modelu: všech 7 otisků v `scripts/v2_digests.py` zůstane stejných.

### A1: referenční rozložení z WALS

Skript `scripts/build_v2_typology.py` vytáhne z WALS (CLDF, CC BY 4.0)
rozložení hodnot rysů, které engine umí vyjádřit, a uloží je do
`src/cee/data/v2_typology.json`. Kandidáti (ověř hodnoty a vyber jen ty, které
se dají na stav enginu namapovat jednoznačně):

| Rys enginu | WALS |
|---|---|
| počet souhlásek | 1A |
| počet samohlásek | 2A |
| stavba slabiky | 12A |
| člen (`DEFINITE`) | 37A |
| slovosled (`ORDER`) | 81A |
| zápor (`NEG`: pre / embraced / post) | 143A, případně 112A |
| minulý čas (`PAST`) | 66A |
| budoucí čas (`FUTURE`) | 67A |
| plurál (`PL`) | 33A |
| pád (`OBJ`) | 49A |
| nosové samohlásky (pro část B) | 10A |

- Rozložení vážit podle genů WALS (každý genus váha 1 rozdělená mezi jeho
  jazyky), aby velké rodiny nepřevážily.
- Převodní tabulka „stav enginu → hodnota WALS“ patří do deníku i s tím,
  co se namapovat nedá a proč.
- Hodnoty WALS, které engine vyjádřit neumí (např. 81A „bez dominantního
  pořadí“ proti `free`), označ výslovně. Nepřiřazuj je odhadem.

### A2: měření

Skript `scripts/v2_typology.py`. Pro každý jazyk vyhodnotí rysy z A1
(převládající stav přes skupiny jazyka) a spočítá:

- rozložení rysu přes jazyky v časech 0, 1 000, 2 000, 3 000 a 5 000 let;
- Hellingerovu vzdálenost od WALS (`metrics.hellinger`);
- normovanou entropii rysu v čase (1 = všechny hodnoty stejně časté,
  0 = všechny jazyky stejně). Kolaps pestrosti = entropie klesá k 0.

Dva pokusy, každý aspoň 20 seedů nezávislých protojazyků (malý scénář,
např. `village_grid(6, …, syntax=True, semantics=True, phonology=True,
morphology=True)`; velikost zvol podle času a zdůvodni v deníku):

1. **Stejný start.** Výchozí gramatika `SYNTAX_GRAMMAR`. Otázka: vznikne
   pestrost a vydrží, nebo všechny jazyky dojdou do jednoho stavu?
2. **Start z WALS.** Gramatiku protojazyka los z rozložení A1 (pevný seed).
   Otázka: je rozložení WALS pro dynamiku modelu přibližně stacionární?
   Pokud se za 5 000 let výrazně vzdálí, model má atraktor, který skutečné
   jazyky nemají.

Funkce `metrics.typology_profile(world, language)` a metriky do
`src/cee/v2/metrics.py`, s jednotkovými testy. Pokud dlouhé běhy zpomalí
celou sadu, patří pod značku `slow`.

### A3: výstup

Tabulka v deníku pro každý rys a oba pokusy: rozložení v čase, Hellinger od
WALS, entropie. U každého rysu, který kolabuje nebo se vzdaluje, uveď
mechanismus v kódu, který za tím je (které změny vedou jen jedním směrem,
chybějící zpětná cesta, tlak). **Model v této části neopravuj.** Výsledek je
podklad pro M7 a rozhodne o něm uživatel. Brána A: otisky beze změny, testy
projdou, tabulka a rozbor v deníku.

## Část B: sekundární artikulace ve výstupech změn

### B1: filtr podle záměru

Zákaz zachovat jen pro *vedlejší produkt* hledání nejbližší hlásky. Změna,
která sekundární artikulaci výslovně chce, ji smí vytvořit. Návrh: změna
deklaruje povolené značky (např. `allow=("ʲ",)` nebo `("̃",)`),
`SegmentTable.changed` je předá do `_closest_cached` a kandidátní maska
pustí jen hlásky s těmito značkami. Regresní test: /o/ se zvýšeným jazykem
dál dá /u/, ne /oˠ/.

Ověř, že tabulka hlásek (PanPhon) potřebné hlásky obsahuje (kʲ, tʲ, sʲ, kʷ,
ɡʷ, ã, ẽ, ĩ, õ, ũ…). Pokud ne, doplň je způsobem, jakým tabulka vzniká
(rysy skládáním diakritik, ne ručně psané vektory).

### B2: změny

Malá sada, každá s obousměrnou cestou, aby nevznikl další atraktor:

| Změna | Příklad | Zpětná cesta |
|---|---|---|
| sekundární palatalizace | C → Cʲ / _i, j | depalatalizace Cʲ → C |
| palatalizace přes mezistupeň | k → kʲ / _i, pak kʲ → t͡ʃ | (stávající přímé k → t͡ʃ zachovat nebo nahradit, zdůvodnit) |
| nazalizace samohlásky | V → Ṽ / _N(C\|#) | denazalizace Ṽ → V |
| labializace | k → kʷ / _u, w | delabializace kʷ → k; kʷ → p (řečtina, p-keltština) |

- Kontrast vzniká sám přes existující fonologizaci: když ve slově zmizí
  spouštěč (např. `CodaLoss` odstraní N po nazalizaci, `Apocope` odstraní
  koncové i po palatalizaci), alofon se stane fonémem. Nepřidávej zkratku,
  která kontrast vytvoří přímo.
- Priory podle literatury (např. Kümmel 2007; Blevins 2004; Ohala 1993),
  citace v docstringu, jako u stávajících rodin.
- Aspirace, ejektivy a glotalizace nejsou v rozsahu; zapiš je do Známých
  mezer.

### B3: ověření

- Metriky 4 a 5 (inventáře v pásmu, homofonie) dál drží.
- Měřidlo z části A na stejných seedech před a po: podíl jazyků s nosovými
  samohláskami porovnat s WALS 10A. Nevyladit na shodu, jen změřit a
  zapsat. Žádný rys nesmí kolabovat víc než před změnou.
- Všechny brány projdou (pravidlo stochastických bran viz výše), nové
  otisky zapsané v `v2_digests.py`, deníku a `05-specifikace.md`.
- `valley-50` nejvýš o 10 % pomalejší než na `68d4e54` (sériový pár).
- Řádek „Výstup změny je vždy obyčejná hláska“ ve specifikaci přepsat podle
  nového pravidla.

Brána B: vše výše, `ruff` a `mypy` čisté, celá sada `pytest -q` prochází.
