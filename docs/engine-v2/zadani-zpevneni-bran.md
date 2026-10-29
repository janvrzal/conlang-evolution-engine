# Zadání: zpevnění milníkových bran

Datum: 29. 10. 2026. Větev: `engine-v2-numba`, navazuje na `f3a9dfd`.
Předchází kalibraci M7; bez něj by M7 nešla měřit.

## Proč

Ve fázi 5 se změnil proud náhodných čísel inovací (`hash_poisson` místo
`PCG64.poisson`). Model se statisticky nezměnil (43 veličin pod 2 SD), přesto
padly čtyři brány. Agenti pak zkoušeli doménovou konstantu klíče, dokud všechny
brány neprošly, a skončili u `"innovation-change-34"`
(`src/cee/v2/simulation.py`).

Měření v `08-davkova-inovace.md` ukázalo, že tyto brány procházely náhodou
i na původním `825d1c3`:

| Brána | Seedů | Průchod na jeden seed |
|---|---:|---:|
| `test_v2_m4_gate.py::test_jespersenuv_cyklus_ne_ne_pas_pas` | 1 | 3/10 |
| `test_v2_m3b_gate.py::test_tabu_vyvola_kolobeh_opisu` | 1 | 5/8 |
| `test_v2_m3_gate.py::test_morfologizace_vznikne_sama` | 2 (aspoň 1) | ~7/10 |
| `test_v2_m4b_gate.py::test_exaptace_zbytkove_koncovky` | 1 | 8/10 |

Brána s pevným seedem a pravděpodobností průchodu 30–80 % neověřuje model,
ověřuje jeden konkrétní proud náhody. Každá další změna, která se toho proudu
dotkne (M7 ho změní určitě), shodí některou bránu i tehdy, když je správná.
Vybírat konstanty nebo seedy podle výsledku testů je zakázané.

## Cíl

1. Každá stochastická brána buď prochází spolehlivě (≥ 95 % seedů), nebo
   ověřuje míru průchodu přes více seedů s prahem odvozeným z měření.
2. Konstanta klíče je neutrální, `"innovation-change"`, zvolená bez ohledu na
   výsledky testů.
3. Brány dál odhalí rozbitý mechanismus: negativní kontrola musí padnout.

## Pravidla

- **Vlastnosti se nemění.** Prahy uvnitř tvrzení (např. `>= 4` skupiny,
  `weakness < 0.4`, roky simulace, velikosti scénářů) zůstávají znak po znaku.
  Mění se jen počet seedů a způsob agregace (k z N).
- **Výběr seedů ani konstant podle výsledku je zakázán.** Seedy bran jsou pevné
  souvislé řady `1..N`. Měření, ze kterého se odvozuje práh, běží na jiné řadě
  (`101..120`), aby se práh nevolil na stejných datech, na kterých se testuje.
- Robustní brány (≥ 95 % v auditu) zůstávají beze změny.
- Determinismus platí dál: pevné seedy, žádné `hash()`, žádné pořadí množin.
- Necommitnuté soubory uživatele v `ui/`, `src/cee/project_schema.py`
  a `tests/test_projects.py` se nesmí dotknout. Žádný `git stash`, push ani
  sloučení do `engine-v2`.

## Kroky

### Krok 1: neutrální konstanta a nové otisky

V `Simulation._configure` a `_apply_innovations` nahradit
`"innovation-change-34"` za `"innovation-change"` (jedno místo, ideálně
modulová konstanta). Spustit `scripts/v2_digests.py`, zapsat nové otisky.
Brány teď mohou padat; to je očekávané a řeší to další kroky.

### Krok 2: audit všech stochastických tvrzení

Skript `scripts/v2_gate_rates.py`: pro každou bránu v `tests/v2/*_gate.py`,
jejíž výsledek závisí na seedu, spustí její scénář na seedech `101..120`
a zapíše, zda tvrzení prošlo. Tvrzení se musí vyhodnocovat stejným kódem jako
v bráně: logiku tvrzení vytáhnout do pomocných funkcí v modulu bran nebo
v `tests/v2/gate_checks.py`, ne kopírovat.

Netýká se testů determinismu, výkonu (`test_vykon_rezimu_udoli`) ani testů
přiblížení nepropojené oblasti; ty jsou deterministické ze své podstaty.

Výstup: tabulka v deníku `09-zpevneni-bran.md` (brána, počet seedů dnes,
průchod x/20, Wilsonův 95% interval, zařazení):

- **robustní**: ≥ 19/20, beze změny;
- **křehká**: 10–18/20, převést na k z N (krok 3);
- **slabá**: < 10/20, nepřevádět, nahlásit (krok 4).

Audit běží sériově na pozadí, bez souběžné zátěže. Odhad: desítky minut.

### Krok 3: převod křehkých bran na k z N

- Seedy brány `1..N`, výchozí N = 10. U drahých scénářů smí být N menší, ale
  aspoň 5; důvod zapsat do deníku.
- Práh k: největší celé číslo takové, že P(Bin(N, p_dolní) < k) ≤ 1 %, kde
  p_dolní je dolní mez Wilsonova 95% intervalu z auditu. Výpočet k je ve skriptu,
  ne ručně, a v bráně je u prahu komentář s naměřeným x/20.
- Brána hlásí při selhání počet úspěšných seedů a jejich seznam.
- Sdílet běhy přes `scope="module"` fixtures, jak to brány dělají dnes.

### Krok 4: slabé brány

Brány pod 50 % (podle dosavadních měření Jespersen) **nepřevádět
a nezmírňovat**. Do deníku zapsat naměřenou míru, příčinu (u Jespersena
`NegationReduction` od podílu 0,5, viz `08-davkova-inovace.md`) a dvě
možnosti pro uživatele:

1. k z N s nízkým k jako ochrana proti regresi, s otázkou do M7, zda je míra
   věrohodná;
2. ponechat jako známé selhání do M7 (`xfail(strict=False)` s odkazem).

Rozhodne uživatel. Do té doby agent slabou bránu jen hlásí.

### Krok 5: negativní kontroly

Pro každou převedenou bránu jednorázově změřit (ne jako trvalý test) míru
průchodu se **vypnutým mechanismem** na seedech `1..N`. Příklady:
- Jespersen bez oslabení záporky;
- tabu s `taboo=()`;
- morfologizace bez fonologických změn, které ji spouštějí;
- exaptace s volným slovosledem.

Tam, kde už brána kontrolu obsahuje, použít ji. Výsledek musí být pod k.
Pokud není, brána je bezzubá a hlásí se uživateli, ne snižuje.

### Krok 6: pravidlo do `AGENT.md`

Doplnit: „Když změna proudu náhody shodí stochastickou bránu, nezkoušej jiné
seedy ani konstanty. Změř míru průchodu před a po (`scripts/v2_gate_rates.py`)
a rozhodni podle ní.“

## Brána tohoto zadání

- Konstanta je `"innovation-change"`; v kódu není žádná konstanta ani seed
  zvolený podle výsledků testů.
- Tabulka auditu je v deníku pro všechna stochastická tvrzení.
- Všechny brány kromě slabých, o kterých rozhodne uživatel, procházejí;
  negativní kontroly jsou pod prahem.
- Celá sada `pytest -q` trvá nejvýš 6 minut (dnes 3 min 12 s). Při překročení
  snížit N u nejdražších bran (ne pod 5) a zapsat do deníku.
- `ruff`, `mypy` čisté; otisky z kroku 1 zapsané v deníku, `05-specifikace.md`
  a `CURRENT_STATE.md`.
- Commit po krocích, jen po potvrzení uživatele.
