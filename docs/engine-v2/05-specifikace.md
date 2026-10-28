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
    constructions.py  Construction, zdroje gramatikalizace
  changes/
    base.py           Change (rodič)
    sound.py          rodiny A
    morphology.py     B
    syntax.py         C
    lexicon.py        D
  pressures/
    base.py           Pressure
    linguistic.py     artikulace … expresivita
    social.py         učitelnost … tabu
  transmission.py     děti, dospělí, L2, inkrementace, drift, prahy
  phonology.py        procesní proměnné, fonologizace, uzavření, povrch
  morphology.py       tvary buněk, produktivita, analogie, její zápis
  semantics.py        graf pojmů (výřez CLICS⁴ + DatSemShift), recepty složenin
  syntax.py           konstrukční proměnné, slabost vyjádření, zápis nové koncovky
  assessment.py       hodnocení procesu nad slovní zásobou (pro tlaky)
  contact.py          filtry přenositelnosti, adaptace výpůjček, přechod jazyka
  institutions.py     psaný kód, kanály čtení a školy
  events.py           WorldEvent a jeho podtřídy
  observe.py          vzdálenosti (slova, tvary příbuzných slov, konstrukce), shluky, linie jazyků
  export.py           export běhu pro UI (JSON)
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
- `p0` platí pro skupinu o 500 obyvatelích. Inovace začíná u jednoho
  mluvčího, takže skupina s `N` obyvateli dostane počáteční podíl
  `p0 · 500 / N` (v mezích 0,002 až 0,2) a inovací v poměru `p0` ku tomuto
  podílu. Tempo neutrálních změn tak na velikosti nezávisí (Kimura 1968);
  malá skupina víc podléhá driftu, velká selekci.

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
| **M3b lexikon a význam** | sémantický graf pojmů (výřez CLICS⁴ + DatSemShift), posun významu, odvozování, skládání, expresivní tvoření, tabu a opis, kontaminace, zpětné tvoření; lexikální tlaky místo dočasného `Appeal` | metrika 1 (retence 70–95 % za tisíciletí), metrika 2 (častá slova se nahrazují pomaleji), nová slova mají doložitelný původ, erodovaná a homofonní slova se nahrazují častěji |
| **M4 syntax** | konstrukce, změny C, velký cyklus | emergentní analytizace při erozi |
| **M4b modulární gramatika** | katalog gramatických funkcí (data), profil gramatiky protojazyka, varianta `zero`, buňky paradigmatu vznikající za běhu, exaptace | brána M4 beze změny prahů; vznik členu z ukazovacího zájmena, exaptace zbytkové koncovky, jazyk bez kategorie |
| **M5 kontakt** | kódy, L1/L2, interference, výpůjčky, přechod | S2, S3, metrika 11 |
| **M6a instituce** | písmo jako zmrazený psaný kód, gramotnost, škola, tisk, tlak `Norma` | S4 |
| **M6b společnost** | události (migrace, dobytí, válka, epidemie, kolaps, obchod, náboženská změna), podíl L2 z migrace, domény a vitalita jazyka (stabilní dvojjazyčnost, přechod elity a superstrát, Fergusonova diglosie) | metrika 9 (sublineární), stabilní dvojjazyčnost, superstrát, diglosie, liturgické výpůjčky |
| **M6c linie a export** | vzdálenost i podle tvarů kognátů, emergentní strom jazyků, export pro UI, změření výkonu | stabilní emergentní strom se známou historií |
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

### Stav M3b (2026-10-28)

Splněno, testy v `tests/v2/test_v2_m3b_gate.py` a `test_v2_lexicon.py`.
Měřeno na kontinuu 8 vesnic, 3 seedy, 3 000 let:

- **Metrika 1**: retence základní slovní zásoby 90,6–91,1 % za tisíciletí
  (pásmo 70–95 %; průměr glottochronologie ~86 % doladí M7).
- **Metrika 2**: nahrazeno 0,8–1,6 % častých a 33–37 % vzácných pojmů.
- **Původ nových slov**: posun významu ~40 %, odvození ~40 %, složenina
  ~17 %, nový kořen ~1 %. Příklady doložených cest: „den“ ze „slunce“,
  „vědět“ z „vidět“, „červený“ z „krve“.
- **Eroze**: v kontrolovaném pokusu se slova zkrácená na dvě hlásky
  za 1 500 let nahradí v 71 % případů, kontrolní slova v 16 %.
- **Tabu**: za 2 500 let se u tabuizovaného pojmu vystřídají aspoň dva
  opisy (eufemistický koloběh); bez tabu žádný.
- Výkon: 8 vesnic s fonologií, paradigmaty a významem × 3 000 let ≈ 9 s.

Zpřesnění návrhu při implementaci:

- **Graf pojmů je přibalený** (`cee/data/v2_core_semantics.json`, 425 vztahů
  mezi 132 pojmy, CC BY 4.0, citace a SHA-256 vstupů uvnitř) a vzniká
  skriptem `scripts/build_v2_core_semantics.py` z lokální cache. DatSemShift
  dává orientované posuny a odvození zvlášť (počty rodin), CLICS⁴
  kolexifikace (aspoň 5 jazyků). Recepty složenin jsou převzaté z legacy
  (`docs/SWADESH_COMPOUNDS.md`).
- **Každý kód vede, který kořen je dominantní pro který pojem.** Posun
  významu dá jednomu kořeni víc pojmů; ze slovní zásoby vypadne, až když ho
  neužívá žádný.
- **Frekvence užití se vyvíjí** (dříve známá mezera): tvar je tak častý,
  jak časté jsou pojmy, které právě vyjadřuje. Frekvence je vlastnost
  významu; slovo, které posunem získá pojem, zčastění.
- **Lexikální tlaky** místo dočasného `Appeal` (ten zůstává jen ve světě
  bez hláskových tvarů, M1): `LexicalClarity` (−0,5 za erozi na dvě hlásky,
  −0,4 za homofon s nepříbuzným pojmem; krátké slovo odjakživa se netrestá),
  `Entrenchment` (+0,3 × frekvence pojmu pro dominantní slovo; Pagel),
  `Motivation` (průhledná odvozenina či složenina +0,15, posun +0,05, nový
  kořen −0,15), `Taboo` (−0,6 pro slovo užívané déle než 10 generací),
  `LexicalActuation`.
- **Posun významu jen mezi pojmy stejné třídy slov**; konverze (sloveso →
  jméno) zatím chybí.
- Odvozovací přípona se nemění zvukovými změnami (nežije ve slovní zásobě
  sama); změnami prochází až odvozené slovo jako celek.
- Homofonie v metrikách počítá jen různé kořeny se stejným tvarem; posun
  významu je polysémie.

### Stav M4 (2026-10-28)

Splněno, testy v `tests/v2/test_v2_m4_gate.py` a `test_v2_syntax.py`.
Scénář se syntaxí: podstatná jména mají i tvar předmětu (-m 60 %, -ne 40 %),
minulý čas je syntetický, zápor částice před slovesem, slovosled volný.
Přirozená eroze konkrétní koncovky je vzácná (viz Známé mezery), proto se
odpověď syntaxe ověřuje kontrolovanými pokusy na kontinuu 6 vesnic:

- **Analytizace**: po erozi pádu předmětu přejde na pevný slovosled všech
  6 vesnic do 1 500 let; bez eroze zůstane volný ve všech.
- **Velký cyklus**: po erozi minulého času převezme funkci do 500 let opis
  (*dokončit* + sloveso), ten se stane přiklonkou a v letech 1 250–1 900
  sroste v novou koncovku v 6 vesnicích; slabost vyjádření klesne ze 100 %
  na 3–4 %. Nejčastější slovesa si ponechají starý tvar (silná slovesa).
- **Jespersenův cyklus**: po obroušení záporky přejde 4 z 6 vesnic do 500
  let na *ne … zesilovač* a do 1 000 let na samotný zesilovač; cyklus pak
  může začít znovu.
- Bez eroze zůstává syntax beze změny a zvukové metriky drží.

Zpřesnění návrhu při implementaci:

- **Gramatická funkce je konstrukční proměnná** (`PAST`, `NEG`, `ORDER`).
  Změny navrhují jen další krok od konstrukce, která ve skupině převažuje,
  takže gramatikalizace je jednosměrná. Zdroje (`have`, `finish`, `come`
  pro minulý čas; `thing`, `step`, `one` pro zápor) jsou autorský výběr
  podle Heine & Kuteva 2002.
- **Tlaky**: `Expressivity` (opis a nová koncovka získají tolik, kolik tvarů
  minulého času splynulo; zápor je tak silný jako jeho neobroušené slovo),
  `Economy` (−0,15 za každé slovo navíc), `Fusion` (+0,25 pro další krok
  gramatikalizace), `Ambiguity` (volný slovosled −podíl splynulých tvarů
  předmětu).
- **Slabost slova = eroze, ne krátkost**: krátká záporka odjakživa (*ne*)
  slabá není.
- **Zpětná vazba syntax → zvuk**: splynutí pádu předmětu s citačním tvarem
  stojí ve funkční zátěži jen 30 %, když skupina už má pevný slovosled.
  Funkční zátěž zvukových změn byla zmírněna (násobek 5 místo 12, splynutí
  buněk paradigmatu stojí jako běžný homofon), protože eroze koncovek se v
  reálných jazycích děje i přes splynutí tvarů.
- **Nová koncovka** z pomocného slova se zkrátí na první slabiku (fonetická
  redukce při gramatikalizaci) a zapíše se do tvarů minulého času, kromě
  lexémů s frekvencí aspoň 0,7.
- **Reanalýza hranice** mezi záporkou a slovesem (*a napron → an apron*) a
  **konverze** mezi slovními druhy jsou doplněné; exaptace odložena.
- **Přeměřeno po zmírnění funkční zátěže**: metriky M2 drží (63–67 %
  souhláskových změn, délka slova 4,45–4,55, relikty 5,7–6,6 %), homofonie
  klesla na nejvýš 0,7 %; v M3 má s vyrovnáním alternaci 47–48 % tvarů,
  bez něj 71–72 %.
- **Pořadí aktivace procesů** v jednom kroku je nově kanonické (podle ID).
  Dřív záviselo na pořadí řádků skladu, které ovlivňují i nepropojené
  oblasti; test izolace z M2 to zachytil.

### Stav M4b (2026-10-28)

Splněno, testy v `tests/v2/test_v2_m4b_gate.py`; brána M4 prošla po přepisu
beze změny prahů.

- **Katalog gramatických funkcí** `cee/data/v2_grammar.yaml`: funkce je
  řádek dat, ne kód. Pole: šablona (`inflection` koncovka/opis/nic,
  `negation` Jespersenův cyklus, `order` slovosled), třída slov, buňka a
  její váha, potřeba `need` (0 až 1), zdroje gramatikalizace, `compensates`
  (čí roli funkce převezme) a `donors` (čí zbytkovou koncovku si může vzít).
  Katalog má minulý čas, budoucí čas, plurál, pád předmětu, určenost, zápor
  a slovosled. Změny, tlaky, hodnocení funkční zátěže i reanalýza hranice
  čtou jen katalog.
- **Profil gramatiky protojazyka** (`village_grid(grammar=…)`, výchozí
  `SYNTAX_GRAMMAR`): funkce → výchozí konstrukce. Funkce mimo profil jazyk
  nemá a nevyvine; funkce s konstrukcí `zero` nevyjadřuje, ale vyvinout ji
  může. Buňky paradigmatu se odvodí z funkcí vyjádřených koncovkou; nová
  buňka vznikne, až funkce poprvé sroste v koncovku nebo ji převezme
  exaptací.
- **Tlaky obecně**: `Expressivity` = potřeba × síla vyjádření (nic 0, opis
  a přiklonka 1, koncovka 1 − slabost buňky, nová nezapsaná koncovka 1,
  zápor 1, má-li neobroušené slovo). S `need` 1,0 pro minulý čas a 0,5 pro
  zápor dává stejné rozdíly jako M4. Nově slábne i zapsaná nová koncovka,
  takže druhé kolo velkého cyklu má stejnou hnací sílu jako první.
  `Ambiguity` platí pro každou funkci s `compensates`. Funkce bez buňky má
  slabost 1: jazyk bez pádu dostane pevný slovosled (6 vesnic z 6 ve 3
  seedech).
- **Vznik členu**: v jazyce bez pádu a s určeností jako `zero` (`need`
  0,25) vznikne člen z *that*/*this*. V 8 seedech převládá ve většině
  vesnic do 1 000 let ve 3 jazycích, do 2 000 let v 7 a do 3 000 let ve
  všech; často pak sroste v koncovku (typ skandinávského a rumunského
  postponovaného členu). Řádově to odpovídá románským jazykům (asi 800 let),
  jenže člen nakonec vznikne všude (viz Známé mezery). S `need` 0,4 vznikal
  ještě dřív, proto zůstává 0,25.
- **Opis jako obnova**: opis vedle koncovky se navrhuje, jen když koncovka
  aspoň trochu zeslábla (slabost > 0). Funkci `zero` se navrhuje vždy.
  Opis vedle neporušené koncovky tlaky stejně vždy zahodily (Expressivity
  0, Economy −0,15). Navíc by bral náhodná čísla opisům jiných funkcí: když
  plurál dostal vlastní proměnnou, klesl počet vesnic s novou koncovkou
  minulého času v 11 seedech v průměru z 5,4 na 4,3. S pravidlem obnovy
  jsou čísla stejná jako v M4 (6, 5, 6, 6, 6, 6, 5, 6, 6, 1, 6).
- **Exaptace**: koncovka funkce, jejíž roli nese jiná konstrukce (pád vedle
  pevného slovosledu), přejde na funkci téže třídy slov, kterou jazyk
  nevyjadřoval. V pokusu s pevným slovosledem od začátku přejde koncovka
  předmětu na určenost ve všech 6 vesnicích v letech 925–1 250 (60–64
  slov). Při volném slovosledu se do 1 500 let nestane nic.
- **Jazyk bez kategorie**: bez minulého času v profilu nemají slovesa
  buňku PAST ani po 1 000 letech. S minulým časem jako `zero` ho do 2 000
  let vytvoří opis s *finish* ve všech vesnicích a v 5 z 6 už sroste
  v koncovku; buňka PAST přitom vznikne.
- **Klíč konstrukce** se prodlouží o dárce jen u exaptace, takže ID variant
  z M4 zůstala stejná.

### Stav M5 (2026-10-28)

Splněno, testy v `tests/v2/test_v2_m5_gate.py` a `test_v2_contact.py`.
Svět s jedním jazykem dává po M5 bitově stejnou historii jako před ním
(ověřeno porovnáním otisků logu s předchozím commitem pro světy M1 až M4b).

- **Kód je uzel sítě.** Vícejazyčná komunita je v simulaci víc skupin, jedna
  na kód, se společným `community`. Přenos, sklad živých proměnných i
  všechny změny tak dál pracují se skupinou a jejím hlavním kódem. Iterace 4
  s víc skupinami v jednom sídle počítá; datový model `SpeechGroup.codes`
  zůstává, ale simuluje se jen první kód.
- **Linie jazyka**: `Code.language` a `Morpheme.language`. Svět může mít víc
  protojazyků (`contact_world`); ID slov a variant výchozí linie `proto`
  se nezměnila. Paradigmata světa jsou sjednocení buněk všech jazyků, každý
  jazyk má koncovky jen ve svých buňkách.
- **Filtr přenositelnosti** (Thomason & Kaufman 1988) v míšení: vazba mezi
  skupinami různých linií přenáší proměnnou jen s vahou podle typu.
  Výpůjčka: slova 0,5 × (1 − frekvence pojmu), procesy a konstrukce 0,1,
  analogie 0. Interference L2 kódu z prvního jazyka jeho mluvčích (váha
  0,5 × podíl L2 mluvčích): procesy a konstrukce 1, slova 0,05, analogie 0.
  Konstrukce jsou popsané pojmy, ne morfémy, takže převzatá konstrukce je
  rovnou kalk (vyjádří se domácím slovem pro *step*).
- **Adaptace výpůjčky**: cizí kořen dostane při vstupu do slovní zásoby
  tvar od nejbližšího mluvčího dárcovského jazyka a cizí hlásky se nahradí
  nejbližší hláskou příjemce podle rysů PanPhonu (samohláska zůstane
  samohláskou). Tvary buněk dostane podle produktivních koncovek příjemce a
  jen v buňkách, které příjemce má.
- **Proměnné, ve kterých se jazyky liší od začátku**, se při startu a po
  každé události načtou do živého skladu (`LivePools.load_differing`);
  jinak by se slova dvou jazyků nikdy nesetkala.
- **`Teachability`** (Trudgill 2011): vyrovnání a rozšíření vzoru mají ve
  skupině výhodu rovnou podílu L2 mluvčích a L2 mluvčí je navrhují až
  pětkrát častěji (přehnané zobecnění). Podíl drží přistěhovalectví
  (`immigration`, podíl dospělých nováčků na generaci) nebo přechod jazyka.
- **Přechod jazyka** (událost `LanguageShift`): vznikne skupina téže
  komunity, která mluví kódem cílového jazyka jako druhým (`l2_share` 1,
  otevřenost 0,2, protože komunita se jazyk učí hlavně sama od sebe). Mluvčí
  přecházejí podle Abramse a Strogatze (2003): za generaci podíl `status ×
  podíl_cíle^1,31` (status z prestiže). Pod 20 % užívání se starý kód
  nepředává dětem a skupina jen stárne; pod jednoho mluvčího zaniká
  (`transmission_stopped`, `language_shift`). Pak má skupina zase svou
  dřívější otevřenost.

Naměřeno (seedy 1 a 2, není-li uvedeno jinak):

- **Výpůjčky**: po 1 500 letech kontaktu dvou jazyků přes jednu vazbu má
  každá vesnice 8–15 přejatých slov z asi 200 pojmů a výpůjčky se rozšíří i
  do vnitrozemí. Přejaté pojmy mají průměrnou frekvenci 0,13–0,14, všechny
  pojmy 0,34–0,36. Konstrukce ani koncovky se nepřejímají.
- **S2**: po 2 000 letech má město s 30 % přistěhovalců 7,5–8,2 %
  nepravidelných tvarů vzácných slov, ostrov 27–31 %; podíl produktivní
  koncovky 0,87–0,89 proti 0,68–0,73. Častá slova si nepravidelnost drží i
  ve městě. Totéž město bez přistěhovalců má složitost 0,15–0,17, se 60 %
  přistěhovalců 0,05–0,06.
- **S3**: tři vesnice jazyka s prestiží 0,3 přejdou na sousední jazyk
  s prestiží 1 za 200–250 let (děti přestanou starý jazyk učit 200–250 let po
  kontaktu, hned potom vymře). O 800 let později mají vnitrozemské vesnice
  0,63–0,86 podílu konstrukcí původního jazyka (zápor za slovesem, SOV),
  pohraniční 0,25–0,41, sousední vesnice většinového jazyka 0,04–0,10 a jeho
  jádro 0,01. Všechny zvukové změny původního jazyka jsou zapsané v tvarech
  nového a slov původního jazyka je pod 1,5 %.
- **Metrika 11** (20 izolovaných skupin, populace 100–10 000 × podíl L2
  0–0,45, 1 500 let, seedy 1–3): Spearmanova korelace složitosti s podílem L2
  −0,77 až −0,86, s populací −0,12 až −0,36. Malá skupina drží menšinové
  vzory driftem, ve velké vítězí selekce pro jednotnost. Vliv populace je
  ale slabý; v reálném světě jde z velké části přes podíl L2 mluvčích (velké
  jazyky jich mají víc), který scénář nastavuje nezávisle.

### Inovace podle velikosti skupiny (doplněk M5, 2026-10-28)

Splněno, brány M1 až M5 prošly. Vesnice o 500 obyvatelích dávají bitově
stejnou historii jako před změnou (ověřeno otisky logu), takže se čísla
bran M1 až M4b nezměnila.

- Inovace vzniká u jednoho mluvčího: počáteční podíl `p0 · 500 / N`
  (0,002 až 0,2) a četnost inovací převrácená, aby součin zůstal stejný.
  Do teď měla každá skupina stejný počet inovací a stejný počáteční podíl
  bez ohledu na velikost, takže velikost působila jen driftem.
- **Metrika 11** (seedy 1–3): složitost s velikostí skupiny (při pevném
  podílu L2) Spearman −0,95 až −1,0; s podílem L2 (při pevné velikosti)
  −0,76 až −1,0. Skupina o 100 lidech má složitost 0,34–0,36, o 10 000
  lidech 0,07–0,09. Ve velké skupině selekce pro jednotnost vzorů funguje
  účinně, malá drží menšinové vzory driftem. Test brány měří obě souvislosti
  při pevné hodnotě té druhé; přes všech 20 skupin dohromady velikost
  přebije vliv L2 (korelace s podílem L2 klesla na −0,57 až −0,63).
- **S2**: rozdíl ostrova a města se zvětšil, velké město nepravidelnosti
  vzácných slov odstraní úplně (0 % proti 30–31 % na ostrově). Totéž město
  bez přistěhovalců má složitost 0,07–0,11, se 60 % přistěhovalců
  0,016–0,019; test proto porovnává poměr, ne rozdíl.
- **S3**: konstrukce původního jazyka ve vnitrozemských vesnicích 0,52–0,88;
  zůstane 4–8 kořenů původního jazyka ze 154 (2,6–5,2 %), všechny pro vzácné
  pojmy (frekvence 0,08–0,15), většinou odvozeniny a složeniny vzniklé
  v původním jazyce. Práh brány je proto 8 % a výpůjčky musí být vzácnější
  než průměr.
- **Alternace kmene** zůstává ve velkých skupinách vyšší (Spearman s
  velikostí +0,31 až +0,39). Velká skupina účinněji přijme i přirozené
  zvukové změny zvýhodněné tlaky (oslabování, zkracování) a ty alternace
  vytvářejí. Viz Známé mezery.

### Stav M6a (2026-10-28)

Splněno, testy v `tests/v2/test_v2_m6a_gate.py` a `test_v2_institutions.py`.
Svět bez písma dává bitově stejnou historii jako před M6a (ověřeno otisky
logu pro světy M1 až M5).

- **Psaný kód** (událost `Codification`) je skupina bez mluvčích: kopie
  řeči zdroje (elity), ve které má každá proměnná jen variantu převládající
  v roce kodifikace. Nevznikají v něm inovace, neprochází fonologizací a do
  dialektů ani jazyků se nepočítá. Bez tisku stojí.
- **Tisk** (událost `Printing`): psaná norma se jednou za 100 let reviduje a
  převezme podíl `update` (0,3) řeči zdroje. Nové psané tvary slov se ale
  nezapisují (pravopis zaostává za výslovností).
- **Kanály mimo síť** (`transmission.Channel`): interference z M5, **čtení**
  (gramotní dospělí, váha 0,1 × gramotnost, jen slova) a **škola** (děti,
  0,3 × docházka; slova, konstrukce a tvary plně, zvukové změny jen 0,1,
  protože výslovnost si děti nesou z domova).
- **`Norm`** zvýhodní kodifikovanou variantu o 0,3 × školní docházka. Působí
  na všechny typy proměnných, kromě zvukových změn, které si kód už uzavřel
  do podkladových tvarů: ty škola nevrátí. Silnější norma (0,8) srovnala řeč
  s psanou úplně a každou inovaci přebila.

Naměřeno (S4: šest vesnic, písmo v roce 500, škola a tisk v roce 1500,
seedy 1 a 2):

- Vzdálenost mluvené řeči od psané roste do zavedení školy (rok 1000:
  0,08–0,10, rok 1500: 0,11–0,12) a pak klesne (rok 2000: 0,011–0,014, rok
  2500: 0,006–0,008). Bez školy roste dál až na 0,35–0,36 v roce 3000.
- Škola s tiskem sjednotí dialekty (vzájemná vzdálenost vesnic 0,004–0,007
  proti 0,12–0,13 bez školy), ale jazyk se mění dál: za 500 let se ustálí
  135–560 inovací (bez školy 560–750).
- **Kontrafaktuál**: masová škola se zmrazenou normou (bez tisku) změnu
  prakticky zastaví (1–25 ustálených inovací za 500 let). Historicky masová
  škola přišla až s tiskem; kde byla psaná norma zmrazená (latina,
  klasická arabština), učila se jen elita a lidová řeč se měnila dál.

### Stav M6b (2026-10-28)

Splněno, testy v `tests/v2/test_v2_m6b_gate.py` a `test_v2_society.py`.
Světy M1 až M4b a S2 dávají bitově stejnou historii jako před M6b. Přechod
jazyka (S3) se změnil záměrně, protože demografie se teď počítá ze sítě.

- **Metrika 9 (Séguyho zákon)** vzniká v plném modelu na mapě sama: mřížka
  5×5 vesnic s morfologií a významem po 2 500 letech, seedy 2–4, korelace
  vzdálenosti nářečí se zeměpisnou 0,78–0,84 a logaritmus sedí lépe než
  přímka (R² 0,68–0,73 proti 0,61–0,70). Očekávané selhání z M1 mělo dvě
  příčiny: řadu vesnic (1D), kde teorie (stepping-stone model, Malécot a
  Kimura) dává lineární růst až do nasycení, a svět M1, kde má inovace
  stejnou výhodu všude (`Appeal`), takže její vlna projde celým územím.
  Test v bráně M1 je proto nahrazen testem v bráně M6b.
- **Tlak místní identity** (výhoda varianty častější doma než u sousedů,
  Labov a Milroy) byl vyzkoušen a vyřazen. Při síle do 0,2 průběh nezmění, od
  0,35 rozbije kontinuum (sousední vesnice se liší víc než vzdálené) a pro
  Séguyho zákon není potřeba.
- **Migrace** (`World.migration`, podíl lidí, kteří se za generaci
  přestěhují): z každé skupiny odchází k sousedům úměrně síle vazby,
  velikosti a prestiži cíle (Ravenstein 1885). Populace se nemění (úbytek
  doplní přirozený přírůstek); příchozí určují `immigration`, a tím podíl L2
  mluvčích. Ve scénáři s městem, čtyřmi městečky a osmi vesnicemi (migrace
  0,1, seed 1) má město 13 % L2 mluvčích, městečka 10 %, vesnice 1–7 %.
  Korelace podílu L2 s populací +0,89, složitosti s populací −0,64 a
  s podílem L2 −0,70: hypotéza jazykové niky (Lupyan & Dale 2010) vzniká bez
  ručního nastavení.
- **Události**: `Migration` (přesun do sídla, nebo založení nového), `Conquest`
  (elita s prestiží 2 a dálkovou vazbou domů), `War` (oslabí vazby přes
  frontu, ztráty), `Epidemic`, `StateCollapse` (zruší dálkové vazby, školy
  a většinu gramotnosti) a dříve `Contact`, `Border`.
- **Vitalita jazyka** (Giles, Bourhis & Taylor 1977) v přechodu: status
  z prestiže, **demografie ze sítě** (podíl mluvčích cílového jazyka mezi
  lidmi, se kterými komunita mluví, vážený silou vazby, ne jen podíl uvnitř
  komunity) a **loajalita** (přechod se zpomalí na `1 − loyalty`).
- **Domény**: `LanguageShift(domain="public")` znamená kód jen pro trh nebo
  úřad. Dvojjazyční se neodečtou z komunity, děti se doma učí dál svůj
  jazyk a veřejný kód se každá generace učí znovu v dospělosti (podíl L2 je
  stále 1). Výsledek je stabilní dvojjazyčnost.

Naměřeno (seedy 1 a 2, není-li uvedeno jinak):

- **Superstrát**: elita (sto lidí, prestiž 2) mezi čtyřmi vesnicemi poddaných
  přejde na jejich jazyk za 150–500 let (seed 1: 250 let, řádově jako
  Normané v Anglii). V jazyce poddaných zůstane 4–6 slov elity ze 154 a
  stavba elity jen 0,01; superstrát je slovní, opak substrátu v S3.
- **Stabilní dvojjazyčnost**: pohraniční vesnice s třetinou dvojjazyčných
  zůstane po 1 500 letech celá u svého jazyka (přes 80 % vlastních slov),
  výpůjčky z jazyka trhu přibývají postupně.
- **Loajalita** (S3, seed 1): bez ní přejdou vesnice v letech 1600–1700, s
  0,6 v letech 1725–1900, s 0,9 přejde do roku 2500 jen pohraniční.
- **S3 s novou demografií**: pohraniční vesnice přejde 100 let po kontaktu
  (dřív 200), vnitrozemí 175–200 let po kontaktu.
- **Fergusonova diglosie** (`Schooling(diglossic=True)`): každá vesnice
  dostane skupinu veřejné domény, která mluví psaným kódem naučeným ve škole
  (vysoká varieta, ~ škola × populace lidí), s interferencí z lidové řeči.
  Lidová řeč školou neprochází, jen čtením přejímá učená slova. Vysoké
  variety sousedních vesnic spolu mluví. Školní výuka tlumí interferenci o
  80 % (`SCHOOL_CORRECTION`): bez toho se vysoká varieta během pár století
  přiblížila lidové řeči víc než psanému kódu. Naměřeno (S4 s diglosní
  školou v roce 1500, seedy 1 a 2): vysoká varieta je od psaného kódu
  0,02–0,06 a vzdaluje se jen pomalu, lidová řeč 0,13–0,18 a dál se
  vzdaluje, vzdálenost vysoké a lidové variety 0,10–0,13. Při standardizaci
  (S4 s tiskem) splyne lidová řeč s psanou na 0,01.
- **Náboženská změna** (`ReligiousChange`): skupiny dostanou liturgický kód
  (psaný kód, často cizího jazyka) a kanál liturgie (váha 0,1 × podíl
  věřících, jen slova, vzácné pojmy víc než základní). Volitelně je propojí
  slabé vazby církevní správy. Naměřeno (čtyři vesnice, liturgie v cizím
  jazyce od roku 500, podíl věřících 0,3, seedy 1 a 2): za 1 500 let 2–6
  učených slov v krajních vesnicích, průměrná frekvence jejich pojmů 0,07–0,14
  (všech pojmů 0,35), adaptovaných do hlásek příjemce; bez náboženství
  žádná.
- **Veřejná doména se nepočítá do dialektů ani jazyků**: kód trhu, úřadu
  nebo školy je druhý jazyk, jazyk komunity určuje řeč z domova. Konstrukce původního jazyka ve vnitrozemí
  0,49–0,86, na hranici 0,23–0,42, v jádru většinového jazyka 0,01–0,03; práh
  brány M5 je proto 0,4.

### Stav M6c (2026-10-28)

Splněno, testy v `tests/v2/test_v2_m6c_gate.py` a `test_v2_observe.py`.

- **Vzdálenost kódů** (`observe.code_distances`): variační vzdálenost slov
  a konstrukcí plus **tvary příbuzných slov**. U pojmu, kde mají oba kódy
  stejné převládající slovo, se přičte normalizovaná editační vzdálenost
  dnešních tvarů; záměna hlásky stojí podíl odlišných rysů PanPhonu (šest
  rysů = plná cena), takže *t → d* je levnější než *t → a*. Vše se dělí
  počtem lexikálních proměnných, svět bez tvarů (M1) má vzdálenost beze
  změny. Zvukové procesy se nepočítají zvlášť; jejich výsledek je v tvarech.
- **Hystereze jazyků**: dvojice skupin, která byla jedním jazykem, se
  rozdělí až nad prahem + 10 %, oddělená se spojí až pod prahem − 10 %. V
  kontinuu 5×5 vesnic (3 000 let, seedy 2 a 3) klesl počet zpětných
  sloučení z 10–11 na 0–1 a rozštěpení z 33–35 na 19–23.
- **Strom jazyků** se známou historií (`known_tree`: řada devíti vesnic, C
  oddělena hranicí v roce 300, A a B v roce 1800): ve třech seedech vždy
  vyjde ((A, B), C), C se oddělí 1 600–2 000 let po hranici a B od A 1 000–1 700
  let po druhé hranici, právě dvě rozštěpení a žádný zánik linie. Do
  jazykového prahu 0,25 trvá oddělení zhruba tolik, kolik odpovídá asi 70 %
  sdílené základní slovní zásoby.
- **Export pro UI** (`export.export`, `write_json`, formát `cee-v2/1`): území,
  skupiny (poloha, populace, jazyková linie kódu i pozorovaný jazyk, podíl
  L2, gramotnost, škola, liturgie), vazby, snímky dialektů a jazyků, strom
  linií (rodič, začátek, konec, skupiny), dnešní slova každé skupiny (tvar
  IPA, lexém, jazyk původu, výpůjčka, původ: zděděné, posun, odvozenina,
  složenina, gramatikalizace…), gramatika skupin a události pro časovou osu.
- **Rozdělení testů**: brány milníků (`*_gate.py`) mají značku `slow`.
  Rychlá sada `pytest -m "not slow"` trvá asi 17 s, celá sada asi 8 minut.
- **Výkon** (bez změny výsledků, ověřeno otisky logu): zapamatovaná
  aplikace zvukových procesů, index kořen → pojmy pro frekvenci užití a
  index odvozenin pro zpětné tvoření zrychlily plný model asi o 27 %.
  Rozpočet ale plný model nesplňuje: údolí (50 skupin, 2 000 let) 67 s proti
  rozpočtu 5 s, region odhadem 280 s proti 60 s (100 skupin za 1 000 let:
  47 s). Svět jen se slovy (M1) zvládne údolí za 1,6 s. Profil je teď
  plochý (miliony drobných operací nad tvary slov); další řádové zrychlení
  potřebuje jiné uložení tvarů nebo paralelní běh nezávislých oblastí.

## Známé mezery a kam patří

Sepsáno 2026-10-28 při revizi plánu po M3.

| Mezera | Kam |
|---|---|
| Přízvuk jako proměnná (změna pravidla přízvuku), délka a kompenzační prodloužení, tónová perturbace → tonogeneze | doplněk M2 (po M3b) |
| Sporadické změny: metateze, disimilace, nepravidelné zkracování velmi častých slov | doplněk M2 |
| ~~Frekvence užití se nevyvíjí~~ | vyřešeno v M3b |
| ~~Rodokmen slova (původ)~~ | původ slova je v exportu (M6c); historie tvarů viz níže |
| Spuštění enginu mimo testy: CLI, API, převod projektu z UI na svět v2 (export do JSON už je) | před napojením UI |
| ~~`AGENT.md` a `CURRENT_STATE.md` engine v2 nezmiňují~~ | vyřešeno po M3b |
| ~~Konverze mezi slovními druhy~~ | vyřešeno v M4 |
| ~~Exaptace a jazyky bez některých kategorií~~ | vyřešeno v M4b |
| Další funkce katalogu: vid, shoda, osoba, rod a jmenné třídy; víc dárců exaptace | rozšíření katalogu (data), kdykoli |
| Člen (a obecně funkce `zero`) do 3 000 let vznikne ve všech jazycích; chybí tlak, který by jazyk bez kategorie dlouho udržel (např. norma) | M6 (instituce), tempo M7 |
| Přirozená četnost eroze konkrétní koncovky je nízká (zvukové inovace se dělí mezi stovky kandidátů); analytizace je proto doložena kontrolovanými pokusy | M7 (kalibrace tempa zvukových změn) |
| Malé izolované komunity podle Trudgilla hromadí morfofonologickou složitost díky husté síti silných vazeb, která udrží i neobvyklé změny. Model to nereprodukuje: alternace kmene roste s velikostí skupiny, protože velká skupina účinněji přijme přirozené zvukové změny. Nepravidelnost koncovek už velikost sleduje správně. Tlak místní identity (M6b) to nevyřešil | M7 (tempo a váhy zvukových změn), případně výzkum |
| ~~Stabilní dvojjazyčnost a superstrát~~ | vyřešeno v M6b (domény, demografie ze sítě) |
| Prestižní asymetrie výpůjček je slabá: ve stabilní dvojjazyčnosti si i město s prestiží 1 vypůjčí od vesnice s prestiží 0,5 skoro stejně slov, jako vesnice od něj (vážení prestiží jen na `α` = 1) | M7 |
| ~~Náboženská změna~~ | vyřešeno v M6b (`ReligiousChange`) |
| Migrace nemění velikost sídel (populace jsou stacionární) | podle potřeby UI |
| Výpůjčka nového pojmu nebo kategorie (změna `Výpůjčka`): všechny jazyky mají stejnou sadu pojmů | až budou pojmy přibývat (M6, události) |
| Příbuzné jazyky se po rozpadu mísí bez filtru, protože mají stejnou linii; filtr by měl záviset na pozorované vzdálenosti | M6 (linie jazyků) |
| Konstanty kontaktu (filtry, váha interference, rychlost přechodu) jsou odhad | M7 |
| ~~Stabilní diglosie (Ferguson 1959)~~ | vyřešeno v M6b (`Schooling(diglossic=True)`) |
| Učené výpůjčky se vracejí jako stará slova s dnešní výslovností; skutečné učené dublety (*fragile* vedle *frêle*) mají tvar psaného kódu | M6c nebo později |
| Pravopisná výslovnost a revize pravopisu: psané tvary slov se nemění ani s tiskem | později |
| CI je červené kvůli 48 chybám mypy v legacy kódu | samostatná úklidová práce |
| Výkon plného modelu je 5–13× nad rozpočtem (údolí 67 s místo 5 s, region odhadem 280 s místo 60 s); profil je plochý | samostatný výkonový milník: sloupcové uložení tvarů, paralelní běh propojených komponent, případně Numba |
| Sousední vesnice se v plném modelu liší příliš (kontinuum 5×5, 3 000 let: sousedé 0,29, nejvzdálenější 0,38; v nářečních atlasech sousedé asi 0,05–0,15). Prahy dialektu a jazyka proto dávají skoro každou vesnici jako jazyk. Místní mísení je slabé proti tempu změn | M7 (otevřenost, tempo změn, prahy dialektu a jazyka) |
| Rodokmen slova: export nese původ dnešního slova, ne historii jeho tvarů | později (snímky tvarů v exportu) |

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
