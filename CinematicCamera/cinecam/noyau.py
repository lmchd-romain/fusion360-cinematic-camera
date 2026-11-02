"""Noyau pur : réglages, trajectoire de la caméra, machine d'états. Aucun import adsk.

Unités : longueurs dans l'unité de l'appelant (la couche Fusion passe des cm), angles en degrés
dans les réglages, en radians dans les calculs.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, fields, asdict

Vec = tuple[float, float, float]

AXES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}


# ---------------------------------------------------------------- vecteurs
def ajoute(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def soustrait(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def echelle(a: Vec, k: float) -> Vec:
    return (a[0] * k, a[1] * k, a[2] * k)


def scalaire(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vectoriel(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def norme(a: Vec) -> float:
    return math.sqrt(scalaire(a, a))


def unitaire(a: Vec) -> Vec:
    n = norme(a)
    if n < 1e-12:
        raise ValueError("vecteur nul")
    return echelle(a, 1.0 / n)


def tourne(v: Vec, axe: Vec, angle_rad: float) -> Vec:
    """Rotation de v autour de l'axe unitaire (formule de Rodrigues)."""
    k = unitaire(axe)
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    kv = vectoriel(k, v)
    kd = scalaire(k, v)
    return (
        v[0] * c + kv[0] * s + k[0] * kd * (1 - c),
        v[1] * c + kv[1] * s + k[1] * kd * (1 - c),
        v[2] * c + kv[2] * s + k[2] * kd * (1 - c),
    )


def axe_le_plus_proche(v: Vec) -> Vec:
    """Axe du monde (X, Y ou Z, sens positif) le plus aligné avec v."""
    return max(AXES.values(), key=lambda a: abs(scalaire(a, v)))


def centre_boite(mini: Vec, maxi: Vec) -> Vec:
    return echelle(ajoute(mini, maxi), 0.5)


# ---------------------------------------------------------------- réglages
@dataclass
class Reglages:
    actif: bool = True               # bouton marche / arrêt
    delai_s: float = 60.0            # inactivité avant de démarrer (MobPrez : 5 s, outil de présentation)
    vitesse_deg_s: float = 2.4       # comme MobPrez : un tour en 150 s (choix de Romain)
    inclinaison_deg: float = 35.0    # comme MobPrez : « trois-quarts de studio »
    recadrage_s: float = 6.0         # comme MobPrez : voyage souple vers le cadrage, rotation déjà en cours
    cadence_hz: float = 30.0         # pas de caméra par seconde
    sens: int = 1                    # 1 = sens trigonométrique vu du haut, -1 = inverse
    axe: str = "auto"                # "auto" (préférence Fusion), "y", "z"
    cadrer: bool = True              # cadrer le modèle au démarrage
    restaurer_vue: bool = False      # False = arrêt net comme MobPrez ; True = rendre la vue d'avant

    BORNES = {
        "delai_s": (5.0, 3600.0),
        "vitesse_deg_s": (0.5, 90.0),
        "inclinaison_deg": (-60.0, 80.0),
        "cadence_hz": (1.0, 60.0),
        "recadrage_s": (0.0, 30.0),
    }

    @classmethod
    def depuis_dict(cls, d: dict | None) -> "Reglages":
        """Champs absents ou invalides → valeur par défaut ; nombres ramenés dans leurs bornes."""
        r = cls()
        if not isinstance(d, dict):
            return r
        for f in fields(cls):
            if f.name not in d:
                continue
            defaut = getattr(r, f.name)
            v = d[f.name]
            try:
                if isinstance(defaut, bool):
                    if isinstance(v, bool):
                        setattr(r, f.name, v)
                elif isinstance(defaut, int):
                    setattr(r, f.name, -1 if int(v) < 0 else 1)
                elif isinstance(defaut, float):
                    v = float(v)
                    if math.isfinite(v):
                        lo, hi = cls.BORNES[f.name]
                        setattr(r, f.name, min(hi, max(lo, v)))
                elif isinstance(defaut, str):
                    if str(v).lower() in ("auto", "y", "z"):
                        setattr(r, f.name, str(v).lower())
            except (TypeError, ValueError):
                pass
        return r

    def vers_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- trajectoire
@dataclass(frozen=True)
class Pose:
    oeil: Vec
    cible: Vec
    haut: Vec


def pose_initiale(oeil: Vec, cible: Vec, axe: Vec, inclinaison_deg: float,
                  nouvelle_cible: Vec | None = None) -> Pose:
    """Garde l'azimut et la distance de la vue courante, impose l'inclinaison au-dessus de l'horizon.

    nouvelle_cible : centre du modèle, si on recentre ; sinon la cible courante.
    """
    axe = unitaire(axe)
    cible_finale = nouvelle_cible if nouvelle_cible is not None else cible
    d = soustrait(oeil, cible)
    distance = norme(d) or 1.0
    horiz = soustrait(d, echelle(axe, scalaire(d, axe)))
    if norme(horiz) < 1e-9 * distance:
        # Vue de dessus ou de dessous : azimut arbitraire, perpendiculaire à l'axe.
        aide = (1.0, 0.0, 0.0) if abs(axe[0]) < 0.9 else (0.0, 1.0, 0.0)
        horiz = vectoriel(axe, aide)
    horiz = unitaire(horiz)
    a = math.radians(inclinaison_deg)
    direction = ajoute(echelle(horiz, math.cos(a)), echelle(axe, math.sin(a)))
    return Pose(ajoute(cible_finale, echelle(direction, distance)), cible_finale, axe)


def pose_a(depart: Pose, axe: Vec, angle_deg: float) -> Pose:
    """Pose obtenue en faisant tourner l'œil de angle_deg autour de l'axe passant par la cible."""
    rel = soustrait(depart.oeil, depart.cible)
    rel = tourne(rel, axe, math.radians(angle_deg))
    return Pose(ajoute(depart.cible, rel), depart.cible, unitaire(axe))


def angle_au_temps(t_s: float, vitesse_deg_s: float, sens: int, montee_s: float = 0.0) -> float:
    """Angle cumulé (degrés) après t_s secondes de rotation : indépendant de la cadence réelle.

    Pendant montee_s, la vitesse part de zéro et monte en douceur (courbe en S) jusqu'à vitesse_deg_s :
    aucun à-coup au départ. L'angle est l'intégrale de cette vitesse.
    """
    t = max(0.0, t_s)
    if montee_s > 0 and t < montee_s:
        x = t / montee_s
        parcouru = montee_s * (x ** 3 - x ** 4 / 2)
    elif montee_s > 0:
        parcouru = montee_s / 2 + (t - montee_s)
    else:
        parcouru = t
    return (sens * vitesse_deg_s * parcouru) % 360.0


def cadrage(mini: Vec, maxi: Vec, marge: float = 1.15) -> tuple[Vec, float]:
    """Centre et rayon de la sphère qui englobe la boîte, marge comprise.

    La sphère ne dépend pas de la direction du regard : le modèle reste entier pendant tout le tour.
    """
    centre = centre_boite(mini, maxi)
    rayon = norme(soustrait(maxi, mini)) / 2 * marge
    return centre, rayon


def distance_perspective(rayon: float, angle_rad: float) -> float:
    """Distance œil-cible pour qu'une sphère de ce rayon tienne dans l'angle de vue (côté le plus court)."""
    demi = min(max(angle_rad, 1e-3), math.pi - 1e-3) / 2
    return rayon / math.sin(demi)


def adoucir(x: float) -> float:
    """Courbe d'accélération puis de freinage (cubique), x borné à [0, 1]."""
    x = min(1.0, max(0.0, x))
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


class Trajet:
    """Rotation autour de l'axe vertical pendant un voyage souple vers le cadrage.

    En coordonnées sphériques autour de l'axe : cible, distance et élévation glissent du départ vers
    l'arrivée pendant duree_s ; l'azimut suit la rotation depuis le départ, sans arrêt.
    """

    def __init__(self, axe: Vec, oeil0: Vec, cible0: Vec, cible1: Vec, distance1: float,
                 elevation1_deg: float, duree_s: float,
                 etendue0: float | None = None, etendue1: float | None = None):
        self.axe = unitaire(axe)
        self.cible0, self.cible1 = cible0, cible1
        d = soustrait(oeil0, cible0)
        self.distance0 = norme(d) or distance1 or 1.0
        self.distance1 = distance1 if distance1 > 0 else self.distance0
        hauteur = scalaire(d, self.axe)
        horiz = soustrait(d, echelle(self.axe, hauteur))
        if norme(horiz) < 1e-9 * self.distance0:
            aide = (1.0, 0.0, 0.0) if abs(self.axe[0]) < 0.9 else (0.0, 1.0, 0.0)
            horiz = vectoriel(self.axe, aide)
        self.h0 = unitaire(horiz)
        self.p0 = vectoriel(self.axe, self.h0)
        self.elev0 = math.asin(max(-1.0, min(1.0, hauteur / self.distance0)))
        self.elev1 = math.radians(elevation1_deg)
        self.duree_s = max(0.0, duree_s)
        self.etendue0, self.etendue1 = etendue0, etendue1

    def avancement(self, t_s: float) -> float:
        return 1.0 if self.duree_s <= 0 else adoucir(t_s / self.duree_s)

    def pose(self, t_s: float, angle_deg: float) -> Pose:
        s = self.avancement(t_s)
        cible = ajoute(self.cible0, echelle(soustrait(self.cible1, self.cible0), s))
        dist = self.distance0 + (self.distance1 - self.distance0) * s
        el = self.elev0 + (self.elev1 - self.elev0) * s
        az = math.radians(angle_deg)
        horiz = ajoute(echelle(self.h0, math.cos(az)), echelle(self.p0, math.sin(az)))
        direction = ajoute(echelle(horiz, math.cos(el)), echelle(self.axe, math.sin(el)))
        return Pose(ajoute(cible, echelle(direction, dist)), cible, self.axe)

    def etendue(self, t_s: float) -> float | None:
        """Étendue de vue (caméra orthographique) interpolée, ou None."""
        if self.etendue0 is None or self.etendue1 is None:
            return None
        return self.etendue0 + (self.etendue1 - self.etendue0) * self.avancement(t_s)


# ---------------------------------------------------------------- machine d'états
ARRET, VEILLE, ROTATION = "arret", "veille", "rotation"

# Actions rendues par Machine.etape
RIEN, DEMARRER, PAS, ARRETER = "rien", "demarrer", "pas", "arreter"

REPRISE_S = 0.5  # inactivité sous ce seuil pendant la rotation = l'utilisateur est revenu


@dataclass
class Action:
    type: str
    angle_deg: float = 0.0
    t_s: float = 0.0          # temps écoulé depuis le démarrage de la rotation
    restaurer: bool = False


class Machine:
    """Décide, à chaque tic, ce que la couche Fusion doit faire. Le temps est injecté."""

    def __init__(self, reglages: Reglages):
        self.reglages = reglages
        self.etat = VEILLE if reglages.actif else ARRET
        self.t0 = 0.0

    def intervalle_tic_s(self) -> float:
        """Cadence demandée au fil de surveillance."""
        if self.etat == ROTATION:
            return 1.0 / self.reglages.cadence_hz
        return 0.5

    def basculer(self, actif: bool) -> Action:
        self.reglages.actif = actif
        if actif:
            if self.etat == ARRET:
                self.etat = VEILLE
            return Action(RIEN)
        en_rotation = self.etat == ROTATION
        self.etat = ARRET
        return Action(ARRETER, restaurer=self.reglages.restaurer_vue) if en_rotation else Action(RIEN)

    def etape(self, inactif_s: float | None, maintenant_s: float, occupe: bool = False) -> Action:
        """inactif_s : secondes depuis la dernière saisie (None = inconnu → jamais de démarrage).

        occupe : une commande est en cours ou aucun modèle n'est affiché → ne pas démarrer.
        """
        if self.etat == ARRET:
            return Action(RIEN)
        if self.etat == VEILLE:
            if inactif_s is not None and not occupe and inactif_s >= self.reglages.delai_s:
                self.etat = ROTATION
                self.t0 = maintenant_s
                return Action(DEMARRER)
            return Action(RIEN)
        # ROTATION
        if inactif_s is None or inactif_s < REPRISE_S or occupe:
            self.etat = VEILLE
            return Action(ARRETER, restaurer=self.reglages.restaurer_vue)
        r = self.reglages
        t = maintenant_s - self.t0
        return Action(PAS, angle_deg=angle_au_temps(t, r.vitesse_deg_s, r.sens, r.recadrage_s), t_s=t)

    def echec(self) -> None:
        """La couche Fusion n'a pas pu appliquer l'action : retour en veille sans tourner."""
        if self.etat == ROTATION:
            self.etat = VEILLE
