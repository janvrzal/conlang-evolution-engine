# Značka CEE – pravidla (pro lidi i agenty)

## Značka
- Měkký rodokmen ve tvaru E: kořen vlevo, dělení křivkami S, tři různě dlouhá ramena.
- Vždy jeden souvislý vyplněný tvar, jedna barva. Žádná kolečka, obrysy, stíny, průhlednost ani přechody.
- Neměnit proporce, neotáčet, neskládat z oddělených tahů (vznikají bílé švy).

## Ochranná zóna a velikost
- Zóna kolem značky = x, kde x je tloušťka kmene (≈ 18 % šířky značky).
- Mezera značka–„CEE“ v nápisu = 1,5 x.
- Minimum 16 px; pod 24 px bez nápisu.

## Barvy (Poloostrov)
| Token | Hex | Použití |
|---|---|---|
| inkoust | #1b2830 | značka a nápis na světlém |
| pevnina | #fbfbf9 | světlý podklad |
| papír | #ecdfc5 | značka na tmavém |
| noc | #17202a | tmavý podklad |
| břidlice | #56656e | podtitul, popisky |
| mlha | #c3ccd0 | doprovodný strom, šipky |
Červená #ae2a1f do značky nepatří (jen varování a chyby).

## Písmo
- Nápis: Charis (OFL, desktop/static/fonts). „CEE“ regulár, prostrkání 0,08 em; „Conlang Evolution Engine“ kurzíva.
- V SVG souborech je text převedený na křivky. UI aplikace dál používá Piazzollu.

## Světlá / tmavá
- Na světlém podkladu inkoust, na tmavém papír. Favicon a README se přepínají samy.
- Ikona aplikace: světlá dlaždice (macOS i Windows; na Windows nikdy bez dlaždice).

## Pohyb
- Úvodní animace: nádech → růst rodokmenu, kamera se oddaluje a předbíhá růst → část větví vymře (zúžením) → vlna → nápis. ~4,5 s.
- Čekání na dosimulování: mřížka 3×3 teček pulzující vlnou + „Simuluji generaci N…“.
- Strom = jeden <path> přepočítaný v každém snímku. Žádná průhlednost. prefers-reduced-motion → rovnou konečný stav.

## V aplikaci ($lib/ds)
- Značku vkládat z `svg/cee-mark-currentColor.svg` (barva z `color`).
- Ikony pojmů enginu jsou v `$lib/ds/Icon.svelte` (zdroj `ikony/icon-paths.ts`, sprite `ikony/icons-sprite.svg`).
- Referenční kód animací: `animace/splash.html` (úvodní), `animace/loader.html` (čekání) a `animace/states.html`
  (dosimulováno, chyba, prázdný projekt, ikona v Docku); jádro je v `nastroje/tree-core.js` a `nastroje/states-core.js`.

## Kde co je
| Cesta | Obsah |
|---|---|
| `svg/` | značka, nápisy, favicon, hlavička README, náhled pro sdílení, ikona dokumentu, zdroje ikon aplikace |
| `png/` | rastrové verze 1024 px a `social-preview.png` (GitHub → Settings → Social preview) |
| `splash-light.gif`, `splash-dark.gif` | úvodní animace pro README |
| `desktop/src-tauri/icons/` | ikony aplikace (macOS `.icns` s vlastními 16 a 32 px, Windows `.ico`) |
| `desktop/src-tauri/installer/` | pozadí okna DMG a obrázky pro instalátory NSIS a WiX |

## Přegenerování
- SVG sady: `node nastroje/gen.mjs <výstup> nastroje/text.json`. Text převádí na křivky `nastroje/outline.py` (potřebuje `fonttools` a `brotli`).
- Animace: `node nastroje/anim.mjs <výstup> nastroje/text.json` vytvoří `splash.html` a `loader.html`.
- GIF: `node nastroje/frames.mjs <stránka> <složka> light 25`, pak `python nastroje/mkgif.py <složka> <výstup>` (Pillow).
- Ikony aplikace: `npx tauri icon png/icon-windows-1024.png`; `.icns` z `png/icon-macos-light-1024.png`, malé velikosti pro macOS ze `svg/icon-macos-small.svg`.
- Boční panel instalátoru obsahuje text „verze 0.1.0“, při novém vydání ho přegeneruj.
