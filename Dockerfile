
# ---------- Stage 1 : construction des dependances ----------
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


# ---------- Stage 2 : image d'execution ----------
FROM python:3.13-slim AS runtime

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
COPY --chown=django:django . .

# Fichiers statiques collectes a la construction
RUN SECRET_KEY=build-only DJANGO_SECRET_KEY=build-only \
    python manage.py collectstatic --noinput \
    && chown -R django:django /app/staticfiles

USER django

EXPOSE 8000

CMD ["gunicorn", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--worker-class", "sync", \
     "--timeout", "60", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "ecommerce.wsgi:application"]
