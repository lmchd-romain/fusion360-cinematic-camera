"""Lecture et écriture de reglages.json, à côté de l'add-in. Aucun import adsk."""
from __future__ import annotations

import json
from pathlib import Path

from .noyau import Reglages


def lire(chemin: Path) -> Reglages:
    try:
        return Reglages.depuis_dict(json.loads(Path(chemin).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return Reglages()


def ecrire(chemin: Path, r: Reglages) -> None:
    Path(chemin).write_text(json.dumps(r.vers_dict(), indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
