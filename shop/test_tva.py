"""Tests unitaires du calcul de TVA.

Fonctions pures : aucune base de données, aucun réseau. SimpleTestCase
interdit d'ailleurs toute requête SQL, ce qui garantit leur isolement.
"""
from decimal import Decimal

from django.test import SimpleTestCase, override_settings

from .services import calculate_tax_totals, get_tax_rate_percent


class TauxDeTvaTest(SimpleTestCase):

    @override_settings(TAX_RATE_PERCENT="20")
    def test_taux_standard(self):
        self.assertEqual(get_tax_rate_percent(), Decimal("20"))

    @override_settings(TAX_RATE_PERCENT="5.5")
    def test_taux_decimal(self):
        self.assertEqual(get_tax_rate_percent(), Decimal("5.5"))

    @override_settings(TAX_RATE_PERCENT="2O")
    def test_taux_invalide_retombe_silencieusement_sur_20(self):
        """Comportement actuel, discutable : une faute de frappe dans la
        configuration n'est pas signalée. Voir l'issue dédiée."""
        self.assertEqual(get_tax_rate_percent(), Decimal("20"))


class CalculTvaTest(SimpleTestCase):

    @override_settings(TAX_RATE_PERCENT="20")
    def test_cas_simple(self):
        taux, tva, ttc = calculate_tax_totals(Decimal("100.00"))
        self.assertEqual(taux, Decimal("20"))
        self.assertEqual(tva, Decimal("20.00"))
        self.assertEqual(ttc, Decimal("120.00"))

    @override_settings(TAX_RATE_PERCENT="20")
    def test_arrondi_au_centime(self):
        _, tva, ttc = calculate_tax_totals(Decimal("12.34"))  # TVA brute : 2,468
        self.assertEqual(tva, Decimal("2.47"))
        self.assertEqual(ttc, Decimal("14.81"))

    @override_settings(TAX_RATE_PERCENT="5.5")
    def test_taux_reduit(self):
        _, tva, ttc = calculate_tax_totals(Decimal("19.99"))  # TVA brute : 1,09945
        self.assertEqual(tva, Decimal("1.10"))
        self.assertEqual(ttc, Decimal("21.09"))

    @override_settings(TAX_RATE_PERCENT="10")
    def test_arrondi_commercial_et_non_bancaire(self):
        """0,045 donne 0,05 en arrondi commercial (ROUND_HALF_UP),
        mais 0,04 en arrondi bancaire (ROUND_HALF_EVEN). Ce test
        verrouille le choix du code."""
        _, tva, ttc = calculate_tax_totals(Decimal("0.45"))
        self.assertEqual(tva, Decimal("0.05"))
        self.assertEqual(ttc, Decimal("0.50"))

    @override_settings(TAX_RATE_PERCENT="20")
    def test_montant_nul(self):
        _, tva, ttc = calculate_tax_totals(Decimal("0"))
        self.assertEqual(tva, Decimal("0.00"))
        self.assertEqual(ttc, Decimal("0.00"))

    @override_settings(TAX_RATE_PERCENT="20")
    def test_resultats_exprimes_au_centime(self):
        _, tva, ttc = calculate_tax_totals(Decimal("100"))
        self.assertEqual(tva.as_tuple().exponent, -2)
        self.assertEqual(ttc.as_tuple().exponent, -2)

    @override_settings(TAX_RATE_PERCENT="20")
    def test_refuse_un_nombre_flottant(self):
        """Un float introduirait des erreurs d'arrondi binaire :
        la fonction doit recevoir un Decimal."""
        with self.assertRaises(TypeError):
            calculate_tax_totals(12.34)
