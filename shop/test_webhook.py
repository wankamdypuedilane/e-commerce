"""Tests du webhook Stripe.

Le webhook est le seul code qui décrémente le stock en production. Ces tests
exercent la vraie vérification de signature : chaque requête est signée avec
le secret de test, comme le ferait Stripe. Seul l'appel réseau vers l'API
Stripe (Session.retrieve) est simulé ; tout le reste du code s'exécute.
"""
import hashlib
import hmac
import json
import time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import stripe
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Category, Commande, OrderItem, Product

SECRET_WEBHOOK = "whsec_test_secret"
SESSION_ID = "cs_test_123"


def signer(payload, secret=SECRET_WEBHOOK):
    """Calcule l'en-tête Stripe-Signature, selon le format documenté par Stripe."""
    horodatage = int(time.time())
    contenu = f"{horodatage}.".encode() + payload
    signature = hmac.new(secret.encode(), contenu, hashlib.sha256).hexdigest()
    return f"t={horodatage},v1={signature}"


def evenement(type_evenement, session_id=SESSION_ID):
    """Construit un événement Stripe minimal, au format JSON attendu par la bibliothèque."""
    return json.dumps({
        "id": "evt_test_1",
        "object": "event",
        "api_version": getattr(stripe, "api_version", None),
        "type": type_evenement,
        "data": {"object": {"id": session_id, "object": "checkout.session", "metadata": {}}},
    }).encode()


def session_stripe(statut):
    """Réponse simulée de Session.retrieve : seuls les champs lus par le code."""
    return SimpleNamespace(payment_status=statut, payment_intent="pi_test_123")


@override_settings(
    STRIPE_SECRET_KEY="sk_test_fake",
    STRIPE_PUBLIC_KEY="pk_test_fake",
    STRIPE_WEBHOOK_SECRET=SECRET_WEBHOOK,
)
class StripeWebhookTest(TestCase):

    def setUp(self):
        categorie = Category.objects.create(name="Audio")
        self.produit = Product.objects.create(
            title="Casque", price=Decimal("100.00"), description="Test",
            category=categorie, stock=10,
        )
        self.commande = Commande.objects.create(
            total=Decimal("240.00"), nom="Client Test", email="client@example.com",
            address="1 rue du Test", ville="Brest", pays="France", zipcode="29200",
            stripe_checkout_session_id=SESSION_ID,
        )
        OrderItem.objects.create(
            commande=self.commande, product=self.produit,
            price=Decimal("100.00"), quantity=2,
        )
        self.url = reverse("stripe_webhook")

    def envoyer(self, type_evenement="checkout.session.completed", secret=SECRET_WEBHOOK):
        payload = evenement(type_evenement)
        return self.client.post(
            self.url, data=payload, content_type="application/json",
            HTTP_STRIPE_SIGNATURE=signer(payload, secret),
        )

    def rafraichir(self):
        self.commande.refresh_from_db()
        self.produit.refresh_from_db()

    # --- Sécurité -----------------------------------------------------------

    @override_settings(STRIPE_WEBHOOK_SECRET="")
    def test_refuse_si_secret_absent(self):
        with self.assertLogs("shop", level="ERROR"):
            reponse = self.envoyer()
        self.assertEqual(reponse.status_code, 400)
        self.rafraichir()
        self.assertEqual(self.produit.stock, 10)

    def test_refuse_signature_invalide(self):
        with self.assertLogs("shop", level="ERROR"):
            reponse = self.envoyer(secret="whsec_mauvais_secret")
        self.assertEqual(reponse.status_code, 400)
        self.rafraichir()
        self.assertEqual(self.commande.payment_status, "pending")
        self.assertEqual(self.produit.stock, 10)

    # --- Paiement confirmé --------------------------------------------------

    @patch("stripe.checkout.Session.retrieve", return_value=session_stripe("paid"))
    def test_paiement_confirme_decremente_le_stock(self, _retrieve):
        reponse = self.envoyer()
        self.assertEqual(reponse.status_code, 200)
        self.rafraichir()
        self.assertEqual(self.commande.payment_status, "paid")
        self.assertEqual(self.commande.status, "confirmed")
        self.assertEqual(self.commande.payment_reference, "pi_test_123")
        self.assertTrue(self.commande.stock_deducted)
        self.assertEqual(self.produit.stock, 8)

    @patch("stripe.checkout.Session.retrieve", return_value=session_stripe("paid"))
    def test_evenement_recu_deux_fois_decremente_une_seule_fois(self, _retrieve):
        self.assertEqual(self.envoyer().status_code, 200)
        self.assertEqual(self.envoyer().status_code, 200)
        self.rafraichir()
        self.assertEqual(self.produit.stock, 8)

    @patch("stripe.checkout.Session.retrieve", return_value=session_stripe("paid"))
    def test_email_de_confirmation_envoye_une_seule_fois(self, _retrieve):
        self.envoyer()
        self.envoyer()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("client@example.com", mail.outbox[0].to)

    # --- Paiement non confirmé ----------------------------------------------

    @patch("stripe.checkout.Session.retrieve", return_value=session_stripe("unpaid"))
    def test_paiement_non_confirme_ne_touche_pas_au_stock(self, _retrieve):
        reponse = self.envoyer()
        self.assertEqual(reponse.status_code, 200)
        self.rafraichir()
        self.assertEqual(self.commande.payment_status, "processing")
        self.assertFalse(self.commande.stock_deducted)
        self.assertEqual(self.produit.stock, 10)
        self.assertEqual(len(mail.outbox), 0)

    def test_session_expiree_annule_la_commande(self):
        reponse = self.envoyer("checkout.session.expired")
        self.assertEqual(reponse.status_code, 200)
        self.rafraichir()
        self.assertEqual(self.commande.payment_status, "cancelled")
        self.assertEqual(self.produit.stock, 10)

    # --- Panne pendant le traitement ----------------------------------------

    @patch("stripe.checkout.Session.retrieve", side_effect=RuntimeError("Stripe indisponible"))
    def test_panne_pendant_le_traitement_renvoie_500(self, _retrieve):
        """Une panne doit produire un 500 pour que Stripe réessaie.

        Répondre 200 ferait croire à Stripe que l'événement est traité :
        il ne réessaierait jamais, et le paiement serait perdu côté boutique.
        Les réessais sont sans danger, le traitement étant idempotent.
        """
        with self.assertLogs("shop", level="ERROR"):
            reponse = self.envoyer()
        self.assertEqual(reponse.status_code, 500)
        self.rafraichir()
        self.assertEqual(self.produit.stock, 10)
