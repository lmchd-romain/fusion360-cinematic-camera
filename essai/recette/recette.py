"""Recette automatique de CinematicCamera.

Lancée par Claude Desktop à travers le MCP de Fusion (voir MESSAGE.md), ou à la main comme script :
Utilitaires → Scripts et compléments → Scripts → « + » → ce dossier → Exécuter. Pendant la recette
(≈ 2 min), ne touchez ni souris ni clavier : toute saisie arrête la rotation, c'est ce qu'on mesure.

Tout se joue dans un document NEUF (un caisson et un mur), jamais enregistré, refermé sans enregistrer ;
le document de Romain redevient actif à la fin. Rapport : ../resultats/recette-<horodatage>.json et .md,
images dans ../resultats/captures-<horodatage>/.

Trois parties :
- sonde (S*) : ce que Fusion permet (caméra, cadrage, inactivité) ;
- pilote (P*) : le moteur de CinematicCamera (PiloteCamera + trajectoire du noyau) joué comme l'add-in le
  joue, à 30 pas par seconde, sur une vraie vue : rotation mesurée, arrêt, vue rendue ;
- add-in en marche (R*) : l'add-in lancé par Romain, délai ramené à 3 s le temps de l'essai (remis
  ensuite), départ réel sur inactivité, arrêt sur un mouvement de souris simulé d'un pixel.

Fonctions pour le MCP : lancer(), etat(), juger(code, verdict, remarque), continuer(), rapport(), arreter().
"""

from __future__ import annotations

import importlib.util
import logging
import math
import sys
import time
import traceback
from pathlib import Path

ICI = Path(__file__).resolve().parent
ESSAI = ICI.parent
ADDIN = ESSAI.parent / "CinematicCamera"
RESULTATS = ESSAI / "resultats"
NOM_MODULE = "recette_camera"
ID_EVENEMENT = "LmchdRecetteCamera"
ID_ADDIN = "lmchdCinematicCamera_basculer"
COMMANDE_REPOS = "SelectCommand"
VITESSE_ATTENDUE = 2.4  # °/s : un tour en 150 s, comme MobPrez (choix de Romain)
DUREE_TOUR_S = 9.0  # rotation mesurée : 6 s de recadrage + 3 s de croisière
DELAI_ESSAI_S = 3.0


def _charger_moteur():
    nom = f"{NOM_MODULE}_moteur"
    if nom not in sys.modules:
        spec = importlib.util.spec_from_file_location(nom, ICI / "moteur.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[nom] = mod
        spec.loader.exec_module(mod)
    return sys.modules[nom]


M = _charger_moteur()
D = M.Definition

if str(ADDIN) not in sys.path:
    sys.path.insert(0, str(ADDIN))

CATALOGUE = [
    D("A1", "Add-in chargé", M.AUTO, "commande « Caméra auto » définie et posée dans un panneau"),
    D("A2", "Réglages de l'add-in en marche", M.AUTO, "actif, vitesse 2,4 °/s (un tour en 150 s)"),
    D("S1", "Commande au repos", M.AUTO, "ui.activeCommand = SelectCommand quand rien ne tourne"),
    D("S1b", "Orientation de modélisation lisible", M.AUTO, "Y ou Z en haut, lu dans les préférences"),
    D("S2", "Inactivité Windows lisible", M.AUTO, "GetLastInputInfo rend un nombre de secondes"),
    D("S3", "Écrire la caméra est rapide", M.AUTO, "60 écritures, p95 < 5 ms"),
    D("S4", "isFitView cadre tout le modèle", M.AUTO, "les 8 coins de la boîte du modèle dans la vue"),
    D("P1", "Départ sans saut", M.AUTO, "aucun pas de caméra > 8 % de la distance pendant le recadrage"),
    D("P2", "Cadrage d'arrivée", M.AUTO, "cible au centre du modèle (≤ 2 % de sa diagonale), vue à 35° ± 1°"),
    D("P3", "Modèle entier pendant le tour", M.AUTO, "les 8 coins dans la vue à 4 instants"),
    D("P4", "Vitesse mesurée", M.AUTO, "2,4 °/s ± 5 % : un tour en 150 s"),
    D("P5", "Cadence", M.AUTO, "≥ 25 pas/s, pas p95 < 5 ms"),
    D("P6", "Document intact, murs gardés", M.AUTO,
      "timeline inchangée, chaque corps garde sa visibilité (rien n'est masqué pendant le tour)"),
    D("P7", "Arrêt net", M.AUTO, "après l'arrêt, la vue reste exactement où elle est"),
    D("P8", "Vue rendue (option restaurer_vue)", M.AUTO, "la vue revient à celle d'avant le tour"),
    D("R1", "Départ réel sur inactivité", M.AUTO, "l'add-in tourne la vue après 3 s sans saisie"),
    D("R2", "Arrêt réel sur la souris", M.AUTO, "un mouvement de souris d'un pixel arrête la rotation en < 1 s"),
    D("R3", "Pas de rotation pendant une commande", M.AUTO, "commande ouverte : la vue ne bouge pas"),
    D("R4", "Ctrl+Z après le tour", M.AUTO,
      "une annulation défait la dernière vraie opération (nom du mur), pas la vue : la caméra ne laisse "
      "rien dans l'historique d'annulation"),
    D("K0", "Vue de départ", M.CAPTURE, "le caisson et le mur, vus de biais, décentrés"),
    D("K1", "Pendant le tour", M.CAPTURE,
      "modèle centré et entier, vu en trois-quarts d'en haut (35°), mur visible"),
    D("K2", "Un quart de tour plus loin", M.CAPTURE, "même cadrage, vu d'un autre côté, mur visible"),
    D("K3", "Vue rendue", M.CAPTURE, "identique à K0"),
    D("M1", "Vraie souris pendant un vrai tour", M.MAIN,
      "le départ glisse sans saut d'image ; la vue s'arrête net à la moindre saisie",
      geste="Ouvrir un design, ne plus toucher à rien 60 s : regarder le départ. Puis bouger la souris."),
    D("M2", "Bouton marche / arrêt", M.MAIN, "message « ARRÊT », plus de rotation ; recliquer → « MARCHE »",
      geste="Utilitaires → Compléments → Caméra auto (deux fois)."),
    D("M3", "Icône claire et sombre", M.MAIN, "icône nette et lisible dans les deux thèmes",
      geste="Regarder l'icône « Caméra auto » en thème clair puis sombre."),
]


# --------------------------------------------------------------------------- outils


def _adsk():
    import adsk.core  # noqa: PLC0415
    import adsk.fusion  # noqa: PLC0415

    return adsk


def _app():
    return _adsk().core.Application.get()


def _cam():
    from cinecam import fusion_camera, noyau  # noqa: PLC0415

    return fusion_camera, noyau


def _xyz(p):
    return (p.x, p.y, p.z)


def _log():
    log = logging.getLogger("recette_camera")
    if not log.handlers:
        log.addHandler(logging.NullHandler())
    return log


class DocCamera:
    """Document neuf : un caisson 60 × 40 × 72 cm et un mur derrière, vus de biais."""

    def __init__(self):
        adsk = _adsk()
        app = _app()
        self.doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        self.design = adsk.fusion.Design.cast(app.activeProduct)
        self.design.designType = adsk.fusion.DesignTypes.ParametricDesignType
        root = self.design.rootComponent
        p3 = adsk.core.Point3D.create

        def boite(nom, x0, y0, x1, y1, h):
            sk = root.sketches.add(root.xYConstructionPlane)
            sk.sketchCurves.sketchLines.addTwoPointRectangle(p3(x0, y0, 0), p3(x1, y1, 0))
            f = root.features.extrudeFeatures.addSimple(
                sk.profiles.item(0), adsk.core.ValueInput.createByReal(h),
                adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
            f.bodies.item(0).name = nom
            return f

        boite("Caisson", 0, 0, 60, 40, 72)
        boite("Mur", -60, 50, 120, 60, 250)
        self.root = root
        self.tl = self.design.timeline
        self.vue = app.activeViewport

    def visibilites(self) -> dict:
        corps = self.root.bRepBodies
        return {corps.item(k).name: bool(corps.item(k).isVisible) for k in range(corps.count)}

    def boite(self):
        return self.root.boundingBox

    def vue_de_biais(self):
        adsk = _adsk()
        cam = self.vue.camera
        cam.target = adsk.core.Point3D.create(0, 0, 0)
        cam.eye = adsk.core.Point3D.create(260, -380, 90)
        cam.isSmoothTransition = False
        self.vue.camera = cam
        return self.vue.camera

    def fermer(self):
        try:
            self.doc.close(False)
        except Exception:  # noqa: BLE001
            pass


def coins_hors_vue(vue, boite) -> int:
    adsk = _adsk()
    mn, mx = boite.minPoint, boite.maxPoint
    hors = 0
    for x in (mn.x, mx.x):
        for y in (mn.y, mx.y):
            for z in (mn.z, mx.z):
                q = vue.modelToViewSpace(adsk.core.Point3D.create(x, y, z))
                if q is None or not (0 <= q.x <= vue.width and 0 <= q.y <= vue.height):
                    hors += 1
    return hors


def elevation_deg(oeil, cible, axe) -> float:
    _, noyau = _cam()
    d = noyau.soustrait(oeil, cible)
    return math.degrees(math.asin(max(-1.0, min(1.0, noyau.scalaire(d, axe) / noyau.norme(d)))))


def azimut_deg(oeil, cible, h0, p0) -> float:
    _, noyau = _cam()
    d = noyau.soustrait(oeil, cible)
    return math.degrees(math.atan2(noyau.scalaire(d, p0), noyau.scalaire(d, h0)))


def vitesse_mesuree(echantillons) -> float | None:
    """°/s par moindres carrés sur les azimuts dépliés [(t, azimut)]."""
    if len(echantillons) < 3:
        return None
    ts, az, prec, tour = [], [], None, 0.0
    for t, a in echantillons:
        if prec is not None:
            if a - prec > 180:
                tour -= 360
            elif a - prec < -180:
                tour += 360
        prec = a
        ts.append(t)
        az.append(a + tour)
    n = len(ts)
    mt, ma = sum(ts) / n, sum(az) / n
    num = sum((t - mt) * (a - ma) for t, a in zip(ts, az))
    den = sum((t - mt) ** 2 for t in ts)
    return abs(num / den) if den else None


def inactivite_s():
    if sys.platform != "win32":
        return None
    try:
        from cinecam.inactivite import creer_lecteur  # noqa: PLC0415

        return creer_lecteur()()
    except Exception:  # noqa: BLE001
        return None


def bouger_souris(px: int = 2) -> int:
    """Mouvement de souris simulé (aller-retour de px pixels) : compte comme une saisie pour Windows.
    Rend le nombre d'entrées acceptées (0 hors Windows)."""
    if sys.platform != "win32":
        return 0
    import ctypes  # noqa: PLC0415
    from ctypes import wintypes  # noqa: PLC0415

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class _U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("_place", ctypes.c_byte * 32)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", _U)]

    entrees = (INPUT * 2)()
    for k, dx in enumerate((px, -px)):
        entrees[k].type = 0  # INPUT_MOUSE
        entrees[k].mi = MOUSEINPUT(dx, 0, 0, 0x0001, 0, 0)  # MOUSEEVENTF_MOVE
    return int(ctypes.windll.user32.SendInput(2, entrees, ctypes.sizeof(INPUT)))


def trouver_annuler(ui, memoire):
    for cid in ("UndoCommand", "Undo", "CommonUndoCommand", "FusionUndoCommand"):
        d = ui.commandDefinitions.itemById(cid)
        if d is not None:
            memoire["annuler"] = cid
            return d
    defs = ui.commandDefinitions
    trouves = [defs.item(k).id for k in range(defs.count)
               if "undo" in defs.item(k).id.lower() and "redo" not in defs.item(k).id.lower()]
    memoire["annuler_candidats"] = trouves[:20]
    if trouves:
        memoire["annuler"] = trouves[0]
        return defs.itemById(trouves[0])
    return None


def capturer(chemin: Path) -> bool:
    vue = _app().activeViewport
    return bool(vue and vue.saveAsImageFile(str(chemin), 1280, 800))


def _proche(a, b, tol) -> bool:
    _, noyau = _cam()
    return noyau.norme(noyau.soustrait(a, b)) <= tol


# --------------------------------------------------------------------------- blocs


def b_contexte(r):
    r.declarer_bloc(("A1", "A2", "S1", "S1b", "S2"))
    app = _app()
    ui = app.userInterface
    d = ui.commandDefinitions.itemById(ID_ADDIN)
    panneau = None
    for p in ("SolidScriptsAddinsPanel", "SolidInspectPanel"):
        tp = ui.allToolbarPanels.itemById(p)
        if tp is not None and tp.controls.itemById(ID_ADDIN) is not None:
            panneau = p
    r.verifier("A1", d is not None and panneau is not None, {"definition": d is not None, "panneau": panneau},
               "" if d is not None else "Add-in pas lancé : Scripts et compléments → Compléments → CinematicCamera → "
                                         "Exécuter. Les points A2 et R* en dépendent.", sinon=M.A_REGARDER)
    etat = _etat_addin()
    if etat is None:
        r.point("A2", M.A_REGARDER, detail="add-in pas lancé : réglages illisibles")
    else:
        reg = etat["machine"].reglages
        m = {"actif": reg.actif, "vitesse_deg_s": reg.vitesse_deg_s, "delai_s": reg.delai_s,
             "tour_s": round(360 / reg.vitesse_deg_s, 1)}
        bon = reg.actif and abs(reg.vitesse_deg_s - VITESSE_ATTENDUE) < 1e-6
        detail = ""
        if abs(reg.vitesse_deg_s - VITESSE_ATTENDUE) > 1e-6:
            detail = "reglages.json a une autre vitesse : le supprimer puis Arrêter / Exécuter CinematicCamera"
        elif not reg.actif:
            detail = "add-in sur ARRÊT : cliquer « Caméra auto »"
        r.verifier("A2", bon, m, detail, sinon=M.A_REGARDER)
    cmd = ui.activeCommand
    r.verifier("S1", cmd == COMMANDE_REPOS, {"activeCommand": cmd},
               "" if cmd == COMMANDE_REPOS else "adopter cette valeur dans COMMANDE_REPOS (addin.py) si c'est "
                                                 "bien le repos", sinon=M.A_REGARDER)
    try:
        o = app.preferences.generalPreferences.defaultModelingOrientation
        noms = adsk_noms_orientation()
        r.point("S1b", M.OK, {"orientation": noms.get(o, o)})
    except Exception as e:  # noqa: BLE001
        r.point("S1b", M.A_REGARDER, {"erreur": str(e)}, "repli : axe le plus proche du haut de la vue")
    s = inactivite_s()
    r.verifier("S2", isinstance(s, (int, float)), {"inactivite_s": s})
    yield M.Attendre(0)


def adsk_noms_orientation() -> dict:
    o = _adsk().core.DefaultModelingOrientations
    return {getattr(o, n): n for n in dir(o) if not n.startswith("_") and isinstance(getattr(o, n), int)}


def _etat_addin():
    mod = sys.modules.get("cinecam.addin")
    etat = getattr(mod, "_etat", None) if mod is not None else None
    return etat if etat and "machine" in etat else None


def b_sonde(r):
    r.declarer_bloc(("S3", "S4"))
    adsk = _adsk()
    d = DocCamera()
    r.au_nettoyage(d.fermer)
    vue = d.vue
    cam0 = d.vue_de_biais()
    durees = []
    for i in range(60):
        cam = vue.camera
        t = time.perf_counter()
        cam.eye = adsk.core.Point3D.create(260 + i, -380, 90)
        cam.isSmoothTransition = False
        vue.camera = cam
        durees.append((time.perf_counter() - t) * 1000)
    durees.sort()
    p95 = durees[int(0.95 * len(durees))]
    r.verifier("S3", p95 < 5, {"p95_ms": p95, "max_ms": durees[-1]}, sinon=M.A_REGARDER)
    vue.camera = cam0
    yield M.Attendre(0.2)
    cam = vue.camera
    cam.isFitView = True
    cam.isSmoothTransition = False
    vue.camera = cam
    yield M.Attendre(0.3)
    hors = coins_hors_vue(vue, d.boite())
    r.verifier("S4", hors == 0, {"coins_hors_vue": hors})


def b_pilote(r):
    r.declarer_bloc(("K0", "P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "K1", "K2", "K3", "R4"))
    fusion_camera, noyau = _cam()
    app = _app()
    d = DocCamera()
    r.au_nettoyage(d.fermer)
    vue = d.vue
    depart = d.vue_de_biais()
    oeil_depart = _xyz(depart.eye)
    yield M.Attendre(0.5)
    yield M.Capture("K0", "Vue de départ : voit-on le caisson et le grand mur, de biais et décentrés ?")
    n_tl, vis0 = d.tl.count, d.visibilites()
    modif0 = d.doc.isModified
    reglages = noyau.Reglages()
    pilote = fusion_camera.PiloteCamera(app, _log())
    if not pilote.demarrer(reglages):
        r.point("P1", M.KO, detail="PiloteCamera.demarrer a refusé (pas de vue active ?)")
        return
    tr = pilote.trajet
    b = d.boite()
    centre = noyau.centre_boite(_xyz(b.minPoint), _xyz(b.maxPoint))
    diag = noyau.norme(noyau.soustrait(_xyz(b.maxPoint), _xyz(b.minPoint)))
    echantillons, sauts, hors, instants = [], [], [], [1.5, 4.0, 7.0, 8.8]
    precedent = oeil_depart
    t0 = time.perf_counter()
    while True:
        t = time.perf_counter() - t0
        if t > DUREE_TOUR_S:
            break
        angle = noyau.angle_au_temps(t, reglages.vitesse_deg_s, reglages.sens, reglages.recadrage_s)
        pilote.pas(t, angle)
        cam = vue.camera
        oeil, cible = _xyz(cam.eye), _xyz(cam.target)
        echantillons.append((t, oeil, cible))
        dist = noyau.norme(noyau.soustrait(oeil, cible)) or 1.0
        if t < reglages.recadrage_s + 0.2:
            sauts.append(noyau.norme(noyau.soustrait(oeil, precedent)) / dist)
        precedent = oeil
        if instants and t >= instants[0]:
            instants.pop(0)
            hors.append(coins_hors_vue(vue, b))
        yield M.Attendre(1 / reglages.cadence_hz)
    duree = time.perf_counter() - t0
    # P1 : aucun saut
    pire = max(sauts) if sauts else None
    r.verifier("P1", pire is not None and pire < 0.08, {"plus_grand_pas_sur_distance": pire, "pas": len(sauts)})
    # P2 : arrivée
    _, oeil, cible = echantillons[-1]
    m2 = {"ecart_cible_centre_cm": noyau.norme(noyau.soustrait(cible, centre)), "diagonale_cm": diag,
          "elevation_deg": elevation_deg(oeil, cible, pilote.axe), "axe": pilote.axe}
    bon_el = abs(m2["elevation_deg"] - 35) <= 1
    bon_centre = m2["ecart_cible_centre_cm"] <= 0.02 * diag
    r.point("P2", M.OK if bon_el and bon_centre else (M.KO if not bon_el else M.A_REGARDER), m2,
            "" if bon_centre else "Fusion cadre sur un autre centre que celui de la boîte : voir K1")
    # P3 : modèle entier
    r.verifier("P3", len(hors) == 4 and not any(hors), {"coins_hors_vue_aux_4_instants": hors})
    # P4 : vitesse
    croisiere = [(t, azimut_deg(o, c, tr.h0, tr.p0)) for t, o, c in echantillons if t >= reglages.recadrage_s + 0.3]
    v = vitesse_mesuree(croisiere)
    m4 = {"vitesse_deg_s": v, "tour_s": (360 / v) if v else None, "echantillons": len(croisiere)}
    r.verifier("P4", v is not None and abs(v - VITESSE_ATTENDUE) <= 0.05 * VITESSE_ATTENDUE, m4)
    # P5 : cadence
    m5 = {"pas_par_s": len(echantillons) / duree, "duree_pas_ms": pilote.duree_pas_ms.resume(),
          "intervalle_ms": pilote.intervalle_ms.resume()}
    p95 = m5["duree_pas_ms"].get("p95", 99)
    r.verifier("P5", m5["pas_par_s"] >= 25 and p95 < 5, m5, sinon=M.A_REGARDER)
    # captures pendant le tour (rotation figée pendant la pause)
    yield M.Capture("K1", "Pendant le tour : modèle centré et entier, vu en trois-quarts d'en haut, mur visible ?")
    t_fin = echantillons[-1][0]
    pilote.pas(t_fin, noyau.angle_au_temps(t_fin, reglages.vitesse_deg_s, reglages.sens, reglages.recadrage_s) + 90)
    yield M.Attendre(0.3)
    yield M.Capture("K2", "Un quart de tour plus loin : même cadrage vu d'un autre côté, mur visible ?")
    # P7 : arrêt net
    avant_arret = _xyz(vue.camera.eye)
    pilote.arreter(False)
    yield M.Attendre(0.5)
    apres_arret = _xyz(vue.camera.eye)
    r.verifier("P7", _proche(avant_arret, apres_arret, 1e-6 * diag + 1e-9),
               {"deplacement_cm": noyau.norme(noyau.soustrait(apres_arret, avant_arret))})
    # P6 : document intact, murs gardés
    m6 = {"timeline_avant": n_tl, "timeline_apres": d.tl.count, "visibles_avant": vis0,
          "visibles_apres": d.visibilites(), "isModified_avant": modif0, "isModified_apres": d.doc.isModified}
    r.verifier("P6", m6["timeline_avant"] == m6["timeline_apres"] and vis0 == m6["visibles_apres"], m6)
    # P8 : vue rendue
    d.vue_de_biais()
    yield M.Attendre(0.3)
    reglages_r = noyau.Reglages(restaurer_vue=True)
    pilote.demarrer(reglages_r)
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < 1.5:
        t = time.perf_counter() - t0
        pilote.pas(t, noyau.angle_au_temps(t, reglages_r.vitesse_deg_s, reglages_r.sens, reglages_r.recadrage_s))
        yield M.Attendre(1 / reglages_r.cadence_hz)
    pilote.arreter(True)
    yield M.Attendre(2.0)
    rendu = _xyz(vue.camera.eye)
    r.verifier("P8", _proche(rendu, oeil_depart, 1e-3 * diag), {
        "ecart_cm": noyau.norme(noyau.soustrait(rendu, oeil_depart))})
    yield M.Capture("K3", "La vue est-elle revenue exactement à celle de K0 ?")
    # R4 : Ctrl+Z après le tour
    if r.pilote.synchrone:
        r.point("R4", M.A_REGARDER, detail="mode synchrone : commande Annuler non jouée")
        return
    annuler = trouver_annuler(app.userInterface, r.memoire)
    if annuler is None:
        r.point("R4", M.A_REGARDER, detail="commande Annuler introuvable")
        return
    modele_avant = (d.tl.count, sorted(d.visibilites()))
    oeil_avant = _xyz(vue.camera.eye)
    annuler.execute()
    yield M.AttendreCommande(annuler.id, 5)
    modele_apres = (d.tl.count, sorted(d.visibilites()))
    m = {"modele_avant": modele_avant, "modele_apres": modele_apres,
         "vue_deplacee_cm": noyau.norme(noyau.soustrait(_xyz(vue.camera.eye), oeil_avant)),
         "commande": annuler.id}
    bon = modele_apres != modele_avant  # l'annulation a défait le renommage du mur (dernière vraie opération)
    r.verifier("R4", bon, m, "" if bon else "l'annulation a porté sur la vue : la caméra laisse des entrées "
                                            "d'annulation")


def b_addin(r):
    r.declarer_bloc(("R1", "R2", "R3"))
    etat = _etat_addin()
    if etat is None:
        for c in ("R1", "R2", "R3"):
            r.point(c, M.A_REGARDER, detail="add-in CinematicCamera pas lancé")
        return
    if r.pilote.synchrone:
        for c in ("R1", "R2", "R3"):
            r.point(c, M.A_REGARDER, detail="mode synchrone : l'add-in ne reçoit pas ses tics")
        return
    machine = etat["machine"]
    if not machine.reglages.actif:
        for c in ("R1", "R2", "R3"):
            r.point(c, M.A_REGARDER, detail="add-in sur ARRÊT : cliquer « Caméra auto » puis relancer")
        return
    _, noyau = _cam()
    app = _app()
    ui = app.userInterface
    delai = machine.reglages.delai_s  # 1 h pendant la recette (_neutraliser_addin) ; vrai délai remis à la fin

    def remettre():
        machine.reglages.delai_s = delai

    r.a_la_fin(remettre)

    def stopper_rotation():
        p = etat.get("pilote")
        if p is not None and p.en_cours:
            p.arreter(False)
            machine.etat = noyau.VEILLE

    d = DocCamera()
    r.au_nettoyage(d.fermer)
    r.au_nettoyage(stopper_rotation)
    d.vue_de_biais()
    machine.reglages.delai_s = DELAI_ESSAI_S
    yield M.Attendre(0.3)

    # R3 : commande ouverte → pas de rotation
    cmd_def = None
    for cid in ("ExtrudeCommand", "SketchCreate", "MeasureCommand"):
        cmd_def = ui.commandDefinitions.itemById(cid)
        if cmd_def is not None:
            break
    if cmd_def is None:
        r.point("R3", M.A_REGARDER, detail="aucune commande native trouvée pour l'essai")
    else:
        oeil = _xyz(d.vue.camera.eye)
        cmd_def.execute()
        yield M.Attendre(DELAI_ESSAI_S + 3)
        m = {"commande": cmd_def.id, "activeCommand": ui.activeCommand, "etat": machine.etat,
             "inactivite_s": inactivite_s(),
             "vue_deplacee_cm": noyau.norme(noyau.soustrait(_xyz(d.vue.camera.eye), oeil))}
        ouverte = m["activeCommand"] not in ("", COMMANDE_REPOS)
        bon = ouverte and machine.etat != noyau.ROTATION and m["vue_deplacee_cm"] < 1e-6
        r.verifier("R3", bon, m, "" if ouverte else "la commande ne s'est pas ouverte", sinon=M.KO if ouverte
                   else M.A_REGARDER)
        ui.terminateActiveCommand()
        stopper_rotation()
        yield M.Attendre(0.5)

    # R1 : départ réel
    oeil = _xyz(d.vue.camera.eye)
    debut = time.perf_counter()
    tourne = False
    while time.perf_counter() - debut < DELAI_ESSAI_S + 10:
        yield M.Attendre(0.5)
        if machine.etat == noyau.ROTATION:
            tourne = True
            break
    yield M.Attendre(1.5)
    m = {"etat": machine.etat, "attente_s": time.perf_counter() - debut, "inactivite_s": inactivite_s(),
         "vue_deplacee_cm": noyau.norme(noyau.soustrait(_xyz(d.vue.camera.eye), oeil))}
    r.verifier("R1", tourne and m["vue_deplacee_cm"] > 1e-3, m,
               "" if tourne else "pas de départ : quelqu'un a touché souris ou clavier ? sinon voir journal.log")
    if not tourne:
        r.point("R2", M.A_REGARDER, detail="pas de rotation à arrêter (R1)")
        return

    # R2 : arrêt sur un mouvement de souris simulé
    n = bouger_souris()
    t = time.perf_counter()
    arret = None
    while time.perf_counter() - t < 2.0:
        yield M.Attendre(0.1)
        if machine.etat != noyau.ROTATION:
            arret = time.perf_counter() - t
            break
    o1 = _xyz(d.vue.camera.eye)
    yield M.Attendre(0.5)
    o2 = _xyz(d.vue.camera.eye)
    m = {"entrees_envoyees": n, "arret_apres_s": arret, "etat": machine.etat,
         "bouge_encore_cm": noyau.norme(noyau.soustrait(o2, o1))}
    if n == 0:
        r.point("R2", M.A_REGARDER, m, "souris non simulable ici : voir M1")
    else:
        r.verifier("R2", arret is not None and arret < 1.0 and m["bouge_encore_cm"] < 1e-6, m)
    remettre()


BLOCS = [
    ("contexte", b_contexte),
    ("sonde", b_sonde),
    ("pilote", b_pilote),
    ("add-in en marche", b_addin),
]

# --------------------------------------------------------------------------- pour le MCP

_recette = None


def lancer(synchrone: bool = False) -> str:
    """Lance la recette. Rend aussitôt (mode événements) : suivre avec etat()."""
    global _recette
    if _recette is not None and _recette.avancement.phase in ("en cours", "pause"):
        return "Une recette tourne déjà : " + _recette.etat()
    app = _app()
    origine = app.activeDocument
    infos = {"fusion": app.version, "mode": "synchrone" if synchrone else "événements",
             "document_de_romain": origine.name if origine else None}
    r = M.Recette("CinematicCamera", RESULTATS, CATALOGUE, BLOCS, infos, capturer)

    def rendre_document():
        if origine is not None:
            try:
                origine.activate()
            except Exception:  # noqa: BLE001
                pass

    r.a_la_fin(rendre_document)
    _neutraliser_addin(r)
    _recette = r
    if synchrone:
        adsk = _adsk()

        def attendre(s):
            fin = time.perf_counter() + s
            while time.perf_counter() < fin:
                adsk.doEvents()
                time.sleep(0.005)

        return r.lancer(M.PiloteSynchrone(attendre))
    return r.lancer(M.PiloteFusion(ID_EVENEMENT))


def _neutraliser_addin(r):
    """L'add-in en marche ne doit pas tourner la vue pendant les mesures (Romain est inactif) : rotation
    en cours arrêtée, délai porté à 1 h, remis à la fin (le bloc R* le ramène à 3 s le temps de son essai)."""
    etat = _etat_addin()
    if etat is None:
        return
    _, noyau = _cam()
    machine = etat["machine"]
    delai = machine.reglages.delai_s
    r.infos["delai_addin_s"] = delai
    pilote = etat.get("pilote")
    if pilote is not None and pilote.en_cours:
        pilote.arreter(False)
    if machine.etat == noyau.ROTATION:
        machine.etat = noyau.VEILLE
    machine.reglages.delai_s = 3600.0

    def remettre():
        machine.reglages.delai_s = delai

    r.a_la_fin(remettre)


def _r():
    if _recette is None:
        raise RuntimeError("aucune recette : lancer() d'abord")
    return _recette


def etat() -> str:
    return _r().etat() if _recette is not None else "Aucune recette lancée."


def juger(code: str, verdict: str, remarque: str = "") -> str:
    return _r().juger(code, verdict, remarque)


def continuer() -> str:
    return _r().continuer()


def arreter() -> str:
    return _r().arreter()


def rapport() -> str:
    return _r().markdown()


def run(context):
    adsk = _adsk()
    adsk.autoTerminate(False)
    ui = _app().userInterface
    try:
        ui.messageBox("Après OK : ne touchez plus ni souris ni clavier pendant 2 minutes.\n"
                      "Le rapport s'écrit dans essai/resultats/.", "Recette CinematicCamera")
        lancer()
        if _recette is not None:
            _recette.a_la_fin(lambda: ui.messageBox(_recette.etat(), "Recette CinematicCamera"))
    except Exception:  # noqa: BLE001
        ui.messageBox(traceback.format_exc(), "Recette CinematicCamera")


def stop(context):
    if _recette is not None and _recette.avancement.phase != "fini":
        _recette.arreter()
