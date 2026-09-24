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
- GitHub Actions pour l’intégration continue : scan des dépendances, analyse statique, scan de l’image, tests dans l’image, test de fumée du conteneur

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
- Django 6.1 — versions exactes de toutes les dépendances : `requirements.txt`
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

## Sécurité des dépendances

Les dépendances sont épinglées à une version exacte : les builds sont reproductibles, mais aucune correction de sécurité n'arrive d'elle-même. Deux mécanismes compensent :

- **pip-audit**, dans la CI, compare les dépendances aux bases de vulnérabilités publiques et fait échouer la CI dès qu'une faille connue est trouvée ;
- **Dependabot** ouvre chaque semaine des pull requests de mise à jour, testées par la CI avant toute fusion.

Pour scanner en local :

```bash
docker run --rm -v "$PWD:/src:ro" python:3.13-slim \
  sh -c "pip install --quiet --root-user-action=ignore pip-audit==2.10.1 && pip-audit -r /src/requirements-dev.txt"
```

Procédure de mise à jour d'une dépendance vulnérable :

1. Retenir le dernier correctif de la même série, sans changer de version majeure au passage.
2. Modifier `requirements.txt`, reconstruire les images, puis vérifier la version réellement installée dans l'image.
3. Lancer la suite de tests et la couverture.
4. Relancer pip-audit : aucune vulnérabilité ne doit subsister.

Une alerte sans objet pour ce projet peut être ignorée avec `--ignore-vuln`, uniquement accompagnée d'une justification écrite dans le workflow.

## Analyse statique du code

**Bandit** analyse le code de `shop` et `ecommerce`, migrations et fichiers de test exclus, à la recherche de motifs dangereux : `mark_safe` sur une donnée saisie, requête SQL construite par concaténation, secret écrit en dur… Dans la CI, il s'exécute juste après pip-audit et avant la construction des images, et la fait échouer dès qu'un motif est détecté, quelle que soit sa gravité.

Pour analyser en local, avec la même commande que la CI :

```bash
docker run --rm -v "$PWD:/src:ro" -w /src python:3.13-slim \
  sh -c "pip install --quiet --root-user-action=ignore bandit==1.9.4 && bandit -r shop ecommerce -x '*/migrations/*,*/test*.py'"
```

Un faux positif ne s'ignore que ligne par ligne, par un commentaire `# nosec` sur la ligne concernée, toujours accompagné d'une justification écrite qui explique pourquoi le motif est sans danger à cet endroit. Par exemple :

```python
return mark_safe(html)  # nosec B703 — html ne contient que des constantes du code, aucune donnée saisie
```

Aucun test Bandit n'est désactivé globalement.

## Sécurité de l'image

**Trivy** analyse l'image de production une fois construite : paquets du système Debian et paquets Python. Dans la CI, il s'exécute juste après la construction des images et la fait échouer dès qu'il trouve une faille grave ou critique (`HIGH`, `CRITICAL`) disposant d'un correctif. Les failles sans correctif publié sont ignorées : aucune mise à jour ne permettrait de les supprimer.

Pour analyser en local, avec les mêmes options que la CI, après avoir construit l'image :

```bash
docker compose build web
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  aquasec/trivy:0.74.0 image --scanners vuln --severity HIGH,CRITICAL \
  --ignore-unfixed --exit-code 1 dilane-shop:0.1.0
```

**pip est absent de l'image de production.** L'application n'installe jamais de paquet à l'exécution. L'étape `runtime` du Dockerfile désinstalle donc pip, du virtualenv comme du Python système : il n'offrirait qu'un outil d'installation à un attaquant, et les bibliothèques qu'il embarque dans `pip/_vendor` portaient deux failles graves (`msgpack`, `setuptools`), présentes dans l'image uniquement sous cette forme. L'image de test conserve pip, qui y installe `coverage` : elle n'est jamais déployée ni analysée par Trivy.

Une faille sans objet pour ce projet ne s'ignore que dans un fichier `.trivyignore`, identifiant par identifiant (`CVE-…` ou `GHSA-…`), toujours accompagné d'une justification écrite en commentaire. Aucune exception n'existe aujourd'hui, et le dépôt ne contient pas de `.trivyignore`. La CI monte le dépôt dans le conteneur Trivy (`-v "$PWD:/src:ro" -w /src`), comme pour pip-audit et Bandit : un `.trivyignore` placé à la racine y serait lu.

## En-têtes de sécurité HTTP

Chaque réponse porte une politique de sécurité du contenu (CSP), native dans Django 6 et définie par `SECURE_CSP` dans `ecommerce/settings.py`, ainsi qu'un en-tête `Permissions-Policy` posé par `shop/middleware.py`, que Django ne fournit pas. Les protections envoyées par défaut par Django restent en place : `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `Cross-Origin-Opener-Policy`. Le détail des directives et leur justification figurent dans [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

- **Scripts** : seuls s'exécutent les fichiers du site, de `cdn.jsdelivr.net` et de `code.jquery.com`, et les scripts en ligne qui portent le jeton de la page. Un script injecté sans ce jeton est bloqué par le navigateur.
- **Styles** : exception assumée, `'unsafe-inline'` est autorisé. Les jetons ne s'appliquent pas aux attributs `style=` écrits dans le HTML, et une injection de style est bien moins grave qu'une injection de script.
- **Formulaires** : ils ne peuvent être envoyés qu'au site et à `checkout.stripe.com`, pour la redirection vers le paiement. Cette redirection n'a pas encore été vérifiée avec de vraies clés Stripe.
- **Strict-Transport-Security** n'est pas envoyé : il est reporté à l'issue #42, avec un certificat reconnu.

**Tout nouveau script en ligne doit porter le jeton**, sans quoi il sera bloqué :

```html
<script nonce="{{ csp_nonce }}">
  …
</script>
```

Un test de `shop/test_entetes.py` le vérifie sur l'accueil, la fiche produit, la commande et la confirmation : un script sans jeton sur l'une de ces pages fait échouer la CI. Une nouvelle page contenant un script en ligne doit être ajoutée à ce test. Les gestionnaires d'événements écrits dans le HTML (`onclick=`, etc.) ne peuvent pas porter de jeton : ils sont bloqués, à remplacer par un script qui porte le jeton.

**Pour modifier la politique**, repasser par le mode d'observation :

1. Recopier la politique modifiée dans `SECURE_CSP_REPORT_ONLY`, en laissant `SECURE_CSP` inchangé : le navigateur applique l'ancienne politique et signale seulement, dans sa console, ce que la nouvelle bloquerait.
2. Parcourir toutes les pages, admin comprise, console ouverte, jusqu'à ne plus voir aucune violation.
3. Reporter la politique dans `SECURE_CSP` et supprimer `SECURE_CSP_REPORT_ONLY`.
4. Lancer les tests : `shop/test_entetes.py` vérifie que la politique est bien appliquée et non plus seulement observée.

## Déploiement Kubernetes (local, kind)

Les manifestes du répertoire [k8s/](k8s/) déploient la même image que Docker Compose sur un cluster Kubernetes. Le cluster de référence est un cluster local [kind](https://kind.sigs.k8s.io/) à trois nœuds. Le choix de Kubernetes et ses contreparties sont documentés dans [docs/adr/002-kubernetes.md](docs/adr/002-kubernetes.md).

### Prérequis

- Docker Engine (kind exécute les nœuds du cluster comme des conteneurs)
- `kubectl` — série utilisée : 1.37
- `kind` — série utilisée : 0.33

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

Le correctif [k8s/07-ingress-controller-patch.yaml](k8s/07-ingress-controller-patch.yaml) n'est pas facultatif. Le manifeste `provider/kind` devrait contraindre le contrôleur au nœud portant `ingress-ready=true` ; dans la version installée par la commande ci-dessus, son `nodeSelector` ne contient que `kubernetes.io/os: linux`. Sans le correctif, le contrôleur peut se placer sur un nœud de travail, où les ports 80 et 443 ne sont pas mappés vers l'hôte : le site ne répond pas, alors que tous les pods sont `Running`. Vérifiez le placement :

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
- `/healthz/` état de l’application et de la base, pour les sondes Kubernetes et le test de fumée de la CI

Les pages de confirmation et de retour de paiement exigent une connexion et n’affichent que les commandes de l’utilisateur connecté : la commande d’un autre client répond 404.

## Structure du projet

```text
.
├── Dockerfile                  # Étapes builder, base, test et runtime (dernière), utilisateur non-root
├── docker-compose.yml          # Services web et db, service tests (profil test), volumes nommés
├── .dockerignore               # Exclusions de contexte de build
├── .env.example                # Modèle du fichier .env
├── .coveragerc                 # Mesure de couverture et seuil minimal
├── manage.py
├── requirements.txt            # Dépendances d'exécution, versions exactes
├── requirements-dev.txt        # Dépendances de test (coverage), image de test uniquement
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
└── .github/
    ├── dependabot.yml          # Mises à jour hebdomadaires : pip, image Docker, GitHub Actions
    └── workflows/              # Workflow CI (ci.yml) et sa documentation
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
- [docs/sprints/sprint-11-tests.md](docs/sprints/sprint-11-tests.md) — rétrospective du sprint de tests : webhook Stripe, TVA, authentification, couverture en cliquet.
- [.github/workflows/README.md](.github/workflows/README.md) — étapes du workflow CI, dans l’ordre.
- [docs/definition-of-done.md](docs/definition-of-done.md) — critères qu'une tâche doit remplir pour être considérée comme terminée, chacun issu d'un défaut réel du projet.

## Suivi du projet

Le backlog est tenu sur GitHub Projects, dans le tableau **Dilane Shop — Roadmap**.

- **Issues** : chaque tâche porte un contexte, un objectif et des critères d’acceptation vérifiables.
- **Labels par epic** : `epic:catalogue`, `epic:commande`, `epic:paiement`, `epic:comptes`, `epic:notifications`, `epic:infra`, `epic:qualite`, `epic:securite`, `epic:conformite`, `epic:ia`. Ils sont complétés par des labels `type:` et `priorite:`.
- **Milestones** : `v0.1 - MVP deploye`, `v0.2 - Fiabilise`, `v1.0 - Boutique reelle`.

## Historique : déploiement AWS EC2 (septembre 2026)

Cette architecture n’est plus active — le compte AWS est fermé ; le job de déploiement EC2, neutralisé au Sprint 9, a été retiré de la CI et reste consultable dans l’historique Git. Les trois sections ci-dessous sont conservées à titre documentaire.

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

Il n’existe aujourd’hui aucune procédure de sauvegarde active. Les données de la pile Docker résident dans le volume nommé `postgres_data`. Ce point correspond à la dette 2.5 de [docs/AUDIT.md](docs/AUDIT.md), suivie par l’issue #83.

## Auteur

Projet développé par Dilane Junior.
