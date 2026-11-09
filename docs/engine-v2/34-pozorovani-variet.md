# 34. Varieta po přechodu jazyka je nářečím (M14)

Stav: **zapsáno na větvi `verejny`** (9. 11. 2026).

Podnět uživatele: „Upravit pozorování“ (dok. 33: přešlé skupiny se počítaly jako samostatné
jazyky).

## Nález

Pod tvrdou politikou Istrenu (Talvera) mluví přešlé skupiny talmurským slovníkem se serenskou
výslovností (hláskově 0,40–0,43 od Istrenu) a pozorování z nich dělalo sedm nových jazyků.
Výslovnost se liší proto, že malé skupiny dospělých L2 mluvčích v modelu silně zjednodušují
(populační tlak podle Trudgilla). Na stejném mechanismu stojí ztráta pádů v románských
provinciích, takže ho v dynamice oslabit nelze.

## Zapsáno

- **Brána tvarů u jazyků** (`observe::LANGUAGE_FORM_GATE` 0,3, `Hysteresis::form_gate`):
  rozdíl výslovnosti příbuzných slov se do vzdálenosti jazyků započte jen z podílu
  `min(1, rozdíl slov a konstrukcí / 0,3)` (na jednu proměnnou slova). Varieta se stejným slovníkem
  a cizí výslovností (irská angličtina) je nářečím cílového jazyka; jazyky s odlišným slovníkem
  (španělština a portugalština) se dál rozdělí. Shluky nářečí beze změny.
- **Unášení veřejné skupiny z řeči rodilého vzoru** (`World::sampled_population`): skupina, která
  se úřední jazyk učí od rodilého vzoru téhož jazyka (`prestige_mirror`), vybírá vstup z populace
  vzoru. Populační tlaky (zjednodušování u L2 mluvčích) se dál řídí vlastní velikostí. Samo
  o sobě Talveře pomůže málo (přešlí 0,38–0,41 od Istrenu místo 0,43), románské cíle nerozbije.

| brána | Talvera jazyků (sem. 1, 2) | přešlí v jazyce Istrenu | Evropa |
|---|---|---|---|
| bez (M13) | 59–69 | 0 ze 7 | 62 |
| 0,1 | 62–64 | 0 ze 7 | 57 |
| **0,3** | **54, 54** | **7 ze 7** | **51–56** |
| 0,6 | 46–48 | 7 ze 7 | 50 |

## Ověření

**Testy 15 z 16 sad** (selhává `spec_check::scenare_evropa_a_romania_nemaji_chyby` z `25a177f`),
**brány 47 z 47, kalibrace 37 z 38**: `m8::pocet_jazyku` 56, `m8::rodiny` 0,647,
`m7::kontinuum` 0,099. Neprošla `m7::typologie_37A` (člen) 0,129 při mezi 0,112 (M13: 0,115):
typologie se počítá po pozorovaných jazycích, a ty jsou teď větší.
