"""Mouvements de caméra : vues clés, coupes, boucles, zoom."""
import math

import pytest

from cinecam import mouvements as m
from cinecam import noyau as n

REP = m.Repere((0, 0, 0), 50.0, 100.0, (0, 0, 1), (1, 0, 0), (0, 1, 0))


def proche(a, b, tol=1e-6):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


@pytest.mark.parametrize("mv", m.CATALOGUE, ids=lambda mv: mv.nom)
def test_vues_dans_l_ordre_et_assez_serrees(mv):
    cles = m.cles(mv, 20.0, REP)
    temps = [c.t for c in cles]
    assert temps[0] == 0 and temps == sorted(temps) and len(set(temps)) == len(temps)
    assert temps[-1] == pytest.approx(20.0 + m.COUPE_S * sum(s.coupe for s in mv.segments))
    for a, b in zip(cles, cles[1:]):
        if b.t - a.t <= m.COUPE_S + 1e-9:
            continue                                     # coupe franche
        assert b.t - a.t <= m.INTERVALLE_MAX_S + 1e-9
        assert n.norme(n.soustrait(b.pose.oeil, a.pose.oeil)) / REP.distance < 2 * m.ECART_MAX


@pytest.mark.parametrize("mv", [mv for mv in m.CATALOGUE if mv.boucle], ids=lambda mv: mv.nom)
def test_les_boucles_finissent_ou_elles_commencent(mv):
    cles = m.cles(mv, 30.0, REP)
    assert proche(cles[0].pose.oeil, cles[-1].pose.oeil) and proche(cles[0].pose.cible, cles[-1].pose.cible)


def test_platine_vue_de_trois_quarts_a_la_bonne_distance():
    p = m.cles(m.PAR_NOM["platine"], 60, REP)[0].pose
    rel = n.soustrait(p.oeil, p.cible)
    assert n.norme(rel) == pytest.approx(100)
    assert math.degrees(math.asin(rel[2] / 100)) == pytest.approx(35)
    assert rel[0] > 0 and rel[1] == pytest.approx(0)      # du côté de la vue de départ


def test_zoom_rapproche():
    p = m.cles(m.PAR_NOM["platine"], 60, REP, zoom=2.0)[0]
    assert n.norme(n.soustrait(p.pose.oeil, p.pose.cible)) == pytest.approx(50) and p.facteur == 0.5


def test_edit_a_des_coupes_franches():
    cles = m.cles(m.PAR_NOM["edit"], 15, REP)
    coupes = [(a, b) for a, b in zip(cles, cles[1:]) if b.t - a.t <= m.COUPE_S + 1e-9]
    assert len(coupes) == 5
    assert all(n.norme(n.soustrait(b.pose.oeil, a.pose.oeil)) > 0.2 * REP.distance for a, b in coupes)


def test_travelling_en_ligne_droite():
    cles = m.cles(m.PAR_NOM["travelling"], 10, REP)
    d = n.soustrait(cles[-1].pose.oeil, cles[0].pose.oeil)
    for c in cles:
        r = n.soustrait(c.pose.oeil, cles[0].pose.oeil)
        assert n.norme(n.vectoriel(r, d)) / n.norme(d) < 1e-6        # sur la droite
        assert n.soustrait(c.pose.oeil, c.pose.cible) == pytest.approx(
            n.soustrait(cles[0].pose.oeil, cles[0].pose.cible))      # regard constant


def test_vue_de_dessus_garde_un_haut_valable():
    p = m.cles(m.PAR_NOM["dessus"], 20, REP)[0].pose
    regard = n.unitaire(n.soustrait(p.cible, p.oeil))
    assert abs(n.scalaire(regard, p.haut)) < math.cos(math.radians(4))


def test_reglages_d_animation_bornes_et_choix():
    r = n.Reglages.depuis_dict({"anim_mouvement": "EDIT", "anim_duree_s": 1, "anim_zoom_pct": 999})
    assert r.anim_mouvement == "edit" and r.anim_duree_s == 3 and r.anim_zoom_pct == 300
    assert n.Reglages.depuis_dict({"anim_mouvement": "inconnu"}).anim_mouvement == "platine"


def test_boite_des_pieces_choisies():
    import sys
    import types

    from tests import faux_adsk
    if "adsk" not in sys.modules:
        faux_adsk.installer()
    from cinecam import fusion_camera as fc
    P = lambda x, y, z: types.SimpleNamespace(x=x, y=y, z=z)  # noqa: E731
    a = types.SimpleNamespace(boundingBox=types.SimpleNamespace(minPoint=P(0, 0, 0), maxPoint=P(1, 1, 1)))
    b = types.SimpleNamespace(boundingBox=types.SimpleNamespace(minPoint=P(5, -2, 0), maxPoint=P(6, 0, 3)))
    assert fc.boite_de([a, b]) == ((0, -2, 0), (6, 1, 3))
    assert fc.boite_de([]) is None


def test_quatre_faces_s_arrete_entre_les_quarts():
    f = m.PAR_NOM["quatre_faces"].segments[0].cadre
    assert f(0.2).az == pytest.approx(90) and f(0.24).az == pytest.approx(90)     # pause
    assert f(0.5).az == pytest.approx(180) and f(1.0).az == pytest.approx(360)


REP_P = m.Repere((0, 0, 0), 50.0, 100.0, (0, 0, 1), (1, 0, 0), (0, 1, 0), angle=30.0)


def test_vertigo_garde_la_taille_du_modele():
    cles = m.cles(m.PAR_NOM["vertigo"], 10, REP_P)
    tailles = {round(n.norme(n.soustrait(c.pose.oeil, c.pose.cible)) * math.sin(math.radians(c.fov) / 2), 6)
               for c in cles}
    assert len(tailles) == 1
    fovs = [c.fov for c in cles]
    assert max(fovs) == pytest.approx(80) and min(fovs) == pytest.approx(14)
    assert all(abs(b.fov - a.fov) < m.FOV_MAX + 0.5 for a, b in zip(cles, cles[1:]))


def test_angle_de_vue_du_dialogue_et_vue_orthographique():
    c = m.cles(m.PAR_NOM["platine"], 60, REP_P, fov=90)[0]
    assert c.fov == 90
    assert n.norme(n.soustrait(c.pose.oeil, c.pose.cible)) == pytest.approx(
        100 * math.sin(math.radians(15)) / math.sin(math.radians(45)))
    assert m.cles(m.PAR_NOM["vertigo"], 10, REP)[0].fov is None        # orthographique : pas d'objectif
    assert m.cles(m.PAR_NOM["grand_angle"], 8, REP_P, fov=20)[0].fov == 95   # le mouvement garde le sien


def test_coups_de_zoom_resserrent_l_objectif():
    f = m.PAR_NOM["coups_zoom"].segments[0].cadre
    assert f(0).fov == 60 and f(0.2).fov == pytest.approx(38) and f(1).fov == pytest.approx(15)
