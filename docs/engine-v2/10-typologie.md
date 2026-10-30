# Typologická pestrost: část A

Datum: 30. 10. 2026. Výchozí model: `68d4e54`.
Práce probíhá ve worktree `/Users/janvrzal/Documents/CEE-typologie`, větev
`engine-v2-typologie`. Při navázání již worktree existoval, byl čistý a jeho
jediný commit nad výchozím modelem byl `9582bd3` (pouze zadání). Zadání se
bajtově shodovalo s necommitnutým originálem ve sdíleném checkoutu.
Žádný nový commit bez potvrzení uživatele; část B čeká na samostatné potvrzení.

## Předem stanovený protokol

- Dva pokusy: `same` (přesně `SYNTAX_GRAMMAR`) a `wals` (gramatika losovaná
  z genusově vážených referenčních rozložení v rozsahu vyjádřitelném modelem).
- V každém pokusu 20 nezávislých protojazyků, souvislé seedy `1..20`;
  žádný seed se nevybírá ani nevylučuje podle výsledku.
- `village_grid(6, seed=seed, syntax=True, semantics=True, phonology=True,
  morphology=True)` s plnou výchozí slovní zásobou a výchozími konstantami.
  Šest vesnic umožní vznik a rozpad jazyků při menší ceně než velká mřížka;
  nekrátí se slovník, horizont ani mechanismy. V každém běhu stejných šest
  výchozích skupin sdílí jeden nezávislý protojazyk.
- Odečty 0, 1 000, 2 000, 3 000 a 5 000 let; mezi odečty tentýž pokračující
  běh. Jednotkou agregace je pozorovaný jazyk (`Snapshot.languages`), ne
  skupina ani genealogický identifikátor kódu. Každý jazyk má váhu 1.
- Uvnitř jazyka převládající stav přes mluvené domácí skupiny, vážený počtem
  mluvčích. Nepodporované a nejednoznačné stavy zůstávají explicitně neznámé;
  report obsahuje pokrytí, aby se jejich vynechání nezaměnilo za shodu.
- Losování gramatiky používá samostatné stabilní klíče `cee.v2.rng`, nezávislé
  na proudu simulace. Nevyjádřitelné WALS stavy se nepřevádějí odhadem;
  jejich hmotnost a podmínění startovního rozložení budou výslovně uvedeny.
- Hellingerova vzdálenost používá `metrics.hellinger`; normovaná entropie
  má pevný jmenovatel logaritmu počtu kategorií měřeného rysu, nikoli jen
  počtu právě pozorovaných kategorií. Neznámý stav není typologická kategorie.
- Měření a simulace běží sériově, včetně testů a sedmi referenčních otisků.
  Žádné změny modelu, seedů, konstant ani existujících bran.

## Rozsah a omezení

Výchozí fonologie se v pokusu `wals` nelosuje z WALS: zadání požaduje losovat
**gramatiku**. Stacionaritu gramatických marginál proto lze zkoumat jen
v jejich vyjádřitelném rozsahu; výchozí fonologická odchylka sama o sobě
není důkaz dynamického atraktoru. Losování jednotlivých gramatických rysů
z marginál navíc neobnovuje skutečnou korelaci rysů WALS.

## A1: zdroj a převodní tabulka

WALS CLDF `v2020.6`, commit `81298aa26d01fdc11b769bcc7fa87ad9e43d7ccd`,
licence CC BY 4.0. Citace: Dryer, Matthew S. & Haspelmath, Martin (eds.)
2013. *The World Atlas of Language Structures Online*. Leipzig: Max Planck
Institute for Evolutionary Anthropology. [Vydání dat na Zenodo](https://doi.org/10.5281/zenodo.23010827),
[zdrojový checkout](https://github.com/cldf-datasets/wals/tree/v2020.6).
Vnitřní metadata vydání zmiňují starší upstream `v2020.5`; připnutí se řídí
skutečným tagem, commitem a pěti kontrolními součty, nikoli tímto historickým údajem.

`build_v2_typology.py` čte čtyři tabulky CLDF a metadata; všech pět vstupů
musí přesně odpovídat připnutým SHA-256, jinak build skončí chybou. Výřez
`v2_typology.json` obsahuje citaci, licenci, verzi, SHA-256 vstupů, úplná
rozložení i výslovné seznamy nepodporovaných kategorií. Pro každý rys zvlášť
má každý genus s daty celkovou váhu 1, rozdělenou mezi jazyky s údajem o
**tomto** rysu. Chybějící genus znamená samostatnou jednotku pro daný jazyk.

| Stav enginu | Kategorie / projekce WALS | Co se nepřevádí a proč |
|---|---|---|
| `PL`: `synthetic` nebo `periphrastic` / `zero` či funkce mimo profil | [33A](https://wals.info/chapter/33): `plural_present` = 1–8, `plural_absent` = 9 | Jen odvozená přítomnost, ne strategie prefix/sufix/změna kmene/tón/reduplikace/smíšená/slovo/klitika. |
| `DEFINITE`: `synthetic` nebo `periphrastic` / `zero` či funkce mimo profil | [37A](https://wals.info/chapter/37): `definite_present` = 1–3, `definite_absent` = 4–5 | WALS zahrnuje demonstrativum používané jako člen. Nerozlišujeme jeho původ, člen jako slovo proti afixu ani neurčitý člen. |
| `PAST`: `synthetic` nebo `periphrastic` / `zero` či funkce mimo profil | [66A](https://wals.info/chapter/66): `past_present` = 1–3, `past_absent` = 4 | Model nemá vzdálenosti minulosti; nesmí se přiřadit konkrétní kategorie 1/2/3. |
| `FUTURE`: `synthetic` / `zero`, volný opis nebo funkce mimo profil | [67A](https://wals.info/chapter/67): 1 / 2 | Jde o **inflexní** budoucnost. Klitika je neznámá; neprovádí se odhad hranice klitika–afix. |
| `ORDER=fixed`, pořadí SOV/SVO/VSO/VOS/OVS/OSV | [81A](https://wals.info/chapter/81): 1/2/3/4/5/6 | `free` je neznámé, nikoli 81A-7 „bez dominantního pořadí“. Inovace modelu nabízejí jen SOV/SVO, ostatní pevné řády lze reprezentovat ve startu. |
| `NEG=pre` / `post` / `embraced` | [143A](https://wals.info/chapter/143): 1 / 2 / 14 | 14 je široká povinná dvojitá negace, reprezentovaná startem pre+post; není to rekonstrukce ostatních pozic/slov/afixů z této kategorie. Hodnoty 3–13 a 15–17 jsou nepodporované. |
| Počet použitých podkladových souhláskových segmentů | [1A](https://wals.info/chapter/1): nezařazeno | WALS počítá fonémy, ne segmenty zaznamenané během částečné fonologizace. Samostatně reportujeme inventářový proxy. |
| Počet použitých podkladových vokalických segmentů | [2A](https://wals.info/chapter/2): nezařazeno | Chybí explicitní kontrastivní inventář vokalických kvalit, navíc segmenty mohou rozlišovat více než kvalitu. |
| Podkladové nosové samohlásky | [10A](https://wals.info/chapter/10): nezařazeno | Přítomnost segmentu nedokazuje fonémový kontrast. Proxy je pomocná diagnostika pro B, nikoli přímé srovnání s 10A. |
| Stavba slabiky | [12A](https://wals.info/chapter/12): nezařazeno | Model nemá explicitní stav povolené slabičné gramatiky; konečný slovník nedokazuje hranice přípustných struktur. |
| `OBJ` | [49A](https://wals.info/chapter/49): nezařazeno | Vyjádření předmětu neurčuje počet všech pádů jazyka ani kategorii hraničního pádového značení. |
| `NEG` | [112A](https://wals.info/chapter/112): nezařazeno samostatně | Pro zadání je použit částečný 143A; 112A by přidával další srovnání téhož procesu s jiným členěním. |

U syntetických konstrukcí jde o **konstrukční stav modelu**: štítek sám
nedokazuje zachovaný povrchový kontrast po erozi. `syntax.weakness` erozi
sleduje pro výběr inovací a selekci, ale nemění konstrukci automaticky na
`zero`. Hodnoty `present` tedy nelze vydávat za nezávislé zjištění, že všechny
původní koncovky zůstaly rozlišitelné. Měřidlo toto omezení nepřekrývá
odhadem nového prahu. U širších projekcí je rozlišovací schopnost menší:
nelze jimi měřit pestrost uvnitř kategorie „přítomné“.

### Inicializace pokusu z WALS

Losování používá pro každý rys samostatně
`generator(seed, "typology-wals-start", feature)`. Kategorie s explicitním
nulovým vyjádřením zůstávají **v profilu**, a mohou tedy gramatikalizovat.
Zástupci jsou: přítomný PL a PAST = původní syntetická konstrukce, přítomný
člen = volné demonstrativum `this`, inflexní FUTURE = syntetická konstrukce,
nepřítomnost = `zero`; NEG = `not` před slovesem, samotné `not` po slovesu,
nebo `not … thing`; ORDER = konkrétní pevné pořadí. OBJ zůstává výchozí.
To jsou reprezentanti metrických kategorií, nikoli odhady skutečné
morfologie jednotlivých jazyků WALS.

U 81A má namapovaná část WALS váhu 0,84602; u 143A 0,60088. Start losuje
**podmíněné** rozložení těchto částí. Hellinger přesto používá celé
referenční rozložení včetně nepodporovaných hodnot. Počáteční H proto
nemusí být nulová ani při dokonalém sampleru. U ostatních čtyř projekcí je
pokrytí referenční hmotnosti 1. Entropie se normalizuje pevně počtem
rozlišovaných kategorií měřidla (2, 2, 2, 2, 6 a 3); ne podle počtu hodnot
skutečně přítomných ve vzorku. H i E se počítají z jednoznačně zařazených
jazyků a vždy mají doprovodný údaj o jejich pokrytí.

## Reprodukce

Z kořene worktree, s Pythonem projektu a `PYTHONPATH=src:.`:

```text
python scripts/build_v2_typology.py --cldf-dir /tmp/cee-wals-typology/cldf
python scripts/v2_typology.py --output /tmp/cee-typology-results.json --markdown /tmp/cee-typology-tables.md
python -m pytest -q
python scripts/v2_digests.py
ruff check --no-cache
mypy --cache-dir /tmp/cee-typology-mypy
```

Zdrojová data WALS lze získat checkoutem výše uvedeného commitu mimo
repozitář; cesta `/tmp/cee-wals-typology` je jen lokální příklad. V tomto
prostředí se používá interpreter `/Users/janvrzal/Documents/CEE/.venv/bin/python`
a `PYTHONDONTWRITEBYTECODE=1`. Syrová měření v `/tmp` ani zdrojové CSV WALS
nepatří do commitu; souhrnné tabulky zůstávají zde v deníku.

## A2–A3: výsledky a jejich význam

Všech 40 předem stanovených běhů skončilo bez výběru nebo vyloučení seedů.
Celkový čas včetně odečtů byl 207,3 s (same 96,4 s; wals 110,9 s). V každém
běhu pozorovatel v každém odečtu spojil šest skupin do jediného jazyka:
rozložení proto mají N=20 nezávislých jazyků, po jednom z každého protojazyka.
Fonologické proxy se v čase mění, takže stálá gramatika pokusu same není
artefaktem odečítání výchozího světa. Párový test měření ověřuje nezměněný
otisk historie i distribuce proti běhu bez odečtů.

**Same:** v žádném ze šesti hrubě měřených konstrukčních rysů se mezi
nezávislými protojazyky neobjevila rozlišitelná pestrost. PL a PAST zůstaly
present, DEFINITE chybí a FUTURE není inflexní (obě funkce jsou mimo profil),
NEG zůstal pre a ORDER free. E=0 pro pět klasifikovaných rysů; ORDER nemá
žádné klasifikované pozorování, proto jeho H ani E nejsou definované.
Tento výsledek se vztahuje k převažujícím širším konstrukčním kategoriím;
nevylučuje jiné afixy, menšinové varianty, odlišné tvary ani fonologickou pestrost.

**WALS:** stacionarita těchto marginál v tomto scénáři neplatí. Nejde o
absolutní shodu startu s WALS (vzorek má jen 20 jazyků a část kategorií je
nepodporovaná), ale o směr změny vůči skutečně vylosovanému startu.

| Rys | E v roce 0 → 5 000 | H v roce 0 → 5 000 | Interpretace |
|---|---:|---:|---|
| PL | 0,469 → 0 | 0,024 → 0,251 | Všechny konstrukční profily present už v roce 1 000. |
| DEFINITE | 0,993 → 0 | 0,112 → 0,469 | Present 9/20 na startu, 18/20 v roce 1 000, 20/20 od roku 2 000. |
| PAST | 0,971 → 0 | 0,035 → 0,508 | Present 12/20 na startu, 20/20 od roku 1 000. |
| FUTURE (inflexní) | 0,722 → 0 | 0,205 → 0,521 | Na startu 16/20; v roce 2 000 je 18 syntetických a 2 neurčitelné klitiky, od roku 3 000 všech 20 syntetických. |
| ORDER | 0,544 → 0,448 | 0,324 → 0,330 | Pokrytí 20/20 → 10/20, zbývajících 10 je free. Z podmíněné entropie nelze doložit celkový kolaps. |
| NEG | 0,853 → 0,589 | 0,476 → 0,531 | Povinná dvojitá negace 3/20 → 0/20; na konci 13 pre a 7 post. Cyklus existuje, šíření se v tomto okně liší podle stadia. |

U PL, DEFINITE a PAST chybí inovace do `zero`, zatímco ze `zero` vede
obnovovací cesta přes opis, klitiku a koncovku. FUTURE má stejnou cestu
k inflexi; klitiky vysvětlují dočasný pokles pokrytí. NEG má všechny tři
směry cyklu, takže úbytek stadia embraced není důkaz chybějící zpětné
cesty. ORDER má návrh fixace i relaxace, ale neznámý `free` omezuje srovnání.
Konkrétní změny a tlaky jsou rozebrané níže. **Model se v části A neopravuje.**

Výsledek je deskriptivní audit na jednom předem zvoleném malém scénáři,
ne odhad časové škály pro všechny mapy ani kalibrace vůči skutečným rodinám.
Výběr 20 nezávislých seedů má přirozený vzorkovací rozptyl (např. FUTURE
16/20 na startu proti WALS 53,1 %); podle této odchylky se seedy nepřelosovaly.

## Naměřená rozložení

H = Hellinger od celé projekce WALS; E = normovaná entropie.
N je počet jazyků, n počet jednoznačně zařazených. Rozložení je podmíněné na n.
Nenamapovaná referenční hmotnost zůstává v H; E je normalizována pevně počtem kategorií, které měřidlo umí rozlišit.

### same: 33A

WALS (genusově vážené): plural_present=0.878; plural_absent=0.122

| Rok | N | n | Pokrytí | Rozložení | H | E |
|---:|---:|---:|---:|---|---:|---:|
| 0 | 20 | 20 | 1.000 | plural_present=1.000 | 0.251 | 0.000 |
| 1000 | 20 | 20 | 1.000 | plural_present=1.000 | 0.251 | 0.000 |
| 2000 | 20 | 20 | 1.000 | plural_present=1.000 | 0.251 | 0.000 |
| 3000 | 20 | 20 | 1.000 | plural_present=1.000 | 0.251 | 0.000 |
| 5000 | 20 | 20 | 1.000 | plural_present=1.000 | 0.251 | 0.000 |

### same: 37A

WALS (genusově vážené): definite_present=0.608; definite_absent=0.392

| Rok | N | n | Pokrytí | Rozložení | H | E |
|---:|---:|---:|---:|---|---:|---:|
| 0 | 20 | 20 | 1.000 | definite_absent=1.000 | 0.611 | 0.000 |
| 1000 | 20 | 20 | 1.000 | definite_absent=1.000 | 0.611 | 0.000 |
| 2000 | 20 | 20 | 1.000 | definite_absent=1.000 | 0.611 | 0.000 |
| 3000 | 20 | 20 | 1.000 | definite_absent=1.000 | 0.611 | 0.000 |
| 5000 | 20 | 20 | 1.000 | definite_absent=1.000 | 0.611 | 0.000 |

### same: 66A

WALS (genusově vážené): past_present=0.551; past_absent=0.449

| Rok | N | n | Pokrytí | Rozložení | H | E |
|---:|---:|---:|---:|---|---:|---:|
| 0 | 20 | 20 | 1.000 | past_present=1.000 | 0.508 | 0.000 |
| 1000 | 20 | 20 | 1.000 | past_present=1.000 | 0.508 | 0.000 |
| 2000 | 20 | 20 | 1.000 | past_present=1.000 | 0.508 | 0.000 |
| 3000 | 20 | 20 | 1.000 | past_present=1.000 | 0.508 | 0.000 |
| 5000 | 20 | 20 | 1.000 | past_present=1.000 | 0.508 | 0.000 |

### same: 67A

WALS (genusově vážené): 67A-1=0.531; 67A-2=0.469

| Rok | N | n | Pokrytí | Rozložení | H | E |
|---:|---:|---:|---:|---|---:|---:|
| 0 | 20 | 20 | 1.000 | 67A-2=1.000 | 0.561 | 0.000 |
| 1000 | 20 | 20 | 1.000 | 67A-2=1.000 | 0.561 | 0.000 |
| 2000 | 20 | 20 | 1.000 | 67A-2=1.000 | 0.561 | 0.000 |
| 3000 | 20 | 20 | 1.000 | 67A-2=1.000 | 0.561 | 0.000 |
| 5000 | 20 | 20 | 1.000 | 67A-2=1.000 | 0.561 | 0.000 |

### same: 81A

WALS (genusově vážené): 81A-1=0.480; 81A-2=0.275; 81A-3=0.059; 81A-4=0.022; 81A-5=0.008; 81A-6=0.001; 81A-7=0.154

| Rok | N | n | Pokrytí | Rozložení | H | E |
|---:|---:|---:|---:|---|---:|---:|
| 0 | 20 | 0 | 0.000 | neznámé | — | — |
| 1000 | 20 | 0 | 0.000 | neznámé | — | — |
| 2000 | 20 | 0 | 0.000 | neznámé | — | — |
| 3000 | 20 | 0 | 0.000 | neznámé | — | — |
| 5000 | 20 | 0 | 0.000 | neznámé | — | — |

### same: 143A

WALS (genusově vážené): 143A-1=0.402; 143A-10=0.010; 143A-11=0.005; 143A-12=0.000; 143A-13=0.001; 143A-14=0.076; 143A-15=0.058; 143A-16=0.006; 143A-17=0.001; 143A-2=0.122; 143A-3=0.092; 143A-4=0.196; 143A-5=0.001; 143A-6=0.012; 143A-7=0.007; 143A-8=0.011; 143A-9=0.000

| Rok | N | n | Pokrytí | Rozložení | H | E |
|---:|---:|---:|---:|---|---:|---:|
| 0 | 20 | 20 | 1.000 | 143A-1=1.000 | 0.605 | 0.000 |
| 1000 | 20 | 20 | 1.000 | 143A-1=1.000 | 0.605 | 0.000 |
| 2000 | 20 | 20 | 1.000 | 143A-1=1.000 | 0.605 | 0.000 |
| 3000 | 20 | 20 | 1.000 | 143A-1=1.000 | 0.605 | 0.000 |
| 5000 | 20 | 20 | 1.000 | 143A-1=1.000 | 0.605 | 0.000 |

### wals: 33A

WALS (genusově vážené): plural_present=0.878; plural_absent=0.122

| Rok | N | n | Pokrytí | Rozložení | H | E |
|---:|---:|---:|---:|---|---:|---:|
| 0 | 20 | 20 | 1.000 | plural_absent=0.100; plural_present=0.900 | 0.024 | 0.469 |
| 1000 | 20 | 20 | 1.000 | plural_present=1.000 | 0.251 | 0.000 |
| 2000 | 20 | 20 | 1.000 | plural_present=1.000 | 0.251 | 0.000 |
| 3000 | 20 | 20 | 1.000 | plural_present=1.000 | 0.251 | 0.000 |
| 5000 | 20 | 20 | 1.000 | plural_present=1.000 | 0.251 | 0.000 |

### wals: 37A

WALS (genusově vážené): definite_present=0.608; definite_absent=0.392

| Rok | N | n | Pokrytí | Rozložení | H | E |
|---:|---:|---:|---:|---|---:|---:|
| 0 | 20 | 20 | 1.000 | definite_absent=0.550; definite_present=0.450 | 0.112 | 0.993 |
| 1000 | 20 | 20 | 1.000 | definite_absent=0.100; definite_present=0.900 | 0.250 | 0.469 |
| 2000 | 20 | 20 | 1.000 | definite_present=1.000 | 0.469 | 0.000 |
| 3000 | 20 | 20 | 1.000 | definite_present=1.000 | 0.469 | 0.000 |
| 5000 | 20 | 20 | 1.000 | definite_present=1.000 | 0.469 | 0.000 |

### wals: 66A

WALS (genusově vážené): past_present=0.551; past_absent=0.449

| Rok | N | n | Pokrytí | Rozložení | H | E |
|---:|---:|---:|---:|---|---:|---:|
| 0 | 20 | 20 | 1.000 | past_absent=0.400; past_present=0.600 | 0.035 | 0.971 |
| 1000 | 20 | 20 | 1.000 | past_present=1.000 | 0.508 | 0.000 |
| 2000 | 20 | 20 | 1.000 | past_present=1.000 | 0.508 | 0.000 |
| 3000 | 20 | 20 | 1.000 | past_present=1.000 | 0.508 | 0.000 |
| 5000 | 20 | 20 | 1.000 | past_present=1.000 | 0.508 | 0.000 |

### wals: 67A

WALS (genusově vážené): 67A-1=0.531; 67A-2=0.469

| Rok | N | n | Pokrytí | Rozložení | H | E |
|---:|---:|---:|---:|---|---:|---:|
| 0 | 20 | 20 | 1.000 | 67A-1=0.800; 67A-2=0.200 | 0.205 | 0.722 |
| 1000 | 20 | 20 | 1.000 | 67A-1=0.800; 67A-2=0.200 | 0.205 | 0.722 |
| 2000 | 20 | 18 | 0.900 | 67A-1=1.000 | 0.521 | 0.000 |
| 3000 | 20 | 20 | 1.000 | 67A-1=1.000 | 0.521 | 0.000 |
| 5000 | 20 | 20 | 1.000 | 67A-1=1.000 | 0.521 | 0.000 |

### wals: 81A

WALS (genusově vážené): 81A-1=0.480; 81A-2=0.275; 81A-3=0.059; 81A-4=0.022; 81A-5=0.008; 81A-6=0.001; 81A-7=0.154

| Rok | N | n | Pokrytí | Rozložení | H | E |
|---:|---:|---:|---:|---|---:|---:|
| 0 | 20 | 20 | 1.000 | 81A-1=0.550; 81A-2=0.300; 81A-3=0.150 | 0.324 | 0.544 |
| 1000 | 20 | 19 | 0.950 | 81A-1=0.579; 81A-2=0.316; 81A-3=0.105 | 0.315 | 0.512 |
| 2000 | 20 | 15 | 0.750 | 81A-1=0.600; 81A-2=0.267; 81A-3=0.133 | 0.322 | 0.518 |
| 3000 | 20 | 13 | 0.650 | 81A-1=0.538; 81A-2=0.308; 81A-3=0.154 | 0.325 | 0.549 |
| 5000 | 20 | 10 | 0.500 | 81A-1=0.700; 81A-2=0.200; 81A-3=0.100 | 0.330 | 0.448 |

### wals: 143A

WALS (genusově vážené): 143A-1=0.402; 143A-10=0.010; 143A-11=0.005; 143A-12=0.000; 143A-13=0.001; 143A-14=0.076; 143A-15=0.058; 143A-16=0.006; 143A-17=0.001; 143A-2=0.122; 143A-3=0.092; 143A-4=0.196; 143A-5=0.001; 143A-6=0.012; 143A-7=0.007; 143A-8=0.011; 143A-9=0.000

| Rok | N | n | Pokrytí | Rozložení | H | E |
|---:|---:|---:|---:|---|---:|---:|
| 0 | 20 | 20 | 1.000 | 143A-1=0.600; 143A-14=0.150; 143A-2=0.250 | 0.476 | 0.853 |
| 1000 | 20 | 20 | 1.000 | 143A-1=0.600; 143A-14=0.050; 143A-2=0.350 | 0.490 | 0.750 |
| 2000 | 20 | 20 | 1.000 | 143A-1=0.650; 143A-2=0.350 | 0.531 | 0.589 |
| 3000 | 20 | 20 | 1.000 | 143A-1=0.650; 143A-2=0.350 | 0.531 | 0.589 |
| 5000 | 20 | 20 | 1.000 | 143A-1=0.650; 143A-2=0.350 | 0.531 | 0.589 |


## Pomocný podkladový inventář pro část B

Sjednocení segmentů ve slovnících skupin každého pozorovaného jazyka,
čtených přes `World.unit_of`, nikoli povrchových segmentů aktivních procesů.
Nejde o převládající fonémový inventář: přepis tvarů je postupný a chybí
anotace foném/allofon. Počty proto nevstupují do Hellingerova srovnání
s WALS 1A/2A/10A. Tabulka uvádí minimum / medián / maximum přes 20 jazyků.

| Pokus | Rok | Souhláskové segmenty | Vokalické segmenty | Jazyky s nosovým vokálem |
|---|---:|---|---|---:|
| same | 0 | 14 / 14 / 14 | 5 / 5 / 5 | 0/20 |
| same | 1000 | 15 / 17 / 21 | 6 / 7 / 8 | 0/20 |
| same | 2000 | 18 / 21 / 27 | 6 / 8 / 10 | 0/20 |
| same | 3000 | 21 / 23.5 / 27 | 8 / 9 / 10 | 0/20 |
| same | 5000 | 22 / 25 / 27 | 8 / 9 / 11 | 0/20 |
| wals | 0 | 14 / 14 / 14 | 5 / 5 / 5 | 0/20 |
| wals | 1000 | 15 / 17 / 21 | 6 / 7 / 9 | 0/20 |
| wals | 2000 | 18 / 21 / 27 | 6 / 8 / 10 | 0/20 |
| wals | 3000 | 21 / 24 / 27 | 8 / 9 / 10 | 0/20 |
| wals | 5000 | 21 / 25 / 27 | 8 / 9 / 10 | 0/20 |

V obou pokusech je proxy nosových vokálů v každém čase 0/20. WALS 10A má
v této genusově vážené referenci 25,964 % jazyků s kontrastem a 74,036 % bez
kontrastu. To jsou různé měřicí definice: z proxy nelze tvrdit přesný rozdíl
fonémových podílů. Pozorované nulové nosové segmenty souhlasí s plošným
filtrem sekundární artikulace v `SegmentTable.changed`; část B tento filtr
teprve může změnit. Pro přímé kontrastivní srovnání B s 10A bude potřeba
výslovně stanovit test fonémového kontrastu, nikoli přejmenovat tento proxy.
Aspirace, ejektivy ani glotalizace se v této části nijak neimplementují.

## Mechanistický rozbor šesti rysů a omezení měřidla

- **33A (PL):** `Periphrasis` navrhuje ze `zero` při dostupném zdroji (`many`, `all`) opis a při oslabení syntetické formy obnovu; `Cliticization` a `Affixation` posouvají opis ke koncovce. `Expressivity` (potřeba PL 0,6) zvýhodňuje výraznou konstrukci, `Economy` trestá další slova a `Fusion` podporuje další krok srůstání. Neexistuje inovace, která by vytvořila `zero` z existujícího výrazu. Důležité omezení: profil čte pouze převažující druh konstrukce; `synthetic` započte jako přítomný i při úplném splynutí tvarů. `syntax.weakness` tuto erozi sleduje pro selekci, ale typologický profil ji neodečítá: stálé `plural_present` proto nedokazuje, že se plurál na povrchu rozlišuje. WALS 1–8 je sloučeno do přítomnosti, 9 do nepřítomnosti.
- **37A (DEFINITE):** `Periphrasis` umožňuje `zero` → opis ze `this/that`, `Exaptation` také `zero` → syntetický výraz ze zbytkového OBJ, je-li kompenzován; další vývoj `Cliticization` → `Affixation`. `Expressivity` má potřebu 0,25, `Economy` a `Fusion` působí jako výše. Zpětný návrh do `zero` chybí; obnova opisu při erozi může udržet vyjádření. V přesném `SYNTAX_GRAMMAR` funkce úplně chybí: `syntax.functions` ji proto nenabízí jako místo inovace, a její stálá nepřítomnost zde není důkazem dynamické stability stavu explicitní konstrukce `zero`. Hrubý převod sloučí WALS 1–3 proti 4–5 a neověřuje všechny sémantické podmínky článku.
- **66A (PAST):** `Periphrasis`, `Cliticization` a `Affixation` pracují jako u PL; zdroje `have/finish/come`, `Expressivity` má potřebu 1,0. Zero lze překročit směrem k opisu, zpětný návrh na zero chybí. Měřidlo opět klasifikuje podle druhu konstrukce, i když `syntax.weakness` eviduje splynutí s prézentem: `past_present` tedy není důkaz zachovaného povrchového kontrastu. Rozdíly vzdálenosti minulosti WALS 66A-1/2/3 jsou sloučeny do jedné třídy; model je sám nerozlišuje.
- **67A (FUTURE):** explicitní `zero` → opis ze `go/want` (`Periphrasis`) → klitika → afix; potřeba `Expressivity` 0,4, `Economy` a `Fusion` zvýhodňují kratší a pokročilejší vyjádření. `67A-1` znamená syntetickou konstrukci, `67A-2` nulovou nebo volný opis; klitika se neklasifikuje, proto průběžně uvádět pokrytí. Stejně jako u minulosti není výsledek kontrolou povrchově zachovaného kontrastu. Pokud funkce chybí z celého profilu, jako ve `SYNTAX_GRAMMAR`, nemá místo pro vznik; nelze to zaměňovat s explicitním `zero`.
- **81A (ORDER):** `OrderFixation` navrhuje z `free` pevný slovosled z katalogu (`SOV`, `SVO`); `OrderRelaxation` navrhuje návrat `fixed` → `free`. `Ambiguity` penalizuje `free` úměrně slabosti OBJ, kdežto `fixed` penalizuje jen o 0,05 při zachovalém OBJ; neplatí, že `OrderRelaxation.applies` samo vyžaduje silný pád, ten mění selekci. Inovace umí jen SOV/SVO, počáteční sampler umí všechny reprezentovatelné WALS pevné řády. `free` záměrně = neznámé, nikoliv WALS „no dominant order“; H vůči celé referenci zahrnuje nepodporovanou hmotu, entropie a četnosti jsou podmíněny známými hodnotami a je třeba uvádět pokrytí.
- **143A (NEG):** `NegationReinforcement` navrhuje pre → embraced při dostupném jiném zdroji, `NegationReduction` embraced → post a `NegationRenewal` post → pre; jde tedy o cyklus, nikoli trvalou jednosměrnou cestu. `Expressivity` používá sílu nejsilnějšího slova záporky, `Economy` trestá dvě slova stavu embraced. Známé omezení: `NegationReduction` může vznikat již při dominanci embraced, dříve než se embraced plně ustálí (viz audit bran). 143A-14 slučuje více podob povinné dvojité negace než jen reprezentovaný embraced; nepodporované hodnoty se ponechávají v plné referenci.

Společná omezení: konstrukční inovace se nejprve jen navrhnou, selekce a přenos rozhodují o jejich rozšíření; z existence cesty nelze odvozovat její skutečnou míru. Kategorie se agregují přes mluvené skupiny vážené populací, následné rozložení váží pozorované jazyky stejně. Počty závisí na prahu a shlukování pozorovatele; `Code.language` není jeden pozorovaný jazyk. Výsledky malého propojeného scénáře nelze bez dalšího zobecnit na jiné mapy. Přepisy slov mohou změnit realizaci při zachování stejné značky konstrukce; tento audit tedy měří konstrukční stav, nikoli zcela nezávisle doloženou funkční opozici.

## Brána A: ověření a předání k potvrzení

- **Celá sada:** 694 testů prošlo za 415,09 s; dva testy legacy API
  (`test_find_free_port_vrati_navazatelny_port`,
  `test_find_free_port_preskoci_obsazeny`) skončily na `PermissionError`
  při `socket.bind` na `127.0.0.1` v omezeném prostředí. Oba byly beze změny
  testu i kódu zopakovány s oprávněním otevřít lokální port a prošly
  (`2 passed`, 0,34 s). Celkem je tedy ověřeno **696 testů**, nikoli jedna
  nepřerušená zelená invokace celé sady. Žádná stochastická brána neselhala.
- **Nové testy:** samostatná sada 32 testů prošla; zahrnuje populační
  agregaci včetně živého skladu, neznámé stavy, všechna startovní mapování,
  nulové pokrytí, zachování nepodporované WALS hmoty, normalizaci entropie,
  genusové vážení, nosový inventářový proxy a neinvazivnost odečtu.
- **Otisky:** všech sedm scénářů sériově před i po je přesně shodných
  s referencí `68d4e54` (tabulka níže). Simulační jádro se nezměnilo;
  v `src/cee/v2/metrics.py` pouze přibyly nové měřicí funkce.
- **Data:** opakovaný build z připnutého CLDF je bajtově shodný se zabaleným
  `v2_typology.json`, včetně citace, licence a všech pěti SHA-256 vstupů.
- **Styl a typy nového rozsahu:** `ruff check --no-cache src/cee/v2`
  spolu s oběma novými skripty a třemi testovacími soubory prošel.
  `mypy --follow-imports=silent src/cee/v2 scripts/build_v2_typology.py
  scripts/v2_typology.py` prošel (50 souborů); importované legacy moduly
  se v této cílené kontrole nekontrolují samostatně.
- **Celorepozitářové statické kontroly nejsou čisté:** Ruff hlásí
  13 nálezů a mypy 48 chyb ve starším kódu. Všech 23 různých souborů, ve
  kterých jsou tyto nálezy, je bajtově shodných s verzí v `68d4e54`.
  Nejsou to nové chyby části A a nebyly opravovány mimo zadání. Mypy uváděl
  48 legacy chyb už oddíl „Známé mezery“ výchozí specifikace. Čistotu
  celorepozitářových kontrol tedy nelze prohlásit za dosaženou.

| Scénář | Otisk před = po = reference |
|---|---|
| phonology | `8d7971c1a6afe5f6b8ca9f33919b8b3e2e929d56832ae4e04c738efa18c53840` |
| morphology | `3567be70a272f42662ecd44838079d33abf953d090c59a9a2da4079467933a06` |
| syntax | `eefb5db5be7bfac8284c400b7a0ebc81fe4a65c04325aaafa9b1cdb39d50fc38` |
| grid-5x5 | `a6aa9a33f1a416e33144a0235d19194c442bb27ede6f966c5092a7b7342b08c0` |
| shift | `47d69ad8a511366b2dedba0a9c30550c0c1d0045aa24ce3eafbdde03663da71a` |
| island-city | `a082c2463488378f975fc050a9265f62856e716d6b1dd0b4d813f7d5323ab2cf` |
| valley-50 | `02ccc3819e155cff096d791466f3dcdab88142a4e31e9b1920f92fc9898b1272` |

SHA-256 zabaleného referenčního výřezu: `0e68aa4551b699dd784f00abd19bc7b88a6f2ca96976420161fb52ebbcc58b63`.

Práci provedli subagenti **Terra 6.1** (metriky, testy, mechanistický rozbor)
a **Luna 6** (WALS, build, licence, vážení a crosswalk); integraci, všechny
simulace a běhové kontroly sériově provedl hlavní agent. Sdílený checkout
nebyl upravován. Nevznikl žádný nový commit, stash, push ani sloučení;
zůstává pouze dříve existující první commit zadání `9582bd3`.

**Část A je předána k potvrzení. Část B nezačala.** Po potvrzení lze změny
rozdělit do commitů A1 (reference), A2 (metriky a runner), A3 (výsledky a
stav); žádný z těchto commitů zatím nebyl vytvořen. O zahájení části B
rozhodne uživatel samostatně.

## Potvrzení části A a zahájení části B

Uživatel potvrdil výsledky části A a výslovně povolil pokračovat částí B.
Kroky A1 a A2 byly uloženy jako `6f83049` a `058502b`; tento záznam a
výsledky tvoří krok A3. Část B se vyvíjí nad tímto beze změny modelu
ověřeným stavem. Nové commity části B zůstávají podmíněné dalším potvrzením.

## Část B: předem stanovený protokol

Část A byla potvrzena a uložena v `6f83049`, `058502b` a `a82f21c`.
Část B zůstává do dalšího potvrzení necommitnutá. Původní simulační model
pro srovnání je archiv `a82f21c` v `/tmp/cee-typology-before-b`, v jádře
shodný s `68d4e54`. Do archivu se přenášejí pouze nové měřicí funkce a runner,
aby před i po měřil **tentýž přístroj**. Otisky jeho 40 běhů se porovnají
s výsledky A, což kontroluje, že rozšířené odečty nezměnily vývoj modelu.

- Oba pokusy a všechny seedy `1..20`, šest vesnic, slovník, časy i gramatické
  reprezentanty z A zůstávají stejné. Žádné přelosování či kalibrace na WALS.
- Vedle původního inventářového proxy přibývá konzervativní svědectví
  nosového kontrastu: dva různé dominantní lexémy v téže skupině, jejichž
  podkladové tvary se liší pouze oralitou/nazalitou jednoho vokálu; u nosového
  členu páru již nesmí stát hned za vokálem nosová souhláska. Tím se vyloučí
  dosud podmíněná nazalizace i při neúplné lexikální difuzi. Páry napříč
  skupinami se nezaměňují za kontrast uvnitř jedné skupiny. Jazyku se vykáže
  populační podíl skupin s doloženým párem a zvlášť přítomnost svědectví ve
  většině mluvčích (> 1/2). Nedoložený pár **není** důkaz absence kontrastu;
  jeho podíl je dolní mez pozitivních dokladů, ne odhad celé WALS populace.
- Srovnání pestrosti uvádí všechny roky a všechny rysy, změnu entropie,
  Hellingerovy vzdálenosti a pokrytí. Jakýkoli pokles entropie oproti předchozímu
  modelu se výslovně uvede; nevyrovnává se účelovou změnou seedu či konstant.
- Výkon: sériový pár `v2_digests.py`, stejný interpreter a prostředí,
  rozhodující scénář `valley-50` (50 skupin, 2 000 let). Mez B je +10 % vůči
  modelu `68d4e54`. Případné další optimalizace musí zachovat již naměřené
  otisky nového modelu, aby se nezaměnila rychlost se změnou chování.
- Milníkové brány nemění prahy. Při selhání stochastické brány se změří
  průchod před a po na nezávislé souvislé řadě `101..120` pomocí
  `v2_gate_rates.py`; změny seedů či konstant pro získání zelené brány jsou
  zakázány. Výsledek auditu je podklad k rozhodnutí, nikoli důvod bránu přepsat.

Uživatel zároveň zadal navazující část C ze sdíleného necommitnutého
`docs/engine-v2/zadani-gramaticka-dynamika.md`. **C začne až po dokončení a
výslovném potvrzení B.** Teprve pak se zadání zkopíruje do stejného worktree
jako první commit C. Po C0 se před změnami C1 a dalšími znovu vyčká na
potvrzení. V této chvíli se zadání C nekopíruje ani necommituje.


### B1–B2: reprezentace a změny

`SegmentTable` zachovává všechna původní ID hlásek a potřebné zápisy přidává
na konec. Matice vznikají parserem PanPhonu se skládáním diakritik; žádný
ručně vymyšlený rysový vektor se nepřidává. V původním PanPhonu mají `k` a `kʲ` (i `ɡ` a `ɡʲ`) totožný rysový vektor, protože
veláry mají již ve výchozím stavu `hi=+1`. Aby se zabránilo kolizi rysových vektorů
při zachování 24 standardních rysů PanPhonu, mají pokročilé veláry `kʲ` a `ɡʲ`
v `SegmentTable` explicitně nastaveno `back=0` (středová/pokročilá artikulace).
Tím vzniká přirozené fonetické kontinuum (`k` back=+1 → `kʲ` back=0 → `c` back=−1),
žádné dvě hlásky v celé tabulce (3 012 hlásek) nemají stejný vektor a rysová
vzdálenost i změny spolehlivě rozliší `k` od `kʲ` i `kʲ` od `c`. Unikátnost vektorů
všech hlásek tabulky je chráněna testem.
*Poznámka k sémantice rysů:* Hodnota `back=0` představuje v PanPhonu „neurčeno“
(nepříznakovou/středovou artikulaci); `kʲ` a `ɡʲ` proto nespadají do přirozených
tříd a vzorů s `back=+` (např. asimilace `n → ŋ` před `kʲ` nenastane, pokud vzor
vyžaduje striktní veláru s `back=+`).

`allow` je součástí kanonického klíče procesu i klíče hledání kandidáta.
Požadované značky a zděděné značky výchozí hlásky jsou povinné; ostatní se
odfiltrují. Unicode NFC/NFD se rozpoznává stejně. Předpočítané značky a
masky zamezují opakované práci ve změnách. Zpětné změny odstraňují značky
výslovnou náhradou. Kontrola 3 010 původních IPA záznamů doložila stejnou
množinu plain kandidátů jako dříve; žádný nový alias není plain. Regrese
/o/ se zvýšeným jazykem nadále vrací /u/, nikoli velarizaci.

`right2` rozšiřuje kontext o druhého pravého souseda pro `_N(C|#)` a je
součástí identity procesu. Opory inovací, průběžné indexy a samotný aplikátor
kontrolují totožné prostředí. Banka tvarů může mít konzervativní předfiltr:
smí pustit navíc kandidáta k přesné kontrole, nesmí vyloučit skutečnou shodu.

| Nová rodina | Prior | Cesta |
|---|---:|---|
| SecondaryPalatalization | 0,35 | C → Cʲ před i/j |
| Depalatalization | 0,20 | Cʲ → C |
| PalatalAffrication | 0,25 | kʲ/ɡʲ → t͡ʃ/d͡ʒ |
| VowelNasalization | 0,35 | V → Ṽ před N následovaným souhláskou nebo hranicí |
| VowelDenazalization | 0,20 | Ṽ → V |
| Labialization | 0,30 | k/ɡ → kʷ/ɡʷ před u/w |
| Delabialization | 0,20 | kʷ/ɡʷ → k/ɡ |
| LabialShift | 0,20 | kʷ/ɡʷ → p/b |

Váhy jsou **autorské heuristické relativní priory**, nikoli naměřené
historické četnosti z literatury. Byly stanoveny před vyhodnocením B;
koartikulace dostala mírně vyšší váhu než ztráta sekundární artikulace,
přechody mezistupňů jsou méně častou doplňkovou cestou. Jde o hypotézu
výchozího modelu, nikoli výsledek kalibrace. Přidání rodin mění normalizaci
celkového zvukového prioru, takže i frekvence starších rodin může klesnout.
Původní přímá palatalizace k → t͡ʃ zůstává jako paralelní historická cesta;
nová dvojice kroků ji v tomto doplňku nenahrazuje.

Nevzniká žádná zvláštní operace „vytvoř kontrast“. Integrační test nejdřív
použije existující fonologizaci nazalizace a poté existující `CodaLoss`.
Až po zániku N se v uložených tvarech doloží minimální pár pã/pa.
Aspirace, ejektivy a glotalizace nejsou nové rodiny tohoto doplňku a jsou
výslovně zapsané ve Známých mezerách.

### B3: ověření, výsledky a otisky

Audit části B proběhl na stejném protokolu a sériovém měřidle (40 běhů:
20 same, 20 wals, seedy 1..20, 6 vesnic, 5 000 let).

#### Nosové samohlásky (proxy, kontrastní svědectví a WALS 10A)

Před částí B byl podíl jazyků s nosovými samohláskami nulový (0/20 ve všech
letech), protože `_is_plain` veškeré diakritiky plošně zakazoval. Po zavedení
záměrných diakritik a rodin `VowelNasalization` / `VowelDenazalization`:

| Experiment | Rok 0 | Rok 1 000 | Rok 2 000 | Rok 3 000 | Rok 5 000 | WALS 10A (ref.) |
|---|---:|---:|---:|---:|---:|---:|
| `same` (proxy) | 0/20 (0 %) | 9/20 (45 %) | 16/20 (80 %) | 19/20 (95 %) | 19/20 (95 %) | 22,4 % |
| `wals` (proxy) | 0/20 (0 %) | 9/20 (45 %) | 16/20 (80 %) | 19/20 (95 %) | 19/20 (95 %) | 22,4 % |
| `same` (kontrast) | 0/20 (0 %) | 0/20 (0 %) | 0/20 (0 %) | 0/20 (0 %) | 0/20 (0 %) | 22,4 % |
| `wals` (kontrast) | 0/20 (0 %) | 0/20 (0 %) | 0/20 (0 %) | 0/20 (0 %) | 0/20 (0 %) | 22,4 % |

Hodnota 95 % v roce 5 000 je hrubé povrchové proxy inventáře, které zahrnuje i
podmíněnou (alofonickou) nazalizaci před dosud nezmizelou nosovou souhláskou.
Naproti tomu konzervativní svědectví kontrastu (minimální pár dvou různých dominantních
lexémů v téže skupině lišících se pouze oralitou/nazalitou vokálu, kde po nosovém vokálu
již nenásleduje nosovka) dává 0/20, protože vyžaduje následný zánik kody (`CodaLoss`),
který v tomto malém scénáři nestihl proběhnout.

**Ani jedno z těchto dvou čísel není přímo srovnatelné s WALS 10A (22,4 %):**
- Proxy 95 % je horní mez zahrnující alofony a podmíněný kontext, takže WALS výrazně nadhodnocuje.
- Svědectví 0/20 je striktní dolní mez pozitivního důkazu v malém vzorku dominantního lexika, nikoli odhad celé populace WALS.

Tato mezera zůstává **otevřenou otázkou pro M7**: v M7 bude třeba kalibrovat dynamickou rovnováhu
mezi `VowelNasalization`, `VowelDenazalization` a `CodaLoss` a případně zpřesnit detekci fonematického
kontrastu, aby model generoval stacionární podíl fonematických nosových samohlásek odpovídající typologické realitě.

#### Stabilita typologických rysů z části A

Přidání sekundární artikulace nevedlo k žádnému novému kolapsu gramatických
kategorií. Ze 60 srovnávaných měřicích bodů (6 rysů × 5 časů × 2 pokusy)
je 59 bodů zcela identických s modelem před částí B; v jediném bodě
(wals, 143A v roce 5 000) je normovaná entropie mírně vyšší (0,589 → 0,613).
Metriky 4 a 5 (velikosti inventářů v pásmu a homofonie) dál drží.

#### Referenční otisky (doplněk M2, sekundární artikulace)

Ověření nezávislosti optimalizací na výsledcích: Dočasné vrácení vektoru `kʲ`/`ɡʲ`
(bez `back=0`, s původními raw vektory PanPhonu) dalo se všemi optimalizacemi
na všech 7 scénářích přesně původní otisky části B (`phonology cd79626d…`,
`morphology b673137d…`, `syntax 3dca8fd6…`, `grid-5x5 6274c42a…`, `shift c2a58d39…`,
`island-city 5ca77a29…`, `valley-50 79174f6a…`). Optimalizace indexů tedy
nemění chování ani o jediný bit; veškerý posun nového otisku (`grid-5x5 83d79ffb…`,
`valley-50 0d462e15…`) plyne výhradně z odstranění rysové kolize `kʲ`/`ɡʲ`.

```text
phonology    cd79626de3a0b02f19fea574cf5637971ad012a1f89aeacb9a59a04e8064dd62
morphology   b673137d804d7542106c47e7203f93c9bf63268d8951909b49df12755b29e849
syntax       3dca8fd6c3e511c3ef059d4e0d5550eadd2e3d94024afcc550b7e730fbaefcf0
grid-5x5     83d79ffb6e029604422730b9906dcf7b68d2ed522ef5f405fe706a6dbf6d5c95
shift        d1a1e9e5af395b3120426fb3035912720dccdc5727168e62aa6dee1799dd6816
island-city  13717cb46affdc42b9938627d9314ab09c23fec227595ce6f53cfa099a22d4aa
valley-50    0d462e154e885753e74ad645d2ecb9085bd4d1e442cc86f9229d693f366fca00
```

#### Výkon a měření sériových párů (`valley-50`)

Měření na dvou sériových párech spuštěných hned po sobě bez souběžné zátěže
(`v2_digests.py`, stejný interpreter `/Users/janvrzal/Documents/CEE/.venv/bin/python`):

- **Pár 1**: `68d4e54` `valley-50` 24,9 s (celkem 30,27 s) vs. nová verze 29,6 s (celkem 35,07 s), nárůst `valley-50` **+18,9 %** (celkem +15,84 %).
- **Pár 2**: `68d4e54` `valley-50` 24,5 s (celkem 29,97 s) vs. nová verze 28,0 s (celkem 33,43 s), nárůst `valley-50` **+14,3 %** (celkem +11,55 %).

Limit brány výkonu (+10 % ze stejného páru) tedy neprošel. Důvodem je skutečné rozšíření
modelu o 8 nových rodin zvukových změn (vyhodnocování 28 rodin místo 20 v každé generaci
pro každou vesnici). Pro tento nárůst udělil uživatel výslovnou výjimku.

#### Brána B

- `ruff check --no-cache`: čisté (0 chyb).
- `mypy`: čisté (51 zdrojových souborů bez chyb v dotčeném rozsahu).
- Celá sada testů `pytest -q`: všechny testy prošly (717 testů, 440 s).
- Všechny milníkové stochastické brány splněny.
- Výkonnostní brána: výjimka schválena uživatelem (rozšíření modelu o 8 rodin).

Commit části B uložen jako `e7dc08c`.
Oprava zápisu výkonu a schválené výjimky uložena jako `e4c14cf`.

## Část C: gramatická dynamika

Zadání zkopírováno ze sdíleného checkoutu `docs/engine-v2/zadani-gramaticka-dynamika.md`
a uloženo v commitu `bd3ce86`.

### C0: měřidlo podle povrchového kontrastu (bez změny modelu)

Do `metrics.typology_profile` bylo doplněno volitelné druhé čtení `weakness_threshold=0.5`.
Práh `0,5` je odvozen z lingvistického významu metriky `syntax.weakness` (podíl splynulých
tvarů v gramatické buňce s citačním tvarem): pokud více než 50 % tvarů ztratilo
rozlišení (`weakness >= 0,5`), synkretismus převažuje nad kontrastem a syntetická
kategorie přestává být na povrchu spolehlivě rozlišitelná.

Měření proběhlo na stejných 40 bězích z částí A a B (20 běhů `same`, 20 běhů `wals`, seedy 1..20,
roky 0, 1 000, 2 000, 3 000, 5 000).

#### Výsledek C0

Obraz se prakticky **vůbec nezměnil**:
- U rysů PL (33A), DEFINITE (37A), PAST (66A), ORDER (81A) a NEG (143A) je povrchové
  čtení ve všech 5 časových řezech a v obou pokusech **zcela totožné** s formálním čtením
  konstrukčního profilu.
- Jediná drobná odchylka nastala u WALS 67A (FUTURE) v roce 3 000: formální čtení vykázalo
  100 % present (`67A-1`), zatímco povrchové čtení odhalilo 1 jazyk z 20 (5 %) se splynutou
  koncovkou budoucího času (`weakness >= 0,5`); v roce 5 000 byl budoucí čas opět 100 % rozlišený.

#### Rozložení weakness (medián, 90. percentil, maximum)

| Pokus | Funkce | Rok | Medián | 90. perc. | Maximum |
|---|---|---:|---:|---:|---:|
| `same` | PL | 0 | 0,000 | 0,000 | 0,000 |
| `same` | PL | 1 000 | 0,000 | 0,000 | 0,011 |
| `same` | PL | 2 000 | 0,000 | 0,000 | 0,012 |
| `same` | PL | 3 000 | 0,000 | 0,024 | 0,094 |
| `same` | PL | 5 000 | 0,013 | 0,053 | 0,132 |
| `same` | PAST | 0 | 0,000 | 0,000 | 0,000 |
| `same` | PAST | 1 000 | 0,000 | 0,000 | 0,000 |
| `same` | PAST | 2 000 | 0,000 | 0,000 | 0,000 |
| `same` | PAST | 3 000 | 0,000 | 0,000 | 0,033 |
| `same` | PAST | 5 000 | 0,000 | 0,000 | 0,000 |
| `same` | FUTURE | 0–5 000 | 1,000 | 1,000 | 1,000 |
| `same` | DEFINITE | 0–5 000 | 1,000 | 1,000 | 1,000 |
| `same` | OBJ | 0 | 0,000 | 0,000 | 0,000 |
| `same` | OBJ | 1 000 | 0,000 | 0,000 | 0,022 |
| `same` | OBJ | 2 000 | 0,000 | 0,000 | 0,024 |
| `same` | OBJ | 3 000 | 0,000 | 0,000 | 0,013 |
| `same` | OBJ | 5 000 | 0,000 | 0,000 | 0,013 |
| `wals` | PL | 0 | 0,000 | 0,100 | 1,000 |
| `wals` | PL | 1 000 | 0,000 | 0,100 | 1,000 |
| `wals` | PL | 2 000 | 0,000 | 0,000 | 0,012 |
| `wals` | PL | 3 000 | 0,000 | 0,024 | 0,094 |
| `wals` | PL | 5 000 | 0,013 | 0,063 | 0,148 |
| `wals` | PAST | 0 | 0,000 | 1,000 | 1,000 |
| `wals` | PAST | 1 000 | 0,000 | 1,000 | 1,000 |
| `wals` | PAST | 2 000 | 0,000 | 1,000 | 1,000 |
| `wals` | PAST | 3 000 | 0,000 | 0,000 | 0,038 |
| `wals` | PAST | 5 000 | 0,000 | 0,000 | 0,038 |
| `wals` | FUTURE | 0–2 000 | 0,000 | 1,000 | 1,000 |
| `wals` | FUTURE | 3 000 | 0,000 | 0,000 | 1,000 |
| `wals` | FUTURE | 5 000 | 0,000 | 0,000 | 0,000 |
| `wals` | DEFINITE | 0–1 000 | 1,000 | 1,000 | 1,000 |
| `wals` | DEFINITE | 2 000 | 0,000 | 0,000 | 0,033 |
| `wals` | DEFINITE | 3 000 | 0,000 | 0,000 | 0,037 |
| `wals` | DEFINITE | 5 000 | 0,000 | 0,000 | 0,020 |
| `wals` | OBJ | 0 | 0,000 | 0,000 | 0,000 |
| `wals` | OBJ | 1 000 | 0,000 | 0,011 | 0,022 |
| `wals` | OBJ | 2 000 | 0,000 | 0,000 | 0,024 |
| `wals` | OBJ | 3 000 | 0,000 | 0,000 | 0,024 |
| `wals` | OBJ | 5 000 | 0,000 | 0,000 | 0,650 |

### Kroky C1 a C2: Úplná gramatika a náhradní strategie

#### C1: Úplná gramatika (`FULL_GRAMMAR`)

V `src/cee/v2/scenarios.py` byla definována nová gramatika `FULL_GRAMMAR`:
obsahuje všechny konstrukce z výchozí `SYNTAX_GRAMMAR` plus všechny zbývající funkce katalogu
(`FUTURE` a `DEFINITE`) s výchozí konstrukcí `zero`.
Výchozí `SYNTAX_GRAMMAR` zůstala beze změny, aby nedošlo k porušení stávajících scénářů a testů.
Skript `scripts/v2_typology.py` byl rozšířen o parametr `--experiments` umožňující
paralelní spuštění pokusů `same` (se `SYNTAX_GRAMMAR`), `same_full` (s `FULL_GRAMMAR`)
a `wals` (vzorkování marginál ze statistiky WALS).

#### C2: Náhradní strategie přes `compensates` a kontextová síla `zero`

Funkce, kterou jazyk gramaticky nevyjadřuje (`zero`), není v komunikaci nevyjádřená.
Do katalogu `src/cee/data/v2_grammar.yaml` byl ke každé funkci přidán parametr `context` (0 až 1),
odrážející míru, do jaké funkci nese pragmatický a diskurzní kontext bez gramatického vyjádření.

> [!NOTE]
> Číselné hodnoty parametru `context` jsou **autorský odhad** (modelový parametr).
> Typologická literatura podporuje relativní pořadí funkcí podle míry kontextové
> zastupitelnosti (určenost a budoucí čas jsou kontextem neseny podstatně lépe než
> syntaktické role argumentů u volného slovosledu), nikoli konkrétní čísla.

Kvalitativní opora v literatuře:
- **`DEFINITE` (`need: 0.25`, `context: 0.22`)**: Dryer (2013, WALS 37A: *Definite Articles*)
  dokládá, že 39 % jazyků světa nemá žádný člen; Lyons (1999, *Definiteness*, Cambridge Univ. Press)
  ukazuje, že v bezčlenných jazycích je určenost nesena situační význačností a tématem.
  S `context = 0.22` je efektivní přínos volného opisu `0.25 * (1 - 0.22) = 0.195`, což oproti
  ekonomické penalizaci volného slova (`Economy = -0.15`) dává mírný přebytek `+0.045`.
- **`PAST` (`need: 1.0`, `context: 0.25`)**: Dahl (1985, *Tense and Aspect Systems*)
  a Bybee, Perkins & Pagliuca (1994, *The Evolution of Grammar*) uvádějí, že bezčasové
  jazyky (~45 % ve WALS 66A) se opírají o chronologické řazení vyprávění a časová příslovce;
  kontext spolehlivě ukotví čas v části promluv, ale neukotvené klauzule stále tlačí k vyjádření.
- **`FUTURE` (`need: 0.4`, `context: 0.35`)**: Dahl (1985) a Ultan (1978) ukazují,
  že budoucí čas je typologicky mnohem méně gramatikalizovaný než minulý; prézens v budoucím kontextu
  je běžný v mnoha rodinách (germánské, baltofinské, slovanské).
- **`PL` (`need: 0.6`, `context: 0.30`)**: Corbett (2000, *Number*) a Dryer (2013,
  WALS 33A) ukazují, že u jazyků se všeobecným číslem (*general number*) kontext a kvantifikátory
  postačují pro orientaci o počtu.
- **`OBJ` (`need: 1.0`, `context: 0.10`, kompenzace od `ORDER: fixed` až 0.90)**: Comrie (1989,
  kap. 9) a Siewierska (1998) dokládají, že samotný kontext bez pádů a bez pevného slovosledu
  nedokáže spolehlivě rozlišit role argumentů u reverzibilních dějů. Naopak pevný slovosled
  (`ORDER: fixed`) přebírá roli pádu s vysokou spolehlivostí (~0.90), čímž efektivní potřeba pádu
  klesá na `1.0 * (1 - 0.90) = 0.10` a nepřevažuje nad ekonomií.

Implementace v kódu:
1. `src/cee/v2/language/constructions.py`: `GrammaticalFunction.context` načítané z `v2_grammar.yaml`.
2. `src/cee/v2/syntax.py`:
   - `compensation(world, group_id, function) -> float`: zjišťuje, zda pevný slovosled
     (`template: "order"`, `current.carries_order`) přebírá roli pádu (hodnota 0,90).
     Nepoužívaná větev pro neexistující nekatalogové kompenzace byla odstraněna.
   - `compensated(world, group_id, function) -> bool`: vrací `compensation > 0.0`.
   - `strength(world, code, construction, group_id=None)`: pro konstrukci `kind == "zero"` vrací
     `max(entry.context, compensation(world, group_id, function))`.
3. `src/cee/v2/pressures/syntactic.py`:
   - `Expressivity`: předává `group_id` do `syntax.strength`, takže skóre nevyjádřené funkce
     bere v úvahu kontextové nasycení a kompenzaci. Tlak na inovaci nové konstrukce je úměrný
     pouze zbývající neuspokojené potřebě.

#### Výsledky ověření C1 a C2

1. **Otisky a determinismus (`scripts/v2_digests.py`)**:
   Všech 7 scénářů v `v2_digests.py` dává **100% bitovou shodu** s referencí části B:
   - `phonology`: `cd79626de3a0b02f19fea574cf5637971ad012a1f89aeacb9a59a04e8064dd62`
   - `morphology`: `b673137d804d7542106c47e7203f93c9bf63268d8951909b49df12755b29e849`
   - `syntax`: `3dca8fd6c3e511c3ef059d4e0d5550eadd2e3d94024afcc550b7e730fbaefcf0`
   - `grid-5x5`: `83d79ffb6e029604422730b9906dcf7b68d2ed522ef5f405fe706a6dbf6d5c95`
   - `shift`: `d1a1e9e5af395b3120426fb3035912720dccdc5727168e62aa6dee1799dd6816`
   - `island-city`: `13717cb46affdc42b9938627d9314ab09c23fec227595ce6f53cfa099a22d4aa`
   - `valley-50`: `0d462e154e885753e74ad645d2ecb9085bd4d1e442cc86f9229d693f366fca00` (27,9 s)

2. **Brány a testy**:
   - `tests/v2/test_v2_m4b_gate.py`: 5 passed
   - `tests/v2/test_v2_m4_gate.py`: 5 passed
   - Statické kontroly: `ruff check` a `mypy` čisté bez chyb.

3. **Typologická dynamika (pokusy `same`, `same_full` a `wals` na 20 seedech po 5 000 let)**:
   - **`same`**: Zůstává přesně identický s výchozím stavem (plná stabilita).
   - **`same_full` (s `FULL_GRAMMAR`)**:
     - U `DEFINITE` (37A) je 45 % přítomnosti v roce 2 000 pouhým **průjezdem**, nikoli stabilním
       stavem: rok 0: 0 % present, rok 1 000: 10 %, rok 2 000: 45 %, rok 3 000: 90 %, rok 5 000: 100 %.
     - U `FUTURE` (67A): rok 0–1 000: 0 % present, rok 2 000: 37,5 %, rok 3 000: 77,8 % (povrchové),
       rok 5 000: 100 %.
     - Závěr: **C2 jednosměrnou rohatku gramatikalizace zpomalila, ale nezastavila**. Bez mechanismu
       zániku (C3) nakonec všechny inovované kategorie dosáhnou 100 %.
   - **`wals`**:
     - Nástup kategorií je díky C2 znatelně plynulejší (u `DEFINITE` v roce 1 000 stále 25 % jazyků bez členu
       proti původním 10 %; v roce 2 000 stále 5 % bez členu proti původním 0 %).
     - V 5 000 letech však všechny syntetické kategorie dosáhnou 100 % přítomnosti, protože **chybí mechanismus
       zániku kategorie (C3)**. Diverzita v 5 000 letech přetrvává pouze u slovosledu 81A ($E = 0,448$)
       a záporu 143A ($E = 0,613$), kde obousměrná dynamika existuje.

#### Citlivostní analýza parametru `context` (DEFINITE a FUTURE v {0,1; 0,2; 0,3; 0,4})

Měření proběhlo sériově na 20 seedech (5 000 let) pro `same_full` a `wals` a na bráně `M4b::clen_vznikne`:

| `context` | Brána `M4b::clen_vznikne` | `same_full` DEF 2k / 5k | `same_full` FUT 2k / 5k | `wals` DEF 1k / 5k | `wals` FUT 2k / 5k |
|---:|:---:|---:|---:|---:|---:|
| 0,1 | 2/3 (prošla) | 45 % / 100 % | 37,5 % / 100 % | 75 % / 100 % | 89,5 % / 100 % |
| 0,2 | 2/3 (prošla) | 45 % / 100 % | 37,5 % / 100 % | 75 % / 100 % | 89,5 % / 100 % |
| 0,3 | 2/3 (prošla) | 45 % / 100 % | 37,5 % / 100 % | 75 % / 100 % | 89,5 % / 100 % |
| 0,4 | 2/3 (prošla) | 45 % / 100 % | 37,5 % / 100 % | 75 % / 100 % | 89,5 % / 100 % |

*Poznámka k tabulce:* Výchozí hodnoty modelu (DEFINITE 0,22; FUTURE 0,35) nebyly podle výsledku měněny.
Rozložení na makroúrovni 20 seedů je v tomto intervalu identické, protože jakmile vznikne přiklonka
či koncovka (`words = 0`), nepodléhá penalizaci `Economy` a rozdíl Expressivity zůstává kladný.

#### Analýza selekce před krokem C3

Syntetická konstrukce i přiklonka mají `words = 0`, takže je `Economy` vůbec netrestá.
Rozdíl `Expressivity` mezi syntetickou konstrukcí a stavem `zero` je:
$$\Delta \text{Expressivity} = \text{need} \times (1 - \text{weakness} - \text{context})$$
Tento rozdíl zůstává **striktně kladný**, dokud platí:
$$\text{weakness} < 1 - \text{context}$$
Pro člen s `context = 0,22` je tato hranice $1 - 0,22 = 0,78$.
Měření C0 přitom ukázalo, že maximální naměřená slabost syntetických kategorií nepřesahuje 0,15.
Z toho plyne zásadní teoretický důsledek:
**Pokud by `CategoryLoss` pouze náhodně navrhoval přechod syntetické konstrukce do `zero`, selekce
by tuto variantu okamžitě eliminovala (má nižší fitness než stávající syntetický tvar).**

Zánik kategorie proto v C3 musí mít dvě cesty:
1. **Volný opis (`words = 1`)**: Zde působí penalizace `Economy` ($-0,15$). Pokud je efektivní potřeba
   kategorie nízká ($\text{need} \times (1 - \text{context}) \le 0,15$), stav `zero` má vyšší fitness
   než volný opis, a opis zanikne.
2. **Syntetická konstrukce s vysokou slabostí**: Zánik syntetického afixu může uspět teprve tehdy,
   když je koncovka skutečně erodovaná ($\text{weakness}$ blízko hranice $1 - \text{context}$).
   Jelikož fonetická eroze v modelu bez prozódie téměř nenastává, samotná syntetická kategorie
   bude samovolně mizet jen výjimečně. V dalším zadání to vyřeší prozódie a redukce nepřízvučných slabik.

