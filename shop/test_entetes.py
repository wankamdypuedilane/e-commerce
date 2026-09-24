"""Tests des en-têtes de sécurité HTTP (issue #38).

Vérifie la politique de sécurité du contenu, le jeton porté par chaque
script écrit dans la page, l'en-tête Permissions-Policy, et que les
protections envoyées par défaut par Django restent en place.
"""
import re

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Category, Product


class EnTetesDeSecuriteTest(TestCase):

    def setUp(self):
        self.reponse = self.client.get("/")

    def politique(self):
        return self.reponse.headers.get("Content-Security-Policy", "")

    def test_politique_appliquee_et_non_seulement_observee(self):
        self.assertIn("Content-Security-Policy", self.reponse.headers)
        self.assertNotIn("Content-Security-Policy-Report-Only", self.reponse.headers)

    def test_chaque_script_en_ligne_porte_le_jeton_de_la_page(self):
        jeton = re.search(r"'nonce-([^']+)'", self.politique())
        self.assertIsNotNone(jeton, "Aucun jeton dans la règle script-src")
        html = self.reponse.content.decode()
        scripts_en_ligne = [b for b in re.findall(r"<script\b[^>]*>", html) if "src=" not in b]
        # Sans script en ligne, le test ne vérifierait rien : on l'exige
        self.assertTrue(scripts_en_ligne, "Aucun script en ligne trouvé dans la page")
        for balise in scripts_en_ligne:
            with self.subTest(balise=balise):
                self.assertIn(f'nonce="{jeton.group(1)}"', balise)

    def test_directives_essentielles(self):
        for directive in ("frame-ancestors 'none'", "object-src 'none'",
                          "base-uri 'self'", "https://checkout.stripe.com"):
            with self.subTest(directive=directive):
                self.assertIn(directive, self.politique())

    def test_permissions_policy(self):
        politique = self.reponse.headers.get("Permissions-Policy", "")
        for fonction in ("camera=()", "microphone=()", "geolocation=()"):
            with self.subTest(fonction=fonction):
                self.assertIn(fonction, politique)

    def test_en_tetes_par_defaut_conserves(self):
        self.assertEqual(self.reponse.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(self.reponse.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(self.reponse.headers.get("Referrer-Policy"), "same-origin")


class JetonSurChaquePageTest(TestCase):
    """Chaque page, et pas seulement l'accueil : un script oublié sans jeton
    serait bloqué en production, et la fonctionnalité cesserait de marcher."""

    def setUp(self):
        categorie = Category.objects.create(name="Audio")
        self.produit = Product.objects.create(
            title="Casque", price=Decimal("10.00"), description="Test",
            category=categorie, stock=5,
        )
        self.client.force_login(
            get_user_model().objects.create_user(username="client", email="client@example.com")
        )

    def test_scripts_en_ligne_portent_le_jeton_sur_chaque_page(self):
        pages = {
            "accueil": reverse("home"),
            "fiche produit": reverse("detail", args=[self.produit.id]),
            "commande": reverse("checkout"),
            "confirmation": reverse("confirmation"),
        }
        for nom, url in pages.items():
            with self.subTest(page=nom):
                reponse = self.client.get(url)
                self.assertEqual(reponse.status_code, 200)
                jeton = re.search(r"'nonce-([^']+)'", reponse.headers.get("Content-Security-Policy", ""))
                self.assertIsNotNone(jeton, "Aucun jeton dans la politique")
                balises = [b for b in re.findall(r"<script\b[^>]*>", reponse.content.decode()) if "src=" not in b]
                self.assertTrue(balises, "Aucun script en ligne dans la page")
                for balise in balises:
                    self.assertIn(f'nonce="{jeton.group(1)}"', balise)
