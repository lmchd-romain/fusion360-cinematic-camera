"""Sonde : peut-on faire bouger des pièces dans un storyboard de l'espace Animation, par le complément ?

À lancer par Claude Desktop à travers le MCP de Fusion (voir MESSAGE.md), ou à la main comme script
(Utilitaires → Scripts et compléments → Scripts → « + » → ce dossier → Exécuter). Dure ~30 s.

Tout se joue dans un document NEUF (une caisse, un couvercle, un tiroir), jamais enregistré, refermé sans
enregistrer. Rapport : ../resultats/sonde-pieces-<horodatage>.json.

Questions :
- Q1 : enregistrement des vues allumé, une occurrence déplacée par `transform2` à la tête de lecture 2 s :
  Fusion crée-t-il une action (fin du storyboard qui avance) ?
- Q2 : même chose, enregistrement éteint.
- Q3 : le déplacement reste-t-il dans le design (position de retour dans l'espace Conception, timeline,
  document modifié) ?
- Q4 : quelles commandes natives de l'espace Animation existent (identifiants : transformer, éclater,
  afficher / masquer) ?
- Q5 : « éclatement automatique » natif lancé par son identifiant, pièces présélectionnées : une action
  apparaît-elle ?
"""
from __future__ import annotations

import json
import time
import traceback
from pathlib import Path

import adsk.core
import adsk.fusion

ICI = Path(__file__).resolve().parent
RESULTATS = ICI.parent / "resultats"


def _attendre(s: float) -> None:
    fin = time.perf_counter() + s
    while time.perf_counter() < fin:
        adsk.doEvents()
        time.sleep(0.02)


def _boite(comp, lx, ly, lz):
    """Pavé par esquisse + extrusion, cm, coin à l'origine du composant."""
    esq = comp.sketches.add(comp.xYConstructionPlane)
    p = adsk.core.Point3D.create
    esq.sketchCurves.sketchLines.addTwoPointRectangle(p(0, 0, 0), p(lx, ly, 0))
    comp.features.extrudeFeatures.addSimple(esq.profiles.item(0), adsk.core.ValueInput.createByReal(lz),
                                            adsk.fusion.FeatureOperations.NewBodyFeatureOperation)


def _composant(design, nom, x, y, z, lx, ly, lz):
    racine = design.rootComponent
    occ = racine.occurrences.addNewComponent(adsk.core.Matrix3D.create())
    occ.component.name = nom
    _boite(occ.component, lx, ly, lz)
    m = adsk.core.Matrix3D.create()
    m.translation = adsk.core.Vector3D.create(x, y, z)
    occ.transform2 = m
    return occ


def _position(occ):
    t = occ.transform2.translation
    return [round(t.x, 4), round(t.y, 4), round(t.z, 4)]


def _fin(sb):
    try:
        return float(sb.end)
    except Exception:
        return -1.0


def _deplacer(occ, dz):
    m = occ.transform2
    t = m.translation
    t.z = t.z + dz
    m.translation = t
    occ.transform2 = m


def lancer() -> str:
    app = adsk.core.Application.get()
    ui = app.userInterface
    rapport = {"version": app.version, "debut": time.strftime("%Y-%m-%d %H:%M:%S")}
    doc_avant = app.activeDocument
    doc = None
    try:
        doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        design = adsk.fusion.Design.cast(app.activeProduct)
        design.designType = adsk.fusion.DesignTypes.ParametricDesignType
        caisse = _composant(design, "Caisse", 0, 0, 0, 60, 40, 30)
        couvercle = _composant(design, "Couvercle", 0, 0, 30, 60, 40, 8)
        tiroir = _composant(design, "Tiroir", 5, -0.5, 5, 50, 38, 12)
        app.activeViewport.fit()
        _attendre(0.5)
        try:
            design.snapshots.add()          # position capturée : la référence du design
        except Exception:
            pass
        rapport["timeline_avant"] = design.timeline.count
        rapport["couvercle_design_avant"] = _position(couvercle)

        # Commandes natives de l'espace Animation (Q4)
        cand = []
        defs = ui.commandDefinitions
        for i in range(defs.count):
            id_ = defs.item(i).id
            b = id_.lower()
            if any(m in b for m in ("explode", "transform", "storyboard", "anim", "showhide", "restorehome")):
                cand.append(id_)
        rapport["Q4_commandes"] = cand[:120]

        gestion = design.animationManager
        gestion.activateAnimationWorkspace()
        _attendre(1.0)
        sb = gestion.storyboards.add(True)
        sb.activate()
        _attendre(0.5)
        rapport["fin_depart"] = _fin(sb)

        # Q1 : enregistrement allumé
        sb.isViewRecordingOn = True
        _attendre(0.3)
        sb.playheadPosition = 2.0
        _attendre(0.3)
        _deplacer(couvercle, 25)
        _attendre(1.0)
        rapport["Q1"] = {"enregistrement_relu": sb.isViewRecordingOn, "fin": _fin(sb),
                         "couvercle": _position(couvercle)}

        # Q2 : enregistrement éteint, tiroir
        sb.isViewRecordingOn = False
        _attendre(0.3)
        sb.playheadPosition = 4.0
        _attendre(0.3)
        m = tiroir.transform2
        t = m.translation
        t.y = t.y - 30
        m.translation = t
        tiroir.transform2 = m
        _attendre(1.0)
        rapport["Q2"] = {"fin": _fin(sb), "tiroir": _position(tiroir)}

        # Lecture : la tête revient à 0, les pièces reviennent-elles ?
        sb.playheadPosition = 0.0
        _attendre(0.8)
        rapport["tete_0"] = {"couvercle": _position(couvercle), "tiroir": _position(tiroir)}
        sb.playheadPosition = 3.0
        _attendre(0.8)
        rapport["tete_3"] = {"couvercle": _position(couvercle), "tiroir": _position(tiroir)}

        # Q5 : éclatement automatique natif, pièces présélectionnées
        q5 = {}
        for id_ in [c for c in cand if "explode" in c.lower()][:4]:
            try:
                ui.activeSelections.clear()
                for o in (caisse, couvercle, tiroir):
                    ui.activeSelections.add(o)
                avant = _fin(sb)
                sb.playheadPosition = 6.0
                _attendre(0.3)
                ok = defs.itemById(id_).execute()
                _attendre(2.0)
                q5[id_] = {"execute": ok, "fin_avant": avant, "fin_apres": _fin(sb),
                           "commande_active": ui.activeCommand}
                try:
                    if ui.activeCommand and ui.activeCommand != "SelectCommand":
                        ui.terminateActiveCommand()
                except Exception:
                    pass
                _attendre(0.5)
            except Exception as e:
                q5[id_] = {"erreur": str(e)}
        rapport["Q5"] = q5

        # Q3 : retour dans le design
        try:
            ws = ui.workspaces.itemById("FusionSolidEnvironment")
            if ws:
                ws.activate()
        except Exception as e:
            rapport["retour_design_erreur"] = str(e)
        _attendre(1.0)
        rapport["Q3"] = {"couvercle_design_apres": _position(couvercle), "timeline_apres": design.timeline.count,
                         "document_modifie": doc.isModified}
    except Exception:
        rapport["erreur"] = traceback.format_exc()
    finally:
        rapport["fin"] = time.strftime("%Y-%m-%d %H:%M:%S")
        RESULTATS.mkdir(exist_ok=True)
        chemin = RESULTATS / f"sonde-pieces-{time.strftime('%Y%m%d-%H%M%S')}.json"
        chemin.write_text(json.dumps(rapport, indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            if doc is not None:
                doc.close(False)
            if doc_avant is not None:
                doc_avant.activate()
        except Exception:
            pass
    return f"FINI, rapport : {chemin}\n" + json.dumps(rapport, ensure_ascii=False)[:3000]


def run(context):
    adsk.core.Application.get().userInterface.messageBox(lancer()[:1500], "Sonde pièces")
