# Kalibrace nářečního kontinua (`region_world`)

Datum: 31. 10. 2026. Větev `engine-v2-dynamika`. Navazuje na
[`13-region-world.md`](13-region-world.md): sousední vesnice se v modelu
rozcházely rychleji, než ukazují nářeční atlasy, a 80 km se za 3 000 let
rozpadlo na čtyři jazyky.

## Páky

Síly vazeb se v `mixing_matrix` normalizují v každém řádku: silnější vazba
nezvýší, **kolik** se vesnice od sousedů učí, jen **od koho**. Množství
mísení řídí jen otevřenost. Proto dvě páky (obě v `Parameters`, používá je
jen `region_world`):

- `village_openness`: podíl vstupu dětí od sousedních vesnic;
- `border_link_scale`: váha vazby přes hranici regionu proti gravitační síle
  (propustnost hranice).

Tempo změn se neladí: určují ho jiné cíle (slovní zásoba, zvuky, gramatika).

## Cíle

Čísla z atlasů (0,05–0,15 pro sousední vesnice) nejsou s naší mírou
(`observe.code_distances`) přímo srovnatelná; dialektometrie měří jinak.
Proto pásmo + cíle nezávislé na míře:

- **pásmo**: sousedé v regionu v letech 2 000 a 3 000 v 0,05–0,15;
- **rovnováha**: mezi 2 000 a 3 000 lety vzdálenost sousedů nevzroste
  o víc než 10 %;
- **pořadí**: sousedé < přes hranici < vzdálené regiony;
- **jeden jazyk**: 80 km bez bariér zůstane jedním jazykem.

`scripts/v2_calibrate_continuum.py`: čtyři regiony ve čtverci (40 km),
po pěti vesnicích, plný model, 3 000 let; mřížka 6 × 5 (otevřenost
0,05–0,7, hranice 0,25–4) na seedech 1..4, ověření na 101..108.

## Výsledky

Mřížka (vzdálenost sousedů v regionu po 3 000 letech; jazyků):

| otevřenost | hranice 0,25 | 1,0 | 4,0 |
|---:|---|---|---|
| 0,05 | 0,200; 4 | 0,230; 4,25 | 0,266; 8,5 |
| 0,1 (dosavadní) | 0,169; 4 | 0,207; 4 | 0,248; 6,25 |
| 0,2 | 0,110; 4 | 0,140; 3,75 | 0,175; 3,5 |
| 0,35 | 0,064; 1 | 0,086; 1,25 | 0,102; 1 |
| 0,5 | 0,048; 1 | 0,061; 1 | 0,069; 1 |
| 0,7 | 0,043; 1 | 0,050; 1 | 0,054; 1 |

Ověření (seedy 101..108; sousedé v letech 1 000 / 2 000 / 3 000, přes
hranici a vzdálené v roce 3 000):

| otevřenost, hranice | ztráta | sousedé | přes hranici | vzdálené | jazyků |
|---|---:|---|---:|---:|---:|
| 0,1; 1,0 (dosavadní) | 0,727 | 0,069 / 0,161 / 0,204 | 0,340 | 0,412 | 4,0 |
| 0,35; 1,0 | 0,252 | 0,033 / 0,066 / 0,086 | 0,209 | 0,261 | 1,25 |
| **0,5; 1,0** | 0,157 | 0,025 / 0,048 / 0,061 | 0,153 | 0,194 | 1,0 |
| 0,5; 2,0 | 0,107 | 0,027 / 0,054 / 0,065 | 0,118 | 0,162 | 1,0 |
| 0,7; 1,0 | 0,130 | 0,022 / 0,041 / 0,051 | 0,125 | 0,158 | 1,0 |
| 0,7; 4,0 | 0,106 | 0,025 / 0,047 / 0,056 | 0,072 | 0,110 | 1,0 |

- **Určené: otevřenost.** Jeden jazyk na 80 km vyžaduje aspoň 0,35; při 0,7
  jsou sousedé na dolní hraně pásma. Střed pásma dává 0,35–0,5.
- **Neurčená: propustnost hranice.** Ztráta se mezi hodnotami liší jen
  členem rovnováhy; silná hranice (4) ale skoro maže rozdíl mezi sousedy
  a hranicí. Zůstává 1,0.
- **Rovnováha nenastane** v žádném bodě. Delší běh s otevřeností 0,5
  (seedy 1..4): sousedé 0,061 (3 000 let) → 0,073 (4 000) → 0,090 (6 000),
  přírůstek za tisíciletí klesá z 0,021 na asi 0,009. Kontinuum se tedy dál
  pomalu rozchází, ale zpomaluje a sousedé zůstávají v pásmu; jazyk je
  i po 6 000 letech převážně jeden (1,25). Pravděpodobná příčina:
  nevratná ustálení (fonologizace, nahrazená slova) v jedné vesnici,
  která mísení už nesmaže. Otevřená otázka pro M7.

## Přijetí

`Parameters.village_openness` = **0,5**, `border_link_scale` = 1,0. Mění se
jen `region_world`; `village_grid` a ostatní scénáře mají dál 0,1, otisky
a brány se nemění.

**Důsledek:** kalibrace gramatiky M7a běžela na `village_grid`
s otevřeností 0,1. Při otevřenosti 0,5 se inovace šíří jinak, takže M7a je
potřeba zopakovat na `region_world`, až se tam přesune celá kalibrace.
