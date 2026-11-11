# Pipeline de transactions financières — CI/CD

[![CI](https://github.com/cocoalice03/TP-Mise_en_situation_D-int-gration_continu/actions/workflows/ci.yml/badge.svg)](https://github.com/cocoalice03/TP-Mise_en_situation_D-int-gration_continu/actions/workflows/ci.yml)
[![CD](https://github.com/cocoalice03/TP-Mise_en_situation_D-int-gration_continu/actions/workflows/cd.yml/badge.svg)](https://github.com/cocoalice03/TP-Mise_en_situation_D-int-gration_continu/actions/workflows/cd.yml)
[![Terraform](https://github.com/cocoalice03/TP-Mise_en_situation_D-int-gration_continu/actions/workflows/terraform.yml/badge.svg)](https://github.com/cocoalice03/TP-Mise_en_situation_D-int-gration_continu/actions/workflows/terraform.yml)

Projet de Mastère Data Engineering & IA (mise en situation d'intégration continue) : une pipeline data qui génère des transactions bancaires au format CSV, les stocke dans un service S3, les valide, les traite et les insère dans MySQL. La pipeline est testée, conteneurisée, déployée automatiquement et son infrastructure est décrite en Terraform.

## Le flux

```
Génération CSV ──► MinIO (S3) ──► Lecture ──► Validation ──► Traitement ──► MySQL
                                                  │
                                      lignes invalides rejetées
                                      et listées dans le rapport
```

- **Génération** : fichiers CSV de transactions (IBAN, banques, pays, montants), avec des cas de test injectés (montant > 5000, montant négatif).
- **Stockage S3** : les fichiers sont envoyés dans MinIO, puis relus depuis MinIO (jamais depuis le disque local).
- **Validation** : chaque ligne est contrôlée (colonnes, date, IBAN et pays, montant strictement positif) ; une ligne invalide est rejetée et signalée, les autres continuent.
- **Traitement** : sommes par IBAN d'origine, par banque source et par IBAN destinataire, et repérage des transactions de plus de 5000 €, par des fonctions pures.
- **Base de données** : insertion dans MySQL, dans une seule transaction SQL par fichier.
- **Anti-doublon** : un fichier déjà traité (même hash SHA-256) n'est jamais retraité.
- **Retry** : lecture MinIO et insertion MySQL réessayées en cas d'erreur passagère, sans créer de doublon, puis arrêt propre avec un message explicite.

## Stack

| Domaine | Outil |
|---|---|
| Langage | Python 3.12 |
| Stockage objet S3 | MinIO (API S3 via Boto3) |
| Base de données | MySQL 8.4 (PyMySQL, SQL écrit à la main, schéma dans `sql/ddl/`) |
| Tests et typage | Pytest, Mypy |
| Conteneurs | Docker, Docker Compose |
| CI/CD | GitHub Actions, Docker Hub |
| Infrastructure as Code | Terraform (Azure) |

## Structure du dépôt

```
src/
  generator/      génération des fichiers CSV
  storage/        accès à MinIO (S3) : bucket, envoi, liste, lecture
  loader/         lecture des CSV et calcul du hash
  validation/     règles de validation des transactions
  processing/     traitements (fonctions pures)
  database/       connexion MySQL, insertion, anti-doublon
  retry.py        mécanisme de retry
  config.py       configuration par variables d'environnement
  pipeline.py     point d'entrée : python -m src.pipeline
sql/ddl/          création des tables (transactions, processed_files)
tests/unit/       tests unitaires (sans service)
tests/integration/ tests d'intégration (vrais MySQL et MinIO)
terraform/        infrastructure de production sur Azure
docs/             guides : Terraform, simulation de panne, captures
.github/workflows/ ci.yml, cd.yml, terraform.yml
docker-compose.yml  MySQL, MinIO et l'application (dév, CI et production)
Dockerfile          image de l'application
run-pipeline.sh     lancement planifié (cron) sur la VM
```

## Démarrage en local

Prérequis : Python 3.12, Docker Desktop.

```bash
# 1. Environnement Python
python -m venv .venv
source .venv/Scripts/activate      # PowerShell : .venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Configuration : copier le modèle puis remplir les mots de passe
cp .env.example .env

# 3. Démarrer MySQL et MinIO
docker compose up -d --wait

# 4. Lancer la pipeline (génère de nouveaux fichiers, les traite, affiche le rapport)
python -m src.pipeline
```

Le fichier `.env` n'est jamais commité. Console MinIO : http://localhost:9001.

### Tests

```bash
mypy src tests                 # typage
pytest tests/unit              # tests unitaires (aucun service nécessaire)
pytest tests/integration -v    # tests d'intégration (MySQL et MinIO démarrés)
```

Les tests d'intégration travaillent dans une base `<MYSQL_DATABASE>_test` et un bucket `<MINIO_BUCKET>-test` créés puis supprimés : les données de travail ne sont jamais touchées. Ils sont ignorés si MySQL ou MinIO ne répond pas.

## CI/CD

| Workflow | Déclenchement | Ce qu'il fait |
|---|---|---|
| **CI** (`ci.yml`) | push sur `main`, pull request | installe les dépendances, Mypy, tests unitaires, construit l'image Docker, démarre MySQL et MinIO avec Docker Compose, tests d'intégration, statut final SUCCESS ou FAILED |
| **CD** (`cd.yml`) | après une CI réussie sur `main`, ou à la main | construit et publie l'image sur Docker Hub, puis, sur la VM : copie le compose, écrit le `.env`, démarre MySQL et MinIO, lance une première exécution et planifie la pipeline toutes les 5 minutes (cron) |
| **Terraform** (`terraform.yml`) | modification de `terraform/` | vérifie le format et la validité du code Terraform |

Secrets et variables GitHub (Settings, Secrets and variables, Actions) :

| Secrets | Variables |
|---|---|
| `MYSQL_ROOT_PASSWORD`, `MYSQL_PASSWORD`, `MINIO_ROOT_PASSWORD` | `MYSQL_USER`, `MYSQL_DATABASE`, `MINIO_ROOT_USER`, `MINIO_BUCKET` |
| `SSH_HOST`, `SSH_USER`, `SSH_PRIVATE_KEY` | `DOCKERHUB_USERNAME` (en minuscules) |
| `DOCKERHUB_TOKEN` | |

## Infrastructure (Terraform, Azure)

Terraform crée l'infrastructure de production ; le CD y déploie l'application.

- groupe de ressources `rg-transactions-dk` (région `denmarkeast`) ;
- réseau virtuel, sous-réseau, pare-feu (seul le port 22 ouvert à tous), IP publique statique ;
- VM Ubuntu 24.04 `Standard_B2s` avec connexion par clé SSH et Docker installé au premier démarrage ;
- disque de données de 32 Go pour les volumes MySQL et MinIO.

Les choix (et ce qui n'est pas déployé : Kubernetes, base managée, etc.), la procédure complète et le dépannage sont dans [`docs/terraform.md`](docs/terraform.md).

```bash
cd terraform
terraform init
terraform plan
terraform apply
```

## Vérifier le déploiement sur la VM

Se connecter à la VM (depuis `terraform/`, l'IP est donnée par Terraform) :

```bash
ssh -i ~/.ssh/transactions_deploy azureuser@$(terraform output -raw public_ip)
cd ~/transactions-app
```

Puis, sur la VM :

| Vérification | Commande | Résultat attendu |
|---|---|---|
| Machine prête (premier démarrage terminé) | `cloud-init status` | `status: done` |
| Disque de données monté | `df -h /var/lib/docker` | un disque d'environ 32 Go |
| Services démarrés | `docker compose ps` | `transactions-mysql` et `transactions-minio` en `Up (healthy)` |
| Version déployée | `grep APP_IMAGE .env` | `<compte>/transactions-pipeline:<SHA du commit déployé>` |
| Planification active | `crontab -l \| grep transactions-pipeline` | une ligne `*/5 * * * * …/run-pipeline.sh` |
| Dernière exécution | `grep "Résumé" pipeline.log \| tail -1` | `Résumé : N transaction(s) insérée(s), M rejetée(s), …` |
| Suivi en direct | `tail -f pipeline.log` | un nouveau bloc toutes les 5 minutes (quitter avec `Ctrl+C`) |

Données en base (le mot de passe est lu à l'intérieur du conteneur, il n'apparaît pas dans l'historique) :

```bash
docker exec transactions-mysql sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" -e "
  SELECT COUNT(*) AS fichiers, MAX(processed_at) AS dernier_traitement FROM processed_files;
  SELECT COUNT(*) AS transactions, SUM(is_high_value) AS plus_de_5000 FROM transactions;"'
```

Le nombre de fichiers doit augmenter de 3 toutes les 5 minutes.

Fichiers dans MinIO :

```bash
docker exec transactions-minio sh -c 'mc alias set local http://localhost:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && mc ls --recursive local/ | tail -5'
```

Lancer une exécution à la main (même commande que le cron) :

```bash
./run-pipeline.sh
```

Si quelque chose ne va pas : `docker compose logs --tail=50 mysql minio` pour les services, `tail -50 pipeline.log` pour la pipeline, et `/var/log/cloud-init-output.log` pour l'installation de la VM.

### Mettre en pause ou supprimer le traitement planifié

À lancer sur la VM. Ces commandes ne touchent que la ligne `# transactions-pipeline` du cron ; une exécution déjà en cours va jusqu'à son terme.

| Action | Commande |
|---|---|
| Mettre en pause (la ligne est mise en commentaire) | `crontab -l \| sed '/transactions-pipeline/ s/^[^#]/#&/' \| crontab -` |
| Reprendre | `crontab -l \| sed '/transactions-pipeline/ s/^#//' \| crontab -` |
| Supprimer la planification | `crontab -l \| grep -v transactions-pipeline \| crontab -` |
| Vérifier l'état | `crontab -l \| grep transactions-pipeline` (une ligne qui commence par `#` = en pause ; rien = supprimée) |

**Attention** : chaque déploiement du CD réinstalle la ligne cron, active. Après une mise en pause, il faut la refaire si le CD repasse (par exemple après un push sur `main`).

Pour arrêter aussi MySQL et MinIO sans perdre de données : `docker compose stop` (reprise avec `docker compose start`). Pour ne plus payer la VM, l'éteindre depuis votre poste : `az vm deallocate -g rg-transactions-dk -n vm-transactions-dk`.

## Limites et perspectives

Les choix actuels sont adaptés à un projet d'école (un seul serveur, un crédit étudiant, des droits Azure limités). Voici leurs limites et la manière de les dépasser.

### Infrastructure et déploiement

| Limite actuelle | Pourquoi aujourd'hui | Perspective | Effort |
|---|---|---|---|
| `terraform apply` lancé depuis un poste, pas par GitHub Actions | Le compte Azure de l'école ne permet pas de créer une identité d'application | Fédération OIDC entre GitHub et Azure (aucun secret stocké) : `plan` automatique sur chaque pull request, `apply` à la fusion sur `main` avec approbation d'un environnement GitHub. Le code Terraform est déjà prêt, seule l'authentification change | Moyen, avec un droit accordé par l'école |
| État Terraform en fichier local | Une seule personne applique ; un état distant demande un stockage créé au préalable | Backend `azurerm` : compte de stockage dédié, verrouillage automatique, historique des versions, partage dans l'équipe | Faible |
| Aucune sauvegarde de MySQL ni de MinIO | Base en conteneur sur un disque de la VM | Court terme : `mysqldump` planifié vers MinIO ou vers un stockage Azure, et instantanés du disque de données. Long terme : Azure Database for MySQL (sauvegardes automatiques, restauration à un instant donné), au prix d'une connexion TLS à ajouter dans `get_connection()` | Faible à moyen |
| Un seul serveur, pas de haute disponibilité | Coût | Exécuter la pipeline en tâche planifiée gérée (Azure Container Apps Jobs, qui remplacent le cron) et utiliser des services managés pour la base et le stockage : plus de VM à maintenir | Élevé |
| Image MinIO non officielle et figée | MinIO ne publie plus d'images (§4.6) | Construire notre propre image depuis les sources, ou passer à un service compatible S3 maintenu. Le code d'accès est isolé dans `src/storage/` et se change sans toucher au reste | Moyen |
| Port SSH ouvert à tous, MySQL et MinIO sans TLS | Les adresses des runners GitHub changent à chaque exécution | Runner GitHub auto-hébergé dans le réseau Azure, ou Azure Bastion, pour fermer le port 22 ; TLS sur MySQL et MinIO | Moyen |
| Mots de passe en clair dans le `.env` de la VM | Simplicité : ils viennent des secrets GitHub | Azure Key Vault lu au démarrage par la VM grâce à son identité managée : plus aucun secret sur le disque | Moyen |

### Exploitation et application

| Limite actuelle | Pourquoi aujourd'hui | Perspective | Effort |
|---|---|---|---|
| Les données grossissent sans limite (3 fichiers toutes les 5 minutes) | Démonstration du traitement en continu | Règle de cycle de vie MinIO (suppression des fichiers traités après N jours), purge ou partitionnement de la table `transactions`, fréquence du cron en variable | Faible |
| La pause du cron est annulée par chaque déploiement | Le CD réinstalle la ligne cron | Variable GitHub `CRON_ENABLED` lue par le CD | Faible |
| Pas de supervision ni d'alerte | Hors périmètre du sujet | Agent Azure Monitor sur la VM, alertes sur la mémoire, le disque et l'échec du cron ; métriques de la pipeline (lignes insérées et rejetées) | Moyen |
| Lignes rejetées visibles seulement dans `pipeline.log` | Choix d'un rapport en console | Table `rejected_rows` (fichier, ligne, colonne, raison) pour les analyser et les corriger | Faible |
| Image Docker lourde (outils de test inclus, `pandas` non utilisé) | Un seul `requirements.txt`, plus simple à gérer | Fichier de dépendances d'exécution séparé, construction de l'image en plusieurs étapes : téléchargement et déploiement plus rapides | Faible |
| Infrastructure non testée automatiquement au-delà de `validate` | Pas d'identifiants Azure dans la CI | Analyse statique sans identifiants (`tflint`, `checkov`) dès maintenant ; `terraform plan` en CI une fois l'OIDC en place | Faible |

## Documentation

| Document | Contenu |
|---|---|
| [`SPECIFICATIONS.md`](SPECIFICATIONS.md) | spécifications techniques et fonctionnelles, et décisions prises |
| [`sujet.md`](sujet.md) | sujet de la mise en situation |
| [`docs/terraform.md`](docs/terraform.md) | infrastructure as code : ressources, justifications, procédure |
| [`docs/simulation-panne.md`](docs/simulation-panne.md) | simulation d'un échec de la pipeline détecté par la CI, puis corrigé |
| [`docs/captures/`](docs/captures/) | captures d'écran de la simulation de panne |
