"""Tests de la construction de la session de paiement Stripe.

Invariant central : la somme des lignes envoyées à Stripe, en centimes,
égale exactement le total TTC enregistré sur la commande. Aucune base de
données : la commande n'est utilisée que pour son identifiant.
"""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase, override_settings

from .services import build_stripe_line_items, calculate_tax_totals, create_stripe_checkout_session

CLES_STRIPE = dict(STRIPE_SECRET_KEY="sk_test_fake", STRIPE_PUBLIC_KEY="pk_test_fake")


def article(prix, quantite, titre="Produit"):
    """Même forme que les éléments construits par la vue checkout."""
    return {"title": titre, "price": str(Decimal(prix)), "quantity": quantite}


def total_en_centimes(lignes):
    return sum(l["price_data"]["unit_amount"] * l["quantity"] for l in lignes)


class LignesStripeTest(SimpleTestCase):

    def test_conversion_exacte_en_centimes(self):
        lignes = build_stripe_line_items([article("19.99", 1)])
        self.assertEqual(lignes[0]["price_data"]["unit_amount"], 1999)
        self.assertEqual(lignes[0]["price_data"]["currency"], "eur")

    def test_ligne_de_tva_ajoutee(self):
        lignes = build_stripe_line_items(
            [article("20.00", 1)], tax_amount=Decimal("4.00"), rate_percent=Decimal("20"),
        )
        self.assertEqual(len(lignes), 2)
        self.assertEqual(lignes[1]["price_data"]["product_data"]["name"], "TVA (20%)")
        self.assertEqual(lignes[1]["price_data"]["unit_amount"], 400)

    def test_aucune_ligne_de_tva_si_montant_nul(self):
        lignes = build_stripe_line_items([article("20.00", 1)], tax_amount=Decimal("0.00"))
        self.assertEqual(len(lignes), 1)

    @override_settings(TAX_RATE_PERCENT="5.5")
    def test_somme_envoyee_a_stripe_egale_le_total_ttc(self):
        articles = [article("19.99", 3), article("0.10", 7), article("249.00", 1)]
        sous_total = sum(Decimal(a["price"]) * a["quantity"] for a in articles)
        taux, tva, ttc = calculate_tax_totals(sous_total)

        lignes = build_stripe_line_items(articles, tax_amount=tva, rate_percent=taux)

        self.assertEqual(ttc, Decimal("326.70"))
        self.assertEqual(total_en_centimes(lignes), 32670)


@override_settings(**CLES_STRIPE)
class SessionStripeTest(SimpleTestCase):

    def setUp(self):
        self.requete = RequestFactory().post("/checkout")
        self.commande = SimpleNamespace(id=42)
        self.articles = [article("100.00", 2)]

    @patch("stripe.checkout.Session.create")
    def test_session_creee_avec_les_bons_parametres(self, creation):
        create_stripe_checkout_session(
            self.requete, self.commande, self.articles, "client@example.com",
            tax_amount=Decimal("40.00"), rate_percent=Decimal("20"),
        )
        parametres = creation.call_args.kwargs

        self.assertEqual(parametres["mode"], "payment")
        self.assertEqual(parametres["customer_email"], "client@example.com")
        self.assertEqual(parametres["metadata"], {"commande_id": "42"})
        self.assertIn("session_id={CHECKOUT_SESSION_ID}", parametres["success_url"])
        self.assertIn("order_id=42", parametres["success_url"])
        self.assertIn("order_id=42", parametres["cancel_url"])
        self.assertEqual(total_en_centimes(parametres["line_items"]), 24000)

    @override_settings(STRIPE_SECRET_KEY="")
    @patch("stripe.checkout.Session.create")
    def test_aucune_session_si_stripe_non_configure(self, creation):
        resultat = create_stripe_checkout_session(
            self.requete, self.commande, self.articles, "client@example.com",
        )
        self.assertIsNone(resultat)
        creation.assert_not_called()
