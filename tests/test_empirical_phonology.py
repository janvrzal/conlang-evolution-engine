"""Index Diachronica a PHOIBLE: offline import, priory a validace inventáře."""
from cee.engine.empirical import (
    DiachronicaPriors,
    PhoibleInventoryModel,
    build_empirical_cache,
    build_diachronic_priors,
    default_paths,
    load_diachronic_priors,
    load_phoible_model,
    save_diachronic_priors,
    save_phoible_model,
)
from cee.engine.generator import SoundChangeGenerator
from cee.engine.inventory import InventoryView
from cee.core.models import Inventory, Lexicon, State
from cee.pipeline import SimulationConfig, build_empirical_phonology


def test_index_diachronica_redux_se_prevede_na_auditovatelne_priory(tmp_path):
    changes = tmp_path / "changes"
    changes.mkdir()
    (changes / "sample.txt").write_text(
        "# family language\n- *p / f\n- *t / č / _i\n- *k / c / _i\n- *a / / _#\n- *e / i\n",
        encoding="utf-8",
    )
    priors = build_diachronic_priors(changes)

    assert priors.observations == 5
    assert priors.counts["unconditional_fricatization"] == 1
    assert priors.counts["palatalization"] == 2
    assert priors.counts["apocope"] == 1
    assert priors.counts["vowel_shift"] == 1
    assert priors.environments == {"unconditional": 2, "conditioned": 2, "word_final": 1}
    assert priors.provenance["source"] == "Index Diachronica Redux"
    assert priors.multiplier("palatalization") > 1


def test_phoible_model_validuje_nepravdepodobnou_znelou_stopu_bez_nezneleho(tmp_path, mapper):
    csv_path = tmp_path / "phoible.csv"
    csv_path.write_text(
        "InventoryID,Phoneme\n1,p\n1,b\n1,a\n2,t\n2,d\n2,i\n",
        encoding="utf-8",
    )
    model = PhoibleInventoryModel.from_csv(csv_path)

    good = InventoryView(mapper, {"p", "b", "a"})
    bad = InventoryView(mapper, {"b", "a"})
    assert model.validate(good).accepted
    report = model.validate(bad)
    assert not report.accepted
    assert "voiceless counterpart" in " ".join(report.reasons)


def test_empiricke_cache_se_serializuje_bez_sitove_zavislosti(tmp_path):
    priors = DiachronicaPriors(
        counts={"palatalization": 4},
        observations=4,
        provenance={"source": "fixture", "sha256": "abc"},
    )
    model = PhoibleInventoryModel(
        inventories=[frozenset({"p", "a"})],
        provenance={"source": "fixture", "sha256": "def"},
    )
    paths = default_paths(tmp_path / "cache")
    paths["root"].mkdir()
    save_diachronic_priors(priors, paths["diachronica_priors"])
    save_phoible_model(model, paths["phoible_model"])

    assert load_diachronic_priors(paths["diachronica_priors"]) == priors
    assert load_phoible_model(paths["phoible_model"]).inventories == model.inventories


def test_cache_vznikne_z_lokalnich_raw_zdroju(tmp_path):
    paths = default_paths(tmp_path / "cache")
    changes = paths["diachronica_raw"] / "data" / "changes"
    changes.mkdir(parents=True)
    (changes / "sample.txt").write_text("- *p / f\n", encoding="utf-8")
    paths["phoible_raw"].parent.mkdir(parents=True, exist_ok=True)
    paths["phoible_raw"].write_text("InventoryID,Phoneme\n1,p\n1,a\n", encoding="utf-8")

    result = build_empirical_cache(paths["root"])

    assert result["observations"] == "1"
    assert result["inventories"] == "1"
    assert paths["diachronica_priors"].exists()
    assert paths["phoible_model"].exists()


def test_pipeline_nacte_explicitne_zafixovanou_empirickou_cache(tmp_path):
    priors_path = tmp_path / "priors.json"
    model_path = tmp_path / "model.json"
    save_diachronic_priors(
        DiachronicaPriors({"lenition": 3}, 3, {"source": "fixture"}), priors_path
    )
    save_phoible_model(
        PhoibleInventoryModel([frozenset({"p", "a"})], {"source": "fixture"}), model_path
    )

    priors, model = build_empirical_phonology(
        SimulationConfig(
            diachronica_priors_path=str(priors_path),
            phoible_model_path=str(model_path),
            use_empirical_phonology=True,
        )
    )

    assert priors is not None and priors.counts == {"lenition": 3}
    assert model is not None and model.provenance["source"] == "fixture"


def test_empiricke_priory_meni_vahy_generatoru(mapper):
    priors = DiachronicaPriors(
        counts={"palatalization": 100, "lenition": 1}, observations=101,
        provenance={"source": "test", "sha256": "test"},
    )
    preset = {
        "schemas": {"palatalization": {"base_weight": 1}, "lenition": {"base_weight": 1}},
        "biomes": {},
    }
    generator = SoundChangeGenerator(preset, seed=1, empirical_priors=priors)
    state = State(node_id="x", inventory=Inventory(), lexicon=Lexicon())
    choices, weights = generator._weighted_schemas(None)
    names = {schema.name: weight for schema, weight in zip(choices, weights)}
    assert names["palatalization"] > names["lenition"]
