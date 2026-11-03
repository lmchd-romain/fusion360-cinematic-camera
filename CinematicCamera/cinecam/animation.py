"""Animation : un storyboard de l'espace Animation de Fusion, qui joue un mouvement de `mouvements`.

API Animation de Fusion : en preview depuis mai 2026.

Essai 0.2.0 [vérifié, Romain, 2026-11-02] : tout fait d'un bloc dans le gestionnaire de la commande, la vue
tourne en accéléré, Fusion affiche « View is not recording » et le storyboard reste vide. Les changements de
caméra faits pendant une commande ne sont pas enregistrés [déduit].

Méthode 0.2.1 [supposé] : hors de toute commande, un pas par tic de l'événement personnalisé, Fusion reprenant
la main entre deux pas : enregistrement allumé et relu, puis pour chaque vue la tête de lecture posée, puis la
caméra posée. Après deux vues, la fin du storyboard doit avoir avancé ; sinon on recommence en « lisse »
(transition douce de Fusion, comme une orbite à la souris), sinon on abandonne avec un diagnostic.
"""
from __future__ import annotations

import math
import time

from . import mouvements, noyau
from .fusion_camera import PiloteCamera, _est_ortho, boite_modele, design_actif

# Une étape rendue par le générateur = un tic (≈ 1/30 s) rendu à Fusion avant la suivante.
ATTENTE_DIRECTE = 2       # tics après une caméra posée sans transition
ATTENTE_LISSE = 25        # tics après une caméra posée avec transition (≈ 0,8 s, la transition en dure 0,55)
METHODES = ("directe", "lisse")
VUES_TEMOINS = 2          # vues posées avant de vérifier que Fusion enregistre


class ErreurAnimation(Exception):
    """Message en français, affiché tel quel."""


def verifier(app):
    """Contrôles avant de commencer. Rend le gestionnaire d'animation. Lève ErreurAnimation."""
    design = design_actif(app)
    if design is None:
        raise ErreurAnimation("Ouvrez d'abord un design avec un modèle.")
    gestion = getattr(design, "animationManager", None)
    if gestion is None:
        raise ErreurAnimation("Cette version de Fusion ne permet pas de créer une animation par un "
                              "complément. Mettez Fusion à jour.")
    if boite_modele(app) is None:
        raise ErreurAnimation("Le design est vide : rien à filmer.")
    return gestion


def _fin(storyboard) -> float:
    try:
        return float(storyboard.end)
    except Exception:
        return -1.0


def _commandes_enregistrement(ui) -> list[str]:
    """Pour le diagnostic : commandes de Fusion dont l'id parle d'enregistrement ou de vue d'animation."""
    trouves = []
    try:
        defs = ui.commandDefinitions
        for i in range(defs.count):
            id_ = defs.item(i).id
            bas = id_.lower()
            if "record" in bas or ("view" in bas and "anim" in bas) or "storyboard" in bas:
                trouves.append(id_)
    except Exception:
        pass
    return trouves[:40]


def etapes(app, reglages: noyau.Reglages, log, resultat: dict, boite=None, normales=None):
    """Générateur : crée le storyboard pas à pas. Remplit `resultat` (duree, vues, methode) en cas de succès.

    Lève ErreurAnimation (message pour l'utilisateur) si Fusion n'enregistre pas les vues.
    `normales` : (face avant, face du dessus), normales sortantes des faces choisies ou None.
    À la fin, l'enregistrement des vues reste allumé, comme dans l'espace Animation par défaut :
    l'éteindre faisait afficher « View is not recording » [vérifié, Romain, 0.6.0] ; il est rallumé à la fin.
    """
    t0 = time.perf_counter()
    gestion = verifier(app)
    if not gestion.isAnimationWorkspaceActive:
        gestion.activateAnimationWorkspace()
        yield
    storyboard = gestion.storyboards.add(True)
    if storyboard is None:
        raise ErreurAnimation("Fusion a refusé de créer un storyboard.")
    yield
    storyboard.activate()
    yield
    log.info("animation : storyboard %d/%d créé, actif %s, enregistrement %s, tête %s, fin %s, mode %s",
             gestion.storyboards.count, gestion.storyboards.count, storyboard.isActive,
             storyboard.isViewRecordingOn, storyboard.playheadPosition, _fin(storyboard),
             getattr(gestion, "recordingMode", "?"))

    pilote = PiloteCamera(app, log)
    trajet = pilote.preparer(reglages, 0.0, boite)   # repère du modèle (ou des pièces choisies)
    if trajet is None:
        raise ErreurAnimation("Aucune vue active.")
    mouvement = mouvements.PAR_NOM.get(reglages.anim_mouvement, mouvements.CATALOGUE[0])
    avant = pilote.camera_avant
    angle0 = None if _est_ortho(avant) else math.degrees(avant.perspectiveAngle)
    n_avant, n_dessus = normales or (None, None)
    haut, devant, cote = mouvements.orienter(trajet.axe, trajet.h0, n_dessus, n_avant)
    log.info("animation : orientation haut %s, devant %s (face avant %s, dessus %s)", haut, devant, n_avant, n_dessus)
    rep = mouvements.Repere(trajet.cible1, pilote.rayon, trajet.distance1, haut, devant, cote, angle0)
    fov = reglages.anim_fov_deg if reglages.anim_fov_deg >= mouvements.FOV_BORNES[0] else None
    vues = mouvements.cles(mouvement, reglages.anim_duree_s, rep, reglages.anim_zoom_pct / 100.0, fov)
    etendue = trajet.etendue(0.0)
    log.info("animation : mouvement %s, %.0f s, zoom %.0f %%, angle de vue %s → %s, %d vues", mouvement.nom,
             reglages.anim_duree_s, reglages.anim_zoom_pct, angle0, fov, len(vues))

    for methode in METHODES:
        storyboard.isViewRecordingOn = True
        yield
        allume = storyboard.isViewRecordingOn
        log.info("animation, méthode %s : enregistrement demandé, relu %s", methode, allume)
        attente = ATTENTE_LISSE if methode == "lisse" else ATTENTE_DIRECTE
        enregistre = True
        for k, cle in enumerate(vues):
            storyboard.playheadPosition = cle.t
            yield
            pilote._appliquer(cle.pose, etendue=None if etendue is None else etendue * cle.facteur,
                              angle_deg=cle.fov)
            if methode == "lisse":
                cam = pilote.vue.camera
                cam.isSmoothTransition = True
                pilote.vue.camera = cam
            for _ in range(attente):
                yield
            if k == VUES_TEMOINS:
                fin = _fin(storyboard)
                log.info("animation, méthode %s : après %d vues, tête %s, fin du storyboard %.2f s",
                         methode, k + 1, storyboard.playheadPosition, fin)
                if fin < vues[1].t * 0.5:
                    enregistre = False
                    break
        if enregistre:
            storyboard.isViewRecordingOn = False
            yield
            # L'angle de vue est-il gardé par le storyboard ? On se place sur la vue la plus éloignée de
            # l'angle de départ, on relit, puis on rend l'angle de départ à la vue (sinon il reste, comme
            # celui de l'espace Rendu).
            fov_ok = None
            if angle0 is not None and any(c.fov is not None and abs(c.fov - angle0) > 3 for c in vues):
                temoin = max(vues, key=lambda c: abs((c.fov or angle0) - angle0))
                storyboard.playheadPosition = temoin.t
                for _ in range(10):
                    yield
                lu = math.degrees(pilote.vue.camera.perspectiveAngle)
                fov_ok = abs(lu - temoin.fov) < 1.5
                log.info("animation : angle de vue à %.2f s attendu %.1f°, relu %.1f° → %s", temoin.t, temoin.fov,
                         lu, "gardé" if fov_ok else "PAS gardé")
            storyboard.playheadPosition = 0
            yield
            if angle0 is not None:
                try:
                    pilote.poser_angle(angle0)
                except Exception:
                    pass
            yield
            # Rallumé comme Fusion le met par défaut dans l'espace Animation : éteint, il affiche « View is not
            # recording » [vérifié, Romain, 0.6.0]. Plus aucun changement de vue après : rien n'est enregistré.
            storyboard.isViewRecordingOn = True
            resultat.update(fov_garde=fov_ok)
            resultat.update(duree=vues[-1].t, vues=len(vues), methode=methode, fin=_fin(storyboard),
                            mouvement=mouvement.libelle, boucle=mouvement.boucle)
            log.info("animation créée : méthode %s, %d vues, %.1f s, fin du storyboard %.1f s, %.1f s de calcul",
                     methode, len(vues), vues[-1].t, _fin(storyboard), time.perf_counter() - t0)
            return
        storyboard.playheadPosition = 0
        yield
    storyboard.isViewRecordingOn = True
    log.error("animation : Fusion n'enregistre pas les vues posées par le complément. Commandes candidates : %s",
              _commandes_enregistrement(app.userInterface))
    raise ErreurAnimation("Fusion n'a enregistré aucune vue dans le storyboard : il refuse pour l'instant "
                          "les vues posées par un complément.\nDétail dans journal.log (dossier de l'add-in) : "
                          "envoyez-le pour la suite.")
