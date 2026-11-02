"""Point d'entrée de l'add-in CinematicCamera (preuve de concept)."""
import sys
import traceback
from pathlib import Path

_DOSSIER = Path(__file__).resolve().parent
if str(_DOSSIER) not in sys.path:
    sys.path.insert(0, str(_DOSSIER))
for _nom in [n for n in sys.modules if n == "cinecam" or n.startswith("cinecam.")]:
    del sys.modules[_nom]


def _trace(etape):
    with open(_DOSSIER / "demarrage.log", "a", encoding="utf-8") as f:
        f.write(f"--- {etape}\n{traceback.format_exc()}\n")


try:
    from cinecam import addin
except Exception:
    _trace("import")
    raise


def run(context):
    try:
        addin.run(context)
    except Exception:
        _trace("run")
        raise


def stop(context):
    try:
        addin.stop(context)
    except Exception:
        _trace("stop")
        raise
