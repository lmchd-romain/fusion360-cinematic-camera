"""Recette automatique : chargement avec un faux adsk, mesures pures, catalogue ↔ ETAT.md.

Le moteur est une copie de celui de TimelineManager (dépôt fusion360-test-proof-of-concept)."""
import importlib
import importlib.util
import math
import re
import sys
import types
from pathlib import Path

import pytest

from tests import faux_adsk

RACINE = Path(__file__).resolve().parent.parent
RECETTE = RACINE / "essai" / "recette"


def charger(nom, chemin):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nom] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def recette(tmp_path):
    app = faux_adsk.installer()
    sys.modules["adsk"].doEvents = lambda: None
    sys.modules["adsk"].autoTerminate = lambda v: None
    sys.modules["adsk.core"].DocumentTypes = types.SimpleNamespace(FusionDesignDocumentType=0)
    mod = charger("recette_camera_test", RECETTE / "recette.py")
    mod.RESULTATS = tmp_path
    yield mod, app
    for n in [n for n in sys.modules if n.startswith("adsk")]:
        del sys.modules[n]
    for n in ("recette_camera_test", "recette_camera_moteur"):
        sys.modules.pop(n, None)


def test_catalogue_coherent_avec_etat(recette):
    mod, _ = recette
    codes = [d.code for d in mod.CATALOGUE]
    assert len(set(codes)) == len(codes)
    etat = (RACINE / "docs" / "ETAT.md").read_text(encoding="utf-8")
    for d in mod.CATALOGUE:
        assert d.mode in (mod.M.AUTO, mod.M.CAPTURE, mod.M.MAIN)
        assert re.search(rf"\| {re.escape(d.code)} \|[^\n]*\| {re.escape(d.mode)} \|", etat), d.code
        if d.mode == mod.M.MAIN:
            assert d.geste


def test_vitesse_mesuree_avec_retour_a_moins_180(recette):
    mod, _ = recette
    echantillons = []
    for k in range(40):
        t = k / 30
        a = (170 + 12 * t * 10) % 360  # 120 °/s : passe de 180 à -180
        echantillons.append((t, a if a <= 180 else a - 360))
    assert mod.vitesse_mesuree(echantillons) == pytest.approx(120, rel=1e-6)
    assert mod.vitesse_mesuree([(0, 0)]) is None


def test_elevation_et_azimut(recette):
    mod, _ = recette
    oeil = (math.cos(math.radians(35)), 0.0, math.sin(math.radians(35)))
    assert mod.elevation_deg(oeil, (0, 0, 0), (0, 0, 1)) == pytest.approx(35)
    assert mod.azimut_deg((0, 1, 0), (0, 0, 0), (1, 0, 0), (0, 1, 0)) == pytest.approx(90)


def test_recette_survit_a_un_fusion_en_panne_et_ecrit_son_rapport(recette, tmp_path):
    mod, app = recette
    app.activeDocument = types.SimpleNamespace(name="Meuble", activate=lambda: setattr(app, "rendu", True))

    def panne(*a):
        raise RuntimeError("pas de document dans le faux Fusion")

    app.documents = types.SimpleNamespace(add=panne)
    assert mod.lancer(synchrone=True).startswith("FINI")
    r = mod._recette
    assert app.rendu is True
    assert r.points["A1"].verdict == r.points["A2"].verdict == mod.M.A_REGARDER
    assert r.points["S1"].verdict == mod.M.OK  # le faux Fusion est au repos
    assert r.points["P4"].verdict == mod.M.KO
    assert r.points["R1"].verdict == mod.M.A_REGARDER
    assert list(tmp_path.glob("recette-*.md"))
    assert "Recette CinematicCamera" in mod.rapport()


def test_l_add_in_en_marche_est_neutralise_puis_rendu(recette, tmp_path):
    mod, app = recette
    noyau = importlib.import_module("cinecam.noyau")
    machine = noyau.Machine(noyau.Reglages(delai_s=60))
    machine.etat = noyau.ROTATION
    arrets = []
    pilote = types.SimpleNamespace(en_cours=True, arreter=lambda restaurer: arrets.append(restaurer))
    sys.modules["cinecam.addin"] = types.SimpleNamespace(_etat={"machine": machine, "pilote": pilote})
    vus = []

    def espion(r):
        vus.append(machine.reglages.delai_s)
        yield mod.M.Attendre(0)

    mod.BLOCS = [("espion", espion)]
    try:
        app.activeDocument = None
        assert mod.lancer(synchrone=True).startswith("FINI")
    finally:
        sys.modules.pop("cinecam.addin", None)
    assert vus == [3600.0]  # pendant la recette, l'add-in ne part pas tout seul
    assert arrets == [False] and machine.etat == noyau.VEILLE
    assert machine.reglages.delai_s == 60  # rendu à la fin
    assert mod._recette.infos["delai_addin_s"] == 60
