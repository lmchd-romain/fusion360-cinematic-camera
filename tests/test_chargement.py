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
    assert a.ID_CMD in ui.commandDefinitions.d
    assert a.ID_CMD in ui.allToolbarPanels.d["SolidScriptsAddinsPanel"].controls.d
    assert len(app.evenements[a.ID_EVENEMENT].handlers) == 1
    assert (a.DOSSIER / "reglages.json").exists()
    time.sleep(1.2)
    assert app.tirs == 1  # un seul tir tant que le tic n'a pas été traité
    # Fusion traite le tic : pas de vue → occupé → rien ne bouge, nouveau tir permis
    app.evenements[a.ID_EVENEMENT].handlers[0].notify(None)
    time.sleep(0.7)
    assert app.tirs == 2
    # Bouton : passe en arrêt, réglage écrit
    ui.commandDefinitions.d[a.ID_CMD].commandCreated.handlers[0].notify(None)
    assert '"actif": false' in (a.DOSSIER / "reglages.json").read_text()
    assert "ARRÊT" in ui.messages[-1][0]
    mod.stop(None)
    assert a.ID_CMD not in ui.commandDefinitions.d
    assert not ui.allToolbarPanels.d["SolidScriptsAddinsPanel"].controls.d
    assert a.ID_EVENEMENT not in app.evenements
    assert not any(t.name == "CinematicCameraVeilleur" for t in __import__("threading").enumerate())


def test_run_nettoie_un_arret_incomplet(addin):
    mod, a, app = addin
    mod.run(None)
    mod.run(None)  # deuxième run sans stop : pas d'erreur de doublon
    assert len(app.evenements[a.ID_EVENEMENT].handlers) == 1
    mod.stop(None)
