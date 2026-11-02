# Pojmy: oblasti, domény a půjčitelnost

Sepsáno 2026-11-02. Rozhodnutí s uživatelem: rovnováhu mezi lidovou řečí,
psanou normou a kontaktem engine nemá hledat jednou provždy, ale dát ji
autorovi světa do ruky jako parametry. K tomu musí engine vědět, k čemu
jsou slova vázaná: slova moci vymění nová elita, náboženská slova přijdou
s liturgií, věci obchodem a základní slovní zásoba zůstává.

## Data (krok 2, hotovo)

`cee.v2.concept_data` čte výřez z World Loanword Database
(Haspelmath & Tadmor 2009; CLDF lexibank/wold, commit `1df62b9`, CC BY 4.0)
v `cee/data/v2_concepts.json`, který staví `scripts/build_v2_concepts.py`:

- **pojmy enginu**: všech 149 pojmů `DEFAULT_CONCEPTS` má význam WOLD (přes
  glos Concepticonu; 15 ručně: `child` CHILD (YOUNG HUMAN), `god` DEITY,
  `hair` HAIR (HEAD), `know`, `lie` LIE DOWN, `louse` HEAD LOUSE, `mountain`
  MOUNTAIN OR HILL, `old`, `river` FLOWING BODY OF WATER, `spirit` SOUL,
  `stone` STONE OR ROCK, `war` BATTLE, `trade` TRADE OR BARTER, `close` SHUT,
  `ritual` WORSHIP);
- **katalog**: 1 458 významů WOLD doložených aspoň v 10 jazycích, tedy
  zásobník pro větší slovník; význam z jednoho slovníku (ID `…-999xx`, 1–2
  tvary, často skóre 1,0) se nebere;
- u každého významu: sémantická oblast (24), doména enginu, podíl jazyků
  s přejatým slovem (`borrowed`), skóre stáří a jednoduchosti, počet jazyků,
  zda patří do základního seznamu WOLD.

Půjčitelnost oblastí (průměr významů aspoň v 10 jazycích):

| oblast | doména | půjčitelnost |
|---|---|---|
| Modern world | culture | 0,63 |
| Religion and belief | religion | 0,42 |
| Clothing and grooming | culture | 0,38 |
| The house | culture | 0,37 |
| Law | power | 0,34 |
| Social and political relations | power | 0,32 |
| Food and drink, Agriculture | culture | 0,31 |
| Warfare and hunting | power | 0,29 |
| Animals | core | 0,28 |
| Possession, Basic actions and technology | culture | 0,26–0,27 |
| Cognition, Speech and language, Time | learned | 0,24 |
| Quantity, The physical world | culture, core | 0,22 |
| Emotions and values | learned | 0,21 |
| Motion | core | 0,19 |
| Kinship, The body, Spatial relations | core | 0,14–0,15 |
| Sense perception | core | 0,12 |
| Miscellaneous function words | core | 0,08 |

Z pojmů enginu se nejvíc půjčují *law* 0,63, *horse* 0,57, *boat* 0,54,
*king* 0,53 a *town* 0,47; nejméně *this* a *we* 0, *lie*, *stand*, *nose*
a *say* pod 0,03.

Oblasti moci se v průměru půjčují jen zhruba dvakrát víc než domácí jádro
a zhruba jako kultura. Že slova moci vymění nová elita (normanská *duke,
count, baron* proti přeživšímu *earl*), tedy není obecná vlastnost slov, ale
kontaktní situace: proto domény a ne jen půjčitelnost.

Přiřazení oblastí k doménám je náš úsudek (`DOMAINS` v build skriptu):

- `power`: společnost a politika, právo, válka a lov; působí na ně nová
  elita;
- `religion`: náboženství a víra; liturgie;
- `culture`: moderní svět, zemědělství, jídlo, oblečení, dům, vlastnictví,
  technika, kvantita; obchod a kontakt;
- `learned`: řeč a jazyk, myšlení, emoce a hodnoty, čas; čtení a škola;
- `core`: tělo, prostor, vnímání, pohyb, příroda, příbuzenství, zvířata,
  funkční slova.

Pojem mimo data (vlastní pojem autora) má doménu `core` a průměrnou
půjčitelnost katalogu, dokud je autor nezadá.

## Další kroky

3. **Domény v mechanismech**: cizí elita (`Conquest`, `ForeignElite`)
   přenáší hlavně slova `power`, liturgie hlavně `religion` (dnes váží
   jen vzácností), obchod (`TradeShift`) hlavně `culture`, čtení a škola
   hlavně `learned`, a všude podle půjčitelnosti. Váhy domén pro každý
   kanál budou parametry světa. Kalibrovat proti WOLD: podíl přejatých
   slov podle oblasti a kontaktní situace (WOLD má u slov i typ kontaktu
   a účinek: koexistence, náhrada, vložení).
4. **Nástroje pro autora**:
   - vlastní pojmy ve specifikaci světa (vymyšlené i reálné: název,
     doména, frekvence, volitelně příbuzné pojmy a půjčitelnost);
   - volba velikosti slovníku z katalogu (100, 200, 1 000 slov)
     s varováním, že jiný slovník dá jiné výsledky; tahy náhody jsou vázané
     na ID pojmu, takže stávající slova se nepřelosují, ale slova spolu
     soutěží;
   - parametry rovnováhy v UI.

   Pro velký slovník chybí:
   - **sémantické vztahy**: posuny významu z DatSemShift a kolexifikace
     z CLICS, CC BY 4.0. Výřez `build_v2_core_semantics.py` je jen pro
     149 pojmů a pro katalog se přegeneruje;
   - **frekvence pojmů**: engine je dnes generuje (prvních 20 pojmů 0,9,
     ostatní log-rovnoměrně náhodně), WOLD je nemá. Hledáme zdroj
     s licencí CC0, CC BY, MIT nebo BSD. `wordfreq` má data pod CC BY-SA,
     a proto nejde.
