# 29. Splynutí řad, spouštěč tónů, obroušení záporky a vyrovnávání nářečí (M10d)

Stav: **zapsáno na větvi `opravy`** (8. 11. 2026).

Podnět uživatele: „Sprav je tedy“ (otevřené body dok. 28: tóny ve Slavii, kontakt a vzdálenost
románských větví, počet jazyků Evropy, zápor latiny). Během práce: „Nemusíme u toho latinského
scénáře ladit detaily, ty jsou bezpředmětné, my naopak chceme zdravou variaci“. Proto jsou všechny
opravy obecné mechanismy enginu (platí pro každý svět i conlang), ne podmínky scénáře.

## Tóny: riziko splynutí řad

Ve Slavii vznikaly tóny takto: samovolná ztráta znělosti celé řady *b d g* → *p t k* (rodina
`fortition`, bez podmínky okolí) doběhla, přestože jazyk *p t k* měl, tedy řady splynuly; ztráta
znělosti je spouštěč tónů (Haudricourt 1954), a tak naskočila tonogeneze.

Splynutí celé řady je vzácné (Martinet 1955: jazyky se kontrastů nevzdávají snadno). **Zapsáno:**
`merger_risk` v `transfer/pressures.rs` je zrcadlo bonusu řetězu (`chain_bonus`, dok. 26). Řadový
posun bez podmínky okolí dostane k sociálnímu ocenění

    −chain_shift_weight × podíl obsazených výstupů × (1 − podíl vyprazdňující změny / ½)⁺,

kde podíl obsazených výstupů počítá jen vstupní hlásky, které skupina má (`rows::outputs`, hlásky
bez protějšku se vynechají), a vyprazdňující změna je ta, jejíž výstupní třídu posun zaplňuje
(*p t k* → *ɸ θ x*). Riziko klesá k nule v polovině vyprazdňující změny, od ní dál táhne bonus
řetězu: tlak přechází nulou souvisle.

**Spouštěč tónů ze ztráty koncovky jen u h/ʔ.** Odpadnutí celé třídy koncových frikativ (s, x, h …)
se dřív počítalo jako ztráta h a ve Vaskonii spouštělo tóny. Teď musí změna mířit jen na h nebo ʔ;
tón z *-s* vzniká až přes *-s* → *-h* (vietnamština, čínské 去聲).

| tóny (podíl slov, Evropa 1900) | semínko 1 | 2 | 3 |
|---|---|---|---|
| Slavia | 0 % | 0 % | 0 % |
| region s nejvíc tóny | Vaskonie 26 % | Hispánie 29 % | Kambrie 22 % |

Tóny tak vzniknou zhruba v jednom okrajovém regionu z třinácti, vždy po splynutí znělých
a neznělých okluziv, tedy po Haudricourtově cestě. Je to uvěřitelné; i Evropa má jazyky
s melodickým přízvukem (srbochorvatština, švédština, litevština).

**Grimmův řetěz (hračka PIE, 12 vesnic, 1 500 let, 6 semínek):** *b d g* → *p t k* proběhne tam,
kde první krok *p t k* → *ɸ θ x* dojde aspoň do ~¾ (semínko 5: 0,75 → 0,57–0,64; semínko 6:
0,73 → 0,24); kde první krok uvízne pod polovinou (semínka 1 a 3), druhý se nespustí. Dřívějších
56–63 % zahrnovalo i samovolné splynutí bez řetězu.

## Kontakt a vzdálenost od latiny

Zrychlení kontaktem (`m9::tempo`) je po M10c a těchto změnách **2,39** (mez 2,8; dřív 2,807).
Vzdálenost románských větví od latiny v Evropě (střední normalizovaná Levenshteinova vzdálenost
zděděných slov domácích latinských skupin od tvaru v roce −500, 2 400 let), 3 semínka:

| | Itálie | Galie | Hispánie |
|---|---|---|---|
| d | 0,55–0,66 | 0,70–0,73 | 0,67–0,77 |
| r za tisíciletí | 0,33–0,45 | 0,51–0,54 | 0,46–0,62 |

Skutečnost (IE-CoR, dok. 24): Romance r 0,30–0,70, italština nejpomalejší, francouzština
nejrychlejší. Pořadí i rozpětí sedí. Dok. 28 uváděl 0,75–0,92; tehdejší měření se nezachovalo
a nové (popsané výše, skript odpovídá převodu cíle `m9::tempo`) je nižší. Nic se proto neměnilo.

## Zápor: obroušení až po ztrátě poloviny

V Romanii měl v roce 1200 obemknutý zápor 40 % větví a některé už byly v III. stadiu. Jespersenův
cyklus běžel asi dvakrát rychleji než ve skutečnosti: záporka platila za „zchátralou“
(`syntax::eroded`), jakmile ztratila jedinou hlásku, takže latinské *non* → *no* hned tlačilo
k *ne … pas*. Italské *non* a španělské *no* ale drží zápor před slovesem přes tisíc let; slabá
je až proklitika typu fr. *ne* → *n'*.

**Zapsáno:** `syntax::worn(now, original)`: slovo je zchátralé, až když z něj zbude nejvýš jedna
hláska, nebo když ztratí aspoň polovinu hlásek. Používá ho tlak zřetelnosti (`Pressures::eroded`)
i zkrácení II. stadia (`NegationReduction`). Brána `m4` (záporka obroušená na samohlásku) dál platí.

`m7::latina_zapor` **0,70** (14 z 20, projde; dřív 0,40). Zápor před slovesem v roce 1200:
Itálie 17, Galie 17, Hispánie 15, Dácie 2 z 20. Dácie je v roce 1200 latinská jen z 10 %
a obemknutý zápor přebírá od dáckých mluvčích (kontakt), což je zdravá variace, ne chyba.

## Počet jazyků: vyrovnávání nářečí

Evropa měla 73,5 jazyka (pásmo 10–60). Většina byla jednoskupinová: v malých regionech
(Vaskonie, Kambrie, 9 vesnic po 250 lidech) sdílely vesnice s městem jen ~30 % tvarů (Germánie
a Slavia 60–80 %), takže každá vesnice byla samostatný jazyk; stejně germánští osadníci
v Británii (7–23 % společných tvarů navzájem). Malé skupiny driftují rychleji a jejich vazby jsou
slabší; vyrovnávání podle města (`leveling_rate` 0,1, autorský odhad) to nedohnalo.

| `leveling_rate` | medián jazyků (12 semínek) | rozpětí |
|---|---|---|
| 0,1 (dosud) | 73,5 | 69–86 |
| 0,2 | 63 | 58–67 |
| **0,35** | **56** | 51–64 |

**Zapsáno:** `leveling_rate` 0,35 (koiné kolem města, Trudgill 1986; Kerswill a Williams 2000).
Vyrovnává se jen uvnitř regionu, takže regiony a větve se dál rozcházejí: semínko 1 s 0,35 má
stejné tvary sousedních vesnic Germánie 0,86, Slavie 0,85, Itálie 0,61, Galie 0,22, vzdálenost od
latiny Itálie 0,54, Hispánie 0,73, Galie 0,77 a tóny jen ve Vaskonii (38 %, Slavia 0 %). Tabulky
tónů a vzdáleností výše jsou změřené ještě s 0,1.

## Ověření

**Testy 16 z 16, brány 47 z 47, kalibrace 38 z 38.** Dříve neprošlé: `m8::pocet_jazyku` 56
(pásmo 10–60), `m9::tempo` zrychlení kontaktem 2,23 (tempo bez kontaktu 0,372),
`m7::latina_zapor` 0,75. Retence vůči latině 0,584, ostrůvky 0,167 (p_min 0,2 podle Wilsona
k z N projde). Fixture `tests/fixtures/parameters.json` má nové `leveling_rate`.

## Pro editor

Opravy jsou mechanismy, takže je worldbuilder dostane automaticky. Z ladění plynou ale i vlastnosti
světů, na které by editor měl upozornit: malý region (do ~10 vesnic po ~250 lidech) se slabými
vazbami a bez města se rozpadá na jazyk za vesnici; osadníci (migrace) bez propojení s městem
regionu tvoří samostatné jazyky; tóny vzniknou jen po splynutí znělých a neznělých souhlásek nebo
po ztrátě koncového h/ʔ; řetězový posun potřebuje, aby první krok doběhl (událost `sound_shift`).
