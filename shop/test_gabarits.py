"""Tests des gabarits après le nettoyage de l'issue #50 (dettes 3.5 et 3.6).

Vérifié ici :
- chaque gabarit du dépôt est bien celui que Django charge sous son nom :
  aucun fichier masqué par un gabarit de même nom trouvé avant lui, ce qui
  était le cas des dix gabarits morts supprimés ;
- les parcours de réinitialisation du mot de passe, du site et de
  l'administration, rendent toujours leurs pages ;
- les pages du panier chargent le script commun shop/panier.js, avec le
  jeton CSP, avant leur script propre.
"""
import re
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.contrib.staticfiles import finders
from django.core import mail
from django.template import TemplateDoesNotExist
from django.template.loader import get_template
from django.templatetags.static import static
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from catalog.models import Category, Product

User = get_user_model()
HACHEUR_RAPIDE = ["django.contrib.auth.hashers.MD5PasswordHasher"]
RACINE = Path(settings.BASE_DIR)

# Masqués par les gabarits par défaut de Django, mais cités par shop/urls.py
# pour l'email de réinitialisation du site : conservés et signalés dans
# l'issue #50, leur texte n'étant aujourd'hui jamais utilisé.
MASQUES_CONNUS = {
    "registration/password_reset_email.html",
    "registration/password_reset_subject.txt",
}


class ResolutionDesGabaritsTest(SimpleTestCase):
    """Django charge un gabarit par nom : le premier trouvé dans DIRS
    (templates/), puis dans les apps, dans l'ordre d'INSTALLED_APPS."""

    def gabarits_du_depot(self):
        for dossier in [RACINE / "templates", RACINE / "shop" / "templates"]:
            for fichier in sorted(dossier.rglob("*")):
                if fichier.is_file():
                    yield fichier.relative_to(dossier).as_posix(), fichier

    def test_aucun_gabarit_masque(self):
        """Chaque gabarit du dépôt est celui que Django charge sous son nom."""
        for nom, fichier in self.gabarits_du_depot():
            if nom in MASQUES_CONNUS:
                continue
            with self.subTest(nom=nom):
                self.assertEqual(Path(get_template(nom).origin.name).resolve(), fichier.resolve())

    def test_gabarits_admin_du_site_prioritaires(self):
        """Les pages admin personnalisées viennent de templates/admin/."""
        for nom in [
            "admin/login.html",
            "admin/password_reset_form.html",
            "admin/password_reset_done.html",
            "admin/password_reset_confirm.html",
            "admin/password_reset_complete.html",
        ]:
            with self.subTest(nom=nom):
                origine = Path(get_template(nom).origin.name).resolve()
                self.assertEqual(origine, (RACINE / "templates" / nom).resolve())

    def test_gabarit_profil_supprime(self):
        """La vue profil rend shop/mes_commandes.html ; shop/profil.html n'existe plus."""
        with self.assertRaises(TemplateDoesNotExist):
            get_template("shop/profil.html")


@override_settings(PASSWORD_HASHERS=HACHEUR_RAPIDE)
class ReinitialisationDuSiteTest(TestCase):
    """Les quatre étapes du parcours « mot de passe oublié » du site."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="client", email="client@example.com", password="Ancien-passe-42",
        )

    def test_formulaire(self):
        reponse = self.client.get(reverse("password_reset"))
        self.assertEqual(reponse.status_code, 200)
        self.assertTemplateUsed(reponse, "shop/password_reset_form.html")

    def test_demande_envoie_un_email_puis_page_envoye(self):
        reponse = self.client.post(
            reverse("password_reset"), {"email": "client@example.com"}, follow=True,
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertTemplateUsed(reponse, "shop/password_reset_done.html")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/reinitialisation/", mail.outbox[0].body)

    def test_page_envoye(self):
        reponse = self.client.get(reverse("password_reset_done"))
        self.assertEqual(reponse.status_code, 200)
        self.assertTemplateUsed(reponse, "shop/password_reset_done.html")

    def test_lien_valide_puis_nouveau_mot_de_passe(self):
        """Le lien de l'email mène au formulaire, qui change le mot de passe."""
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        jeton = default_token_generator.make_token(self.user)
        lien = reverse("password_reset_confirm", kwargs={"uidb64": uid, "token": jeton})

        reponse = self.client.get(lien, follow=True)
        self.assertEqual(reponse.status_code, 200)
        self.assertTemplateUsed(reponse, "shop/password_reset_confirm.html")
        self.assertTrue(reponse.context["validlink"])

        reponse = self.client.post(
            reponse.redirect_chain[-1][0],
            {"new_password1": "Nouveau-passe-42", "new_password2": "Nouveau-passe-42"},
            follow=True,
        )
        self.assertTemplateUsed(reponse, "shop/password_reset_complete.html")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Nouveau-passe-42"))

    def test_page_terminee(self):
        reponse = self.client.get(reverse("password_reset_complete"))
        self.assertEqual(reponse.status_code, 200)
        self.assertTemplateUsed(reponse, "shop/password_reset_complete.html")


@override_settings(PASSWORD_HASHERS=HACHEUR_RAPIDE)
class ReinitialisationAdminTest(TestCase):
    """Le parcours « mot de passe oublié » de l'administration."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="Ancien-passe-42",
        )

    def test_connexion_admin(self):
        reponse = self.client.get(reverse("admin:login"))
        self.assertEqual(reponse.status_code, 200)
        self.assertTemplateUsed(reponse, "admin/login.html")

    def test_formulaire_et_email(self):
        reponse = self.client.get(reverse("admin_password_reset"))
        self.assertEqual(reponse.status_code, 200)
        self.assertTemplateUsed(reponse, "admin/password_reset_form.html")

        reponse = self.client.post(
            reverse("admin_password_reset"), {"email": "admin@example.com"}, follow=True,
        )
        self.assertTemplateUsed(reponse, "admin/password_reset_done.html")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/admin/reset/", mail.outbox[0].body)

    def test_lien_valide_et_page_terminee(self):
        uid = urlsafe_base64_encode(force_bytes(self.admin.pk))
        jeton = default_token_generator.make_token(self.admin)
        lien = reverse("admin_password_reset_confirm", kwargs={"uidb64": uid, "token": jeton})

        reponse = self.client.get(lien, follow=True)
        self.assertEqual(reponse.status_code, 200)
        self.assertTemplateUsed(reponse, "admin/password_reset_confirm.html")

        reponse = self.client.get(reverse("admin_password_reset_complete"))
        self.assertEqual(reponse.status_code, 200)
        self.assertTemplateUsed(reponse, "admin/password_reset_complete.html")


@override_settings(PASSWORD_HASHERS=HACHEUR_RAPIDE)
class ScriptDuPanierTest(TestCase):
    """Le script commun du panier est chargé par les pages, dans le respect de la CSP."""

    def setUp(self):
        categorie = Category.objects.create(name="Audio")
        self.produit = Product.objects.create(
            title="Casque", price=Decimal("100.00"), description="Test",
            category=categorie, stock=3,
        )
        self.user = User.objects.create_user(username="client", password="Passe-42")

    def balise_panier(self, reponse):
        """Balise <script> qui charge shop/panier.js, ou None."""
        page = reponse.content.decode()
        adresse = re.escape(static("shop/panier.js"))
        return re.search(r'<script nonce="[^"]+" src="' + adresse + r'"></script>', page)

    def verifier(self, reponse):
        self.assertEqual(reponse.status_code, 200)
        balise = self.balise_panier(reponse)
        self.assertIsNotNone(balise, "script du panier absent, ou sans jeton CSP")
        page = reponse.content.decode()
        # Chargé avant l'amorçage du popover, qui l'utilise
        self.assertLess(balise.start(), page.index("Panier.initialiserPopover();"))

    def test_fichier_statique_present(self):
        self.assertIsNotNone(finders.find("shop/panier.js"))

    def test_accueil(self):
        reponse = self.client.get(reverse("home"))
        self.verifier(reponse)
        page = reponse.content.decode()
        # Le script de la page vient après le script commun, qu'il utilise
        self.assertLess(self.balise_panier(reponse).start(), page.index("Panier.initialiserPopover({ modifiable: true });"))

    def test_fiche_produit(self):
        self.verifier(self.client.get(reverse("detail", args=[self.produit.id])))

    def test_commande(self):
        self.client.force_login(self.user)
        reponse = self.client.get(reverse("checkout"))
        self.verifier(reponse)
        self.assertLess(self.balise_panier(reponse).start(), reponse.content.decode().index("var panier = Panier.contenu;"))

    def test_plus_de_logique_de_panier_en_double(self):
        """La gestion du popover et du stockage n'existe plus que dans panier.js."""
        self.client.force_login(self.user)
        for nom, args in [("home", []), ("detail", [self.produit.id]), ("checkout", [])]:
            with self.subTest(page=nom):
                page = self.client.get(reverse(nom, args=args)).content.decode()
                self.assertNotIn("new bootstrap.Popover", page)
                self.assertNotIn("localStorage.setItem", page)
