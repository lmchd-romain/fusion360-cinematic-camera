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

from .noyau import Pose, Reglages, Vec, ajoute, echelle, norme, scalaire, soustrait, unitaire, vectoriel

COUPE_S = 0.04            # durée d'un changement de plan franc (un peu plus d'une image à 25 i/s)
ECART_MAX = 0.06          # écart d'œil maximal entre deux vues, en part de la distance de cadrage
ECART_CIBLE_MAX = 0.03
INTERVALLE_MAX_S = 1.0
AZIMUT_MAX = 5.0          # degrés de rotation au plus entre deux vues (vue de dessus : l'œil bouge peu)
FOV_MAX = 2.0             # degrés d'angle de vue au plus entre deux vues
FINESSE = 400             # points examinés par segment pour placer les vues
FOV_BORNES = (5.0, 120.0)
HAUTEUR_MAX = 85.0        # au-delà, le haut de la vue se confond avec le regard


@dataclass(frozen=True)
class Cadre:
    az: float                      # degrés, 0 = côté de la vue de départ
    el: float                      # degrés au-dessus de l'horizon
    dist: float = 1.0              # facteur de la distance qui cadre le modèle entier
    decal: Vec = (0.0, 0.0, 0.0)   # décalage de la cible, en rayons : (devant, côté, haut)
    fov: float | None = None       # angle de vue (degrés) ; None = celui choisi dans le dialogue, ou l'actuel


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


def rampe(u: float, k: float = 6.0) -> float:
    """Rampe de vitesse : lent, coup d'accélérateur au milieu, lent (sigmoïde normalisée)."""
    u = min(1.0, max(0.0, u))
    return 0.5 + 0.5 * math.tanh(k * (u - 0.5)) / math.tanh(k / 2)


def entree(u: float) -> float:
    """Part lentement et finit à fond (avant une coupe)."""
    return min(1.0, max(0.0, u)) ** 3


def sortie(u: float) -> float:
    """Part à fond et se pose (après une coupe)."""
    return 1.0 - (1.0 - min(1.0, max(0.0, u))) ** 3


def bosse(u: float) -> float:
    """0 au début et à la fin, 1 au milieu : l'objectif s'ouvre au plus vite du mouvement."""
    return math.sin(math.pi * min(1.0, max(0.0, u))) ** 2


def _mix(a: float, b: float, s: float) -> float:
    return a + (b - a) * s


def glisse(a: Cadre, b: Cadre, courbe=doux) -> Callable[[float], Cadre]:
    def f(u: float) -> Cadre:
        s = courbe(u)
        fov = None if a.fov is None or b.fov is None else _mix(a.fov, b.fov, s)
        return Cadre(_mix(a.az, b.az, s), _mix(a.el, b.el, s), _mix(a.dist, b.dist, s),
                     tuple(_mix(x, y, s) for x, y in zip(a.decal, b.decal)), fov)
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


def _quatre_faces(u):
    """Quatre quarts de tour, chacun suivi d'une pause : 70 % du temps en mouvement, 30 % à l'arrêt."""
    k = min(3, int(u * 4))
    v = u * 4 - k
    return Cadre(90.0 * (k + doux(v / 0.7)), 30.0)


def _huit(u):
    w = 2 * math.pi * u
    return Cadre(50.0 * math.sin(w), 25.0 + 15.0 * math.sin(2 * w), 1.0)


def _coups_de_zoom(u):
    """Trois coups de zoom secs (angle de vue qui se resserre vite), chacun suivi d'un temps de pose."""
    k = min(2, int(u * 3))
    v = u * 3 - k
    fovs = (60.0, 38.0, 24.0, 15.0)
    return Cadre(10.0 + 20.0 * u, 20.0, 1.0, fov=_mix(fovs[k], fovs[k + 1], doux(min(1.0, v / 0.15))))


def _orbite_eclair(u):
    return Cadre(-40.0 + 360.0 * rampe(u), 20.0, 1.0, fov=40.0 + 55.0 * bosse(u))


def _pulsation(u):
    """Rotation lente ; à chaque temps (8 dans l'animation), l'objectif se resserre d'un coup puis se relâche."""
    temps = 8
    k = min(temps - 1, int(u * temps))
    v = u * temps - k
    coup = doux(v / 0.12) if v < 0.12 else 1.0 - doux((v - 0.12) / 0.88)
    return Cadre(60.0 * u, 22.0, 1.0, fov=46.0 - 16.0 * coup)


def _vertigo_orbital(u):
    s = doux(u)
    return Cadre(90.0 * s, 18.0, 1.0, fov=75.0 - 60.0 * s)


def _chute(u):
    s = doux(u)
    return Cadre(90.0 * s, 84.0 - 46.0 * s, 1.0, fov=112.0 - 67.0 * s)


def _plan(az0, az1, el0, el1, d0, d1, f0, f1, courbe_pos=doux, courbe_fov=None, decal=(0.0, 0.0, 0.0)):
    """Plan de montage : position et objectif sur deux courbes différentes."""
    courbe_fov = courbe_fov or courbe_pos

    def f(u):
        s, sf = courbe_pos(u), courbe_fov(u)
        return Cadre(_mix(az0, az1, s), _mix(el0, el1, s), _mix(d0, d1, s), decal, _mix(f0, f1, sf))
    return f


def _crash(u):
    """Zoom éclair de l'objectif dans le premier quart, puis plan fixe qui glisse à peine."""
    return Cadre(20.0 + 6.0 * u, 25.0, 1.0, (0.2, 0.0, 0.1), _mix(62.0, 16.0, sortie(min(1.0, u / 0.25))))


def _whip(u):
    return Cadre(120.0 + 140.0 * rampe(u, 7.0), 15.0, 1.0, fov=50.0 + 35.0 * bosse(u))


def _tornade(u):
    s = doux(u)
    return Cadre(540.0 * s, 84.0 - 69.0 * s, 1.45 - 0.5 * s)


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
    Mouvement("quatre_faces", "Quatre faces (tourne et s'arrête)",
              "Un quart de tour, une pause, quatre fois : chaque face se montre. Boucle sans à-coup.",
              20.0, (Segment(1, _quatre_faces),), boucle=True),
    Mouvement("heroique", "Contre-plongée héroïque",
              "Caméra basse qui s'approche en tournant légèrement : le modèle paraît imposant.",
              8.0, (Segment(1, glisse(Cadre(-25, 3, 1.0, (0, 0, -0.25)), Cadre(15, 9, 0.7, (0, 0, -0.1)))),)),
    Mouvement("approche", "Approche lente",
              "La caméra avance tout droit vers le modèle, de loin à tout près. Avec « Cadrer sur », "
              "elle va vers la pièce choisie.",
              8.0, (Segment(1, glisse(Cadre(30, 22, 1.3), Cadre(30, 22, 0.45))),)),
    Mouvement("huit", "Orbite en 8",
              "La caméra dessine un huit autour du modèle : va-et-vient en montant et descendant. Boucle.",
              24.0, (Segment(1, _huit),), boucle=True),
    Mouvement("vertigo", "Vertigo (dolly zoom)",
              "Effet Hitchcock : la caméra recule pendant que l'angle de vue se resserre ; le modèle garde sa "
              "taille, la perspective s'écrase. Puis l'inverse.",
              10.0, (Segment(1, glisse(Cadre(25, 15, 1.0, fov=80), Cadre(25, 15, 1.0, fov=14))),
                     Segment(1, glisse(Cadre(25, 15, 1.0, fov=14), Cadre(25, 15, 1.0, fov=80)))), boucle=True),
    Mouvement("grand_angle", "Grand angle supercar",
              "Objectif très large, tout près et au ras du sol : perspective exagérée, comme les pubs de "
              "voiture. Tourne lentement.",
              8.0, (Segment(1, glisse(Cadre(-40, 5, 0.75, (0, 0, -0.25), 95), Cadre(40, 8, 0.75, (0, 0, -0.25), 95))),)),
    Mouvement("teleobjectif", "Téléobjectif",
              "Objectif très serré, de loin : perspective aplatie, rendu photo produit. Tourne lentement.",
              12.0, (Segment(1, glisse(Cadre(-30, 20, 1.0, fov=12), Cadre(30, 20, 1.0, fov=12))),)),
    Mouvement("coups_zoom", "Coups de zoom",
              "Trois zooms secs de l'objectif, chacun suivi d'une pause, sur un lent glissement. "
              "Avec « Cadrer sur », zoome vers la pièce choisie.",
              6.0, (Segment(1, _coups_de_zoom),)),
    Mouvement("tornade", "Descente en tornade",
              "Part du zénith et descend en spirale d'un tour et demi jusqu'à une vue de trois-quarts.",
              14.0, (Segment(1, _tornade),)),
    Mouvement("eclair", "Orbite éclair (rampe de vitesse)",
              "Lent, puis un tour fouetté à toute vitesse, puis lent : l'objectif s'ouvre en grand au plus vite, "
              "la perspective s'étire comme une accélération.",
              6.0, (Segment(1, _orbite_eclair),)),
    Mouvement("warp", "Transitions warp (perspective étirée)",
              "La caméra fonce sur le modèle en ouvrant l'objectif à l'extrême ; coupe au sommet de l'étirement, "
              "le plan suivant repart d'un autre côté en se resserrant. Deux fois, puis plan final.",
              8.0, (
                  Segment(1.0, _plan(0, 18, 20, 16, 1.0, 0.8, 40, 115, entree, entree)),
                  Segment(1.0, _plan(150, 168, 30, 26, 0.8, 1.0, 115, 42, sortie, sortie), coupe=True),
                  Segment(1.0, _plan(168, 186, 26, 22, 1.0, 0.8, 42, 115, entree, entree)),
                  Segment(1.4, _plan(290, 320, 14, 24, 0.8, 1.0, 115, 38, sortie, sortie), coupe=True),
              )),
    Mouvement("pulsation", "Pulsation rythmée",
              "Rotation lente ; huit coups d'objectif réguliers, comme sur le rythme d'une musique. Durée = "
              "8 temps (8 s : un temps par seconde ; 4 s : 120 battements par minute).",
              8.0, (Segment(1, _pulsation),)),
    Mouvement("vertigo_orbital", "Vertigo en orbite",
              "Dolly zoom pendant un quart de tour : la perspective s'aplatit en tournant, le modèle garde sa "
              "taille.",
              8.0, (Segment(1, _vertigo_orbital),)),
    Mouvement("chute", "Chute grand angle",
              "Part du dessus avec un objectif extrême, descend en tournant pendant que l'objectif se referme : "
              "la perspective se détend.",
              8.0, (Segment(1, _chute),)),
    Mouvement("montage_fov", "Montage dynamique (objectifs)",
              "Montage nerveux, six plans coupés franc : grand angle au ras du sol, téléobjectif qui glisse, "
              "zoom éclair, tour fouetté, vertigo, plan final qui se pose.",
              14.0, (
                  Segment(0.9, _plan(-30, -18, 4, 5, 0.95, 0.78, 100, 100, mi_doux)),
                  Segment(0.9, _plan(70, 96, 12, 12, 1.0, 1.0, 14, 14, mi_doux), coupe=True),
                  Segment(0.7, _crash, coupe=True),
                  Segment(0.8, _whip, coupe=True),
                  Segment(0.8, _plan(200, 206, 10, 10, 1.0, 1.0, 20, 80, mi_doux), coupe=True),
                  Segment(1.4, _plan(-60, 10, 12, 28, 0.85, 1.0, 92, 40, doux, sortie), coupe=True),
              )),
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
    angle: float | None = None   # angle de vue de départ (degrés) ; None = vue orthographique (pas d'objectif)


def pose(rep: Repere, c: Cadre, zoom: float = 1.0, fov: float | None = None) -> tuple[Pose, float, float | None]:
    """Pose de la caméra pour un cadre, facteur d'échelle (étendue d'une vue orthographique) et angle de vue.

    Avec un autre angle de vue que celui de départ, la distance change pour que le modèle garde sa taille à
    l'image (c'est ce qui fait le « dolly zoom »).
    """
    dx, dy, dz = c.decal
    cible = ajoute(rep.centre, echelle(ajoute(ajoute(echelle(rep.devant, dx), echelle(rep.cote, dy)),
                                              echelle(rep.axe, dz)), rep.rayon))
    az, el = math.radians(c.az), math.radians(max(-HAUTEUR_MAX, min(HAUTEUR_MAX, c.el)))
    horiz = ajoute(echelle(rep.devant, math.cos(az)), echelle(rep.cote, math.sin(az)))
    direction = ajoute(echelle(horiz, math.cos(el)), echelle(rep.axe, math.sin(el)))
    facteur = c.dist / max(zoom, 1e-6)
    angle = None
    distance = rep.distance
    if rep.angle is not None:
        angle = min(FOV_BORNES[1], max(FOV_BORNES[0], c.fov or fov or rep.angle))
        distance *= math.sin(math.radians(rep.angle) / 2) / math.sin(math.radians(angle) / 2)
    return Pose(ajoute(cible, echelle(direction, distance * facteur)), cible, rep.axe), facteur, angle


def orienter(axe: Vec, devant: Vec, dessus: Vec | None = None, avant: Vec | None = None) -> tuple[Vec, Vec, Vec]:
    """(haut, devant, côté) du repère des mouvements.

    `dessus` : normale de la face choisie comme dessus du meuble (sinon l'axe vertical de Fusion).
    `avant` : normale de la face choisie comme face avant (sinon le côté de la vue actuelle). Ramenée à
    l'horizontale ; si elle est presque verticale, le côté de la vue actuelle reste.
    """
    haut = unitaire(dessus) if dessus is not None and norme(dessus) > 1e-9 else unitaire(axe)

    def a_plat(v):
        h = soustrait(v, echelle(haut, scalaire(v, haut)))
        return unitaire(h) if norme(h) > 0.2 * norme(v) else None

    face = a_plat(avant) if avant is not None and norme(avant) > 1e-9 else None
    devant_plat = face or a_plat(devant)
    if devant_plat is None:     # vue actuelle de dessus ou de dessous : un côté quelconque
        aide = (1.0, 0.0, 0.0) if abs(haut[0]) < 0.9 else (0.0, 1.0, 0.0)
        devant_plat = unitaire(vectoriel(haut, aide))
    return haut, devant_plat, vectoriel(haut, devant_plat)


@dataclass(frozen=True)
class Cle:
    t: float
    pose: Pose
    facteur: float
    fov: float | None = None


def cles(mouvement: Mouvement, duree_s: float, rep: Repere, zoom: float = 1.0,
         fov: float | None = None) -> list[Cle]:
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
            p, f, a = pose(rep, cadre, zoom, fov)
            if derniere is not None and k < FINESSE:
                e_oeil = norme(soustrait(p.oeil, derniere.pose.oeil)) / rep.distance
                e_cible = norme(soustrait(p.cible, derniere.pose.cible)) / rep.distance
                e_fov = abs((a or 0.0) - (derniere.fov or 0.0))
                if (e_oeil < ECART_MAX and e_cible < ECART_CIBLE_MAX and abs(cadre.az - az_pose) < AZIMUT_MAX
                        and e_fov < FOV_MAX and t + d / FINESSE - derniere.t <= INTERVALLE_MAX_S):
                    continue
            derniere = Cle(t, p, f, a)
            az_pose = cadre.az
            res.append(derniere)
        t_debut += d
    return res
