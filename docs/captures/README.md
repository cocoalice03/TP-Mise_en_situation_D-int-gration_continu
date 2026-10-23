# Captures d'écran de la simulation de panne

Placez ici les captures prises en suivant `docs/simulation-panne.md`, avec ces noms de fichiers :

| Fichier | Contenu |
|---|---|
| `01-ci-verte-avant.png` | CI de `main` verte avant la panne |
| `02-diff-bug.png` | La cause : `>` devient `>=` (ligne 47 de `src/processing/aggregations.py`) |
| `03-pr-checks-rouge.png` | La pull request avec les vérifications en échec |
| `04-graphe-workflow-echec.png` | Jobs de tests en échec, intégration ignorée, Statut CI FAILED |
| `05-log-erreur-pytest.png` | Le message d'erreur dans le log de Pytest |
| `06-cd-non-declenche.png` | Aucun déploiement pour la branche de démonstration |
| `07-diff-correction.png` | La correction : `>=` redevient `>` |
| `08-pr-checks-vert.png` | La pull request avec toutes les vérifications vertes |
| `09-graphe-workflow-succes.png` | Les trois jobs en succès, Statut CI SUCCESS |
| `10-cd-deploiement.png` | Le CD réussi après la fusion (optionnel) |

Vérifiez avant de les commiter qu'aucune capture ne montre un mot de passe, un secret ou une adresse que vous ne voulez pas publier (le log du CD masque les secrets, mais pas l'adresse de la VM).
