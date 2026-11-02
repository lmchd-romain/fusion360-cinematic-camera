"""Animation : un storyboard de l'espace Animation de Fusion, qui fait un tour complet du modèle.

API Animation de Fusion : en preview depuis mai 2026 [supposé : comportement à prouver dans Fusion].
Méthode : nouveau storyboard propre, enregistrement des vues allumé, puis pour chaque vue la tête de lecture
posée à son instant et la caméra posée ; Fusion crée une action de vue entre deux vues enregistrées.
Rien d'autre du design n'est touché.
"""
from __future__ import annotations

import time

import adsk

from . import noyau
from .fusion_camera import PiloteCamera, boite_modele, design_actif


class ErreurAnimation(Exception):
    """Message en français, affiché tel quel."""


def creer(app, reglages: noyau.Reglages, log) -> tuple[float, int]:
    """Crée le storyboard. Rend (durée en s, nombre de vues). Lève ErreurAnimation."""
    design = design_actif(app)
    if design is None:
        raise ErreurAnimation("Ouvrez d'abord un design avec un modèle.")
    gestion = getattr(design, "animationManager", None)
    if gestion is None:
        raise ErreurAnimation("Cette version de Fusion ne permet pas de créer une animation par un "
                              "complément. Mettez Fusion à jour.")
    if boite_modele(app) is None:
        raise ErreurAnimation("Le design est vide : rien à filmer.")
    t = time.perf_counter()
    if not gestion.isAnimationWorkspaceActive:
        gestion.activateAnimationWorkspace()
        adsk.doEvents()
    storyboard = gestion.storyboards.add(True)
    if storyboard is None:
        raise ErreurAnimation("Fusion a refusé de créer un storyboard.")
    storyboard.activate()
    adsk.doEvents()

    pilote = PiloteCamera(app, log)
    trajet = pilote.preparer(reglages, 0.0)     # déjà cadré au premier instant : la vidéo boucle
    if trajet is None:
        raise ErreurAnimation("Aucune vue active.")
    vues = noyau.instants_animation(reglages.vitesse_deg_s, reglages.sens)
    storyboard.isViewRecordingOn = True
    try:
        for instant, angle in vues:
            storyboard.playheadPosition = instant
            adsk.doEvents()
            pilote._appliquer(trajet.pose(0.0, angle), etendue=trajet.etendue(0.0))
            adsk.doEvents()
    finally:
        storyboard.isViewRecordingOn = False
        try:
            storyboard.playheadPosition = 0
        except Exception:
            pass
    duree = vues[-1][0]
    log.info("animation créée : %d vues, %.1f s, fin du storyboard %.1f s, calcul %.0f ms",
             len(vues), duree, getattr(storyboard, "end", -1), (time.perf_counter() - t) * 1000)
    return duree, len(vues)

