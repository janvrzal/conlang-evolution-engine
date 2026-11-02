"""Souběžná variabilita slovní zásoby protojazyka (``cee.v2.variation``)."""

from cee.v2.parameters import Parameters
from cee.v2.scenarios import ProtoLanguage, Region, region_world, village_grid
from cee.v2.simulation import Simulation
from cee.v2.variation import measured, source_graph, target, village_features


def world(scale=1.0, languages=("a",)):
    regions = (Region("p", (0.0, 0.0), language="a", villages=3, neighbours=("q",)),
               Region("q", (60.0, 0.0), language=languages[-1], villages=3, neighbours=("p",)))
    return region_world(regions, languages=tuple(ProtoLanguage(id) for id in languages), semantics=True,
                        seed=3, params=Parameters(standing_variation=scale))


def state(w):
    lexical = sorted(v for v, variable in w.variables.items() if variable.kind == "lexical")
    return {(g, v): w.distribution(g, v).as_dict() for g in w.group_ids() for v in lexical}


def test_namerena_data_maji_koše_podle_frekvence():
    data = measured()
    assert len(data["bins"]) == len(data["edges"]) + 1
    for entry in data["bins"]:
        assert entry["density"] and all(value >= 0 for value in entry["density"].values())
        assert entry["peak"] == sorted(entry["peak"]) and len(entry["peak"]) == len(data["quantiles"])
        assert entry["decay"] == sorted(entry["decay"], reverse=True)


def test_variabilita_zachova_slovo_autora_a_vznikne_z_opravdovych_zmen():
    w = world()
    before = {key: next(iter(value)) for key, value in state(w).items()}
    Simulation(w)
    after = state(w)
    assert sum(len(value) > 1 for value in after.values()) > len(after) // 10
    for key, shares in after.items():
        assert max(shares, key=shares.get) == before[key]
        assert shares[before[key]] >= 1.0 - w.params.variation_cap - 1e-9
        assert abs(sum(shares.values()) - 1.0) < 1e-9
    seeded = {variant for shares in after.values() for variant in shares if w.variants[variant].origin.change}
    assert seeded and all(w.variants[variant].origin.tick == 0 for variant in seeded)
    assert {w.variants[variant].origin.change for variant in seeded} >= {"derivation", "semantic_shift"}


def test_variabilita_je_deterministicka_jednorazova_a_vypnutelna():
    first, second = world(), world()
    Simulation(first)
    Simulation(second)
    assert state(first) == state(second)
    once = state(first)
    Simulation(first)
    assert state(first) == once
    cold = world(0.0)
    Simulation(cold)
    assert all(len(shares) == 1 for shares in state(cold).values())


def test_varianty_se_nesiri_do_jineho_jazyka():
    w = world(languages=("a", "b"))
    Simulation(w)
    for (group_id, _), shares in state(w).items():
        language = w.groups[group_id].main_code.language
        for variant in shares:
            morpheme = w.variants[variant].payload.get("morpheme")
            if w.variants[variant].origin.change and morpheme:
                assert w.morphemes[morpheme].language == language


def minority_entries(w):
    return sum(len(shares) - 1 for shares in state(w).values())


def test_mnozstvi_variability_se_ridi_otevrenosti_a_populaci_vesnice():
    model = measured()["village_model"]
    assert target(model, (0.5, 500.0, 3.0))[0] > 2 * target(model, (0.05, 500.0, 3.0))[0]
    # Malá vesnice drží méně variant, zato silnějších (drift).
    small, large = target(model, (0.1, 125.0, 3.0)), target(model, (0.1, 2000.0, 3.0))
    assert small[0] < large[0] and small[1] / small[0] > large[1] / large[0]
    worlds = {openness: village_grid(6, seed=3, semantics=True, openness=openness) for openness in (0.05, 0.5)}
    for w in worlds.values():
        Simulation(w)
    assert minority_entries(worlds[0.5]) > 1.5 * minority_entries(worlds[0.05])


def test_graf_vazeb_slaba_hranice_propusti_mene():
    w = world()
    groups = [g for g in w.group_ids() if not w.groups[g].written]
    graph = source_graph(w, groups)
    index = {g: i for i, g in enumerate(groups)}
    origin = groups[0]
    region = origin.split("-", 1)[0]
    same = [g for g in groups if g.split("-", 1)[0] == region and g != origin]
    other = [g for g in groups if g.split("-", 1)[0] != region]
    assert same and other
    # Vazby uvnitř kraje jsou silné, přes hranici slabé: varianta z vesnice
    # dosáhne k sousedům v kraji výrazně víc než za hranici.
    assert min(graph[index[g], index[origin]] for g in same) > 2 * max(graph[index[g], index[origin]] for g in other)
    assert all(value[2] > 0 for value in village_features(w, groups, graph).values())
