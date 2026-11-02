import math

import pytest

from cinecam import noyau as n
from cinecam.inactivite import ecart_ms
from cinecam.mesure import Mesure


def proche(a, b, tol=1e-9):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


# ------------------------------------------------------------- trajectoire
def test_tourne_quart_de_tour_autour_de_z():
    assert proche(n.tourne((1, 0, 0), (0, 0, 1), math.pi / 2), (0, 1, 0))


def test_pose_initiale_garde_distance_et_impose_inclinaison():
    p = n.pose_initiale((100, 0, 0), (0, 0, 0), (0, 0, 1), 30)
    assert math.isclose(n.norme(p.oeil), 100)
    assert math.isclose(p.oeil[2], 100 * math.sin(math.radians(30)))
    assert p.oeil[1] == pytest.approx(0)  # azimut gardé
    assert p.haut == (0, 0, 1)


def test_pose_initiale_recentre_sur_le_modele():
    p = n.pose_initiale((10, 0, 0), (0, 0, 0), (0, 0, 1), 0, nouvelle_cible=(5, 5, 5))
    assert p.cible == (5, 5, 5)
    assert proche(p.oeil, (15, 5, 5))


def test_pose_initiale_vue_de_dessus_ne_plante_pas():
    p = n.pose_initiale((0, 0, 50), (0, 0, 0), (0, 0, 1), 20)
    assert math.isclose(n.norme(p.oeil), 50)
    assert p.oeil[2] == pytest.approx(50 * math.sin(math.radians(20)))


def test_pose_initiale_axe_y():
    p = n.pose_initiale((0, 0, 80), (0, 0, 0), (0, 1, 0), 20)
    assert p.oeil[1] == pytest.approx(80 * math.sin(math.radians(20)))


def test_orbite_garde_cible_distance_et_hauteur():
    depart = n.pose_initiale((100, 0, 0), (1, 2, 3), (0, 0, 1), 20)
    for angle in (0, 45, 90, 180, 359):
        p = n.pose_a(depart, (0, 0, 1), angle)
        assert p.cible == depart.cible
        assert math.isclose(n.norme(n.soustrait(p.oeil, p.cible)),
                            n.norme(n.soustrait(depart.oeil, depart.cible)))
        assert math.isclose(p.oeil[2], depart.oeil[2])


def test_angle_au_temps_independant_de_la_cadence():
    assert n.angle_au_temps(10, 6, 1) == pytest.approx(60)
    assert n.angle_au_temps(60, 6, 1) == pytest.approx(0)       # un tour par minute
    assert n.angle_au_temps(10, 6, -1) == pytest.approx(300)
    assert n.angle_au_temps(-1, 6, 1) == 0


def test_axe_le_plus_proche():
    assert n.axe_le_plus_proche((0.1, 0.2, 0.97)) == (0, 0, 1)
    assert n.axe_le_plus_proche((0.1, -0.99, 0.1)) == (0, 1, 0)


def test_centre_boite():
    assert n.centre_boite((0, 0, 0), (10, 20, 30)) == (5, 10, 15)


# ------------------------------------------------------------- réglages
def test_reglages_par_defaut():
    r = n.Reglages.depuis_dict(None)
    # Calés sur le viewer MobPrez, sauf le délai (60 s : Fusion est un outil de travail).
    assert (r.delai_s, r.vitesse_deg_s, r.inclinaison_deg, r.recadrage_s) == (60.0, 2.4, 35.0, 6.0)
    assert (r.restaurer_vue, r.actif) == (False, True)


def test_reglages_bornes_et_valeurs_invalides():
    r = n.Reglages.depuis_dict({"delai_s": 1, "vitesse_deg_s": "abc", "cadence_hz": 1000,
                                "restaurer_vue": "non", "axe": "Z", "sens": -5, "inconnu": 3,
                                "inclinaison_deg": float("nan")})
    assert r.delai_s == 5.0
    assert r.vitesse_deg_s == 2.4
    assert r.cadence_hz == 60.0
    assert r.restaurer_vue is False
    assert r.axe == "z"
    assert r.sens == -1
    assert r.inclinaison_deg == 35.0


def test_reglages_aller_retour():
    r = n.Reglages(delai_s=30, actif=False)
    assert n.Reglages.depuis_dict(r.vers_dict()) == r


# ------------------------------------------------------------- machine
def machine(**k):
    return n.Machine(n.Reglages(delai_s=60, vitesse_deg_s=6, **k))


def test_veille_puis_demarrage_apres_le_delai():
    m = machine()
    assert m.etape(59.9, 0).type == n.RIEN
    assert m.etape(60, 100).type == n.DEMARRER
    assert m.etat == n.ROTATION
    a = m.etape(65, 105)
    assert a.type == n.PAS and a.angle_deg == pytest.approx(n.angle_au_temps(5, 6, 1, 6))
    a = m.etape(70, 110)
    assert a.angle_deg == pytest.approx(6 * (3 + 4))     # 6 s de montée valent 3 s à pleine vitesse


def test_reprise_des_que_l_utilisateur_bouge():
    m = machine(restaurer_vue=True)
    m.etape(60, 0)
    a = m.etape(0.2, 3)
    assert a.type == n.ARRETER and a.restaurer is True
    assert m.etat == n.VEILLE
    assert m.etape(5, 8).type == n.RIEN   # repart de zéro : il faut de nouveau 60 s


def test_reprise_par_defaut_arret_net_sans_restaurer():
    m = machine()
    m.etape(60, 0)
    assert m.etape(0.3, 1).type == n.ARRETER   # moindre saisie : arrêt
    assert m.etape(0, 1).restaurer is False


def test_pas_porte_le_temps_ecoule():
    m = machine()
    m.etape(60, 100)
    assert m.etape(62, 102.5).t_s == pytest.approx(2.5)


def test_pas_de_demarrage_si_occupe_ou_inactivite_inconnue():
    m = machine()
    assert m.etape(120, 0, occupe=True).type == n.RIEN
    assert m.etape(None, 0).type == n.RIEN


def test_commande_lancee_pendant_la_rotation_arrete():
    m = machine()
    m.etape(60, 0)
    assert m.etape(61, 1, occupe=True).type == n.ARRETER


def test_bouton_arret_pendant_rotation_et_remise_en_marche():
    m = machine()
    m.etape(60, 0)
    a = m.basculer(False)
    assert a.type == n.ARRETER and m.etat == n.ARRET
    assert m.etape(500, 10).type == n.RIEN
    m.basculer(True)
    assert m.etat == n.VEILLE


def test_machine_creee_inactive():
    m = n.Machine(n.Reglages(actif=False))
    assert m.etat == n.ARRET and m.etape(999, 0).type == n.RIEN


def test_intervalle_de_tic():
    m = machine(cadence_hz=30)
    assert m.intervalle_tic_s() == 0.5
    m.etape(60, 0)
    assert m.intervalle_tic_s() == pytest.approx(1 / 30)


def test_echec_revient_en_veille():
    m = machine()
    m.etape(60, 0)
    m.echec()
    assert m.etat == n.VEILLE


# ------------------------------------------------------------- divers
def test_ecart_tickcount_reboucle():
    assert ecart_ms(100, 50) == 50
    assert ecart_ms(10, 0xFFFFFFF0) == 26


def test_mesure():
    m = Mesure()
    assert m.resume() == {"n": 0}
    for v in (10, 20, 30):
        m.ajoute(v)
    assert m.resume()["moy"] == 20 and m.resume()["max"] == 30


# ------------------------------------------------------------- trajet (voyage souple + rotation)
def test_adoucir():
    assert n.adoucir(0) == 0 and n.adoucir(1) == 1 and n.adoucir(0.5) == pytest.approx(0.5)
    assert n.adoucir(-3) == 0 and n.adoucir(9) == 1
    assert n.adoucir(0.1) < 0.1 and n.adoucir(0.9) > 0.9   # démarre et arrive en douceur


def trajet(**k):
    # Vue de départ : de face (axe X), à plat, 100 cm de la cible à l'origine. Arrivée : cible (10,0,0),
    # 50 cm, 35° au-dessus de l'horizon.
    base = dict(axe=(0, 0, 1), oeil0=(100, 0, 0), cible0=(0, 0, 0), cible1=(10, 0, 0),
                distance1=50, elevation1_deg=35, duree_s=6)
    base.update(k)
    return n.Trajet(**base)


def test_trajet_part_exactement_de_la_vue_courante():
    p = trajet().pose(0, 0)
    assert proche(p.oeil, (100, 0, 0)) and p.cible == (0, 0, 0) and p.haut == (0, 0, 1)


def test_trajet_arrive_au_cadrage_a_35_degres():
    tr = trajet()
    p = tr.pose(6, 0)
    rel = n.soustrait(p.oeil, p.cible)
    assert proche(p.cible, (10, 0, 0))
    assert n.norme(rel) == pytest.approx(50)
    assert math.degrees(math.asin(rel[2] / 50)) == pytest.approx(35)
    assert proche(tr.pose(60, 0).oeil, p.oeil)   # après le voyage, plus rien ne glisse


def test_trajet_tourne_pendant_le_voyage():
    tr = trajet()
    a, b = tr.pose(3, 0), tr.pose(3, 90)
    assert a.cible == b.cible
    assert n.norme(n.soustrait(a.oeil, a.cible)) == pytest.approx(n.norme(n.soustrait(b.oeil, b.cible)))
    rel = n.soustrait(b.oeil, b.cible)
    assert rel[0] == pytest.approx(0, abs=1e-9) and rel[1] > 0   # quart de tour, sens trigonométrique


def test_trajet_a_mi_course():
    p = trajet().pose(3, 0)
    assert proche(p.cible, (5, 0, 0))
    assert n.norme(n.soustrait(p.oeil, p.cible)) == pytest.approx(75)


def test_trajet_sans_voyage_saute_au_cadrage():
    p = trajet(duree_s=0).pose(0, 0)
    assert proche(p.cible, (10, 0, 0))


def test_trajet_depart_vue_de_dessus():
    p = trajet(oeil0=(0, 0, 100)).pose(0, 0)
    assert proche(p.oeil, (0, 0, 100), 1e-6)
    p6 = trajet(oeil0=(0, 0, 100)).pose(6, 0)
    assert n.soustrait(p6.oeil, p6.cible)[2] == pytest.approx(50 * math.sin(math.radians(35)))


def test_trajet_etendue_orthographique():
    tr = trajet(etendue0=40, etendue1=20)
    assert tr.etendue(0) == 40 and tr.etendue(3) == pytest.approx(30) and tr.etendue(6) == 20
    assert trajet().etendue(3) is None


# ------------------------------------------------------------- départ en douceur
def test_rotation_part_de_zero_et_monte_sans_a_coup():
    v, montee = 2.4, 6.0
    pas = 1 / 30
    vitesses = [(n.angle_au_temps(t + pas, v, 1, montee) - n.angle_au_temps(t, v, 1, montee)) / pas
                for t in [i * pas for i in range(int(10 / pas))]]
    assert vitesses[0] < 0.01 * v                      # quasi immobile au départ
    assert all(b >= a - 1e-9 for a, b in zip(vitesses, vitesses[1:]))   # ne fait que monter
    assert vitesses[-1] == pytest.approx(v, rel=1e-6)   # pleine vitesse après la montée
    sauts = [abs(b - a) for a, b in zip(vitesses, vitesses[1:])]
    assert max(sauts) < 0.02 * v                        # aucune marche d'un pas à l'autre


def test_rotation_continue_a_la_fin_de_la_montee():
    avant, apres = n.angle_au_temps(5.999, 2.4, 1, 6), n.angle_au_temps(6.001, 2.4, 1, 6)
    assert (apres - avant) / 0.002 == pytest.approx(2.4, rel=1e-3)


def test_sans_montee_vitesse_pleine_tout_de_suite():
    assert n.angle_au_temps(10, 6, 1, 0) == pytest.approx(60)


def test_cadrage_englobe_la_boite():
    centre, rayon = n.cadrage((0, 0, 0), (60, 40, 80), marge=1.0)
    assert proche(centre, (30, 20, 40))
    for x in (0, 60):
        for y in (0, 40):
            for z in (0, 80):
                assert n.norme(n.soustrait((x, y, z), centre)) <= rayon + 1e-9


def test_distance_perspective_fait_tenir_la_sphere():
    d = n.distance_perspective(50, math.radians(60))
    assert d == pytest.approx(100)          # sin(30°) = 0,5
    assert n.distance_perspective(50, 0) > 0
