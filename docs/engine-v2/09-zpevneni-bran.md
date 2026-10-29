# Zpevnění milníkových bran enginu v2

Navazuje na dokončenou fázi 5 M6e (`f3a9dfd`, deník `08-davkova-inovace.md`)
podle zadání `docs/engine-v2/zadani-zpevneni-bran.md`.

Ve fázi 5 ukázal přechod z `PCG64.poisson` na `hash_poisson`, že několik
jednoseedových milníkových bran v `tests/v2/*_gate.py` prochází i na původním
enginu pouze v 30–80 % seedů, a doménová konstanta `"innovation-change-34"`
byla zvolena účelově tak, aby všechny brány prošly. Před kalibrací M7 je proto
nutné:

1. přepnout doménovou konstantu klíče inovací na neutrální `"innovation-change"`,
2. změřit míru průchodu všech stochastických tvrzení v `tests/v2/*_gate.py` na
   nezávislé řadě seedů `101..120`,
3. křehké brány (`10–18/20`) převést na agregaci `k` z `N` na souvislé řadě
   seedů `1..N` s prahem odvozeným z dolní meze Wilsonova 95% intervalu,
4. slabé brány (`< 10/20`) nahlásit uživateli k rozhodnutí a u převedených bran
   ověřit negativní kontroly se vypnutým mechanismem.

## Krok 1: neutrální konstanta a nové otisky

V `src/cee/v2/simulation.py` byla zavedena modulová konstanta
`_INNOVATION_CHANGE_DOMAIN = "innovation-change"` a nahradila účelový řetězec
`"innovation-change-34"` v `Simulation._configure` i v kusové variantě
`Simulation._innovate_with` (v zadání zmíněné `_apply_innovations` dostává už
vylosovaný počet `count` a volá `generator(..., "innovation", ...)`).

### Nové referenční otisky (`v2_digests.py`)

Měřeno sériově (`.venv/bin/python scripts/v2_digests.py`, Python 3.11.9,
NumPy 2.4.6) bez souběžné zátěže:

| Scénář | Čas (s) | Předchozí otisk (`f3a9dfd`) | Nový otisk (`innovation-change`) |
|---|---:|---|---|
| `phonology` | 0,2 | `91e46de9b912a8847fb7b1595c007c18c5ff0bbf4ca52eb414980df7f2bad4f4` | `8d7971c1a6afe5f6b8ca9f33919b8b3e2e929d56832ae4e04c738efa18c53840` |
| `morphology` | 0,4 | `7ea78265d605f629dab2edc1f90e7d594d47fde4215d8392e5c3472bb9d5fa87` | `3567be70a272f42662ecd44838079d33abf953d090c59a9a2da4079467933a06` |
| `syntax` | 0,8 | `9e1abfe36cce76d10594a7a5087ae61f5f82e0ab6f2b94bae56897e75625dd0c` | `eefb5db5be7bfac8284c400b7a0ebc81fe4a65c04325aaafa9b1cdb39d50fc38` |
| `grid-5x5` | 2,5 | `36767c976a7af2c7c989dce2e37b86a582ee97233c2c4cce0e5fc3bde5f2b9bf` | `a6aa9a33f1a416e33144a0235d19194c442bb27ede6f966c5092a7b7342b08c0` |
| `shift` | 0,8 | `1bfbc2a466d61db09d5762ff2d718069adde6da343eb289bbffee5ce44de36eb` | `47d69ad8a511366b2dedba0a9c30550c0c1d0045aa24ce3eafbdde03663da71a` |
| `island-city` | 0,6 | `3577e966ab9e39320f55688982c42e0d95b9ccfb0b6eb37b6388d937bf20c29e` | `a082c2463488378f975fc050a9265f62856e716d6b1dd0b4d813f7d5323ab2cf` |
| `valley-50` | **25,4** | `6246ebdba75988f78e32d386c320bfd6d6842f6dc09d833537b05ef94544a08d` | `02ccc3819e155cff096d791466f3dcdab88142a4e31e9b1920f92fc9898b1272` |

Rychlá sada testů (`pytest -m "not slow" -q`: 585 testů za 32,8 s), `ruff` i
`mypy` procházejí bez chyb. Pomalé stochastické milníkové brány mohou po této
změně proudu náhody padat – to je očekávané a řeší je kroky 2–4.

## Krok 2: audit všech stochastických tvrzení (`101..120`)

Logika spouštění scénářů a vyhodnocení tvrzení byla vytažena do sdílených funkcí
`run_*` a `check_*` přímo v jednotlivých souborech `tests/v2/test_v2_m*_gate.py`
(beze změny jediného vnitřního prahu, počtu let, velikosti scénáře či dnešních
seedů). Statistické funkce (`wilson_interval`, `binomial_cdf_lt`, `threshold_k`,
`classify_rate`, `passes`, `assert_k_of_n`) jsou v `tests/v2/gate_checks.py`
a pokrývají je jednotkové testy v `tests/v2/test_v2_gate_rates.py` (včetně AST
kontroly úplnosti: ze 62 testovacích funkcí v `*_gate.py` je 52 stochastických
bran v registru a 10 deterministických/výkonových testů vyloučených podle zadání).

Skript `scripts/v2_gate_rates.py` spustil sériově bez souběžné zátěže všech
30 sdílených dávek scénářů na nezávislé řadě 20 seedů `101..120` (u dvou
souborových 3seedových bran v M2 – `metrika_6` s prahem `total >= 30` a párové
`jazyky_z_ruznych_seedu_se_lisi` – na 20 disjunktních trojicích seedů
`101..160`). Celkový čistý čas simulací auditu byl **2 074,4 s** (34,6 min).

### Tabulka auditu 52 stochastických bran

| Brána | Seedů dnes | Průchod | Wilson 95 % | Zařazení | k (N=10) | k (N=5) | Čas/seed (s) |
|---|---:|---:|---:|---|---:|---:|---:|
| `test_v2_m1_gate.py::test_s1_kontinuum_je_plynule_a_vzdalenost_roste_se_vzdalenosti` | 1 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 0.99 |
| `test_v2_m1_gate.py::test_s1_hranice_vytvori_svazek_izoglos` | 1 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 0.77 |
| `test_v2_m1_gate.py::test_metrika_7_usalene_zmeny_se_siri_po_s_krivce` | 1 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 0.99 |
| `test_v2_m1_gate.py::test_metrika_8_vetsina_inovaci_zanikne` | 1 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 0.99 |
| `test_v2_m1_gate.py::test_velka_souhrnna_skupina_driftuje_mene_nez_mala_vesnice` | 1 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 0.05 |
| `test_v2_m2_gate.py::test_metrika_3_delka_slov_zustava_v_pasmu` | 3 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 3.63 |
| `test_v2_m2_gate.py::test_metrika_4_inventare_lezi_v_pasmu_realnych_jazyku` | 3 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 3.63 |
| `test_v2_m2_gate.py::test_metrika_5_homofonie_zustava_nizka` | 3 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 3.63 |
| `test_v2_m2_gate.py::test_metrika_6_ustalene_zmeny_odpovidaji_prioru_a_nejsou_jednostranne` | 3 (soubor) | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 11.40 |
| `test_v2_m2_gate.py::test_jazyky_z_ruznych_seedu_se_lisi` | 3 (soubor) | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 11.40 |
| `test_v2_m2_gate.py::test_zvukove_zmeny_se_siri_arealne_a_maji_male_vyjimky` | 3 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 3.63 |
| `test_v2_m3_gate.py::test_sturtevantuv_paradox_zvuk_tvori_nepravidelnost_analogie_ji_opravuje` | 2 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 4.98 |
| `test_v2_m3_gate.py::test_morfologizace_vznikne_sama` | 2 | 19/20 | [0.764, 0.991] | robustní | 4 | 1 | 4.98 |
| `test_v2_m3_gate.py::test_produktivni_vzor_se_siri_a_caste_slova_si_drzi_nepravidelnost` | 2 | 19/20 | [0.764, 0.991] | robustní | 4 | 1 | 4.98 |
| `test_v2_m3_gate.py::test_analogie_zasahuje_spis_vzacna_slova` | 2 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 4.98 |
| `test_v2_m3_gate.py::test_zvukove_metriky_drzi_i_s_paradigmaty` | 2 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 4.98 |
| `test_v2_m3b_gate.py::test_metrika_1_retence_zakladni_slovni_zasoby_v_pasmu` | 2 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 3.80 |
| `test_v2_m3b_gate.py::test_metrika_2_caste_pojmy_se_nahrazuji_pomaleji` | 2 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 3.80 |
| `test_v2_m3b_gate.py::test_nova_slova_maji_doloditelny_puvod` | 2 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 3.80 |
| `test_v2_m3b_gate.py::test_erodovana_slova_se_nahrazuji_casteji` | 1 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 0.93 |
| `test_v2_m3b_gate.py::test_tabu_vyvola_kolobeh_opisu` | 1 | 11/20 | [0.342, 0.742] | křehká | 0 | 0 | 1.85 |
| `test_v2_m3b_gate.py::test_zvukove_metriky_drzi_i_s_lexikalni_zmenou` | 2 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 3.80 |
| `test_v2_m4_gate.py::test_analytizace_po_erozi_padu_se_ustali_slovosled` | 1 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 2.35 |
| `test_v2_m4_gate.py::test_velky_cyklus_eroze_opis_priklonka_nova_koncovka` | 1 | 15/20 | [0.531, 0.888] | křehká | 2 | 0 | 2.22 |
| `test_v2_m4_gate.py::test_jespersenuv_cyklus_ne_ne_pas_pas` | 1 | 8/20 | [0.219, 0.613] | slabá | 0 | 0 | 2.66 |
| `test_v2_m4_gate.py::test_bez_eroze_syntax_zustava_a_zvukove_metriky_drzi` | 1 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 2.35 |
| `test_v2_m4b_gate.py::test_clen_vznikne_z_ukazovaciho_zajmena` | 3 (aspoň 2) | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 2.45 |
| `test_v2_m4b_gate.py::test_bez_padu_se_slovosled_ustali` | 3 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 2.45 |
| `test_v2_m4b_gate.py::test_exaptace_zbytkove_koncovky` | 1 | 15/20 | [0.531, 0.888] | křehká | 2 | 0 | 2.07 |
| `test_v2_m4b_gate.py::test_jazyk_bez_kategorie_ji_nema_dokud_ji_nevyvine` | 1 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 2.05 |
| `test_v2_m5_gate.py::test_s2_mesto_s_pristehovalci_zjednodusuje_ostrov_drzi` | 2 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 1.95 |
| `test_v2_m5_gate.py::test_s2_zjednoduseni_pusobi_l2_mluvci` | 2 | 19/20 | [0.764, 0.991] | robustní | 4 | 1 | 3.86 |
| `test_v2_m5_gate.py::test_s3_region_prejde_na_prestizni_jazyk` | 2 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 2.53 |
| `test_v2_m5_gate.py::test_s3_v_novem_jazyce_zustane_stavba_a_vyslovnost_ale_malo_slov` | 2 | 11/20 | [0.342, 0.742] | křehká | 0 | 0 | 2.53 |
| `test_v2_m5_gate.py::test_vypujcky_jsou_vzacne_pojmy_adaptovane_hlaskami_prijemce` | 2 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 1.71 |
| `test_v2_m5_gate.py::test_bez_dvojjazycnosti_se_stavba_nepujcuje` | 2 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 1.71 |
| `test_v2_m5_gate.py::test_metrika_11_slozitost_klesa_s_l2_mluvcimi_a_populaci` | 2 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 3.24 |
| `test_v2_m6a_gate.py::test_s4_rozdil_roste_do_skoly_pak_se_zmensuje` | 2 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 6.40 |
| `test_v2_m6a_gate.py::test_s4_bez_skoly_rozdil_roste_dal` | 2 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 6.40 |
| `test_v2_m6a_gate.py::test_skola_sjednoti_dialekty_ale_jazyk_se_meni_dal` | 2 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 6.40 |
| `test_v2_m6a_gate.py::test_skola_se_zmrazenou_normou_zmenu_zastavi` | 2 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 6.40 |
| `test_v2_m6a_gate.py::test_psany_kod_bez_tisku_stoji` | 1 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 0.23 |
| `test_v2_m6b_gate.py::test_metrika_9_vzdalenost_roste_se_zemepisnou_zpomalene` | 2 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 13.44 |
| `test_v2_m6b_gate.py::test_elita_v_mensine_prejde_na_jazyk_poddanych` | 2 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 2.14 |
| `test_v2_m6b_gate.py::test_superstrat_je_hlavne_slovni` | 2 | 16/20 | [0.584, 0.919] | křehká | 2 | 0 | 2.14 |
| `test_v2_m6b_gate.py::test_jazyk_trhu_jen_mimo_domov_je_stabilni_dvojjazycnost` | 2 | 16/20 | [0.584, 0.919] | křehká | 2 | 0 | 1.47 |
| `test_v2_m6b_gate.py::test_loajalita_prechod_zpomali_nebo_zastavi` | 1 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 8.26 |
| `test_v2_m6b_gate.py::test_podil_l2_mluvcich_vyplyne_z_migrace_a_slozitost_klesa` | 2 | 15/20 | [0.531, 0.888] | křehká | 2 | 0 | 3.10 |
| `test_v2_m6b_gate.py::test_fergusonova_diglosie_vysoka_varieta_stoji_lidova_rec_se_vzdaluje` | 2 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 4.31 |
| `test_v2_m6b_gate.py::test_nabozenstvi_prinese_ucena_slova_z_liturgickeho_jazyka` | 2 | 20/20 | [0.839, 1.000] | robustní | 5 | 2 | 3.44 |
| `test_v2_m6c_gate.py::test_strom_jazyku_odpovida_historii_rozpadu` | 2 | 19/20 | [0.764, 0.991] | robustní | 4 | 1 | 5.44 |
| `test_v2_m6c_gate.py::test_strom_je_stabilni` | 2 | 19/20 | [0.764, 0.991] | robustní | 4 | 1 | 5.44 |

### Poznámky k souhrnným a víceseedovým branám

1. **Souhrnné dvou-seedové brány (`m3::produktivni_vzor`, `m3b::metrika_2`, `m3b::nova_slova`)**:
   Všechny tři prošly jako **robustní** už při přísnějším jednoseedovém vyhodnocení
   (`19/20`, `20/20` a `20/20`), takže přeměřování po dvojicích seedů nebylo nutné.
2. **Brána `test_v2_m4b_gate.py::test_clen_vznikne_z_ukazovaciho_zajmena` (`3 (aspoň 2)`)**:
   Na jednotlivé seedy prošla v **20/20** případech (`p̂ = 1,000`, Wilsonův 95%
   interval `[0.839, 1.000]`). Odvozená pravděpodobnost průchodu celé brány
   `P(Bin(3, p) >= 2) = 3 p² (1 - p) + p³` je pro bodový odhad **100,0 %**
   (`1.000`) a na dolní mezi Wilsonova 95% intervalu (`p_dolní = 0,839`) činí
   **93,0 %** (`0.930`, interval `[0.930, 1.000]`).
3. **Pět bran s `19/20` v auditu `101..120`, které dnes vyžadují `all` přes 2 seedy**:
   `m3::morfologizace`, `m3::produktivni_vzor`, `m5::s2_l2`, `m6c::strom_odpovida`
   a `m6c::strom_stabilni` splnily jednoseedové kritérium `≥ 19/20` (**robustní**);
   čtyři z nich zůstávají beze změny, zatímco `m3::morfologizace` ukázala v
   rozšířeném měření `101..140` míru `35/40` (87,5 %) a byla spolu s
   `m3::zvukove_metriky` převedena na `k` z `10` (viz níže).
4. **Dvě křehké brány s `11/20` (`m3b::tabu` a `m5::s3_substrat`) a práh `k` pro `N = 10`**:
   Pro `11/20` vychází `p_dolní = 0,3421`. Při výchozím `N = 10` je
   `P(Bin(10, 0.3421) = 0) = 0,6579¹⁰ = 1,525 % > 1 %`, takže vzorec
   `P(Bin(N, p_dolní) < k) <= 1 %` vrací **`k = 0`**, čímž by brána byla triviálně
   splněná i pro 0 úspěšných seedů (a neprošla by negativní kontrolou v kroku 5).
   Při zvýšení na **`N = 12`** (`seedy 1..12`) klesne `P(X = 0) = 0,6579¹² = 0,660 % <= 1 %`
   a vychází netriviální **`k = 1`** (případně při `N = 17` vychází `k = 2`).
5. **Slabá brána (`< 10/20`) – krok 4**:
   Jedinou slabou branou v celém souboru je
   `test_v2_m4_gate.py::test_jespersenuv_cyklus_ne_ne_pas_pas` s průchodem
   **8/20 (40 %)**, Wilsonův 95% interval `[0.219, 0.613]`. Příčinou (popsanou už
   v `08-davkova-inovace.md`) je, že `NegationReduction` spouští přechod z
   `embraced` na koncové `post` už od podílu `embraced >= 0.5`; v řadě běhů tak
   `post` vytlačí `embraced` dřív, než `embraced` dosáhne prahu ustálení
   `establish_threshold = 0.999`, takže v historii událostí `established` chybí
   mezistupeň `"embraced"`. Uživatel zvolil variantu (1): převod na `N = 19, k = 1`
   jako ochranu proti regresi s otevřenou otázkou do kalibrace M7.

## Krok 5: negativní kontroly před uzamčením prahů `k`

Před převodem bran byly jednorázově změřeny negativní kontroly (vypnutý příčinný
mechanismus) pro všech 7 křehkých bran z auditu `101..120`, pro Jespersena i pro
dvě hraniční brány v M3 (`morfologizace` a `zvukove_metriky`, viz níže) na
cílových řadách seedů `1..N`:

| Brána | Vypnutý mechanismus | Seedy | Práh `k` | Průchod kontroly | Výsledek (`< k`) | Čas (s) |
|---|---|---|---:|---:|---|---:|
| `test_v2_m3_gate.py::test_morfologizace_vznikne_sama` | bez `SoundChange` (žádné hláskové změny) | `1..10` | 4 | **0/10** | OK | 8,8 |
| `test_v2_m3_gate.py::test_zvukove_metriky_drzi_i_s_paradigmaty` | bez `Clarity` a `FunctionalLoad` (nehlídaná eroze a splynutí) | `1..10` | 5 | **3/10** | OK | 31,4 |
| `test_v2_m3b_gate.py::test_tabu_vyvola_kolobeh_opisu` | `taboo=()` (žádné tabu) | `1..12` | 1 | **0/12** | OK | 22,0 |
| `test_v2_m4_gate.py::test_velky_cyklus_eroze_opis_priklonka_nova_koncovka` | `cell=None` (bez počáteční eroze `PAST`) | `1..10` | 2 | **0/10** | OK | 33,5 |
| `test_v2_m4_gate.py::test_jespersenuv_cyklus_ne_ne_pas_pas` | `particle=None` (bez oslabení záporky) | `1..19` | 1 | **0/19** | OK | 50,3 |
| `test_v2_m4b_gate.py::test_exaptace_zbytkove_koncovky` | `ORDER="free"` (volný slovosled, pád nese role) | `1..10` | 2 | **0/10** | OK | 10,1 |
| `test_v2_m5_gate.py::test_s3_v_novem_jazyce_zustane_stavba_a_vyslovnost_ale_malo_slov` | `contact.INTERFERENCE_WEIGHT = 0.0` (bez L1 interference) | `1..12` | 1 | **0/12** | OK | 27,1 |
| `test_v2_m6b_gate.py::test_superstrat_je_hlavne_slovni` | `events=()` (bez dobytí elitou `Conquest`) | `1..10` | 2 | **0/10** | OK | 21,2 |
| `test_v2_m6b_gate.py::test_jazyk_trhu_jen_mimo_domov_je_stabilni_dvojjazycnost` | `domain="home"` (bez omezení jazyka trhu jen mimo domov) | `1..10` | 2 | **0/10** | OK | 9,2 |
| `test_v2_m6b_gate.py::test_podil_l2_mluvcich_vyplyne_z_migrace_a_slozitost_klesa` | `migration=0.0` (bez gravitační migrace) | `1..10` | 2 | **0/10** | OK | 28,3 |

Všech 10 negativních kontrol skončilo pod prahem `k` (`0/N` u devíti bran a
`3/10 < 5` u `m3::zvukove_metriky`), žádná z převáděných bran tedy není bezzubá.

### Zjištění při běhu celé sady v M3 a měření před/po

Při prvním spuštění celé sady (`pytest -q`, 390,99 s) prošlo všech 8 původně
převedených bran, ale spadla nedotčená brána
`test_v2_m3_gate.py::test_zvukove_metriky_drzi_i_s_paradigmaty` na `seed = 1`
(`profile.homophony = 0,05369 >= 0,05` v jedné z 8 vesnic). Podle pravidla z
kroku 6 byla změřena míra průchodu před a po:

- V M3 je vypnutá sémantika (`semantics=False`), takže homofona vzniklá splynutím
  hlásek nenahrazuje lexikální obměna. Nad 149 kořeny skáče podíl homofonů po
  dvojicích z `6/149 = 0,0403` (3 dvojice, projde) rovnou na `8/149 = 0,0537`
  (4 dvojice v kterékoli z 8 vesnic, neprojde).
- **Před krokem 1 (`f3a9dfd`, `"innovation-change-34"`)**: `101..120` → `20/20`,
  `1..20` → `19/20` (selhal `seed=4`: `0,0805`), celkem **39/40 (97,5 %)**.
- **Po kroku 1 (`"innovation-change"`)**: `101..140` → `40/40`, `1..20` → `17/20`
  (selhaly `seed=1, 4, 6`: vždy `8/149 = 0,0537`), celkem **57/60 (95,0 %)**.
- Sousední `test_v2_m3_gate.py::test_morfologizace_vznikne_sama` vyšla v auditu
  `101..120` těsně `19/20`, ale v rozšířeném auditu `101..140` má míru **35/40
  (87,5 %, Wilson `[0.739, 0.945]`)** a na `1..10` **7/10**.
- Po odsouhlasení uživatelem byly v `test_v2_m3_gate.py` sdílené běhy rozšířeny
  na `1..10` (`without_leveling` zůstává na `1..2`) a obě tyto brány převedeny
  podle stejného vzorce na `k` z `10` (`k = 5` a `k = 4`).

## Kroky 3 a 4: převod křehkých bran a Jespersena na `k` z `N`

42 robustních bran a 10 deterministických/výkonových testů zůstalo beze změny.
Převedeno bylo celkem 10 bran podle vzorce `P(Bin(N, p_dolní) < k) <= 1 %` na
souvislých řadách seedů `1..N`:

| Brána | Audit `101..120` | Wilson 95 % | `N` | `k` | `P(Bin(N, p_dolní) < k)` | Negativní kontrola | Poznámka |
|---|---:|---:|---:|---:|---:|---:|---|
| `test_v2_m3_gate.py::test_morfologizace_vznikne_sama` | 19/20 (`35/40` na `101..140`) | [0.764, 0.991] (`[0.739, 0.945]`) | 10 | 4 | 0,20 % (0,34 %) | 0/10 | sdílí běhy `1..2` s ostatními M3 branami |
| `test_v2_m3_gate.py::test_zvukove_metriky_drzi_i_s_paradigmaty` | 20/20 (`57/60` celkem) | [0.839, 1.000] | 10 | 5 | 0,14 % | 3/10 | diskrétní skok 4. dvojice homofonů (`8/149 = 0,0537`) bez sémantiky |
| `test_v2_m3b_gate.py::test_tabu_vyvola_kolobeh_opisu` | 11/20 | [0.342, 0.742] | 12 | 1 | 0,66 % | 0/12 | **brána existence** (otázka do M7) |
| `test_v2_m4_gate.py::test_velky_cyklus_eroze_opis_priklonka_nova_koncovka` | 15/20 | [0.531, 0.888] | 10 | 2 | 0,60 % | 0/10 | — |
| `test_v2_m4_gate.py::test_jespersenuv_cyklus_ne_ne_pas_pas` | 8/20 | [0.219, 0.613] | 19 | 1 | 0,92 % | 0/19 | ochrana proti regresi (otázka do M7) |
| `test_v2_m4b_gate.py::test_exaptace_zbytkove_koncovky` | 15/20 | [0.531, 0.888] | 10 | 2 | 0,60 % | 0/10 | — |
| `test_v2_m5_gate.py::test_s3_v_novem_jazyce_zustane_stavba_a_vyslovnost_ale_malo_slov` | 11/20 | [0.342, 0.742] | 12 | 1 | 0,66 % | 0/12 | **brána existence** (otázka do M7) |
| `test_v2_m6b_gate.py::test_superstrat_je_hlavne_slovni` | 16/20 | [0.584, 0.919] | 10 | 2 | 0,25 % | 0/10 | sdílí běhy `1..2` s `elita_prejde` |
| `test_v2_m6b_gate.py::test_jazyk_trhu_jen_mimo_domov_je_stabilni_dvojjazycnost` | 16/20 | [0.584, 0.919] | 10 | 2 | 0,25 % | 0/10 | — |
| `test_v2_m6b_gate.py::test_podil_l2_mluvcich_vyplyne_z_migrace_a_slozitost_klesa` | 15/20 | [0.531, 0.888] | 10 | 2 | 0,60 % | 0/10 | — |

### Otevřené otázky pro kalibraci M7

1. **Jespersenův cyklus (`test_v2_m4_gate.py::test_jespersenuv_cyklus_ne_ne_pas_pas`, audit 8/20, `N = 19, k = 1`)**:
   Ověřit, zda má zdvojená záporka `embraced` (*ne … pas*) v modelu dosáhnout
   plného ustálení (`establish_threshold = 0.999`) dřív, než ji vytlačí koncové
   `post` (*pas*), vzhledem k tomu, že `NegationReduction` se dnes spouští už od
   podílu `embraced >= 0.5`.
2. **Koloběh tabu (`test_v2_m3b_gate.py::test_tabu_vyvola_kolobeh_opisu`, audit 11/20, brána existence `N = 12, k = 1`)**:
   Posoudit v M7, zda je 55% míra alespoň dvou po sobě jdoucích ustálených
   opisných náhrad tabuovaného pojmu za 2 500 let realistická, nebo zda má být
   tlak tabu silnější.
3. **Substrát při jazykovém přechodu S3 (`test_v2_m5_gate.py::test_s3_v_novem_jazyce_zustane_stavba_a_vyslovnost_ale_malo_slov`, audit 11/20, brána existence `N = 12, k = 1`)**:
   Posoudit v M7 kalibraci `INTERFERENCE_WEIGHT` a rychlosti šíření přes hranici,
   protože přísné uspořádání gradientu substrátu mezi pohraniční a vnitrozemskou
   vesnicí (`x1>y > x2>y > y2` a `min(x0>y, x1>y) > 0.4`) dnes vychází v ~55 %
   běhů.

## Ověření celé sady a krok 6

- **Celá sada testů (`pytest -q`)**: prošlo všech **665 testů** za **428,48 s
  (7 min 8 s)** bez jediného selhání (po přidání 8 sdílených běhů v M3 o 8,5 s
  nad 7minutovým rozpočtem `420 s`; před případným snížením `N` nahlášeno
  uživateli podle pokynu).
- **Statická kontrola a otisky**: `ruff check`, `mypy` i všech 7 referenčních
  otisků v `scripts/v2_digests.py` procházejí bez chyb.
- **Krok 6**: do `AGENT.md` doplněno pravidlo o zákazu výběru seedů či konstant
  při pádu stochastické brány a povinnosti měřit míru průchodu před a po přes
  `scripts/v2_gate_rates.py`; nové otisky a shrnutí jsou zapsané také v
  `docs/engine-v2/05-specifikace.md` a `docs/CURRENT_STATE.md`.
