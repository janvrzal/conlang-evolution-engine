"""
Persistence projektů.

Bez ní se rozdělaná práce držela jen v paměti prohlížeče a mizela při přechodu
mezi stránkami i po reloadu.
"""

import json
from pathlib import Path

import pytest

from cee import projects
from cee.project_schema import CURRENT_PROJECT_SCHEMA


FIXTURES = Path(__file__).parent / "fixtures"


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


def test_v1_projekt_se_pri_nacteni_migruje_na_verzovane_schema(izolovana_slozka):
    (izolovana_slozka / "legacy-v1.json").write_text(
        (FIXTURES / "project_v1.json").read_text(encoding="utf-8"), encoding="utf-8"
    )

    project = projects.load("legacy-v1")
    assert project.schema_version == CURRENT_PROJECT_SCHEMA
    assert project.data["timeSteps"] == [0, 1000]
    assert set(project.data["snapshots"]) == {"0"}
    assert project.data["generatedProtoLexicon"] == []


def test_v2_projekt_migruje_do_v3_bez_mutace_puvodniho_vstupu():
    legacy = json.loads((FIXTURES / "project_v2.json").read_text(encoding="utf-8"))["data"]
    original = json.loads(json.dumps(legacy))

    version, migrated = projects.normalize_data(2, legacy)

    assert version == 3
    assert legacy == original
    assert migrated["simulation"]["empiricalPhonology"] is True
    assert migrated["simulation"]["calibration"]["isolation"] == 0.4
    assert migrated["schemaProfileId"] == "heuristic-default"  # legacy alias zůstává na hraně


def test_jazyk_se_smi_opakovat_v_nasledujicich_casovych_snimcich():
    """Časová osa drží stav stejného jazyka v každém roce řezu."""
    project = projects.Project(
        id="timeline",
        data={
            "timeSteps": [0, 100],
            "snapshots": {
                "0": {"nodes": [{"id": "proto"}], "edges": []},
                "100": {"nodes": [{"id": "proto"}, {"id": "child"}], "edges": []},
            },
        },
    )

    projects.save(project)
    assert projects.load("timeline").data["snapshots"]["100"]["nodes"][0]["id"] == "proto"


def test_neplatna_reference_je_srozumitelna_chyba_a_nezapise_se():
    payload = json.loads((FIXTURES / "project_invalid_reference.json").read_text(encoding="utf-8"))
    project = projects.Project(id="broken", data=payload["data"])

    with pytest.raises(projects.ProjectError, match="neexistující ID: missing"):
        projects.save(project)
    assert not (projects.projects_dir() / "broken.json").exists()


def test_budouci_verze_se_neotevre_ani_neprepise(izolovana_slozka):
    path = izolovana_slozka / "future.json"
    contents = (FIXTURES / "project_future.json").read_text(encoding="utf-8")
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(projects.ProjectError, match="novější schéma 999"):
        projects.load("future")
    assert path.read_text(encoding="utf-8") == contents


def test_prezije_opakovane_ulozeni():
    projects.save(projects.Project(id="demo", data={"v": 1}))
    projects.save(projects.Project(id="demo", data={"v": 2}))
    assert projects.load("demo").data == {"v": 2}


def test_mapovy_podklad_se_uklada_s_meritkem_a_viditelnosti():
    projects.save(
        projects.Project(
            id="demo",
            data={
                "mapBackground": {
                    "dataUrl": "data:image/png;base64,cG5n",
                    "scale": 140,
                    "opacity": 0.45,
                }
            },
        )
    )

    background = projects.load("demo").data["mapBackground"]
    assert background == {
        "dataUrl": "data:image/png;base64,cG5n",
        "scale": 140.0,
        "opacity": 0.45,
    }


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
    assert ids == sorted(ids, key=lambda i: projects.load(i).updated_at, reverse=True)


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


@pytest.mark.parametrize(
    "project_id",
    ["indoevropský-fantasy-jazyk", "český", "muj-svet", "日本語", "a-1_b"],
)
def test_id_smi_mit_diakritiku(project_id):
    """
    Projekt se jmenuje podle toho, co uživatel napíše. Odmítat diakritiku
    znamená, že "indoevropský-fantasy-jazyk" nejde uložit vůbec.
    """
    projects.save(projects.Project(id=project_id, data={"x": 1}))
    assert projects.load(project_id).data == {"x": 1}


def test_id_se_normalizuje_na_nfc():
    """
    "ý" jde zapsat jedním znakem i jako "y" + háček. Bez sjednocení by se
    projekt uložil pod jedním zápisem a hledal pod druhým.
    """
    import unicodedata

    nfc = unicodedata.normalize("NFC", "ý-projekt")
    nfd = unicodedata.normalize("NFD", "ý-projekt")
    assert nfc != nfd

    projects.save(projects.Project(id=nfc, name="Původní"))
    assert projects.load(nfd).name == "Původní"
    assert len(projects.list_projects()) == 1


def test_docasny_soubor_neni_videt_jako_projekt(izolovana_slozka):
    """Rozepsaný zápis se nesmí objevit ve výpisu projektů."""
    projects.save(projects.Project(id="hotovy"))
    (izolovana_slozka / ".tmp-abc.json.tmp").write_text("{}", encoding="utf-8")

    assert [p["id"] for p in projects.list_projects()] == ["hotovy"]
