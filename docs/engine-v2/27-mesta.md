# 27. Města regionů a vyrovnávání nářečí (M10)

Stav: **zapsáno na větvi `mesta`** (7. 11. 2026), ověření níže.

Podnět uživatele: „udělat ony města regionů, které budou fungovat jako hegemon toho jazyka.
Města historicky fungovala jako houby na populaci, lidé tam umírali a zároveň přicházeli noví
z venkova.“ Cíl: Evropa se po rekalibraci tempa (dok. 24) rozpadala na ~150 „jazyků“ v roce 1900
(`m8::pocet_jazyku`, pásmo 10–60).

## Rozbor

Ze 150 jazyků (semínko 1) bylo 142 jednoskupinových; regiony s kontaktem nebo politikou (Británie,
Řecko, Balkán, Dácie, Kambrie, Hispánie, Galie) se rozpadly na jednovesnické jazyky, regiony bez
kontaktu ne. Sousední vesnice mají **stejné kořeny ve 100 % slov, ale stejnou výslovnost jen ve
2–37 %** (Galie 2 %, Řecko 6 %, Germánie 25 %, Itálie 44 %). Výslovnost slova se v modelu měnila
jen hláskovými změnami: vesnice, které si prosadí jiné změny, se rozcházejí navždy. Chyběl
mechanismus, kterým venkov přebírá výslovnost centra.

## Zapsáno

1. **Město v regionu** (`scenarios::region_world`, `RegionSpec.city` v Rustu i `spec.py`):
   středová vesnice regionu s aspoň dvěma vesnicemi je město, `city_size` (6) × vesnice,
   prestiž + `city_prestige` (0,3), vazba aspoň `city_link` (0,5) ke každé vesnici regionu.
   `city` u regionu přepíše velikost, 0 = bez města.
2. **Město jako hřbitov** (Wrigley 1967; de Vries 1984): `Territory::urban` = `urban_mortality`
   (0,15 za generaci navíc), úbytek doplňuje příliv z venkova; podíl přistěhovalců města drží
   aspoň na této úrovni (`communities::urban_inflow`), takže se městská řeč učí dospělí
   z venkova a vyrovnává nářečí (koiné; Trudgill 1986; Kerswill a Williams 2000).
3. **Vyrovnávání výslovnosti** (`communities::level_forms`, `leveling_rate` 0,1, jen uvnitř
   regionu): skupina převezme
   za generaci u podílu `leveling_rate` × síla vazby × (A_dárce − A) / A_dárce slov výslovnost
   téhož slova od propojené skupiny stejné linie s vyšší přitažlivostí A = prestiž × √populace
   (gravitační model šíření, Trudgill 1974). Vesnice se srovnávají podle města svého regionu;
   srovnávání provincií podle sídla státu (Říma) zastavilo vývoj románských větví. Prestiž sama nestačí: po přechodu na jazyk státu mají všechny skupiny prestiž zrcadlenou
   od sídla (Galie 2,6 všude) a vyrovnávání by se nespustilo. Loajalita vyrovnávání nebrzdí
   (platí vlastnímu jazyku proti cizímu, ne místní výslovnosti proti centru).
4. **Město jako zdroj změn** (Labov 2001): populační exponent sociálního ocenění změn (−1, dok. 24)
   počítá u města s velikostí vesnice (město je síť čtvrtí). Bez toho bylo město 6× konzervativnější
   a vyrovnávání šířilo konzervativní tvary i s pádovými koncovkami na venkov (Romania: všechny
   větve ztratí pád ve 25 % běhů místo potřebných 60 %).
5. **Společné ocenění změn v regionu** (`actuation_coherence` ρ = 0,8): sociální ocenění změny
   ve skupině = √ρ × složka regionu + √(1 − ρ) × místní složka. Změna, která „frčí“ v regionu,
   frčí ve všech jeho vesnicích (uživatelův dřívější „společný směr“).
6. `shift_return` (zpětný tok přechodu, Abrams a Strogatz 2003) zapsán s výchozí 0: v Evropě
   počet jazyků ani ostrůvky nezlepšil (0,5 → 60, 1 → 71 jazyků proti 54).

## Evropa, semínko 1

| nastavení | jazyků v roce 1900 | jednoskupinových | stejný tvar sousedů (Germánie / Galie / Řecko) |
|---|---|---|---|
| bez měst (dosud) | 150 | 142 | 0,25 / 0,02 / 0,06 |
| města | 145 | 135 | |
| města + soudržnost 0,8 | 114 | 98 | 0,37 / 0,05 / 0,16 |
| + vyrovnávání podle prestiže | 98 | 81 | 0,45 / 0,08 / 0,10 |
| + přitažlivost prestiž × √populace | 63 | 39 | 0,71 / 0,31 / 0,41 |
| **+ bez loajality (výchozí)** | **54** | 30 | 0,78 / 0,37 / 0,35 |

Galie, Hispánie a Balkán drží po jednom jazyku. Zbytek tříštění (Řecko 13, Británie 13, Kambrie
12) tvoří drobné ostrůvky jiné linie uvnitř vesnic (latinské rodiny v řeckých a velšských
vesnicích, 50–200 lidí, z římské doby), které nemají centrum své linie, k němuž by se srovnaly.

Tabulka výše je s `leveling_rate` 0,3 a srovnáváním i podle sídla státu. Rozklad na rychlých bězích
(kontinuum 0,05–0,15; Romania „pád ztratí ≥ 3 větve“ aspoň 0,6):

| varianta | kontinuum | Romania |
|---|---|---|
| vše (vyrovnávání 0,3, město konzervativní) | 0,039 | 0,25 |
| bez měst | 0,133 | 0,75 |
| bez vyrovnávání | 0,079 | 0,65 |
| bez soudržnosti | 0,033 | 0,05 |
| město jako zdroj změn, vyrovnávání 0,05 / 0,1 / 0,2 | 0,074 / **0,060** / 0,046 | 0,80 / **0,70** / 0,70 |

Evropa (semínko 1) s vyrovnáváním 0,05 / 0,1: 89 / 65 jazyků.

## Ověření (výchozí: města 6×, vyrovnávání 0,1, soudržnost 0,8)

**Testy prošly, brány 47 z 47, kalibrace 35 z 38.** Splněno nově `m7::kontinuum` 0,060
a `m7::latina_pady` 0,70. Neprošly:

- `m8::pocet_jazyku` **68,5** (pásmo 10–60; před M10 153). Zbývá tříštění v Řecku, Británii
  a Kambrii (ostrůvky jiné linie uvnitř vesnic).
- `m7::latina_poradi` 0,50 (pásmo 0,75–1): koncové *-m* zeslábne dřív, než zanikne pád, jen
  v polovině větví (dřív v pásmu).
- `m9::tempo`, zrychlení kontaktem 2,09 (pásmo 1–2; otevřené od M9d, dok. 26).
