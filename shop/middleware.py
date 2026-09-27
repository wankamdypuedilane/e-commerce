"""Intergiciels propres au projet."""
import time

from . import metrics


class PrometheusMetricsMiddleware:
    """Alimente les métriques Prometheus des quatre signaux d'or (issue #45).

    Placé en tête de MIDDLEWARE, donc le plus à l'extérieur : la durée
    mesurée couvre toute la pile, intergiciels de sécurité compris, et non
    la seule vue. C'est la latence que perçoit le visiteur, à l'Ingress près.

    Les métriques elles-mêmes sont définies dans shop/metrics.py.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        debut = time.perf_counter()
        # Incrémentée avant le traitement et décrémentée après, quoi qu'il
        # arrive : une exception qui ne décrémenterait pas ferait croire à
        # une saturation permanente.
        metrics.requetes_en_cours.inc()
        try:
            reponse = self.get_response(request)
        finally:
            metrics.requetes_en_cours.dec()

        route = metrics.nom_de_route(request)
        metrics.latence_secondes.labels(
            method=request.method, view=route
        ).observe(time.perf_counter() - debut)
        metrics.requetes_total.labels(
            method=request.method, status=str(reponse.status_code), view=route
        ).inc()
        return reponse

    def process_exception(self, request, exception):
        """Compte les exceptions non rattrapées par une vue.

        Django appelle ce point d'entrée avant de transformer l'exception en
        réponse 500 ; la réponse est ensuite comptée normalement par
        __call__. Aucune valeur n'est retournée : le traitement habituel de
        l'erreur par Django n'est pas modifié.
        """
        metrics.exceptions_total.labels(view=metrics.nom_de_route(request)).inc()
        return None


class PermissionsPolicyMiddleware:
    """Ajoute l'en-tête Permissions-Policy, que Django n'envoie pas nativement.

    Interdit à la page l'accès aux fonctions du navigateur dont une boutique
    n'a pas besoin. payment=() désactive l'API de paiement du navigateur : le
    paiement passe par une redirection vers la page de Stripe. À revoir si le
    paiement est un jour intégré directement dans le site.
    """

    POLITIQUE = "camera=(), microphone=(), geolocation=(), usb=(), payment=()"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        reponse = self.get_response(request)
        reponse.setdefault("Permissions-Policy", self.POLITIQUE)
        return reponse
