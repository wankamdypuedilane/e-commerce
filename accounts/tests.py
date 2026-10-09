"""Tests de la transition du moteur d'authentification vers accounts (#49).

Chaque session enregistre le chemin du moteur qui a authentifié
l'utilisateur. Le moteur a changé de chemin : les sessions ouvertes avant
le déploiement doivent rester valides, sans que l'ancien chemin serve à
authentifier qui que ce soit.
"""
from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY, get_user_model
from django.test import TestCase
from django.urls import reverse

from shop.backends import EmailOrUsernameModelBackend as AncienMoteur

ANCIEN = "shop.backends.EmailOrUsernameModelBackend"
NOUVEAU = "accounts.backends.EmailOrUsernameModelBackend"
MOT_DE_PASSE = "MotDePasse-Solide-42"


class TransitionDuMoteurTest(TestCase):

    def setUp(self):
        self.utilisateur = get_user_model().objects.create_user(
            "marie", "marie@example.com", MOT_DE_PASSE, is_staff=True, is_superuser=True,
        )

    def ouvrir_session(self, moteur):
        """Session telle que Django l'aurait écrite, avec le chemin donné."""
        session = self.client.session
        session[SESSION_KEY] = str(self.utilisateur.pk)
        session[BACKEND_SESSION_KEY] = moteur
        session[HASH_SESSION_KEY] = self.utilisateur.get_session_auth_hash()
        session.save()

    def test_le_nouveau_moteur_passe_en_premier(self):
        self.assertEqual(settings.AUTHENTICATION_BACKENDS[0], NOUVEAU)

    def test_session_ouverte_avant_le_deploiement_reste_connectee(self):
        self.ouvrir_session(ANCIEN)
        reponse = self.client.get(reverse("profil"))
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.context["user"], self.utilisateur)

    def test_administrateur_garde_l_acces_a_l_admin(self):
        self.ouvrir_session(ANCIEN)
        self.assertEqual(self.client.get("/admin/").status_code, 200)

    def test_l_ancien_chemin_n_authentifie_personne(self):
        """Sinon, chaque connexion ratée vérifierait le mot de passe deux fois."""
        self.assertIsNone(AncienMoteur().authenticate(None, username="marie", password=MOT_DE_PASSE))

    def test_la_connexion_enregistre_le_nouveau_chemin(self):
        self.client.post(reverse("connexion"), {"username": "marie@example.com", "password": MOT_DE_PASSE})
        self.assertEqual(self.client.session[BACKEND_SESSION_KEY], NOUVEAU)

    def test_l_inscription_connecte_avec_le_nouveau_chemin(self):
        """login() exige un chemin explicite quand plusieurs moteurs sont déclarés."""
        reponse = self.client.post(reverse("inscription"), {
            "username": "paul", "email": "paul@example.com",
            "password1": "Xy-12345678-zz", "password2": "Xy-12345678-zz",
        })
        self.assertRedirects(reponse, reverse("home"))
        self.assertEqual(self.client.session[BACKEND_SESSION_KEY], NOUVEAU)


class AdressesInchangeesTest(TestCase):
    """LOGIN_URL et les liens des emails de réinitialisation déjà envoyés."""

    def test_adresses(self):
        attendues = {
            "connexion": "/connexion/",
            "inscription": "/inscription/",
            "deconnexion": "/deconnexion/",
            "password_reset": "/mot-de-passe-oublie/",
            "password_reset_done": "/mot-de-passe-oublie/envoye/",
            "password_reset_complete": "/reinitialisation/terminee/",
        }
        for nom, adresse in attendues.items():
            with self.subTest(nom=nom):
                self.assertEqual(reverse(nom), adresse)
        self.assertEqual(
            reverse("password_reset_confirm", kwargs={"uidb64": "AA", "token": "x-y"}),
            "/reinitialisation/AA/x-y/",
        )
        self.assertEqual(settings.LOGIN_URL, "/connexion/")
