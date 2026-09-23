"""Test de l'environnement d'exécution : le dossier des médias.

Ce test s'exécute dans l'image, sous l'utilisateur django, comme en
production. Il vérifie que les fichiers téléversés depuis l'administration
peuvent effectivement être enregistrés.
"""
import os

from django.conf import settings
from django.test import SimpleTestCase


class DossierMediasTest(SimpleTestCase):

    def test_dossier_des_medias_inscriptible_par_l_application(self):
        self.assertTrue(
            os.path.isdir(settings.MEDIA_ROOT),
            f"{settings.MEDIA_ROOT} n'existe pas dans l'image",
        )
        self.assertTrue(
            os.access(settings.MEDIA_ROOT, os.W_OK),
            f"{settings.MEDIA_ROOT} n'est pas inscriptible par l'application",
        )
