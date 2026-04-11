# E-commerce Django

Application e-commerce développée avec Django, Stripe, Terraform et GitHub Actions. Le projet couvre le catalogue produits, l’authentification, le checkout, la gestion de stock, les paiements et le déploiement automatisé sur AWS EC2.

Ce dépôt contient deux documentations utiles:

- ce README racine pour l’application et le workflow global
- [infra/terraform/README.md](infra/terraform/README.md) pour les détails d’infrastructure AWS

## Vue d’ensemble

Ce projet a été construit pour aller au-delà d’une simple application web:

- Django pour la logique métier et les pages du site
- Stripe pour les paiements
- Brevo pour les emails transactionnels
- Terraform pour l’infrastructure AWS
- GitHub Actions pour la CI/CD
- Bootstrap serveur automatique via `user_data` / cloud-init
- Gunicorn + Nginx pour l’exécution en production
- Scripts de backup et restauration de base de données

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

- Python 3.12
- Django 6
- SQLite en local par défaut, PostgreSQL possible via variables d’environnement
- Stripe
- Brevo SMTP
- Gunicorn
- Nginx
- Terraform
- AWS EC2
- GitHub Actions

## Prérequis

- Python 3.12+
- pip
- Git
- Un compte Stripe si tu veux tester les paiements
- Un compte Brevo si tu veux activer les emails
- AWS CLI et Terraform si tu veux gérer l’infrastructure

## Installation locale

```bash
git clone https://github.com/wankamdypuedilane/e-commerce.git
cd e-commerce
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Le projet charge un fichier `.env` à la racine du projet.

Exemple minimal:

```env
DJANGO_SECRET_KEY=your-secret-key
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost

DB_ENGINE=sqlite
DB_NAME=/absolute/path/to/db.sqlite3

# Si PostgreSQL est utilisé
# DB_ENGINE=postgres
# DB_NAME=ecommerce
# DB_USER=postgres
# DB_PASSWORD=your-password
# DB_HOST=127.0.0.1
# DB_PORT=5432

STRIPE_PUBLIC_KEY=pk_test_xxx
STRIPE_SECRET_KEY=sk_test_xxx
BREVO_SMTP_LOGIN=your@login.com
BREVO_SMTP_KEY=your-brevo-key
EMAIL_FROM=your@login.com
```

Notes:

- Si `DB_ENGINE=sqlite`, Django utilise `db.sqlite3`.
- Si `DB_ENGINE=postgres`, Django lit la configuration PostgreSQL depuis les variables `DB_*`.
- Ne commit jamais tes secrets.

## Lancer le projet

```bash
python manage.py migrate
python manage.py runserver
```

Puis ouvre:

- http://127.0.0.1:8000/
- http://127.0.0.1:8000/connexion/
- http://127.0.0.1:8000/admin/

## Tests

```bash
python manage.py test
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

## Déploiement

Le déploiement de production est automatisé avec:

- GitHub Actions pour les tests et le déploiement
- Terraform pour créer l’instance EC2, la security group et l’Elastic IP
- cloud-init / `user_data` pour bootstrapper automatiquement le serveur
- Gunicorn et Nginx pour servir l’application

## Infrastructure Terraform

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

## Sauvegarde base de données

Scripts disponibles:

- `scripts/backup_postgres.sh`
- `scripts/restore_postgres.sh`

## Structure du projet

```text
.
├── ecommerce/
├── shop/
├── infra/terraform/
├── scripts/
├── Templates/
└── requirements.txt
```

## Bonnes pratiques

- Les secrets restent dans `.env` ou `terraform.tfvars`
- Les fichiers `terraform.tfstate` et `tfplan` ne doivent pas être versionnés
- Les tests Django doivent passer avant tout déploiement

## Idée de prochaine étape

- Passer de SQLite à PostgreSQL en production si tu veux une base plus robuste
- Externaliser les secrets dans AWS SSM ou Secrets Manager
- Ajouter des captures d’écran et un lien de démo

## Auteur

Projet développé par Dilane Junior.
