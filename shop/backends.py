"""Ancien chemin du moteur d'authentification, gardé pour la transition (#49).

Le moteur a déménagé dans accounts/backends.py. Chaque session ouverte
enregistre le chemin du moteur qui a authentifié l'utilisateur, et Django
ne reconnaît une session que si ce chemin figure dans
AUTHENTICATION_BACKENDS. Sans ce module, toutes les sessions ouvertes avant
le déploiement seraient perdues : clients et administrateurs déconnectés.

Il ne sert qu'à relire ces sessions (get_user, permissions). Il
n'authentifie personne : sinon, chaque tentative de connexion ratée
vérifierait le mot de passe deux fois. À retirer, avec sa ligne dans
AUTHENTICATION_BACKENDS (#135), quand les sessions antérieures auront expiré
(SESSION_COOKIE_AGE, deux semaines par défaut).
"""
from accounts.backends import EmailOrUsernameModelBackend as MoteurActuel


class EmailOrUsernameModelBackend(MoteurActuel):

    def authenticate(self, request, username=None, password=None, **kwargs):
        return None
