# Caméra cinématique (CinematicCamera)

Add-in Fusion : la vue tourne lentement autour du modèle, en douceur, comme une caméra de présentation.

- **Bouton « Caméra cinématique »** : la rotation part tout de suite. La souris peut bouger ; un clic, une
  touche du clavier ou un nouveau clic sur le bouton l'arrête.
- **Rotation quand je m'absente** : après un temps sans souris ni clavier, la vue se met à tourner seule ;
  la moindre saisie l'arrête.
- **Réglages** : durée d'un tour (vitesse), temps avant activation, rotation quand je m'absente.
- **Espace Animation → « Créer l'animation de rotation »** : crée un storyboard d'un tour complet du
  modèle, cadré, à la vitesse des réglages ; la fin rejoint le début, la vidéo boucle sans à-coup.

*EN — Fusion add-in: smooth, slow orbit of the model. On demand (button), automatically when the user is
away, or recorded as an Animation storyboard (one seamless loop).*

Statut : rotation au bouton et en absence essayées dans Fusion (préversion CameraAuto, 2026-11-02) ;
réglages, lancement au bouton et animation **pas encore essayés**. Voir `docs/ETAT.md`.

## Installer

1. Si l'ancienne préversion **CameraAuto** (dépôt `fusion360-test-proof-of-concept`) est installée :
   Utilitaires → Scripts et compléments → Compléments → CameraAuto → **Arrêter**, décocher « Exécuter au
   démarrage », puis la retirer de la liste (bouton « – » ou clic droit).
2. Utilitaires → **Scripts et compléments** → onglet **Compléments** → **+** → choisir le dossier
   `CinematicCamera` (dans le clone de `fusion360-cinematic-camera`) → **Exécuter**, cocher **Exécuter au
   démarrage**.
3. Boutons : **Utilitaires → Compléments** (Caméra cinématique, Réglages) et, dans l'espace **Animation**,
   un panneau **CAMÉRA CINÉMATIQUE** (Créer l'animation de rotation, Réglages).

## Vérifier dans Fusion : recette automatique

1. Ouvrir Fusion, lancer l'add-in CinematicCamera (Arrêter / Exécuter s'il tournait déjà).
2. Coller le contenu de `essai/recette/MESSAGE.md` dans Claude Desktop (qui a le MCP de Fusion), puis ne
   plus toucher ni souris ni clavier ~3 minutes.
3. Lire le compte rendu de Claude, faire les gestes « à la main » qu'il liste.

Sans Claude Desktop : Utilitaires → Scripts et compléments → Scripts → « + » → dossier `essai/recette` →
Exécuter ; le rapport s'écrit dans `essai/resultats/recette-….md`. Vérifications : `docs/ETAT.md`.

## Réglages (`reglages.json`)

| Clé | Défaut | Rôle |
|---|---|---|
| `actif` | `true` | Rotation quand je m'absente (dialogue Réglages) |
| `delai_s` | `60` | Temps avant activation, en secondes (5–3600, dialogue Réglages) |
| `vitesse_deg_s` | `2.4` | Vitesse : un tour en 150 s ; le dialogue Réglages la règle en durée d'un tour (10–600 s) |
| `inclinaison_deg` | `35` | Hauteur de la caméra au-dessus de l'horizon (MobPrez) |
| `recadrage_s` | `6` | Durée du départ en douceur : montée de la vitesse et voyage vers le cadrage ; `0` = saut |
| `cadence_hz` | `30` | Pas de caméra par seconde |
| `sens` | `1` | `1` ou `-1` |
| `axe` | `"auto"` | Axe vertical : `"auto"` (préférence Fusion Y ou Z en haut), `"y"`, `"z"` |
| `cadrer` | `true` | Recentrer et cadrer le modèle au départ |
| `restaurer_vue` | `false` | `false` = arrêt net (MobPrez) ; `true` = retour en douceur à la vue d'avant |

Le dialogue Réglages s'applique tout de suite. Les autres clés : modifier le fichier, puis Arrêter / Exécuter l'add-in.

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
- Reprise, rotation en absence : la moindre saisie (souris, clavier) arrête la rotation au tic suivant.
- Rotation au bouton : un bouton de souris ou une touche enfoncé (lu par `GetAsyncKeyState`) l'arrête ;
  le mouvement seul de la souris non. Les 0,4 s qui suivent le clic sont ignorées (relâcher le bouton).
- Vue bougée par autre chose (souris 3D, vue nommée, ViewCube) : la rotation rend la main aussitôt, et
  ne repart seule qu'après un nouveau temps d'attente complet.
- Animation : nouveau storyboard propre, enregistrement des vues allumé, une vue tous les 5° posée à son
  instant (72 vues pour un tour), puis enregistrement éteint. API Animation de Fusion en **preview**
  (depuis mai 2026) : Autodesk peut la changer.
- Jamais de modification du document : seule la caméra de la vue change.

## Limites connues

- Windows seulement (hors Windows : jamais de rotation).
- Souris 3D (SpaceMouse) probablement non comptée comme saisie [supposé].
- Références MobPrez (`app-mobprez` @ cd5ccb4, `viewer/src/scene.js`), relevées par la session chef de
  projet : `autoRotateSpeed = 0.4` (≈ 2,4 °/s), `RECENTER_MS = 6000`, `RECENTER_ELEVATION_DEG = 35`,
  `autoRotateAfterMs = 5000`.

## Dépannage

`demarrage.log` (panne au chargement) et `journal.log` (démarrage, chaque rotation avec cadence mesurée,
animation créée, erreurs) dans le dossier `CinematicCamera/`.

## Développement

```
python -m pytest        # à la racine du dépôt
python CinematicCamera/ressources/generer_icone.py
```

`cinecam/noyau.py` : trajectoire, réglages, machine d'états (pur, testé). `cinecam/inactivite.py` : Windows.
`cinecam/fusion_camera.py` : seule couche qui touche la caméra. `cinecam/addin.py` : boutons, dialogue, fil, événement. `cinecam/animation.py` : storyboard.
