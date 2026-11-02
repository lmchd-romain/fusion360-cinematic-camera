Bonjour Claude. Joue la recette automatique du plugin **CinematicCamera** dans Fusion, puis fais-moi un compte rendu. Je suis menuisier, pas codeur : parle simple, ne m'explique pas le code. **Pendant la recette, ne me pose aucune question** : si je touche la souris ou le clavier, la rotation s'arrête et les mesures sont faussées.

**1. Prérequis (vérifie toi-même, avant de lancer)**
- Tu as le MCP de Fusion (il exécute du Python dans Fusion ouvert). Sinon, dis-le-moi en une phrase et arrête-toi.
- Dossier du dépôt sur mon PC : `C:\Users\PC-ADMIN\Documents\GitHub\fusion360-cinematic-camera`. S'il n'existe pas, cherche-le avec Python dans Fusion (le dossier qui contient `essai\recette\recette.py`, sous `C:\Users`) et utilise ce chemin partout à la place de `<DEPOT>`.
- Dépôt à jour : si tu as un outil pour lancer git, fais `git pull` dans `<DEPOT>` ; sinon demande-moi : « Ouvre GitHub Desktop → Fetch origin → Pull origin ».
- Add-in lancé : en Python, `adsk.core.Application.get().userInterface.commandDefinitions.itemById("lmchdCinematicCamera_lancer")` ne doit pas être `None`. Sinon, ou si tu viens de mettre le dépôt à jour, demande-moi : « Utilitaires → Scripts et compléments → Compléments → CinematicCamera → Arrêter puis Exécuter ».
- Dis-moi : « Je lance la recette : lâche la souris et le clavier pendant 3 minutes, ne m'écris rien. Un document de test va s'ouvrir, la vue va tourner puis s'arrêter, et il se fermera sans rien enregistrer ; tes documents ne sont pas touchés. » Puis lance aussitôt.

**2. Lancement (un appel au MCP)**
```python
import importlib.util, sys
D = r"<DEPOT>\essai\recette"
s = importlib.util.spec_from_file_location("recette_camera", D + r"\recette.py")
R = importlib.util.module_from_spec(s); sys.modules["recette_camera"] = R; s.loader.exec_module(R)
print(R.lancer())
```
Si le MCP exige une fonction `run(context)`, mets ces lignes dedans. Ensuite, toutes les 10 secondes environ :
```python
import sys; R = sys.modules["recette_camera"]; print(R.etat())
```
- `EN COURS` : attends, puis redemande.
- `PAUSE capture K0` (puis `K1`, `K2`, `K3`) : la vue est figée. Prends la capture de la vue avec le MCP (ou ouvre l'image dont le chemin est donné, si tu peux lire les fichiers). Juge toi-même ce que demande la question : `R.juger("K1", "OK", "ce que tu vois")` (ou `"KO"`, ou `"À REGARDER"` si tu doutes), puis `print(R.continuer())`. Pour K3, compare avec ta capture de K0. La pause se lève seule après 4 minutes.
- `FINI` : `print(R.rapport())`, puis passe au compte rendu.
- Si l'état reste sur le bloc « contexte » plus de 30 secondes (Fusion ne rend pas la main au moteur) : `R.arreter()`, puis `print(R.lancer(synchrone=True))` (bloque Fusion ~2 minutes ; les points R* passeront en « À REGARDER »).
- Erreur Python ou Fusion bloqué : `print(R.arreter())` (ferme le document de test, remet le délai de l'add-in, écrit le rapport), puis dis-moi l'erreur en une phrase.

**3. Compte rendu : 5 lignes au plus, en mots simples**
1. Bilan : nombre de OK, KO, À REGARDER, sur combien de points ; vitesse mesurée (un tour en combien de secondes).
2. Ce qui ne marche pas (KO) : une ligne par point, code et ce qui cloche, sans jargon.
3. Ce qui reste douteux (À REGARDER) : idem, avec ce que tu proposes (par exemple supprimer `<DEPOT>\CinematicCamera\reglages.json` si A2 signale une vitesse différente de 2,4).
4. À faire à la main : les gestes de la section « À la main (Romain) » du rapport, un par ligne, avec le résultat attendu.
5. « Je pousse les résultats sur GitHub ? »

**4. Pousser les résultats (seulement si je réponds oui)**
Fichiers : `<DEPOT>\essai\resultats\recette-<horodatage>.json`, `recette-<horodatage>.md` et le dossier `captures-<horodatage>\`.
- Si tu as git : `git add` ces fichiers seulement, `git commit -m "Recette CinematicCamera <horodatage>"`, `git pull --rebase`, `git push` sur `main`.
- Sinon, dis-moi : « Ouvre GitHub Desktop, coche seulement ces fichiers, résumé "Recette CinematicCamera", Commit to main, puis Push origin. »
