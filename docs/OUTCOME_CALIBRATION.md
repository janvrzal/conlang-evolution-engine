# Outcome calibration

CEE může vytvořit popis **výsledných vlastností současných jazyků**. Nejde o
rekonstrukci jejich historických změn; jde o referenční rozmezí pro volitelný
earth-like režim a o cíl pro budoucí citlivostní experimenty.

## Vstup

Příkaz přijímá místní CLDF-like soubory:

- `languages.csv`: povinné `ID`; volitelné `Family`, `Macroarea` a
  `Glottocode`.
- `forms.csv`: povinné `Language_ID`; jedna z forem `Segments`, `Value` nebo
  `Form`; pro proxy homofonie volitelný `Parameter_ID`.
- `phoible.csv`: volitelný zdroj skutečných fonémových inventářů. Připojí se
  přes `Glottocode`; marginální fonémy se do velikosti inventáře nepočítají.

Příklad nad lokálně staženým Lexibank a PHOIBLE:

```bash
cee calibrate outcomes \
  --forms /data/lexibank/forms.csv \
  --languages /data/lexibank/languages.csv \
  --phoible ~/.cee/phonology/phoible/data/phoible.csv \
  --out /data/outcomes/lexibank-earth.json
```

Zdrojová data se neukládají do repozitáře. Výstup obsahuje SHA-256 všech
vstupů, seed a počet bootstrapových opakování.

## Metriky a nejistota

Metriky se počítají na úrovni jednotlivého jazyka a pak agregují třikrát:
globálně, podle makroregionu a podle rodiny. Interval 95 % je cluster
bootstrap: pro globální a regionální profil se resamplují rodiny, pro rodinný
profil jazyky. Interval se neuvádí, pokud skupina nemá alespoň dva klastry.

První sada zahrnuje průměrnou a mediánovou délku segmentované formy, velikost
inventáře ve wordlistu, průměrnou délku nejdelšího souhláskového shluku,
podíl kodových segmentů, wordlistovou proxy homofonie a — je-li dodán PHOIBLE
— medián velikosti jeho nemarginálních inventářů pro daný glottocode.

Wordlist není úplný lexikon ani frekvenční korpus. Proto wordlistová homofonie
není funkční zátěž a nelze z ní odvozovat komunikační rychlost. Tyto limity jsou
součástí výstupu a nesmějí se skrýt v jedné „plausibility“ známce.

## Použití při kalibraci

Outcome profil neurčuje jedinou správnou sadu vah. Více kombinací procesů může
vést ke stejné délce slov či podobnému inventáři. Kalibrátor proto má hledat
množinu scénářů, jejichž opakované simulace vstoupí do zvolených intervalů.
Rodinný profil se vzorkuje před simulací jako sdílený styl větví; nemění se
zpětně podle výsledku jednoho běhu.

První automatický krok je makro-hledání nad konkrétním scénářem. Pro vzorkované
kombinace `change_rate`, `coda_erosion` a `deletion_rate` opakuje simulaci přes
více seedů, změří listové jazyky a řadí kandidáty podle vzdálenosti od intervalů
vybraného outcome profilu:

```bash
cee calibrate outcome-search \
  --target /data/outcomes/lexibank-earth.json \
  --target-kind macroarea --target-id Eurasia \
  --topology /data/scenario.yaml \
  --proto /data/proto.csv \
  --preset src/cee/data/presets/fantasy_preset.yaml \
  --out /data/outcomes/eurasia-candidates.json
```

Tento první search hledá pouze makro-parametry a je určen pro dostatečně velký,
segmentovaný protolexikon. Nelze z něj vyvozovat „správnou historii“ ani jej
spolehlivě vyhodnotit nad ukázkovým slovníkem s několika slovy. Další vrstva
rozšíří hledání o sdílené rodinné váhy schémat a nezávislý holdout scénář.
