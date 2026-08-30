# ADR-004: Kalibrace podle vlastností výsledných jazyků

**Status:** Accepted
**Date:** 2026-08-30

## Context

CEE má simulovat důsledky explicitních diachronních parametrů, nikoli
rekonstruovat jedinou skutečnou historii. Seznamy doložených změn jsou neúplné,
licenčně různorodé a nevystačí pro všechny možné světy. Naproti tomu otevřené
lexikální, genealogické, geografické a inventářové zdroje umožňují měřit
vlastnosti současných jazyků: délku forem, shluky, omezenou homofonii a
inventář.

Stejný výsledek může vzniknout více cestami. Přímé odvození jediného vektoru
historických vah z finálních podob jazyků je proto neidentifikovatelné a nesmí
se vydávat za rekonstrukci skutečných změn.

## Decision

1. Vstupem bude otevřený, lokální kontrakt `languages.csv` + `forms.csv`.
   Jazyk nese identifikátor, volitelnou rodinu a makroregion; forma jazyk,
   koncept a IPA nebo segmenty. Zdrojová data se nebalí do repozitáře.
2. CEE vypočítá metriky nejdřív pro jednotlivé jazyky a teprve pak je agreguje
   globálně, podle makroregionu a podle rodiny. Interval 95 % vzniká cluster
   bootstrapem: globální a regionální profil resampluje rodiny, rodinný profil
   resampluje jazyky. Pro příliš malý vzorek se interval neuvádí.
3. Výsledek je auditovatelný JSON s počty, seedem, počtem bootstrapů a SHA-256
   obou vstupů. Metriky odvozené pouze z wordlistu jsou takto označeny; nejsou
   vydávány za vlastnost kompletního živého lexikonu.
4. Kalibrace simulátoru pracuje s intervaly výsledků. Vzorkuje scénáře,
   vyhodnocuje jejich outcome metriky a hledá *množinu* parametrů, která se
   vejde do zvoleného profilu. Rodinný styl se volí před během a sdílí se mezi
   větvemi; výstupy váhy samy zpětně nepřepisují.

## Consequences

- Earth-like profil je volitelný prior, ne podmínka platnosti simulace.
- CEE rozlišuje globální, geografickou a genealogickou variabilitu místo
  jedné průměrné „pozemské“ váhy.
- Výsledky závisejí na pokrytí a transkripčním standardu daného zdroje; report
  proto vždy ukazuje velikost vzorku a nejistotu.
- Skutečná informační rychlost, funkční zátěž a frekvenčně vážená homofonie
  vyžadují budoucí korpusovou vrstvu a nejsou součástí tohoto prvního kontraktu.
