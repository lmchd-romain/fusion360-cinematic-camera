Bonjour Claude. Joue la sonde « pièces » du plugin **Caméra cinématique** dans Fusion, puis fais-moi un compte rendu en 5 lignes simples. Je suis menuisier, pas codeur : ne m'explique pas le code.

1. Il te faut le MCP de Fusion. Sinon, dis-le en une phrase et arrête-toi.
2. Dossier du dépôt : `C:\Users\PC-ADMIN\Documents\GitHub\fusion360-cinematic-camera` (sinon cherche le dossier qui contient `essai\sonde_pieces\sonde_pieces.py` sous `C:\Users`). Mets-le à jour (`git pull`) si tu peux, sinon demande-moi : « GitHub Desktop → Fetch origin → Pull origin ».
3. Dis-moi : « Je lance la sonde : ~30 s, un document de test s'ouvre puis se ferme sans rien enregistrer. » Puis lance, en un appel au MCP :
```python
import importlib.util, sys
f = r"<DEPOT>\essai\sonde_pieces\sonde_pieces.py"
s = importlib.util.spec_from_file_location("sonde_pieces", f)
S = importlib.util.module_from_spec(s); sys.modules["sonde_pieces"] = S; s.loader.exec_module(S)
print(S.lancer())
```
4. Compte rendu : Q1 (pièce déplacée, enregistrement allumé : la fin du storyboard a-t-elle avancé ?), Q2 (idem éteint), Q3 (le couvercle est-il revenu à sa place dans l'espace Conception, timeline et document inchangés ?), Q4 (identifiants des commandes « explode » et « transform »), Q5 (éclatement automatique : une action est-elle apparue ?). Dernière ligne : « Je pousse le rapport sur GitHub ? »
5. Si je dis oui : `git add essai/resultats/sonde-pieces-*.json`, commit « Sonde pièces », push sur `main` (sinon guide-moi dans GitHub Desktop).
