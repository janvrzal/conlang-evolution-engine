# 24. Tempo hláskových změn (M9)

Stav: **měřicí základ zapsán, kalibrace otevřená** (6. 11. 2026).

Podnět uživatele: „přijde mi, že ty varianty původní stále přežívají“ (po M8e, kdy Evropa dostala
skutečné slovníky z IE-CoR). Po 2 400 letech zůstala slovanská slova skoro beze změny (*voda* →
*voda*), zatímco Řecko a Kambrie se rozpadly na jednovesnické jazyky.

## Cíl ze skutečných dvojic (IE-CoR)

`scripts/iecor_form_rates.py`: příbuzná slova stejného významu (stejná sada kognátů), fonemický
zápis převedený na hlásky enginu (bez přízvuku a délky), d = průměrná normalizovaná Levenshteinova
vzdálenost, tempo r = −ln(1 − d) za tisíciletí.

| dvojice | hloubka | r za tisíciletí |
|---|---|---|
| **ladění:** latina → 7 románských jazyků | 2 050 let | 0,30 (italština, sardinština) – 0,70 (francouzština) |
| staroslověnština → 8 slovanských | 1 100 let | 0,39 (srbochorvatština) – 0,76 (polština) |
| staroangličtina → angličtina | 1 100 let | 0,85 |
| stará horní němčina → němčina | 1 100 let | 0,67 |
| *medián ladicích dvojic* | | *0,49* |
| **kontrola** (k ladění se nepoužívá): starořečtina → novořečtina | 2 400 let | 0,23 |
| klasická → východní / západní arménština | 1 550 let | 0,22 / 0,39 |
| staroirština → irština, skotská gaelština, manština | 1 200 let | 0,85–0,98 |
| staroislandština → nynorsk | 800 let | 1,15 |

Cíl `m9::tempo`: tempo bez kontaktu v pásmu [0,30; 0,85]; zrychlení kontaktem [1; 2] (návrh:
angličtina a francouzština s mnoha kontakty 0,70–0,85 proti sardinštině a italštině 0,30, rozdíl
mírný, ne řádový).

## Rychlá zkušební sada (`cee calibrate --only tempo`, 12 semínek, 8 s)

Kontrolované světy, 1 000 let: 12 vesnic staroslověnštiny, 12 vesnic latiny (obojí bez kontaktu)
a 12 vesnic staroslověnštiny pod latinským státem se snášenlivou politikou.

| | tempo | slov beze změny |
|---|---|---|
| staroslověnština bez kontaktu | 0,091 | 66 % |
| latina bez kontaktu | 0,031 | 87 % |
| staroslověnština pod latinským státem | 0,278 | 37 % |
| **tempo bez kontaktu / zrychlení kontaktem** | **0,060 / 2,45×** | cíl 0,30–0,85 / 1–2× |

## Rozbor

Kontrolované světy (12 vesnic, 1 000 let, 4 semínka; vzdálenost d):

| svět | dokončených změn na vesnici | d | beze změny |
|---|---|---|---|
| samotná vesnice | 0,8 | 0,03 | 94 % |
| 12 vesnic | 1,8 | 0,09 | 66 % |
| 3 regiony po 12 vesnicích | 1,7 | 0,11 | 60 % |
| 12 vesnic po 250 lidech | 3,5 | 0,09 | 66 % |
| cizí stát, snášenlivá / podporovaná politika | 1,2 / 4,8 | 0,17 / 0,24 | 49 % / 39 % |

- **Velikost sítě skoro nevadí** (větší síť je o trochu rychlejší: vesnice navrhují stejné změny
  a posilují se). Hypotéza, že husté sítě změny rozmělňují, neplatí.
- **Výchozí tempo je asi 5× pod skutečností** a hláskové změny pohání hlavně kontakt.
- Ze 112 hláskových inovací (12 vesnic, 1 000 let) se dokončí asi 12; jedno ujmutí zasáhne 3–4 slova,
  proces za tisíciletí kolem 12 slov na vesnici (asi 8 % slovníku). Šíře změn je přiměřená;
  chybí dotažení.

**Páky** na sadě (tempo bez kontaktu / zrychlení kontaktem): 3× víc inovací 0,144 / 1,88; artikulace
×2 0,194 / 2,84; konformita ×0,5 zastaví změny úplně (konformita pomáhá dokončit křivku S); zachování
nebo zažitost ×0,5 beze změny. **Sociální ocenění změny (`actuation`, Weinreich, Labov a Herzog 1968)
jen u hláskových změn** (`changes::SOUND_PRESSURES`): váha 1,5 → 0,156 / 2,14; 2,0 → 0,339 / 1,78;
**2,5 → 0,513 / 1,53** (slovanská slova beze změny 19 %, latinská 7 %, skutečnost 0–10 %). Změna
potřebuje výhodu, aby doběhla (Blythe a Croft 2012); dnes ji má příliš slabou.

## Proč zatím nezapsáno

S `actuation` 2,5 (i 2,0) se rozbije, co bylo kalibrované při pomalém tempu:

| cíl | 1,0 (dnes) | 2,0 | 2,5 |
|---|---|---|---|
| `m7::kontinuum` (sousední vesnice, pásmo 0,05–0,15) | v pásmu | 0,174 | 0,269 |
| `m7::slozitost` (Trudgill, alternace × populace, pásmo −1–0) | v pásmu | 0,363 | 0,500 |
| `m7::latina_konzervativni` (větev drží pád v roce 1200, `p_min` 0,3) | ano | 1 z 20 | 1 z 20 |
| `m7::latina_obnova_futura` | ano | 4 z 20 | 5 z 20 |

A výkon: Romania 50 s místo 6 s na 20 semínek; běh Evropy do roku 300 trvá 13 s, do roku 800 44 s
(banka tvarů 110 tisíc → 361 tisíc), celý přes minuty. Profil do roku 800: přenos 33 %, přestavba
fonologie 22 %, komunity 21 %, události 11 % — žádné jedno úzké hrdlo.

**Další kroky:** (1) výkon při realistickém tempu (banka tvarů, přestavba fonologie, komunity);
(2) společná rekalibrace provázaných parametrů (`actuation` hláskových změn, otevřenost vesnic pro
kontinuum, další podle cílů) přes všechny rychlé běhy najednou; Evropa a typologie jen na potvrzení.
