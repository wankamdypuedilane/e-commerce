"""Tests de l'API REST interne, fondations (issue #56).

Vérifié ici :
- le catalogue est lisible sans authentification, sous /api/v1/ ;
- il est en lecture seule : aucune écriture possible, même authentifié ;
- un jeton s'obtient avec des identifiants valides, et authentifie les
  requêtes suivantes ;
- seule la version v1 existe ;
- les commandes ne sont visibles que de leur propriétaire, avec la même
  règle que le site (test_acces_commandes) : la commande d'autrui répond
  404 et non 403, pour ne pas confirmer qu'elle existe ;
- la limitation de débit répond 429 au-delà du seuil ;
- le schéma OpenAPI et Swagger UI sont servis, sans script inline que la
  CSP bloquerait.
"""
import re
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from catalog.models import Category, Product
from orders.models import Commande, OrderItem

User = get_user_model()
MOT_DE_PASSE = "Mot-de-passe-de-test-42"


def url(nom, **kwargs):
    """Adresse d'une route de l'API, version comprise."""
    return reverse(f"api:{nom}", kwargs={"version": "v1", **kwargs})


class ApiTestCase(TestCase):
    """Base des tests de l'API : compteurs de limitation de débit remis à zéro.

    Les compteurs vivent dans le cache, partagé par toute la suite : sans
    cette remise à zéro, les requêtes d'un test compteraient pour le suivant.
    """

    def setUp(self):
        cache.clear()


class CatalogueApiTest(ApiTestCase):

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.audio = Category.objects.create(name="Audio")
        self.maison = Category.objects.create(name="Maison")
        self.casque = Product.objects.create(
            title="Casque", price=Decimal("100.00"), description="Casque audio",
            category=self.audio, stock=10, image="https://example.com/casque.jpg",
        )
        self.lampe = Product.objects.create(
            title="Lampe", price=Decimal("25.50"), description="Lampe de bureau",
            category=self.maison, stock=0,
        )

    # --- Lecture publique ---------------------------------------------------

    def test_liste_des_produits_publique(self):
        """GET /api/v1/products/ sans authentification renvoie tous les produits."""
        reponse = self.client.get("/api/v1/products/")
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse["Content-Type"], "application/json")
        donnees = reponse.json()
        self.assertEqual(len(donnees), 2)
        self.assertEqual([p["title"] for p in donnees], ["Casque", "Lampe"])
        self.assertEqual(
            set(donnees[0]),
            {"id", "title", "description", "price", "stock", "category", "image"},
        )

    def test_detail_d_un_produit(self):
        """GET /api/v1/products/{id}/ renvoie le bon produit, prix en chaîne exacte."""
        reponse = self.client.get(url("product-detail", pk=self.casque.pk))
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.json(), {
            "id": self.casque.pk,
            "title": "Casque",
            "description": "Casque audio",
            "price": "100.00",
            "stock": 10,
            "category": self.audio.pk,
            "image": "https://example.com/casque.jpg",
        })

    def test_produit_inexistant_repond_404(self):
        """Un identifiant inconnu répond 404, en JSON."""
        reponse = self.client.get(url("product-detail", pk=999999))
        self.assertEqual(reponse.status_code, 404)

    def test_liste_des_categories_publique(self):
        """GET /api/v1/categories/ renvoie les catégories, triées par nom."""
        reponse = self.client.get(url("category-list"))
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.json(), [
            {"id": self.audio.pk, "name": "Audio"},
            {"id": self.maison.pk, "name": "Maison"},
        ])

    def test_racine_de_l_api(self):
        """La racine /api/v1/ liste les routes de l'API."""
        reponse = self.client.get("/api/v1/")
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(set(reponse.json()), {"products", "categories", "orders"})

    def test_version_inconnue_introuvable(self):
        """Seule v1 existe : /api/v2/ ne correspond à aucune route."""
        reponse = self.client.get("/api/v2/products/")
        self.assertEqual(reponse.status_code, 404)

    # --- Lecture seule ------------------------------------------------------

    def test_ecriture_refusee_meme_authentifie(self):
        """POST, PUT, PATCH et DELETE répondent 405, même avec un jeton valide."""
        utilisateur = User.objects.create_user(username="client", password=MOT_DE_PASSE)
        jeton = Token.objects.create(user=utilisateur)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {jeton.key}")

        liste = url("product-list")
        detail = url("product-detail", pk=self.casque.pk)
        nouveau = {"title": "Pirate", "price": "1.00", "description": "x",
                   "category": self.audio.pk, "stock": 1}

        self.assertEqual(self.client.post(liste, nouveau, format="json").status_code, 405)
        self.assertEqual(self.client.put(detail, nouveau, format="json").status_code, 405)
        self.assertEqual(self.client.patch(detail, {"price": "1.00"}, format="json").status_code, 405)
        self.assertEqual(self.client.delete(detail).status_code, 405)
        self.assertEqual(self.client.post(url("category-list"), {"name": "X"}, format="json").status_code, 405)

        self.casque.refresh_from_db()
        self.assertEqual(self.casque.price, Decimal("100.00"))
        self.assertEqual(Product.objects.count(), 2)
        self.assertEqual(Category.objects.count(), 2)

    def test_ecriture_anonyme_refusee_avant_tout(self):
        """Sans authentification, une écriture est refusée en 401, avant même le 405."""
        reponse = self.client.post(url("product-list"), {"title": "Pirate"}, format="json")
        self.assertEqual(reponse.status_code, 401)
        self.assertEqual(Product.objects.count(), 2)


class JetonApiTest(ApiTestCase):

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.utilisateur = User.objects.create_user(username="client", password=MOT_DE_PASSE)

    def test_identifiants_valides_renvoient_un_jeton(self):
        """POST /api/v1/auth/token/ avec de bons identifiants renvoie le jeton de l'utilisateur."""
        reponse = self.client.post(
            "/api/v1/auth/token/",
            {"username": "client", "password": MOT_DE_PASSE},
            format="json",
        )
        self.assertEqual(reponse.status_code, 200)
        jeton = reponse.json()["token"]
        self.assertEqual(jeton, Token.objects.get(user=self.utilisateur).key)

    def test_meme_jeton_a_chaque_demande(self):
        """Un second appel renvoie le même jeton, sans en créer un nouveau."""
        identifiants = {"username": "client", "password": MOT_DE_PASSE}
        premier = self.client.post(url("token"), identifiants, format="json").json()["token"]
        second = self.client.post(url("token"), identifiants, format="json").json()["token"]
        self.assertEqual(premier, second)
        self.assertEqual(Token.objects.count(), 1)

    def test_mauvais_mot_de_passe_refuse(self):
        """Des identifiants invalides répondent 400, sans jeton créé."""
        reponse = self.client.post(
            url("token"), {"username": "client", "password": "faux"}, format="json",
        )
        self.assertEqual(reponse.status_code, 400)
        self.assertNotIn("token", reponse.json())
        self.assertFalse(Token.objects.exists())

    def test_jeton_invalide_refuse(self):
        """Un jeton inconnu est rejeté en 401, même sur une route en lecture publique."""
        self.client.credentials(HTTP_AUTHORIZATION="Token jeton-inexistant")
        reponse = self.client.get(url("product-list"))
        self.assertEqual(reponse.status_code, 401)


class CommandesApiTest(ApiTestCase):
    """Accès aux commandes par l'API (issue #56), calqué sur test_acces_commandes."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.proprietaire = User.objects.create_user(username="proprietaire", password=MOT_DE_PASSE)
        self.autre = User.objects.create_user(username="autre", password=MOT_DE_PASSE)
        categorie = Category.objects.create(name="Audio")
        self.produit = Product.objects.create(
            title="Casque", price=Decimal("100.00"), description="Test",
            category=categorie, stock=10,
        )
        self.commande = self.creer_commande(self.proprietaire)
        self.commande_d_autrui = self.creer_commande(self.autre)

    def creer_commande(self, utilisateur):
        commande = Commande.objects.create(
            subtotal_ht=Decimal("100.00"), tax_amount=Decimal("20.00"),
            total=Decimal("120.00"), nom="Client A", email="a@example.com",
            address="1 rue du Test", ville="Brest", pays="France", zipcode="29200",
            stripe_checkout_session_id=f"cs_test_{Commande.objects.count()}",
            payment_reference="pi_test_secret",
            user=utilisateur,
        )
        OrderItem.objects.create(
            commande=commande, product=self.produit, price=Decimal("100.00"), quantity=1,
        )
        return commande

    def authentifier(self, utilisateur):
        """Authentifie les requêtes suivantes par jeton, comme un client de l'API."""
        jeton = Token.objects.create(user=utilisateur)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {jeton.key}")

    # --- Consultation ---------------------------------------------------------

    def test_le_proprietaire_voit_ses_commandes(self):
        """GET /api/v1/orders/ renvoie uniquement les commandes de l'utilisateur."""
        self.authentifier(self.proprietaire)
        reponse = self.client.get("/api/v1/orders/")
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual([c["id"] for c in reponse.json()], [self.commande.id])

    def test_commandes_triees_de_la_plus_recente_a_la_plus_ancienne(self):
        """La liste commence par la dernière commande passée."""
        recente = self.creer_commande(self.proprietaire)
        self.authentifier(self.proprietaire)
        reponse = self.client.get(url("order-list"))
        self.assertEqual([c["id"] for c in reponse.json()], [recente.id, self.commande.id])

    def test_les_commandes_d_autrui_absentes_de_la_liste(self):
        """La commande d'un autre utilisateur n'apparaît pas dans la liste."""
        self.authentifier(self.autre)
        ids = [c["id"] for c in self.client.get(url("order-list")).json()]
        self.assertNotIn(self.commande.id, ids)
        self.assertEqual(ids, [self.commande_d_autrui.id])

    def test_le_proprietaire_consulte_sa_commande(self):
        """Le détail expose le suivi de la commande et ses lignes."""
        self.authentifier(self.proprietaire)
        reponse = self.client.get(url("order-detail", pk=self.commande.id))
        self.assertEqual(reponse.status_code, 200)
        donnees = reponse.json()
        self.assertEqual(donnees["id"], self.commande.id)
        self.assertEqual(donnees["total"], "120.00")
        self.assertEqual(donnees["status"], "pending")
        self.assertEqual(donnees["payment_status"], "pending")
        self.assertEqual(donnees["items"], [
            {"product": self.produit.id, "title": "Casque", "price": "100.00", "quantity": 1},
        ])

    def test_aucune_donnee_personnelle_ni_interne_exposee(self):
        """Ni coordonnées, ni identifiants Stripe, ni indicateurs internes."""
        self.authentifier(self.proprietaire)
        donnees = self.client.get(url("order-detail", pk=self.commande.id)).json()
        self.assertEqual(
            set(donnees),
            {"id", "date", "status", "payment_status", "subtotal_ht", "tax_amount", "total", "items"},
        )
        self.assertNotIn("pi_test_secret", str(donnees))
        self.assertNotIn("a@example.com", str(donnees))

    def test_produit_supprime_reste_lisible(self):
        """Une ligne dont le produit a été supprimé garde un libellé."""
        self.produit.delete()
        self.authentifier(self.proprietaire)
        items = self.client.get(url("order-detail", pk=self.commande.id)).json()["items"]
        self.assertEqual(items, [
            {"product": None, "title": "Produit supprimé", "price": "100.00", "quantity": 1},
        ])

    def test_commande_d_autrui_introuvable(self):
        """La commande d'autrui répond 404, et non 403 qui confirmerait son existence."""
        self.authentifier(self.autre)
        reponse = self.client.get(url("order-detail", pk=self.commande.id))
        self.assertEqual(reponse.status_code, 404)

    def test_commande_d_autrui_et_commande_inexistante_indiscernables(self):
        """Même réponse pour la commande d'autrui et pour un identifiant inexistant."""
        self.authentifier(self.autre)
        autrui = self.client.get(url("order-detail", pk=self.commande.id))
        inexistante = self.client.get(url("order-detail", pk=999999))
        self.assertEqual(autrui.status_code, inexistante.status_code)
        self.assertEqual(autrui.json(), inexistante.json())

    def test_commande_sans_utilisateur_inaccessible(self):
        """Une commande orpheline (user=None) n'est visible de personne."""
        orpheline = self.creer_commande(None)
        self.authentifier(self.proprietaire)
        self.assertEqual(self.client.get(url("order-detail", pk=orpheline.id)).status_code, 404)
        ids = [c["id"] for c in self.client.get(url("order-list")).json()]
        self.assertNotIn(orpheline.id, ids)

    def test_session_du_site_donne_le_meme_acces(self):
        """Connecté au site (session), l'utilisateur ne voit aussi que ses commandes."""
        self.client.force_login(self.autre)
        self.assertEqual(self.client.get(url("order-detail", pk=self.commande.id)).status_code, 404)
        ids = [c["id"] for c in self.client.get(url("order-list")).json()]
        self.assertEqual(ids, [self.commande_d_autrui.id])

    # --- Authentification -----------------------------------------------------

    def test_visiteur_anonyme_refuse(self):
        """Sans authentification, liste et détail répondent 401, même en lecture."""
        self.assertEqual(self.client.get("/api/v1/orders/").status_code, 401)
        self.assertEqual(self.client.get(url("order-detail", pk=self.commande.id)).status_code, 401)

    # --- Lecture seule ------------------------------------------------------

    def test_ecriture_refusee_meme_sur_sa_propre_commande(self):
        """POST, PUT, PATCH et DELETE répondent 405 : les commandes naissent au paiement."""
        self.authentifier(self.proprietaire)
        liste = url("order-list")
        detail = url("order-detail", pk=self.commande.id)

        self.assertEqual(self.client.post(liste, {"total": "1.00"}, format="json").status_code, 405)
        self.assertEqual(self.client.put(detail, {"total": "1.00"}, format="json").status_code, 405)
        self.assertEqual(self.client.patch(detail, {"status": "delivered"}, format="json").status_code, 405)
        self.assertEqual(self.client.delete(detail).status_code, 405)

        self.commande.refresh_from_db()
        self.assertEqual(self.commande.total, Decimal("120.00"))
        self.assertEqual(self.commande.status, "pending")
        self.assertEqual(Commande.objects.count(), 2)


class LimitationDeDebitTest(ApiTestCase):
    """Limitation de débit (dette 4.9) : 429 au-delà du seuil.

    Les seuils sont abaissés le temps du test. override_settings ne suffit
    pas : DRF lit DEFAULT_THROTTLE_RATES une seule fois, à l'import, dans
    l'attribut de classe THROTTLE_RATES. C'est lui qui est remplacé.
    """
    SEUILS_DE_TEST = {"anon": "3/min", "user": "5/min"}

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        remplacement = patch.object(SimpleRateThrottle, "THROTTLE_RATES", self.SEUILS_DE_TEST)
        remplacement.start()
        self.addCleanup(remplacement.stop)

    def test_seuils_de_production(self):
        """60 requêtes par minute pour un visiteur, 1000 pour un utilisateur."""
        taux = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
        self.assertEqual(taux, {"anon": "60/min", "user": "1000/min"})

    def test_visiteur_au_dela_du_seuil_recoit_429(self):
        """La 4e requête anonyme de la minute répond 429, avec Retry-After."""
        for _ in range(3):
            self.assertEqual(self.client.get(url("product-list")).status_code, 200)
        reponse = self.client.get(url("product-list"))
        self.assertEqual(reponse.status_code, 429)
        self.assertIn("Retry-After", reponse)

    def test_utilisateur_au_dela_du_seuil_recoit_429(self):
        """Authentifié, la limite est celle du compte, plus haute que celle des visiteurs."""
        utilisateur = User.objects.create_user(username="client", password=MOT_DE_PASSE)
        self.client.force_authenticate(utilisateur)
        for _ in range(5):
            self.assertEqual(self.client.get(url("order-list")).status_code, 200)
        self.assertEqual(self.client.get(url("order-list")).status_code, 429)

    def test_demandes_de_jeton_limitees(self):
        """La vue de jeton de DRF n'est pas limitée par défaut : ici, elle l'est.

        Sans limite, elle permettrait d'essayer des mots de passe à volonté.
        """
        User.objects.create_user(username="client", password=MOT_DE_PASSE)
        for _ in range(3):
            reponse = self.client.post(url("token"), {"username": "client", "password": "faux"}, format="json")
            self.assertEqual(reponse.status_code, 400)
        reponse = self.client.post(url("token"), {"username": "client", "password": MOT_DE_PASSE}, format="json")
        self.assertEqual(reponse.status_code, 429)
        self.assertFalse(Token.objects.exists())

    def test_visiteurs_comptes_par_adresse_du_client(self):
        """Derrière l'Ingress, chaque client a son compteur : l'adresse retenue
        est la dernière de X-Forwarded-For, celle ajoutée par l'Ingress."""
        for _ in range(3):
            self.client.get(url("product-list"), HTTP_X_FORWARDED_FOR="203.0.113.1")
        bloque = self.client.get(url("product-list"), HTTP_X_FORWARDED_FOR="203.0.113.1")
        autre = self.client.get(url("product-list"), HTTP_X_FORWARDED_FOR="203.0.113.2")
        self.assertEqual(bloque.status_code, 429)
        self.assertEqual(autre.status_code, 200)

    def test_adresse_forgee_par_le_client_ne_contourne_pas_la_limite(self):
        """Une adresse ajoutée en tête de X-Forwarded-For par le client est ignorée."""
        for i in range(3):
            self.client.get(url("product-list"), HTTP_X_FORWARDED_FOR=f"10.0.0.{i}, 203.0.113.1")
        reponse = self.client.get(url("product-list"), HTTP_X_FORWARDED_FOR="10.0.0.99, 203.0.113.1")
        self.assertEqual(reponse.status_code, 429)


class DocumentationApiTest(ApiTestCase):
    """Schéma OpenAPI et Swagger UI, sous /api/v1/."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def test_schema_openapi_decrit_les_routes(self):
        """GET /api/v1/schema/ renvoie un document OpenAPI 3 avec toutes les routes."""
        reponse = self.client.get(url("schema"), {"format": "json"})
        self.assertEqual(reponse.status_code, 200)
        schema = reponse.json()
        self.assertTrue(schema["openapi"].startswith("3."))
        self.assertEqual(schema["info"]["title"], "API Dilane Shop")
        # drf-spectacular ajoute la version d'URL : « 1.0.0 (v1) »
        self.assertEqual(schema["info"]["version"], "1.0.0 (v1)")
        for chemin in [
            "/api/v1/products/", "/api/v1/products/{id}/",
            "/api/v1/categories/", "/api/v1/categories/{id}/",
            "/api/v1/orders/", "/api/v1/orders/{id}/",
            "/api/v1/auth/token/",
        ]:
            self.assertIn(chemin, schema["paths"])

    def test_schema_ne_documente_que_la_lecture_des_ressources(self):
        """Le catalogue et les commandes n'exposent que GET dans le schéma."""
        schema = self.client.get(url("schema"), {"format": "json"}).json()
        for chemin, operations in schema["paths"].items():
            if chemin != "/api/v1/auth/token/":
                self.assertEqual(set(operations) - {"parameters"}, {"get"}, chemin)

    def test_swagger_ui_servi(self):
        """GET /api/v1/docs/ renvoie la page HTML de Swagger UI."""
        reponse = self.client.get(url("docs"))
        self.assertEqual(reponse.status_code, 200)
        self.assertTrue(reponse["Content-Type"].startswith("text/html"))
        self.assertContains(reponse, 'id="swagger-ui"')

    def test_swagger_ui_compatible_avec_la_csp(self):
        """Aucun script inline : chaque script vient de jsdelivr ou du site.

        La CSP n'autorise que 'self', les jetons et quelques CDN. Un script
        inline sans jeton serait bloqué, et la page resterait blanche.
        """
        page = self.client.get(url("docs")).content.decode()
        scripts = re.findall(r"<script([^>]*)>(.*?)</script>", page, re.S)
        self.assertTrue(scripts)
        for attributs, contenu in scripts:
            self.assertEqual(contenu.strip(), "", "script inline")
            source = re.search(r'src="([^"]+)"', attributs).group(1)
            self.assertTrue(
                source.startswith("https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.33.0/")
                or source.startswith("/api/v1/docs/"),
                source,
            )
        self.assertNotIn("unpkg.com", page)
        self.assertIn(settings.SPECTACULAR_SETTINGS["SWAGGER_UI_DIST"], page)

    def test_script_d_amorcage_servi_par_le_site(self):
        """Le script d'amorçage de Swagger UI est un fichier du site, pointant vers le schéma."""
        reponse = self.client.get(url("docs"), {"script": ""})
        self.assertEqual(reponse.status_code, 200)
        self.assertTrue(reponse["Content-Type"].startswith("application/javascript"))
        self.assertIn("/api/v1/schema/", reponse.content.decode())
