# Změny návrhu: Talvera a engine v2 (9. 11. 2026)

Plátno: Design canvas `Gxj1bv7Wb29iWytp5jSLUt` („CEE Talvera · obrazovky“), 14 obrazovek.
Data: Talvera (`docs/scenare/talvera.world.json`), seed 1, engine v2 v Rustu (e75802b), dva běhy:
hlavní a „bez tvrdé politiky 1875“. Čísla na obrazovkách pochází z těchto běhů, ne z odhadu.

## Co se mění v obrazovkách

| Obrazovka | Dřív (Poloostrov) | Teď (Talvera) |
|---|---|---|
| Lišta | 4 kroky zadání | přibyl **Model** (parametry); „Větve“ se jmenují **Co kdyby** |
| Svět | 20 krajů | 96 krajů, **města** (velikost), jména míst z onomastiky s významem, **upozornění z kalibrace** (kraj bez města, jeden jazyk na kraj) |
| Protojazyky | 2 protojazyky | 4 (serenština, talmurština, veretština, idarština), slabičná stavba, **potomci** protojazyka |
| Pojmy | 200 pojmů | volba 149 / 500 / 1 000 / ~1 600, vlastní pojmy s vazbou na WOLD/Concepticon, **vymyšlené** pojmy |
| Dějiny | 16 událostí, 2 pruhy | 59 událostí; pruhy Státy, Jazyk ve společnosti, Lidé a místa, **Hlásky** (sound_shift); studijní případy v rámečku |
| Model (nový) | – | parametry podle rolí: *world* jako slovní úrovně, *active* pro pokročilé, *fixed* skryté; vlastní hodnoty světa vyznačené |
| Atlas | 9 jazyků | 68 jazyků; **odstín = rodina, světlost = jazyk**; města čtverečky; kraj ukazuje vsi a skupiny, sčítání doma a na veřejnosti |
| Jazyky | řeka 10 jazyků | řeka 77 linií seskupená po rodinách; vlastní jméno v čase, **retence kořenů**, zvuky a analogie |
| Slova | 1 tvar na kraj | 40 tvarů slova „voda“ v 96 krajích, izoglosy, **původ slova** (obnova, zkrácení, metateze, disimilace), vrt kraje |
| Kronika | po událostech | po stoletích se souhrny (zvukové změny, analogie, nová slova…), drobné události sloučené |
| Co kdyby | připojení krajů 1300 | **bez tvrdé politiky Istrenu 1875**: Utjipeng 77 % talmursky vs. 100 % serensky; mapy **přiblížené na rozdíl**, jeden červený obrys kolem 7 vsí |
| Běh | 2000 let | −700–1950, průběžná mapa roku 700 s neosídlenými vsemi, 36 jazyků |
| Ověření | vymyšlená hláška | **doslovné hlášení enginu** (`'selvaa' není stát ani region světa.`, `events.28`) a nabídka oprav od aplikace; varování z kalibrace |
| Zastaralé | Obrození 1800 | smazané Obrození 1925, šrafa na ose od 1925, Vrátit / Ctrl Z |

## Mapa světa (kartografie)

- Pevnina z kostry spojů mezi kraji a alfa-tvaru, ne z bublin kolem vsí; souostroví drží pohromadě.
- Reliéf (stínování) podle terénu krajů: hory, pahorky, rovina, ostrov.
- Hranice jako přírodní čáry sdílené sousedními buňkami; kraj = sjednocení buněk jeho vsí, takže hranice
  krajů, jazyků a států leží na stejných čarách.
- Pobřeží s pásy mělčiny, města jako čtverečky.
- Popisky jazyků, krajů a států bez překryvů (státy zkouší náhradní pozice, kraje se vynechají, když není místo).
- Porovnání větví se přiblíží na oblast rozdílu a jeho sousedy; „Ukázat celou mapu“ vrátí celý svět.

## Co zůstává otevřené (pro implementaci)

- API snímků zatím neposílá slovník; Slova v čase a vrt potřebují slovník ve snímcích.
- Kontrolní body a přepočet od roku větvení nejsou v API; „Co kdyby“ zatím počítá celý běh znovu.
- Formát onomastiky se ještě mění; jména míst bereme z exportu `toponyms`.

## Soubory

- `zdroje/aplikace/template.html`: kartografie, přiblížení porovnání, popisky států bez překryvů.
- `zdroje/aplikace/prep.py`: nové druhy původu slov, `sound_shift`, jména krajů a míst z exportu.
- `zdroje/aplikace/naming.js`: přepis IPA do latinky pro jména jazyků.
