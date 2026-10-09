"""Tests des métriques Prometheus (issue #45).

Les compteurs vivent dans le processus et sont partagés par tous les tests :
les valeurs absolues dépendraient donc de l'ordre d'exécution. Chaque test
mesure un **écart** entre deux relevés, jamais une valeur absolue.
"""
import os
import tempfile
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from prometheus_client import REGISTRY

from . import metrics as mesures
from .metrics import ROUTE_INCONNUE
from catalog.models import Category, Product


def releve(nom, etiquettes):
    """Valeur d'une métrique, ou 0 si elle n'a pas encore été observée."""
    valeur = REGISTRY.get_sample_value(nom, etiquettes)
    return 0 if valeur is None else valeur


class ExpositionDesMetriquesTest(TestCase):

    def test_metrics_repond_et_expose_le_format_prometheus(self):
        reponse = self.client.get("/metrics")
        self.assertEqual(reponse.status_code, 200)
        self.assertIn("text/plain", reponse["Content-Type"])
        corps = reponse.content.decode()
        # Le format d'exposition annonce chaque métrique par deux commentaires
        self.assertIn("# HELP django_http_requests_total", corps)
        self.assertIn("# TYPE django_http_requests_total counter", corps)
        self.assertIn("django_http_requests", corps)

    def test_les_quatre_signaux_sont_exposes(self):
        corps = self.client.get("/metrics").content.decode()
        for metrique in (
            "django_http_requests_latency_seconds",   # latence
            "django_http_requests_total",             # trafic et erreurs
            "django_http_exceptions_total",           # erreurs
            "django_http_requests_in_progress",       # saturation
        ):
            with self.subTest(metrique=metrique):
                self.assertIn(metrique, corps)


class ExpositionEnMultiprocessusTest(TestCase):
    """La branche empruntée en production.

    Gunicorn y lance trois workers et PROMETHEUS_MULTIPROC_DIR est défini par
    le manifeste : c'est donc ce chemin de code qui répond, et non celui des
    tests. Sans ce test, une erreur n'y apparaîtrait qu'en production, alors
    que toute la suite serait verte.
    """

    def test_l_exposition_multiprocessus_fonctionne(self):
        with tempfile.TemporaryDirectory() as repertoire:
            with patch.dict(os.environ, {"PROMETHEUS_MULTIPROC_DIR": repertoire}):
                sortie = mesures.exposition()
        self.assertIsInstance(sortie, bytes)

    def test_la_jauge_est_agregee_entre_processus(self):
        """`livesum` additionne les processus vivants.

        Sans ce mode, la jauge serait rendue une fois par identifiant de
        processus, et la saturation du pod deviendrait illisible.
        """
        self.assertEqual(mesures.requetes_en_cours._multiprocess_mode, "livesum")


class ComptageDesRequetesTest(TestCase):

    def setUp(self):
        categorie = Category.objects.create(name="Audio")
        self.produit = Product.objects.create(
            title="Casque", price=Decimal("10.00"), description="Test",
            category=categorie, stock=5,
        )

    def test_le_compteur_augmente_apres_un_appel_a_une_vue(self):
        etiquettes = {"method": "GET", "status": "200", "view": "home"}
        avant = releve("django_http_requests_total", etiquettes)

        self.assertEqual(self.client.get("/").status_code, 200)

        apres = releve("django_http_requests_total", etiquettes)
        self.assertEqual(apres, avant + 1, "l'appel à l'accueil n'a pas été compté")

    def test_la_latence_est_observee(self):
        etiquettes = {"method": "GET", "view": "home"}
        avant = releve("django_http_requests_latency_seconds_count", etiquettes)

        self.client.get("/")

        apres = releve("django_http_requests_latency_seconds_count", etiquettes)
        self.assertEqual(apres, avant + 1)

    def test_une_erreur_est_comptee_avec_son_code(self):
        etiquettes = {"method": "GET", "status": "404", "view": ROUTE_INCONNUE}
        avant = releve("django_http_requests_total", etiquettes)

        self.assertEqual(self.client.get("/page-inexistante-pour-le-test").status_code, 404)

        apres = releve("django_http_requests_total", etiquettes)
        self.assertEqual(apres, avant + 1)

    def test_les_requetes_en_cours_reviennent_a_zero(self):
        """La jauge de saturation doit être décrémentée après la réponse.

        Une jauge qui ne redescend pas ferait croire à une saturation
        permanente, et l'alerte correspondante serait inexploitable.
        """
        self.client.get("/")
        self.assertEqual(releve("django_http_requests_in_progress", {}), 0)

    def test_l_etiquette_est_le_nom_de_route_et_non_le_chemin(self):
        """Garde-fou de cardinalité.

        Étiqueter par chemin créerait une série temporelle par identifiant de
        produit. Le test échouerait si quelqu'un remplaçait le nom de route
        par `request.path`.
        """
        etiquettes = {"method": "GET", "status": "200", "view": "detail"}
        avant = releve("django_http_requests_total", etiquettes)

        self.client.get(f"/{self.produit.id}")

        self.assertEqual(releve("django_http_requests_total", etiquettes), avant + 1)
        # Aucune série ne doit porter le chemin demandé comme étiquette
        chemin = f"/{self.produit.id}"
        self.assertIsNone(
            REGISTRY.get_sample_value(
                "django_http_requests_total",
                {"method": "GET", "status": "200", "view": chemin},
            ),
            "le chemin est utilisé comme étiquette : cardinalité non bornée",
        )


class AccesAuxMetriquesTest(TestCase):
    """/metrics ne doit pas être joignable depuis Internet.

    L'Ingress route `/` en `Prefix`, donc tout chemin atteint l'application :
    vérifié en production, un chemin inexistant y reçoit les en-têtes de
    Django. Le contrôle repose donc sur les en-têtes que le contrôleur ajoute.
    """

    def test_acces_interne_autorise(self):
        """Sans en-tête de proxy : un scraper interne du cluster."""
        self.assertEqual(self.client.get("/metrics").status_code, 200)

    def test_acces_via_l_ingress_refuse(self):
        """Avec X-Forwarded-For : la requête est passée par l'Ingress."""
        reponse = self.client.get("/metrics", headers={"x-forwarded-for": "203.0.113.5"})
        self.assertEqual(reponse.status_code, 404)
        self.assertNotIn("django_http_requests", reponse.content.decode())

    def test_les_autres_entetes_de_proxy_sont_refuses(self):
        for entete in ("x-real-ip", "forwarded"):
            with self.subTest(entete=entete):
                reponse = self.client.get("/metrics", headers={entete: "203.0.113.5"})
                self.assertEqual(reponse.status_code, 404)

    def test_404_et_non_403(self):
        """Un 403 confirmerait l'existence de l'endpoint.

        Même raisonnement que pour les pages de commande (issue #70).
        """
        reponse = self.client.get("/metrics", headers={"x-forwarded-for": "203.0.113.5"})
        self.assertNotEqual(reponse.status_code, 403)
