"""Génère les icônes : cube gris en cavalière + flèche d'orbite bleue ; réglages (+ curseurs) et animation
(+ pellicule) en badge en bas à droite. Pillow, rendu suréchantillonné.

Lancer : python ressources/generer_icone.py
Fichiers : 16x16, 16x16@2x, 32x32, 32x32@2x, + copies -dark et -dark_blue (cf. docs/lecons-skill.md).
"""
from pathlib import Path

from PIL import Image, ImageDraw

RESSOURCES = Path(__file__).resolve().parent
SS = 8  # suréchantillonnage


def dessiner(px: int, sombre: bool, badge: str | None = None) -> Image.Image:
    n = px * SS
    u = n / 32.0  # une unité de la grille 32
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    trait = None if sombre else "#666666"
    lw = max(1, int(u))
    # Cube en cavalière, centré
    x0, y0, c, p = 9 * u, 13 * u, 11 * u, 5 * u
    face = [(x0, y0), (x0 + c, y0), (x0 + c, y0 + c), (x0, y0 + c)]
    dessus = [(x0, y0), (x0 + p, y0 - p), (x0 + c + p, y0 - p), (x0 + c, y0)]
    flanc = [(x0 + c, y0), (x0 + c + p, y0 - p), (x0 + c + p, y0 + c - p), (x0 + c, y0 + c)]
    for poly, coul in ((face, "#D9D9D9"), (dessus, "#F3F3F3"), (flanc, "#BBBBBB")):
        d.polygon(poly, fill=coul, outline=trait, width=lw if trait else 0)
    # Orbite : ellipse ouverte autour du cube, avec pointe de flèche
    bleu = "#73C5FF" if sombre else "#178FE6"
    epais = int((2.6 if px <= 16 else 2.0) * u)
    boite = [2 * u, 17 * u, 30 * u, 29 * u]
    d.arc(boite, start=200, end=500, fill=bleu, width=epais)
    # pointe à gauche, orientée vers le haut-gauche (sens de rotation)
    pointe = [(1 * u, 20 * u), (7.5 * u, 19 * u), (3.5 * u, 25 * u)]
    d.polygon(pointe, fill=bleu)
    if badge:
        _badge(d, u, badge, sombre, lw)
    return im.resize((px, px), Image.LANCZOS)


def _badge(d, u, badge, sombre, lw):
    """Pastille en bas à droite, sur fond plein pour rester lisible par-dessus l'orbite."""
    trait = "#D9D9D9" if sombre else "#666666"
    fond = "#3C3C3C" if sombre else "#FFFFFF"
    bleu = "#73C5FF" if sombre else "#178FE6"
    x0, y0, x1, y1 = 17 * u, 17 * u, 31 * u, 31 * u
    d.rounded_rectangle([x0, y0, x1, y1], radius=2 * u, fill=fond, outline=trait, width=lw)
    if badge == "reglages":
        # deux curseurs : rails gris, boutons bleus
        for y, x in ((21.5, 26.5), (26.5, 21.5)):
            d.line([(19.5 * u, y * u), (28.5 * u, y * u)], fill=trait, width=max(1, int(1.6 * u)))
            d.ellipse([(x - 2) * u, (y - 2) * u, (x + 2) * u, (y + 2) * u], fill=bleu)
    elif badge == "animation":
        # pellicule : bande grise perforée, image bleue au centre
        d.rectangle([19 * u, 19.5 * u, 29 * u, 28.5 * u], fill=trait)
        d.rectangle([21.5 * u, 21.5 * u, 26.5 * u, 26.5 * u], fill=bleu)
        for y in (20.3, 27.0):
            for x in (19.6, 27.6):
                d.rectangle([x * u, y * u, (x + 0.9) * u, (y + 0.9) * u], fill=fond)


def main():
    for nom, badge in (("icone", None), ("icone_reglages", "reglages"), ("icone_animation", "animation")):
        generer(RESSOURCES / nom, badge)


def generer(DOSSIER, badge):
    DOSSIER.mkdir(parents=True, exist_ok=True)
    for taille in (16, 32):
        for echelle, suffixe in ((1, ""), (2, "@2x")):
            clair = dessiner(taille * echelle, False, badge)
            sombre = dessiner(taille * echelle, True, badge)
            clair.save(DOSSIER / f"{taille}x{taille}{suffixe}.png")
            # Conventions relevées sur les icônes natives : -dark avant @2x, jetons de thème après.
            sombre.save(DOSSIER / f"{taille}x{taille}-dark{suffixe}.png")
            for jeton in ("-dark_blue", "-dark_gray"):
                sombre.save(DOSSIER / f"{taille}x{taille}{suffixe}{jeton}.png")


if __name__ == "__main__":
    main()
