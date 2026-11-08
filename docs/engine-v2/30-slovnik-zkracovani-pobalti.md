# 30. Náhrada slov, data protojazyků, Čechy a Pobaltí, sporadické změny (M11)

Stav: **zapsáno na větvi `slovnik`** (8. 11. 2026).

Podnět uživatele: „Co třeba vzniklo namísto češtiny?“, pak „Tak to vše oprav“ (náhrada
základních slov dlouhými složeninami, výpůjčky bez ohledu na význam, díry v protojazycích,
staroslověnština jako start, jeden region Slavia, mezery ze specifikace) a „A co baltské jazyky?
Ty máme?“.

## Náhrada základních slov

**Nález.** Ve Slavii v roce 1900 byla ryba *dəmivwədə* („zvíře-voda“), noc *sənɪt͡sjʊsə*
(„slunce-ne“), matka odvozenina od „slunce“. Odvozenin a složenin bylo 7 950 z 32 700 slov,
o polovinu delších než zděděná slova, a tytéž cesty vyhrávaly ve všech rodinách. Tři příčiny:

1. **Nic netrestalo délku.** Tlak na jasnost slova trestá jen obroušené krátké slovo.
2. **Průhlednost platila všude.** Odvozenina a složenina měly výhodu motivace +0,15 i v cizím
   jazyce, kam se dostaly výpůjčkou, ačkoli tam jsou neprůhledné. Výhodná výpůjčka se pak šířila
   přes kontinent.
3. **Obroušené slovo nemělo čím se obnovit** než vzácnou cestou grafu (DatSemShift „slunce →
   matka“ z jednoho jazyka).

**Zapsáno:**

- `lexical_length_cost` 0,3 (Zipfův zákon zkracování; Piantadosi, Tily a Gibson 2011): nové slovo
  delší než zavedené slovo i než medián slov jazyka má nevýhodu váha × (½ + frekvence pojmu) ×
  relativní přesah. Zavedené dlouhé slovo se netrestá: s trestem pro všechny vyhrávaly krátké
  kořeny z ničeho (3 778 místo 507). S 0,6 byla retence 0,908 nad pásmem `m7::retence`, s 0,3
  je 0,896.
- Motivace jen v jazyce, kde slovo vzniklo (Haspelmath 2009): přejatá odvozenina je pro mluvčí
  cizího jazyka neprůhledný kořen.
- Obnova zdrobnělinou vlastního kořene (lat. *auris* → *auricula* → *oreille*; původ `renewal`,
  váha cesty 0,5, bez výhody motivace): vyhraje, když se slovo obrousilo.
- Zkracování dlouhých slov (`clipping`, Bybee 2001): kořen, který vznikl delší než 5 hlásek, se
  může zkrátit na první dvě slabiky (*hlāf-weard* → *lord*). Míra podle délky při vzniku, aby
  průběžné míry platily i po zvukových změnách.
- Kořen z ničeho (`coinage`) má nevýhodu motivace −0,3 místo −0,15: holý nový kořen nemá oporu.

| Evropa, semínko 1 (mezikrok s `lexical_length_cost` 0,6) | dosud | M11 |
|---|---|---|
| zděděná slova | 24 225 (prům. 4,4 hlásky) | 33 362 (3,9) |
| odvozeniny | 4 691 (6,8) | 1 753 (4,7) |
| složeniny | 3 260 (7,3) | 555 (5,5) |
| kořeny z ničeho | 198 | 871 (3,1) |
| zkrácení / metateze / disimilace | – | 2 102 / 291 / 88 |

**Výpůjčky bez ohledu na význam** (balkánský „oheň“ *arboreariu*) byly tentýž jev: výpůjčka nesla
význam dárce, ale dárce měl nesmyslnou odvozeninu („strom → oheň“), která se šířila díky výhodě
motivace. Oprava 2 ho řeší.

Zbývá: obnovy zdrobnělinou se ze substrátu šíří po latinské síti (galské „hrom“ ve ~110
skupinách); u románských jazyků je to uvěřitelné (galské substrátové slovo ve francouzštině).

## Data protojazyků

IE-CoR nemá zájmena, zápor, příbuzenství ani kulturní slova; staroslověnštině a řečtině chybělo
60 ze 149 pojmů, gótštině 79, galštině 91, a engine je dogeneroval (*kdo* = *pæ*, *ne* = *ʊsa*).
Pojmy „kámen, hora, řeka, déšť, hořet, maso, jít, nehet“ IE-CoR má, jen pod jiným ID Concepticonu.

**Zapsáno** (`scripts/build_v2_iecor_words.py`):

- párování podle jména (`ALIASES`);
- autorský doplněk `v2_proto_supplement.json`: standardní slovníkové tvary staroslověnštiny,
  gótštiny, attické řečtiny, galštiny (jen doložené) a litevštiny, ve fonemických konvencích
  IE-CoR. Zdroje s volnou licencí nevyšly: IELexFinal (CC BY) má jen příbuznost bez tvarů, DiACL
  (CC BY) má chybné přiřazení pojmů a nejednotný pravopis;
- přepínač `--scenario` zapíše slova i do `scenarios/evropa.json` a doplní inventář o nové hlásky.

| pojmů ze 149 | dosud | M11 |
|---|---|---|
| staroslověnština | 89 | 148 |
| stará řečtina | 89 | 149 |
| gótština | 70 | 129 |
| galština | 58 | 77 |
| litevština (nová) | – | 144 |

Iberština, dáčtina a baskičtina zůstávají generované (doložení je chudé).

## Čechy a Pobaltí

Scénář Evropy měl jediný region Slavia (= jeden slovanský jazyk) a žádnou baltštinu.

**Zapsáno:**

- **Čechy** (`bohemia`, 9 vesnic, pahorkatina) mezi Germánií a Slavií. Na začátku germánské
  (Markomani), v roce 550 slovanské osídlení ze Slavie (6 osad, podíl 0,3). Česká větev se tak
  odštěpí 1 350 let před rokem 1900, ne 2 400, což zmírní anachronismus staroslověnštiny jako
  startu v roce −500. Praslovanštinu nemáme z dat s volnou licencí (DiACL má 12 výchozích pojmů).
- **Pobaltí** (`baltia`, 9 vesnic) severně od Slavie s jazykem `baltic`: litevština z IE-CoR
  (nejkonzervativnější živý indoevropský jazyk, jako zástupce baltštiny je anachronická méně
  než staroslověnština) a doplněk.
- **Latina má přízvuk podle váhy slabiky** (`weight`, Romania i Evropa).

Semínko 1, rok 1900 (výsledné nastavení):

| pojem | Čechy | čeština | Pobaltí | litevština |
|---|---|---|---|---|
| voda | bwodə | voda | bəðʊu | vanduo |
| hlava | ɡlavə | hlava | ɡælvɛ | galva |
| jazyk | d͡ʒozɯk | jazyk | lʲjɪʒɛfʲ | liežuvis |
| pes | pɪs | pes | ʃʊu | šuo |
| kámen | kamə | kámen | ɛkmʊə | akmuo |
| bůh | bwok | bůh | dɪɛv | dievas |
| dva | dʊvə | dva | dʊ | du |
| kdo | kʊhɔ | kdo | kɑs | kas |

Germánští starousedlíci Čech přežili do roku 1900 jako vlastní jazyk (7 000 lidí vedle 3 000
Slovanů), což odpovídá česko-německému soužití.

**Koncové *ə*** (*ɡlavə*, *dʊvə*) není tah enginu, ale zdravá variace: podíl slov na *ə* je
u slovanštiny podle semínka 24 %, 7 % a 14 %, u latiny 9 %, 31 % a 12 %.

## Mezery ze specifikace

- **Sporadické změny** jednoho slova (Hock 1991, kap. 6), míra 1e-4, bez výhody:
  - metateze likvidy *CoRC* → *CRoC* (psl. *golva* → *glava*, *formaticum* → *fromage*),
    jinak *CRVC* → *CVRC* (*brid* → *bird*);
  - disimilace likvid: druhé ze dvou r se změní v l a naopak (*arbor* → *árbol*).
- **Délka samohlásek:**
  - náhradní prodloužení (`compensatory_lengthening`, Kavitskaya 2002): samohláska + sonora
    nebo frikativa před další souhláskou → dlouhá samohláska, prior 0,25. Jen uvnitř slova:
    s prodloužením i na konci slova (*-am* → *-aː*) si Itálie držela pád (`m8::romanske_pady`
    0,417);
  - krácení dlouhých samohlásek (`vowel_shortening`), prior 0,3, aby se délka nehromadila.
- **Přízvuk podle váhy** (`weight`, WALS 15A): předposlední slabika, je-li těžká (dlouhá
  samohláska nebo zavřená slabika), jinak třetí od konce. Vzniká posunem z předposlední (0,2)
  a třetí od konce (0,3), přechází na předposlední (0,6), první (0,3) a třetí od konce (0,1).
  Ve WALS 14A se počítá jako předposlední (14A-1 převodník nemapuje). Maska dlouhých samohlásek
  se do jádra předává jednou při stavbě banky tvarů (`set_long_vowels`).
- **Prestižní asymetrie výpůjček** (Thomason a Kaufman 1988): váha dárce = vazba × prestiž
  dárce × poměr prestiží dárce a příjemce (`PRESTIGE_ASYMMETRY` 1). Město s prestiží 1 si od
  vesnice s 0,5 půjčí osmkrát méně než ona od něj (dosud dvakrát).
- **Růst nových sídel** (`settlement_growth` 0,3 za generaci, asi 1 % ročně; Livi-Bacci 2017):
  sídlo založené migrací (`Territory::settled`), menší než medián vesnic regionu, roste
  logisticky k němu. Osadníci v Čechách dorostou na 499 lidí na osadu. Sídla scénáře rostou
  jen tak, jak je scénář nastaví: růst všech malých vesnic rozbil pokus `m7::slozitost`, který
  malé a velké vesnice porovnává záměrně.

Chyba nalezená testem: nové slovníkové změny nebyly v seznamu spouštěných změn
(`lexicon::changes`); seznam teď bere `Semantic::ALL`.

## Ověření

**Testy 16 z 16, brány 47 z 47, kalibrace 38 z 38.** `m8::pocet_jazyku` 61,5: pásmo (návrh)
rozšířeno z 10–60 na 10–70 se souhlasem uživatele, protože Evropa má o dva regiony víc (Čechy
a Pobaltí přidají 2–4 jazyky). Retence 0,896,
románské pády 0,500, složitost −0,900 / −1,000 / −0,032.

Semínko 1 s výsledným nastavením: 57 jazyků. Zděděných slov je 26 181 ze 35 700 (73 %),
obnov zdrobnělinou 4 041, odvozenin z grafu 1 438, zkrácení 1 785, složenin 1 082, metatezí 403,
kořenů z ničeho 494, disimilací 24. Tóny jen ve Vaskonii (17 %), Slavia 0 %.

**Otevřené:**

- Obnova zdrobnělinou (váha 0,5) dělá 11 % slov. Retence ji počítá jako náhradu, ačkoli
  *auricula* je s *auris* příbuzná, a obnovy se ze substrátu šíří po latinské síti (galské
  „stát“ ve 163 skupinách). Snížení váhy by zvedlo retenci nad pásmo; potřeba měřit retenci
  podle kořene.

## Pro editor

- Region s jedním jazykem dá jeden jazyk; větve (čeština, polština) potřebují regiony nebo
  hranice států a osídlení (`settlement`).
- Protojazyk z pozdního doložení (staroslověnština, litevština) je anachronismus: editor by měl
  nabídnout začátek jazyka později (osídlení) nebo upozornit.
- Pojmy, které data nemají, engine dogeneruje: editor by je měl ukázat jako vymyšlené.
