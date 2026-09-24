"""Tests de l'administration : affichage du panier d'une commande.

La méthode panier_lisible insère les titres des produits dans du HTML.
Un titre saisi par un administrateur ne doit jamais être exécuté dans le
navigateur d'un autre (script intersite stocké, dette 3.3, signalé par
Bandit : règles B308 et B703).
"""
from decimal import Decimal

from django.contrib import admin
from django.test import TestCase

from .models import Category, Commande, OrderItem, Product


class PanierLisibleTest(TestCase):

    def setUp(self):
        # Récupère l'administration réellement enregistrée pour Commande
        self.admin_commande = admin.site._registry[Commande]
        self.categorie = Category.objects.create(name="Audio")
        self.commande = Commande.objects.create(
            total=Decimal("20.00"), nom="Client", email="client@example.com",
            address="1 rue du Test", ville="Brest", pays="France", zipcode="29200",
        )

    def ajouter_article(self, titre):
        produit = Product.objects.create(
            title=titre, price=Decimal("10.00"), description="Test",
            category=self.categorie, stock=5,
        )
        OrderItem.objects.create(
            commande=self.commande, product=produit,
            price=Decimal("10.00"), quantity=2,
        )

    def test_titre_malveillant_echappe(self):
        self.ajouter_article('<script>alert("xss")</script>')
        html = str(self.admin_commande.panier_lisible(self.commande))
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_mise_en_forme_conservee(self):
        self.ajouter_article("Casque")
        html = str(self.admin_commande.panier_lisible(self.commande))
        self.assertIn("<b>Casque</b> x2 — 20.00 €<br>", html)
