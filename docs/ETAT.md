# État — Caméra cinématique (CinematicCamera)

Mis à jour le 2026-11-02 (0.3.0 : mouvements d'animation, dialogue avant création, onglet ANIMATION).

## Historique

- Préversion **CameraAuto** dans `fusion360-test-proof-of-concept` (jusqu'à 0.1.1).
- 0.1.1 : premier essai de Romain, « ça fait juste une téléportation ». Corrigé (cadrage calculé au lieu de
  `isFitView`, `viewport.refresh()` à chaque pas, vitesse qui monte en douceur). **Romain : « ça fonctionne
  nickel » [vérifié, 2026-11-02, rotation en absence].**
- 0.2.0 : dépôt `fusion360-cinematic-camera`, nouveaux identifiants (GUID, commandes `lmchdCinematicCamera_*`).
- 0.2.0, essai de Romain [vérifié] : « Créer l'animation » → timeline vide, « View is not recording » en rouge
  à l'écran, la vue fait le tour en accéléré en 1 s. Tout se faisait d'un bloc dans la commande.
- 0.2.1 : création pas à pas par l'événement de tic, hors de la commande, Fusion reprenant la main entre
  chaque geste (enregistrement allumé et relu, tête de lecture, caméra). Contrôle après 3 vues : si la fin
  du storyboard n'avance pas, deuxième méthode avec transition douce de Fusion (≈ 1 min) ; sinon abandon
  avec message et diagnostic dans `journal.log` (états relus, commandes d'enregistrement de Fusion).
- 0.2.1, essai de Romain [vérifié] : l'animation fonctionne. Le panneau tombait dans l'onglet OUTILS.
- 0.3.0 : dialogue avant création (mouvement, durée, zoom), 8 mouvements (`cinecam/mouvements.py`),
  panneau dans l'onglet ANIMATION, dialogue Réglages réduit aux champs (sans texte, sans curseur).

## 0.3.0 — à vérifier dans Fusion [supposé]

| Code | Geste | Attendu |
|---|---|---|
| W1 | Espace Animation | panneau CAMÉRA CINÉMATIQUE dans l'onglet ANIMATION, plus dans OUTILS |
| W2 | Réglages | trois champs seulement, durée d'un tour en valeur (pas de curseur), pas de texte |
| W3 | Créer une animation caméra | dialogue : Mouvement, Durée (s), Zoom (%) ; changer de mouvement remet sa durée par défaut |
| W4 | Chaque mouvement, durée par défaut, zoom 100 % | storyboard créé, lecture fluide, modèle cadré |
| W5 | Edit supercar | six plans, coupes franches (pas de glissé de 0,04 s visible) |
| W6 | Zoom 200 % puis 50 % | deux fois plus près, puis plus loin |
| W7 | Platine, spirale, balancier en lecture en boucle | aucun à-coup au raccord |

## 0.2.0 — nouveautés à vérifier dans Fusion [supposé]

| Code | Geste | Attendu |
|---|---|---|
| V1 | Utilitaires → Compléments | boutons « Caméra cinématique » (promu) et « Réglages de la caméra cinématique », icônes nettes en clair et sombre |
| V2 | Clic sur « Caméra cinématique » | la vue part en douceur tout de suite ; bouger la souris sans cliquer ne l'arrête pas ; le nom du bouton devient « Arrêter la caméra cinématique » |
| V3 | Pendant V2 : un clic dans la vue, ou une touche | arrêt net |
| V4 | Pendant V2 : molette (zoom) ou ViewCube | arrêt, la vue reste où l'utilisateur l'a mise |
| V5 | Réglages : décocher « Rotation quand je m'absente », OK, attendre plus que le délai | rien ne tourne ; le bouton marche toujours |
| V6 | Réglages : durée d'un tour 30 s, temps 10 s, OK, attendre 10 s | rotation seule, un tour en 30 s |
| V7 | Espace Animation | panneau « CAMÉRA CINÉMATIQUE » : « Créer l'animation de rotation » et « Réglages » |
| V8 | Clic sur « Créer l'animation de rotation » | nouveau storyboard, message « un tour complet en N s » ; Lecture : un tour régulier, sans pause à chaque vue, la fin rejoint le début |
| V9 | `journal.log` après V8 | ligne « animation créée » ; « fin du storyboard » ≈ durée annoncée |

Questions ouvertes de l'animation : Fusion crée-t-il bien une action de vue par vue enregistrée (playhead
déplacé, enregistrement allumé) ? Les actions de vue ont-elles un ralenti en entrée et sortie (la rotation
« pulserait » tous les 5°) ? Replis : vues plus espacées, ou export d'images par `saveAsImageFile` pour une
vidéo hors Fusion.

## Fait

- Add-in complet : bouton lancer / arrêter, dialogue de réglages, création d'animation, fil de surveillance + événement personnalisé, rotation avec
  voyage souple de 6 s vers le cadrage, arrêt net à la moindre saisie (retour à la vue d'avant en option),
  réglages JSON, journaux.
- Calé sur le viewer MobPrez (relevé par la session chef de projet, `app-mobprez` @ cd5ccb4) : 2,4 °/s,
  élévation 35°, recadrage souple 6 s pendant la rotation, arrêt immédiat. Seul écart : délai 60 s au lieu
  de 5 s (mon choix, expliqué dans le README).
- Noyau pur testé : 32 tests (trajectoire, voyage souple, inclinaison, vue de dessus, caméra orthographique,
  cadence indépendante, réglages bornés, machine d'états, rebouclage de `GetTickCount`).
- Test de chargement avec faux `adsk` : `run()` / `stop()` posent et retirent bouton, événement, fil ; un
  seul tir en file ; `run()` relancé sans `stop()` repart propre (bug trouvé et corrigé ainsi).
- Vérifié avec Python 3.13 et 3.14 (celui de Fusion) : compilation + 40 tests verts (dont le chargement de
  l'add-in et de la recette avec un faux `adsk`).
- Recette automatique `essai/recette` : Claude Desktop la joue par le MCP de Fusion
  (`essai/recette/MESSAGE.md`).
- Sonde de cadence `essai/CinematicCameraSonde` (S1–S6).
- Icône 16/32 px, clair et sombre (`-dark`, `-dark_blue`, `-dark_gray`).

## Rien n'a tourné dans Fusion

Toute affirmation ci-dessous est **[supposé]** jusqu'au premier passage de la recette automatique.
Colonne **Vérif.** : point de la recette qui tranche, et son mode.

| Question | Hypothèse | Repli si faux | Vérif. |
|---|---|---|---|
| Écrire `viewport.camera` 30 fois/s est fluide | pas < 5 ms | baisser `cadence_hz` à 15 | S3, P5 auto |
| Les tics arrivent à la cadence demandée | 30 Hz tenus | cadence plus basse ; l'angle suit le temps de toute façon | P5 auto |
| `isFitView = True` cadre le modèle | oui | `viewport.fit()` puis relire la caméra | S4, P2, P3 auto ; K1, K2 capture |
| Cadrage d'essai puis retour à la vue de départ dans le même tic : aucune image intermédiaire | oui | calculer la distance soi-même (boîte + angle de vue) | P1 auto (pas de saut entre deux pas) ; M1 à la main (l'œil voit le départ) |
| Changer la caméra ne marque pas le document modifié ni n'ajoute d'annulation | oui | aucun connu : arrêt du projet | P6, R4 auto |
| `ui.activeCommand` vaut `SelectCommand` au repos | oui | lire la valeur et l'adopter | S1 auto |
| Préférence d'orientation lisible | `defaultModelingOrientation` | axe le plus proche du haut de la vue | S1b auto |
| Inactivité lisible (`GetLastInputInfo`) | oui | jamais de rotation | S2 auto |
| Bouton visible dans Utilitaires → Compléments | `SolidScriptsAddinsPanel` | `SolidInspectPanel` (déjà en repli) | A1 auto |
| Restaurer la caméra avec `isSmoothTransition = True` (option `restaurer_vue`) | oui | sans transition | P8 auto ; K3 capture |
| Pas de rotation pendant une commande | oui | — | R3 auto |
| Un mouvement de souris simulé (`SendInput`, 2 px aller-retour) compte comme une saisie | [supposé] | M1 à la main seulement | R2 auto |

## Recette automatique (`essai/recette`)

Romain colle `essai/recette/MESSAGE.md` dans Claude Desktop (PC Windows, Fusion ouvert, MCP de Fusion) et ne
touche plus ni souris ni clavier ~3 minutes. Claude lance `recette.py`, suit son avancement, juge les
captures, puis rend un compte rendu. Tout se joue dans un document neuf (un caisson et un mur), jamais
enregistré, fermé sans enregistrer. Rapport : `essai/resultats/recette-<horodatage>.json` et `.md`, images
dans `essai/resultats/captures-<horodatage>/`.

Trois parties : la sonde (S*) ; le moteur de l'add-in (`PiloteCamera` + trajectoire du noyau) joué à
30 pas/s sur une vraie vue (P*) ; l'add-in en marche (R*), délai ramené à 3 s le temps de l'essai puis
remis.

| Code | Vérification | Mode | Attendu |
|---|---|---|---|
| A1 | Add-in chargé | auto | bouton « Caméra auto » posé |
| A2 | Réglages de l'add-in en marche | auto | actif, 2,4 °/s (un tour en 150 s) |
| S1 | Commande au repos | auto | `SelectCommand` |
| S1b | Orientation de modélisation | auto | lue dans les préférences |
| S2 | Inactivité Windows | auto | nombre de secondes |
| S3 | Écriture de la caméra | auto | p95 < 5 ms |
| S4 | `isFitView` | auto | les 8 coins du modèle dans la vue |
| P1 | Départ sans saut | auto | aucun pas > 8 % de la distance |
| P2 | Cadrage d'arrivée | auto | cible au centre (≤ 2 % de la diagonale), 35° ± 1° |
| P3 | Modèle entier pendant le tour | auto | 8 coins dans la vue, 4 instants |
| P4 | Vitesse mesurée | auto | 2,4 °/s ± 5 % |
| P5 | Cadence | auto | ≥ 25 pas/s, pas p95 < 5 ms |
| P6 | Document intact, murs gardés | auto | timeline et visibilité des corps inchangées |
| P7 | Arrêt net | auto | vue immobile après l'arrêt |
| P8 | Vue rendue (option) | auto | retour à la vue d'avant |
| R1 | Départ réel sur inactivité | auto | rotation après 3 s sans saisie |
| R2 | Arrêt réel sur la souris | auto | arrêt < 1 s après un mouvement simulé |
| R3 | Pas de rotation pendant une commande | auto | vue immobile |
| R4 | Ctrl+Z après le tour | auto | l'annulation défait le modèle, pas la vue |
| K0 | Vue de départ | capture | caisson et mur, de biais |
| K1 | Pendant le tour | capture | centré, entier, trois-quarts d'en haut, mur visible |
| K2 | Un quart de tour plus loin | capture | même cadrage, autre côté |
| K3 | Vue rendue | capture | identique à K0 |
| M1 | Vraie souris pendant un vrai tour | à la main | départ sans saut, arrêt net |
| M2 | Bouton marche / arrêt | à la main | « ARRÊT » puis « MARCHE » |
| M3 | Icône claire et sombre | à la main | nette dans les deux thèmes |

Compte : **19 auto, 4 capture, 3 à la main.** Les anciens gestes G1–G8 du README sont couverts : G1 → A1 ;
G2 inutile (la recette règle le délai) ; G3 → P1–P5, K1, K2, M1 ; G4 → R2, P7, M1 ; G5 → P6, R4 ; G6 → R3 ;
G7 → M2 ; G8 (sonde) → S1–S4, P5.

## Décisions de Romain (2026-11-02)

- **Vitesse** : celle du viewer MobPrez, choisie par Romain : **2,4 °/s** (un tour en 150 s), recadrage
  doux 6 s, élévation 35°. (Le « tour en 30 s » de Q47 porte sur la durée de la **boucle vidéo** du site,
  pas sur la caméra : la vidéo de 30 s filme environ 72° de rotation, à vitesse réelle. Un passage
  provisoire à 12 °/s a été annulé le jour même.)
- **Murs gardés pendant le tour** (vidéo du site et plugin) : pas un réglage. CinematicCamera ne touche qu'à la caméra : rien n'est
  masqué ni affiché, les murs restent donc visibles. Aucun changement de code ; vérifié par la recette
  (P6 auto : visibilité de chaque corps, dont un mur, inchangée ; K1, K2 capture).

## Non fait / ouvert

- Code rangé dans `fusion360-test-proof-of-concept/CinematicCamera/`, copié depuis le dépôt écosystème le
  2 novembre 2026 (dernier commit d'origine 905ec7a).
- Pas de dialogue de réglages (le fichier JSON suffit pour la preuve de concept).
- La vitesse de rotation monte en douceur de zéro pendant `recadrage_s` (0.1.1).
