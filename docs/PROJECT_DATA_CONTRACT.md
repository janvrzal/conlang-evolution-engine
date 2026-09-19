# Projektová data: stabilní kontrakt V3

Každý uložený projekt CEE má obálku s `schema_version` a `data`. Aktuální
verze je **V3**. Projekt se při načtení může převést v paměti, ale soubor se
nikdy automaticky nepřepisuje; přepis vznikne až následujícím explicitním
uložením uživatelem.

## Stabilní tvar

Názvy veřejných polí používají camelCase, shodně s UI. `data` obsahuje:

| Sekce | Význam |
| --- | --- |
| `generatedProtoLexicon` | záznamy `{ id, ipa }`, volitelně polysemie, frekvence a gramatické rysy |
| `timeSteps`, `snapshots` | vzestupná absolutní časová osa a stav uzlů/hran v každém roce |
| `communities`, `varieties`, `socialTies` | sociální skupiny, variety a jejich vazby |
| `polities`, `tradeRoutes`, `historicalEvents` | státy, obchodní trasy a datované události |
| `languageNames` | endonyma/exonyma, platnost a zdroj změny |
| `simulation` | seed, profil, empirická fonologie a kalibrace |
| `savedRun` | volitelný identifikátor uloženého běhu |
| `mapBackground` | volitelný rastrový mapový podklad |

Každý uzel má `id`, `type: "language"`, `position` a `data`; dědičná hrana
má `type: "straight"`, kontaktní `type: "contact"`. U objektů, které ovlivňují
simulaci, jsou povinné identifikátory a hodnoty striktně kontrolované.
Například roky jsou v rozsahu −100 000 až 100 000, podíly komunit a intenzity
států/trasy jsou 0 až 1 a kontaktní intenzita hrany je 0 až 100.

## Integrita a kompatibilita

Reference na jazyky, komunity, státy a události se ověřují při načtení,
ukládání i před spuštěním simulace. Chyba uvádí konkrétní chybějící ID.
Neznámá pole na kořeni `data` se uchovávají pro novější klienty; neznámá pole
uvnitř kritických objektů se odmítají, aby překlep neměnil význam simulace.

Historické aliasy `schemaProfileId`, `empiricalPhonology`, `calibration`,
`simulationRunId` a `simulationRunAt` jsou ve V3 migrovány do `simulation`
a `savedRun`. Zůstanou fyzicky zachované jako dopředně kompatibilní metadata,
ale simulátor čte pouze kanonické V3 sekce.

## Migrace

Migrace jsou čisté kroky a nemutují vstup:

1. **V1 → V2:** původní normalizace protolexikonu, osy a snímků.
2. **V2 → V3:** explicitní prostorová, historická, sociální a simulační data.

Projekt s vyšší verzí než podporovanou CEE se odmítne před jakýmkoli zápisem.
Nová migrace se přidává pouze tehdy, když se mění význam uložených dat, nikoli
pro kosmetickou úpravu serializace.

## Transportní aliasy API

`POST /api/simulate_dynamic` dočasně přijímá také dřívější transportní tvar
(`nodes`/`edges` nebo seznam snímků). Server jej nejprve bez mutace přeloží na
V3 a validuje. Tyto aliasy nejsou součástí stabilního persistentního formátu
a nesmějí být předány enginu bez explicitního překladu.
