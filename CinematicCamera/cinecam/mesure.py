"""Statistiques de cadence (intervalle entre tics, durée d'un pas). Aucun import adsk."""
from __future__ import annotations


class Mesure:
    def __init__(self):
        self.valeurs: list[float] = []

    def ajoute(self, v: float) -> None:
        self.valeurs.append(v)

    def resume(self) -> dict:
        v = sorted(self.valeurs)
        if not v:
            return {"n": 0}
        n = len(v)
        return {
            "n": n,
            "min": round(v[0], 2),
            "moy": round(sum(v) / n, 2),
            "p95": round(v[min(n - 1, int(0.95 * n))], 2),
            "max": round(v[-1], 2),
        }
