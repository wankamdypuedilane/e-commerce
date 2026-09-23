# E-commerce Django

Application e-commerce développée avec Django, Stripe et Brevo, exécutée en conteneurs Docker avec PostgreSQL. Le projet couvre le catalogue produits, l’authentification, le checkout, la gestion de stock et les paiements.

Ce dépôt contient sa documentation dans [docs/](docs/) : architecture, modèle de données, audit, décisions d’architecture (ADR) et rétrospectives de sprint.

## Vue d’ensemble

Ce projet a été construit pour aller au-delà d’une simple application web:

- Django pour la logique métier et les pages du site
- Stripe pour les paiements
- Brevo pour les emails transactionnels
- Image Docker multi-stage pour l’exécution
- PostgreSQL en service séparé
- Gunicorn et WhiteNoise pour servir l’application et ses fichiers statiques
- Kubernetes pour l’orchestration : replicas, sondes de santé, mises à jour sans coupure
- GitHub Actions pour la CI/CD

## Fonctionnalités

- Catalogue et fiche produit
- Recherche produits via API interne
- Inscription, connexion, déconnexion et mot de passe oublié
- Checkout protégé par authentification
- Gestion des commandes et profil utilisateur
- Vérification du stock côté serveur
- Intégration Stripe pour les paiements
- Webhook Stripe
- Interface admin personnalisée
- Favicon et branding navigateur

## Stack technique

- Python 3.13
- Django 6.0.3
- PostgreSQL 17
- Docker et Docker Compose
- Kubernetes (kind en local, k3s visé en production)
- ingress-nginx et cert-manager pour l’exposition HTTPS
- Gunicorn (3 workers, timeout 60 s)
- WhiteNoise pour les fichiers statiques
- Stripe pour les paiements
- Brevo SMTP pour les emails transactionnels
- GitHub Actions pour l’intégration continue

## Prérequis

- Docker Engine et Docker Compose v2 (commande `docker compose`)
- Git
- Un compte Stripe pour tester les paiements (facultatif)
- Un compte Brevo pour activer les emails (facultatif)

Un virtualenv Python n’est plus nécessaire pour lancer le projet. Il reste utile pour du développement hors conteneur (autocomplétion de l’éditeur, exécution ponctuelle de `manage.py`) :

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Installation locale

```bash
git clone https://github.com/wankamdypuedilane/e-commerce.git
cd e-commerce
cp .env.example .env
```

Renseignez ensuite `DJANGO_SECRET_KEY` dans `.env`. Cette variable est **obligatoire** : sans elle, l’application lève `ImproperlyConfigured` et refuse de démarrer. Pour générer une valeur :

```bash
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Puis démarrez la pile :

```bash
docker compose up -d
```

## Configuration

Toute la configuration est lue depuis l’environnement. Le fichier `.env` à la racine est transmis au conteneur `web` par `env_file`, et sert aussi à Docker Compose pour renseigner le service `db`.

| Variable | Obligatoire | Défaut | Rôle |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | **Oui** | aucun | Clé de signature. L’application refuse de démarrer si elle est absente. |
| `DJANGO_DEBUG` | Non | `False` | Mode debug. Ne pas activer hors développement local. |
| `DJANGO_ALLOWED_HOSTS` | Non | `127.0.0.1,localhost` | Hôtes autorisés, séparés par des virgules. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Non | vide | Origines de confiance CSRF, schéma inclus. Nécessaire derrière un proxy en HTTPS. |
| `DJANGO_LOG_LEVEL` | Non | `INFO` | Niveau de journalisation vers la sortie standard. |
| `DB_ENGINE` | Non | `sqlite` | Doit valoir `postgres` avec Docker. |
| `DB_NAME` | **Oui** (pile Docker) | `ecommerce` | Nom de la base. Également lu par le service `db`. |
| `DB_USER` | **Oui** (pile Docker) | `postgres` | Utilisateur PostgreSQL. Également lu par le service `db`. |
| `DB_PASSWORD` | **Oui** (pile Docker) | vide | Mot de passe PostgreSQL. Également lu par le service `db`. |
| `DB_HOST` | Non | `127.0.0.1` | Vaut `db` en conteneur : c’est le nom du service Docker, pas une adresse IP. |
| `DB_PORT` | Non | `5432` | Port PostgreSQL. |
| `DB_CONN_MAX_AGE` | Non | `60` | Durée de réutilisation des connexions, en secondes. |
| `DB_SSLMODE` | Non | `prefer` | `disable` en local, le réseau Docker n’étant pas exposé. |
| `STRIPE_PUBLIC_KEY` | Non | vide | Sans elle, le paiement Stripe est inactif. |
| `STRIPE_SECRET_KEY` | Non | vide | Sans elle, le paiement Stripe est inactif. |
| `STRIPE_WEBHOOK_SECRET` | Non | vide | Sans elle, le webhook répond 400 et le stock n’est pas décrémenté. |
| `BREVO_SMTP_LOGIN` | Non | vide | Identifiant SMTP Brevo. |
| `BREVO_SMTP_KEY` | Non | vide | Clé SMTP Brevo. |
| `EMAIL_FROM` | Non | adresse codée | Expéditeur des emails transactionnels, à vérifier dans Brevo. |
| `TAX_RATE_PERCENT` | Non | `20` | Taux de TVA appliqué au checkout. |

Ne versionnez jamais le fichier `.env` : il est listé dans `.gitignore` et exclu de l’image par `.dockerignore`.

## Lancer le projet

Démarrez les deux services. Le service `web` attend que `db` réponde à son healthcheck avant de démarrer :

```bash
docker compose up -d
```

Les migrations ne sont pas jouées automatiquement. Sur une base neuve, exécutez-les :

```bash
docker compose exec web python manage.py migrate
```

Chargez le catalogue de démonstration (5 catégories, 25 produits) :

```bash
docker compose exec web python manage.py loaddata fixtures/demo-catalogue.json
```

Créez un compte administrateur :

```bash
docker compose exec web python manage.py createsuperuser
```

Puis ouvre:

- http://127.0.0.1:8000/
- http://127.0.0.1:8000/connexion/
- http://127.0.0.1:8000/admin/

Pour consulter les journaux ou arrêter la pile :

```bash
docker compose logs -f web
docker compose down
```

`docker compose down` conserve les volumes `postgres_data` et `media_files`. Ajoutez `-v` pour les supprimer également.

## Tests

Les tests s'exécutent dans l'image de test, qui ajoute `coverage` à l'image de production :

```bash
docker compose run --rm tests sh -c "coverage run manage.py test && coverage report"
```

La couverture est mesurée avec les branches : un `if` n'est couvert que si ses deux issues sont testées. Le seuil minimal, défini dans `.coveragerc`, fonctionne comme un cliquet : fixé juste sous le niveau atteint, il empêche toute baisse et sera relevé à mesure que les tests progressent.

## Déploiement Kubernetes (local, kind)

Les manifestes du répertoire [k8s/](k8s/) déploient la même image que Docker Compose sur un cluster Kubernetes. Le cluster de référence est un cluster local [kind](https://kind.sigs.k8s.io/) à trois nœuds. Le choix de Kubernetes et ses contreparties sont documentés dans [docs/adr/002-kubernetes.md](docs/adr/002-kubernetes.md).

### Prérequis

- Docker Engine (kind exécute les nœuds du cluster comme des conteneurs)
- `kubectl` — version utilisée : v1.37.0
- `kind` — version utilisée : v0.33.0

```bash
kubectl version --client
kind version
```

### 1. Créer le cluster

```bash
kind create cluster --config k8s/kind-cluster.yaml
```

Le cluster s'appelle `dilane-shop` et compte un nœud de contrôle — qui porte le label `ingress-ready=true` et expose les ports 80 et 443 vers la machine hôte — et deux nœuds de travail.

```bash
kubectl cluster-info --context kind-dilane-shop
kubectl get nodes
```

### 2. Construire l'image et la charger dans le cluster

kind n'a pas accès aux images du démon Docker local : elles doivent être copiées explicitement dans les nœuds. Aucune image n'est téléchargée depuis un registre (`imagePullPolicy: IfNotPresent`).

```bash
docker build -t dilane-shop:0.2.0 .
kind load docker-image dilane-shop:0.2.0 --name dilane-shop
```

### 3. Créer le namespace, le Secret et la configuration

Le Secret n'est jamais versionné : seul le modèle commenté [k8s/02-secrets.example.yaml](k8s/02-secrets.example.yaml) l'est. Créez-le avec `kubectl`, après le namespace et avant tout le reste — PostgreSQL comme Django y lisent leurs variables au démarrage.

```bash
kubectl apply -f k8s/00-namespace.yaml

kubectl create secret generic dilane-shop-secrets \
  --namespace dilane-shop \
  --from-literal=DJANGO_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')" \
  --from-literal=DB_PASSWORD="..." \
  --from-literal=STRIPE_PUBLIC_KEY="pk_test_..." \
  --from-literal=STRIPE_SECRET_KEY="sk_test_..." \
  --from-literal=STRIPE_WEBHOOK_SECRET="whsec_..." \
  --from-literal=BREVO_SMTP_LOGIN="..." \
  --from-literal=BREVO_SMTP_KEY="..." \
  --from-literal=EMAIL_FROM="..."

kubectl apply -f k8s/01-configmap.yaml
```

Un Secret Kubernetes est **encodé en base64, pas chiffré**. Quiconque peut lire les Secrets du namespace peut lire les valeurs en clair. Voir la conséquence correspondante dans [docs/adr/002-kubernetes.md](docs/adr/002-kubernetes.md).

### 4. Appliquer les manifestes applicatifs, dans l'ordre

L'ordre compte : la base doit répondre avant les migrations, et les migrations doivent être passées avant que les pods Django ne servent du trafic.

```bash
kubectl apply -f k8s/03-postgres.yaml
kubectl wait --namespace dilane-shop \
  --for=condition=ready pod -l app.kubernetes.io/name=postgres --timeout=180s

kubectl apply -f k8s/05-migration-job.yaml
kubectl wait --namespace dilane-shop \
  --for=condition=complete job/django-migrate --timeout=180s

kubectl apply -f k8s/04-django.yaml
```

**Les migrations passent par le Job `k8s/05-migration-job.yaml`, pas au démarrage des pods.** Le `CMD` de l'image lance directement Gunicorn et aucun manifeste n'exécute `migrate` à l'initialisation d'un conteneur : avec deux replicas, plusieurs `migrate` s'exécuteraient en parallèle sur la même base. Le Job s'exécute une fois puis se termine, et se supprime cinq minutes après sa réussite (`ttlSecondsAfterFinished: 300`). Relancez-le après chaque changement de schéma, avant de déployer la nouvelle version de l'application :

```bash
kubectl delete job django-migrate -n dilane-shop --ignore-not-found
kubectl apply -f k8s/05-migration-job.yaml
kubectl logs -n dilane-shop job/django-migrate
```

### 5. Installer le contrôleur Ingress et son correctif de placement

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.15.1/deploy/static/provider/kind/deploy.yaml
kubectl apply -f k8s/07-ingress-controller-patch.yaml
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod --selector=app.kubernetes.io/component=controller --timeout=180s
```

Le correctif [k8s/07-ingress-controller-patch.yaml](k8s/07-ingress-controller-patch.yaml) n'est pas facultatif. Le manifeste `provider/kind` devrait contraindre le contrôleur au nœud portant `ingress-ready=true` ; en v1.15.1, son `nodeSelector` ne contient que `kubernetes.io/os: linux`. Sans le correctif, le contrôleur peut se placer sur un nœud de travail, où les ports 80 et 443 ne sont pas mappés vers l'hôte : le site ne répond pas, alors que tous les pods sont `Running`. Vérifiez le placement :

```bash
kubectl get pods -n ingress-nginx -o wide
```

Le pod `ingress-nginx-controller` doit être sur `dilane-shop-control-plane`.

### 6. Installer cert-manager et publier le site en HTTPS

```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.16.2/cert-manager.yaml
kubectl wait --namespace cert-manager \
  --for=condition=available deployment --all --timeout=180s

kubectl apply -f k8s/08-tls.yaml
kubectl apply -f k8s/06-ingress.yaml
```

`k8s/08-tls.yaml` déclare un `Issuer` auto-signé et le `Certificate` correspondant ; cert-manager crée le Secret `tls-dilane-shop` que l'Ingress consomme. Il doit donc être appliqué avant l'Ingress.

```bash
kubectl get certificate -n dilane-shop
```

La colonne `READY` doit valoir `True`.

Let's Encrypt ne peut pas valider `dilane-shop.local`, qui n'existe que sur le poste : le certificat est **auto-signé**. Le navigateur affichera un avertissement, et `curl` exige `-k`.

### 7. Ajouter le domaine local au fichier hosts

```text
127.0.0.1 dilane-shop.local
```

- Linux et macOS : `/etc/hosts`
- Windows : `C:\Windows\System32\drivers\etc\hosts`, à éditer en administrateur
- **WSL2** : ajoutez la ligne au fichier hosts **de Windows**. WSL régénère `/etc/hosts` à chaque démarrage et la résolution passe par l'hôte Windows.

### 8. Vérifier

```bash
kubectl get pods -n dilane-shop -o wide
curl -k -o /dev/null -w '%{http_code}\n' https://dilane-shop.local/
curl -k https://dilane-shop.local/healthz/
```

Réponses attendues : deux pods `django` prêts sur deux nœuds différents, `200` sur la page d'accueil, et `{"status": "ok", "database": "reachable"}` sur l'endpoint de santé. En HTTP, `http://dilane-shop.local/` répond `308` vers HTTPS.

### 9. Peupler la base

```bash
kubectl exec -n dilane-shop deploy/django -- python manage.py loaddata fixtures/demo-catalogue.json
kubectl exec -it -n dilane-shop deploy/django -- python manage.py createsuperuser
```

### Commandes utiles

```bash
kubectl logs -n dilane-shop deploy/django -f          # journaux applicatifs
kubectl get events -n dilane-shop --sort-by=.lastTimestamp
kubectl describe pod -n dilane-shop <nom-du-pod>
kubectl rollout status -n dilane-shop deploy/django   # suivre une mise à jour
kubectl delete namespace dilane-shop                  # tout supprimer, sauf le cluster
kind delete cluster --name dilane-shop                # supprimer le cluster
```

## Routes principales

- `/` accueil
- `/api/produits/` recherche produits
- `/checkout` checkout protégé
- `/confirmation/<id>/` confirmation de commande
- `/paiement/succes/` retour Stripe succès
- `/paiement/annule/` retour Stripe annulation
- `/inscription/` inscription
- `/connexion/` connexion
- `/deconnexion/` déconnexion
- `/profil/` commandes de l’utilisateur
- `/admin/` administration Django
- `/gestion/` raccourci vers l’administration

## Structure du projet

```text
.
├── Dockerfile                  # Image multi-stage, utilisateur non-root
├── docker-compose.yml          # Services web et db, volumes nommés
├── .dockerignore               # Exclusions de contexte de build
├── manage.py
├── requirements.txt
├── ecommerce/                  # Configuration Django (settings, urls, wsgi)
├── shop/                       # App métier : modèles, vues, services, tests
├── templates/                  # Surcharges de gabarits de l'admin
├── fixtures/                   # Données de démonstration (loaddata)
├── k8s/                        # Manifestes Kubernetes et configuration kind
├── docs/
│   ├── adr/                    # Décisions d'architecture
│   └── sprints/                # Rétrospectives de sprint
├── infra/terraform/            # Archive : infrastructure AWS, plus active
├── scripts/                    # Archive : sauvegarde et restauration PostgreSQL
└── .github/workflows/          # Intégration continue
```

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — arborescence commentée, rôle des apps Django, diagramme de déploiement et inventaire des dépendances externes.
- [docs/MODELE-DONNEES.md](docs/MODELE-DONNEES.md) — diagramme de classes des quatre modèles, détail des champs et contraintes, chronologie des 15 migrations.
- [docs/AUDIT.md](docs/AUDIT.md) — fonctionnalités implémentées ou mortes, couverture de tests réelle, problèmes de sécurité et dette technique classée par criticité.
- [docs/HISTORIQUE.md](docs/HISTORIQUE.md) — analyse du journal Git, commits regroupés en phases de travail datées.
- [docs/adr/001-conteneurisation.md](docs/adr/001-conteneurisation.md) — décision de conteneuriser l’application et de séparer PostgreSQL, avec ses conséquences.
- [docs/adr/002-kubernetes.md](docs/adr/002-kubernetes.md) — décision de déployer sur Kubernetes plutôt que sur un serveur unique, alternatives chiffrées (AKS, VPS, EKS/GKE) et critères de révision.
- [docs/adr/003-monolithe-modulaire.md](docs/adr/003-monolithe-modulaire.md) — choix d’un monolithe modulaire plutôt que de microservices, et critères de révision.
- [docs/sprints/sprint-09-docker.md](docs/sprints/sprint-09-docker.md) — rétrospective du sprint de conteneurisation, décisions techniques et points reportés.
- [docs/sprints/sprint-10-kubernetes.md](docs/sprints/sprint-10-kubernetes.md) — rétrospective du sprint Kubernetes, diagnostic du placement du contrôleur Ingress et points reportés.

## Suivi du projet

Le backlog est tenu sur GitHub Projects, dans le tableau **Dilane Shop — Roadmap**.

- **Issues** : chaque tâche porte un contexte, un objectif et des critères d’acceptation vérifiables.
- **Labels par epic** : `epic:catalogue`, `epic:commande`, `epic:paiement`, `epic:comptes`, `epic:notifications`, `epic:infra`, `epic:qualite`, `epic:securite`, `epic:conformite`, `epic:ia`. Ils sont complétés par des labels `type:` et `priorite:`.
- **Milestones** : `v0.1 - MVP deploye`, `v0.2 - Fiabilise`, `v1.0 - Boutique reelle`.

## Historique : déploiement AWS EC2 (septembre 2026)

Cette architecture n’est plus active — le compte AWS est fermé et le job de déploiement EC2 est neutralisé dans la CI depuis le Sprint 9 ; les trois sections ci-dessous sont conservées à titre documentaire.

### Déploiement

Le déploiement de production était automatisé avec:

- GitHub Actions pour les tests et le déploiement
- Terraform pour créer l’instance EC2, la security group et l’Elastic IP
- cloud-init / `user_data` pour bootstrapper automatiquement le serveur
- Gunicorn et Nginx pour servir l’application

### Infrastructure Terraform

La configuration Terraform se trouve dans [infra/terraform](infra/terraform).

Commandes utiles:

```bash
cd infra/terraform
terraform init
terraform plan
terraform apply
terraform destroy
```

Variables principales:

- `aws_region`
- `ssh_key_name`
- `ssh_allowed_cidr`
- `django_secret_key`
- `database_url`
- `stripe_public_key`
- `stripe_secret_key`
- `brevo_smtp_login`
- `brevo_smtp_key`
- `email_from`
- `allowed_hosts`

### Sauvegarde base de données

Deux scripts existent dans le dépôt:

- `scripts/backup_postgres.sh`
- `scripts/restore_postgres.sh`

**Leurs chemins sont obsolètes et ces scripts n’ont jamais fonctionné.** Tous deux attendent le projet dans `/home/ubuntu/ecommerce` (`backup_postgres.sh:4`, `restore_postgres.sh:10`), alors que `bootstrap.sh` l’installait dans `/home/ubuntu/e-commerce`. Le répertoire attendu n’a donc jamais existé sur le serveur : les scripts sortaient sur `Missing env file` avant d’atteindre `pg_dump`. La tâche cron proposée dans [docs/ops-backup.md](docs/ops-backup.md) ne surcharge pas `PROJECT_DIR` et échouait silencieusement.

Il n’existe aujourd’hui aucune procédure de sauvegarde active. Les données de la pile Docker résident dans le volume nommé `postgres_data`. Ce point correspond à la dette 2.5 de [docs/AUDIT.md](docs/AUDIT.md).

## Auteur

Projet développé par Dilane Junior.
