"""Chargement de l'add-in avec un faux adsk : run() pose bouton, événement et fil ; stop() retire tout."""
import importlib.util
import sys
import time
from pathlib import Path

import pytest

from tests import faux_adsk

RACINE = Path(__file__).resolve().parent.parent


@pytest.fixture
def addin(tmp_path, monkeypatch):
    app = faux_adsk.installer()
    spec = importlib.util.spec_from_file_location("CinematicCamera", RACINE / "CinematicCamera" / "CinematicCamera.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    from cinecam import addin as a
    monkeypatch.setattr(a, "FICHIER_REGLAGES", tmp_path / "reglages.json")
    monkeypatch.setattr(a, "DOSSIER", tmp_path)
    yield mod, a, app
    for n in [n for n in sys.modules if n.startswith("adsk")]:
        del sys.modules[n]


def test_run_puis_stop(addin):
    mod, a, app = addin
    ui = app.userInterface
    mod.run(None)
    panneau = ui.allToolbarPanels.d["SolidScriptsAddinsPanel"].controls.d
    for id_ in (a.ID_LANCER, a.ID_REGLAGES, a.ID_ANIMATION):
        assert id_ in ui.commandDefinitions.d
    assert a.ID_LANCER in panneau and a.ID_REGLAGES in panneau and panneau[a.ID_LANCER].isPromoted
    anim = ui.allToolbarPanels.d[a.ID_PANNEAU_ANIMATION].controls.d
    assert a.ID_ANIMATION in anim and a.ID_REGLAGES in anim
    assert ui.allToolbarPanels.d[a.ID_PANNEAU_ANIMATION].hote == "AnimationTab"   # pas dans OUTILS
    for id_, dossier in ((a.ID_LANCER, "icone"), (a.ID_REGLAGES, "icone_reglages"),
                         (a.ID_ANIMATION, "icone_animation")):
        icones = Path(ui.commandDefinitions.d[id_].ressources)
        assert icones.name == dossier
        assert (RACINE / "CinematicCamera" / "ressources" / dossier / "32x32.png").exists()
    assert len(app.evenements[a.ID_EVENEMENT].handlers) == 1
    assert (a.DOSSIER / "reglages.json").exists()
    time.sleep(1.2)
    assert app.tirs == 1  # un seul tir tant que le tic n'a pas été traité
    # Fusion traite le tic : pas de vue → occupé → rien ne bouge, nouveau tir permis
    app.evenements[a.ID_EVENEMENT].handlers[0].notify(None)
    time.sleep(0.7)
    assert app.tirs == 2
    # Bouton lancer sans vue : la machine repart au repos, sans erreur
    ui.commandDefinitions.d[a.ID_LANCER].commandCreated.handlers[0].notify(None)
    assert a._etat["machine"].etat == "veille"
    assert ui.commandDefinitions.d[a.ID_LANCER].controlDefinition.name == a.NOM_LANCER
    mod.stop(None)
    for id_ in (a.ID_LANCER, a.ID_REGLAGES, a.ID_ANIMATION):
        assert id_ not in ui.commandDefinitions.d
    assert not ui.allToolbarPanels.d["SolidScriptsAddinsPanel"].controls.d
    assert a.ID_PANNEAU_ANIMATION not in ui.allToolbarPanels.d
    assert a.ID_EVENEMENT not in app.evenements
    assert not any(t.name == "CinematicCameraVeilleur" for t in __import__("threading").enumerate())


def test_run_nettoie_un_arret_incomplet(addin):
    mod, a, app = addin
    mod.run(None)
    mod.run(None)  # deuxième run sans stop : pas d'erreur de doublon
    assert len(app.evenements[a.ID_EVENEMENT].handlers) == 1
    mod.stop(None)
