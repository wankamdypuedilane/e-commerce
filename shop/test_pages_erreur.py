"""Tests des pages d'erreur personnalisees 404 et 500 (issue #55).

Les deux gabarits vivent dans le dossier `templates/` racine, deja present
dans `DIRS` : les gestionnaires par defaut de Django les trouvent sans
handler explicite.

Le choix de conception, verifie ici :
- la 404 est rendue AVEC un RequestContext, elle peut donc heriter de
  `shop/base.html` (jeton csp_nonce, balises {% url %}, contexte de requete) ;
- la 500 est rendue SANS RequestContext, elle doit donc etre autonome :
  aucune dependance qui casserait la page d'erreur en cas de panne.
"""
from pathlib import Path

from django.conf import settings
from django.template import loader
from django.test import SimpleTestCase, override_settings


@override_settings(DEBUG=False)
class Page404Test(SimpleTestCase):
    """La 404 utilise le gabarit personnalise et herite du site."""

    def test_url_inexistante_rend_la_404_personnalisee(self):
        """Une URL inconnue renvoie 404 et le gabarit templates/404.html."""
        reponse = self.client.get("/cette-page-n-existe-pas/")
        self.assertEqual(reponse.status_code, 404)
        self.assertTemplateUsed(reponse, "404.html")
        self.assertContains(reponse, "Page introuvable", status_code=404)


class Page500Test(SimpleTestCase):
    """La 500 se rend sans contexte et n'a aucune dependance interdite."""

    CHEMIN_500 = Path(settings.TEMPLATES_DIRS) / "500.html"

    def test_le_gabarit_500_se_rend_sans_contexte(self):
        """render_to_string sans contexte ne leve pas et rend le marqueur.

        C'est exactement la contrainte de server_error : rendre le gabarit
        alors qu'aucune variable de contexte n'est disponible.
        """
        rendu = loader.render_to_string("500.html")
        self.assertIn("Une erreur est survenue", rendu)

    def test_le_gabarit_500_n_a_aucune_dependance_interdite(self):
        """Le fichier 500.html ne contient ni heritage, ni {% url %}, ni jeton.

        Chacune de ces constructions exige un contexte absent au moment du
        rendu de la 500 et casserait la page d'erreur.
        """
        source = self.CHEMIN_500.read_text(encoding="utf-8")
        self.assertNotIn("{% extends", source)
        self.assertNotIn("{% load", source)
        self.assertNotIn("{% url", source)
        self.assertNotIn("csp_nonce", source)
