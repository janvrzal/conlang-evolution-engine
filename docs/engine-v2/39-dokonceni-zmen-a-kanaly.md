# 39. Dokončení hláskových změn a kanály, které berou jen z domova

Stav: **zapsáno na větvi `dokonceni`** (11. 11. 2026).

Podněty uživatele: „Nechat neúspěšné změny odumírat … Přesně tohle musíme implementovat“ a
o kalibraci: „když zvýšíme váhu nějakému přenosu, tak tím vytlačujeme ostatní typy? To je špatně
… Měli by ty parametry ideálně být na sobě nezávislé.“

## Nález

Měření Talvery −700 až 1950 (dok. 20, oddíl 11. 11.): krok se během běhu zpomalí asi 23× a stav
roste. Kód má kolem 260 slov, ale v roce 1800 kolem 190 živých hláskových procesů a 8 tisíc
položek ve frontách. Procesy se hromadí na obou koncích křivky S: 21 tisíc skoro dokončených
(podíl mezi ½ a 1), které nikdy nedoběhnou, protože zbytek drží kontakt se sousedy, a přes 9 tisíc
neujatých (podíl pod 1 %), které nikdy nezaniknou.

## Dokončení (jen konec křivky S, jen hláskové změny)

Pokus z větve `engine-dokonceni` (690b413, 72ccc9f) zapomínal variantu, jakmile ztratila
většinu, a inovaci, která jednou klesla pod `activation_share`. Tím mizela variabilita, ze které
změny rostou:

| | bez dokončení | pokus | cíl |
|---|---|---|---|
| `m7::retence` | 0,865 | 0,925 | [0,80; 0,90] |
| `m7::latina_zapor` | 0,75 | 0,25 | ≥ 0,6 běhů |
| `m8::romanske_pady` | 0,42 | 0 | ≥ 0,5 běhů |
| relikty (`m2::zvukove_zmeny_se_siri`) | 0,04 | 0,47 | [0,01; 0,15] |
| školní brány M6a | prošly | neprošly | |

Zapsané pravidlo (Blythe a Croft 2012: změna potřebuje výhodu, aby doběhla, a stará varianta
dožije se starší generací):

- **Zapomenutí jen v ocasu.** Skupina zapomene variantu, která právě klesla pod `forget_share`
  (= `activation_share`, 5 %), když jiná varianta drží aspoň `1 − forget_share`. Zapomenutou
  se děti neučí a dospělí ji jen opouštějí, dokud ji skupina neslyší aspoň s `completion_share`
  (½). Paměť je `TransferState::forgotten` (proměnná → skupina, varianta), v kontrolních bodech.
- **Jen hláskové změny** (`State::completing` v `settle`, řádky `VariableKind::Process`). Slova,
  tvary a konstrukce si nechávají dosavadní dynamiku: synonyma, doublety a rejstříky mohou žít
  vedle sebe dlouho. S dokončením i u slovníku byla retence 0,93 a románské pády 0.
- **Škola učí spisovnou variantu** i tam, kde ji skupina doma zapomněla: kodifikovaná varianta
  standardu skupiny se školní docházkou se jako zapomenutá nemaskuje (`transfer::block::taught`).
- **Uzavření procesu.** Proces se v kódu uzavře, když je změna dokončená (podíl aspoň
  `1 − activation_share`) nebo odumřelá (pod `activation_share`) po `closure_generations`;
  odumřelý se znovu otevře, když se změna vrátí nad práh. Slova, která dokončená změna ve frontě
  nezastihla, zůstanou relikty (Wangova lexikální rezidua); dopsat je všechna dávalo relikty 0.
- **Relikty v bráně `m2::zvukove_zmeny_se_siri`** se počítají jen z dokončených změn: odumřelá
  změna slova ve frontě nikdy nezasáhla, nejsou to výjimky ze změny. Pásmo brány se nemění.

## Kanály berou podíl jen z domácího vstupu

Dosud `hear` sečetl domácí vazby (vlastní skupina, sousedé téhož jazyka) a vazby mezi jazyky
(soused, elita, obchod) a vydělil je součtem vah: silnější vazba jednoho kanálu ubírala ostatním.
Vedlejší kanály (interference, čtení, škola, liturgie) se míchaly postupně
`(1 − s) · dosavadní + s · zdroj`, takže každý další zmenšil všechny před sebou a výsledek závisel
na pořadí.

Nově (`cee_core::transmission::hear_range`):

```
domov   = vazby téhož jazyka / jejich váha
podíl_k = w_k / (váha domova + w_k)          vazby mezi jazyky kanálu k (jako by byl jediný)
podíl_s = min(faktor × váha, 1)               vedlejší kanál s
slyšené = (1 − Σ podílů) · domov + Σ podíl · zdroj    (Σ > 1: všechny podíly úměrně zmenšené)
```

Zvýšení jednoho kanálu tedy bere jen domovu, ostatní kanály se nemění a na pořadí nezáleží.
Vstup mluvčího je konečný, takže úměrné zmenšení zůstává jen jako strop. Svět bez kontaktu a bez
škol počítá bajtově stejně jako dřív. Kalibrace se nezměnila: posunuly se jen `latina_retence`
0,732 → 0,726, `latina_rozmanitost` 0,594 → 0,566, `m9::tempo` 2,551 → 2,543 a
`m8::pocet_jazyku` 42,5 → 42, vše v pásmu.

## Přesné zrychlení

- Tlak (`Pressures::fitness`) se nepočítá pro buňky, kde skupina slyší nejvýš jednu variantu:
  výběr váží jen slyšené sloty, takže s jedinou na výsledek nemá vliv. Stejný otisk.
- Aktivace, kterou `phonology::activate` hned zahodí (proces živý, nebo uzavřený s dokončenou
  změnou), se při souběžném přenosu nezapisuje. Stejný otisk.
- `LivePools::reaxis` (z `engine-dokonceni`, 501f7b7): nová osa skupin z hustých řádků. Stejný
  otisk, fáze událostí 13,1 s → 4,5 s.

## Výsledek

Talvera −700 až 1950 proti `engine-v2-dynamika` po sloučení `engine-tempo`:

| | dosud | nově |
|---|---|---|
| celý běh (Apple Silicon) | 51,3 s | 35–38 s |
| krok kolem roku 1800 | 1,19 s | 0,72 s |
| paměť během běhu | ~1,1 GB | ~0,87 GB |
| tvary v bance | 716 tis. | 274 tis. |
| hláskové procesy na kód: živé | 190 | 50 |
| položky ve frontách na kód | 8 115 | 598 |
| buňky s víc variantami (1700) | 178 tis. | 66 tis. (dokončení i slovníku) |
| záznamy historie | 1,95 mil. | 1,47 mil. |

Brány 47 ze 47. Kalibrace 38 ze 40 (dosud také 38): nově prochází `m7::typologie_37A` (konec
0,094 → v pásmu), neprochází `m7::typologie_67A` (0,123 při mezi 0,111, šum vzorku 40 jazyků)
a dál `m8::romanske_pady` (0,25, dosud 0,42; intervaly se překrývají).

Časy kolísají o ±15 % podle zátěže stroje; počty stavu jsou přesné.
