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
