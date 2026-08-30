# Audit zdrojů směrované historické změny

Stav: 2026-08-30. Tento seznam rozlišuje data vhodná pro globální metriky od
dat použitelných jako distribuované váhy směrovaných schémat.

| Zdroj | Licence / původ | Co umí | Rozhodnutí |
| --- | --- | --- | --- |
| GLED 20221127 | CC BY 4.0 | 262 859 forem, kognátní sady a fonologická zarovnání napříč rodinami | Přijat pro **nesměrované** globální korespondence; není zdrojem `A → B`. |
| BDPROTO 1.1 | CC BY 4.0 | Inventáře rekonstruovaných a starých jazyků | Budoucí kontrola vstupních protoinventářů, ne zdroj změn. |
| PILA | dataset je metodicky výborný, ale publikace uvádí CC BY-NC 4.0 a vstupy zahrnují Wiktionary CC BY-SA | Proto-italické etymony a latinské reflexy | Nepřijato pro distribuované váhy. Může sloužit jen jako oddělený nekomerční evaluační benchmark po právní kontrole. |
| JAMBU | historické CLDF, ale zdrojová dokumentace uvádí části získané jen pro akademické účely; žádná jednoznačná redistribuční licence pro odvozené váhy | protoformy, reflexy a vztahy | Nepřijato bez výslovného licenčního souhlasu. |
| Index Diachronica (kompletní) | CC BY-NC-SA | explicitní změny | Nepřijato pro placený produkt. |

## Závěr

Pro globální **směr** změny dosud nemáme dostatečně široký, licenčně čistý a
strojově čitelný korpus. Správný další krok není hádat směr z GLED, ale vytvořit
vlastní kurátorskou sadu: minimálně pět genealogicky nezávislých rodin,
explicitní protoforma → reflex, prostředí, reference a licence pro každý řádek.
Ta se pak přímo načte přes `cee calibrate global`.
