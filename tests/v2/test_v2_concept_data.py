"""Data o pojmech z WOLD (``cee.v2.concept_data``)."""

import statistics

from cee.v2 import concept_data
from cee.v2.scenarios import DEFAULT_CONCEPTS


def test_kazdy_pojem_enginu_ma_zaznam_s_licenci_a_citaci():
    data = concept_data.data()
    assert set(DEFAULT_CONCEPTS) <= set(data["concepts"])
    source = data["sources"][0]
    assert source["license"] == "CC BY 4.0" and "Haspelmath" in source["citation"] and source["commit"]
    for concept in DEFAULT_CONCEPTS:
        entry = concept_data.info(concept)
        assert entry is not None and entry["domain"] in concept_data.DOMAINS
        assert entry["languages"] >= data["min_languages"]
        assert entry["borrowed"] is None or 0.0 <= entry["borrowed"] <= 1.0


def test_oblasti_moci_a_viry_se_pujcuji_vic_nez_jadro():
    fields = concept_data.data()["fields"]

    def mean(domain):
        return statistics.mean(entry["borrowed_mean"] for entry in fields.values() if entry["domain"] == domain)

    # WOLD (významy aspoň v deseti jazycích): víra a kultura se půjčují nejvíc,
    # moc zhruba dvakrát víc než domácí jádro; tělo a prostor nejméně.
    assert mean("religion") > mean("culture") > mean("learned") > mean("core")
    assert mean("power") > 1.5 * mean("core")
    assert fields["Social and political relations"]["borrowed_mean"] > 2 * fields["The body"]["borrowed_mean"]
    assert concept_data.borrowed("king") > 3 * concept_data.borrowed("hand")
    assert concept_data.domain("king") == "power" and concept_data.domain("hand") == "core"


def test_katalog_a_pojem_mimo_data():
    data = concept_data.data()
    assert len(data["catalog"]) > 1000
    assert len({item["wold_id"] for item in data["catalog"]}) == len(data["catalog"])
    assert concept_data.info("vymysleny-pojem") is None
    assert concept_data.domain("vymysleny-pojem") == "core"
    assert 0.2 < concept_data.borrowed("vymysleny-pojem") < 0.5


def test_frekvence_z_dat_pokryji_pojmy_enginu_a_davaji_smysl():
    data = concept_data.frequencies()
    assert data["alignment"]["leipzig_vs_calude"]["correlation"] > 0.8
    assert {source["license"].split()[0] for source in data["sources"]} == {"CC"}
    for concept in DEFAULT_CONCEPTS:
        value = concept_data.frequency(concept)
        assert value is not None and 0.05 <= value <= 0.9
    # Funkční slova a základní slovesa jsou častější než vzácné části těla a přírody.
    assert concept_data.frequency("not") > concept_data.frequency("heart") > concept_data.frequency("louse")
    assert concept_data.frequency("say") > concept_data.frequency("bite")
    assert concept_data.frequency("vymysleny-pojem") is None


def test_katalog_ma_jedinecna_id_mimo_pojmy_enginu():
    from cee.v2.language.constructions import GRAMMATICAL_SOURCES

    ids = concept_data.catalog_ids()
    assert len(ids) == 1304 == len(concept_data.catalog_order())
    assert set(ids).isdisjoint(DEFAULT_CONCEPTS) and set(ids).isdisjoint(GRAMMATICAL_SOURCES)
    assert set(concept_data.catalog_order()) == set(ids)
    # Hmyz a sloveso „fly“ se nesmí splést; číslo homonyma se zachová.
    assert ids["fly-3-83"]["name"] == "the fly" and ids["rough-2"]["wold_id"]
    assert "mountain-or-hill" not in ids  # pojem enginu `mountain`


def test_pojmy_katalogu_maji_data_jako_pojmy_enginu():
    assert concept_data.info("snake") is not None and concept_data.domain("snake") in concept_data.DOMAINS
    entry = concept_data.info("sky")
    assert entry is not None and entry["domain"] in concept_data.DOMAINS
    assert concept_data.borrowed("sky") == entry["borrowed"]
    low, high = concept_data.FREQUENCY_RANGE
    assert all(low <= concept_data.frequency(concept) <= high for concept in concept_data.catalog_ids())
    # Zdroje gramatikalizace jsou v enginu bez dat, aby se výchozí svět nezměnil.
    assert concept_data.frequency("go") is None and concept_data.info("have") is None
    # Frekvence významu enginu je totéž z pojmu i z katalogu.
    for concept in DEFAULT_CONCEPTS:
        item = concept_data.info(concept)
        assert abs(concept_data.item_frequency(item) - concept_data.frequency(concept)) < 1e-9


def test_poradi_rozsireni_slovniku_je_pevne():
    order = concept_data.catalog_order()
    assert order[:5] == ("and", "in", "at", "he", "with")
    table = concept_data.frequencies()["catalog"]
    swadesh = [concept for concept in order if table[concept_data.catalog_ids()[concept]["wold_id"]][1] == "calude2011"]
    # Swadeshův seznam jde první a uvnitř skupin sestupně podle frekvence.
    assert order[:len(swadesh)] == tuple(swadesh)
    for group in (swadesh, [concept for concept in order if concept not in swadesh]):
        values = [concept_data.log_frequency(concept) for concept in group]
        assert values == sorted(values, reverse=True)


def test_vazba_na_data_podle_wold_concepticonu_a_glosu():
    item = concept_data.find(wold="4-35")
    assert item is not None and item["name"] == "the leg"
    assert concept_data.find(concepticon=item["concepticon_id"]) is item
    assert concept_data.find(gloss="leg") is item and concept_data.find(gloss="LEG") is item
    assert concept_data.find(wold="9-9999") is None and concept_data.find(gloss="nic takového") is None


def test_prumery_katalogu_podle_domeny():
    assert 0.05 < concept_data.mean_frequency() < 0.5
    assert concept_data.mean_borrowed("religion") > concept_data.mean_borrowed("core")
    assert concept_data.mean_borrowed() == concept_data.mean_borrowed(None)
