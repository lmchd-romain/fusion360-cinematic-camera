"""Création d'animation pas à pas, avec un faux storyboard : enregistre, n'enregistre qu'en lisse, ou jamais."""
import sys
import types

import pytest

from tests import faux_adsk


class FauxCamera:
    isSmoothTransition = False


class FauxVue:
    def __init__(self, sb):
        self.sb = sb

    @property
    def camera(self):
        return FauxCamera()

    @camera.setter
    def camera(self, cam):
        self.sb.vue_posee(cam.isSmoothTransition)


class FauxStoryboard:
    def __init__(self, enregistre_si):
        self.enregistre_si = enregistre_si    # "toujours", "lisse", "jamais"
        self.isViewRecordingOn = False
        self.playheadPosition = 0.0
        self.end = 0.0
        self.isActive = False

    def activate(self):
        self.isActive = True

    def vue_posee(self, lisse):
        if not self.isViewRecordingOn:
            return
        if self.enregistre_si == "toujours" or (self.enregistre_si == "lisse" and lisse):
            self.end = max(self.end, self.playheadPosition)


@pytest.fixture
def module(monkeypatch):
    faux_adsk.installer()
    from cinecam import animation, noyau
    yield animation, noyau
    for n in [n for n in sys.modules if n.startswith("adsk") or n.startswith("cinecam")]:
        del sys.modules[n]


def jouer(animation, noyau, monkeypatch, enregistre_si, **reglages):
    sb = FauxStoryboard(enregistre_si)
    gestion = types.SimpleNamespace(isAnimationWorkspaceActive=True, recordingMode=0,
                                    storyboards=types.SimpleNamespace(add=lambda propre: sb, count=1))
    monkeypatch.setattr(animation, "verifier", lambda app: gestion)
    vue = FauxVue(sb)

    class Pilote:
        def __init__(self, app, log):
            self.vue = vue
            self.rayon = 50.0

        def preparer(self, reglages, duree, boite=None):
            return noyau.Trajet((0, 0, 1), (100, 0, 0), (0, 0, 0), (0, 0, 0), 100, 35, 0)

        def _appliquer(self, pose, etendue=None):
            vue.camera = FauxCamera()

    monkeypatch.setattr(animation, "PiloteCamera", Pilote)
    app = types.SimpleNamespace(userInterface=types.SimpleNamespace(commandDefinitions=types.SimpleNamespace(count=0)))
    resultat = {}
    log = types.SimpleNamespace(info=lambda *a: None, error=lambda *a: None)
    pas = 0
    for _ in animation.etapes(app, noyau.Reglages(**({"anim_duree_s": 150.0} | reglages)), log, resultat):
        pas += 1
    return sb, resultat, pas


def test_enregistre_en_direct(module, monkeypatch):
    animation, noyau = module
    sb, r, _ = jouer(animation, noyau, monkeypatch, "toujours")
    assert r["methode"] == "directe" and r["vues"] > 72 and r["boucle"]
    assert sb.end == pytest.approx(150) and sb.playheadPosition == 0


def test_repli_sur_la_transition_lisse(module, monkeypatch):
    animation, noyau = module
    sb, r, _ = jouer(animation, noyau, monkeypatch, "lisse")
    assert r["methode"] == "lisse" and sb.end == pytest.approx(150)


def test_abandon_clair_si_fusion_n_enregistre_rien(module, monkeypatch):
    animation, noyau = module
    with pytest.raises(animation.ErreurAnimation, match="aucune vue"):
        jouer(animation, noyau, monkeypatch, "jamais")


def test_chaque_mouvement_se_cree(module, monkeypatch):
    animation, noyau = module
    from cinecam import mouvements
    for m in mouvements.CATALOGUE:
        sb, r, _ = jouer(animation, noyau, monkeypatch, "toujours", anim_mouvement=m.nom, anim_duree_s=12.0,
                         anim_zoom_pct=150.0)
        assert r["mouvement"] == m.libelle and sb.end >= 12.0
