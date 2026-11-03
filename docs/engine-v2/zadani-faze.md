# Zadání: fáze kroku jako funkce nad poli (krok A5 bez přenosu a tlaků) se zlatými daty (A7)

Přečti si:
- `docs/engine-v2/18-priprava-na-rust.md` (fáze A, řádek A5 včetně řídkých
  fondů, fáze B);
- zadání a výsledky A1 až A4 (`zadani-datovy-model.md` v jiném worktree,
  `zadani-registry.md`, `zadani-sloupce.md`);
- zadání B2 (`zadani-rust-b2.md`), kde je vzor zlatých dat.

## Cíl

Rust bude dál přepisovat celé fáze kroku simulace. K tomu musí být fáze
**čistými funkcemi nad poli**: vstup jsou pole stavu (registry, sloupce
světa, pole kódů, bloky fondů), výstup jsou pole změn a deník. Python
třídy zůstanou tenkou fasádou. **Výsledky musí zůstat bitově stejné.**

Tvoje část A5:
1. **Inovace** (`simulation._innovate`, `_apply_innovations`,
   `_innovate_with`, `_changes`, `changes/base.py`): vyhledání míst,
   váhy, počet inovací (`hash_poisson`), výběr místa (`Stream`) a návrh
   varianty. Rozděl to na (a) výpočet míst a vah jako pole, (b) losy jako
   funkci polí a klíčů, (c) návrh varianty, který zůstane v Pythonu (tvoří
   objekty `Variant`), a jasně popiš hranici.
2. **Morfologie, syntax a prozódie** (`morphology.py`, `syntax.py`,
   `prosody.py`, `changes/morphology.py`, `changes/syntax.py`,
   `changes/prosody.py`, `language/morphology*.py`): kroky, které běží
   každý tik (zapisování koncovek do tvarů, ustálení konstrukcí, pravidlo
   přízvuku, analogie), jako funkce nad poli.
3. **Sledování slovní zásoby po přenosu** (`simulation._follow_vocabulary`,
   `_activations`, `_trace`) jako funkce polí bloku před a po.
4. **Zlatá data (A7)** pro funkce z bodů 1–3: skript v `scripts/`, který při
   skutečných bězích (grid-5x5, shift, valley-50 zkráceně) zaznamená vstupy
   a výstupy funkcí, výřez do `tests/` (do 1 MB na modul) a testy, které
   zlatá data ověří proti Pythonu. Rust implementace je pak ověří stejně.
5. **Profil**: změř podíl těchto fází na čase valley-50 a grid-5x5 (s Rustem
   z B2: `PYTHONPATH=src:.:../CEE-rust-b2/rust/cee_core/target/py`,
   rozšíření je tam sestavené; samo ho nestav) a zapiš ho.

## Rozsah

**Tvoje soubory:**
- `src/cee/v2/simulation.py` kromě `_transmit` a toho, co volá přenos;
- `src/cee/v2/changes/base.py`, `changes/morphology.py`, `changes/syntax.py`,
  `changes/prosody.py`, `changes/lexicon.py` (jen místa a váhy, ne
  `LexicalBorrowing`);
- `src/cee/v2/morphology.py`, `syntax.py`, `prosody.py`;
- `src/cee/v2/language/morphology.py`, `morphology_index.py`,
  `semantic_index.py`.

**Nesahej na:**
- `transmission.py`, `pools.py`, `contact.py`, `institutions.py`,
  `events.py`, `background.py`, `polity.py` (pracuje na nich agent na
  domény kontaktu; přenos a řídké fondy přijdou až po něm);
- `assessment.py`, `language/assessment_index.py`, `form_assessment_index.py`,
  `lexical_index.py`, `language/index.py`, `changes/sound.py`,
  `pressures/*`, `rust/` (pracuje na nich agent na B3).

Když bez změny v cizím souboru nejde pokračovat, zastav se a popiš proč.

## Prostředí

- Pracuješ výhradně ve worktree `/Users/janvrzal/Documents/CEE-phases` na
  větvi `engine-v2-phases`. Jiné adresáře **neměň** (rozšíření
  z `CEE-rust-b2` jen používáš přes `PYTHONPATH`).
- Python: `/Users/janvrzal/Documents/CEE/.venv/bin/python` z kořene
  worktree, `PYTHONPATH=src:.` (bez Rustu) nebo s cestou k rozšíření (viz
  výše). Lint: `/Users/janvrzal/Documents/CEE/.venv/bin/ruff check src/cee/v2 tests/v2 scripts`.
- Stroj má 16 GB RAM a souběžně na něm pracují dva další agenti. Pouštěj
  jeden těžký běh najednou a nejvýš 2 procesy. Žádný paralelní pytest.
  Pomocné soubory ukládej do worktree, ne do scratchpadu, protože ten stroj
  průběžně čistí.
- Nic neinstaluj. Commituj na `engine-v2-phases` po malých krocích. Zpráva
  anglicky, na konci `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
  Soubory přidávej jménem. Nic nepushuj, nemerguj, nepoužívej `git stash`.
  Když ti systém něco zamítne, neobcházej to a napiš to do zprávy.

## Invarianty (porušení = práce se nepřijme)

- **Bitová shoda** (bez Rustu i s rozšířením z B2): `scripts/v2_digests.py`
  vypíše přesně:
  ```
  phonology    3990a6381c1a91b4c4ffddf42731d42915325960dc128c834b6eec74ba2f97a3
  morphology   710009d641a04a0b1f007d29fa18a3d273780e322667b826bb3d9a7e7165d43b
  syntax       a55966f235d171ee1b772c2196b7bb2c2a742172a064d2b293c17a4df7553482
  grid-5x5     cc4ef6e136b0eaa543c08fc4c7e424ca53d781bcdd0e905858d3cb32de0bcc61
  shift        f74dad095fcbaa129349dddd4ed74da4c3d1ced888dfe2ed81bc692212612559
  island-city  a3efb455923bf5a6489b55e68ca877ed4e5ab2b422076a0ed4d7a569d6313e47
  valley-50    79b033067955967931819647325eb42d83f4aa21e826587be4f2d49f13373e88
  ```
  Spouštěj `--quick` po každém kroku, valley-50 aspoň po každém druhém
  kroku a na konci. Shodný musí zůstat i připnutý otisk v
  `tests/v2/test_v2_vocabulary.py`.
- **Determinismus**: žádné `hash()` ani `uuid4` a žádná iterace přes `set`,
  na jejímž pořadí záleží. Čísla z registrů neurčují pořadí.
- **Checkpointy a pickle** fungují.
- **Žádné změny modelu**, konstant, `Parameters` ani bran. Existující testy
  neupravuj tak, aby prošly.
- Komentáře a docstringy piš česky ve stylu okolního kódu, identifikátory
  anglicky. `ruff` musí být čistý.

Na konci pusť celou sadu na pozadí bez Rustu a ještě jednou s rozšířením
z B2.

## Výstup

Závěrečnou zprávu napiš česky a nic nepřikrášluj. Má obsahovat:

- commity a co každý dělá,
- funkce: vstupní a výstupní pole (jména, typy, význam), aby šlo navrhnout
  rozhraní pro Rust,
- zlatá data (skripty, velikost, pokrytí),
- profil (podíl fází na čase),
- otisky a výsledky obou celých sad,
- co zůstalo na objektech a proč, co nešlo.
