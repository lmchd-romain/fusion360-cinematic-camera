"""Mouvements de caméra pour les animations : pur, aucun import adsk.

Un mouvement est une suite de segments. Chaque segment décrit, pour u allant de 0 à 1, un cadre relatif au
modèle : azimut et hauteur de l'œil (degrés), distance (facteur de la distance qui cadre tout le modèle),
décalage de la cible (en rayons du modèle, dans le repère (devant, côté, haut) de la vue de départ).
Un segment marqué `coupe` commence par un changement de plan franc, comme au montage.

Les vues clés sont ensuite posées assez serrées pour que Fusion, qui va en ligne droite d'une vue à
l'autre, suive la courbe : écart d'œil sous 6 % de la distance, une vue au moins par seconde.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

from .noyau import Pose, Reglages, Vec, ajoute, echelle, norme, soustrait

COUPE_S = 0.04            # durée d'un changement de plan franc (un peu plus d'une image à 25 i/s)
ECART_MAX = 0.06          # écart d'œil maximal entre deux vues, en part de la distance de cadrage
ECART_CIBLE_MAX = 0.03
INTERVALLE_MAX_S = 1.0
AZIMUT_MAX = 5.0          # degrés de rotation au plus entre deux vues (vue de dessus : l'œil bouge peu)
FINESSE = 400             # points examinés par segment pour placer les vues
HAUTEUR_MAX = 85.0        # au-delà, le haut de la vue se confond avec le regard


@dataclass(frozen=True)
class Cadre:
    az: float                      # degrés, 0 = côté de la vue de départ
    el: float                      # degrés au-dessus de l'horizon
    dist: float = 1.0              # facteur de la distance qui cadre le modèle entier
    decal: Vec = (0.0, 0.0, 0.0)   # décalage de la cible, en rayons : (devant, côté, haut)


@dataclass(frozen=True)
class Segment:
    part: float                            # part de la durée totale (relative)
    cadre: Callable[[float], Cadre]
    coupe: bool = False


@dataclass(frozen=True)
class Mouvement:
    nom: str
    libelle: str
    info: str
    duree_defaut_s: float
    segments: tuple[Segment, ...] = field(default_factory=tuple)
    boucle: bool = False


# ---------------------------------------------------------------- courbes
def doux(u: float) -> float:
    """Accélère puis freine (sinusoïde)."""
    u = min(1.0, max(0.0, u))
    return 0.5 - 0.5 * math.cos(math.pi * u)


def mi_doux(u: float) -> float:
    """Moitié linéaire, moitié douce : glisse sans à-coup mais sans traîner (plans du montage)."""
    return 0.5 * min(1.0, max(0.0, u)) + 0.5 * doux(u)


def _mix(a: float, b: float, s: float) -> float:
    return a + (b - a) * s


def glisse(a: Cadre, b: Cadre, courbe=doux) -> Callable[[float], Cadre]:
    def f(u: float) -> Cadre:
        s = courbe(u)
        return Cadre(_mix(a.az, b.az, s), _mix(a.el, b.el, s), _mix(a.dist, b.dist, s),
                     tuple(_mix(x, y, s) for x, y in zip(a.decal, b.decal)))
    return f


# ---------------------------------------------------------------- catalogue
def _platine(u):
    return Cadre(360.0 * u, 35.0)


def _spirale(u):
    w = 2 * math.pi * u
    return Cadre(360.0 * u, 35.0 + 22.0 * math.sin(w), 1.0 + 0.12 * (1 - math.cos(2 * w)) / 2)


def _balancier(u):
    return Cadre(40.0 * math.sin(2 * math.pi * u), 28.0)


def _dessus(u):
    return Cadre(180.0 * u, 80.0, 1.1)


CATALOGUE: tuple[Mouvement, ...] = (
    Mouvement("platine", "Platine (tour complet)",
              "La vue fait un tour complet à vitesse constante, vue de trois-quarts. Boucle sans à-coup.",
              60.0, (Segment(1, _platine),), boucle=True),
    Mouvement("spirale", "Orbite en spirale",
              "Un tour complet en montant puis en redescendant, avec un léger souffle de distance. Boucle.",
              40.0, (Segment(1, _spirale),), boucle=True),
    Mouvement("drone", "Vue drone",
              "Arrive de haut et de loin, plonge en tournant jusqu'à une vue de trois-quarts proche.",
              12.0, (Segment(1, glisse(Cadre(-70, 72, 1.9), Cadre(70, 22, 1.0))),)),
    Mouvement("revelation", "Révélation supercar",
              "Part au ras du sol, tout près, puis recule lentement en tournant pour dévoiler le modèle.",
              10.0, (Segment(1, glisse(Cadre(-35, 4, 0.55, (0, 0, -0.35)), Cadre(45, 24, 1.0))),)),
    Mouvement("edit", "Edit supercar (montage)",
              "Montage façon vidéo de voiture : six plans courts coupés franc (ras du sol, travelling de "
              "côté, dessus, arrière, détail), puis plan large final.",
              15.0, (
                  Segment(1.0, glisse(Cadre(-35, 5, 0.78, (0, 0, -0.3)), Cadre(-24, 6, 0.55, (0, 0, -0.3)),
                                      mi_doux)),
                  Segment(1.0, glisse(Cadre(78, 9, 0.62, (0, -0.25, -0.1)), Cadre(102, 9, 0.62, (0, 0.25, -0.1)),
                                      mi_doux), coupe=True),
                  Segment(1.0, glisse(Cadre(0, 80, 1.0), Cadre(40, 80, 0.88), mi_doux), coupe=True),
                  Segment(1.0, glisse(Cadre(198, 6, 0.6, (0, 0, -0.25)), Cadre(214, 7, 0.72, (0, 0, -0.25)),
                                      mi_doux), coupe=True),
                  Segment(0.8, glisse(Cadre(30, 20, 0.5, (0.25, 0, 0.15)), Cadre(34, 24, 0.36, (0.25, 0, 0.15)),
                                      mi_doux), coupe=True),
                  Segment(1.6, glisse(Cadre(-60, 14, 0.8), Cadre(20, 30, 1.05)), coupe=True),
              )),
    Mouvement("balancier", "Balancier",
              "La vue va et vient de 40° de part et d'autre, comme un présentoir. Boucle sans à-coup.",
              20.0, (Segment(1, _balancier),), boucle=True),
    Mouvement("travelling", "Travelling latéral",
              "La caméra glisse en ligne droite le long du modèle, comme sur un rail.",
              10.0, (Segment(1, glisse(Cadre(20, 15, 0.8, (0, -0.6, 0)), Cadre(20, 15, 0.8, (0, 0.6, 0)))),)),
    Mouvement("dessus", "Vue de dessus tournante",
              "Vue presque à la verticale qui tourne d'un demi-tour, comme un plan de drone au zénith.",
              20.0, (Segment(1, _dessus),)),
)

PAR_NOM = {m.nom: m for m in CATALOGUE}
NOMS = tuple(PAR_NOM)
Reglages.CHOIX["anim_mouvement"] = NOMS


# ---------------------------------------------------------------- vers les poses
@dataclass(frozen=True)
class Repere:
    """Le modèle et la vue de départ, en coordonnées du monde."""
    centre: Vec
    rayon: float
    distance: float      # distance œil-cible qui cadre tout le modèle
    axe: Vec             # haut du monde, unitaire
    devant: Vec          # direction horizontale de la cible vers l'œil de la vue de départ, unitaire
    cote: Vec            # axe ^ devant


def pose(rep: Repere, c: Cadre, zoom: float = 1.0) -> tuple[Pose, float]:
    """Pose de la caméra pour un cadre, et facteur d'échelle (pour l'étendue d'une vue orthographique)."""
    dx, dy, dz = c.decal
    cible = ajoute(rep.centre, echelle(ajoute(ajoute(echelle(rep.devant, dx), echelle(rep.cote, dy)),
                                              echelle(rep.axe, dz)), rep.rayon))
    az, el = math.radians(c.az), math.radians(max(-HAUTEUR_MAX, min(HAUTEUR_MAX, c.el)))
    horiz = ajoute(echelle(rep.devant, math.cos(az)), echelle(rep.cote, math.sin(az)))
    direction = ajoute(echelle(horiz, math.cos(el)), echelle(rep.axe, math.sin(el)))
    facteur = c.dist / max(zoom, 1e-6)
    return Pose(ajoute(cible, echelle(direction, rep.distance * facteur)), cible, rep.axe), facteur


@dataclass(frozen=True)
class Cle:
    t: float
    pose: Pose
    facteur: float


def cles(mouvement: Mouvement, duree_s: float, rep: Repere, zoom: float = 1.0) -> list[Cle]:
    """Vues clés de l'animation, du temps 0 à duree_s (plus les coupes)."""
    total = sum(s.part for s in mouvement.segments) or 1.0
    res: list[Cle] = []
    t_debut = 0.0
    for i, seg in enumerate(mouvement.segments):
        d = duree_s * seg.part / total
        if seg.coupe and res:
            t_debut = res[-1].t + COUPE_S
        enchaine = bool(res) and not seg.coupe     # suite sans coupe : le premier point est déjà posé
        derniere = res[-1] if enchaine else None
        az_pose = seg.cadre(0.0).az
        for k in range(1 if enchaine else 0, FINESSE + 1):
            u = k / FINESSE
            t = t_debut + d * u
            cadre = seg.cadre(u)
            p, f = pose(rep, cadre, zoom)
            if derniere is not None and k < FINESSE:
                e_oeil = norme(soustrait(p.oeil, derniere.pose.oeil)) / rep.distance
                e_cible = norme(soustrait(p.cible, derniere.pose.cible)) / rep.distance
                if (e_oeil < ECART_MAX and e_cible < ECART_CIBLE_MAX and abs(cadre.az - az_pose) < AZIMUT_MAX
                        and t + d / FINESSE - derniere.t <= INTERVALLE_MAX_S):
                    continue
            derniere = Cle(t, p, f)
            az_pose = cadre.az
            res.append(derniere)
        t_debut += d
    return res
