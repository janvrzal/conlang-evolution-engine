# 26. Řetězové posuny a zadané hláskové změny (M9d)

Stav: **zapsáno na větvi `retezeni`** (7. 11. 2026), ověření níže.

Podnět uživatele: „šíří se určité změny napříč celým slovníkem (třeba Grimmův zákon)?“ a dál:
„společný směr jazykové linie … event engineu, který poběží, dokud nebude absolutní většina *p*
změněna na *f*; to spustí tlak na změnu *b* na *p*“.

## Výchozí stav

Dokončená hlásková změna zasáhne celý slovník (12 vesnic, 1 500 let: medián 100 % způsobilých
slov, průměr 93 %, 87 ze 160 změn bez reliktů); postupuje slovo po slově, častá slova napřed
(lexikální difúze). Řadové změny (celá přirozená třída hlásek) existovaly jen s podmínkou okolí
(znělost a frikativizace /V_V, zesílení /#_, zúžení středních samohlásek). Chyběly:

1. řadové posuny **bez podmínky okolí** (Grimmovy kroky);
2. **zadaný posun**, který by se rozběhl a táhl, dokud nepřevládne;
3. **řetězení**: po vyprázdnění třídy (všechna *p* → *f*) má sousední řada zaplnit mezeru
   (*b* → *p*), ne s ní splynout.

## Zapsáno

- **Kandidáti** (`cee_core::candidates`): v rodině `spirantization` „řada neznělých okluziv →
  frikativy“ (*p t k* → *ɸ θ x*, bez podmínky), v rodině `fortition` „řada znělých okluziv →
  nezněle“ (*b d g* → *p t k*) a „řada přídechových znělých → bez přídechu“ (*bʰ dʰ gʰ* → *b d g*).
  Samovolně vznikají zřídka: navazující kroky váha 0,5 (`UNCONDITIONED_SERIES`), počáteční tření
  neznělých 0,2 (`UNCONDITIONED_ONSET`; napříč jazyky vzácné, rozbíhá ho hlavně událost). Ztráta
  znělosti má mírnou nevýhodu (námaha −0,05, zřetelnost 0): bez mezery v řadě by splynula s
  neznělými, ujme se hlavně v řetězu.
- **Událost `sound_shift`** (`events.rs`, `phonology::rows::shift_event`, `spec.py`
  `SoundShiftSpec`): `language`, volitelně `regions`, `family`, `label` (jako
  `LanguageSpec.processes`), `share` (start, výchozí 0,2), `pull` (výchozí 1). Změna dostane ve
  skupinách jazyka výhodu `pull`, **dokud tam nemá všechny mluvčí** (`SHIFT_UNTIL` = 1); pak tah
  skončí. Bez tahu se zadaný posun neujme (start 0,3 udusí výběr ve všech semínkách: ztráta
  zřetelnosti a funkční zatížení *p t k*), s tahem jen do ½ nebo 0,9 se zastaví napůl a proces se
  nikdy neuzavře (živý pak zasahuje i *p* vzniklá jinak a vznikají splynutí).
- **Protikrmení** (Kiparsky 1968: řetězový posun je protikrmící pořadí): změna B, jejíž výstupy
  padnou do třídy, kterou vyprazdňuje změna A bez podmínky okolí (`phonology::rows::fills`,
  `gap_partners`), neposílá své nové tvary do fronty A, jakmile má A ve skupině podíl aspoň ½
  (`cee_core::code_state::Round::no_feed`).
- **Výhoda tahového řetězu** (Martinet 1955, *Économie des changements phonétiques*; Labov
  1994): parametr `chain_shift_weight` (výchozí 1): řadový posun bez podmínky okolí, který zaplňuje
  mezeru po jiném, dostane k sociálnímu ocenění navíc váha × (podíl vyprazdňující změny − ½) / ½.
  Jen řadové posuny: když výhodu dostávala každá změna s výstupem v prázdné třídě, posílila i
  znělost *p* → *b* /V_V, která nová *p* vracela (druhý krok 41 % místo 65 %).
- **Oprava tabulky hlásek** (`SegmentTable::changed`): značka, kterou kóduje měněný rys (ʰ ʱ u
  přídechu, ◌̃ u nosovosti, ʼ, ː, ʷ), se nezachovává, a při stejné vzdálenosti vyhraje hláska
  s kratším zápisem. Dřív změna přidechnutých hlásek končila u nesmyslů (*dʰ* → *ɗʰ*, *ɡʰ* →
  *kʰʰ*, *bʰ* → *ɓʰ*); týkalo se to i starořečtiny (*pʰ tʰ kʰ*).

## Pokus: pokusná indoevropština

12 vesnic, souhlásky *p t k b d ɡ bʰ dʰ ɡʰ s m n r l w j*, generovaný slovník, v roce 25 událost
`sound_shift` (první krok, `share` 0,3, `pull` 1); 6 semínek, 1 500 let. Osud původních hlásek
v zděděných slovech (tvar z ticku 0 proti roku 1500, slova stejné délky, po hláskách):

| výhoda řetězu | *p t k* → *ɸ θ x* | *b d g* → *p t k* | *b d g* → *ɸ θ x* (splynutí) | *bʰ dʰ gʰ* → *b d g* |
|---|---|---|---|---|
| 0 | 88 % | 65 % | 4 % | 6 % |
| **1** | 88 % | 63 % | 9 % | **18 %** |
| 2 | 88 % | 60 % | 10 % | 20 % |

Za 3 000 let (výhoda 0, 4 semínka): *bʰ dʰ gʰ* → *b d g* 49 %; *ɸ θ x* → *β ð ɣ* 25 % (znělost
třených mezi samohláskami, obdoba Vernerova zákona).

**Tahový řetěz z modelu vyplývá sám**: když *p* zmizí, přestane funkční zatížení bránit *b* → *p*
(splynutí by už nerozlišilo žádná slova). To je mechanismus, který uživatel popsal („po většině tlak
na *b* → *p*“); chyběl jen posun, který doběhne. Výhoda řetězu urychlí hlavně třetí krok.
Splynutí řad (*b* → *ɸ*) zůstává možné (4–10 %), jako ve skutečnosti.

## Ověření

**Testy prošly, brány 47 z 47, kalibrace 36 z 38.** Neprošly:

- `m8::pocet_jazyku` 153 (pásmo 10–60): neprocházel už před touto změnou (152, dok. 24).
- `m9::tempo`, zrychlení kontaktem **2,14** (pásmo 1–2; před změnou 1,97). Samotné tempo bez
  kontaktu 0,371 je v pásmu. Zrychlení skoro nezávisí na tom, jak často nové posuny vznikají
  (váhy 0,1–0,5 dávají 2,1–2,4; bez nových kandidátů 1,97): v kontaktním světě se řadové posuny
  ujmou (4 semínka: ztráta znělosti 118×, tření neznělých 82× ve vesnicích) a jeden posun přepíše
  celou řadu hlásek. Interval 12 semínek je široký (dřív 1,4–6,1). Pásmo 1–2 je náš návrh; zdroj
  cíle sám uvádí angličtinu 0,85 a francouzštinu 0,70 proti italštině a sardinštině 0,30, tedy
  poměr až 2,8. Rozšíření na [1; 3] čeká na rozhodnutí uživatele.

Jeden zlatý vektor tabulky hlásek z Pythonu se změnil (1 ze 440): *ɡ* + nosovost dá *ŋ* místo
*kⁿ* (stejná vzdálenost, rozhoduje kratší zápis); předloha `tests/fixtures/segments.json` upravena.
