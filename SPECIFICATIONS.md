# Spécifications fonctionnelles et techniques

## 1. Document de référence

**Projet :** Mise en situation – Intégration continue  
**Repository :** TP-Mise_en_situation_D-int-gration_continu  
**Version :** 1.0  
**Statut :** Validé – base de référence du projet

Ce document formalise les décisions prises concernant le périmètre fonctionnel, l'architecture et les choix techniques du projet. Toute évolution importante devra être discutée puis ajoutée à ce document afin de conserver une trace des décisions.

---

## 2. Objectif du projet

Construire une pipeline Data automatisée, testable et fiable permettant de traiter des données de transactions financières.

La pipeline doit permettre de :

1. générer plusieurs fichiers CSV de transactions ;
2. stocker automatiquement les fichiers dans un stockage compatible S3 ;
3. récupérer les fichiers depuis le stockage S3 ;
4. charger et valider les données ;
5. appliquer les traitements demandés ;
6. insérer les résultats dans une base de données relationnelle ;
7. gérer les erreurs temporaires avec des mécanismes de retry ;
8. éviter le retraitement et l'insertion de doublons ;
9. vérifier automatiquement la qualité et le fonctionnement de la pipeline avec des tests ;
10. intégrer l'ensemble dans une démarche CI/CD ;
11. déployer l'environnement avec Docker ;
12. décrire l'infrastructure avec Terraform.

---

## 3. Problématique

> Comment concevoir et automatiser une pipeline de traitement de données financières fiable et testable, capable de récupérer des données depuis un stockage S3, de les traiter puis de les intégrer dans une base de données relationnelle, tout en garantissant la qualité des données, la gestion des erreurs et l'absence de doublons ?

---

## 4. Périmètre fonctionnel

### 4.1 Génération des données

La pipeline doit générer plusieurs fichiers CSV contenant chacun entre 5 et 10 transactions financières.

Chaque transaction contient les colonnes :

- `datetime_transaction`
- `iban_origine`
- `pays_source`
- `banque_source`
- `iban_destinataire`
- `pays_destinataire`
- `montant`

Les données ne doivent pas être totalement aléatoires. Elles doivent permettre de tester les traitements et les cas particuliers.

Les jeux de données doivent notamment contenir :

- plusieurs transactions provenant du même IBAN ;
- plusieurs transactions provenant de la même banque ;
- plusieurs transactions vers le même IBAN destinataire ;
- des montants inférieurs à 5 000 € ;
- des montants supérieurs à 5 000 € ;
- plusieurs fichiers afin de tester le traitement de fichiers distincts.

### 4.2 Chargement des données

Le chargement des données doit être séparé du traitement.

Une fonction de chargement est responsable de récupérer les données et de produire une structure exploitable par le traitement.

Le traitement métier ne doit pas effectuer directement des opérations d'entrée/sortie.

### 4.3 Validation

Les données récupérées doivent être contrôlées avant leur traitement et leur insertion en base.

Les règles de validation seront précisées et implémentées progressivement. Une donnée invalide doit produire une erreur explicite et empêcher l'insertion de données incorrectes.

Règles implémentées (`src/validation/`, fonctions pures sans accès fichier, MinIO ni MySQL) :

- le fichier contient au moins une transaction et exactement les 7 colonnes attendues (ni manquante, ni en trop) ;
- aucune valeur manquante ou vide ;
- `datetime_transaction` au format `AAAA-MM-JJ HH:MM:SS`, date existante ;
- `pays_source` et `pays_destinataire` : 2 lettres majuscules ;
- `iban_origine` et `iban_destinataire` : 2 lettres majuscules, 2 chiffres, puis 11 à 30 caractères alphanumériques ; le préfixe de l'IBAN doit correspondre au pays associé ;
- `banque_source` : 100 caractères maximum ;
- `montant` : nombre fini **strictement positif**, 2 décimales maximum, ne dépassant pas la capacité de la colonne `DECIMAL(12,2)`. Un montant négatif ou nul est donc invalide. Le générateur injecte volontairement un montant négatif (-50.00) dans chaque fichier : le résultat final de la pipeline montre ainsi que la validation est bien exécutée.

Comportement en cas d'erreur :

- **Rejet par ligne** : une ligne invalide est rejetée seule, avec toutes ses erreurs. Elle n'est ni traitée ni insérée. Les lignes valides du même fichier sont traitées et insérées, et `rows_count` dans `processed_files` ne compte que les lignes insérées.
- **Fichier inexploitable** : un fichier illisible (pas de l'UTF-8 ou pas un CSV), vide ou dont l'en-tête est incorrect n'est ni traité, ni inséré, ni marqué comme traité. La pipeline s'arrête alors avec un message `ERREUR` et le code de sortie 1.
- **Fichier sans aucune ligne valide** : il n'est pas inséré ni marqué comme traité, et la pipeline continue avec les autres fichiers.
- **Rapport final** : la pipeline affiche un bloc « Validation » qui liste chaque ligne rejetée (fichier, ligne du CSV, colonne, valeur, raison), puis un résumé : transactions insérées, lignes rejetées, fichiers traités, fichiers déjà traités. Les sommes et le comptage des montants supérieurs à 5000 portent sur les seules lignes insérées.

### 4.4 Traitement

La pipeline doit réaliser les traitements suivants :

- calcul de la somme des montants par `iban_origine` ;
- calcul de la somme des montants par `banque_source` ;
- calcul de la somme des montants reçus par `iban_destinataire` ;
- ajout d'un indicateur lorsque le montant est supérieur à 5 000 €.

Les fonctions de traitement doivent être pures :

- pas de modification de l'entrée ;
- pas d'état externe ;
- même entrée = même résultat ;
- pas d'accès direct aux fichiers, à MinIO ou à MySQL.

### 4.5 Base de données

La base de données relationnelle retenue est **MySQL**.

Elle doit permettre de stocker les données traitées et de conserver la trace des fichiers déjà traités.

Deux besoins principaux sont identifiés :

- stockage des transactions traitées ;
- suivi des fichiers déjà traités pour empêcher leur retraitement.

### 4.6 Stockage S3

Le stockage objet retenu pour le développement local est **MinIO**, compatible avec l'API S3.

Le flux attendu est :

`Génération CSV → MinIO → lecture depuis MinIO → validation → traitement → MySQL`

La pipeline ne devra pas dépendre du système de fichiers local pour lire les CSV dans le fonctionnement cible du niveau 2.


Choix d'implémentation :

- Le module `src/storage/` utilise **Boto3** avec un `endpoint_url` pointant sur MinIO. Les identifiants (`MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`), l'adresse (`MINIO_ENDPOINT`) et le bucket (`MINIO_BUCKET`) viennent de variables d'environnement : fichier `.env` local ignoré par git, secrets et variables GitHub en CI/CD. Aucune valeur par défaut n'est écrite dans le dépôt.
- Le bucket est créé s'il n'existe pas. Après chaque upload, la taille de l'objet stocké est comparée à celle du fichier local ; une différence lève une erreur.
- Les fichiers sont stockés à la racine du bucket, la clé étant le nom du fichier CSV. La pipeline lit **uniquement** depuis MinIO : elle génère les CSV dans un dossier temporaire, les envoie dans le bucket, puis relit les objets du bucket pour les traiter.
- Les tests d'intégration utilisent un bucket dédié `<MINIO_BUCKET>-test`, créé puis supprimé, afin de ne jamais toucher aux données applicatives.

### 4.7 Anti-doublon

La pipeline doit empêcher le retraitement d'un fichier déjà traité.

Une stratégie basée sur l'identification du fichier sera utilisée, notamment à l'aide de :

- son nom ;
- et/ou un hash du fichier ;
- et d'une table de suivi en base.

Un fichier traité avec succès ne doit pas être traité une deuxième fois lors d'un retry ou d'une nouvelle exécution.


Le hash SHA-256 est calculé sur le contenu lu dans MinIO et stocké dans `processed_files` (colonne unique). Les transactions d'un fichier et son enregistrement dans `processed_files` sont écrits dans une seule transaction SQL.

### 4.8 Retry

Deux mécanismes de retry sont prévus :

- retry lors de la récupération des fichiers depuis MinIO ;
- retry lors de l'insertion dans MySQL.

Pour chaque opération concernée :

1. détecter l'échec ;
2. attendre avant une nouvelle tentative ;
3. effectuer plusieurs tentatives ;
4. limiter le nombre maximum de tentatives ;
5. arrêter proprement la pipeline si toutes les tentatives échouent ;
6. produire un message d'erreur explicite.

Le retry ne doit pas provoquer de doublons.


Choix d'implémentation (`src/retry.py`) :

- **3 tentatives** maximum, **2 s** d'attente puis doublement à chaque échec (backoff x2), sans attente après la dernière tentative. Réglable par les variables d'environnement optionnelles `RETRY_MAX_ATTEMPTS` et `RETRY_DELAY_SECONDS`.
- **MinIO** : sont retentées les erreurs de connexion, les délais dépassés, les erreurs HTTP 5xx et le throttling. Les erreurs permanentes (objet absent, accès refusé) ne sont pas retentées.
- **MySQL** : sont retentées les erreurs de connexion perdue ou impossible, les deadlocks et les attentes de verrou. Les erreurs permanentes (accès refusé, base inconnue) ne sont pas retentées.
- **Pas de doublon** : chaque tentative d'insertion utilise une connexion neuve et une transaction atomique. Après un échec, la tentative suivante vérifie d'abord si le fichier est déjà enregistré (cas où le commit a réussi mais où la réponse s'est perdue). La contrainte d'unicité sur le hash est le dernier filet : un doublon est interprété comme « déjà traité » et n'est ni retenté ni signalé comme erreur.
- **Arrêt propre** : si toutes les tentatives échouent, la pipeline s'arrête avec un message `ERREUR` indiquant l'opération, le nombre de tentatives et la dernière cause, et un code de sortie 1. Les fichiers déjà traités restent en base.

---

## 5. CI – Intégration continue

La CI sera réalisée avec **GitHub Actions**.

À chaque modification pertinente du projet, la pipeline CI doit notamment pouvoir :

1. installer les dépendances ;
2. vérifier le typage avec Mypy ;
3. exécuter les tests unitaires avec Pytest ;
4. démarrer les services nécessaires avec Docker ;
5. exécuter les tests d'intégration ;
6. retourner un statut SUCCESS ou FAILED.

Le but est de détecter automatiquement les régressions et les erreurs avant le déploiement.

Workflow implémenté (`.github/workflows/ci.yml`) :

- **Déclenchement** : push sur `main`, pull request, ou lancement manuel, uniquement si `src/`, `tests/`, `sql/`, `requirements.txt`, `pytest.ini`, `docker-compose.yml` ou le workflow lui-même changent. Une nouvelle exécution annule la précédente sur la même branche.
- **Job `quality`** : installation des dépendances, `mypy src tests`, `pytest tests/unit`. Il n'a besoin ni de secret ni de service Docker (S3 simulé avec moto, MySQL simulé).
- **Job `integration`** (après `quality`) : vérifie que les secrets et variables sont définis, démarre MySQL et MinIO avec `docker compose up -d --wait`, exécute `pytest tests/integration`, affiche les logs des services en cas d'échec, puis arrête et supprime les services (`docker compose down -v`). Il est ignoré pour les pull requests venant d'un fork, qui n'ont pas accès aux secrets.
- **Job `status`** : calcule le statut final `SUCCESS` ou `FAILED` et l'écrit dans le résumé de l'exécution. Le workflow échoue si `quality` ou `integration` échoue.
- **Secrets du dépôt** : `MYSQL_ROOT_PASSWORD`, `MYSQL_PASSWORD`, `MINIO_ROOT_PASSWORD`. **Variables du dépôt** : `MYSQL_USER`, `MYSQL_DATABASE`, `MINIO_ROOT_USER`, `MINIO_BUCKET`.

---

## 6. CD – Déploiement continu

Le projet intégrera une partie CD.

Après validation de la CI, le workflow CD devra pouvoir :

1. construire l'image Docker de l'application ;
2. préparer l'environnement de déploiement ;
3. déployer une version validée de l'application.

Stratégie retenue (`.github/workflows/cd.yml`) :

- **Cible** : la machine virtuelle fournie pour le projet, accessible en SSH (utilisateur `ubuntu`). L'environnement déployé contient MySQL, MinIO et le traitement, tous dans des conteneurs, décrits par le **même `docker-compose.yml`** que celui du développement et de la CI (un seul fichier, le service de l'application étant dans le profil `job`). Kubernetes n'est pas retenu : un cluster et de nombreux manifests seraient disproportionnés pour ce projet. La VM sera créée par Terraform (§8).
- **Déclenchement** : automatique après une CI réussie sur `main` (push), et manuel depuis `main`. Le CD déploie exactement le commit validé par la CI. Le déploiement est systématique : il n'y a pas d'interrupteur.
- **Étape 1, construire l'image** : le `Dockerfile` construit l'image de l'application (Python 3.12, utilisateur non root, dépendances de `requirements.txt` ; aucun identifiant dans l'image). Un seul fichier `requirements.txt` sert en local, en CI et dans l'image, au prix d'une image plus lourde (outils de test inclus). L'image est publiée sur **Docker Hub** (`<compte>/transactions-pipeline`) avec deux étiquettes : le SHA du commit (version précise, base d'un retour arrière) et `latest`. Un test rapide vérifie que l'image démarre. La CI construit aussi l'image pour détecter une erreur de `Dockerfile` avant le CD.
- **Étape 2, préparer l'environnement** : le workflow installe Docker sur la VM s'il est absent (l'utilisateur doit pouvoir utiliser `sudo` sans mot de passe), copie `docker-compose.yml` et le script de lancement, et écrit un fichier `.env` (droits 600) à partir des secrets et variables du dépôt GitHub. Les ports de MySQL (3306), de l'API MinIO (9000) et de sa console (9001) sont publiés sur toutes les interfaces de la machine : ils sont joignables depuis n'importe quelle adresse IP, sous réserve du pare-feu du réseau de la VM.
- **Étape 3, déployer** : la VM récupère (`docker compose pull`) l'image publiée sur Docker Hub, sans aucun identifiant (le dépôt Docker Hub doit donc être public ; l'image ne contient aucun secret), démarrage de MySQL et MinIO avec attente de leur état sain, première exécution du traitement avec génération de données de démonstration (qui sert de test de fumée), puis planification. L'ancienne version déployée est conservée dans `.previous_image` sur la VM pour un retour arrière manuel.
- **Traitement régulier** : une entrée cron sur la VM lance la pipeline toutes les 5 minutes (`run-pipeline.sh`, `flock` empêche deux exécutions simultanées). Comme en développement, chaque exécution commence par générer de **nouveaux** fichiers CSV (graine aléatoire, dates du jour, noms uniques horodatés qui ne s'écrasent pas), les envoie dans MinIO, puis traite ce qui s'y trouve ; le mécanisme anti-doublon (§4.7) évite tout retraitement d'un fichier déjà traité. La génération reste reproductible (graine 42, noms fixes) par défaut, pour les tests et la CI. La sortie est écrite dans `pipeline.log`.
- **Connexion SSH** : par mot de passe (`sshpass`), car c'est le seul accès fourni pour la VM. Ni le mot de passe ni l'adresse ne sont écrits dans le dépôt : ils sont fournis par les secrets GitHub.
- **Secrets** du dépôt (Settings, Secrets and variables, Actions ; ceux de la CI sont partagés avec le CD) : `SSH_HOST`, `SSH_USER`, `SSH_PASSWORD`, `MYSQL_ROOT_PASSWORD`, `MYSQL_PASSWORD`, `MINIO_ROOT_PASSWORD`, et en option `SSH_KNOWN_HOSTS`. `DOCKERHUB_TOKEN` (jeton d'accès Docker Hub avec droit d'écriture). **Variables** : `DOCKERHUB_USERNAME`, `MYSQL_USER`, `MYSQL_DATABASE`, `MINIO_ROOT_USER`, `MINIO_BUCKET`, et en option `SSH_PORT`.

---

## 7. Infrastructure et conteneurisation

Les composants principaux seront exécutés avec Docker.

L'environnement cible comprend au minimum :

- application Python ;
- MinIO ;
- MySQL.

Docker Compose sera utilisé pour faciliter le démarrage de l'environnement local et des tests d'intégration.

---

## 8. Infrastructure as Code

**Terraform** est retenu pour la partie Infrastructure as Code.

L'objectif est de décrire de manière reproductible les ressources nécessaires au projet plutôt que de dépendre uniquement de configurations manuelles.

Les ressources exactes prises en charge par Terraform seront définies lors de la mise en œuvre de la partie niveau 3.

---

## 9. Stack technique validée

| Besoin | Technologie |
|---|---|
| Langage | Python |
| Manipulation des données | Pandas |
| Tests | Pytest |
| Vérification du typage | Mypy |
| Stockage objet S3 local | MinIO |
| API S3 Python | Boto3 |
| Base de données | MySQL |
| Conteneurisation | Docker |
| Orchestration locale | Docker Compose |
| CI | GitHub Actions |
| CD | GitHub Actions + Docker |
| Infrastructure as Code | Terraform |
| Versionnement | Git / GitHub |

---

## 10. Architecture cible

```
                         GitHub
                           |
                           v
                  GitHub Actions
                  +--------+--------+
                  |                 |
                  v                 v
                 CI                 CD
          tests / mypy /       build + deploy
             pytest                  |
                                    v
                              Environnement
                                Docker
                                    |
                    +---------------+---------------+
                    |               |               |
                    v               v               v
                  MinIO           Python           MySQL
                   S3             Pipeline          DB
                    |               |
                    |               v
                    +--------> Validation
                                    |
                                    v
                                Processing
                                    |
                                    v
                                Anti-doublon
                                    |
                                    v
                                  MySQL
```

Flux fonctionnel :

```
Génération CSV
      |
      v
    MinIO
      |
      v
Lecture CSV
      |
      v
Validation
      |
      v
Processing
      |
      v
Anti-doublon
      |
      v
MySQL
```

---

## 11. Organisation logique du code

L'organisation cible est la suivante :

```
project/
|
+-- src/
|   +-- generator/
|   +-- storage/
|   +-- loader/
|   +-- validation/
|   +-- processing/
|   +-- database/
|   +-- pipeline.py
|
+-- tests/
|   +-- unit/
|   +-- integration/
|
+-- terraform/
|
+-- docker/
|
+-- .github/
|   +-- workflows/
|       +-- ci.yml
|       +-- cd.yml
|
+-- docker-compose.yml
+-- Dockerfile
+-- requirements.txt
+-- .env.example
+-- README.md
```

Cette organisation pourra évoluer si une meilleure séparation des responsabilités est identifiée pendant le développement.

---

## 12. Tests

Les tests doivent couvrir au minimum :

### Tests unitaires

- génération des données ;
- chargement ;
- validation ;
- calculs d'agrégation ;
- création du flag `montant > 5000` ;
- gestion des cas limites.

### Tests d'intégration

- communication avec MinIO ;
- récupération des fichiers ;
- communication avec MySQL ;
- insertion des données ;
- fonctionnement de la pipeline complète ;
- mécanisme anti-doublon ;
- comportement des retries.

Les tests doivent être exécutables automatiquement dans la CI.

---

## 13. Simulation d'une panne

Le sujet demande de démontrer la capacité de la CI à détecter une erreur.

Une panne volontaire sera introduite afin de montrer :

1. la cause de l'erreur ;
2. l'échec de la pipeline ;
3. le message d'erreur ;
4. la correction ;
5. le succès de la pipeline après correction.

Des captures d'écran seront conservées pour le rendu final.

---

## 14. Niveau 3 retenu

Deux améliorations du niveau 3 sont retenues :

### Option CD / déploiement

Mise en place d'un processus de déploiement automatique avec Docker et GitHub Actions.

### Option Terraform / OpenTofu

Mise en place d'une Infrastructure as Code avec **Terraform**.

Ces deux options ont été retenues car elles sont directement liées aux objectifs de Data Engineering, Cloud et CI/CD du projet.

---

## 15. Ordre de réalisation

Le développement sera réalisé progressivement :

1. définition des données et cas de test ;
2. génération des CSV ;
3. chargement et traitement Python ;
4. tests unitaires ;
5. mise en place de MySQL ;
6. insertion et tests d'intégration ;
7. Docker / Docker Compose ;
8. mise en place de MinIO ;
9. lecture des CSV depuis MinIO ;
10. anti-doublon ;
11. retry MinIO et MySQL ;
12. CI GitHub Actions ;
13. simulation et correction d'une panne ;
14. CD ;
15. Terraform ;
16. documentation finale.

---

## 16. Règles de décision pour la suite

Pour éviter les changements de direction non documentés :

- toute modification importante de la stack doit être discutée avant implémentation ;
- toute modification du périmètre doit être ajoutée à ce document ;
- les choix techniques doivent être justifiés par rapport au sujet ;
- les fonctionnalités du sujet restent prioritaires par rapport aux améliorations facultatives ;
- la complexité inutile doit être évitée ;
- chaque étape doit être testée avant de passer à la suivante.

---

## 17. État des décisions

| Élément | Décision |
|---|---|
| Objectif | Pipeline Data financière fiable et automatisée |
| Langage | Python |
| Data processing | Pandas |
| BDD | MySQL |
| S3 local | MinIO |
| Tests | Pytest |
| Typage | Mypy |
| Conteneurs | Docker |
| Orchestration locale | Docker Compose |
| CI | GitHub Actions |
| CD | GitHub Actions + Docker |
| IaC | Terraform |
| Niveau 3 | CD + Terraform |
| Anti-doublon | Oui |
| Retry S3 | Oui |
| Retry BDD | Oui |
| Tests d'intégration | Oui |

---

## 18. Historique des décisions

### Version 1.0 – 02/10/2026

Première version du document.

Décisions validées :

- MySQL comme base de données relationnelle ;
- MinIO comme stockage S3 local ;
- Docker/Docker Compose pour l'environnement ;
- GitHub Actions pour la CI ;
- CD ajouté au niveau 3 ;
- Terraform ajouté au niveau 3 ;
- mécanisme anti-doublon obligatoire ;
- retry pour MinIO et MySQL ;
- séparation chargement / traitement ;
- fonctions de traitement pures ;
- tests unitaires et d'intégration.

Toute nouvelle décision importante devra être ajoutée à l'historique.
