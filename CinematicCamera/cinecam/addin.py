"""Add-in : boutons (lancer, réglages, animation), fil de surveillance, événement personnalisé de tic."""
from __future__ import annotations

import json
import threading
import time
import traceback
from pathlib import Path

import adsk.core

from . import mouvements, noyau, reglages_fichier
from .fusion_camera import PiloteCamera
from .inactivite import creer_lecteur, creer_lecteur_appuis
from .journal import journal, fermer

DOSSIER = Path(__file__).resolve().parent.parent
FICHIER_REGLAGES = DOSSIER / "reglages.json"
RESSOURCES = DOSSIER / "ressources"

PREFIXE = "lmchdCinematicCamera"
ID_LANCER = f"{PREFIXE}_lancer"
ID_REGLAGES = f"{PREFIXE}_reglages"
ID_ANIMATION = f"{PREFIXE}_animation"
ID_EVENEMENT = f"{PREFIXE}_tic"
ID_PANNEAU_ANIMATION = f"{PREFIXE}_panneauAnimation"
PANNEAUX = ("SolidScriptsAddinsPanel", "SolidInspectPanel")  # premier trouvé (mon choix)
COMMANDE_REPOS = "SelectCommand"  # [supposé] id de ui.activeCommand quand aucune commande ne tourne
NOM_LANCER, NOM_ARRETER = "Caméra cinématique", "Arrêter la caméra cinématique"

_handlers: list = []
_dialogue: list = []
_etat: dict = {}


class Veilleur(threading.Thread):
    """Tire l'événement de tic à l'intervalle demandé, jamais deux à la fois en file."""

    def __init__(self, app):
        super().__init__(daemon=True, name="CinematicCameraVeilleur")
        self.app = app
        self.stop_demande = threading.Event()
        self.en_attente = threading.Event()
        self.intervalle_s = 0.5

    def run(self):
        while not self.stop_demande.wait(self.intervalle_s):
            if self.en_attente.is_set():
                continue
            self.en_attente.set()
            try:
                self.app.fireCustomEvent(ID_EVENEMENT, "")  # le retour (False) ne dit rien : tirer une fois
            except Exception:
                self.en_attente.clear()


def _occupe(app, ui) -> bool:
    """Vrai si on ne doit pas tourner : pas de vue, pas un design, ou commande en cours."""
    try:
        if not app.activeViewport or not app.activeProduct:
            return True
        if app.activeProduct.objectType != "adsk::fusion::Design":
            return True
        cmd = ui.activeCommand
        return bool(cmd) and cmd not in (COMMANDE_REPOS, ID_LANCER)
    except Exception:
        return True


def _appliquer(action: noyau.Action) -> None:
    machine: noyau.Machine = _etat["machine"]
    pilote: PiloteCamera = _etat["pilote"]
    if action.type == noyau.DEMARRER:
        if not pilote.demarrer(machine.reglages):
            machine.echec(time.monotonic())
    elif action.type == noyau.PAS:
        if not pilote.pas(action.t_s, action.angle_deg):
            machine.echec(time.monotonic())
            pilote.arreter(False)
    elif action.type == noyau.ARRETER:
        pilote.arreter(action.restaurer)
    _maj_nom()


def _relancer_le_fil() -> None:
    veilleur = _etat.get("veilleur")
    if veilleur is not None and "machine" in _etat:
        veilleur.intervalle_s = (1 / 30 if _etat.get("animation") is not None
                                 else _etat["machine"].intervalle_tic_s())


def _pas_animation() -> None:
    """Un pas de la création d'animation, hors de toute commande : Fusion reprend la main entre deux pas."""
    from . import animation
    ui = _etat["ui"]
    try:
        next(_etat["animation"])
        return
    except StopIteration:
        r = _etat.get("animation_resultat") or {}
        fin = "Elle boucle sans à-coup. " if r.get("boucle") else ""
        ui.messageBox(f"Animation créée : {r.get('mouvement', '')}, {r.get('duree', 0):.0f} s ({r.get('vues', 0)} vues).\n"
                      f"{fin}Lecture : bouton Lecture sous la timeline du storyboard.", "Caméra cinématique")
    except animation.ErreurAnimation as e:
        ui.messageBox(str(e), "Caméra cinématique")
    except Exception:
        journal().error("animation :\n%s", traceback.format_exc())
        ui.messageBox("L'animation n'a pas pu être créée. Détail dans journal.log (dossier de "
                      "l'add-in).", "Caméra cinématique")
    _etat["animation"] = None


class GestionTic(adsk.core.CustomEventHandler):
    def notify(self, args):
        veilleur = _etat.get("veilleur")
        try:
            if _etat.get("animation") is not None:
                _pas_animation()
                return
            app, ui = _etat["app"], _etat["ui"]
            machine: noyau.Machine = _etat["machine"]
            action = machine.etape(_etat["lire_inactivite"](), time.monotonic(), _occupe(app, ui),
                                   _etat["lire_appuis"]())
            if action.type != noyau.RIEN:
                _appliquer(action)
        except Exception:
            journal().error("tic :\n%s", traceback.format_exc())
            try:
                _etat["machine"].echec(time.monotonic())
                _etat["pilote"].depart = None
                _maj_nom()
            except Exception:
                pass
        finally:
            _relancer_le_fil()
            if veilleur is not None:
                veilleur.en_attente.clear()


class GestionLancer(adsk.core.CommandCreatedEventHandler):
    """Un clic : la caméra part tout de suite. Un clic, une touche ou une commande l'arrête."""

    def notify(self, args):
        try:
            machine: noyau.Machine = _etat["machine"]
            action = machine.lancer_maintenant(time.monotonic())
            journal().info("bouton lancer : %s", action.type)
            _appliquer(action)
            _relancer_le_fil()
        except Exception:
            journal().error("bouton lancer :\n%s", traceback.format_exc())


# ---------------------------------------------------------------- dialogue de réglages
IN_AUTO, IN_DELAI, IN_TOUR = "auto", "delai", "tour"


class GestionReglages(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            cmd = adsk.core.CommandCreatedEventArgs.cast(args).command
            cmd.isRepeatable = False
            cmd.okButtonText = "OK"
            r = _etat["machine"].reglages
            inputs = cmd.commandInputs
            auto = inputs.addBoolValueInput(IN_AUTO, "Rotation quand je m'absente", True, "", r.actif)
            auto.tooltip = "La vue tourne seule après le temps choisi sans souris ni clavier."
            delai = inputs.addIntegerSpinnerCommandInput(IN_DELAI, "Temps avant activation (s)", 5, 3600, 5,
                                                         int(round(r.delai_s)))
            delai.tooltip = "Secondes sans souris ni clavier avant que la vue se mette à tourner."
            delai.isEnabled = r.actif
            tour = inputs.addIntegerSpinnerCommandInput(
                IN_TOUR, "Durée d'un tour (s)", 10, 600, 5,
                int(round(min(600, max(10, noyau.duree_tour_s(r.vitesse_deg_s))))))
            tour.tooltip = "Vitesse de rotation : 150 s = lent et calme, 30 s = rapide."
            for h, ev in ((GestionReglagesChange(), cmd.inputChanged), (GestionReglagesOK(), cmd.execute),
                          (GestionReglagesFin(), cmd.destroy)):
                ev.add(h)
                _dialogue.append(h)
        except Exception:
            journal().error("réglages :\n%s", traceback.format_exc())


def _lire(inputs) -> tuple[bool, int, int]:
    auto = adsk.core.BoolValueCommandInput.cast(inputs.itemById(IN_AUTO)).value
    delai = adsk.core.IntegerSpinnerCommandInput.cast(inputs.itemById(IN_DELAI)).value
    tour = adsk.core.IntegerSpinnerCommandInput.cast(inputs.itemById(IN_TOUR)).value
    return auto, delai, tour


class GestionReglagesChange(adsk.core.InputChangedEventHandler):
    def notify(self, args):
        try:
            inputs = adsk.core.InputChangedEventArgs.cast(args).inputs
            inputs.itemById(IN_DELAI).isEnabled = _lire(inputs)[0]
        except Exception:
            journal().error("réglages, changement :\n%s", traceback.format_exc())


class GestionReglagesOK(adsk.core.CommandEventHandler):
    def notify(self, args):
        try:
            inputs = adsk.core.CommandEventArgs.cast(args).command.commandInputs
            auto, delai, tour = _lire(inputs)
            machine: noyau.Machine = _etat["machine"]
            if machine.etat == noyau.ROTATION:      # la vitesse change : on repart d'un départ propre
                _appliquer(machine._arreter(time.monotonic()))
            machine.reglages.delai_s = float(delai)
            machine.reglages.vitesse_deg_s = noyau.vitesse_pour_tour(tour)
            machine.basculer(auto)
            reglages_fichier.ecrire(FICHIER_REGLAGES, machine.reglages)
            _maj_nom()
            _relancer_le_fil()
            journal().info("réglages : %s", json.dumps(machine.reglages.vers_dict(), ensure_ascii=False))
        except Exception:
            journal().error("réglages, OK :\n%s", traceback.format_exc())


class GestionReglagesFin(adsk.core.CommandEventHandler):
    def notify(self, args):
        _dialogue.clear()


# ---------------------------------------------------------------- animation
IN_MOUVEMENT, IN_DUREE, IN_ZOOM = "mouvement", "duree", "zoom"


class GestionAnimation(adsk.core.CommandCreatedEventHandler):
    """Dialogue avant la création : mouvement, durée (la vitesse), zoom."""

    def notify(self, args):
        try:
            cmd = adsk.core.CommandCreatedEventArgs.cast(args).command
            cmd.isRepeatable = False
            cmd.okButtonText = "Créer"
            r = _etat["machine"].reglages
            inputs = cmd.commandInputs
            liste = inputs.addDropDownCommandInput(IN_MOUVEMENT, "Mouvement",
                                                   adsk.core.DropDownStyles.TextListDropDownStyle)
            choisi = mouvements.PAR_NOM.get(r.anim_mouvement, mouvements.CATALOGUE[0])
            for m in mouvements.CATALOGUE:
                liste.listItems.add(m.libelle, m is choisi)
            liste.tooltip = "Type de mouvement de caméra."
            liste.tooltipDescription = choisi.info
            duree = inputs.addIntegerSpinnerCommandInput(IN_DUREE, "Durée (s)", 3, 600, 1,
                                                         int(round(r.anim_duree_s)))
            duree.tooltip = "Durée du mouvement : plus long = caméra plus lente."
            zoom = inputs.addIntegerSpinnerCommandInput(IN_ZOOM, "Zoom (%)", 50, 300, 10,
                                                        int(round(r.anim_zoom_pct)))
            zoom.tooltip = "100 % = modèle entier à l'image ; 200 % = deux fois plus près ; 50 % = plus loin."
            for h, ev in ((GestionAnimationChange(), cmd.inputChanged), (GestionAnimationOK(), cmd.execute),
                          (GestionReglagesFin(), cmd.destroy)):
                ev.add(h)
                _dialogue.append(h)
        except Exception:
            journal().error("animation, dialogue :\n%s", traceback.format_exc())


def _mouvement_choisi(inputs) -> mouvements.Mouvement:
    liste = adsk.core.DropDownCommandInput.cast(inputs.itemById(IN_MOUVEMENT))
    nom = liste.selectedItem.name if liste.selectedItem else ""
    return next((m for m in mouvements.CATALOGUE if m.libelle == nom), mouvements.CATALOGUE[0])


class GestionAnimationChange(adsk.core.InputChangedEventHandler):
    def notify(self, args):
        try:
            a = adsk.core.InputChangedEventArgs.cast(args)
            if a.input.id != IN_MOUVEMENT:
                return
            m = _mouvement_choisi(a.inputs)
            a.input.tooltipDescription = m.info
            adsk.core.IntegerSpinnerCommandInput.cast(a.inputs.itemById(IN_DUREE)).value = int(m.duree_defaut_s)
        except Exception:
            journal().error("animation, changement :\n%s", traceback.format_exc())


class GestionAnimationOK(adsk.core.CommandEventHandler):
    """Ne fait que vérifier et lancer : la création se fait par les tics, hors de la commande, car Fusion
    n'enregistre pas les vues posées pendant une commande [vérifié, essai 0.2.0]."""

    def notify(self, args):
        from . import animation
        ui = _etat["ui"]
        try:
            if _etat.get("animation") is not None:
                return
            inputs = adsk.core.CommandEventArgs.cast(args).command.commandInputs
            machine: noyau.Machine = _etat["machine"]
            r = machine.reglages
            r.anim_mouvement = _mouvement_choisi(inputs).nom
            r.anim_duree_s = float(adsk.core.IntegerSpinnerCommandInput.cast(inputs.itemById(IN_DUREE)).value)
            r.anim_zoom_pct = float(adsk.core.IntegerSpinnerCommandInput.cast(inputs.itemById(IN_ZOOM)).value)
            reglages_fichier.ecrire(FICHIER_REGLAGES, r)
            if machine.etat == noyau.ROTATION:
                _appliquer(machine._arreter(time.monotonic()))
            animation.verifier(_etat["app"])
            _etat["animation_resultat"] = {}
            _etat["animation"] = animation.etapes(_etat["app"], r, journal(), _etat["animation_resultat"])
            _relancer_le_fil()
            journal().info("animation demandée : %s, %.0f s, zoom %.0f %%", r.anim_mouvement, r.anim_duree_s,
                           r.anim_zoom_pct)
        except animation.ErreurAnimation as e:
            ui.messageBox(str(e), "Caméra cinématique")
        except Exception:
            journal().error("animation :\n%s", traceback.format_exc())
            ui.messageBox("L'animation n'a pas pu être créée. Détail dans journal.log (dossier de "
                          "l'add-in).", "Caméra cinématique")


# ---------------------------------------------------------------- interface
def _maj_nom():
    d = _etat.get("def_lancer")
    if d and "machine" in _etat:
        d.controlDefinition.name = NOM_ARRETER if _etat["machine"].etat == noyau.ROTATION else NOM_LANCER


def _espace_animation(ui):
    """L'espace de travail Animation, cherché par son id puis par son nom [supposé : id inconnu]."""
    try:
        espaces = ui.workspaces
        for i in range(espaces.count):
            e = espaces.item(i)
            if "animation" in (e.id or "").lower() or (e.name or "").strip().lower() == "animation":
                return e
    except Exception:
        journal().error("espace Animation :\n%s", traceback.format_exc())
    return None


def _onglet_animation(espace):
    """L'onglet ANIMATION de l'espace (pas OUTILS) ; None si l'espace n'a pas d'onglets lisibles.

    0.2.0 : un panneau ajouté à l'espace sans onglet tombait dans OUTILS [vérifié, Romain].
    """
    try:
        onglets = espace.toolbarTabs
        tous = [onglets.item(i) for i in range(onglets.count)]
    except Exception:
        return None
    journal().info("onglets de l'espace Animation : %s", [(o.id, o.name) for o in tous])
    for o in tous:
        if "anim" in (o.id or "").lower() or "anim" in (o.name or "").lower():
            return o
    autres = [o for o in tous if not any(m in f"{o.id} {o.name}".lower() for m in ("tool", "outil", "util"))]
    return autres[0] if autres else None


def _definition(ui, id_, nom, info, icone, gestion):
    ancienne = ui.commandDefinitions.itemById(id_)
    if ancienne:
        ancienne.deleteMe()
    d = ui.commandDefinitions.addButtonDefinition(id_, nom, info, str(RESSOURCES / icone))
    d.commandCreated.add(gestion)
    _handlers.append(gestion)
    return d


def _nettoyer_interface(ui):
    for p in PANNEAUX:
        panneau = ui.allToolbarPanels.itemById(p)
        if panneau:
            for id_ in (ID_LANCER, ID_REGLAGES):
                c = panneau.controls.itemById(id_)
                if c:
                    c.deleteMe()
    panneau = ui.allToolbarPanels.itemById(ID_PANNEAU_ANIMATION)
    if panneau:
        panneau.deleteMe()
    for id_ in (ID_LANCER, ID_REGLAGES, ID_ANIMATION):
        d = ui.commandDefinitions.itemById(id_)
        if d:
            d.deleteMe()


def run(context):
    if _etat:  # run() relancé sans stop() : on repart propre (fil, handlers, boutons)
        try:
            stop(context)
        except Exception:
            pass
    app = adsk.core.Application.get()
    ui = app.userInterface
    log = journal(DOSSIER)
    reglages = reglages_fichier.lire(FICHIER_REGLAGES)
    if not FICHIER_REGLAGES.exists():
        reglages_fichier.ecrire(FICHIER_REGLAGES, reglages)
    _etat.update(app=app, ui=ui, machine=noyau.Machine(reglages), pilote=PiloteCamera(app, log),
                 lire_inactivite=creer_lecteur(), lire_appuis=creer_lecteur_appuis())

    _nettoyer_interface(ui)
    try:
        app.unregisterCustomEvent(ID_EVENEMENT)
    except Exception:
        pass

    lancer = _definition(ui, ID_LANCER, NOM_LANCER,
                         "Fait tourner la vue lentement autour du modèle, tout de suite.\n"
                         "Un clic, une touche ou un nouveau clic sur ce bouton l'arrête ; la souris peut bouger.",
                         "icone", GestionLancer())
    reglages_def = _definition(ui, ID_REGLAGES, "Réglages de la caméra cinématique",
                               "Vitesse de rotation, temps avant activation, rotation quand vous vous absentez.",
                               "icone_reglages", GestionReglages())
    animation_def = _definition(ui, ID_ANIMATION, "Créer une animation caméra",
                                "Crée un storyboard : choix du mouvement (platine, drone, edit supercar…), "
                                "de sa durée et du zoom.", "icone_animation", GestionAnimation())
    _etat["def_lancer"] = lancer
    for p in PANNEAUX:
        panneau = ui.allToolbarPanels.itemById(p)
        if panneau:
            panneau.controls.addCommand(lancer).isPromoted = True
            panneau.controls.addCommand(reglages_def)
            _etat["panneau"] = p
            break
    espace = _espace_animation(ui)
    if espace is not None:
        onglet = _onglet_animation(espace)
        hote = onglet if onglet is not None else espace
        panneau = hote.toolbarPanels.add(ID_PANNEAU_ANIMATION, "CAMÉRA CINÉMATIQUE")
        _etat["onglet_animation"] = getattr(onglet, "id", None)
        panneau.controls.addCommand(animation_def).isPromoted = True
        panneau.controls.addCommand(reglages_def)
        _etat["espace_animation"] = espace.id
    _maj_nom()

    evenement = app.registerCustomEvent(ID_EVENEMENT)
    ht = GestionTic()
    evenement.add(ht)
    _handlers.append(ht)
    _etat["evenement"] = evenement
    _etat["gestion_tic"] = ht

    veilleur = Veilleur(app)
    _etat["veilleur"] = veilleur
    veilleur.start()
    log.info("démarré : version %s, réglages %s, panneau %s, espace Animation %s, onglet %s", app.version,
             json.dumps(reglages.vers_dict(), ensure_ascii=False), _etat.get("panneau"),
             _etat.get("espace_animation"), _etat.get("onglet_animation"))


def stop(context):
    log = journal()
    veilleur = _etat.pop("veilleur", None)
    if veilleur:
        veilleur.stop_demande.set()
        veilleur.join(2.0)
    pilote = _etat.get("pilote")
    if pilote and pilote.en_cours:
        try:
            pilote.arreter(_etat["machine"].reglages.restaurer_vue)
        except Exception:
            log.error("arrêt de la rotation :\n%s", traceback.format_exc())
    app, ui = _etat.get("app"), _etat.get("ui")
    if app:
        evenement = _etat.pop("evenement", None)
        if evenement and _etat.get("gestion_tic"):
            evenement.remove(_etat["gestion_tic"])
        app.unregisterCustomEvent(ID_EVENEMENT)
    if ui:
        _nettoyer_interface(ui)
    _handlers.clear()
    _dialogue.clear()
    log.info("arrêté")
    _etat.clear()
    fermer()
