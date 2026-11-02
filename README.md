# CinematicCamera — preuve de concept

La vue de Fusion tourne lentement autour du modèle quand personne ne touche ni souris ni clavier.
Dès que l'utilisateur bouge, la rotation s'arrête net. Comportement calé sur le viewer 3D de MobPrez.

*EN — Proof of concept: the Fusion view slowly orbits the model when the user is away (no mouse or
keyboard input). Any input stops it at once. Behaviour matches the MobPrez 3D viewer.*

Statut : **non essayé dans Fusion**. Tests hors Fusion verts (Python 3.13 et 3.14). Voir `ETAT.md`.

## Installer

1. Fusion → Utilitaires → **Scripts et compléments** → onglet **Compléments** → **+** → choisir le dossier
   `CinematicCamera` (dans ton clone de `fusion360-test-proof-of-concept`) → **Exécuter**.
2. Un bouton **Caméra auto** apparaît dans Utilitaires → Compléments [supposé : emplacement].

## Vérifier dans Fusion : recette automatique

1. Ouvrir Fusion, lancer l'add-in CinematicCamera (Arrêter / Exécuter s'il tournait déjà).
2. Coller le contenu de `essai/recette/MESSAGE.md` dans Claude Desktop (qui a le MCP de Fusion), puis ne
   plus toucher ni souris ni clavier ~3 minutes : un document de test s'ouvre, la vue tourne, s'arrête,
   le document se ferme sans rien enregistrer.
3. Lire le compte rendu de Claude (5 lignes), faire les 3 gestes « à la main » qu'il liste, et lui dire
   s'il peut pousser les résultats.

Sans Claude Desktop : Utilitaires → Scripts et compléments → Scripts → « + » → dossier
`CinematicCamera/essai/recette` → Exécuter ; le rapport s'écrit dans `essai/resultats/recette-….md`.

Liste des vérifications et de leur mode (auto, capture, à la main) : `ETAT.md`. La sonde de cadence
`essai/CinematicCameraSonde` reste disponible pour creuser.

## Réglages (`reglages.json`)

| Clé | Défaut | Rôle |
|---|---|---|
| `actif` | `true` | Marche / arrêt (le bouton l'écrit) |
| `delai_s` | `60` | Secondes sans saisie avant de tourner (5–3600) |
| `vitesse_deg_s` | `2.4` | Vitesse : un tour en 150 s (MobPrez, choix de Romain) |
| `inclinaison_deg` | `35` | Hauteur de la caméra au-dessus de l'horizon (MobPrez) |
| `recadrage_s` | `6` | Durée du départ en douceur : montée de la vitesse et voyage vers le cadrage ; `0` = saut |
| `cadence_hz` | `30` | Pas de caméra par seconde |
| `sens` | `1` | `1` ou `-1` |
| `axe` | `"auto"` | Axe vertical : `"auto"` (préférence Fusion Y ou Z en haut), `"y"`, `"z"` |
| `cadrer` | `true` | Recentrer et cadrer le modèle au départ |
| `restaurer_vue` | `false` | `false` = arrêt net (MobPrez) ; `true` = retour en douceur à la vue d'avant |

Changer un réglage à la main : Arrêter / Exécuter l'add-in.

**Délai : 60 s (mon choix), contre 5 s dans MobPrez.** MobPrez est un outil de présentation : la vue doit
s'animer vite devant un client. Fusion est un outil de travail : on lit un plan, on réfléchit sans toucher
la souris ; 5 s ferait tourner la vue sous les yeux en plein travail. Réglable.

## Comment ça marche

- Un fil de fond tire un événement personnalisé (2 fois/s en veille, 30 fois/s en rotation), jamais deux en
  file. Fusion le traite sur son fil principal.
- Inactivité lue par `GetLastInputInfo` de Windows : globale à la session (toutes applications).
- Départ en douceur : la rotation part de l'arrêt et accélère progressivement (courbe en S) pendant
  `recadrage_s`, pendant que cible, distance et hauteur glissent (accélération puis freinage) vers le
  cadrage : centre de la boîte du composant racine, `inclinaison_deg` au-dessus de l'horizon, azimut
  gardé, distance calculée pour que la sphère qui englobe le modèle tienne dans l'angle de vue. Aucun
  cadrage d'essai par Fusion (`isFitView`) : il faisait sauter la vue. Rotation autour de l'axe vertical ;
  angle calculé sur le temps écoulé, donc vitesse régulière même si des pas sautent. La vue est redessinée
  à chaque pas (`viewport.refresh()`).
- Reprise : la moindre saisie (souris, clavier) arrête la rotation au tic suivant (≤ 1/30 s).
- Jamais de modification du document : seule la caméra de la vue change.

## Limites connues

- Windows seulement (hors Windows : jamais de rotation).
- Souris 3D (SpaceMouse) probablement non comptée comme saisie [supposé].
- Références MobPrez (`app-mobprez` @ cd5ccb4, `viewer/src/scene.js`), relevées par la session chef de
  projet : `autoRotateSpeed = 0.4` (≈ 2,4 °/s), `RECENTER_MS = 6000`, `RECENTER_ELEVATION_DEG = 35`,
  `autoRotateAfterMs = 5000`.

## Dépannage

`demarrage.log` (panne au chargement) et `journal.log` (démarrage, chaque rotation avec cadence mesurée,
erreurs) dans `CinematicCamera/`.

## Développement

```
python -m pytest        # depuis CinematicCamera
python ressources/generer_icone.py
```

`cinecam/noyau.py` : trajectoire, réglages, machine d'états (pur, testé). `cinecam/inactivite.py` : Windows.
`cinecam/fusion_camera.py` : seule couche qui touche la caméra. `cinecam/addin.py` : bouton, fil, événement.
