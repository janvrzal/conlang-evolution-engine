# Návrh UI: Poloostrov

Datum: 1. 11. 2026. Funkční prototypy všech pěti kroků práce s CEE nad skutečnými
běhy enginu v2. Předchozí návrh (design systém „CEE Atlas“, deset obrazovek,
koncepty Delta, Synoptika a Letopis) je tímto nahrazen.

## Postup

Návrh vznikl obráceně než ten předchozí: nejdřív jedna srdeční scéna nad
skutečnými daty, z ní vizuální jazyk, teprve potom ostatní obrazovky. Srdcem
aplikace je otázka autora jazyka *jak se tohle slovo říká tady a proč jinak
než o kus vedle*. Proto na mapách stojí slova, ne barevné plochy.

## Platforma

Kostra aplikace je v [`desktop/`](../../desktop/README.md).

Desktopová aplikace na Tauri 2. UI ve Svelte ve webview, engine zatím jako
pomocný proces s `/api/v2`, po přepisu do Rustu volaný přímo. Webové UI
zůstává kvůli sazbě IPA (kombinační diakritika) a typografii; únikovou cestou
je Electron, mění se jen skořápka.

## Vizuální jazyk

| Prvek | Volba |
|---|---|
| Papír („Břidlice“) | pevnina `#fbfbf9` se zrnem papíru, moře `#bccad0`, světlé vodní linky `#eef3f4` |
| Inkoust | text `#1b2830`, druhotný `#56656e`, linky `#d1d9dc`, panely `#eef1f2` |
| Červený inkoust | `#ae2a1f` (tmavě `#e8806f`): změna, ruka autora, rozdíl mezi větvemi; nic jiného |
| Písmo | Piazzolla (Google Fonts) pro UI i popisky, místa prostrkanými verzálkami; IPA v Charis 7 |
| Jazyky | `#2a6fc9 #c48a12 #16956a #7d4fc0 #8a9a12 #c4508a` (tmavě `#4f8de0 #b47e18 #22a074 #9a72dc #869217 #d05f98`), ověřené na barvoslepost a kontrast; bez červené |
| Státy | bez barev: šrafa s jiným úhlem, čerchovaná hranice, hlavní město čtverečkem |
| Kartografie | izoglosy červeně, šrafy hor, čerchované hranice, měřítko, kurzívní vysvětlivky |

Každá volba, kterou autor nastavuje, má pod sebou kurzívou větu o tom, co
s jazykem udělá. Jména krajů, jazyků a států skládá protojazyk ze svých slov
(`zdroje/naming.js`): kraj podle krajiny („Bílá řeka“), jazyk jako vlastní
jméno („řeč lidí“) s českou podobou na -ština, stát podle hlavního města.

## Obrazovky

| Krok | Prototyp | Artefakt |
|---|---|---|
| 1 Svět | [editor-sveta.html](prototypy/editor-sveta.html) | https://claude.ai/artifact/Mbxi4PRQgGB7kbEJQ2aiE4 |
| 2 Protojazyk | [protojazyk.html](prototypy/protojazyk.html) | https://claude.ai/artifact/GW8TtNdiAqLawzua1crWUh |
| 3 Dějiny | [dejiny.html](prototypy/dejiny.html) | https://claude.ai/artifact/2u3m3HhNgF9spfPwqn6QrC |
| 4 Výsledky | [vysledky.html](prototypy/vysledky.html) | https://claude.ai/artifact/RTBr7v9LLBxxvjZtDbuzi8 |
| 4 Výsledky: Slovo v krajině | [slovo-v-krajine.html](prototypy/slovo-v-krajine.html) | https://claude.ai/artifact/6fFX1iTNUbjLt8eL43JoaJ |
| 5 Větve | [vetve.html](prototypy/vetve.html) | https://claude.ai/artifact/DogNpKFaZdEdruqiyaNUuw |
| **Návrh aplikace** (od nuly, nad běhy v Rustu) | [aplikace.html](prototypy/aplikace.html) | https://claude.ai/artifact/YVXTN8jtrYjoFWxwRxuvCC |
| **Obrazovky na plátně** (návrh + opravy z UX auditu) | plátno Design | https://claude.ai/artifact/Gxj1bv7Wb29iWytp5jSLUt |

1. **Svět.** Kraj je bod, území se dopočítá (Voronoi oříznutý pevninou).
   Nástroje V výběr, R kraj, S spoj. Osídlení slovem (řídké až velmi husté),
   vesnice z rozlohy území. Svébytnost, ochrana jazyka a obchodní město jako
   časové pásky. Podklad z obrázku jde ztlumit, odbarvit nebo skrýt.
   Výstup je živý `cee-v2-world/1`.
2. **Protojazyk.** Tabulka IPA a lichoběžník samohlásek, četnost ve třech
   úrovních přímo v tabulce (engine dostane pořadí), přízvuk, mluvnice,
   slovník 149 pojmů. Výchozí slova jsou z enginu.
3. **Dějiny.** Mapa států v roce pod kurzorem, kronika s pruhem každého
   státu (výplň podle jazykové politiky) a přetahovatelnými událostmi, karta
   pro všech 11 druhů událostí enginu, kraje se vybírají na mapě.
4. **Výsledky.** Mapa vsí obarvená jazykem (nářečí světlostí, lingua franca
   čárkovaným obrysem), řeka jazyků v čase, karta jazyka s vyvíjejícím se
   vlastním jménem, srovnávací slovník s výpůjčkami a vrtem slova. Slovo
   v krajině: tvary jednoho slova přímo na mapě, izoglosy, vrt místa.
5. **Větve.** Dvě dějiny vedle sebe ve stejném roce, vsi s jiným jazykem
   červeně, mluvčí podle jazyka, slova jedné vsi v obou větvích.

## Obrazovky na plátně (6. 11. 2026)

Plátno [CEE Poloostrov · obrazovky](https://claude.ai/artifact/Gxj1bv7Wb29iWytp5jSLUt)
má 13 artboardů (1440 × 900): Projekty; Zadání (Svět, Protojazyky, Pojmy, Dějiny);
Výsledek (Atlas, Jazyky, Slova, Kronika, Větve); stavy (běh počítá, zadání
s chybami, zastaralé výsledky s Vrátit). Zapracovává [UX audit](UX_AUDIT.md):
ověření zadání, Zpět/Znovu, projekty a uložení, původ jazyků, klávesnice
na mapách, jeden rok, červená jen pro změnu, cíle 24 px, `--ink-3` `#5f6b72`.
Mapy a řeka jazyků jsou obrázky vykreslené z obou běhů (výběr inkoustem),
čísla v kartách jsou z týchž dat a hlášení ověření z enginu (`check_spec`).
Plátno je zdrojem pravdy pro implementaci v `desktop/`; HTML návrh níže zůstává
jako funkční ukázka dat.

## Návrh aplikace (6. 11. 2026)

Návrh od nuly nad skutečnými běhy enginu v2 v Rustu nahrazuje skládání pěti
prototypů. Artefakt: https://claude.ai/artifact/YVXTN8jtrYjoFWxwRxuvCC,
kopie [prototypy/aplikace.html](prototypy/aplikace.html) (bez písma).
Vizuální jazyk zůstává (Piazzolla, Charis, papír Břidlice, červený inkoust);
struktura je nová a vychází z toho, co engine umí.

**Lišta má dvě poloviny.** *Zadání* (Svět, Protojazyky, Pojmy, Dějiny) je celý
`cee-v2-world/1`; *Výsledek* (Atlas, Jazyky, Slova, Kronika, Větve) je export
`cee-v2/1` a snímky běhu. Změna zadání označí výsledky jako zastaralé.

| Obrazovka | Co ukazuje z enginu |
|---|---|
| Svět | kraje (krajina, osídlení, svébytnost, ochrana, obchodní město, jazyk), svět (seed, roky, generace, rozestup vsí, pozadí dějin, posun významu) |
| Protojazyky | hlásky, tóny, přízvuk a síla, profil mluvnice a osm funkcí katalogu se zdrojovými slovy, rozběhnuté změny (`processes`), slova autora a vlastní jméno; slova z generátoru (tick 0) |
| Pojmy | velikost slovníku 149–1 453 (WOLD), domény, vlastní pojmy s vazbou a vztahy |
| Dějiny | mapa států v roce pod kurzorem, kronika zadání po skupinách (Státy, Jazyk ve společnosti, Lidé a místa) a pozadí z běhu; karta všech 15 druhů událostí včetně `settlement` a `elite` a „co z toho v běhu vzešlo“ |
| Atlas | vsi podle jazyka doma a nářečí, vrstvy Státy, Řeč na veřejnosti, Písmo a škola, Věrnost; kraj se sčítáním doma a na veřejnosti a skupinami |
| Jazyky | řeka linií (vznik, rozštěpení, zánik), vlastní jméno v čase, nářečí se jmény, mluvnice proti protojazyku, zvukové změny jako pravidla, analogie, přízvuk |
| Slova | srovnávací slovník s etymologií, slovo na mapě s izoglosami, vrt místa po stoletích |
| Kronika | dějiny autora, pozadí dějin, společnost a jazyky po stoletích se souhrnem drobných změn |
| Větve | dva běhy vedle sebe; jazyky spárované podle společných vsí, rozdíly červeně |

**Co engine zatím nedává:** slovník ve snímku (návrh ho má z exportu po
každém pozorování), přepočet od roku přes API (kontrolní body engine umí),
jména osob a pravopis.

Sestavení (běhy trvají asi 3 minuty každý a do repozitáře se nedávají; vazba
`cee_engine_py` musí být sestavená podle `rust/README.md`):

```bash
cd docs/ui-navrh/zdroje/aplikace
python run_world.py ../../../.. BĚH_A          # Poloostrov s pozadím, osídlením a cizí elitou
python run_world.py ../../../.. BĚH_B b        # větev B: bez připojení v roce 1300
python prep.py BĚH_A BĚH_B data.json
python build.py data.json VÝSTUP
```

## Data prototypů

- `zdroje/record.py`: poloostrov 20 krajů × 4 vsi, jeden protojazyk, 2000 let
  (Slovo v krajině, Protojazyk, jména v Editoru a Dějinách).
- `zdroje/record2.py`: stejný svět s dějinami z prototypu Dějin a druhým
  protojazykem na východě (Výsledky, větev A).
- `zdroje/record3.py`: větev B, v roce 1300 západ dobude i východ.

## Co návrh odhalil v enginu

Doplněno v revizi API 9: události `identity` a `immigration` (vlastnosti
kraje „odtud potud“), jméno státu `name` u `state` a `secession` a vlastní
slova protojazyka `languages[].words`. Systém jmen jazyků a nářečí: engine
dodává vývoj vlastního jména, kraj vzniku a polohu nářečí (`cee.v2.naming`,
`languages[].endonym`), čeština se skládá v `zdroje/naming.js`
(`languageLabel`, `dialectLabels`; Výsledky ukazují nářečí jménem). Zbývá:
- Během přechodu k jinému jazyku pozorovatel hlásí krátké jazyky o jedné až
  třech vsích; obrazovka Větve je počítá k rodiči.
- Ves při přechodu jazyka má dvě domácí skupiny (`ves`, `ves>jazyk:home`);
  UI bere početnější.

## Jak prototypy sestavit znovu

Spouští se v `docs/ui-navrh/zdroje`; běhy trvají několik minut a jejich JSON
se do repozitáře nedává. Písmo Charis se vloží jen s `CEE_CHARIS`
(adresář `web` z balíku Charis 7), jinak IPA vysází písmo systému.

```bash
cd docs/ui-navrh/zdroje
export PYTHONPATH=../../../src:../../..
python record.py run.json && python record2.py run2.json && python record3.py run3.json
python prep.py && python build_proto.py && python build_editor.py && python build_dejiny.py
python prep_results.py && python prep_branches.py
```

Pořadí platí: `build_editor.py` a `build_dejiny.py` berou protoslovník ze
stránky `protojazyk.html`. Sestavené stránky jsou fragmenty pro artefakty;
kopie v `prototypy/` mají doplněnou hlavičku dokumentu.
