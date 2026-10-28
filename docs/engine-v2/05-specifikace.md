# Iterace 5 — specifikace

Cíl: převést iterace 1–4 na technické zadání, podle kterého se dá
implementovat a ověřovat. Tato iterace je závazná pro kód; předchozí
iterace vysvětlují proč.

## Názvosloví

Dokumentace je česky, identifikátory v kódu anglicky (stejně jako zbytek
repa).

| Pojem | Kód | Pojem | Kód |
|---|---|---|---|
| svět | `World` | proměnná | `Variable` |
| sídlo | `Settlement` | varianta | `Variant` |
| skupina mluvčích | `SpeechGroup` | morfém | `Morpheme` |
| kód (varieta) | `Code` | konstrukce | `Construction` |
| repertoár | `Repertoire` | procesní proměnná | `ProcessVariable` |
| vazba | `Link` | změna | `Change` |
| událost | `WorldEvent` | tlak | `Pressure` |
| generace (krok) | `tick` | šíření / přenos | `Transmission` |

## Struktura balíčku

Nový engine žije vedle legacy v `src/cee/v2/` a nesdílí s ním stav.

```
src/cee/v2/
  world.py            World, Settlement, SpeechGroup, Link, Code
  repertoire.py       Variable, Variant, Distribution, Repertoire
  pools.py            živé proměnné po sloupcích (LivePools)
  language/
    segments.py       tabulka hlásek nad PanPhonem, přirozené třídy
    processes.py      Process: jedna zvuková změna v jednom prostředí
    lexicon.py        Morpheme, UnitForm, FormStore, PhonologyState
    morphology.py     Paradigm, FormChange (vyrovnání, rozšíření vzoru)
    protoforms.py     protojazyk a nové kořeny podle fonotaktiky
    constructions.py  Construction (M4)
  changes/
    base.py           Change (rodič)
    sound.py          rodiny A
    morphology.py     B
    syntax.py         C
    lexicon.py        D
    contact.py        Výpůjčka, Kalk
  pressures/
    base.py           Pressure
    linguistic.py     artikulace … expresivita
    social.py         učitelnost … tabu
  transmission.py     děti, dospělí, L2, inkrementace, drift, prahy
  phonology.py        procesní proměnné, fonologizace, uzavření, povrch
  morphology.py       tvary buněk, produktivita, analogie, její zápis
  assessment.py       hodnocení procesu nad slovní zásobou (pro tlaky)
  events.py           WorldEvent a jeho podtřídy
  observe.py          vzdálenosti, shluky, linie jazyků
  history.py          log událostí, snímky
  rng.py              deterministické generátory
  simulation.py       hlavní smyčka
tests/v2/
```

## Datové struktury

```python
@dataclass(frozen=True, slots=True)
class Variant:
    id: VariantId                 # stabilní hash z původu
    variable: VariableId
    payload: Payload              # výstup procesu / id morfému / alomorf / id konstrukce
    origin: Origin                # změna, tick, skupina, kód, rodičovská varianta

@dataclass(slots=True)
class Distribution:
    variants: tuple[VariantId, ...]
    freqs: np.ndarray             # float64, součet 1
    previous: np.ndarray | None   # pro inkrementaci

@dataclass(slots=True)
class Repertoire:
    base: Repertoire | None       # sdílený předek (copy-on-write)
    overrides: dict[VariableId, Distribution]
    morphemes: MorphemeStore      # podkladové formy, rovněž copy-on-write
    constructions: ConstructionStore

@dataclass(slots=True)
class Code:
    id: CodeId
    repertoire: Repertoire
    usage_share: float            # podíl užívání ve skupině
    acquisition: Literal["L1", "L2"]
    l1_source: CodeId | None      # odkud plyne interference u L2

@dataclass(slots=True)
class Territory:
    id: TerritoryId
    level: Literal["world", "continent", "region", "area", "settlement"]
    parent: TerritoryId | None
    children: list[TerritoryId]   # prázdné = nerozepsáno
    geometry: Geometry            # hranice nebo bod, terén
    refined_from_year: int | None # None = rozepsáno od začátku

@dataclass(slots=True)
class SpeechGroup:
    id: GroupId
    territory: TerritoryId        # sídlo, nebo nerozepsané území
    aggregate: bool               # True = souhrnná skupina
    internal_diversity: float     # jen u souhrnné skupiny
    population: int
    generation_years: float       # G, výchozí 25
    prestige: float
    openness: float
    literacy: float
    schooling: float
    codes: list[Code]

@dataclass(frozen=True, slots=True)
class Link:
    source: GroupId
    target: GroupId
    strength: float
    kind: Literal["strong", "weak"]
    prestige_bias: float
```

Proměnná s jedinou variantou na 100 % se v `overrides` neukládá (je v
`base`). Skupiny pocházející ze stejného protojazyka tak sdílejí naprostou
většinu dat.

## Rozhraní mechanismů

```python
class Change(ABC):
    kind: ClassVar[str]
    target: ClassVar[VariableType]          # process / lexical / form / construction
    pressures: ClassVar[Mapping[type[Pressure], float]]
    base_rate: ClassVar[float]              # inovací na místo a jednotku tempa
    rate_basis: ClassVar[Literal["generation", "year"]]
    # generation: tempo × r (osvojování); year: tempo × Δt (dospělí)

    @abstractmethod
    def sites(self, code: CodeView) -> Sequence[Site]: ...
    def rate(self, code: CodeView, site: Site) -> float:
        return self.base_rate
    @abstractmethod
    def propose(self, code: CodeView, site: Site, rng: Generator) -> Variant | None: ...
    def on_established(self, code: CodeState, variant: Variant) -> list[Restructuring]:
        return []

class Pressure(ABC):
    name: ClassVar[str]
    @abstractmethod
    def scores(self, batch: PressureBatch) -> FloatArray: ...   # [-1, 1]
```

- Tlak hodnotí celý výřez živých proměnných jednoho typu naráz
  (`PressureBatch.freqs` má tvar proměnné × skupiny × sloty). Po
  jednotlivých variantách by to bylo řádově pomalejší.
- Všechny varianty jedné proměnné se hodnotí stejnými tlaky, i když je
  vyrobily různé změny. Tlaky se proto sdružují podle **typu cílové
  proměnné**; deklaruje-li tentýž tlak víc změn, platí nejvyšší váha.
- `CodeView` je jen pro čtení. `CodeContext` drží indexy, které se počítají
  jednou za tick a kód, a to líně: povrchové formy, index homofonů,
  inventář, fonotaktický profil, typové frekvence vzorů.
- `on_established` vrací popis restrukturalizace (např. přepis podkladových
  forem). Provede ji až `restructure.py`, aby změny neměnily stav samy.

## Jeden tick

```
tick(world_t, year):
  1  world  = apply_events(world_t, year)
  2  ctx    = {kód: CodeContext.lazy(kód) for kód in world}
  3  for skupina in sorted(world.groups):
         for kód in skupina.codes:
             for změna in REGISTRY (pevné pořadí):
                 n ~ Poisson( Σ rate(site) · tempo )   # tempo = r nebo Δt podle rate_basis
                 vyber n míst, propose → nové varianty s p0
  4  fitness[kód, proměnná, varianta] = Σ w · tlak.score(...)   # jen živé proměnné
  5  world' = transmit(world, fitness)      # čte jen world, píše nový stav
  6  restructure(world')                    # fonologizace, ustálení, zánik
  7  if tick % N_OBS == 0: observe(world')
  8  return world'
```

- Krok 5 počítá novou generaci výhradně ze staré (dvoufázově), takže pořadí
  skupin výsledek neovlivní.
- Počet inovací se losuje z Poissonova rozdělení přes všechna místa. Nemusí
  se tak procházet každé místo každou generaci.

### Přenos — vzorec

Pro kód *k* skupiny *g*, proměnnou *v* a variantu *x*:

```
vstup(x)  = (1 − o_g) · p_g(x) + o_g · Σ_h  ŵ_gh · p_h(x)
            ŵ_gh = síla_gh · prestiž_h^α / Σ
sel(x)    = vstup(x) · exp(s · fitness_g(x))
inc(x)    = κ · (p_g(x) − p_g^{t−1}(x))           # jen u L1
drift(x)  = z · σ · √(sel(x)(1 − sel(x)) / (r_g · populace_g)),  z ~ N(0, 1)
dítě(x)   = normalizuj(max(0, sel(x) + inc(x) + drift(x)))
dosp(x)   = p_g(x) + a · (vstup(x) − p_g(x))       # malé přizpůsobení dospělých
p'_g(x)   = (1 − r_g) · dosp(x) + r_g · dítě(x)
            r_g = Δt / G_g
```

- `Δt` je délka kroku (výchozí 25 let, nejvýš min `G` ve světě), `G_g` délka
  generace skupiny. Při `G = Δt` se obnoví celá generace, při `G = 500` jen
  5 % populace za krok.
- `inc` se počítá vůči stavu o jednu generaci zpět, ne o jeden krok.
  Skupina s jedinou variantou trend nemá.
- `sel` se před přičtením `inc` a `drift` normalizuje.
- Drift je Wright–Fisherův: varianta, kterou kohorta vůbec neslyší, driftem
  vzniknout nemůže. `σ` nad 1 vyjadřuje, že na jazyk nemají všichni mluvčí
  stejný vliv (efektivní populace `N / σ²`).

- U L2 kódu se `vstup` doplní o interferenci: varianty stejné proměnné z
  `l1_source` s vahou úměrnou podílu L2 mluvčích.
- Varianta zaniká pod `max(ε, 0,5 / (r_g · populace_g))`, tedy když na ni v
  učící se kohortě nepřipadá ani půl mluvčího (`ε = 0,001`).
- Vedoucí varianta nad `θ = 0,999` se stane jedinou. Je to jen úklid zbytků:
  ustálení vzniká tím, že ostatní varianty vymřou. (Původní `θ = 0,95`
  okamžitě vracelo každou novou inovaci na 2 % zpět na starou variantu.)
- Startovní hodnoty konstant: `α = 1`, `s = 1`, `κ = 0,3`, `σ = 2`,
  `p0 = 0,02`, `a = 0,05`, otevřenost venkovské skupiny `o = 0,1`. Všechny
  se kalibrují (M7).

### Souhrnné skupiny a přiblížení

- Souhrnná skupina se v přenosu chová jako každá jiná, jen její `vstup`
  zahrnuje vnitřní míšení (`o = 1` mezi jejími neviditelnými částmi).
  Výsledkem je správně pomalejší drift velké populace.
- **Přepočet od začátku** (výchozí): nový běh s jemnějším stromem území.
  Seedy se odvozují ze stabilních ID území a skupin, takže nedotčené oblasti
  dostanou tytéž náhodné tahy.
- **Zjemnění od roku X**: v roce X se souhrnná skupina nahradí podřízenými
  skupinami s kopií jejího repertoáru (copy-on-write) a populací rozdělenou
  podle sídel. Rozdělení se zapíše do logu jako `refinement`.

## Determinismus

- Každý náhodný tah: `np.random.Generator(PCG64(SeedSequence([seed_světa,
  otisk(tick, ID_skupiny, ID_kódu, druh_změny)])))`. Používají se stabilní
  ID, ne indexy, aby přidání skupiny jinde nezměnilo tahy ostatních.
- Drift je hashovaný šum závislý jen na (seed, tick, skupina, varianta), ne
  generátor na každou dvojici.
- Míšení se násobí zvlášť pro každou propojenou komponentu sítě: BLAS
  sčítá v pořadí podle velikosti matice. Součty přes sloty se řadí, aby
  nezáležely na pořadí slotů. Díky tomu zjemnění oblasti nezmění ani
  poslední bity v nepropojené oblasti.
- Identifikátory variant, morfémů a linií jsou hashe (`blake2b`) jejich
  původu. Žádné `uuid4`, žádná iterace přes `set`.
- Registr změn a tlaků má pevné pořadí. Redukce přes skupiny běží v pevném
  pořadí a ve `float64`.
- Test: dva běhy se stejným seedem dají bajtově shodný log historie.

## Výkonový rozpočet

Rozpočet odpovídá režimům UI z iterace 4 (údolí → svět). Počítá se v
aktivních jednotkách, tedy včetně souhrnných skupin.

| Režim UI | Rozsah | Cíl |
|---|---|---|
| údolí, oblast | 50 skupin, 500 morfémů, 2 000 let | ≤ 5 s |
| region, země | 200 skupin, 1 500 morfémů, 3 000 let | ≤ 60 s |
| kontinent, svět | 1 000 skupin, 2 000 morfémů, 5 000 let | ≤ 15 min, paralelně přes procesy |

Hrubý náčrt na úrovni světa (desítky souhrnných skupin) má být hotový v
řádu sekund, aby autor mohl iterovat dřív, než začne přibližovat.

Jak toho dosáhnout:

- Počítají se jen **živé proměnné**. Ustálené nestojí nic.
- Povrch se přepočítá jen u morfémů, jejichž forma nebo prostředí se
  změnily (index segment → morfémy).
- Homofonie a funkční zátěž přes hashovací index povrchových tvarů a
  sousedů s jednou záměnou, nikdy porovnáním všech dvojic.
- Živé proměnné leží po sloupcích v `LivePools` (proměnné × skupiny ×
  sloty) a celý krok se počítá vektorově. Bloky podle kapacity slotů
  (2, 4, 8, …) brání tomu, aby jedna proměnná s mnoha variantami
  nafoukla pole všem ostatním.
- Copy-on-write repertoáry: skupina kopíruje jen to, co se u ní liší.

## Historie a export

- **Log událostí** (append-only JSONL): inovace, překročení 10/50/90 %,
  ustálení, zánik, restrukturalizace, rozštěpení shluku, světová událost.
  Každý záznam nese tick, rok, skupinu, kód, proměnnou a variantu.
- **Snímky** každých N generací: shrnutí repertoárů (dominantní tvary,
  živé varianty) a shluky jazyků. Z nich čte UI časovou osu a mapu.
- **Rodokmen slova** se skládá z logu: linie morfému → restrukturalizace →
  výpůjčka → posun významu.
- Formát exportu se navrhne spolu s novým UI; adaptér na současné
  genealogické úložiště je volitelný.

## Metriky realističnosti

Měří se automaticky po každém validačním běhu. Pásma jsou výchozí a
zpřesní se kalibrací.

| # | Metrika | Cílové pásmo | Zdroj |
|---|---|---|---|
| 1 | retence základní slovní zásoby (Swadesh-100) za 1 000 let | 70–95 % | glottochronologie (Lees 1953), Pagel a kol. 2007 |
| 2 | souvislost frekvence slova a rychlosti náhrady | záporná korelace | Pagel a kol. 2007 |
| 3 | průměrná délka slova základní slovní zásoby | celou dobu 3–8 segmentů | modelová pojistka |
| 4 | velikost a složení inventáře | mezi 2,5. a 97,5. percentilem PHOIBLE | PHOIBLE |
| 5 | homofonie v základní slovní zásobě | < 5 % | modelová pojistka |
| 6 | rozložení typů zvukových změn | blízko katalogu doložených změn (Hellingerova vzdálenost) | `DIRECTIONAL_SOURCES.md` |
| 7 | tvar šíření ustálených změn | logistická křivka, R² > 0,9 | Kroch 1989 |
| 8 | podíl inovací, které se ustálí | malý zlomek (modelová vlastnost) | — |
| 9 | vzdálenost dialektů vs. zeměpisná vzdálenost | rostoucí, sublineární (logaritmus sedí lépe než přímka) | Séguyho zákon, Nerbonne 2010 |
| 10 | divergence sesterských jazyků po N letech | v rozložení GLED | GLED |
| 11 | morfologická složitost vs. velikost populace a podíl L2 | záporná korelace | Lupyan & Dale 2010, Trudgill 2011 |
| 12 | determinismus | shodný log při shodném seedu | AGENT.md |

## Validační scénáře

| Scénář | Nastavení | Co musí vyjít |
|---|---|---|
| S1 kontinuum | řada 20 vesnic se stejnými vazbami | plynulý gradient bez ostré hranice; po vložení hranice státu mezi 10. a 11. vesnici se během několika generací vytvoří svazek izoglos |
| S2 ostrov vs. křižovatka | stejný protojazyk; izolovaný ostrov proti obchodnímu městu s přílivem dospělých přistěhovalců | ostrov si drží nepravidelnosti a složitou morfologii, město zjednodušuje |
| S3 přechod jazyka | menšinová skupina přejde na prestižní jazyk | v cílovém jazyce té skupiny zůstanou procesní a konstrukční stopy prvního jazyka, ale málo slov |
| S4 diglosie | písmo v roce X, škola v roce Y | rozdíl mluvené a psané řeči roste do Y, pak se zmenšuje |
| S5 latina → románské jazyky | latinský lexikon a morfologie, zjednodušená sociální historie impéria a jeho rozpadu | kvalitativní kontrolní seznam: palatalizace velár před předními vokály, ztráta pádů, člen z ukazovacího zájmena, budoucí čas z opisu, lenice v části území. Typy změn, ne přesné tvary. |

### Data pro S5

- **Lexikon:** IE-CoR (Heggarty a kol. 2023, CC BY 4.0, `lexibank/iecor`).
  Latina má 170 pojmů základní slovní zásoby s rozdělením na hlásky (CLTS).
  Stejný soubor obsahuje reflexy v italštině, španělštině, portugalštině,
  francouzštině, katalánštině, rumunštině, sardinštině, neapolštině,
  dalmatštině a ve staré francouzštině, staré španělštině a staré
  okcitánštině, s kognátními sadami a označením výpůjček. Z nich se
  porovná, jaké typy změn simulace vyrobila, ne přesné tvary.
- **Morfologie:** IE-CoR má jen citační tvary. Doplní se ručně kurátorovaná
  minimální paradigmata: 1.–3. deklinace, prézens, perfektum a futurum
  sloves, ukazovací zájmeno *ille*, sloveso *habere*. Odhadem 30–40 morfémů.
- Data se stahují mimo Git novým příkazem (např. `cee data update iecor`), s verzí, licencí a
  citací v manifestu, stejně jako PHOIBLE.

## Testy

- **Jednotkové**: každá `Change` a každý `Pressure` na mikrosvětě o jedné
  skupině a několika morfémech.
- **Vlastnosti**: frekvence proměnné dávají 1, nic nevzniká ani nezaniká
  mimo log, determinismus.
- **Emergence**: testy z tabulky v iteraci 3 (řetězový posun,
  morfologizace, analytizace, koineizace) jako malé scénáře s tolerancí.
- **Scénáře a metriky**: S1–S5 a metriky 1–12 jako regrese s pásmy.
- **Výkon**: benchmark malého a středního světa v CI s prahem.

## Milníky

Každý milník je svislý řez: musí splnit svou bránu, než začne další.

| Milník | Obsah | Brána |
|---|---|---|
| **M1 jádro** | svět, strom území, skupiny (i souhrnné), síť, délka generace, lexikální proměnné, přenos, pozorování; bez fonologie | S1, metrika 7, 8, 9 (rostoucí), 12, režim údolí ≤ 5 s, přiblížení zachová determinismus |
| **M2 zvuk** | segmenty, morfémy, procesní proměnné, fonologizace, povrch, rodiny A, jazykové tlaky | metrika 3–6, emergentní řetězový posun |
| **M3 morfologie** | alomorfy, paradigmata, změny B, `Uniformita`, `Frekvence` | emergentní morfologizace, Sturtevantův paradox v testu |
| **M4 syntax** | konstrukce, změny C, velký cyklus | emergentní analytizace při erozi |
| **M5 kontakt** | kódy, L1/L2, interference, výpůjčky, přechod | S2, S3, metrika 11 |
| **M6 společnost** | instituce, události, linie jazyků, export pro UI | S4, stabilní emergentní strom, metrika 9 (sublineární) |
| **M7 kalibrace** | hledání vah a konstant proti metrikám | S5, metriky 1, 2, 10 |

### Stav M1 (2026-10-28)

Splněno, testy v `tests/v2/test_v2_m1_gate.py`:

- S1: plynulé kontinuum bez ostré hranice; hranice státu vytvoří svazek
  izoglos (vzdálenost přes hranici víc než dvojnásobná oproti ostatním
  sousedům).
- Metrika 7: medián R² logistické křivky ustálených změn ≈ 0,98.
- Metrika 8: ustálí se zhruba 2 % inovací.
- Metrika 9: vzdálenost roste se zeměpisnou vzdáleností (korelace > 0,9).
  **Sublinearita zatím ne:** v M1 má výhodná inovace výhodu ve všech
  skupinách (dočasný tlak `Appeal`), takže úspěšná změna časem projde celým
  kontinuem. Přesunuto do brány M6 (tlak identity, města jako uzly slabých
  vazeb); test je označený jako očekávané selhání.
- Metrika 12 a přiblížení: stejný seed dá stejný log; zjemnění jedné
  oblasti nezmění historii nepropojené oblasti ani v posledním bitu.
- Výkon: režim údolí (50 skupin, 500 pojmů, 2 000 let) ≈ 4,6 s na vývojovém
  notebooku.
- Retence slovní zásoby v S1 vychází kolem 80 % za tisíciletí (metrika 1 se
  hodnotí až v M7).

### Stav M2 (2026-10-28)

Splněno, testy v `tests/v2/test_v2_m2_gate.py` a `test_v2_phonology.py`.
Měřeno na kontinuu 10 vesnic, 3 seedy, 3 000 let:

- Metrika 3: průměrná délka slova 4,5–4,6 hlásky po celou dobu.
- Metrika 4: 22–26 souhlásek a 6–9 samohlásek (pásma WALS 1A/2A).
- Metrika 5: homofonie nejvýš 2,7 % základní slovní zásoby.
- Metrika 6: ustálené změny 63 % souhláskové a 37 % samohláskové proti
  prioru 58 % / 33 % / 9 % (stavba slabiky); Hellingerova vzdálenost
  0,22. Ustálí se 11 rodin. Jazyky z různých seedů sdílejí jen 37–45 %
  ustálených změn.
- Fonologizace: 5–8 % zasažených slov zůstane reliktní výjimkou; častá slova
  vedou v redukčních změnách; dřívější změna připraví půdu pozdější.
- Řetězový posun: posun do uvolněného místa nemá cenu funkční zátěže,
  splynutí s obsazeným vokálem ano (test mechanismu, ne scénáře).
- Zjemnění jedné oblasti nezmění ani zvukovou historii nepropojené oblasti.
- Výkon: 10 vesnic × 150 pojmů × 3 000 let ≈ 4,7 s. Režim údolí bez
  hláskových tvarů (brána M1) ≈ 4,9 s.

Zpřesnění návrhu při implementaci:

- **Životní cyklus změny** (`phonology.py`): proces začne působit na slova
  od 5 % ve skupině; slovo si změnu zapíše při `p_slovo > 0,85`, kde
  `p_slovo = σ(logit p + β·(2f − 1) + b)`, `β = 1` jen u redukčních změn a
  sklon slova `b ~ N(0; 1,5)`. Po dvou generacích na 100 % se proces
  uzavře: nové slovo jím už neprojde a nepřepsaná slova jsou relikty.
- **Chronologii změn drží každý kód sám** (pořadí, ve kterém ho změny
  zasáhly). Globální pořadí vzniku by svázalo nepropojené oblasti.
- **Paralelní inovace** téže změny ve dvou skupinách je tatáž proměnná i
  tatáž varianta a ve skladu sdílí slot.
- **Výstup změny je vždy obyčejná hláska** (bez sekundární artikulace),
  nejbližší k požadovaným rysům; jinak by z /o/ se zvýšeným jazykem vzniklo
  /oˠ/, ne /u/.
- **Tlak `Actuation`** (sociální ocenění změny podle skupiny a epochy, viz
  iterace 3) doplněn: bez něj prošly všechny jazyky stejnými, typologicky
  nejvýhodnějšími změnami (lenice všude).
- **Úspora artikulace je jen mírná** (typicky 0,15). Silnější
  deterministická výhoda převálcovala nahodilost spuštění.
- Tlaky hodnotí změnu nad 120 nejčastějšími slovy kódu a hodnocení
  drží 8 kroků; je to přibližné, ale cena nezávisí na velikosti slovníku.
- Vzdálenost dialektů zatím jen z lexikálních proměnných; mrtvé zvukové
  inovace by ji ředily. Srovnání tvarů kognátů přijde v M6.
- Slovo převzaté od sousedů vstupuje ve výchozím tvaru; adaptace podle
  tvaru u zdroje přijde s kontaktem v M5.

### Stav M3 (2026-10-28)

Splněno, testy v `tests/v2/test_v2_m3_gate.py` a `test_v2_morphology.py`.
Měřeno na kontinuu 8 vesnic, 2 seedy, 3 000 let; podstatná jména mají
singulár a plurál (koncovky -i 65 %, -an 35 %), slovesa prézens a
préteritum (-ta 70 %, -u 30 %):

- **Sturtevantův paradox**: bez vyrovnání má po 3 000 letech 67–70 % buněk
  alternaci kmene, s vyrovnáním 46–47 %.
- **Morfologizace vzniká sama**: 6–15 % buněk ztratilo koncovku a od
  citačního tvaru se liší jen kmenem (typ přehlásky). Synkretismus zůstává
  pod 2 %.
- **Produktivita**: většinová koncovka se rozšíří z 65 % na 93–99 %.
- **Častá slova si drží nepravidelnost**: menšinovou koncovku má 6–19 %
  buněk častých lexémů a 0–1 % vzácných; analogie zasahuje spíš vzácná slova.
- Zvukové metriky (délka slova, homofonie) drží i s paradigmaty.
- Výkon: 8 vesnic × 150 pojmů (240 tvarů buněk) × 3 000 let ≈ 6 s.

Zpřesnění návrhu při implementaci (mění iteraci 2):

- **Slovo a paradigma místo alomorfů**: každá buňka paradigmatu je
  samostatný uložený tvar s hranicí kmen | koncovka a odkazem na koncovku
  (`UnitForm`). Zvukové změny z M2 tak pracují s celými tvary beze změny a
  alomorfie, eroze koncovek i synkretismus jsou jen rozdíly mezi tvary.
  Hranice se při každé změně přepočítá (vložení na hranici patří ke
  koncovce, splynutí přes hranici ke kmeni).
- **Sklon slova vůči zvukové změně patří lexému**, ne tvaru: všechny
  buňky změnu přijmou nebo odmítnou společně a výjimka nevyrobí falešnou
  alternaci.
- **Analogie je formová proměnná** jednoho tvaru (`level`, `extend`). Když
  ve skupině převáží (85 %), tvar se zapíše a změna se uzavře. Nový lexém
  dostane tvary buněk podle produktivní koncovky kódu.
- **Tlaky** `Uniformity` (vyrovnání +0,4, rozšíření 0,35 × zisk
  produktivity), `Conservation` (−0,6 × (2f − 1); jména podle iterace 3
  „Frekvence“) a `Distinctiveness` (−0,8 za vznik synkretismu, +0,6 za jeho
  odstranění). Funkční zátěž zvukových změn počítá splynutí buněk téhož
  paradigmatu dvojnásobně.
- **Odloženo**: gramatikalizace (potřebuje konstrukce, M4), odvozování a
  skládání, reanalýza hranice, kontaminace, zpětné tvoření a exaptace.

## Co převzít z legacy

| Převzít | Nepřevzít |
|---|---|
| `engine/phonology.py` (`FeatureMapper`) | `simulator.py`, `generator.py`, `schemas.py` |
| `engine/empirical.py` (PHOIBLE) | `rules.py`, `decisions.py`, `fold.py` |
| `semantics/` (CLICS, DatSemShift, Concepticon, retence) | `lexicon.py`, `morphology.py`, `social.py` |
| `data/core_vocabulary.py`, Swadeshovy seznamy | `semantic_history.py`, `historical.py` |
| metriky GLED a vzdáleností z `metrics/` | |

Legacy zůstává funkční a testovaný, dokud v2 neprojde M6. Pak se rozhodne
o jeho odstranění.

## Zdroj vah zvukových změn

Otevřený globální katalog směrovaných zvukových změn s licencí slučitelnou
s pravidly projektu (CC0, CC BY, MIT, BSD) v době psaní neexistuje. Audit
zdrojů je v [`DIRECTIONAL_SOURCES.md`](../DIRECTIONAL_SOURCES.md). Váhy
rodin A proto vzniknou ve dvou vrstvách:

1. **Autorský typologický prior.** Ručně nastavené váhy rodin a jejich
   parametrů podle obecně známých směrů změny z učebnic a přehledové
   literatury (lenice je častější než fortice, palatalizace před předními
   vokály, redukce v nepřízvučné pozici…). Prior je označený jako
   heuristický a cituje literaturu, ze které vychází; nepřebírá žádnou
   databázi ani její strukturu.
2. **Empirická korekce.** Směrované korespondence odvozené z otevřených
   historických dat s protoformami: IE-CoR (latina → románské jazyky), ACD
   (praaustronéština → austronéské jazyky, CC BY 4.0), lexibank datasety s
   protoformami a licencí CC BY (ověřit jednotlivě), BDPROTO pro inventáře.
   Korespondence se zarovnají přes LingPy/LingRex, kurátor je ověří a
   načtou se existující cestou `cee calibrate global`.

Dvě rodiny (románská, austronéská) nestačí na globální tvrzení. Engine
proto uvádí, z kolika nezávislých rodin váha pochází, a bez dalších rodin
ji neprezentuje jako globální kalibraci.

## Otevřená rozhodnutí

- Právní posouzení zdrojů s licencí CC BY-SA (např. Mixtec Sound Change
  Database 2.0): zda je přípustné z nich odvozovat agregované váhy. Do
  rozhodnutí se nepoužívají.
