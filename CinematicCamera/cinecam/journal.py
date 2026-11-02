"""Journal fichier (journal.log, rotation 1 Mo × 2). Aucun import adsk."""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

NOM = "CinematicCamera"


def journal(dossier: Path | None = None) -> logging.Logger:
    log = logging.getLogger(NOM)
    if dossier is not None and not log.handlers:
        h = logging.handlers.RotatingFileHandler(
            Path(dossier) / "journal.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(h)
        log.setLevel(logging.INFO)
        log.propagate = False
    return log


def fermer() -> None:
    log = logging.getLogger(NOM)
    for h in list(log.handlers):
        h.close()
        log.removeHandler(h)
