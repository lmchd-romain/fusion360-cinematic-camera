"""Inactivité de l'utilisateur, via GetLastInputInfo de Windows (ctypes). Aucun import adsk.

Mesure globale à la session Windows : clavier et souris, toutes applications confondues [supposé :
une souris 3D SpaceMouse n'est pas comptée].
"""
from __future__ import annotations

import sys


def _lecteur_windows():
    import ctypes
    from ctypes import wintypes

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    kernel32.GetTickCount.restype = wintypes.DWORD
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(LASTINPUTINFO)

    def lire():
        if not user32.GetLastInputInfo(ctypes.byref(info)):
            return None
        return ecart_ms(kernel32.GetTickCount(), info.dwTime) / 1000.0

    return lire


def ecart_ms(maintenant: int, derniere: int) -> int:
    """Écart entre deux compteurs 32 bits de GetTickCount, qui reboucle tous les 49,7 jours."""
    return (maintenant - derniere) & 0xFFFFFFFF


def creer_lecteur():
    """Rend une fonction sans argument → secondes d'inactivité, ou None si inconnue (hors Windows)."""
    if sys.platform != "win32":
        return lambda: None
    try:
        return _lecteur_windows()
    except Exception:
        return lambda: None


# Touches lues pour l'arrêt d'une rotation manuelle : boutons de souris (1, 2, 4, 5, 6) et clavier (8–254).
# Le mouvement seul de la souris n'est pas un appui.
TOUCHES = (1, 2, 4, 5, 6) + tuple(range(8, 255))


def _lecteur_appuis_windows():
    import ctypes

    user32 = ctypes.windll.user32
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.GetAsyncKeyState.restype = ctypes.c_short

    def lire():
        return any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in TOUCHES)

    return lire


def creer_lecteur_appuis():
    """Rend une fonction sans argument → vrai si un bouton de souris ou une touche est enfoncé."""
    if sys.platform != "win32":
        return lambda: False
    try:
        return _lecteur_appuis_windows()
    except Exception:
        return lambda: False
