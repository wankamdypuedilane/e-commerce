# ADR-001 — Conteneurisation de l'application

## Statut

Accepté — 20/09/2026. Implémenté au Sprint 9 (issues #9, #10, #11, #12, #13, #23, #24).

---

## Contexte

Le déploiement reposait sur `infra/terraform/bootstrap.sh`, un script cloud-init de 200 lignes exécuté au démarrage d'une instance EC2. Il installait les paquets système, clonait le dépôt, créait un virtualenv, écrivait le `.env`, lançait les migrations, puis configurait Gunicorn et Nginx.

L'audit du 20/09/2026 (`docs/AUDIT.md`) a relevé les défauts suivants sur cette chaîne.

### Incohérences de nommage entre les deux moitiés du déploiement

`bootstrap.sh` et `.github/workflows/deploy.yml` ont été écrits à 14 heures d'intervalle, sans relecture croisée. Ils ne décrivent pas la même machine :

| Élément | `bootstrap.sh` (ce qui est créé) | `deploy.yml` (ce qui est attendu) |
|---|---|---|
| Service systemd | `ecom` | `dilane-shop` |
| Virtualenv | `Ecom/` | `.venv/` |
| Répertoire projet | `/home/ubuntu/e-commerce` | `/home/ubuntu/ecommerce` (documenté) |

Le script de déploiement s'exécute sous `set -e`. Le `source .venv/bin/activate` échouait donc avant `pip install`, `migrate` et `collectstatic`. Ces échecs se produisaient à l'intérieur d'une commande SSH, à des étapes variables selon l'état du serveur — d'où un pipeline qui pouvait migrer une base sans jamais recharger le code applicatif.

Les scripts `scripts/backup_postgres.sh` et `scripts/restore_postgres.sh` utilisaient un troisième chemin (`/home/ubuntu/ecommerce`), et sortaient en erreur « Missing env file » avec la tâche cron proposée dans `docs/ops-backup.md`.

### Écart de versions Python

Trois environnements, deux versions :

| Environnement | Version |
|---|---|
| CI GitHub Actions (`deploy.yml`) | 3.12 |
| `bootstrap.sh` (serveur EC2) | 3.12 |
| Poste de développement | 3.13.5 |

Les tests validaient donc un interpréteur différent de celui utilisé pour écrire le code.

### Propriété des fichiers

`bootstrap.sh` s'exécute en tant que `root` via cloud-init. Il exécutait `git clone`, la création du virtualenv, `pip install`, `migrate` et `collectstatic` sans changer d'utilisateur. Le seul `chown ubuntu:ubuntu` portait sur le fichier `.env`.

Le service Gunicorn tournait sous `User=ubuntu`. Le dépôt, le virtualenv, `staticfiles/`, `media/` et `db.sqlite3` appartenaient à `root`. En mode SQLite, l'application ne pouvait écrire ni dans la base ni dans `media/` ; le `git pull` du déploiement, exécuté sous l'utilisateur SSH, n'avait pas les droits d'écriture sur l'arborescence.

### Aucun superutilisateur créé

`bootstrap.sh` ne comportait pas d'étape `createsuperuser`. Le contrôle de santé de fin de script interrogeait `http://localhost/admin/`, une interface à laquelle personne ne pouvait se connecter après un déploiement neuf.

### Conséquence d'ensemble

Le serveur produit par Terraform n'était pas celui que le pipeline savait mettre à jour. Le déploiement n'était pas reproductible : sa réussite dépendait d'ajustements manuels non consignés.

---

## Décision

Conteneuriser l'application selon deux principes :

**1. Image Docker multi-stage.**

- Étage `builder` (`python:3.13-slim`) : installe `build-essential` et `libpq-dev`, crée un virtualenv dans `/opt/venv`, y installe les dépendances de `requirements.txt`.
- Étage `runtime` (`python:3.13-slim`) : installe la seule bibliothèque cliente `libpq5`, crée un utilisateur système `django`, copie `/opt/venv` depuis le `builder`, copie le code avec `--chown=django:django`, exécute `collectstatic`, puis bascule sur `USER django`.
- `CMD` lance Gunicorn avec les paramètres repris de `bootstrap.sh` : 3 workers, classe `sync`, timeout 60, journaux sur la sortie standard.
- `.dockerignore` exclut `.git/`, `.venv/`, `__pycache__/`, `.env`, `*.sqlite3`, `staticfiles/`, `media/`, ainsi que `docs/`, `infra/` et `scripts/`.

**2. PostgreSQL en service séparé.**

`docker-compose.yml` déclare deux services. `db` utilise `postgres:17-alpine`, avec un volume nommé `postgres_data` et un `healthcheck` fondé sur `pg_isready`. `web` est construit depuis le `Dockerfile`, lit sa configuration via `env_file: .env`, monte un volume nommé `media_files` sur `/app/media`, et déclare `depends_on: db: condition: service_healthy`.

`DB_HOST` vaut `db` — le nom du service, résolu par le DNS interne de Docker — et non une adresse IP.

Deux décisions complémentaires ont été prises dans le même sprint et font partie de cette architecture :

- **WhiteNoise** sert les fichiers statiques depuis Gunicorn (issue #24), avec le backend `CompressedManifestStaticFilesStorage`. Aucun Nginx n'est embarqué.
- **La configuration est lue exclusivement depuis l'environnement** (issue #12) : `DJANGO_SECRET_KEY` n'a plus de valeur de repli et l'application lève `ImproperlyConfigured` si elle est absente ; `DJANGO_DEBUG` vaut `False` par défaut.

---

## Alternatives considérées

### A. Corriger `bootstrap.sh` et `deploy.yml`

Aligner les noms de service, de virtualenv et de répertoire, ajouter un `chown` global, ajouter la création d'un superutilisateur, harmoniser les versions Python.

Écartée : cette correction traite les symptômes sans supprimer leur cause. Les trois noms auraient continué d'exister à trois endroits, et rien n'aurait empêché une nouvelle divergence. L'écart entre le poste de développement et le serveur serait resté entier.

### B. Image Docker à un seul étage

Un seul `FROM python:3.13-slim`, installation des dépendances et exécution dans la même image.

Écartée : `build-essential` et `libpq-dev` seraient restés dans l'image finale. Ces paquets ne servent qu'à la compilation éventuelle de dépendances et constituent une surface d'attaque inutile en exécution.

### C. Nginx en conteneur annexe pour les fichiers statiques

Reproduire l'architecture EC2 en ajoutant un service `nginx` devant `web`.

Écartée au profit de WhiteNoise : un service de moins à décrire, à surveiller et à mettre à jour, et un comportement identique en local, sous Docker et dans un cluster Kubernetes. Le raisonnement figure dans l'issue #24 et dans le message du commit `7d99c1a`.

### D. Conserver SQLite dans le conteneur

Écartée : voir la conséquence négative correspondante ci-dessous.

---

## Conséquences

### Positives

**Huit dettes de l'audit sont résolues par construction**, c'est-à-dire que le dispositif qui les produisait n'existe plus :

| Dette | Intitulé | Ce qui la supprime |
|---|---|---|
| 1.1 | Virtualenv et service systemd incohérents entre bootstrap et CI | L'image est l'artefact déployé. Il n'y a plus ni virtualenv nommé, ni service systemd, ni script d'installation à synchroniser. |
| 1.2 | `STRIPE_WEBHOOK_SECRET` jamais écrit dans le `.env` de production | `env_file: .env` transmet le fichier complet au conteneur. Il n'y a plus de liste de variables recopiée à la main dans un script. |
| 1.3 | Fichiers appartenant à `root`, service tournant en `ubuntu` | `COPY --chown=django:django` puis `USER django`. Le processus et les fichiers ont le même propriétaire, fixé dans le `Dockerfile`. |
| 1.4 | `db.sqlite3` versionnée avec comptes et commandes réels | Fichier retiré de l'index, ajouté à `.gitignore`, exclu par `.dockerignore`, et retiré de l'historique Git (issue #13). |
| 1.5 | `DEBUG` et `SECRET_KEY` avec valeurs par défaut permissives | `SECRET_KEY` sans repli, `DEBUG` à `False` par défaut (issue #12). |
| 2.10 | `check --deploy` exécuté après le redémarrage, absent de la CI | Ajouté au job `ci` de `deploy.yml` avec `--fail-level ERROR` (issue #23). |
| 5.3 | Trois chemins projet divergents | `WORKDIR /app`, valeur unique et fixée dans l'image. |
| 5.8 | Base de développement devenant base de production en mode SQLite | `DB_ENGINE=postgres` dans tous les environnements, et `*.sqlite3` exclu par `.dockerignore`. |

**Image de taille contenue sans outils de compilation.** L'image `dilane-shop:0.1.0` mesure 233 Mo (`docker images`, 20/09/2026 — le message du commit `12b4201` annonce 230 Mo). `build-essential` et `libpq-dev` restent dans l'étage `builder` et ne sont pas copiés ; seule la bibliothèque `libpq5` est présente en exécution.

**Processus non privilégié.** L'application tourne sous l'utilisateur système `django`, sans shell de connexion défini comme utilisateur interactif, créé par `groupadd --system` / `useradd --system`.

**Environnement d'exécution identique partout.** La même image, avec le même interpréteur Python 3.13 et les mêmes dépendances épinglées, s'exécute en local et en production. Cela supprime l'écart 3.12 / 3.13 décrit dans le contexte, *pour l'exécution*. Voir la réserve ci-dessous.

### Négatives

**Une couche d'abstraction supplémentaire.** Diagnostiquer un incident suppose désormais de distinguer ce qui relève de l'application, de l'image, du réseau Docker et des volumes. Les journaux ne sont plus dans des fichiers du serveur mais sur la sortie standard du conteneur. Cela ajoute un outillage à connaître (`docker compose logs`, `exec`, `inspect`) avant de pouvoir lire une erreur applicative.

**Temps de construction à chaque changement de dépendance.** `COPY requirements.txt` précède `COPY . .`, donc le cache de couches épargne la réinstallation des dépendances lors d'une simple modification de code. En revanche, toute modification de `requirements.txt` invalide cette couche et impose une réinstallation complète dans l'étage `builder`.

**Un registre d'images devient nécessaire pour déployer.** Tant que la construction est locale, l'image ne sort pas du poste. Un déploiement vers une machine distante ou un cluster suppose de publier l'image dans un registre, donc de gérer un compte, une authentification, une politique de nommage des versions et une purge des anciennes images. Ce besoin n'existait pas avec un `git pull` sur le serveur. Le point est ouvert jusqu'au Sprint 10.

**SQLite devient inutilisable.** Un conteneur est sans état : ce qui est écrit dans sa couche inscriptible disparaît à sa suppression, et `.dockerignore` exclut de toute façon `*.sqlite3` de l'image. Une base SQLite dans un conteneur serait recréée vide à chaque recréation. PostgreSQL devient donc obligatoire, y compris pour un lancement local : `docker compose up` démarre deux services au lieu d'un processus unique, et la base de démonstration doit être chargée par une fixture (`fixtures/demo-catalogue.json`, issue #11) plutôt que transportée par le dépôt.

### Réserves sur la portée

Trois limites sont constatées au moment de la rédaction et ne sont pas couvertes par cette décision :

- **La CI construit toujours sur Python 3.12.** `.github/workflows/deploy.yml` fixe `python-version: "3.12"` et exécute les tests sur le runner, pas dans l'image. L'écart de version décrit dans le contexte subsiste donc pour l'étape de test.
- **Les migrations ne sont pas jouées au démarrage.** Le `CMD` lance directement Gunicorn ; `docker-compose.yml` ne définit ni `command`, ni point d'entrée d'initialisation. Sur un volume `postgres_data` neuf, `migrate` doit être lancé explicitement. Un job de migration distinct est prévu au Sprint 10 (issue #19).
- **Aucun HTTPS.** WhiteNoise sert les fichiers statiques en HTTP ; la terminaison TLS est reportée à l'issue #21 (Ingress et cert-manager, Sprint 10). La dette 1.6 de l'audit reste ouverte.

---

## Liens

- Issues : #9 (Dockerfile), #10 (docker-compose), #11 (migration des données), #12 (configuration), #13 (historique Git), #23 (job EC2), #24 (WhiteNoise)
- Commits : `12b4201`, `2f70d6b`, `7d99c1a`, `ddd65ed`, `c87eaae`
- ADR-002 — Kubernetes plutôt qu'un serveur unique : à rédiger, issue #22, Sprint 10
- [ADR-003 — Monolithe modulaire plutôt que microservices](003-monolithe-modulaire.md)
- [docs/AUDIT.md](../AUDIT.md) — numérotation des dettes citées
- [docs/sprints/sprint-09-docker.md](../sprints/sprint-09-docker.md)
