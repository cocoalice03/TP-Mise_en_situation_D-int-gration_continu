link : https://nowledgeable.com/student/courses/2414/project/8a4c6f48-c328-437f-b860-f2fee7d0ca71

Mise en situation D'intégration continu
Objectif
L’objectif de cette mise en situation est d’utiliser les outils d’intégration continue (CI) afin de s’assurer de la qualité et de la fiabilité d’une pipeline data.

Pour cela, vous devrez déployer l’ensemble des outils nécessaires à une pipeline data allant de la génération de données au format CSV jusqu’à leur insertion dans une base de données relationnelle.

Le sujet est découpé en plusieurs niveaux de difficulté.

Niveau 1 — Pipeline Data locale
1. Génération des données CSV
Créer un script permettant de générer plusieurs fichiers CSV contenant chacun 5 à 10 transactions financières.

Les transactions devront respecter le format suivant :

Colonne	Description
datetime_transaction	Date et heure de la transaction
iban_origine	IBAN de l’émetteur
pays_source	Pays de l’émetteur
banque_source	Banque de l’émetteur
iban_destinataire	IBAN du destinataire
pays_destinataire	Pays du destinataire
montant	Montant de la transaction
Les données ne devront pas être totalement aléatoires afin de rendre la pipeline facilement testable.

Vous devrez notamment prévoir des données permettant de vérifier les différents traitements demandés dans la suite du projet.

2. Chargement et traitement des données
Créer un script ou une librairie Python permettant de charger les fichiers CSV et d’effectuer les traitements suivants :

calculer la somme des montants envoyés par iban_origine ;
calculer la somme des montants envoyés par banque_source ;
calculer la somme des montants reçus par iban_destinataire ;
ajouter un flag à une transaction lorsque son montant est supérieur à 5000.
Contraintes
Les fonctions de chargement des données devront être séparées des fonctions de traitement des données.

Les fonctions de traitement devront être pures.

Une fonction pure :

ne modifie pas les données reçues en entrée ;
ne dépend pas d’un état externe ;
produit toujours le même résultat pour les mêmes données d’entrée.
3. Base de données relationnelle
Concevoir une base de données relationnelle permettant d’accueillir les résultats des traitements.

Mettre à jour le projet afin d’ajouter une fonction permettant d’insérer les données traitées dans cette base de données.

Le choix du système de gestion de base de données est libre.

4. Pipeline complète
Mettre en place une pipeline permettant automatiquement de :

générer les fichiers CSV ;
lancer le script de chargement et de traitement ;
mettre en place la base de données relationnelle ;
insérer les données traitées dans la base.
L’ensemble de ces étapes devra pouvoir être exécuté automatiquement.

5. Tests d’intégration automatiques
Mettre en place un ou plusieurs tests d’intégration automatiques permettant de vérifier que :

les données sont bien insérées dans la base ;
les valeurs enregistrées sont correctes ;
les différents traitements produisent les résultats attendus ;
les flags sont correctement positionnés.
Ces tests devront pouvoir être exécutés automatiquement dans la pipeline CI.

6. Simulation d’un échec de pipeline
À l’aide de captures d’écran, présenter un scénario dans lequel la pipeline échoue.

L’échec peut par exemple provenir :

d’un bug dans la génération des données ;
d’un fichier CSV invalide ;
d’une erreur dans le traitement ;
d’une donnée ne respectant pas le format attendu ;
d’un test d’intégration qui échoue.
Vous devrez présenter :

la cause du problème ;
l’échec de la pipeline ;
le message d’erreur obtenu ;
la correction apportée ;
la réussite de la pipeline après correction.
7. Retry lors de l’insertion en base
Simuler un problème temporaire lors de l’insertion des données dans la base.

Mettre en place un mécanisme de retry permettant de réessayer automatiquement l’insertion en cas d’échec.

Le mécanisme devra permettre de :

détecter l’échec ;
attendre avant une nouvelle tentative ;
effectuer plusieurs tentatives ;
définir un nombre maximal de tentatives ;
arrêter la pipeline si le nombre maximal de tentatives est dépassé ;
afficher clairement les erreurs rencontrées.
Remarque importante — Éviter les doublons
Vous devrez absolument éviter de traiter deux fois le même fichier CSV, y compris lorsqu’un mécanisme de retry est déclenché.

Vous devrez donc mettre en place un mécanisme permettant d’identifier les fichiers déjà traités.

Vous pouvez par exemple utiliser :

le nom du fichier ;
un hash du contenu du fichier ;
un identifiant unique ;
une table processed_files dans la base de données.
Votre solution devra garantir qu’un fichier déjà traité avec succès ne soit pas retraité.

Niveau 2 — Stockage S3
1. Stockage des fichiers dans un service S3
Les fichiers CSV ne devront désormais plus être récupérés directement depuis le système de fichiers local du projet.

Ils devront être stockés dans un service compatible S3 (Simple Storage Service).

Afin de ne pas utiliser directement le service S3 d’un fournisseur cloud dans la pipeline, vous utiliserez un service S3 local tel que :

Garage ;
SeaweedFS ;
RustFS ;
ou toute autre alternative compatible avec le protocole S3.
2. Upload automatique dans le S3
Modifier la pipeline afin que les fichiers CSV générés soient automatiquement envoyés dans le stockage S3.

Le service S3 devra être lancé au début de la pipeline.

La pipeline devra notamment :

démarrer le service S3 ;
créer/configurer le bucket nécessaire ;
générer les fichiers CSV ;
envoyer les fichiers dans le bucket ;
vérifier que les fichiers sont présents dans le stockage.
3. Lecture des données depuis le S3
Modifier le système de traitement afin que les fichiers CSV soient récupérés depuis le stockage S3.

Le traitement ne devra plus dépendre directement du système de fichiers local pour récupérer les fichiers à traiter.

Le flux devra désormais être :

S3
 |
 v
Récupération du fichier CSV
 |
 v
Chargement des données
 |
 v
Traitement
 |
 v
Base de données
Le mécanisme permettant d’éviter le double traitement d’un même fichier devra continuer à fonctionner.

4. Retry lors de la récupération depuis le S3
Simuler un problème lors de la récupération d’un fichier depuis le S3.

Par exemple :

service S3 temporairement indisponible ;
erreur réseau ;
timeout ;
fichier temporairement inaccessible.
Mettre en place un mécanisme de retry permettant de réessayer automatiquement la récupération du fichier.

Le système devra :

détecter l’échec de récupération ;
afficher l’erreur rencontrée ;
attendre avant une nouvelle tentative ;
effectuer plusieurs tentatives ;
définir un nombre maximal de tentatives ;
arrêter proprement le traitement si le fichier reste inaccessible.
Niveau 3 — Amélioration de la pipeline
Pour ce niveau, vous devrez implémenter au moins deux améliorations parmi les propositions suivantes.

Option 1 — Pipeline CD et déploiement
Mettre en place une pipeline de Continuous Deployment (CD) permettant de déployer automatiquement l’environnement de production.

Le déploiement pourra être réalisé :

sur une machine virtuelle ;
ou sur un cluster Kubernetes.
L’environnement devra être déployé à l’aide de conteneurs Docker.

Il devra notamment contenir :

le service S3 ;
la base de données relationnelle ;
le système de traitement des données.
Vous devrez également mettre en place un mécanisme permettant de lancer régulièrement le traitement afin de détecter et traiter les nouvelles données disponibles.

Vous pouvez par exemple utiliser :

un Cron ;
un CronJob Kubernetes ;
un scheduler ;
ou tout autre mécanisme pertinent.
Option 2 — Extraction de transactions depuis des images avec OCR
Faire évoluer la pipeline afin de pouvoir traiter des transactions financières contenues dans des images.

Vous devrez utiliser un système OCR (Optical Character Recognition) afin d’extraire les informations présentes dans les images.

Les informations extraites devront ensuite être transformées afin de pouvoir être intégrées au même flux de traitement que les données CSV.

Exemple :

Image
 |
 v
OCR
 |
 v
Extraction des informations
 |
 v
Validation / Transformation
 |
 v
Pipeline Data
 |
 v
Base de données
Option 3 — Extraction depuis du texte avec un SLM
Faire évoluer la pipeline afin de pouvoir extraire des informations de transactions financières contenues dans du texte brut.

Vous devrez utiliser un SLM (Small Language Model) permettant d’identifier et d’extraire les informations nécessaires.

Par exemple, à partir du texte :

Le 12 septembre à 14h30, le compte FR761234567890 a envoyé
6200 € vers le compte DE987654321 appartenant à une banque allemande.
Le système devra être capable d’extraire les informations pertinentes et de les transformer dans un format exploitable par la pipeline.

Le résultat devra ensuite rejoindre le même flux de traitement que les données provenant des fichiers CSV.

Option 4 — Infrastructure as Code avec Terraform / OpenTofu
Utiliser Terraform ou OpenTofu afin de déployer automatiquement les ressources nécessaires à l’environnement de production dans le cloud.

Selon votre architecture, vous pourrez notamment déployer :

un stockage S3 ;
une base de données ;
une machine virtuelle ;
un cluster Kubernetes managé ;
le réseau nécessaire ;
les différentes ressources nécessaires au fonctionnement de votre pipeline.
L’infrastructure devra pouvoir être créée automatiquement à partir du code présent dans votre dépôt.

Résultat attendu
À la fin du projet, vous devrez disposer d’une pipeline data automatisée permettant au minimum de réaliser le flux suivant :

Source de données
       |
       v
CSV / S3
       |
       v
Chargement
       |
       v
Validation
       |
       v
Traitement
       |
       v
Base de données
Selon les améliorations choisies au niveau 3, cette architecture pourra être enrichie avec :

CSV ---------|
             |
Images -> OCR|----> Traitement ----> Base de données
             |
Texte -> SLM-|
L’ensemble du projet devra être intégré à une démarche CI/CD, avec des tests permettant de détecter automatiquement les erreurs et de garantir la qualité des données traitées.