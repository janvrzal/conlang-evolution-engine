# 28. Italské -m, tóny a vzdálenost románských větví (M10c)

Stav: **zapsáno na větvi `latina`** (7. 11. 2026).

Podnět uživatele: „Ano, opravit“ (italské -m a hraniční kontroly Romanie), pak „Je ten drift jazyků
uvěřitelný? Vzniknou po 2000 letech rozdílné jazyky z jednoho protojazyku?“ a „Ano, to opravíme“.

## Italské -m

Itálie koncové *-m* nikdy neztratila (podíl tvarů s -m 0,90–0,98 ještě v roce 1900), i bez měst.
Rozběhnutá ztráta (`LanguageSpec.processes`, podíl 0,3 v roce −100) byla v rodilé latině menšinová
varianta a výběr ji do roku 100 vymazal; v provinciích ji drželi lidé, kteří se latinu učili
v dospělosti. **Zapsáno:** Romania zadává ztrátu -m jako táhnoucí posun (`sound_shift`, `pull` 1,
dok. 26) — podmínka scénáře (ztráta -m byla v celé latině rozběhnutá, Pompeje 1. st.). Itálie pak
má -m v roce 250 u 40 % tvarů, v roce 400 u 15 %; `m7::latina_poradi` 1,00.

**Společné ocenění změn jen u hláskových změn** (`actuation_coherence` 0,8) a slabší pro slovník,
tvary a syntax (`actuation_coherence_other` 0,4): se soudržností 0,8 pro všechno se po regionu
šířila nová slova a změny záporu (retence latiny 0,54, zápor 0,55); s 0 se Evropa rozpadala
(94,5 jazyka). 0,4: Romania projde, Evropa ~80 jazyků.

## Tóny (Haudricourt 1954)

Románské a germánské jazyky měly tóny u poloviny slov (Itálie 57 %, Germánie 60 %): tón po souhlásce
měl kladnou zřetelnost a s rychlejším tempem (dok. 24) se šířil náhodou. **Zapsáno:** tón po
souhlásce i z koncové souhlásky má zřetelnost −0,1 a člen ocenění
`tonogenesis_trigger` × (2 × pokrok spouštěče − 1): spouštěčem je ztráta znělosti (rys `voi` → −,
bez ztráty na konci slova a spodoby) u tónu po souhlásce a úplná ztráta koncového *h*/*ʔ* u tónu
z koncové souhlásky. Slovanský svět bez ztráty znělosti: tóny 0–2 % slov; se zadanou ztrátou
znělosti (*b d g* → *p t k*) 29–56 %. Evropa: celkem 9 % slov (germánština a skandinávština 0 %,
Itálie 11 %), ale slovanská pravlast pořád 43 %, Armorika 28 %, Balkán 22 % — otevřené.

## Společná slova románských větví

Model: Itálie–Galie–Hispánie sdílely 87–99 % slov (IE-CoR: italština, francouzština, španělština
71–78 %). Zdrojem byla vazba k sídlu státu: vazby veřejné dvojjazyčnosti na Řím a jejich kopie
u skupin, které latinu přijaly, zůstávaly i po odtržení provincie. **Zapsáno:** při odchodu státu
z regionu zeslábnou všechny vazby skupin regionu na jeho sídlo na `release_residual` (0,3;
církev, obchod, vzdělanost). Napojení jen měst na sídlo (`centralize`) zapsáno taky, samo ale
nestačilo (0,96 / 0,83 / 0,79).

| sdílená slova (Romania 1900, 3 semínka) | Itálie–Galie | Itálie–Hispánie | Galie–Hispánie |
|---|---|---|---|
| dosud | 0,99 | 0,90 | 0,87 |
| vazby na sídlo zrušené | 0,54 | 0,52 | 0,59 |
| **zbytek 0,3 (výchozí)** | 0,89 | 0,76 | 0,70 |
| skutečnost (it–fr / it–es / fr–es) | 0,78 | 0,74 | 0,71 |

## Ověření

**Testy prošly, brány 47 z 47, kalibrace 35 z 38.** Romania kromě záporu projde celá (pořadí 1,00,
pád 1,00, retence 0,581). Neprošly:

- `m7::latina_zapor` 0,50 (≥ 3 větve se záporem před slovesem v roce 1200 v 80 % běhů): čím
  nezávislejší větve, tím častěji si malá izolovaná Dácie vyvine dvojitý zápor. Cíl je náš návrh.
- `m9::tempo`, zrychlení kontaktem 2,807 (mez 2,8).
- `m8::pocet_jazyku` 79,5 (pásmo 10–60).

**Otevřené:** vzdálenost od latiny v Evropě je velká a rovnoměrná (Itálie 0,75–0,81, Hispánie
0,86–0,92, Galie 0,83–0,86; skutečnost italština 0,46 … francouzština 0,76; Evropa běží od −500,
2 400 let); tóny ve slovanské pravlasti.
