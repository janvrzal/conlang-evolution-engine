# 33. Elita bez patrona, veřejný kód a zakladatelský efekt (M13)

Stav: **zapsáno na větvi `osady`** (8. 11. 2026).

Podnět uživatele: „Ano, pusť se do toho“: problémy enginu z rozboru Talvery (`docs/scenare/talvera.md`,
oddíl „Pro engine“): varieta po přechodu jazyka se počítá jako samostatný jazyk, silný zakladatelský
efekt malých osad, osadníci ani elita nepřejdou na jazyk okolí.

## Varieta po přechodu jazyka

**Nález.** Pod tvrdou politikou Istrenu přešlé skupiny mají talmurský slovník (lexikálně 0,006
od Istrenu), ale hláskově 0,43 daleko, a pozorování je počítá jako samostatné jazyky. Pozorování
je přitom konzistentní: stejný slovník a tvary vzdálené o 0,4 jsou i mezi španělštinou
a portugalštinou. Chyba je v dynamice. Veřejná talmurština (L2) těchto vesnic byla od Istrenu
hláskově 0,52, nezávisle na interferenci: s `interference_weight` 0,25 i 0,1 zůstalo 0,50.

**Příčina.** Veřejná skupina (dospělí, kteří se úřední jazyk učí) má desítky až stovky lidí
a unášení i populační tlaky (Trudgill, exponent −0,75) ji braly jako samostatně předávanou řeč
malé komunity: rychle dokončila nebo zahodila rozjeté změny.

**Zkoušeno a vráceno:** veřejná skupina s rodilým vzorem (`prestige_mirror`) nesla pro unášení
a populační tlaky řeč vzoru. V Talveře to pomohlo (jazyků 55–63 místo 65–70, přešlí 0,29 místo
0,43), ale rozbilo románské cíle: `m7::latina_konzervativni` 0,0 (žádná větev nedrží pád v roce
1200) a `m8::romanske_pady` 0,33–0,42. Rozrůznění románských větví v modelu zčásti stojí na rychlém
vývoji malých veřejných latinských skupin v provinciích; oprava chce nové vyladění Romanie
(samostatná práce).

## Zakladatelský efekt

Ponechán. Osada o ~150 lidech se v první generaci odchýlí o 0,08 (ve vlastním jazykovém
regionu), osada o ~500 lidech o 0,045. Malá komunita bez rodilého vzoru se rychle mění; vazba na
mateřskou obec (síla 0,5) ani společné ocenění změn s mateřským regionem to měřitelně nezměnily
(zkoušeno a vráceno). Osady navíc dorůstají (`settlement_growth`).

## Elita a malá menšina

**Nález.** Talmurská posádka v `m03-06` (60 lidí, prestiž 1,4 z události) zůstala talmurská
1 200 let. Prestiž z události nikdy neklesla a přechod do jazyka okolí model znal jen jako tah
politiky nebo zdomácňující lingua franky; pravidlo ostrůvku platilo jen pro skupinu, která už
nový jazyk přijala.

**Zapsáno:**

- `polity::release`: elita jazyka odcházejícího státu (`Group::elite`) v uvolněných regionech
  přijde o výsadní prestiž (klesne na nejvyšší prestiž domácích skupin jiného jazyka v regionu):
  Normané po ztrátě Normandie, Frankové v Galii.
- `pocket_pull` (komunity): veřejný kód jiného jazyka táhne elitu domů s plnou silou, když má
  její jazyk mezi lidmi, se kterými mluví, podíl pod `child_threshold` (0,2) a elita není
  prestižnější než veřejný jazyk (zrcadlo pravidla ostrůvku). Jen elita: pro všechny menšiny
  pravidlo smetlo i ostrůvky starousedlíků (`m8::ostruvky` 0,0). Vysoká varieta téhož jazyka
  (diglosie `>H`) se nepočítá. `nativize` dostal tah jako parametr.

Osadníci z let 450 a 525 si jazyk drží dál: tvoří třetinu regionu, nejsou ostrůvkem
(enklávy jako sedmihradští Sasové přežily staletí).

## Talvera

Semínka 1–3, scénář se study cases (`dfac84f`):

| | M12 | M13 |
|---|---|---|
| talmurská elita v `m03-06` (60 lidí) | talmursky do 1950 | přejde na serenštinu |
| talmurská slova v serenštině `m03-06` / `m03-07` | 0,15–0,25 / 0,02–0,05 | 0,13–0,15 / 0,01–0,06 |
| jazyků v roce 1950 | 65–70 | 59–69 |
| přešlí pod politikou Istrenu: hláskově od Istrenu | 0,43 | 0,40–0,44 (beze změny) |

Otevřené (dál v `talvera.md`): přešlé skupiny se počítají jako samostatné jazyky, dokud veřejná
skupina mění řeč jako malá komunita; oprava vyžaduje přeladění Romanie.

## Ověření

**Testy 15 z 16 sad, brány 47 z 47, kalibrace 37 z 38** (jako M12): neprošla jen
`m7::typologie_37A` 0,115 (mez 0,112). Selhávající test `spec_check::scenare_evropa_a_romania_nemaji_chyby`
pochází z `25a177f`. Ostrůvky `m8::ostruvky`, románské pády a latina beze změny proti M12.
