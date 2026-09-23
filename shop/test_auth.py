"""Tests de l'authentification : backend de connexion par email et formulaires.

Le hacheur MD5 remplace l'algorithme de production uniquement pendant ces
tests : il est volontairement lent en production, ce qui ralentirait la
suite sans rien apporter à ce que l'on vérifie ici.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from .backends import EmailOrUsernameModelBackend
from .forms import EmailAuthenticationForm, SignupForm

User = get_user_model()
HACHEUR_RAPIDE = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@override_settings(PASSWORD_HASHERS=HACHEUR_RAPIDE)
class ConnexionParEmailTest(TestCase):

    def setUp(self):
        self.backend = EmailOrUsernameModelBackend()
        self.user = User.objects.create_user(
            username="dilane", email="client@example.com", password="passe-correct",
        )

    def connecter(self, identifiant, mot_de_passe="passe-correct"):
        return self.backend.authenticate(None, username=identifiant, password=mot_de_passe)

    def test_connexion_par_email(self):
        self.assertEqual(self.connecter("client@example.com"), self.user)

    def test_connexion_par_email_insensible_a_la_casse(self):
        self.assertEqual(self.connecter("Client@EXAMPLE.com"), self.user)

    def test_connexion_par_nom_utilisateur(self):
        self.assertEqual(self.connecter("dilane"), self.user)

    def test_refuse_un_mauvais_mot_de_passe(self):
        self.assertIsNone(self.connecter("client@example.com", "passe-faux"))

    def test_refuse_un_email_inconnu(self):
        self.assertIsNone(self.connecter("inconnu@example.com"))

    def test_refuse_un_compte_desactive(self):
        self.user.is_active = False
        self.user.save()
        self.assertIsNone(self.connecter("client@example.com"))

    def test_doublon_email_bloque_le_second_compte(self):
        """Comportement actuel, documenté : en cas de doublon, le compte le
        plus ancien est retenu. Le second titulaire ne peut plus se connecter
        par email. Aucune usurpation, mais un blocage (dette 2.7)."""
        second = User.objects.create_user(
            username="homonyme", email="client@example.com", password="passe-second",
        )
        self.assertIsNone(self.connecter("client@example.com", "passe-second"))
        self.assertEqual(self.connecter("homonyme", "passe-second"), second)

    def test_email_inconnu_declenche_quand_meme_le_hachage(self):
        """Sans hachage pour un compte inexistant, la réponse est plus rapide :
        un attaquant peut chronométrer pour savoir quels emails sont inscrits
        (dette 3.4). Le backend standard de Django applique cette parade."""
        with patch.object(User, "set_password") as hachage:
            self.connecter("inconnu@example.com", "un-mot-de-passe")
        hachage.assert_called_once_with("un-mot-de-passe")


@override_settings(PASSWORD_HASHERS=HACHEUR_RAPIDE)
class FormulairesTest(TestCase):

    MOT_DE_PASSE = "Solide-et-Long-2026!"

    def inscription(self, username, email):
        return SignupForm(data={
            "username": username, "email": email,
            "password1": self.MOT_DE_PASSE, "password2": self.MOT_DE_PASSE,
        })

    def test_inscription_enregistre_email_en_minuscules(self):
        form = self.inscription("nouveau", "Nouveau@Example.COM")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().email, "nouveau@example.com")

    def test_inscription_refuse_un_email_deja_utilise_quelle_que_soit_la_casse(self):
        User.objects.create_user(username="existant", email="pris@example.com", password="x")
        form = self.inscription("autre", "PRIS@example.com")
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_message_email_deja_utilise_accentue(self):
        User.objects.create_user(username="existant", email="pris@example.com", password="x")
        form = self.inscription("autre", "pris@example.com")
        form.is_valid()
        self.assertEqual(form.errors["email"], ["Cet email est déjà utilisé."])

    def test_connexion_refuse_un_identifiant_qui_n_est_pas_un_email(self):
        form = EmailAuthenticationForm(data={"username": "pas-un-email", "password": "x"})
        self.assertFalse(form.is_valid())
        self.assertIn("username", form.errors)

    def test_inscription_exige_un_email(self):
        form = self.inscription("sans-email", "")
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)
