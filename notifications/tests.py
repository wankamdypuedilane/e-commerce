"""Tests de l'email de confirmation de commande (app notifications, #49)."""
from decimal import Decimal

from django.core import mail
from django.test import TestCase

from catalog.models import Category, Product
from orders.models import Commande, OrderItem

from .services import build_order_items_payload, send_order_confirmation_email


class EmailDeConfirmationTest(TestCase):

    def setUp(self):
        categorie = Category.objects.create(name="Audio")
        self.produit = Product.objects.create(
            title="Casque", price=Decimal("99.90"), description="", category=categorie, stock=5,
        )
        self.commande = Commande.objects.create(
            total=Decimal("204.80"), nom="Jean", email="jean@example.com",
            address="1 rue", ville="Brest", pays="France", zipcode="29200",
        )
        OrderItem.objects.create(commande=self.commande, product=self.produit,
                                 price=Decimal("99.90"), quantity=2)
        OrderItem.objects.create(commande=self.commande, product=None,
                                 price=Decimal("5.00"), quantity=1)

    def test_email_envoye_en_texte_et_en_html(self):
        self.assertTrue(send_order_confirmation_email(self.commande))

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ["jean@example.com"])
        self.assertEqual(email.subject, f"Confirmation de commande #{self.commande.id}")
        self.assertIn("Casque x2", email.body)
        self.assertEqual(email.alternatives[0][1], "text/html")
        self.assertIn("Casque", email.alternatives[0][0])

    def test_un_seul_envoi_par_commande(self):
        """Le retour de paiement et la page de confirmation appellent tous deux l'envoi."""
        self.assertTrue(send_order_confirmation_email(self.commande))
        self.assertFalse(send_order_confirmation_email(self.commande))

        self.assertEqual(len(mail.outbox), 1)
        self.commande.refresh_from_db()
        self.assertTrue(self.commande.confirmation_email_sent)

    def test_aucun_envoi_sans_adresse(self):
        self.commande.email = ""
        self.assertFalse(send_order_confirmation_email(self.commande))
        self.assertEqual(mail.outbox, [])

    def test_produit_supprime_garde_sa_ligne(self):
        lignes = build_order_items_payload(self.commande)
        self.assertEqual(
            [(l["title"], l["quantity"], l["subtotal"]) for l in lignes],
            [("Casque", 2, "199.80"), ("Produit supprimé", 1, "5.00")],
        )
