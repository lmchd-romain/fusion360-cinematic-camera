"""Add-in : bouton marche / arrêt, fil de surveillance, événement personnalisé de tic."""
from __future__ import annotations

import json
import threading
import time
import traceback
from pathlib import Path

import adsk.core

from . import noyau, reglages_fichier
from .fusion_camera import PiloteCamera
from .inactivite import creer_lecteur
from .journal import journal, fermer

DOSSIER = Path(__file__).resolve().parent.parent
FICHIER_REGLAGES = DOSSIER / "reglages.json"

ID_CMD = "lmchdCinematicCamera_basculer"
ID_EVENEMENT = "lmchdCinematicCamera_tic"
PANNEAUX = ("SolidScriptsAddinsPanel", "SolidInspectPanel")  # premier trouvé (mon choix)
COMMANDE_REPOS = "SelectCommand"  # [supposé] id de ui.activeCommand quand aucune commande ne tourne

_handlers: list = []
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
        return bool(cmd) and cmd != COMMANDE_REPOS
    except Exception:
        return True


class GestionTic(adsk.core.CustomEventHandler):
    def notify(self, args):
        veilleur = _etat.get("veilleur")
        try:
            app, ui = _etat["app"], _etat["ui"]
            machine: noyau.Machine = _etat["machine"]
            pilote: PiloteCamera = _etat["pilote"]
            action = machine.etape(_etat["lire_inactivite"](), time.monotonic(), _occupe(app, ui))
            if action.type == noyau.DEMARRER:
                if not pilote.demarrer(machine.reglages):
                    machine.echec()
            elif action.type == noyau.PAS:
                pilote.pas(action.t_s, action.angle_deg)
            elif action.type == noyau.ARRETER:
                pilote.arreter(action.restaurer)
        except Exception:
            journal().error("tic :\n%s", traceback.format_exc())
            try:
                _etat["machine"].echec()
                _etat["pilote"].depart = None
            except Exception:
                pass
        finally:
            if veilleur is not None:
                veilleur.intervalle_s = _etat["machine"].intervalle_tic_s() if "machine" in _etat else 0.5
                veilleur.en_attente.clear()


class GestionBouton(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            machine: noyau.Machine = _etat["machine"]
            actif = not machine.reglages.actif
            action = machine.basculer(actif)
            if action.type == noyau.ARRETER:
                _etat["pilote"].arreter(action.restaurer)
            reglages_fichier.ecrire(FICHIER_REGLAGES, machine.reglages)
            _maj_nom()
            r = machine.reglages
            msg = (f"Caméra auto : MARCHE. Rotation après {r.delai_s:g} s sans souris ni clavier.\n"
                   f"Auto camera: ON. Turns after {r.delai_s:g} s without mouse or keyboard."
                   if actif else
                   "Caméra auto : ARRÊT.\nAuto camera: OFF.")
            journal().info("bouton : actif=%s", actif)
            _etat["ui"].messageBox(msg, "CinematicCamera")
        except Exception:
            journal().error("bouton :\n%s", traceback.format_exc())


def _maj_nom():
    d = _etat.get("definition")
    if d:
        actif = _etat["machine"].reglages.actif
        d.controlDefinition.name = "Caméra auto : marche" if actif else "Caméra auto : arrêt"


def run(context):
    if _etat:  # run() relancé sans stop() : on repart propre (fil, handlers, bouton)
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
                 lire_inactivite=creer_lecteur())

    # Restes d'un arrêt incomplet.
    for p in PANNEAUX:
        panneau = ui.allToolbarPanels.itemById(p)
        if panneau:
            c = panneau.controls.itemById(ID_CMD)
            if c:
                c.deleteMe()
    ancienne = ui.commandDefinitions.itemById(ID_CMD)
    if ancienne:
        ancienne.deleteMe()
    try:
        app.unregisterCustomEvent(ID_EVENEMENT)
    except Exception:
        pass

    definition = ui.commandDefinitions.addButtonDefinition(
        ID_CMD, "Caméra auto", "Marche / arrêt de la rotation automatique quand vous êtes absent.\n"
        "On / off: auto-rotate the view when you are away.", str(DOSSIER / "ressources" / "icone"))
    h = GestionBouton()
    definition.commandCreated.add(h)
    _handlers.append(h)
    _etat["definition"] = definition
    for p in PANNEAUX:
        panneau = ui.allToolbarPanels.itemById(p)
        if panneau:
            panneau.controls.addCommand(definition)
            _etat["panneau"] = p
            break
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
    log.info("démarré : version %s, réglages %s, panneau %s", app.version,
             json.dumps(reglages.vers_dict(), ensure_ascii=False), _etat.get("panneau"))


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
        p = _etat.get("panneau")
        panneau = ui.allToolbarPanels.itemById(p) if p else None
        if panneau:
            c = panneau.controls.itemById(ID_CMD)
            if c:
                c.deleteMe()
        d = ui.commandDefinitions.itemById(ID_CMD)
        if d:
            d.deleteMe()
    _handlers.clear()
    log.info("arrêté")
    _etat.clear()
    fermer()
