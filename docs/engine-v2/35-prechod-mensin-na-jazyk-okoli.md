# 35. Přechod menšin na jazyk okolí, soudržné komunity si jazyk drží (M15)

Stav: **zapsáno na větvi `jazyky`** (9. 11. 2026).

Podnět uživatele: „přijde mi to excesivní, strašně moc mini-pidi jazyků“, pak „Kombinace obojího.
U pohlcování menšin musíme zajistit, aby close-knitted komunity si svůj jazyk zachovali. Zbytek se
přizpůsobí okolí.“ (Druhá část, zobrazení malých jazyků jako variet, je zadání pro UI.)

## Nález

Talvera (M14, semínka 1 a 2): 54 jazyků, z nich 25–33 v jediném regionu, 21–29 pod 1 000
mluvčích, 12–15 pod 500. Malé jazyky jsou skutečně oddělené skupiny, ne chyba pozorování:

- osady mezi cizojazyčnými sousedy (asi 8: veretská u Istrenu 71 lidí, serenské a talmurská
  v Selvě, veretská na idarském ostrově …);
- zbytky po přechodu jazyka (serenské vesnice ve výpusti pod Istrenem 82 a 128 lidí);
- odtržené ostrovy a horská údolí se dvěma vesnicemi.

Bez vlivu zůstaly: vyšší práh jazyka (0,35: 39 jazyků, malé zůstanou), spodní mez unášení
(150 i 300 lidí), pohlcení skupin pod 300 lidí přes veřejný kód (osady ho nemají), kandidáti
sloučení z téhož prajazyka pro osamělé skupiny. Přechod jazyka bez politiky model neznal:
jen tah státu, zdomácňující lingua franca a pravidlo ostrůvku.

## Zapsáno

`contact_shift` (komunity) a parametr `contact_shift_threshold` 0,3 (role `active`): domácí
skupina, jejíž jazyk má mezi lidmi, se kterými mluví (vazby × populace, sama skupina plnou
vahou), podíl pod prahem, začne přecházet na převažující jazyk okolí (`language_shift` s podílem
5 %; dál `shift` podle Abramse a Strogatze, brzdí loajalita). Nepřejdou:

- **soudržné komunity** (Milroy 1987): husté vazby uvnitř vlastního jazyka (dvě vesnice regionu
  spolu, ostrov, horské údolí) dají vlastním lidem mezi kontakty víc než práh;
- skupiny se **silnou identitou** (loajalita ≥ 0,5);
- **mluvčí úředního jazyka státu**, do kterého patří jejich region (dobyvatelé se státem);
- **elita** (přechází vlastním modelem M13);
- **nové osady 200 let po založení** (`SETTLER_GRACE_YEARS`; přechod trvá asi tři generace,
  Fishman 1966). Bez ochranné doby přešli Anglosasové v Británii na jazyk Britů dřív, než roku
  600 vznikl jejich stát, a scénář Evropy spadl;
- skupina, jejíž odnož `X>jazyk` už někdy vznikla (jméno je obsazené; jinak běh spadl).

Původní podmínka „prestižnější menšina než okolí nepřejde“ v Talveře zablokovala všechny osady
(osadníci mají prestiž 0,65–0,98) a M15 tam nedělalo nic; nahradilo ji pravidlo úředního jazyka.
Dřívější čísla 46/47 jazyků pocházela z verze bez ochranné doby.

## Talvera (semínka 1 a 2)

| | M14 | M15 |
|---|---|---|
| jazyků | 54 / 54 | 54 / 51 |
| v jediném regionu | 25 / 33 | 25 / 30 |
| pod 1 000 mluvčích | 21 / 29 | 21 / 26 |
| pod 500 mluvčích | 12 / 15 | 14 / 12 |

Účinek je malý. Osady po ochranné době vyrostou (`settlement_growth`) a podíl vlastních lidí
mezi kontakty se dostane k prahu (0,24–0,27), takže jich přejde jen několik. Zbývající malé
jazyky jsou hlavně ostrovy a horská údolí (soudržné komunity, které si jazyk mají držet),
serenské zbytky pod politikou Istrenu s obrozením (study case) a osady z roku 1850. Zbytek
„mini-pidi jazyků“ řeší UI: malé jazyky ukazuje jako variety.

## Práh

| práh | Talvera | Evropa: románské pády | ostrůvky | počet jazyků |
|---|---|---|---|---|
| 0,3 | 54 / 51 | 0,417 (5 z 12, potřeba 6) | 0,083 | 54,5 |
| 0,25 | jako M14 | 0,500 | 0,083 | 55,5 |

Zůstává **0,3**. Románské pády 5 z 12 místo 6 z 12 (interval 0,19–0,68) jsou o jeden běh pod
hranou; uživatel je přijal jako šum („Ano, přijmout“). Hranice brány se nemění.

## Ověření

- brány 47 z 47;
- kalibrace 36 z 38: `m7::typologie_37A` 0,129 (od M14) a `m8::romanske_pady` 0,417 (viz výše);
- `cargo test --release` (cee_engine): vše kromě `spec_check::scenare_evropa_a_romania_nemaji_chyby`
  (padá už před M15, varování z commitu `25a177f`).
