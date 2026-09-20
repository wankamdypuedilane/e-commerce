# Sprint 9 — Conteneurisation

**Période :** 20/09/2026, 12h26 → 16h32
**Commits :** 6 (`3771aaf`, `12b4201`, `2f70d6b`, `7d99c1a`, `ddd65ed`, `c87eaae`)
**Issues fermées :** #9, #10, #11, #12, #13, #23, #24 — #14 traitée en fin de sprint
**Documents produits :** `docs/AUDIT.md`, `docs/ARCHITECTURE.md`, `docs/MODELE-DONNEES.md`, `docs/HISTORIQUE.md`, `docs/adr/001-conteneurisation.md`, `docs/adr/003-monolithe-modulaire.md`

---

## 1. Objectif du sprint

Rendre le déploiement reproductible.

Le sprint s'est ouvert sur un audit du dépôt, qui a servi de point de départ aux issues. L'audit a établi que le serveur créé par `bootstrap.sh` n'était pas celui que `deploy.yml` savait mettre à jour : service `ecom` contre `dilane-shop`, virtualenv `Ecom/` contre `.venv/`, et trois chemins projet différents selon le fichier consulté.

L'objectif retenu a donc été de remplacer la chaîne « script d'installation sur machine vierge + déploiement SSH » par une image Docker, et de basculer définitivement sur PostgreSQL.

---

## 2. Issues traitées

| # | Intitulé | Résultat |
|---|---|---|
| 9 | Écrire le Dockerfile de l'application Django | **Fermée.** Critères remplis sauf un (voir ci-dessous). |
| 10 | Écrire le docker-compose avec PostgreSQL | **Fermée.** Critères remplis sauf un (voir ci-dessous). |
| 11 | Migrer les données SQLite vers PostgreSQL | **Fermée.** |
| 12 | Externaliser la configuration selon les 12 facteurs | **Fermée avec deux critères non réalisés.** |
| 13 | Retirer db.sqlite3 de l'historique Git | **Fermée avec un critère non réalisé.** |
| 14 | ADR-003 : monolithe modulaire plutôt que microservices | **Traitée en fin de sprint**, encore ouverte sur GitHub au moment de la rédaction. |
| 23 | Neutraliser le job de déploiement EC2 obsolète | **Fermée.** |
| 24 | Servir les fichiers statiques avec WhiteNoise | **Fermée.** |

### Détail

**#9 — Dockerfile.** `Dockerfile` en deux étages sur `python:3.13-slim`. L'étage `builder` installe `build-essential` et `libpq-dev` puis construit un virtualenv dans `/opt/venv` ; l'étage `runtime` n'installe que `libpq5`, copie le virtualenv, crée l'utilisateur système `django`, copie le code avec `--chown=django:django`, exécute `collectstatic` et bascule sur `USER django`. `CMD` lance Gunicorn avec 3 workers et un timeout de 60 s, paramètres repris de `bootstrap.sh`. `.dockerignore` exclut `.git/`, `.venv/`, `__pycache__/`, `.env`, `*.sqlite3`, `staticfiles/`, `media/`, `docs/`, `infra/` et `scripts/`. Image mesurée : **233 Mo** (`docker images`, 20/09/2026) ; le message du commit `12b4201` annonce 230 Mo.

Le critère « dette 4.8 — répertoire `Templates` avec une majuscule » **n'est pas réalisé** : `Templates/` existe toujours et `ecommerce/settings.py:24` continue de le référencer.

**#10 — docker-compose.** Deux services. `db` en `postgres:17-alpine`, volume nommé `postgres_data`, `healthcheck` par `pg_isready` toutes les 5 s avec 5 tentatives. `web` construit depuis le `Dockerfile`, étiqueté `dilane-shop:0.1.0`, configuration lue par `env_file: .env`, volume nommé `media_files` sur `/app/media`, et `depends_on: db: condition: service_healthy`. Aucune valeur n'est écrite en dur : les variables `POSTGRES_*` du service `db` sont interpolées depuis l'environnement.

Le critère « `docker compose up` suffit à obtenir un site fonctionnel » **n'est pas réalisé en l'état** : le `CMD` lance directement Gunicorn, aucun `command` ni point d'entrée n'exécute `migrate`. Sur un volume `postgres_data` neuf, les tables n'existent pas et la migration doit être lancée à la main. Un job de migration distinct est prévu au Sprint 10 (issue #19).

**#11 — Migration des données.** `fixtures/demo-catalogue.json`, 367 lignes : 5 catégories et 25 produits exportés depuis l'ancienne base SQLite. Les commandes de test et les comptes utilisateurs ont été délibérément exclus. N'importe quel environnement se peuple désormais par un `loaddata` après `docker compose up`. `.env.example` bascule sur `DB_ENGINE=postgres`.

**#12 — Configuration.** `DJANGO_SECRET_KEY` n'a plus de valeur de repli : `settings.py` lève `ImproperlyConfigured` avec un message explicite si la variable est absente. `DJANGO_DEBUG` vaut désormais `False` par défaut, au lieu de `True`. `.env.example` documente les variables obligatoires, la commande de génération d'une clé secrète, et précise que `DB_HOST=db` est un nom de service Docker et non une adresse IP.

Deux critères **ne sont pas réalisés** : `CSRF_TRUSTED_ORIGINS` (dette 4.6) et la configuration `LOGGING` explicite vers la sortie standard (dette 4.5) sont absents de `settings.py`. L'issue a néanmoins été fermée.

**#13 — Historique Git.** L'historique a été réécrit : `git log --all -- db.sqlite3` ne retourne plus aucun commit, et tous les identifiants de commits antérieurs ont changé (« Fix mes commandes template formatting » est passé de `890a472` à `ed22a22`). Le fichier est retiré de l'index et ajouté à `.gitignore`, qui accueille aussi `*.sqlite3`, `staticfiles/`, `media/` et `.venv/`.

Le critère « les 17 fichiers `.pyc` retirés également (dette 3.7) » **n'est pas réalisé** : `git ls-files` en liste toujours 17, tous en `cpython-312`. La réécriture n'a porté que sur `db.sqlite3`.

**#14 — ADR-003.** Le document `docs/adr/003-monolithe-modulaire.md` a été rédigé en fin de sprint. Les six apps cibles y sont nommées, l'alternative microservices y est chiffrée en coûts, les trois critères de révision et le lien avec l'API REST future y figurent. L'issue est **encore ouverte sur GitHub** et reste à fermer.

**#23 — Job EC2.** Le job `deploy` visait une instance supprimée sur un compte AWS fermé et échouait à chaque poussée. Il est neutralisé par `if: false` accompagné d'un commentaire, et non supprimé : il sert de référence jusqu'au déploiement Kubernetes du Sprint 10. Le job `ci` reste actif. Une étape `manage.py check --deploy --fail-level ERROR` y a été ajoutée, avec ses variables d'environnement propres.

**#24 — WhiteNoise.** `whitenoise==6.11.0` ajouté à `requirements.txt`. Middleware inséré juste après `SecurityMiddleware`. `STORAGES` configuré avec `whitenoise.storage.CompressedManifestStaticFilesStorage` pour le stockage des fichiers statiques, `FileSystemStorage` restant le stockage par défaut.

---

## 3. Décisions techniques prises en cours de route

### Build multi-stage plutôt qu'un seul étage

Un étage unique aurait laissé `build-essential` et `libpq-dev` dans l'image d'exécution. Ces paquets ne servent qu'à compiler d'éventuelles dépendances natives au moment de l'installation ; les conserver en exécution augmente la taille de l'image et la surface exposée sans contrepartie. La séparation permet de ne copier que `/opt/venv` et de n'installer que la bibliothèque cliente `libpq5` dans l'étage final.

### Healthcheck plutôt qu'un script d'attente

Le besoin : empêcher le service `web` de démarrer avant que PostgreSQL n'accepte les connexions. Deux approches étaient possibles.

La première, un script d'attente dans le conteneur applicatif — boucle sur un test de port avant de lancer Gunicorn. Elle place la connaissance de la dépendance dans l'image de l'application, ajoute un script à maintenir, et confond disponibilité du port TCP et disponibilité du serveur PostgreSQL.

La seconde, retenue : un `healthcheck` déclaré sur le service `db`, fondé sur `pg_isready -U <user> -d <base>`, associé à `depends_on: condition: service_healthy` côté `web`. La dépendance est déclarée là où elle est vraie, l'image applicative reste ignorante de son ordonnancement, et le test porte sur la capacité réelle du serveur à répondre plutôt que sur l'ouverture d'un port. C'est aussi la formulation la plus proche des probes Kubernetes prévues au Sprint 10 (issue #20).

### WhiteNoise plutôt qu'un Nginx en conteneur annexe

Reproduire l'architecture EC2 aurait signifié ajouter un service `nginx` devant `web`, avec sa configuration, son volume partagé pour `staticfiles/` et son cycle de mise à jour.

WhiteNoise sert les fichiers statiques depuis Gunicorn : une dépendance Python épinglée, un middleware, un réglage `STORAGES`. Le comportement est identique en local, sous Docker et dans un cluster — ce qui évite qu'un défaut d'affichage n'apparaisse que dans un environnement. Le raisonnement est consigné dans l'issue #24 et dans le message du commit `7d99c1a`.

### `DB_HOST` par nom de service

`DB_HOST=db` au lieu d'une adresse IP. Docker résout le nom du service via son DNS interne. L'adresse attribuée au conteneur PostgreSQL change à chaque recréation ; le nom, lui, est stable et lisible. La même variable fonctionnera sans changement avec un Service Kubernetes, dont la résolution repose aussi sur un nom.

---

## 4. Ce qui a surpris

### L'erreur SQLite dans le conteneur a rendu concret le caractère sans état d'un conteneur

`.dockerignore` exclut `db.sqlite3` et `*.sqlite3` — l'image ne contient donc aucune base. Avec `DB_ENGINE=sqlite`, Django crée un fichier vide dans la couche inscriptible du conteneur : la base repart de zéro, et tout ce qui y est écrit disparaît à la suppression du conteneur.

Le caractère sans état d'un conteneur était connu comme principe. L'erreur l'a rendu opérationnel : elle a montré que la persistance ne vient pas du conteneur mais de ce qu'on lui attache — un volume nommé, ou un service distinct. C'est ce constat qui a transformé « PostgreSQL est recommandé en production » en « SQLite n'est pas une option », et qui a justifié le volume `postgres_data` pour la base et `media_files` pour les fichiers téléversés.

### L'audit a révélé que le pipeline CI/CD n'avait jamais réellement déployé

Le dépôt affichait un workflow de déploiement depuis le Sprint 4. La lecture croisée de `deploy.yml` et de `bootstrap.sh` a montré qu'ils décrivaient deux machines différentes : le `source .venv/bin/activate` ne pouvait pas aboutir sur un serveur où le virtualenv s'appelle `Ecom`, et le `systemctl restart dilane-shop` visait un service nommé `ecom`.

Le job échouait par ailleurs depuis la suppression de l'instance EC2. L'issue #23 note l'effet secondaire : un dépôt en échec permanent fait perdre le réflexe de surveiller la CI, et un véritable échec de test serait passé inaperçu. Le job `ci`, lui, réussissait en 19 secondes.

La conséquence sur la conduite du sprint : la conteneurisation n'a pas remplacé un déploiement automatisé fonctionnel, elle en a construit un pour la première fois.

### Le backend Manifest de WhiteNoise a validé l'intégrité des références statiques

`CompressedManifestStaticFilesStorage` calcule une empreinte du contenu de chaque fichier statique, renomme les fichiers en conséquence et construit un manifeste. Lors de `collectstatic`, toute référence `{% static %}` pointant vers un fichier absent du manifeste provoque l'échec de la commande.

`collectstatic` étant exécuté pendant la construction de l'image, une référence cassée aurait fait échouer le build. Le build a réussi : aucune référence statique du projet n'est cassée. Le choix avait été fait pour la mise en cache longue ; il a produit une vérification qu'aucun test n'effectuait.

---

## 5. Reporté

### Unifier la gestion des images produits

Le modèle `Product` porte deux champs d'image, hérités de la migration `0011` :

- `image` — `CharField(max_length=5000)`, URL externe, commenté « URL legacy » dans `shop/models.py:22` ;
- `image_file` — `ImageField(upload_to='products/')`, téléversement local.

La propriété `display_image_url` arbitre entre les deux : elle retourne `image_file.url` si un fichier existe, sinon `image`, sinon une chaîne vide. Les deux champs coexistent, aucune migration ne consolide l'un vers l'autre.

Le sujet devient concret avec la conteneurisation : les fichiers téléversés vivent désormais dans le volume nommé `media_files`, qui n'est pas répliqué entre plusieurs instances. Trancher entre les deux champs suppose de décider où les images sont stockées — volume partagé, ou stockage objet — décision qui relève du travail Kubernetes. Reporté après le Sprint 10.

Dette 4.4 de l'audit.

### Éléments non réalisés dont l'issue a été fermée

À reprendre, par ordre de numéro de dette :

| Dette | Élément | Issue d'origine |
|---|---|---|
| 3.7 | 17 fichiers `.pyc` toujours suivis par Git | #13 |
| 4.5 | Configuration `LOGGING` explicite vers la sortie standard | #12 |
| 4.6 | `CSRF_TRUSTED_ORIGINS` | #12 |
| 4.8 | Répertoire `Templates` à majuscule, toujours référencé | #9 |
| — | `migrate` non joué au démarrage de la pile Docker | #10, repris par #19 |

### Reporté au Sprint 10 par construction

- Registre d'images : la construction reste locale, l'image ne sort pas du poste.
- HTTPS : dette 1.6, reprise par l'issue #21 (Ingress et cert-manager).
- Remplacement du job `deploy` neutralisé par un déploiement Kubernetes.
- ADR-002 — Kubernetes plutôt qu'un serveur unique (issue #22).

### Rappel des échéances annoncées

- **Sprint 10** — Kubernetes : cluster kind, Deployment et Service, StatefulSet PostgreSQL, Secrets et ConfigMap, job de migration, probes, Ingress et HTTPS (issues #15 à #22).
- **Sprint 11** — Tests. Prérequis explicite du sprint suivant.
- **Sprint 12** — Découpage en six apps Django, conformément à l'[ADR-003](../adr/003-monolithe-modulaire.md).

---

## 6. État de la CI en fin de sprint

| Job | État |
|---|---|
| `ci` — installation, `manage.py check`, `manage.py test` | Actif sur chaque poussée |
| `ci` — `manage.py check --deploy --fail-level ERROR` | Ajouté ce sprint |
| `deploy` — SSH vers EC2 | Neutralisé par `if: false`, conservé comme référence |

Le job `ci` s'exécute sur `python-version: "3.12"`, alors que l'image et le poste de développement utilisent Python 3.13.5. L'écart de version relevé dans l'audit subsiste donc pour l'étape de test, bien que l'exécution soit désormais unifiée par l'image. Ce point n'était couvert par aucune issue du sprint.
