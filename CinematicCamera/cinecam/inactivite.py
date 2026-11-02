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
