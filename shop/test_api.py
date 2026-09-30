"""Tests de l'API REST interne, fondations (issue #56).

Vérifié ici :
- le catalogue est lisible sans authentification, sous /api/v1/ ;
- il est en lecture seule : aucune écriture possible, même authentifié ;
- un jeton s'obtient avec des identifiants valides, et authentifie les
  requêtes suivantes ;
- seule la version v1 existe.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from .models import Category, Product

User = get_user_model()
MOT_DE_PASSE = "Mot-de-passe-de-test-42"


def url(nom, **kwargs):
    """Adresse d'une route de l'API, version comprise."""
    return reverse(f"api:{nom}", kwargs={"version": "v1", **kwargs})


class CatalogueApiTest(TestCase):

    def setUp(self):
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
        """La racine /api/v1/ liste les routes du catalogue."""
        reponse = self.client.get("/api/v1/")
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(set(reponse.json()), {"products", "categories"})

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


class JetonApiTest(TestCase):

    def setUp(self):
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
