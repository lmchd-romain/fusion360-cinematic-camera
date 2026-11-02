"""Sonde de cadence pour CinematicCamera. Add-in jetable : Exécuter, ne plus toucher souris ni clavier ~25 s.

Historique des lancements :
- L1 (à jouer) : hypothèse « 30 pas/s tenus, pas < 5 ms, caméra sans effet sur le document ».

Scénarios (rapport : ../resultats/sonde-cadence-<horodatage>.json) :
- S1 contexte : build, type de produit, type de caméra, orientation de modélisation (nom), ui.activeCommand au repos.
- S2 inactivité : GetLastInputInfo lisible, valeur en s.
- S3 écriture brute : 60 écritures de caméra d'affilée, durée par écriture, sans puis avec viewport.refresh().
- S4 cadrage : caméra appliquée avec isFitView = True ; œil et cible avant / après.
- S5 cadence 30 Hz puis 60 Hz, 6 s chacune, rotation 6 °/s : intervalles réels entre tics, durée d'un pas.
- S6 document : isModified avant / après tout le reste (indice d'entrée d'annulation).
- Fin : caméra d'origine rendue.
Ne crée rien, ne modifie pas le document.
"""
import json
import math
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

import adsk.core
import adsk.fusion

DOSSIER = Path(__file__).resolve().parent
RESULTATS = DOSSIER.parent / "resultats"
ID_EVT = "lmchdCinematicCameraSonde_tic"

_h = []
_s = {}


def _inactivite():
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class LII(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

    i = LII()
    i.cbSize = ctypes.sizeof(LII)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(i)):
        return None
    ctypes.windll.kernel32.GetTickCount.restype = wintypes.DWORD
    return ((ctypes.windll.kernel32.GetTickCount() - i.dwTime) & 0xFFFFFFFF) / 1000.0


def _stats(v):
    v = sorted(v)
    if not v:
        return {"n": 0}
    n = len(v)
    return {"n": n, "min": round(v[0], 2), "moy": round(sum(v) / n, 2),
            "p95": round(v[min(n - 1, int(0.95 * n))], 2), "max": round(v[-1], 2)}


def _xyz(p):
    return [round(p.x, 4), round(p.y, 4), round(p.z, 4)]


def _orbite(cam0, angle_rad):
    """Œil de cam0 tourné autour de l'axe haut de cam0 passant par la cible."""
    t, e, k = cam0.target, cam0.eye, cam0.upVector
    k.normalize()
    v = (e.x - t.x, e.y - t.y, e.z - t.z)
    kk = (k.x, k.y, k.z)
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    cr = (kk[1] * v[2] - kk[2] * v[1], kk[2] * v[0] - kk[0] * v[2], kk[0] * v[1] - kk[1] * v[0])
    d = sum(a * b for a, b in zip(kk, v))
    r = [v[i] * c + cr[i] * s + kk[i] * d * (1 - c) for i in range(3)]
    return adsk.core.Point3D.create(t.x + r[0], t.y + r[1], t.z + r[2])


def _poser(vue, cam0, angle_rad, refresh=False):
    cam = vue.camera
    cam.eye = _orbite(cam0, angle_rad)
    cam.target = cam0.target
    cam.upVector = cam0.upVector
    cam.isSmoothTransition = False
    vue.camera = cam
    if refresh:
        vue.refresh()


class Fil(threading.Thread):
    def __init__(self, app):
        super().__init__(daemon=True)
        self.app, self.stop, self.attente, self.intervalle = app, threading.Event(), threading.Event(), 0.2

    def run(self):
        while not self.stop.wait(self.intervalle):
            if not self.attente.is_set():
                self.attente.set()
                self.app.fireCustomEvent(ID_EVT, "")


def _scenarios_statiques(app, ui, r):
    vue = app.activeViewport
    produit = app.activeProduct
    try:
        o = app.preferences.generalPreferences.defaultModelingOrientation
        nom_o = next((n for n in dir(adsk.core.DefaultModelingOrientations)
                      if not n.startswith("_") and getattr(adsk.core.DefaultModelingOrientations, n) == o), o)
    except Exception as e:
        nom_o = f"erreur : {e}"
    cam = vue.camera
    r["S1"] = {"version": app.version, "produit": produit.objectType if produit else None,
               "camera_type": cam.cameraType, "perspective_rad": cam.perspectiveAngle,
               "orientation_modelisation": str(nom_o), "activeCommand_repos": ui.activeCommand,
               "vue_px": [vue.width, vue.height], "oeil": _xyz(cam.eye), "cible": _xyz(cam.target),
               "haut": _xyz(cam.upVector)}
    r["S2"] = {"inactivite_s": _inactivite()}
    doc = app.activeDocument
    r["S6"] = {"isModified_avant": doc.isModified if doc else None}
    cam0 = vue.camera
    _s["cam0"] = cam0
    for nom, refresh in (("S3_sans_refresh", False), ("S3_avec_refresh", True)):
        durees = []
        for i in range(60):
            t = time.perf_counter()
            _poser(vue, cam0, math.radians(i), refresh)
            durees.append((time.perf_counter() - t) * 1000)
        r[nom] = _stats(durees)
    # S4 : cadrage
    cam = vue.camera
    avant = {"oeil": _xyz(cam.eye), "cible": _xyz(cam.target)}
    cam.isFitView = True
    cam.isSmoothTransition = False
    t = time.perf_counter()
    vue.camera = cam
    ms = (time.perf_counter() - t) * 1000
    relue = vue.camera
    design = adsk.fusion.Design.cast(produit)
    boite = None
    if design:
        b = design.rootComponent.boundingBox
        boite = {"min": _xyz(b.minPoint), "max": _xyz(b.maxPoint)}
    r["S4"] = {"avant": avant, "apres": {"oeil": _xyz(relue.eye), "cible": _xyz(relue.target)},
               "ms": round(ms, 2), "boite_racine_cm": boite}
    vue.camera = cam0


class Tic(adsk.core.CustomEventHandler):
    def notify(self, args):
        fil = _s.get("fil")
        try:
            app, ui, r = _s["app"], _s["ui"], _s["rapport"]
            phase = _s.get("phase", "statique")
            if phase == "statique":
                _scenarios_statiques(app, ui, r)
                _s.update(phase=30, t0=time.perf_counter(), dernier=None, inter=[], pas=[])
                fil.intervalle = 1 / 30
                return
            vue, cam0 = app.activeViewport, _s["cam0"]
            maintenant = time.perf_counter()
            if _s["dernier"] is not None:
                _s["inter"].append((maintenant - _s["dernier"]) * 1000)
            _s["dernier"] = maintenant
            ecoule = maintenant - _s["t0"]
            _poser(vue, cam0, math.radians(6 * ecoule))
            _s["pas"].append((time.perf_counter() - maintenant) * 1000)
            if ecoule >= 6:
                r[f"S5_{phase}Hz"] = {"intervalle_ms": _stats(_s["inter"]), "pas_ms": _stats(_s["pas"]),
                                      "tics_par_s": round(len(_s["pas"]) / ecoule, 1)}
                if phase == 30:
                    _s.update(phase=60, t0=time.perf_counter(), dernier=None, inter=[], pas=[])
                    fil.intervalle = 1 / 60
                else:
                    _finir()
        except Exception:
            _s["rapport"].setdefault("erreurs", []).append(traceback.format_exc())
            _finir()
        finally:
            if fil:
                fil.attente.clear()


def _finir():
    if _s.get("fini"):
        return
    _s["fini"] = True
    app, r = _s["app"], _s["rapport"]
    fil = _s.get("fil")
    if fil:
        fil.stop.set()
    try:
        if "cam0" in _s:
            app.activeViewport.camera = _s["cam0"]
        doc = app.activeDocument
        r.setdefault("S6", {})["isModified_apres"] = doc.isModified if doc else None
    except Exception:
        r.setdefault("erreurs", []).append(traceback.format_exc())
    RESULTATS.mkdir(parents=True, exist_ok=True)
    f = RESULTATS / f"sonde-cadence-{datetime.now():%Y%m%d-%H%M%S}.json"
    f.write_text(json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")
    _s["ui"].messageBox(f"Sonde terminée. Rapport :\n{f}", "CinematicCameraSonde")


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    _s.clear()
    _s.update(app=app, ui=ui, rapport={"horodatage": datetime.now().isoformat(timespec="seconds")})
    if not app.activeViewport or not adsk.fusion.Design.cast(app.activeProduct):
        ui.messageBox("Ouvrez d'abord un design avec un modèle, puis relancez la sonde.", "CinematicCameraSonde")
        return
    try:
        app.unregisterCustomEvent(ID_EVT)
    except Exception:
        pass
    e = app.registerCustomEvent(ID_EVT)
    h = Tic()
    e.add(h)
    _h.append(h)
    fil = Fil(app)
    _s["fil"] = fil
    fil.start()


def stop(context):
    fil = _s.get("fil")
    if fil:
        fil.stop.set()
    try:
        adsk.core.Application.get().unregisterCustomEvent(ID_EVT)
    except Exception:
        pass
    _h.clear()
