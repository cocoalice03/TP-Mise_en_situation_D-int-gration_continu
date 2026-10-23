# Simulation d'une panne de pipeline

Ce guide rejoue une panne volontaire pour montrer que la CI détecte une erreur (spec §13, sujet « Simulation d'un échec de pipeline »). Il couvre les cinq points demandés : la cause, l'échec de la pipeline, le message d'erreur, la correction et le succès après correction.

## Le scénario : un bug silencieux dans le traitement

**La cause.** Dans `src/processing/aggregations.py`, ligne 47, la fonction `flag_high_value_transactions` marque une transaction « à risque » si son montant dépasse **strictement** 5000 :

```python
new_row["is_high_value"] = new_row["montant"] > threshold      # code correct
new_row["is_high_value"] = new_row["montant"] >= threshold     # bug introduit
```

Avec le bug, une transaction d'exactement `5000.00` est signalée à tort. C'est une modification d'un seul caractère. Le programme continue de tourner sans aucune erreur et affiche des chiffres plausibles : **seuls les tests peuvent détecter ce bug**, ce qui montre l'utilité de la CI.

**Pourquoi le code cassé n'atteint pas la VM.** On joue la panne sur une branche et une pull request. Le CD ne se déclenche qu'après une CI réussie sur `main`, donc rien n'est déployé tant que le bug existe. Ne commitez jamais le bug sur `main`.

## Avant de commencer

1. Les nouveaux tests du traitement (`tests/unit/test_processing.py`) doivent être commités et poussés sur `main`.
2. Attendez que la CI de `main` soit verte (et que le CD ait déployé) : c'est la **situation de départ** à capturer.

```bash
git switch main
git pull
```

## Déroulé pas à pas

### Étape 1 : introduire la panne

```bash
git switch -c demo/panne-seuil
```

Ouvrez `src/processing/aggregations.py`, ligne 47, et remplacez `> threshold` par `>= threshold`. Avec Git Bash, la même modification en une commande :

```bash
sed -i '47s/> threshold/>= threshold/' src/processing/aggregations.py
git diff
```

Commitez, poussez, puis ouvrez la pull request :

```bash
git commit -am "bug(demo): seuil >= au lieu de > dans flag_high_value_transactions"
git push -u origin demo/panne-seuil
gh pr create --base main --title "Démo : panne volontaire (seuil)" --body "Panne volontaire pour la simulation d'échec de la CI. Ne pas fusionner avant la correction."
```

### Étape 2 : la CI échoue

Ouvrez la pull request sur GitHub, onglet **Checks** (ou l'onglet **Actions**). Il faut environ 5 minutes pour que la CI se termine. Vous devez voir :

| Élément | Résultat attendu |
|---|---|
| Job « Typage et tests unitaires » | **échec** (croix rouge) au pas « Tests unitaires (Pytest) » ; le typage (Mypy) passe, car le bug n'est pas un bug de type |
| Job « Tests d'intégration » | **ignoré** (« skipped »), car il dépend du job précédent |
| Job « Statut CI » | **FAILED** dans le résumé |
| Workflow CD | **aucune exécution** pour cette branche |

### Étape 3 : le message d'erreur

Dans le log du pas « Tests unitaires (Pytest) », les dernières lignes ressemblent à :

```
FAILED tests/unit/test_processing.py::test_flag_high_value[5000.00-False] - assert True is False
FAILED tests/unit/test_processing.py::test_amount_equal_to_threshold_is_not_high_value - AssertionError: 5000.00 ne dépasse pas le seuil de 5000 : le flag doit être faux (le seuil est strictement supérieur)
FAILED tests/unit/test_processing.py::test_flag_uses_custom_threshold - assert [False, True, True] == [False, False, True]
3 failed, 120 passed
```

Lecture : trois tests du traitement échouent. Tous portent sur la valeur exactement égale au seuil. Le message du deuxième test donne directement la cause : « 5000.00 ne dépasse pas le seuil ». Les 120 autres tests passent, donc le problème est bien localisé.

### Étape 4 : la correction

Rétablissez la ligne 47 (`>= threshold` devient `> threshold`) :

```bash
sed -i '47s/>= threshold/> threshold/' src/processing/aggregations.py
git diff
git commit -am "fix: le seuil est strictement supérieur (montant > threshold)"
git push
```

### Étape 5 : la CI réussit

La CI se relance toute seule sur la pull request. Vous devez voir :

| Élément | Résultat attendu |
|---|---|
| Job « Typage et tests unitaires » | succès |
| Job « Tests d'intégration » | succès (MySQL et MinIO démarrés avec Docker) |
| Job « Statut CI » | **SUCCESS** |

### Étape 6 : fusion et déploiement (optionnel)

```bash
gh pr merge --squash --delete-branch
```

La CI de `main` se relance, puis le CD construit l'image et déploie sur la VM : il ne déploie que le code corrigé. Capturez le CD réussi.

### Nettoyage

```bash
git switch main
git pull
git branch -D demo/panne-seuil   # si la branche locale existe encore
```

## Captures d'écran à conserver

Rangez-les dans `docs/captures/` avec ces noms (voir aussi `docs/captures/README.md`) :

| N° | Fichier | Ce qu'il montre | Point du sujet |
|---|---|---|---|
| 1 | `01-ci-verte-avant.png` | Onglet Actions : CI de `main` verte avant la panne | situation de départ |
| 2 | `02-diff-bug.png` | `git diff` ou diff de la PR : `>` devient `>=` ligne 47 | **la cause** |
| 3 | `03-pr-checks-rouge.png` | La PR avec la croix rouge sur les vérifications | **l'échec de la pipeline** |
| 4 | `04-graphe-workflow-echec.png` | Page de l'exécution : job de tests en échec, intégration ignorée, Statut CI FAILED | **l'échec de la pipeline** |
| 5 | `05-log-erreur-pytest.png` | Log du pas « Tests unitaires (Pytest) » avec les lignes `FAILED` | **le message d'erreur** |
| 6 | `06-cd-non-declenche.png` | Onglet Actions filtré sur le CD : aucune exécution pour la branche de démonstration | le code cassé n'est pas déployé |
| 7 | `07-diff-correction.png` | Diff de la correction : `>=` redevient `>` | **la correction** |
| 8 | `08-pr-checks-vert.png` | La PR avec toutes les vérifications vertes | **le succès après correction** |
| 9 | `09-graphe-workflow-succes.png` | Page de l'exécution : les trois jobs en succès, Statut CI SUCCESS | **le succès après correction** |
| 10 | `10-cd-deploiement.png` | Le CD réussi après la fusion (optionnel) | déploiement de la version corrigée |

## Autres pannes possibles

Pour varier, ou si votre encadrant préfère un autre type de panne. Chaque panne est détectée à un endroit différent de la chaîne.

| Panne volontaire | Où la CI la détecte | Message attendu |
|---|---|---|
| Faire retourner un entier à `generate_iban` dans `src/generator/iban.py` (`return len(digits)`) | Pas « Vérifier le typage (Mypy) » du job de qualité | `error: Incompatible return value type (got "int", expected "str")  [return-value]` |
| Introduire une faute dans un fichier de `sql/ddl/` (par exemple `CREATE OR REPLACE TABLE`, accepté par MariaDB mais pas par MySQL) | Job « Tests d'intégration » (vrai MySQL) | `pymysql.err.ProgrammingError: (1064, "You have an error in your SQL syntax ...")` |
| Générer un CSV avec un montant invalide (`python -c "from src.generator import create_csv_files; create_csv_files(corrupt=True)"`) | Pas une panne de CI : la validation à l'exécution rejette la ligne | Bloc « Validation » de la pipeline : `colonne montant (valeur 'INVALID_AMOUNT') : le montant n'est pas un nombre` |

Le deuxième cas s'est produit pour de vrai pendant le projet : la CI l'a signalé avant tout déploiement.
