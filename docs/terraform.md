# Infrastructure as Code avec Terraform (Azure)

Ce document explique ce que Terraform déploie, pourquoi ces choix ont été faits, et comment créer l'infrastructure de production à partir du code du dépôt (`terraform/`).

## Répartition des rôles

| Outil | Responsabilité |
|---|---|
| **Terraform** (`terraform/`) | L'**infrastructure** : groupe de ressources, réseau, pare-feu, IP publique, machine virtuelle avec Docker installé, disque de données. |
| **CD** (`.github/workflows/cd.yml`) | L'**application** : copie de `docker-compose.yml` et `run-pipeline.sh`, écriture du `.env`, récupération de l'image, démarrage de MySQL et MinIO, première exécution, cron. |

Chaque outil fait ce qu'il fait le mieux. Terraform ne manipule **aucun mot de passe de l'application** : son fichier d'état ne contient donc aucun secret applicatif. Le CD, déjà éprouvé sur la VM précédente, est réutilisé presque tel quel (seule la connexion passe du mot de passe à la clé SSH).

```
                     Azure : groupe de ressources rg-transactions-dk
 ┌──────────────────────────────────────────────────────────────────────────┐
 │ Réseau virtuel 10.0.0.0/16 ─ sous-réseau 10.0.1.0/24 ─ pare-feu (NSG)      │
 │                                                                            │
 │   IP publique statique ──► VM Ubuntu 24.04 (B2s, clé SSH, Docker)          │
 │                              ├─ disque système 30 Go                       │
 │                              └─ disque de données 32 Go → /var/lib/docker  │
 │                                   (volumes MySQL et MinIO)                 │
 └──────────────────────────────────────────────────────────────────────────┘
        ▲ terraform apply (depuis un poste, az login)        ▲ CD (SSH, clé)
```

## Ce qui est déployé, et pourquoi

| Proposition du sujet | Décision | Justification |
|---|---|---|
| **Machine virtuelle** | **Déployée** : Ubuntu 24.04 LTS, taille `Standard_B2s` (2 vCPU, 4 Go), connexion par clé SSH uniquement, Docker installé au premier démarrage (cloud-init). | La VM d'1 Go utilisée avant s'est montrée saturée (SSH bloqué, MySQL jamais sain) : 4 Go laissent de la marge à MySQL 8.4, MinIO et Docker. cloud-init rend la VM prête au déploiement sans aucune action manuelle. La taille est une variable. |
| **Réseau** | **Déployé** : réseau virtuel, sous-réseau, groupe de sécurité réseau (pare-feu), IP publique statique, carte réseau. | Le pare-feu n'ouvre que le **port 22**, indispensable au CD dont les adresses GitHub changent (la clé SSH est obligatoire). Les ports 3306, 9000 et 9001 ne s'ouvrent qu'aux adresses listées dans `admin_cidrs` (aucune par défaut). L'IP statique garde la même adresse (secret `SSH_HOST`) même si la VM redémarre. |
| **Stockage S3** | **MinIO en conteneur sur la VM**, ses données sur le disque géré créé par Terraform. | Azure n'a pas de service S3 : Blob Storage n'utilise pas l'API S3, alors que le code (boto3) et la CI reposent sur S3. Garder MinIO : même code en développement, en CI et en production, aucune réécriture. |
| **Base de données** | **MySQL en conteneur sur la VM**, données sur le même disque géré. | Pas de coût en plus de la VM, aucun changement de code (une base managée Azure impose TLS), identique au développement. Limite : pas de sauvegarde automatique. |
| **Disque de données** | **Déployé** : disque géré de 32 Go monté sur `/var/lib/docker`. | Les volumes Docker (base MySQL, fichiers MinIO) sont sur une ressource séparée de la VM : on peut recréer ou redimensionner la VM sans perdre les données. |
| **Cluster Kubernetes managé** | **Non déployé.** | Coût (AKS consomme vite le crédit étudiant) et complexité disproportionnés pour un traitement par lots lancé toutes les 5 minutes. Docker Compose et cron suffisent (spec §6). |
| **Registre d'images** | **Non déployé** : Docker Hub conservé. | Déjà en place et gratuit. Un Azure Container Registry ajouterait un coût et des identifiants. |
| **Coffre de secrets** (Key Vault) | **Non déployé.** | Les secrets restent dans GitHub et sont écrits dans le `.env` de la VM par le CD. Un Key Vault demanderait des droits que le compte de l'école ne donne pas forcément. |
| **État Terraform** | **Fichier local** `terraform/terraform.tfstate`, jamais commité. | Un état distant dans Azure exigerait un compte de stockage créé **avant** `terraform init`, donc une configuration à part : complexité inutile si une seule personne lance `apply`. Règle d'équipe : une seule personne applique, et elle conserve ce fichier. |
| **Exécution** | **Depuis un poste**, avec `az login`. GitHub Actions vérifie le code (`terraform.yml`). | Le compte Azure de l'école ne permet pas de créer l'identité d'application dont GitHub Actions aurait besoin pour un `apply`. Le code ne dépend pas de ce choix : avec une telle identité, il pourrait être appliqué depuis GitHub avec les variables `ARM_*`, sans réécriture. |

## Fichiers

| Fichier | Contenu |
|---|---|
| `terraform/main.tf` | Version de Terraform, provider `azurerm` (`~> 4.0`) et toutes les ressources. |
| `terraform/variables.tf` | Entrées : abonnement, région, taille de VM, utilisateur, clé publique, taille du disque, adresses autorisées. |
| `terraform/outputs.tf` | Sorties : IP publique, utilisateur, commande SSH, URL de la console MinIO. |
| `terraform/cloud-init.yaml.tftpl` | Premier démarrage : montage du disque de données, installation de Docker. |
| `terraform/terraform.tfvars.example` | Modèle des valeurs à fournir (copié en `terraform.tfvars`, ignoré par git). |
| `terraform/.terraform.lock.hcl` | Version exacte du provider, pour que tout le monde utilise la même. |
| `.github/workflows/terraform.yml` | Vérification automatique : `terraform fmt -check` et `terraform validate`. |

## Créer l'infrastructure

Les commandes sont pour Git Bash. Les équivalents PowerShell sont indiqués quand ils diffèrent.

### 1. Installer les outils (une fois)

```powershell
winget install Microsoft.AzureCLI
winget install Hashicorp.Terraform
```

Rouvrez le terminal, puis connectez-vous à Azure et vérifiez l'abonnement :

```bash
az login
az account show --query "{nom:name, id:id}" -o table
```

### 2. Créer la clé SSH du déploiement (une fois)

```bash
ssh-keygen -t ed25519 -f ~/.ssh/transactions_deploy -C transactions-deploy -N ""
```

- La **clé publique** (`~/.ssh/transactions_deploy.pub`) va dans `terraform.tfvars`.
- La **clé privée** (`~/.ssh/transactions_deploy`) devient le secret GitHub `SSH_PRIVATE_KEY` (étape 5). Ne la commitez jamais.

### 3. Renseigner les valeurs

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Dans `terraform.tfvars`, mettez votre `subscription_id` (`az account show --query id -o tsv`) et le contenu de la clé publique (`cat ~/.ssh/transactions_deploy.pub`).

### 4. Créer l'infrastructure

```bash
terraform init
terraform plan      # doit annoncer 10 ressources à créer
terraform apply     # répondre "yes"
```

Puis attendez la fin du premier démarrage (installation de Docker, quelques minutes) :

```bash
ssh -i ~/.ssh/transactions_deploy azureuser@$(terraform output -raw public_ip) "cloud-init status --wait && docker compose version && df -h /var/lib/docker"
```

Attendu : `status: done`, la version de Docker Compose, et un disque d'environ 32 Go monté sur `/var/lib/docker`.

### 5. Brancher le CD sur la nouvelle VM

```bash
gh secret set SSH_HOST --body "$(terraform output -raw public_ip)"
gh secret set SSH_USER --body "$(terraform output -raw admin_username)"
gh secret set SSH_PRIVATE_KEY < ~/.ssh/transactions_deploy
gh secret delete SSH_PASSWORD
```

En PowerShell, pour la clé privée : `Get-Content $HOME\.ssh\transactions_deploy -Raw | gh secret set SSH_PRIVATE_KEY`.

### 6. Déployer l'application

Dans GitHub : onglet **Actions**, workflow **CD**, **Run workflow** sur `main`. Le CD copie le compose, écrit le `.env`, démarre MySQL et MinIO, lance une première exécution et installe le cron.

Vérification sur la VM :

```bash
ssh -i ~/.ssh/transactions_deploy azureuser@$(terraform output -raw public_ip)
cd ~/transactions-app && docker compose ps && crontab -l
```

### 7. Arrêter l'ancienne VM du prof

Le CD ne déploie plus sur l'ancienne VM, mais son cron continue de tourner. Sur l'ancienne VM : `crontab -e` (retirer la ligne `# transactions-pipeline`) puis `cd ~/transactions-app && docker compose down`.

## Coûts et arrêt

| Action | Commande |
|---|---|
| Éteindre la VM (plus de frais de calcul ; disques et IP restent facturés) | `az vm deallocate -g rg-transactions-dk -n vm-transactions-dk` |
| Rallumer la VM | `az vm start -g rg-transactions-dk -n vm-transactions-dk` |
| Tout supprimer (VM, disques et données compris) | `terraform destroy` |

`Standard_B2s` coûte de l'ordre de 30 à 40 € par mois en marche continue, plus le disque et l'IP. Sur un crédit étudiant, éteignez la VM quand vous ne présentez pas et faites `terraform destroy` après le rendu.

## En cas de problème

| Symptôme | Cause probable | Solution |
|---|---|---|
| `apply` refusé avec `RequestDisallowedByAzure` (« best available regions ») | Région non autorisée : Azure for Students n'accepte que `germanywestcentral`, `denmarkeast`, `belgiumcentral`, `switzerlandnorth` et `austriaeast` | Garder `location = "denmarkeast"` (défaut) : c'est la seule de ces régions qui propose `Standard_B2s` à cet abonnement. Vérifier avec `az vm list-skus -l <région> --size Standard_B2 -o table` |
| Erreurs `404 ResourceNotFound` ou `already exists` aléatoires sur des ressources qui existent | Groupe de ressources supprimé puis recréé sous le **même nom** dans une autre région : Azure route encore certaines requêtes vers l'ancienne région | Utiliser un nom neuf (variable `prefix`) ; c'est pourquoi le groupe s'appelle `rg-transactions-dk` |
| Erreur d'enregistrement d'un fournisseur de ressources (`MissingSubscriptionRegistration`) | Fournisseur Azure non enregistré dans l'abonnement | `az provider register --namespace Microsoft.Compute` (idem `Microsoft.Network`) puis relancer `apply` |
| `docker: command not found` sur la VM | cloud-init pas terminé ou en échec | `cloud-init status --wait`, puis lire `/var/log/cloud-init-output.log` |
| Le CD échoue à la connexion SSH | Secrets pas à jour | Vérifier `SSH_HOST`, `SSH_USER` (`azureuser`) et `SSH_PRIVATE_KEY` (clé privée complète, lignes `BEGIN` et `END` comprises) |
| `terraform.tfstate` perdu | État local supprimé | Terraform ne connaît plus les ressources : les supprimer dans le portail Azure (groupe `rg-transactions-dk`) ou les réimporter avec `terraform import` |

## Limites assumées

- Pas de base managée ni de sauvegarde automatique : un instantané du disque de données peut être pris à la main dans Azure.
- Pas d'exécution de `apply` par GitHub Actions, faute de droits sur le compte de l'école ; seule la vérification du code est automatisée.
- État local : une seule personne de l'équipe applique les changements d'infrastructure.
