"""Couche Fusion : lecture et écriture de la caméra de la vue active. Seul lieu des Point3D / Vector3D.

Ne modifie jamais le document : seule la caméra de la vue change [supposé : sans entrée d'annulation].
Unités : cm (unités internes de Fusion), passées telles quelles au noyau.
"""
from __future__ import annotations

import time

import adsk.core
import adsk.fusion

from . import noyau
from .mesure import Mesure

TOLERANCE = 1e-4    # part de la distance œil-cible : au-delà, la vue a été bougée par quelqu'un d'autre


def _vec(p) -> noyau.Vec:
    return (p.x, p.y, p.z)


def _point(v: noyau.Vec):
    return adsk.core.Point3D.create(*v)


def _vecteur(v: noyau.Vec):
    return adsk.core.Vector3D.create(*v)


def axe_vertical(app, reglage: str, haut_courant: noyau.Vec) -> noyau.Vec:
    """Axe vertical : réglage explicite, sinon préférence « orientation de modélisation » de Fusion,
    sinon l'axe du monde le plus proche du haut de la vue courante."""
    if reglage in ("y", "z"):
        return noyau.AXES[reglage]
    try:
        o = app.preferences.generalPreferences.defaultModelingOrientation
        if o == adsk.core.DefaultModelingOrientations.ZUpModelingOrientation:
            return noyau.AXES["z"]
        if o == adsk.core.DefaultModelingOrientations.YUpModelingOrientation:
            return noyau.AXES["y"]
    except Exception:
        pass
    return noyau.axe_le_plus_proche(haut_courant)


def design_actif(app):
    """Le design du document actif, aussi depuis l'espace Animation, ou None."""
    design = adsk.fusion.Design.cast(app.activeProduct)
    if design:
        return design
    try:
        return adsk.fusion.Design.cast(app.activeDocument.products.itemByProductType("DesignProductType"))
    except Exception:
        return None


def boite_modele(app) -> tuple[noyau.Vec, noyau.Vec] | None:
    """Boîte englobante du composant racine (mini, maxi), ou None (pas un design, design vide)."""
    design = design_actif(app)
    if not design:
        return None
    try:
        b = design.rootComponent.boundingBox
        mini, maxi = _vec(b.minPoint), _vec(b.maxPoint)
    except Exception:
        return None
    if any(maxi[i] < mini[i] for i in range(3)):
        return None
    if noyau.norme(noyau.soustrait(maxi, mini)) < 1e-9:
        return None
    return mini, maxi


def centre_modele(app) -> noyau.Vec | None:
    """Centre de la boîte englobante du composant racine, ou None."""
    boite = boite_modele(app)
    return noyau.centre_boite(*boite) if boite else None


def _cote_visible_ortho(vue) -> float | None:
    """Côté le plus court de la zone visible, en cm, pour une caméra orthographique (mesuré à l'écran)."""
    try:
        l, h = vue.width, vue.height
        gauche = vue.viewToModelSpace(adsk.core.Point2D.create(0, h / 2))
        droite = vue.viewToModelSpace(adsk.core.Point2D.create(l, h / 2))
        largeur = gauche.distanceTo(droite)
        return largeur * min(l, h) / l if l > 0 and largeur > 0 else None
    except Exception:
        return None


def _est_ortho(cam) -> bool:
    try:
        return cam.cameraType == adsk.core.CameraTypes.OrthographicCameraType
    except Exception:
        return False


class PiloteCamera:
    """Démarre, fait tourner et arrête la rotation sur la vue active."""

    def __init__(self, app, log):
        self.app = app
        self.log = log
        self.vue = None
        self.camera_avant = None
        self.depart: noyau.Pose | None = None
        self.trajet: noyau.Trajet | None = None
        self.axe: noyau.Vec = (0.0, 0.0, 1.0)
        self.duree_pas_ms = Mesure()
        self.intervalle_ms = Mesure()
        self._dernier_pas = None
        self._pose_posee = None

    @property
    def en_cours(self) -> bool:
        return self.depart is not None

    def _appliquer(self, pose: noyau.Pose, etendue: float | None = None):
        cam = self.vue.camera
        cam.eye = _point(pose.oeil)
        cam.target = _point(pose.cible)
        cam.upVector = _vecteur(pose.haut)
        cam.isSmoothTransition = False     # posé à la main : lue dans la vue, la caméra anime quand même
        cam.isFitView = False
        if etendue is not None:
            cam.viewExtents = etendue
        self.vue.camera = cam

    def preparer(self, reglages: noyau.Reglages, duree_voyage_s: float) -> noyau.Trajet | None:
        """Trajet de la vue active vers le cadrage, sans toucher à la vue.

        Pas de cadrage d'essai par `isFitView` : Fusion peut l'appliquer d'un coup à l'écran, et la vue
        sautait. Le cadrage vient de la boîte du modèle et de l'angle de vue.
        """
        vue = self.app.activeViewport
        if not vue:
            return None
        self.vue = vue
        avant = vue.camera            # copie : Fusion rend un nouvel objet à chaque lecture
        self.camera_avant = avant
        oeil = _vec(avant.eye)
        cible = _vec(avant.target)
        self.axe = axe_vertical(self.app, reglages.axe, _vec(avant.upVector))
        ortho = _est_ortho(avant)
        distance0 = noyau.norme(noyau.soustrait(oeil, cible))
        cible1, distance1, etendue0, etendue1 = cible, distance0, None, None
        if ortho:
            etendue0 = etendue1 = avant.viewExtents
        boite = boite_modele(self.app) if reglages.cadrer else None
        if boite:
            cible1, rayon = noyau.cadrage(*boite)
            if ortho:
                cote = _cote_visible_ortho(vue)
                if cote:
                    etendue1 = etendue0 * (2 * rayon) / cote
                distance1 = max(distance0, 3 * rayon)
            else:
                distance1 = noyau.distance_perspective(rayon, avant.perspectiveAngle)
        return noyau.Trajet(self.axe, oeil, cible, cible1, distance1, reglages.inclinaison_deg,
                            duree_voyage_s if reglages.cadrer else 0.0, etendue0, etendue1)

    def demarrer(self, reglages: noyau.Reglages) -> bool:
        """Calcule le cadrage d'arrivée, puis laisse la caméra où elle est : le voyage se fait par les pas."""
        t = time.perf_counter()
        trajet = self.preparer(reglages, reglages.recadrage_s)
        if trajet is None:
            return False
        self.trajet = trajet
        self.depart = self.trajet.pose(0.0, 0.0)
        self._pose_posee = None
        self.duree_pas_ms = Mesure()
        self.intervalle_ms = Mesure()
        self._dernier_pas = None
        self.log.info("rotation démarrée : axe %s, cible %s → %s, distance %.1f → %.1f cm, étendue %s → %s, "
                      "calcul %.1f ms", self.axe, trajet.cible0, trajet.cible1, trajet.distance0,
                      trajet.distance1, trajet.etendue0, trajet.etendue1, (time.perf_counter() - t) * 1000)
        return True

    def bougee_par_ailleurs(self) -> bool:
        """Vrai si la vue n'est plus celle du dernier pas : orbite, zoom, souris 3D, vue nommée…"""
        if self._pose_posee is None or self.vue is None:
            return False
        try:
            cam = self.vue.camera
            oeil, cible = _vec(cam.eye), _vec(cam.target)
        except Exception:
            return True
        o, c = self._pose_posee
        echelle = noyau.norme(noyau.soustrait(o, c)) or 1.0
        return (noyau.norme(noyau.soustrait(oeil, o)) > TOLERANCE * echelle
                or noyau.norme(noyau.soustrait(cible, c)) > TOLERANCE * echelle)

    def pas(self, t_s: float, angle_deg: float) -> bool:
        """Un pas de rotation. Faux si la vue a été bougée par quelqu'un d'autre : rien n'est posé."""
        if not self.depart:
            return False
        if self.bougee_par_ailleurs():
            self.log.info("vue bougée par ailleurs : rotation rendue")
            return False
        maintenant = time.perf_counter()
        if self._dernier_pas is not None:
            self.intervalle_ms.ajoute((maintenant - self._dernier_pas) * 1000)
        self._dernier_pas = maintenant
        pose = self.trajet.pose(t_s, angle_deg)
        self._appliquer(pose, etendue=self.trajet.etendue(t_s))
        self.vue.refresh()      # redessine tout de suite : chaque pas se voit, pas seulement le dernier
        cam = self.vue.camera   # relue : Fusion peut arrondir ce qu'on lui donne
        self._pose_posee = (_vec(cam.eye), _vec(cam.target))
        self.duree_pas_ms.ajoute((time.perf_counter() - maintenant) * 1000)
        return True

    def arreter(self, restaurer: bool) -> None:
        if not self.depart:
            return
        try:
            if restaurer and self.camera_avant is not None and self.vue is not None \
                    and self.app.activeViewport == self.vue:
                self.camera_avant.isSmoothTransition = True
                self.vue.camera = self.camera_avant
        finally:
            self.log.info("rotation arrêtée (vue rendue : %s) ; intervalle ms %s ; durée pas ms %s",
                          restaurer, self.intervalle_ms.resume(), self.duree_pas_ms.resume())
            self.depart = None
            self.trajet = None
            self._pose_posee = None
            self.camera_avant = None
            self.vue = None
