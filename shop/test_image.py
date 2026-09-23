"""Tests de l'image d'exécution : protection du code de l'application.

Le processus applicatif tourne sous l'utilisateur django. Il doit pouvoir
lire son code, mais jamais le modifier : un processus compromis ne doit pas
pouvoir réécrire les vues ou la configuration qu'il exécute.

Ces tests n'ont de sens que dans l'image, où le code est installé dans /app.
"""
import os
from pathlib import Path
from unittest import skipUnless

from django.conf import settings
from django.test import SimpleTestCase

DANS_L_IMAGE = Path(settings.BASE_DIR) == Path("/app")


@skipUnless(DANS_L_IMAGE, "Vérification propre à l'image Docker")
class ProtectionDuCodeTest(SimpleTestCase):

    def test_fichiers_du_code_non_modifiables(self):
        base = Path(settings.BASE_DIR)
        for chemin in (base / "manage.py", base / "shop" / "views.py", base / "ecommerce" / "settings.py"):
            with self.subTest(chemin=str(chemin)):
                self.assertTrue(os.access(chemin, os.R_OK), f"{chemin} n'est pas lisible")
                self.assertFalse(os.access(chemin, os.W_OK), f"{chemin} est modifiable par l'application")

    def test_dossiers_du_code_non_inscriptibles(self):
        base = Path(settings.BASE_DIR)
        for dossier in (base, base / "shop", base / "ecommerce"):
            with self.subTest(dossier=str(dossier)):
                self.assertFalse(os.access(dossier, os.W_OK), f"{dossier} est inscriptible par l'application")
