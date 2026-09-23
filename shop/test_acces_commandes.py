"""Tests du contrôle d'accès aux commandes (dette 2.1, issue #70).

Un client ne doit pouvoir consulter, confirmer ou annuler que ses propres
commandes. La commande d'autrui répond 404 et non 403 : un 403 confirmerait
qu'elle existe, et les identifiants étant séquentiels, permettrait de
recenser les commandes du site.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Category, Commande, OrderItem, Product

User = get_user_model()


class AccesAuxCommandesTest(TestCase):

    def setUp(self):
        self.proprietaire = User.objects.create_user(username="proprietaire", email="a@example.com")
        self.autre = User.objects.create_user(username="autre", email="b@example.com")
        categorie = Category.objects.create(name="Audio")
        self.produit = Product.objects.create(
            title="Casque", price=Decimal("100.00"), description="Test",
            category=categorie, stock=10,
        )
        self.commande = self.creer_commande(self.proprietaire)

    def creer_commande(self, utilisateur):
        commande = Commande.objects.create(
            total=Decimal("120.00"), nom="Client A", email="a@example.com",
            address="1 rue du Test", ville="Brest", pays="France", zipcode="29200",
            user=utilisateur,
        )
        OrderItem.objects.create(
            commande=commande, product=self.produit, price=Decimal("100.00"), quantity=1,
        )
        return commande

    def url_confirmation(self, commande):
        return reverse("confirmation_order", kwargs={"order_id": commande.id})

    # --- Consultation ---------------------------------------------------------

    def test_le_proprietaire_consulte_sa_commande(self):
        self.client.force_login(self.proprietaire)
        reponse = self.client.get(self.url_confirmation(self.commande))
        self.assertEqual(reponse.status_code, 200)

    def test_commande_d_autrui_introuvable(self):
        self.client.force_login(self.autre)
        reponse = self.client.get(self.url_confirmation(self.commande))
        self.assertEqual(reponse.status_code, 404)

    def test_visiteur_non_connecte_renvoye_vers_la_connexion(self):
        reponse = self.client.get(self.url_confirmation(self.commande))
        self.assertEqual(reponse.status_code, 302)
        self.assertIn("/connexion/", reponse.url)

    def test_confirmation_sans_numero_n_expose_pas_la_commande_d_autrui(self):
        """Avant correction : la dernière commande du site, quel que soit
        son propriétaire."""
        self.client.force_login(self.autre)
        reponse = self.client.get(reverse("confirmation"))
        self.assertNotEqual(reponse.context["commande"], self.commande)

    def test_commande_sans_utilisateur_inaccessible(self):
        orpheline = self.creer_commande(None)
        self.client.force_login(self.proprietaire)
        reponse = self.client.get(self.url_confirmation(orpheline))
        self.assertEqual(reponse.status_code, 404)

    # --- Retour de paiement ---------------------------------------------------

    def test_retour_de_paiement_sur_commande_d_autrui_introuvable(self):
        self.client.force_login(self.autre)
        reponse = self.client.get(reverse("payment_success"), {"order_id": self.commande.id})
        self.assertEqual(reponse.status_code, 404)

    # --- Annulation -----------------------------------------------------------

    def test_annulation_de_la_commande_d_autrui_impossible(self):
        self.client.force_login(self.autre)
        self.client.get(reverse("payment_cancel"), {"order_id": self.commande.id})
        self.commande.refresh_from_db()
        self.assertEqual(self.commande.payment_status, "pending")

    def test_le_proprietaire_annule_sa_commande(self):
        self.client.force_login(self.proprietaire)
        self.client.get(reverse("payment_cancel"), {"order_id": self.commande.id})
        self.commande.refresh_from_db()
        self.assertEqual(self.commande.payment_status, "cancelled")
