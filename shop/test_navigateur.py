"""Bibliothèques chargées par le navigateur depuis un CDN (issue #87).

Aucun scanner de la CI ne les voit : pip-audit et Trivy analysent le
serveur. Ce test empêche le retour d'un double chargement de jQuery et
d'une version vulnérable. Si jQuery est retiré un jour (issue #50), ce
test devra évoluer avec lui.
"""
import re

from django.test import TestCase


class BibliothequesNavigateurTest(TestCase):

    def test_une_seule_version_de_jquery_sans_faille_connue(self):
        html = self.client.get("/").content.decode()
        versions = re.findall(r"code\.jquery\.com/jquery-(\d+)\.(\d+)\.(\d+)", html)
        self.assertEqual(len(versions), 1, f"jQuery chargé {len(versions)} fois")
        majeure, mineure, _ = map(int, versions[0])
        self.assertGreaterEqual(
            (majeure, mineure), (3, 5),
            "Versions antérieures à 3.5 : CVE-2020-11022 et CVE-2020-11023",
        )
