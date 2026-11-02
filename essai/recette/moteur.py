"""Moteur de recette automatique (copie identique dans TimelineManager et CinematicCamera, un test le vérifie).

Une recette = une suite de blocs. Un bloc est une fonction génératrice `bloc(r)` qui joue des gestes dans
Fusion, note des points avec `r.point(...)` et rend la main à Fusion par `yield` :

    yield Attendre(0.5)              # laisser Fusion travailler 0,5 s (événements, commandes, caméra)
    yield AttendreCommande("Id", 10)  # attendre la fin d'une commande lancée par definition.execute()
    yield Capture("K1", "question")   # image de la vue + pause pour le juge (Claude Desktop)

Deux façons de tourner :
- par événements (défaut) : chaque `yield` rend la main à Fusion ; un fil tire un événement personnalisé
  pour reprendre. Fusion reste vivant ; les commandes lancées s'exécutent vraiment.
- synchrone (repli si les événements ne reviennent pas) : boucle `adsk.doEvents()` ; les commandes ne
  tournent pas (points marqués « À REGARDER »), les captures ne font pas de pause.

Aucun import d'adsk en tête : le moteur se teste sans Fusion.
"""

from __future__ import annotations

import json
import threading
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional

OK, KO, A_REGARDER, A_JUGER, A_FAIRE, NON_JOUE = "OK", "KO", "À REGARDER", "À JUGER", "À FAIRE", "NON JOUÉ"
VERDICTS_JUGE = (OK, KO, A_REGARDER)
AUTO, CAPTURE, MAIN = "auto", "capture", "à la main"


@dataclass(frozen=True)
class Attendre:
    secondes: float


@dataclass(frozen=True)
class AttendreCommande:
    commande: str
    delai_max: float = 15.0


@dataclass(frozen=True)
class Capture:
    code: str
    question: str
    delai_max: float = 240.0


@dataclass(frozen=True)
class Definition:
    """Un point du catalogue : ce qu'on vérifie, comment, ce qu'on attend."""

    code: str
    titre: str
    mode: str  # AUTO, CAPTURE, MAIN
    attendu: str
    geste: str = ""  # MAIN : ce que Romain fait


@dataclass
class Point:
    code: str
    titre: str
    mode: str
    attendu: str
    verdict: str
    mesure: object = None
    detail: str = ""
    capture: Optional[str] = None
    geste: str = ""


@dataclass
class Avancement:
    phase: str = "pas commencé"  # pas commencé, en cours, pause, fini
    bloc: str = ""
    pause: Optional[str] = None
    question: str = ""
    debut: float = field(default_factory=time.time)


class PiloteSynchrone:
    """Reprise immédiate : pour les tests et le mode synchrone dans Fusion."""

    synchrone = True

    def __init__(self, attendre: Optional[Callable[[float], None]] = None):
        self.attendre = attendre or (lambda s: None)
        self.reprendre: Callable[[Optional[int]], None] = lambda j=None: None

    def plus_tard(self, secondes: float, jeton: Optional[int] = None) -> None:
        self.attendre(secondes)

    def surveiller_commande(self, commande: str, jeton: int) -> None:
        pass

    def fermer(self) -> None:
        pass


class PiloteFusion:
    """Rend la main à Fusion entre deux gestes ; reprend par un événement personnalisé."""

    synchrone = False

    def __init__(self, id_evenement: str):
        import adsk.core  # noqa: PLC0415

        self.adsk = adsk
        self.app = adsk.core.Application.get()
        self.id = id_evenement
        self.reprendre: Callable[[Optional[int]], None] = lambda j=None: None
        self._commande: Optional[tuple[str, int]] = None
        self._minuteries: list = []
        self._handlers: list = []
        try:
            self.app.unregisterCustomEvent(self.id)
        except Exception:  # noqa: BLE001
            pass
        self.evenement = self.app.registerCustomEvent(self.id)
        pilote = self

        class _Reprise(adsk.core.CustomEventHandler):
            def notify(self, args):
                try:
                    jeton = int(adsk.core.CustomEventArgs.cast(args).additionalInfo)
                except Exception:  # noqa: BLE001
                    jeton = None
                pilote.reprendre(jeton)

        class _FinCommande(adsk.core.ApplicationCommandEventHandler):
            def notify(self, args):
                try:
                    cid = adsk.core.ApplicationCommandEventArgs.cast(args).commandId
                except Exception:  # noqa: BLE001
                    cid = None
                if pilote._commande is not None and cid == pilote._commande[0]:
                    jeton = pilote._commande[1]
                    pilote._commande = None
                    pilote.plus_tard(0.2, jeton)

        h = _Reprise()
        self.evenement.add(h)
        f = _FinCommande()
        self.app.userInterface.commandTerminated.add(f)
        self._handlers += [h, f]

    def plus_tard(self, secondes: float, jeton: Optional[int] = None) -> None:
        info = "" if jeton is None else str(jeton)
        t = threading.Timer(max(0.0, secondes), lambda: self.app.fireCustomEvent(self.id, info))
        t.daemon = True
        self._minuteries.append(t)
        t.start()

    def surveiller_commande(self, commande: str, jeton: int) -> None:
        self._commande = (commande, jeton)

    def annuler_minuteries(self) -> None:
        for t in self._minuteries:
            t.cancel()
        self._minuteries.clear()

    def fermer(self) -> None:
        self.annuler_minuteries()
        try:
            self.app.userInterface.commandTerminated.remove(self._handlers[1])
            self.evenement.remove(self._handlers[0])
            self.app.unregisterCustomEvent(self.id)
        except Exception:  # noqa: BLE001
            pass
        self._handlers.clear()


class Recette:
    """Joue les blocs, tient les points, écrit le rapport (JSON + Markdown)."""

    def __init__(self, nom: str, dossier_resultats: Path, catalogue: list[Definition],
                 blocs: list[tuple[str, Callable]], infos: Optional[dict] = None,
                 capturer: Optional[Callable[[Path], bool]] = None, horodatage: Optional[str] = None):
        self.nom = nom
        self.catalogue = {d.code: d for d in catalogue}
        if len(self.catalogue) != len(catalogue):
            raise ValueError("code de point en double dans le catalogue")
        self.blocs = list(blocs)
        self.infos = dict(infos or {})
        self.capturer = capturer
        self.horodatage = horodatage or time.strftime("%Y%m%d-%H%M%S")
        self.dossier = Path(dossier_resultats)
        self.dossier_captures = self.dossier / f"captures-{self.horodatage}"
        self.points: dict[str, Point] = {}
        for d in catalogue:
            v = A_FAIRE if d.mode == MAIN else NON_JOUE
            self.points[d.code] = Point(d.code, d.titre, d.mode, d.attendu, v, geste=d.geste)
        self.avancement = Avancement()
        self.pilote = None
        self._gen = None
        self._k = -1
        self._pause_jeton = 0
        self._jeton = 0
        self.erreurs: list[str] = []
        self.nettoyages: list[Callable[[], None]] = []
        self.finales: list[Callable[[], None]] = []
        self.memoire: dict = {}

    # ------------------------------------------------------------------ points

    def point(self, code: str, verdict: str, mesure=None, detail: str = "", attendu: Optional[str] = None) -> str:
        if code not in self.points:
            raise KeyError(f"point absent du catalogue : {code}")
        p = self.points[code]
        p.verdict, p.mesure, p.detail = verdict, _simple(mesure), detail
        if attendu:
            p.attendu = attendu
        return verdict

    def verifier(self, code: str, condition: bool, mesure=None, detail: str = "", sinon: str = KO) -> str:
        return self.point(code, OK if condition else sinon, mesure, detail)

    def juger(self, code: str, verdict: str, remarque: str = "") -> str:
        """Verdict du juge (Claude Desktop) sur un point « capture » (ou correction d'un autre point)."""
        if verdict not in VERDICTS_JUGE:
            return f"Verdict inconnu : {verdict!r} (attendu : {', '.join(VERDICTS_JUGE)})."
        p = self.points[code]
        p.verdict = verdict
        if remarque:
            p.detail = (p.detail + " — " if p.detail else "") + f"juge : {remarque}"
        if self.avancement.phase == "fini":
            self.ecrire()
        return f"{code} : {verdict}"

    # ------------------------------------------------------------------ déroulé

    def lancer(self, pilote) -> str:
        self.pilote = pilote
        pilote.reprendre = self._avancer
        self.avancement = Avancement(phase="en cours")
        self._k = -1
        self._suivant_bloc()
        if pilote.synchrone:
            while self.avancement.phase != "fini":
                self._avancer()
        else:
            pilote.plus_tard(0.05, self._nouveau_jeton())
        return self.etat()

    def _nouveau_jeton(self) -> int:
        self._jeton += 1
        return self._jeton

    def _suivant_bloc(self) -> None:
        self._k += 1
        if self._k >= len(self.blocs):
            self._gen = None
            return
        nom, fn = self.blocs[self._k]
        self.avancement.bloc = nom
        self._gen = fn(self)

    def _avancer(self, jeton: Optional[int] = None) -> None:
        """Reprise. Un jeton périmé (reprise en double : fin de commande puis filet) est ignoré."""
        if self.avancement.phase in ("fini", "pause"):
            return
        if jeton is not None and jeton != self._jeton:
            return
        try:
            while True:
                if self._gen is None:
                    self._finir()
                    return
                try:
                    attente = next(self._gen)
                except StopIteration:
                    self._nettoyer()
                    self._suivant_bloc()
                    continue
                except Exception:  # noqa: BLE001
                    self._erreur_bloc(traceback.format_exc())
                    self._nettoyer()
                    self._suivant_bloc()
                    continue
                if self._attendre(attente):
                    return
        except Exception:  # noqa: BLE001
            self.erreurs.append(traceback.format_exc())
            self._finir()

    def _attendre(self, attente) -> bool:
        """True : on rend la main (Fusion reprendra) ; False : on continue tout de suite."""
        p = self.pilote
        if isinstance(attente, Attendre):
            p.plus_tard(attente.secondes, self._nouveau_jeton())
            return not p.synchrone
        if isinstance(attente, AttendreCommande):
            if p.synchrone:
                self.memoire["commande_non_jouee"] = attente.commande
                return False
            self.memoire.pop("commande_non_jouee", None)
            j = self._nouveau_jeton()
            p.surveiller_commande(attente.commande, j)
            p.plus_tard(attente.delai_max, j)  # filet : reprise même si la fin de commande n'arrive pas
            return True
        if isinstance(attente, Capture):
            self._capturer(attente)
            if p.synchrone:
                return False
            self.avancement.phase = "pause"
            self.avancement.pause = attente.code
            self.avancement.question = attente.question
            self._nouveau_jeton()  # toute reprise en vol devient périmée
            self._pause_jeton += 1
            jeton = self._pause_jeton
            t = threading.Timer(attente.delai_max, lambda: self._fin_de_pause(jeton))
            t.daemon = True
            t.start()
            return True
        raise TypeError(f"attente inconnue : {attente!r}")

    def _capturer(self, c: Capture) -> None:
        p = self.points[c.code]
        p.verdict = A_JUGER
        p.detail = c.question
        if self.capturer is None:
            return
        try:
            self.dossier_captures.mkdir(parents=True, exist_ok=True)
            chemin = self.dossier_captures / f"{c.code}.png"
            if self.capturer(chemin):
                p.capture = str(chemin)
        except Exception:  # noqa: BLE001
            self.erreurs.append(f"capture {c.code} :\n{traceback.format_exc()}")

    def _fin_de_pause(self, jeton: int) -> None:
        if self.avancement.phase == "pause" and jeton == self._pause_jeton and self.pilote is not None:
            self.memoire.setdefault("pauses_expirees", []).append(self.avancement.pause)
            self.continuer()

    def continuer(self) -> str:
        """Fin de la pause de capture : la recette reprend."""
        if self.avancement.phase != "pause":
            return self.etat()
        self.avancement.phase = "en cours"
        self.avancement.pause = None
        self.avancement.question = ""
        if self.pilote.synchrone:
            self._avancer()
        else:
            self.pilote.plus_tard(0.05, self._nouveau_jeton())
        return self.etat()

    def _erreur_bloc(self, trace: str) -> None:
        nom = self.avancement.bloc
        self.erreurs.append(f"bloc {nom} :\n{trace}")
        for p in self.points.values():
            if p.verdict == NON_JOUE and p.code in self.memoire.get(f"bloc:{nom}", ()):
                p.verdict, p.detail = KO, "erreur de la recette dans ce bloc (trace en fin de rapport)"

    def declarer_bloc(self, codes: tuple[str, ...]) -> None:
        """Points que le bloc courant doit noter : en cas d'erreur, ils passent en KO."""
        self.memoire[f"bloc:{self.avancement.bloc}"] = codes

    def au_nettoyage(self, fn: Callable[[], None]) -> None:
        """Nettoyage du bloc courant (document de test à fermer…), joué en fin de bloc ou d'étape."""
        self.nettoyages.append(fn)

    def a_la_fin(self, fn: Callable[[], None]) -> None:
        """Joué une fois, à la toute fin (rendre le document de Romain, réglage à remettre…)."""
        self.finales.append(fn)

    def nettoyer(self) -> None:
        self._nettoyer()

    def proteger(self, codes: tuple[str, ...], fn: Callable, *args):
        """Joue fn ; une exception passe les points `codes` encore non joués en KO, la recette continue."""
        try:
            return fn(*args)
        except Exception:  # noqa: BLE001
            self.erreurs.append(f"{', '.join(codes)} :\n{traceback.format_exc()}")
            for c in codes:
                if self.points[c].verdict == NON_JOUE:
                    self.point(c, KO, detail="erreur de la recette (trace en fin de rapport)")
            return None

    def _nettoyer(self) -> None:
        while self.nettoyages:
            fn = self.nettoyages.pop()
            try:
                fn()
            except Exception:  # noqa: BLE001
                self.erreurs.append(f"nettoyage :\n{traceback.format_exc()}")

    def _finir(self) -> None:
        if self.avancement.phase == "fini":
            return
        self._nettoyer()
        while self.finales:
            fn = self.finales.pop()
            try:
                fn()
            except Exception:  # noqa: BLE001
                self.erreurs.append(f"fin :\n{traceback.format_exc()}")
        self.avancement.phase = "fini"
        self.avancement.bloc = ""
        self.infos["duree_s"] = round(time.time() - self.avancement.debut, 1)
        if self.pilote is not None:
            self.pilote.fermer()
        self.ecrire()

    def arreter(self) -> str:
        """Arrêt d'urgence : nettoie (documents de test fermés) et écrit le rapport."""
        if self._gen is not None:
            try:
                self._gen.close()
            except Exception:  # noqa: BLE001
                pass
        self.erreurs.append("recette arrêtée avant la fin")
        self._gen = None
        self._k = len(self.blocs)
        self.avancement.phase = "en cours"
        self._finir()
        return self.etat()

    # ------------------------------------------------------------------ rapport

    def compte(self) -> dict[str, int]:
        c: dict[str, int] = {}
        for p in self.points.values():
            c[p.verdict] = c.get(p.verdict, 0) + 1
        return c

    def chemins(self) -> tuple[Path, Path]:
        base = self.dossier / f"recette-{self.horodatage}"
        return base.with_suffix(".json"), base.with_suffix(".md")

    def ecrire(self) -> tuple[Path, Path]:
        self.dossier.mkdir(parents=True, exist_ok=True)
        fj, fm = self.chemins()
        donnees = {
            "recette": self.nom,
            "horodatage": self.horodatage,
            "infos": self.infos,
            "compte": self.compte(),
            "points": [asdict(p) for p in self.points.values()],
            "erreurs": self.erreurs,
            "memoire": {k: v for k, v in self.memoire.items() if not k.startswith("bloc:")},
        }
        fj.write_text(json.dumps(donnees, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        fm.write_text(self.markdown(), encoding="utf-8")
        return fj, fm

    def markdown(self) -> str:
        c = self.compte()
        lignes = [f"# Recette {self.nom} — {self.horodatage}", ""]
        for k, v in self.infos.items():
            lignes.append(f"- {k} : {v}")
        lignes += ["", "Compte : " + " · ".join(f"{k} {v}" for k, v in sorted(c.items())), ""]
        lignes += ["| Point | Mode | Verdict | Mesure | Attendu | Détail |", "|---|---|---|---|---|---|"]
        for p in self.points.values():
            if p.mode == MAIN:
                continue
            mesure = json.dumps(p.mesure, ensure_ascii=False, default=str) if p.mesure is not None else ""
            detail = p.detail + (f" — capture : `{Path(p.capture).name}`" if p.capture else "")
            lignes.append(f"| {p.code} {p.titre} | {p.mode} | **{p.verdict}** | {_cellule(mesure)} | "
                          f"{_cellule(p.attendu)} | {_cellule(detail)} |")
        mains = [p for p in self.points.values() if p.mode == MAIN]
        if mains:
            lignes += ["", "## À la main (Romain)", ""]
            for p in mains:
                lignes.append(f"- **{p.code}** {p.geste} *Attendu : {p.attendu}* — {p.verdict}")
        if self.erreurs:
            lignes += ["", "## Erreurs de la recette", ""]
            for e in self.erreurs:
                lignes += ["```", e.strip(), "```"]
        return "\n".join(lignes) + "\n"

    def etat(self) -> str:
        a = self.avancement
        if a.phase == "pause":
            return (f"PAUSE capture {a.pause} : {a.question}\n"
                    f"Image : {self.points[a.pause].capture or '(pas d’image)'}\n"
                    f"Regarde la vue de Fusion, puis juger('{a.pause}', 'OK'|'KO'|'À REGARDER', 'remarque') "
                    "et continuer().")
        if a.phase == "fini":
            fj, fm = self.chemins()
            return (f"FINI en {self.infos.get('duree_s', '?')} s. "
                    + " · ".join(f"{k} {v}" for k, v in sorted(self.compte().items()))
                    + f"\nRapport : {fm}\nDonnées : {fj}")
        return f"{a.phase.upper()} : bloc « {a.bloc} »."


def _simple(x):
    """Mesure rendue sérialisable (nombres arrondis)."""
    if isinstance(x, float):
        return round(x, 4)
    if isinstance(x, dict):
        return {str(k): _simple(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_simple(v) for v in x]
    return x


def _cellule(texte: str) -> str:
    return str(texte).replace("|", "\\|").replace("\n", " ")
