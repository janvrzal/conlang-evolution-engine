# Audit zdrojů směrované historické změny

Stav: 2026-10-28 (doplněno pro engine v2). Tento seznam rozlišuje data
vhodná pro globální metriky od dat použitelných jako distribuované váhy
směrovaných schémat.

| Zdroj | Licence / původ | Co umí | Rozhodnutí |
| --- | --- | --- | --- |
| GLED 20221127 | CC BY 4.0 | 262 859 forem, kognátní sady a fonologická zarovnání napříč rodinami | Přijat pro **nesměrované** globální korespondence; není zdrojem `A → B`. |
| BDPROTO 1.1 | CC BY 4.0 | Inventáře rekonstruovaných a starých jazyků | Budoucí kontrola vstupních protoinventářů, ne zdroj změn. |
| PILA | dataset je metodicky výborný, ale publikace uvádí CC BY-NC 4.0 a vstupy zahrnují Wiktionary CC BY-SA | Proto-italické etymony a latinské reflexy | Nepřijato pro distribuované váhy. Může sloužit jen jako oddělený nekomerční evaluační benchmark po právní kontrole. |
| JAMBU | historické CLDF, ale zdrojová dokumentace uvádí části získané jen pro akademické účely; žádná jednoznačná redistribuční licence pro odvozené váhy | protoformy, reflexy a vztahy | Nepřijato bez výslovného licenčního souhlasu. |
| Index Diachronica 10.2 (kompletní) | CC BY-NC-SA 3.0 | explicitní změny a série mezi konkrétními jazyky | Nepřijato pro distribuované váhy ani placené rozhraní bez výslovného přelicencování držitelem práv. Lze jej držet odděleně jako nekomerční auditní referenci. |
| IE-CoR (Heggarty a kol. 2023), `lexibank/iecor` | CC BY 4.0 | 160 indoevropských jazyků, 170 pojmů, segmenty CLTS, kognáty, výpůjčky; mj. latina a 20 románských variet včetně staré francouzštiny, staré španělštiny a dalmatštiny | **Přijato** jako validační data scénáře S5 a jako zdroj směrovaných korespondencí latina → románské jazyky po zarovnání a kurátorské kontrole. |
| ACD (Blust, Trussel, Smith), CLDF v1.2 | CC BY 4.0 (dle acd.clld.org) | praaustronéské rekonstrukce a reflexy | **Přijato** jako druhá nezávislá rodina pro směrované korespondence po kurátorské kontrole. |
| ABVD (Greenhill a kol. 2020), `lexibank/abvd` | CC BY 4.0 | základní slovní zásoba austronéských jazyků, místy protoformy | Doplňkový zdroj k ACD. |
| Mixtec Sound Change Database 2.0 (Auderset a kol. 2025) | CC BY-SA 4.0 | kódované segmentové a tónové změny ve 105 mixtéckých varietách | Do právního posouzení nepřijato (SA). Metodicky cenné jako vzor kódování změn včetně tónu. |
| Hruschka a kol. 2015, CLDF | CC BY-NC 4.0 | pravidelné zvukové změny jako události (turkické jazyky) | Nepřijato (NC). |
| UNIDIA (Ben Hamed & Flavier 2009) | veřejně nedostupná | ~3 750 změn ve ~190 jazycích | Nedostupné; jen literatura. |

## Závěr

Pro globální **směr** změny dosud nemáme dostatečně široký, licenčně čistý a
strojově čitelný korpus. Správný další krok není hádat směr z GLED, ale vytvořit
vlastní kurátorskou sadu: minimálně pět genealogicky nezávislých rodin,
explicitní protoforma → reflex, prostředí, reference a licence pro každý řádek.
Historické CLDF s `Origin_ID` lze nejdřív převést na auditní frontu příkazem
`cee calibrate candidates`; až lidsky ověřené řádky se pak načtou přes
`cee calibrate global`.

### Doplnění 2026-10 (engine v2)

Rešerše nenašla žádný nový otevřený globální katalog. Engine v2 proto
kombinuje autorský typologický prior (vlastní, s citacemi literatury) s
empirickou korekcí z IE-CoR a ACD; viz
[`engine-v2/05-specifikace.md`](engine-v2/05-specifikace.md#zdroj-vah-zvukových-změn).
Další rodiny se mají hledat mezi lexibank datasety s protoformami; licenci je
nutné ověřit u každého zvlášť v jeho `cldf-metadata.json`.

Pozor na právo k databázím v EU: i u zdroje, jehož jednotlivá fakta nejsou
chráněná autorským právem, je zakázané vytěžit jeho podstatnou část bez
svolení. Autorský prior se proto píše z obecné literatury, nikoli přepisem
Index Diachronica.
