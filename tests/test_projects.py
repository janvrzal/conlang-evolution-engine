"""
Persistence projektů.

Bez ní se rozdělaná práce držela jen v paměti prohlížeče a mizela při přechodu
mezi stránkami i po reloadu.
"""
import json

import pytest

from cee import projects


@pytest.fixture(autouse=True)
def izolovana_slozka(tmp_path, monkeypatch):
    monkeypatch.setenv("CEE_PROJECTS_DIR", str(tmp_path))
    return tmp_path


def test_ulozi_a_nacte():
    p = projects.Project(id="demo", name="Demo")
    p.data = {"nodes": [{"id": "proto"}], "timeSteps": [0, 500]}
    projects.save(p)

    nacteny = projects.load("demo")
    assert nacteny.name == "Demo"
    assert nacteny.data["timeSteps"] == [0, 500]


def test_prezije_opakovane_ulozeni():
    projects.save(projects.Project(id="demo", data={"v": 1}))
    projects.save(projects.Project(id="demo", data={"v": 2}))
    assert projects.load("demo").data == {"v": 2}


def test_load_or_create_zalozi_prazdny():
    p = projects.load_or_create("novy", "Můj svět")
    assert p.name == "Můj svět"
    assert projects.load("novy").id == "novy"


@pytest.mark.parametrize(
    "bad_id",
    ["../../etc/passwd", "a/b", "", "..", "x" * 65, "má mezeru", "tečka.json"],
)
def test_nebezpecne_id_se_odmitne(bad_id):
    """ID se stává jménem souboru — cesta ven ze složky projektů je nepřípustná."""
    with pytest.raises(projects.InvalidProjectId):
        projects.validate_id(bad_id)
    with pytest.raises(projects.InvalidProjectId):
        projects.save(projects.Project(id=bad_id))


def test_chybejici_projekt():
    with pytest.raises(projects.ProjectNotFound):
        projects.load("neexistuje")
    with pytest.raises(projects.ProjectNotFound):
        projects.delete("neexistuje")


def test_smazani():
    projects.save(projects.Project(id="docasny"))
    projects.delete("docasny")
    assert projects.list_projects() == []


def test_seznam_radi_od_nejcerstvejsiho():
    projects.save(projects.Project(id="stary", updated_at="2020-01-01T00:00:00+00:00"))
    projects.save(projects.Project(id="novy"))

    # save() razítko přepisuje, takže "stary" dostane čerstvé; seřaď podle něj.
    ids = [p["id"] for p in projects.list_projects()]
    assert set(ids) == {"stary", "novy"}
    assert ids == sorted(
        ids, key=lambda i: projects.load(i).updated_at, reverse=True
    )


def test_poskozeny_soubor_neshodi_vypis(izolovana_slozka):
    projects.save(projects.Project(id="dobry"))
    (izolovana_slozka / "rozbity.json").write_text("{tohle není JSON", encoding="utf-8")

    ids = [p["id"] for p in projects.list_projects()]
    assert ids == ["dobry"]

    with pytest.raises(projects.ProjectError):
        projects.load("rozbity")


def test_zapis_je_atomicky(izolovana_slozka):
    """Po uložení nesmí ve složce zůstat dočasný soubor."""
    projects.save(projects.Project(id="demo", data={"x": 1}))
    zbytky = [f.name for f in izolovana_slozka.iterdir() if f.suffix == ".tmp"]
    assert zbytky == []

    ulozeno = json.loads((izolovana_slozka / "demo.json").read_text(encoding="utf-8"))
    assert ulozeno["data"] == {"x": 1}


def test_razitko_zmeny_se_aktualizuje():
    p = projects.save(projects.Project(id="demo"))
    prvni = p.updated_at
    p.updated_at = "2020-01-01T00:00:00+00:00"
    projects.save(p)
    assert projects.load("demo").updated_at >= prvni
