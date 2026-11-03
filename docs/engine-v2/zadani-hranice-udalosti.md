# Zadání: hranice pro události a státy (krok A8)

Přečti si:
- `docs/engine-v2/18-priprava-na-rust.md`: fáze A (řádek A8, ale i A2 až A5,
  protože registry, sloupce a funkce nad poli jsou stav, který bude jednou
  v Rustu) a fáze B (pořadí přepisu, hlavně krok 6 o hlavní smyčce);
- `docs/engine-v2/17-pozadi-dejin.md` a `19-pojmy.md` (oddíl o doménách
  v kanálech kontaktu: `SpeechGroup.elite`, `World.trade`);
- kód `src/cee/v2/events.py`, `polity.py`, `background.py` a místa, kde
  `Simulation` události spouští.

## Proč

Jádro simulace (fondy, přenos, změny, hodnocení) postupně přechází do Rustu.
Události a státy (dobytí, cizí elita, obchod, náboženská změna, kodifikace,
škola, přesun jazyka, vznik a zánik vesnic, hranice států) jsou vzácné a
nejsou horké, takže zůstanou nejdéle v Pythonu. Dnes ale sahají do světa
přímo, na mnoha místech a do různých struktur. Až bude stav v Rustu, musí
Python měnit svět jen přes **malé a jasné API**, které Rust umí přijmout.

## Cíl

1. **Inventura**: najdi každé místo, kde `events.py`, `polity.py`
   a `background.py` mění stav světa (skupiny a jejich kódy, vazby
   a jejich síly, `World.trade`, `elite`, instituce, živé fondy, registry,
   repertoáry, parametry, čas). Zapiš to jako tabulku (místo, co mění,
   jakou strukturu).
2. **API změn světa**: navrhni malou sadu operací (např. přidat a odebrat
   skupinu, nastavit vazbu, obchodní podíl, příznak elity, instituci,
   přesunout skupinu k jinému jazyku, vložit variantu do skupiny) a dej je
   do nového modulu (např. `cee/v2/edits.py`). Každá operace je
   jednoznačná, má popsaný účinek na stav a deterministické pořadí.
   Události, státy a pozadí pak mění svět **jen** přes ně.
3. **Deník změn**: každá operace se zapíše (tik, operace, argumenty jako
   čísla a řetězce). Napiš test, že přehrání deníku do kopie světa ve
   stejných ticích dá **stejný otisk** jako běh s událostmi (aspoň svět
   s dobytím a elitou, obchodem, liturgií a přesunem jazyka, plus `shift`).
   Tím se ověří, že API pokrývá vše, co události dělají.
4. **Dokumentace**: řádek A8 v `docs/engine-v2/18-priprava-na-rust.md`
   a krátký popis API (operace, účinky, co z nich převezme Rust).

## Rozsah

**Tvoje soubory:**
- `src/cee/v2/events.py`, `polity.py`, `background.py`;
- nový modul API a jeho testy;
- `src/cee/v2/world.py`: jen nové metody v samostatném oddílu, pokud je
  API potřebuje. Části týkající se živých fondů (`live`) a distribucí
  nechej beze změny, upravuje je souběžně agent na přenos;
- `src/cee/v2/simulation.py`: jen místa, kde se spouštějí události.

**Nesahej na:**
- `transmission.py`, `pools.py`, `contact.py`, `institutions.py`,
  `pressures/*`, `phases.py` (pracuje na nich agent na přenos a řídké
  fondy). Když událost dnes volá metody `LivePools` (`load`, `innovate`,
  `release` …) nebo funkce z `contact.py`, API je volá dál beze změny
  jejich kódu;
- `rust/`, `native.py`, fonologii a modelové konstanty, `Parameters`
  a brány.

Když bez změny v cizím souboru nejde pokračovat, zastav se a popiš proč.

## Prostředí

- Pracuješ výhradně ve worktree
  `/Users/janvrzal/Documents/CEE-worktrees/boundary` na větvi
  `engine-v2-boundary`. Jiné adresáře **neměň**.
- Python z kořene worktree: `/Users/janvrzal/Documents/CEE/.venv/bin/python`.
  S Rustem: `PYTHONPATH=src:.:rust/cee_core/target/py` (rozšíření je
  zkopírované, nestav ho). Bez Rustu: `CEE_NATIVE=0 PYTHONPATH=src:.`.
  Lint: `/Users/janvrzal/Documents/CEE/.venv/bin/ruff check src/cee/v2 tests/v2 scripts`.
- Stroj má 16 GB RAM a souběžně pracuje ještě jeden agent. Pouštěj jeden
  těžký běh najednou a nejvýš 2 procesy. Žádný paralelní pytest. Pomocné
  soubory ukládej do worktree, ne do scratchpadu, a na konci je smaž.
- Nic neinstaluj. Commituj na `engine-v2-boundary` po malých krocích.
  Zpráva anglicky, na konci
  `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Soubory
  přidávej jménem. Nic nepushuj, nemerguj, nepoužívej `git stash`. Když ti
  systém něco zamítne, neobcházej to a napiš to do zprávy.

## Invarianty (porušení = práce se nepřijme)

- **Bitová shoda** s Rustem (všech 7) i s `CEE_NATIVE=0` (`--quick`):
  `scripts/v2_digests.py` vypíše přesně
  ```
  phonology    3990a6381c1a91b4c4ffddf42731d42915325960dc128c834b6eec74ba2f97a3
  morphology   710009d641a04a0b1f007d29fa18a3d273780e322667b826bb3d9a7e7165d43b
  syntax       a55966f235d171ee1b772c2196b7bb2c2a742172a064d2b293c17a4df7553482
  grid-5x5     cc4ef6e136b0eaa543c08fc4c7e424ca53d781bcdd0e905858d3cb32de0bcc61
  shift        5d66d45559b5043c19e9259a9b4d7e5d8ce1349d2558f69107db7d6bd1737261
  island-city  a3efb455923bf5a6489b55e68ca877ed4e5ab2b422076a0ed4d7a569d6313e47
  valley-50    79b033067955967931819647325eb42d83f4aa21e826587be4f2d49f13373e88
  ```
  Shodné musí zůstat i otisky v `tests/v2/test_v2_vocabulary.py`
  a `tests/v2/test_v2_domains.py`.
- **Determinismus**: žádné `hash()` ani `uuid4`, žádná iterace přes `set`,
  na jejímž pořadí záleží.
- **Checkpointy a pickle** fungují, včetně deníku změn.
- **Žádné změny modelu.** Existující testy neupravuj tak, aby prošly.
- Komentáře a docstringy česky ve stylu okolního kódu, identifikátory
  anglicky. `ruff` čistý.

Na konci pusť celou sadu s Rustem a s `CEE_NATIVE=0`, po jedné, na pozadí.

## Výstup

Závěrečnou zprávu napiš česky a nic nepřikrášluj. Má obsahovat:
- commity a co každý dělá;
- inventuru (tabulka);
- API: operace, argumenty, účinky, pořadí;
- test přehrání deníku (které světy, výsledek);
- otisky a výsledky obou celých sad;
- co zůstalo mimo API a proč, co nešlo.
