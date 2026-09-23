
# ---------- Étape builder : construction des dépendances ----------
FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Outils necessaires a la compilation eventuelle de dependances
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Environnement virtuel dedie, copie tel quel au stage suivant
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt


# ---------- Étape base : application prête à l'exécution ----------
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=ecommerce.settings

# Bibliotheque cliente PostgreSQL uniquement, sans les outils de build
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Utilisateur non privilegie
RUN groupadd --system django && useradd --system --gid django --home /app django

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
# Code copié en tant que root : lisible par django, jamais modifiable par lui.
COPY . .

# Fichiers statiques collectes a la construction
RUN SECRET_KEY=build-only DJANGO_SECRET_KEY=build-only \
    python manage.py collectstatic --noinput

# Dossier des médias téléversés : le seul emplacement de /app inscriptible
# par l'application. Créé dans l'image pour que les volumes montés dessus
# héritent de ce propriétaire.
RUN mkdir -p /app/media && chown django:django /app/media

USER django

EXPOSE 8000

# --no-control-socket : l'interface de contrôle de gunicorn (depuis la 25.1)
# n'est pas utilisée ici ; la désactiver réduit la surface d'attaque et évite
# qu'elle tente d'écrire dans /app, volontairement non inscriptible.
CMD ["gunicorn", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--worker-class", "sync", \
     "--timeout", "60", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--no-control-socket", \
     "ecommerce.wsgi:application"]


# ---------- Étape test : image de production + outils de test ----------
# Construite uniquement avec --target test, pour la CI. Jamais déployée.
FROM base AS test
USER root
RUN pip install --no-cache-dir -r requirements-dev.txt
USER django


# ---------- Étape finale : image de production ----------
# Doit rester la dernière : c'est celle que Docker construit par défaut,
# sans --target, notamment pour Kubernetes.
FROM base AS runtime
