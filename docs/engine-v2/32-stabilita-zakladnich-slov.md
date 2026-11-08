# 32. Stabilita základních slov a výpůjčky napříč rodinami (M12)

Stav: **zapsáno na větvi `stabilita`** (8. 11. 2026).

Podnět uživatele: rozbor Talvery („Ano, rozbor“), pak „Oprav to vše“ (výpůjčky základních slov
podle frekvence a půjčitelnosti, číslovky a zájmena skoro ne, vyřadit cesty doložené jedním
jazykem, stabilita slova strměji podle frekvence).

## Nález

Talvera (semínko 1, rok 1950, scénář z `18db84e`): jeden kořen pro „dvě“ ve 77 z 218 domácích
skupin ve všech čtyřech rodinách, „slunce“ ve čtyřech rodinách, „matka“ (veretská odvozenina od
„slunce“) ve třech. Výpůjčky tvořily 40–60 % náhrad slov a retence kořenů od −700 byla
u serenštiny 0,35, u veretštiny 0,40. Romania (M11): častá slova se držela jen o málo víc než
střední (0,77 proti 0,75), „voda“ a „ruka“ se nahradily ve všech větvích.

Příčiny:

1. Váha výpůjčky stála na půjčitelnosti z WOLD na třetí mocninu; frekvence se uplatnila jen při
   síle pod 1. WOLD dává „dvě“ 0,23, tedy nad průměrem.
2. Přitažlivost slova (`appeal`) je stálá náhodná hodnota varianty a platila ve všech skupinách:
   slovo s vysokou přitažlivostí vyhrávalo v každém jazyce, kam se dostalo (idarské „pes“ až
   v serenské deltě).
3. Cesty z DatSemShift doložené jedním jazykem („slunce → matka“, „pták → létat“, 47 ze 425
   vztahů) měly váhu ln 2 / 3 a vyhrávaly všude, kde se slovo obrousilo.
4. Ochrana převládajícího slova byla 0,3 × frekvence: slabý rozdíl mezi častými a vzácnými slovy.

## Zapsáno

- **Výpůjčky podle frekvence a třídy** (`contact::transfer`, `normalizer`):
  - váha × (1 − frekvence)^`borrowing_frequency_exponent` (2; Calude a Pagel 2011; Monaghan
    a Roberts 2019);
  - funkční slova (kategorie „Function word“: zájmena, číslovky, zápor, kvantifikátory) × 0,15
    (`CLOSED_CLASS_BORROWING`; Thomason a Kaufman 1988; Tadmor 2009).

  Normalizace drží průměrnou míru výpůjček výchozího slovníku; mění se jen to, co se půjčuje.
- **Přitažlivost a motivace slova jen v jazyce, kde vzniklo** (`Pressures::native_word`):
  v cizím jazyce o výpůjčce rozhoduje prestiž dárce, ne „módnost“ tvaru.
- **Cesty grafu aspoň ze dvou jazyků** (`concepts::MIN_EVIDENCE` 2).
- **Strmější stabilita podle frekvence**: `entrenchment_strength` 0,3 → 0,6,
  `entrenchment_frequency_exponent` 1 → 2 (Pagel, Atkinson a Meade 2007). Síla 0,9 dávala
  strmější rozdíl, ale rozbila typologii plurálu (`m7::typologie_33A` 0,139 při mezi 0,098:
  jazyky se po 5 000 letech slily do jednoho typu); 0,6 dává 0,092 jako M11.

## Výsledky

Talvera, semínko 1 (sloupec „po“ s ochranou 0,9 / 2; výsledná 0,6 / 2 v oddílu Ověření):

| | před | po |
|---|---|---|
| „dvě“ cizí slovo (skupin z 218) | 34 | 2 |
| „slunce“ | 67 | 26 |
| „matka“ | 58 | 22 |
| „pes“ | 60 | 33 |
| „ruka“ | 53 | 22 |
| výpůjčky mezi náhradami | 38–58 % | 25–40 % |
| retence kořenů od −700: seren / talmur / veret / idar | 0,35 / 0,70 / 0,40 / 0,52 | 0,43 / 0,75 / 0,49 / 0,58 |
| jazyků v roce 1950 | 55 | 56 |

Romania, semínka 1–3, podíl latinských kořenů v roce 1900 podle frekvence pojmu (měřeno před
omezením přitažlivosti na domácí slova):

| | nízká | střední | vysoká |
|---|---|---|---|
| M11 | 0,50 | 0,75 | 0,77 |
| **ochrana 0,6 / 2 (zapsáno)** | **0,42** | **0,63** | **0,80** |
| ochrana 0,9 / 2 | 0,45 | 0,68 | 0,86 |
| ochrana 1,2 / 3 | – | – | – (Talvera horší: střední slova ztratí ochranu) |

Otevřené: „voda“ a „ruka“ se v Romanii pořád občas nahradí posunem významu z „řeky“ a „nohy“
(CLICS kolexifikace); posun do nejčastějších pojmů by mohl mít vlastní útlum.

## Slovník 1 000 slov

Engine ho umí už teď (`vocabulary` 149 až ~1 600 z katalogu WOLD). Výchozí zůstává 149:
běh roste se slovníkem zhruba lineárně (Talvera ~9 min místo 80 s), skutečné tvary máme jen pro
~150 pojmů IE-CoR a kalibrační cíle jsou na základním slovníku. Pro worldbuildera je 1 000 slov
volba v editoru (kulturní slova nesou stopu dějin).

## Ověření

**Testy 15 z 16 sad, brány 47 z 47, kalibrace 37 z 38.**

- Neprošla `m7::typologie_37A` (člen) 0,115 při mezi 0,112 (v M11 0,101), na hranici šumu
  vzorku 40 jazyků. Plurál `m7::typologie_33A` 0,092 prošel.
- Retence 0,865 (reálných ~0,86), retence vůči latině 0,728, tempo 0,357, zrychlení kontaktem
  2,652, počet jazyků Evropy 62.
- Selhává test `spec_check::scenare_evropa_a_romania_nemaji_chyby`: varování o úředním jazyce
  zavedená v `25a177f`. Selhává už na `18db84e` a s M12 nesouvisí.
- Nový parametr `borrowing_frequency_exponent` má roli `active` (dok. 31: 25 aktivních).

Talvera, semínko 1, výsledné nastavení: 60 jazyků v roce 1950. Cizí slovo pro „dvě“ ve 2 skupinách
z 218, „matka“ 26, „pes“ 27, „ruka“ 15, „voda“ 12, „slunce“ 47. Výpůjčky tvoří 19–40 % náhrad.
Retence kořenů 0,35 / 0,70 / 0,41 / 0,52: s ochranou 0,6 se víc slov obnoví odvozeninou (čtvrtina
náhrad, zčásti zdrobněliny téhož kořene, které retence počítá jako ztrátu).
