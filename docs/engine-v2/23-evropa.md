# 23. Evropa (M8, návrh)

Stav: **návrh k potvrzení uživatelem** (6. 11. 2026). Navazuje na Romanii (dokument 22, M7.3).

Cíl stejný jako u Romanie: ne kopie dějin, ale svět, který s podmínkami podobnými evropským
(*nudge*) vyprodukuje **rodiny podobné** románské, germánské, keltské a slovanské, včetně jejich
vzájemného kontaktu. Hodnotí se profil rodinné podobnosti (pořadí a směr změn, rozdíly mezi
větvemi a rodinami, k z N běhů), ne letopočty.

## Co model už umí a co chybí

Engine má události po skupinách: `migration` (lidé jazyka X se usadí v regionu), `conquest`
(cizí elita nad poddanými), `religious_change` (liturgický jazyk), `war`, `contact`, `epidemic`,
`state_collapse` (`events.rs`). **Popis světa (`WorldSpec`) je ale nezná** (dokument 16: „událostí po
skupinách zatím ve WorldSpec nejsou“) a `spec.py` přijímá jen události států a regionů. Potřeba:

1. **Události v popisu světa po regionech**: `migration` (jazyk, zdrojový region, cílový region,
   podíl), `conquest` (jazyk elity, region sídla, poddané regiony, síla), `religious_change`
   (liturgický jazyk, regiony). Engine si skupiny dohledá podle regionu a jazyka.
2. **Protojazyky bez slovníku z dat**: kromě latiny (dokument 22) se slovník generuje, jako
   u substrátů v Romanii. Pro rodinnou podobnost rozhoduje gramatika, inventář a podmínky, ne
   konkrétní slova; slovník z dat (IE-CoR) lze doplnit později.

## Scénář (návrh)

Start kolem roku 500 př. n. l., konec 1900; 25 let na generaci.

| region | jazyk na startu | podmínky |
|---|---|---|
| Itálie | latina (dokument 22) | jádro Říma |
| Galie, Hispánie | galština, iberština | romanizace (jako Romania), od 400 franská a vizigótská elita (dobytí, germánská) |
| Dácie | dáčtina | krátká romanizace, od 600 slovanská migrace |
| Británie | britonština | římská správa bez romanizace venkova, od 450 anglosaská migrace na východ, od 1066 normanská (románská) elita |
| Bretaň (Armorika) | britonština | přistěhovalci z Británie (keltský okraj) |
| Germánie, Skandinávie | pragermánština | bez Říma; od 800 seveřané do Británie (kontakt) |
| Slovanská pravlast | praslovanština | od 500 migrace na Balkán a do Dácie |
| Balkán | ilyrština nebo řečtina | Řím, pak slovanská migrace; kontakt s latinou a řečtinou (balkánský svaz) |

Gramatika protojazyků: pragermánština a praslovanština s bohatými pády (předmět, plurál, minulý čas
synteticky), bez členu; keltština s mutacemi zjednodušeně jako syntetický předmět. Liturgická latina
v západní církvi, církevní slovanština na Balkáně a východě (`religious_change`).

## Profil podobnosti (návrh cílů, `k` z `N`)

| cíl | tvrzení | opora |
|---|---|---|
| Romania | profil z dokumentu 22 (10 cílů) platí i v evropském světě | dokument 22 |
| keltský ústup | galština a iberština zaniknou (přechod na latinu); keltština přežije aspoň v jednom okrajovém regionu | historie (velština, bretonština) |
| angličtina | germánská větev v Británii ztratí víc pádů než germánština na kontinentu | angličtina proti němčině a islandštině |
| franská stopa | franská elita v Galii přejde na latinu a zanechá v ní jen málo slov | stovky franských slov ve francouzštině |
| slovanské pády | většina slovanských větví si pád předmětu udrží | slovanské jazyky mimo bulharštinu a makedonštinu |
| balkánský svaz | slovanská větev na Balkáně ztratí pád nebo získá člen častěji než ostatní slovanské | bulharština, makedonština (Joseph 1983, *The Synchrony and Diachrony of the Balkan Infinitive*) |
| rodiny | jazyková vzdálenost uvnitř rodiny je menší než mezi rodinami | samozřejmost, kontrola modelu |
| počet jazyků | v roce 1900 desítky jazyků, ne jeden a ne stovky | evropská mapa |

## Postup

1. Události po regionech v `WorldSpec` (Rust, `spec.py`, kontrola popisu světa).
2. Scénář `src/cee/data/scenarios/evropa.json` a měřidlo `cee calibrate --only evropa`
   (po rodinách a regionech).
3. Cíle jako profil podobnosti; nudge jen podmínkami scénáře.
4. Výkon: odhad 9 regionů × 4 až 6 vesnic × 96 generací, desítky sekund na běh.
