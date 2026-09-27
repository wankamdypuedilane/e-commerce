"""Métriques Prometheus de l'application (issue #45).

Les quatre signaux d'or, tels que définis par le manuel de SRE de Google :

- **latence** : `django_http_requests_latency_seconds`, un histogramme ;
- **trafic** : `django_http_requests_total`, un compteur ;
- **erreurs** : le même compteur, ventilé par code de statut, et
  `django_http_exceptions_total` pour les exceptions non rattrapées ;
- **saturation** : `django_http_requests_in_progress`, une jauge.

Les noms reprennent ceux de la bibliothèque django-prometheus. Celle-ci
n'est pas utilisée : sa dernière version stable exige Django < 6.1, alors
que le projet tourne en 6.1.1, et `pip` refuse d'installer les deux. Garder
ses noms permet de basculer dessus sans réécrire les tableaux de bord le
jour où une version compatible paraît.

**Cardinalité.** Les métriques sont étiquetées par le *nom de route* Django,
jamais par le chemin demandé. Étiqueter par chemin créerait une série
temporelle par identifiant de produit — `/1`, `/2`, `/3`… — et autant pour
chaque URL inexistante visitée par un robot, ce qui ferait grossir la
mémoire de Prometheus sans limite.
"""
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, multiprocess
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest

# Nom donné aux requêtes dont la route n'a pas pu être résolue : URL
# inexistante, ou fichier servi par WhiteNoise avant le routage de Django.
ROUTE_INCONNUE = "<inconnue>"

requetes_total = Counter(
    "django_http_requests_total",
    "Nombre de requêtes HTTP traitées.",
    ["method", "status", "view"],
)

latence_secondes = Histogram(
    "django_http_requests_latency_seconds",
    "Durée de traitement des requêtes HTTP, en secondes.",
    ["method", "view"],
    # Bornes resserrées sous la seconde : les pages du catalogue répondent
    # en quelques dizaines de millisecondes, et la borne haute sert à voir
    # les appels lents, notamment ceux qui attendent Stripe.
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

exceptions_total = Counter(
    "django_http_exceptions_total",
    "Nombre d'exceptions non rattrapées remontées par une vue.",
    ["view"],
)

requetes_en_cours = Gauge(
    "django_http_requests_in_progress",
    "Nombre de requêtes HTTP en cours de traitement.",
    # « livesum » additionne les valeurs des processus vivants. Sans ce mode,
    # une jauge en multiprocessus est rendue une fois par identifiant de
    # processus : la saturation du pod devrait être recalculée à la lecture,
    # et chaque redémarrage de worker laisserait une série orpheline.
    # Vérifié : sans lui, la sortie porte des étiquettes pid="9", pid="10"…
    multiprocess_mode="livesum",
)


def nom_de_route(request):
    """Nom de la route Django, ou une valeur de repli à cardinalité bornée.

    `resolver_match` n'est renseigné qu'après la résolution de l'URL : la
    valeur est donc lue au moment de la réponse, pas à l'entrée.
    """
    correspondance = getattr(request, "resolver_match", None)
    if correspondance is None:
        return ROUTE_INCONNUE
    return correspondance.view_name or correspondance.url_name or ROUTE_INCONNUE


def exposition():
    """Rend les métriques au format texte de Prometheus.

    En présence de PROMETHEUS_MULTIPROC_DIR, les mesures des différents
    processus gunicorn sont agrégées ; sinon, seules celles du processus qui
    répond sont rendues. Voir la réserve dans docs/ARCHITECTURE.md.
    """
    import os

    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registre = CollectorRegistry()
        multiprocess.MultiProcessCollector(registre)
        return generate_latest(registre)
    return generate_latest(REGISTRY)


__all__ = [
    "CONTENT_TYPE_LATEST",
    "ROUTE_INCONNUE",
    "exceptions_total",
    "exposition",
    "latence_secondes",
    "nom_de_route",
    "requetes_en_cours",
    "requetes_total",
]
