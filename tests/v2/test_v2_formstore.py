"""Úložiště tvarů v polích (krok A3) proti dřívějším vrstvám slovníků."""

import random

import pytest

from cee.v2.language.lexicon import FormStore, UnitForm
from cee.v2.scenarios import village_grid
from cee.v2.simulation import Simulation
from cee.v2.world import Code


class LayeredReference:
    """Dřívější úložiště: copy-on-write vrstvy slovníků (jen reference pro test)."""

    def __init__(self, base=None):
        self.base, self.own, self.frozen, self.log = base, {}, False, []

    def get(self, key):
        layer = self
        while layer is not None:
            if key in layer.own:
                return layer.own[key]
            layer = layer.base
        return None

    def set(self, key, unit):
        self.own[key] = unit
        self.log.append(key)

    def branch(self):
        snapshot = LayeredReference(self.base)
        snapshot.own, snapshot.frozen = self.own, True
        self.base, self.own = snapshot, {}
        return LayeredReference(snapshot)


def _random_unit(rng):
    form = tuple(rng.randrange(1, 9) for _ in range(rng.randrange(0, 6)))
    boundary = rng.choice([None, 0, len(form)])
    exponent = rng.choice([None, "e1", "e2", "m3"])
    return UnitForm(form, boundary, exponent)


def test_pole_davaji_stejne_tvary_jako_vrstvy_slovniku_vcetne_vetveni():
    rng = random.Random(7)
    names = [f"m{i}" for i in range(12)]
    pairs = [(FormStore(), LayeredReference())]
    for _ in range(600):
        index = rng.randrange(len(pairs))
        store, reference = pairs[index]
        action = rng.random()
        if action < 0.7:
            name, unit = rng.choice(names), _random_unit(rng)
            store.set(name, unit)
            reference.set(name, unit)
        elif action < 0.8 and len(pairs) < 6:
            pairs.append((store.branch(), reference.branch()))
        for store, reference in pairs:
            for name in names + ["neznamy"]:
                assert store.get(name) == reference.get(name)
            assert store.log == reference.log
    # Každá větev má vlastní identitu deníku.
    assert len({store.token for store, _ in pairs}) == len(pairs)


def test_vetev_nesdili_s_zdrojem_nic_menitelneho():
    store = FormStore()
    store.set("a", UnitForm((1, 2), 1, "e"))
    branch = store.branch()
    store.set("a", UnitForm((3,), None, None))
    store.set("b", UnitForm((4,), None, None))
    assert branch.get("a") == UnitForm((1, 2), 1, "e") and branch.get("b") is None
    branch.set("c", UnitForm((5,), None, None))
    assert store.get("c") is None and branch.log == ["c"] and store.log == ["a", "a", "b"]
    forms, boundaries, exponents = branch.arrays()
    assert len(forms) == len(boundaries) == len(exponents)
    assert (forms >= 0).sum() == 2


def test_zmrazene_uloziste_nejde_menit_ale_vetvi_se():
    store = FormStore().freeze()
    with pytest.raises(RuntimeError):
        store.set("a", UnitForm((1,), None, None))
    store.branch().set("a", UnitForm((1,), None, None))


def test_pripojeni_ke_svetu_prenese_obsah_podle_jmen_morfemu():
    store = FormStore()
    store.set("m:late", UnitForm((7, 8), 1, "m:suffix"))
    world = village_grid(1, seed=1, phonology=True)
    store.bind(world)
    assert store.context is world and store.get("m:late") == UnitForm((7, 8), 1, "m:suffix")
    assert "m:late" in world.registry.morphemes and store.get("m:other") is None


def test_kod_ve_svete_pouziva_registr_a_banku_sveta():
    world = village_grid(4, seed=2, morphology=True, semantics=True)
    Simulation(world).run(1000)
    code = world.groups[world.group_ids()[0]].main_code
    assert code.forms.context is world and world.bank is code.forms.bank()
    changed = [name for name in dict.fromkeys(code.forms.log) if code.forms.get(name) is not None]
    assert changed
    for name in changed:
        number = world.registry.morphemes.number(name)
        form_id = code.forms.arrays()[0][number]
        assert world.bank.forms[form_id] == world.form_of(code, name) == code.forms.get(name).form


def test_cislo_tvaru_ze_sveta_sedi_s_hasovanim_tvaru_v_bance():
    world = village_grid(4, seed=2, morphology=True, semantics=True)
    Simulation(world).run(1000)
    bank = world.form_bank()
    checked = 0
    for group in world.groups.values():
        code = group.main_code
        for morpheme_id in list(code.phonology.vocabulary) + list(dict.fromkeys(code.forms.log)):
            assert world.form_id_of(code, morpheme_id) == bank.id_of(world.form_of(code, morpheme_id))
            checked += 1
    assert checked > 100
    # Kód, který nepatří do světa (vlastní číslování a banka), se přepočte přes banku světa.
    loose = Code("loose", world.groups[world.group_ids()[0]].main_code.repertoire)
    morpheme_ids = list(world.morphemes)[:2]
    loose.forms.set(morpheme_ids[0], UnitForm((1, 2, 3), None, None))
    assert world.form_id_of(loose, morpheme_ids[0]) == bank.id_of((1, 2, 3))
    assert world.form_id_of(loose, morpheme_ids[1]) == bank.id_of(world.morphemes[morpheme_ids[1]].form)
