# UX audit návrhu aplikace

Datum: 6. 11. 2026. Předmět: artefakt [CEE Poloostrov](https://claude.ai/artifact/YVXTN8jtrYjoFWxwRxuvCC)
(verze 2, zdroj `zdroje/aplikace/template.html`, commit 2acc046).

## Metoda

- Průchod všemi devíti obrazovkami ve světlém i tmavém režimu, na šířce 1440, 1280 a 400 px
  (headless Chrome), a čtení kódu stránky.
- Hodnocení podle Nielsenových 10 heuristik se závažností 0–4 (0 = není problém,
  4 = katastrofa, opravit před vydáním), podle zákonů UX (Laws of UX) a podle WCAG 2.2 AA.
- Kontrasty jsou spočtené z tokenů. Velikosti cílů jsou odečtené z CSS.

Audit hodnotí návrh, ne hotovou aplikaci. Kde je chování jen naznačené (tlačítko ukáže
hlášku „v návrhu nefunguje“), hodnotím, co z návrhu vyplývá pro implementaci.

## Shrnutí

Návrh má silné jádro: dvě poloviny (Zadání a Výsledek), jeden čas a věty o dopadu u voleb
jsou srozumitelný model. Výsledky ukazují skutečná data enginu bohatě a věrně. Slabiny jsou
na třech místech:

1. **Chybí bezpečnostní síť zadání.** Nikde se neukazuje ověření světa (`/api/v2/validate`),
   chybí Zpět a smazání události je bez potvrzení i bez vrácení. Návrh také nemá projekt
   a ukládání.
2. **Sliby, které obrazovka nedrží.** Na několika místech vypadá něco jako ovládání, ale
   nic nedělá: neaktivní nástroje, seznam událostí v Atlasu, značky na ose. „Jeden čas“
   neplatí v Dějinách. Jména protojazyků v Zadání se nepotkají se jmény ve Výsledku.
3. **Přístupnost a drobné cíle.** Mapy nejdou ovládat klávesnicí ani je nepřečte čtečka.
   Část textu nemá dost kontrastu a některé cíle jsou menší než 24 px.

### Priority oprav

| # | Nález | Heuristika / zákon | Závažnost |
|---|---|---|---|
| 1 | Zadání neukazuje chyby a varování z ověření; „Spustit“ nic nekontroluje | H5, H9 | 4 |
| 2 | Bez Zpět; smazání události bez potvrzení a vrácení | H3 | 3 |
| 3 | Žádný projekt, ukládání ani stav uložení (obrazovka Projekty vypadla) | H1, H3 | 3 |
| 4 | Jména se nepotkají: protojazyk *Teda* v Zadání je ve Výsledku „lemština“, *Libodi* je „libodzština“ | H2, H4 | 3 |
| 5 | Mapy (canvas) nejdou ovládat klávesnicí a nemají textový popis; řádky seznamů nejsou tlačítka | WCAG 2.1.1, 1.1.1 | 3 |
| 6 | Falešné možnosti: nástroje R a S, klikatelně vypadající seznam událostí v Atlasu, značky na ose jen s tooltipem | H4, Jakob | 3 |
| 7 | Dějiny mají vlastní kurzor po 25 letech, nezávislý na společném roce | H4 | 2 |
| 8 | Červený inkoust nese osm různých významů | Von Restorff, H4 | 2 |
| 9 | Malé cíle: značky na ose 5 px, události v Dějinách 10 × 14 px, malé přepínače kolem 22 px | Fitts, WCAG 2.5.8 | 2 |
| 10 | Text v `--ink-3` má kontrast 2,5 : 1 (světlý), resp. 3,6 : 1 (tmavý) | WCAG 1.4.3 | 2 |

## Nálezy podle heuristik

### H1 Viditelnost stavu systému

- **+** Stav běhu je v liště trvale a slovy („Výsledky odpovídají zadání“, „zastaralé“,
  „Počítá se, rok 1 400 z 2 000“), průběh je i linkou pod lištou.
- **Zastaralé výsledky jsou skoro neviditelné (2).** Položky Výsledku dostanou jen tečku
  „·“ a obrazovky Výsledku zastaralost samy neukazují. Doporučení: proužek nad plátnem
  „Ukazuje se běh z 20:50, zadání se od té doby změnilo · Přepočítat“ a ztlumení dat.
- **Skutečný běh trvá minuty, návrh ukazuje šest sekund (3).** Poloostrov na 2 000 let běží
  zhruba 3 minuty. Návrh nemá odhad zbývajícího času, průběžné kreslení snímků do Atlasu
  ani možnost pracovat dál. Doporučení: Atlas kreslí každý příchozí snímek (API ho dává
  po 100 letech) a lišta ukazuje odhad podle uplynulého času (Doherty).
- **Stav uložení chybí (3).** Starší prototypy měly „Všechny změny uložené“, tady nic.
- **Rok je na Atlasu třikrát (1).** Velké číslo v mapě, hodiny na ose a nadpis karty. Stačí
  osa a jedno místo v mapě.

### H2 Shoda se skutečným světem

- **+** Čeština autora světa: „Svébytnost“, „Obchodní město“, „Řeč na veřejnosti“, věty
  o dopadu u voleb. Jména krajů, jazyků a nářečí se skládají z jazyka světa.
- **Jména protojazyků a výsledků se rozcházejí (3).** V Zadání *Libodi* a *Teda*, ve Výsledku
  „libodzština“ a „lemština“, protože výsledek bere vlastní jméno ze slov (*ləmə*), ne jméno
  ze zadání. Uživatel neví, že lemština je potomek Tedy. Doporučení: u jazyka ve Výsledku
  vždy ukazovat původ („z protojazyka Teda“) a v Zadání náhled jména, které z endonymu
  vyroste.
- **Interní identifikátory na povrchu (2).** Karta kraje ukazuje vsi jako `v0`, `+bal-0`.
  Zvukové změny ukazují rysy `[+cont −strid]` a stadia gramatiky surově anglicky.
  Doporučení: vsi pojmenovat (jméno kraje + číslo, nebo jméno složené z jazyka), rysy
  překládat („zúžení: t → θ mezi samohláskami“) a surový zápis nechat v tooltipu.
- **Souhrn století bez jednotek (1).** „zvuky 2 559 · analogie 1 142“ neříká, čeho je 2 559.
  Doporučení: „2 559 ustálení zvukové změny ve vsích“.

### H3 Kontrola a svoboda uživatele

- **Bez Zpět a Znovu (3).** Editor světa i Dějiny v prototypech Zpět měly. Návrh ho ztratil.
- **Smazání události je okamžité (3).** Odkaz „Odstranit událost“ smaže bez potvrzení
  a bez vrácení. Doporučení: hláška „Událost smazána · Vrátit“ (vzor undo místo potvrzení).
- **Klik na událost v Kronice přepne do Atlasu (2).** Uživatel ztratí místo v Kronice
  a návrat je jen přes lištu. Doporučení: rok nastavit na místě a přechod do Atlasu nabídnout
  odkazem, nebo si pamatovat posun v Kronice.
- **Výběr kraje v Atlasu se ruší jen dalším klikem na tentýž kraj nebo tlačítkem (1).**
  Chybí Esc.

### H4 Konzistence a standardy

- **„Jeden čas“ neplatí všude (2).** Dějiny mají vlastní kurzor `cursor` po 25 letech,
  Výsledek společný `year` po 100 letech. Po přechodu z Atlasu (1 300) do Dějin je kurzor
  jinde, než uživatel čeká. Doporučení: jeden rok; Dějiny ho jen jemněji přichytávají.
- **Stejné gesto, jiný význam (2).** Klik na kraj v Atlasu vybere kraj pro kartu, ve Slovech
  přesune vrt, ve Větvích změní kraj pro slova a v Dějinách nedělá nic. Doporučení: klik
  vždy vybírá kraj a karta ukazuje, co výběr znamená („Vrt: Su“).
- **Tři vzhledy pro totéž rozhodnutí (1).** Přepínače `seg`, záložky a „chip“ (tóny,
  samohlásky) vybírají podobné věci a vypadají různě; tóny vypnuté a zapnuté se liší jen
  rámečkem.
- **Výchozí stav Větví nic neukazuje (2).** Rok je sdílený, takže Větve se otevřou v 1 300,
  kde je rozdíl nulový („0 vsí mluví jinak“). Doporučení: na Větvích ukázat malou křivku
  rozdílu v čase a nabídnout skok na rok největšího rozdílu.
- **Vlastnost kraje a událost se překrývají (2).** „Ochrana jazyka“ a „Obchodní město“ jsou
  v kartě kraje i jako události v Dějinách. Není jasné, co platí, když je Vardun
  v kartě 0 %, ale v roce 1 100 je v Dějinách obchodní město. Doporučení: v kartě kraje
  ukázat časový průběh („od 1 100: 10 %“) a editovat ho na jednom místě.

### H5 Prevence chyb

- **Ověření světa chybí (4).** Engine vrací chyby a varování s cestou k poli. Návrh je
  nikde neukazuje a „Spustit“ i „Přepočítat“ jsou vždy aktivní. Doporučení: v patě Zadání
  počet chyb a varování, u pole značka a věta, u Spustit důvod zákazu. Varování
  (například jiný slovník než výchozí) neblokují.
- **Volné vstupy bez kontroly (2).** Slova autora (IPA), ID vlastního pojmu a rok události
  se přijmou cokoli. Ověřit lze hned (Postelův zákon: přijmi „á“, ulož „a˦“, ale ukaž, co
  engine zná).
- **Nová událost dostane kraje potichu (2).** „+ Událost“ vloží událost s krajem Vardun
  nebo s pevnými kraji (osídlení Vardun → Kwita). V Dějinách nejde kraje vybrat na mapě,
  mapa na klik nereaguje.

### H6 Rozpoznání místo vzpomínání

- **+** Legenda jazyků, popisky na mapě a věty o dopadu u voleb.
- **Barvy jazyků se opakují (1).** Šest odstínů na 14 linií; dva jazyky téže barvy se mohou
  objevit v Řece jazyků současně se zaniklým. Na mapě je to vyřešené popisky, v řece ne.
- **Souvislost zadání a výsledku (2).** Karta události ukazuje „co z toho v běhu vzešlo“
  (dobrý vzor), ale opačný směr chybí. U jazyka ve Výsledku nejsou vidět události, které ho
  formovaly.

### H7 Flexibilita a efektivita

- **Bez zkratek kromě šipek na ose (1).** Prototyp editoru měl V/R/S. Pro desktop navrhnout
  klávesy kroků (1–9), mezerník pro přehrávání a příkazovou paletu na hledání slova, kraje
  a jazyka.
- **Hledání jen ve Slovech (1).** Kraj ani jazyk najít nejde.

### H8 Estetika a minimalismus

- **+** Klidná typografie, papír, jeden akcent, data v barvě jazyků.
- **Osa je přeplněná (2).** Kolem 300 značek: kroužky pozadí dějin tvoří souvislý pás a
  přebíjejí autorovy události. Doporučení: pozadí jako hustotu (histogram), jednotlivě až
  při přiblížení nebo na najetí.
- **Legenda zakrývá mapu (2).** Na 1 440 px zakrývá ostrov Kwita, na 400 px půl mapy.
  Doporučení: legendu sbalit a otevřít na klik, nebo ji dát do karty.
- **Karta Atlasu je dlouhá (1).** Seznam událostí století se opakuje s Kronikou.

### H9 Pomoc s chybami

- **Chybová hlášení nejsou navržená (3).** Nevíme, jak vypadá chyba běhu (`failed`),
  výpadek enginu ani neplatný soubor. Doporučení: převzít vzor z enginu (cesta k poli
  + česká věta) a navrhnout stav „Engine neběží · Spustit znovu“.

### H10 Nápověda

- **+** Věty kurzívou u voleb jsou nápověda v místě, kde je potřeba.
- **Odborné pojmy bez vysvětlení (1).** Izoglosa, analogie, spirantizace, endonym,
  diglosie. Doporučení: tečkované podtržení s krátkou definicí na najetí; učebnice
  Jazykověda pro CEE už texty má.

## Zákony UX

| Zákon | Stav v návrhu |
|---|---|
| **Jakobův zákon** | Časová osa s přehráváním, mapa s legendou a vrstvami a karta vpravo odpovídají zvyklostem map a editorů. Porušení jsou falešné možnosti (nástroje R a S, klikatelný seznam bez akce). |
| **Fittsův zákon** | Hlavní akce (Spustit, Pokračovat) jsou vpravo dole a dost velké. Malé jsou značky na ose (5 px), události v Dějinách (10 × 14 px) a malé přepínače (22 px). Pravítko Dějin je úzké, 18 px. |
| **Hickův zákon** | „+ Událost“ nabízí 15 druhů ve třech skupinách, to je v pořádku. Lišta má devět položek ve dvou pojmenovaných skupinách, to je přijatelné. |
| **Millerův zákon / chunking** | Karta jazyka má sedm bloků pod sebou bez možnosti sbalit. Rozdělit na záložky (Přehled, Mluvnice, Zvuky, Slova). |
| **Teslerův zákon** | Složitost IPA, rysů a parametrů nese engine a návrh ji správně schovává (věty o dopadu, slovní úrovně místo čísel). Výjimkou jsou rysy ve zvukových změnách. |
| **Dohertyho práh (400 ms)** | Přepnutí roku a vrstvy kreslí okamžitě. Běh trvá minuty a potřebuje průběžné snímky a odhad času (H1). Stránka má 5,3 MB dat; aplikace má načítat po částech. |
| **Von Restorffův efekt** | Červená má být jen pro změnu a ruku autora, ale nese osm významů: aktivní položka, výběr, zastaralé, izoglosa, výpůjčka, jazyková událost na ose, kurzor roku a rozdíl větví. Zvýraznění se ředí. Doporučení: výběr a aktivní položka v inkoustu, červená jen pro změnu (izoglosa, rozdíl, zastaralé). |
| **Zákon společné oblasti a blízkosti** | Lišta odděluje Zadání a Výsledek čarou a popiskem, to funguje. Vrstvy v Atlasu plavou nad mapou a na užší šířce se lámou přes data. |
| **Zákon cílového gradientu a Zeigarnikové efekt** | Zadání nemá postup (co je hotové a co chybí do prvního běhu). U nového světa ukazovat „3 ze 4 hotovo · chybí protojazyk“. |
| **Peak-end** | Konec běhu přepne do Atlasu s hláškou, to je dobrý vrchol. Lepší by bylo shrnutí „vznikly 4 jazyky, 1 zanikl“ s odkazy. |
| **Postelův zákon** | Vstupy IPA by měly přijmout běžné náhražky (g/ɡ, tóny diakritikou) a ukázat, co engine zná. |
| **Occamova břitva** | Rok třikrát, souhrn století dvakrát (Atlas a Kronika). |

## Přístupnost (WCAG 2.2 AA)

| Kritérium | Nález | Závažnost |
|---|---|---|
| 1.1.1 Netextový obsah | Plátna map nemají `aria-label` ani textovou alternativu. Data, která ukazují, jsou dostupná jen zčásti (karta). | 3 |
| 1.4.1 Použití barvy | Výpůjčka ve Slovech je červený tvar (kurzíva jen u cizího jazyka). Jazyky jsou barvou, ale s popisky a legendou, to je v pořádku. | 2 |
| 1.4.3 Kontrast | `--ink` 13,3 : 1 a `--ink-2` 5,3 : 1 jsou v pořádku. `--ink-3` má 2,5 : 1 (světlý) a 3,6 : 1 (tmavý) a nese text: vypnuté hlásky v tabulce IPA a tóny. | 2 |
| 1.4.11 Netextový kontrast | Okrová (2,9 : 1) a olivová (3,0 : 1) jako jediná značka jazyka v seznamu jsou na hraně. Na mapě je výplň doplněná popiskem. | 1 |
| 2.1.1 Klávesnice | Výběr kraje, vrtu a slova jde jen myší: plátno a řádky `li` nejsou zaměřitelné, pravítko Dějin nemá klávesy. Osa Výsledku klávesy má. | 3 |
| 2.4.3 Pořadí fokusu / 2.4.1 | Chybí odkaz „Přeskočit na obsah“, po přepnutí obrazovky se fokus nepřesune. | 1 |
| 2.5.8 Velikost cíle | Viz Fitts: 5 px, 10 × 14 px, 22 px. | 2 |
| 3.1.1 Jazyk stránky | Dokument nemá `lang="cs"`; čtečka čte česky psaný text anglicky. IPA potřebuje `lang="und-fonipa"`. | 2 |
| 4.1.2 Název, role, hodnota | Záložky mají `role="tab"`, ale ne `aria-controls` ani ovládání šipkami. Přepínače `seg` mají správně `aria-pressed`. | 1 |
| Šířka 400 px | Lišta i vrstvy přetékají vodorovně. Pro desktopovou aplikaci méně důležité, ale artefakt to porušuje. | 1 |

## Co funguje dobře

- Model **Zadání → Výsledek** s jedním časem je jasný a pojmenovaný v liště.
- **Věty o dopadu** u každé volby učí model enginu tam, kde se rozhoduje.
- **„Co z toho v běhu vzešlo“** u události spojuje příčinu a následek.
- **Vrstvy Atlasu** ukazují skutečné proměnné enginu (veřejná řeč, gramotnost, věrnost),
  a ne jen jazyk.
- **Větve** párují jazyky podle společných vsí, takže rozdíl je poctivý.
- Typografie IPA (Charis) a klidná paleta drží hustá data čitelná.

## Doporučené pořadí

1. Ověření zadání v patě a u polí, Zpět/Znovu a undo místo potvrzování (1, 2).
2. Projekt a ukládání se stavem v liště, chybové stavy enginu (3, H9).
3. Jména: původ jazyka ve Výsledku a náhled jména v Zadání (4).
4. Jeden rok i v Dějinách, jednotný význam kliku na kraj, Větve s křivkou rozdílu (7, H4).
5. Úklid falešných možností a červené, legenda na vyžádání, osa s hustotou pozadí (6, 8, H8).
6. Přístupnost: klávesnice pro mapy (šipky mezi kraji, Enter vybere), `aria-label`
   s textovým souhrnem, `lang`, kontrast `--ink-3` (světle `#5f6b72`, 4,8 : 1), cíle 24 px (5, 9, 10).

Body 1, 2 a 6 patří přímo do implementace v `desktop/`. Ostatní jsou úpravy návrhu.
