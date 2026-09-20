# Architecture

Document de rattrapage — état observé du dépôt au 20/09/2026.
Tout ce qui suit décrit le code tel qu'il existe, sans recommandation.

---

## 1. Arborescence commentée

```text
e-commerce/
├── manage.py                     # Point d'entrée CLI Django, DJANGO_SETTINGS_MODULE=ecommerce.settings
├── requirements.txt              # 6 dépendances épinglées (versions exactes)
├── db.sqlite3                    # Base SQLite locale — VERSIONNÉE dans git (voir AUDIT.md)
├── README.md                     # Documentation projet rédigée au commit 52b363d
├── .env                          # Secrets locaux, ignoré par git
├── .env.example                  # Gabarit des 19 variables d'environnement
├── .gitignore                    # Ignore .env, __pycache__, *.pyc, tfstate, tfplan
│
├── ecommerce/                    # Package de configuration Django (projet)
│   ├── settings.py               # Config unique, pilotée par os.getenv + python-dotenv
│   ├── urls.py                   # URLconf racine : admin, reset password admin, include(shop.urls)
│   ├── wsgi.py                   # Point d'entrée WSGI utilisé par Gunicorn
│   ├── asgi.py                   # Point d'entrée ASGI — présent mais jamais référencé
│   └── __pycache__/              # Bytecode — VERSIONNÉ dans git (17 fichiers .pyc)
│
├── shop/                         # Unique app métier du projet
│   ├── models.py                 # 4 modèles : Category, Product, Commande, OrderItem
│   ├── views.py                  # 12 vues fonctionnelles (aucune CBV)
│   ├── urls.py                   # 16 routes, dont 4 PasswordReset* de django.contrib.auth
│   ├── services.py               # Couche métier : Stripe, TVA, email de confirmation
│   ├── forms.py                  # SignupForm (UserCreationForm + email) et EmailAuthenticationForm
│   ├── backends.py               # EmailOrUsernameModelBackend : login par email OU username
│   ├── admin.py                  # 4 ModelAdmin + inline OrderItem, branding "E-commerce"
│   ├── apps.py                   # ShopConfig, name='shop' (pas de default_auto_field)
│   ├── tests.py                  # 9 tests répartis en 4 TestCase
│   ├── migrations/               # 15 migrations (0001 → 0015), dont 2 data migrations
│   ├── static/shop/
│   │   └── favicon.svg           # Unique fichier statique du projet (aucun CSS/JS local)
│   └── templates/
│       ├── shop/                 # 13 templates métier + 2 templates d'email
│       ├── registration/         # 6 templates ; seuls password_reset_email.html
│       │                         #   et password_reset_subject.txt sont réellement résolus
│       └── admin/                # 5 templates, tous masqués par Templates/admin/ (DIRS > APP_DIRS)
│
├── Templates/                    # Répertoire déclaré dans TEMPLATES['DIRS'] (T majuscule)
│   └── admin/                    # 7 templates de surcharge de l'admin Django, prioritaires
│
├── infra/terraform/              # Infrastructure as Code AWS
│   ├── versions.tf               # terraform >= 1.6, provider aws ~> 5.0
│   ├── variables.tf              # 16 variables, 8 marquées sensitive
│   ├── main.tf                   # AMI Ubuntu 24.04, security group, EC2, Elastic IP
│   ├── outputs.tf                # instance_id, public_ip, public_dns, security_group_id
│   ├── bootstrap.sh              # Script cloud-init injecté via user_data (templatefile)
│   ├── README.md                 # Mode d'emploi Terraform
│   └── .gitignore                # Ignore .terraform/, tfstate, terraform.tfvars
│
├── .github/workflows/
│   ├── deploy.yml                # CI (check + test) puis déploiement SSH sur EC2
│   └── README.md                 # Liste des 5 secrets GitHub attendus
│
├── scripts/
│   ├── backup_postgres.sh        # pg_dump + gzip + rétention 14 jours
│   └── restore_postgres.sh       # gunzip + psql
│
└── docs/
    ├── ops-backup.md             # Procédure de sauvegarde (préexistant)
    ├── terraform-next-step.md    # Checklist Terraform (préexistant)
    ├── ARCHITECTURE.md           # Ce document
    ├── MODELE-DONNEES.md
    ├── AUDIT.md
    └── HISTORIQUE.md
```

---

## 2. Apps Django

`INSTALLED_APPS` contient 7 entrées : les 6 apps contrib de Django et une seule app projet.

| App | Origine | Rôle observé dans ce projet |
|---|---|---|
| `django.contrib.admin` | Django | Back-office. Personnalisé dans `shop/admin.py` (site_header « E-commerce », site_title « SBC-shop », index_title « Manageur ») et surchargé graphiquement par `Templates/admin/`. |
| `django.contrib.auth` | Django | Modèle `User` standard (aucun modèle utilisateur custom). Fournit les vues `PasswordReset*` câblées dans les deux URLconf. |
| `django.contrib.contenttypes` | Django | Dépendance d'`auth` et de l'admin. Pas d'usage direct dans le code métier. |
| `django.contrib.sessions` | Django | Sessions d'authentification. Backend par défaut (base de données). |
| `django.contrib.messages` | Django | Utilisé par 8 appels `messages.*` dans `shop/views.py` (succès checkout, connexion, déconnexion, annulation de paiement). |
| `django.contrib.staticfiles` | Django | Sert `shop/static/`. `STATIC_ROOT = BASE_DIR / 'staticfiles'`, alimenté par `collectstatic`. |
| `shop` | Projet | **Unique app métier.** Porte la totalité du domaine : catalogue, panier côté client, commandes, paiement Stripe, emails, authentification par email. Aucune séparation en sous-apps (pas d'app `orders`, `payments` ou `accounts` distincte). |

### Découpage interne de `shop`

L'app n'est pas découpée en modules Django, mais en couches de fichiers :

- `views.py` — orchestration HTTP, validation des entrées POST, transactions.
- `services.py` — logique sans HTTP : `stripe_is_configured`, `get_tax_rate_percent`, `calculate_tax_totals`, `build_order_items_payload`, `send_order_confirmation_email`, `build_stripe_line_items`, `create_stripe_checkout_session`, `sync_commande_payment_from_stripe`.
- `backends.py` — authentification.
- `forms.py` — validation de formulaires d'inscription/connexion.

Le panier n'a **aucune existence serveur** : il vit intégralement dans le `localStorage` du navigateur, sous la clé `panier_user_<id>` (connecté) ou `panier_guest` (anonyme), définie dans `shop/templates/shop/base.html:175-176`. Il n'est transmis au serveur qu'au moment du POST `/checkout`, via un champ caché `items` contenant du JSON.

---

## 3. Diagramme de déploiement ACTUEL

Ce diagramme décrit ce que provisionne `infra/terraform/` et ce qu'exécute `bootstrap.sh`, tel qu'écrit dans les fichiers.

```mermaid
graph TB
    subgraph Dev["Poste développeur"]
        DEV["Django runserver<br/>DB_ENGINE=sqlite<br/>db.sqlite3"]
    end

    subgraph GH["GitHub"]
        REPO["Dépôt<br/>wankamdypuedilane/e-commerce<br/>branche main"]
        GA["GitHub Actions — deploy.yml<br/>job ci : pip install, manage.py check,<br/>manage.py test<br/>job deploy : SSH"]
        SEC["Secrets : EC2_HOST, EC2_PORT,<br/>EC2_USER, EC2_PROJECT_PATH,<br/>EC2_SSH_KEY"]
    end

    subgraph AWS["AWS — region eu-west-3 (defaut)"]
        subgraph VPC["VPC par defaut / premier subnet"]
            SG["aws_security_group web<br/>ingress 22 depuis ssh_allowed_cidr<br/>ingress 80 et 443 depuis 0.0.0.0/0<br/>egress tout"]
            EIP["aws_eip<br/>Elastic IP"]
            subgraph EC2["aws_instance app — t3.micro, Ubuntu 24.04, gp3 8 Gio"]
                NGX["Nginx<br/>listen 80 uniquement<br/>alias /static/ et /media/"]
                GUN["Gunicorn — service systemd 'ecom'<br/>3 workers sync, bind 127.0.0.1:8000<br/>User=ubuntu, venv /home/ubuntu/e-commerce/Ecom"]
                APP["Django — ecommerce.wsgi<br/>/home/ubuntu/e-commerce<br/>.env genere par bootstrap.sh, chmod 600"]
                SQL["db.sqlite3 local<br/>(si database_url non postgres)"]
            end
        end
    end

    subgraph EXT["Services externes"]
        STRIPE["Stripe<br/>Checkout Session + Webhook"]
        BREVO["Brevo<br/>SMTP smtp-relay.brevo.com:587 TLS"]
        PG["PostgreSQL<br/>hote externe decrit par database_url<br/>(non provisionne par ce Terraform)"]
    end

    CLIENT["Navigateur client"]

    DEV -->|git push main| REPO
    REPO --> GA
    SEC --> GA
    GA -->|ssh, git pull --ff-only,<br/>pip install, migrate,<br/>collectstatic, restart| EC2

    CLIENT -->|HTTP 80| EIP
    EIP --> SG --> NGX
    NGX -->|proxy_pass 127.0.0.1:8000| GUN
    GUN --> APP
    APP --> SQL
    APP -.->|si DB_ENGINE=postgres| PG
    APP -->|API HTTPS| STRIPE
    STRIPE -.->|POST /webhooks/stripe/| NGX
    APP -->|SMTP 587| BREVO

    TF["Terraform local<br/>state fichier local"] -->|apply| AWS
    TF -->|user_data base64<br/>templatefile bootstrap.sh| EC2
```

### Points factuels sur ce déploiement

- Le port 443 est ouvert dans le security group, mais `bootstrap.sh` ne génère **aucun bloc `server` en écoute sur 443** et n'installe pas certbot. Aucun HTTPS n'est configuré.
- `SECURE_PROXY_SSL_HEADER` est positionné en dur dans `settings.py:39`, et Nginx envoie bien `X-Forwarded-Proto`.
- Le state Terraform est local : `versions.tf` ne déclare aucun backend distant.
- Terraform ne crée pas de base PostgreSQL. La variable `database_url` désigne un hôte supposé déjà existant ; sinon le bootstrap retombe sur SQLite.
- Le healthcheck de fin de bootstrap interroge `http://localhost/admin/`.

---

## 4. Inventaire des dépendances externes

### 4.1 Paquets Python (`requirements.txt`)

| Paquet | Version épinglée | Usage observé |
|---|---|---|
| `Django` | 6.0.3 | Framework. Version confirmée en local (`django 6.0.3`). |
| `python-dotenv` | 1.2.2 | `load_dotenv(BASE_DIR / '.env')`. Import protégé par `try/except ImportError` avec un stub no-op (`settings.py:15-19`). |
| `stripe` | 15.0.1 | SDK Stripe. Import protégé par `try/except ImportError` dans `views.py:24-27` et `services.py:11-14`. |
| `Pillow` | 12.2.0 | Requis par `Product.image_file` (`ImageField`). |
| `psycopg[binary]` | 3.3.3 | Driver PostgreSQL, utilisé seulement si `DB_ENGINE=postgres`. |
| `gunicorn` | 23.0.0 | Serveur WSGI en production. |

Aucune dépendance de développement (pas de `pytest`, `coverage`, `ruff`, `black`, ni de `requirements-dev.txt`).

### 4.2 Stripe

| Élément | Valeur observée |
|---|---|
| Variables | `STRIPE_PUBLIC_KEY`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` (`settings.py:177-179`) |
| Condition d'activation | `stripe_is_configured()` exige le module importé **+** `STRIPE_SECRET_KEY` **+** `STRIPE_PUBLIC_KEY`. `STRIPE_WEBHOOK_SECRET` n'entre pas dans ce test. |
| Mode | `stripe.checkout.Session.create(mode='payment', payment_method_types=['card'])`, devise `eur` |
| TVA | Ajoutée comme une ligne de produit supplémentaire nommée `TVA (<taux>%)`, pas via l'API Tax de Stripe |
| Métadonnée | `metadata={'commande_id': str(commande.id)}` |
| URLs de retour | `success_url` = `/paiement/succes/?session_id={CHECKOUT_SESSION_ID}&order_id=<id>`, `cancel_url` = `/paiement/annule/?order_id=<id>` |
| Webhook | `POST /webhooks/stripe/`, vue `stripe_webhook`, décorée `@csrf_exempt`, signature vérifiée par `stripe.Webhook.construct_event` |
| Événements traités | `checkout.session.completed` (synchronisation + décrément de stock) et `checkout.session.expired` (annulation + réincrément). Tout autre événement renvoie 200 sans traitement. |
| Lecture serveur | `sync_commande_payment_from_stripe` appelle `stripe.checkout.Session.retrieve` depuis 3 endroits : le webhook, `payment_success` et `confirmation`. |

Aucune clé publique Stripe n'est exposée dans les templates : il n'y a pas de Stripe.js, le paiement se fait par redirection vers l'URL de session hébergée.

### 4.3 Brevo (email transactionnel)

| Élément | Valeur observée |
|---|---|
| Backend | `django.core.mail.backends.smtp.EmailBackend` — en dur, sans bascule console |
| Hôte | `smtp-relay.brevo.com`, port `587`, `EMAIL_USE_TLS = True` — tous en dur dans `settings.py:169-171` |
| Identifiants | `BREVO_SMTP_LOGIN` / `BREVO_SMTP_KEY` par variables d'environnement |
| Expéditeur | `EMAIL_FROM`, avec pour valeur par défaut codée en dur l'adresse personnelle `wankamdypuedilane@gmail.com` (`settings.py:174`) |
| Emails envoyés | 1) confirmation de commande (`send_order_confirmation_email`, multipart texte + HTML, `fail_silently=False`) ; 2) réinitialisation de mot de passe utilisateur ; 3) réinitialisation de mot de passe admin |
| Anti-doublon | Champ `Commande.confirmation_email_sent`, positionné à `True` après envoi |
| Déclencheurs de l'email de confirmation | `sync_commande_payment_from_stripe` (si passage à `paid`), plus deux rattrapages dans `payment_success` et `confirmation` |

### 4.4 Base de données

`settings.py:92-115` propose deux moteurs, sélectionnés par `DB_ENGINE` :

| Moteur | Condition | Configuration |
|---|---|---|
| SQLite | valeur par défaut, ou toute valeur ≠ `postgres` | `NAME = BASE_DIR / 'db.sqlite3'` |
| PostgreSQL | `DB_ENGINE=postgres` | `django.db.backends.postgresql`, variables `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST` (défaut `127.0.0.1`), `DB_PORT` (défaut `5432`), `CONN_MAX_AGE` (défaut 60), `OPTIONS.sslmode` (défaut `prefer`) |

Remarques factuelles :

- `bootstrap.sh` n'écrit **jamais** `DB_CONN_MAX_AGE` ni `DB_SSLMODE` dans le `.env` généré ; les valeurs par défaut du code s'appliquent.
- Les scripts `scripts/backup_postgres.sh` et `scripts/restore_postgres.sh` refusent de s'exécuter si `DB_ENGINE != postgres`. Il n'existe aucun script de sauvegarde pour SQLite.
- Le code utilise `select_for_update()` dans `checkout` et `stripe_webhook`. Sous SQLite, ce verrouillage de ligne n'a pas la sémantique de PostgreSQL.

### 4.5 Dépendances front chargées par CDN

Référencées dans `shop/templates/shop/base.html`, non versionnées dans le dépôt :

- Bootstrap 5.3.8 CSS — `cdn.jsdelivr.net`
- Bootstrap Icons (classes `bi bi-*` utilisées dans les templates)

### 4.6 Dépendances d'infrastructure

| Élément | Détail |
|---|---|
| AWS | Provider `hashicorp/aws ~> 5.0`, région par défaut `eu-west-3`, AMI Canonical (owner `099720109477`) Ubuntu 24.04 |
| Terraform | `>= 1.6.0`, backend local |
| GitHub Actions | `actions/checkout@v5`, `actions/setup-python@v6` (Python 3.12), runner `ubuntu-latest`, variable `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true` |
| Paquets système installés par `bootstrap.sh` | python3.12, python3.12-venv, python3.12-dev, git, postgresql-client, nginx, curl, wget, build-essential, libssl-dev, libffi-dev |
