"""Tests du déplacement de Commande et OrderItem vers l'app orders (#49).

Comme pour catalog : mêmes tables, mêmes lignes, mêmes contraintes, mêmes
permissions attribuées. Le test de migration peuple une base où les
commandes appartiennent encore à `shop`, puis rejoue le déplacement.
"""
from django.apps import apps
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase, TransactionTestCase

from ecommerce.migrations_de_test import migrer

AVANT = [("shop", "0017_deplacer_catalogue_vers_catalog"), ("orders", None)]


class EmplacementDesModelesTest(SimpleTestCase):

    def test_les_modeles_appartiennent_a_orders(self):
        for nom in ("Commande", "OrderItem"):
            with self.subTest(modele=nom):
                self.assertEqual(apps.get_model("orders", nom)._meta.app_label, "orders")
                with self.assertRaises(LookupError):
                    apps.get_model("shop", nom)

    def test_shop_n_a_plus_de_modele(self):
        self.assertEqual(list(apps.get_app_config("shop").get_models()), [])

    def test_les_tables_gardent_leur_nom(self):
        """Renommer les tables imposerait une vraie migration en production."""
        self.assertEqual(apps.get_model("orders", "Commande")._meta.db_table, "shop_commande")
        self.assertEqual(apps.get_model("orders", "OrderItem")._meta.db_table, "shop_orderitem")


class ContrainteDuWebhookTest(TestCase):
    """L'idempotence du webhook repose sur l'unicité de la session Stripe."""

    def test_session_stripe_toujours_unique_en_base(self):
        Commande = apps.get_model("orders", "Commande")
        champs = dict(total=10, nom="T", email="t@example.com", address="a",
                      ville="v", pays="France", zipcode="29200",
                      stripe_checkout_session_id="cs_unique")
        Commande.objects.create(**champs)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Commande.objects.create(**champs)


class MigrationDesCommandesTest(TransactionTestCase):
    """Rejoue orders.0001 et shop.0018 sur une base peuplée à l'ancienne."""

    def tearDown(self):
        migrer()  # laisser la base dans l'état attendu par les autres tests

    def test_donnees_et_permissions_conservees(self):
        anciennes = migrer(AVANT)
        ContentType = anciennes.get_model("contenttypes", "ContentType")
        Permission = anciennes.get_model("auth", "Permission")
        User = anciennes.get_model("auth", "User")

        type_commande = ContentType.objects.get_or_create(app_label="shop", model="commande")[0]
        permission = Permission.objects.get_or_create(
            content_type=type_commande, codename="change_commande",
            defaults={"name": "Can change commande"},
        )[0]
        agent = User.objects.create(username="agent")
        agent.user_permissions.add(permission)
        categorie = anciennes.get_model("catalog", "Category").objects.create(name="Audio")
        produit = anciennes.get_model("catalog", "Product").objects.create(
            title="Casque", price="99.90", description="", category=categorie, stock=3,
        )
        commande = anciennes.get_model("shop", "Commande").objects.create(
            total="199.80", nom="T", email="t@example.com", address="a", ville="v",
            pays="France", zipcode="29200", user=agent, stripe_checkout_session_id="cs_1",
        )
        anciennes.get_model("shop", "OrderItem").objects.create(
            commande=commande, product=produit, price="99.90", quantity=2,
        )

        nouvelles = migrer()

        commande_apres = nouvelles.get_model("orders", "Commande").objects.get(pk=commande.pk)
        self.assertEqual(commande_apres.stripe_checkout_session_id, "cs_1")
        self.assertEqual(commande_apres.user.username, "agent")
        ligne = commande_apres.order_items.get()
        self.assertEqual((ligne.product.title, ligne.quantity), ("Casque", 2))

        type_apres = nouvelles.get_model("contenttypes", "ContentType").objects.get(pk=type_commande.pk)
        self.assertEqual((type_apres.app_label, type_apres.model), ("orders", "commande"))
        self.assertFalse(
            nouvelles.get_model("contenttypes", "ContentType").objects
            .filter(app_label="shop", model="commande").exists()
        )
        agent_apres = nouvelles.get_model("auth", "User").objects.get(pk=agent.pk)
        self.assertEqual(
            list(agent_apres.user_permissions.values_list("content_type__app_label", "codename")),
            [("orders", "change_commande")],
        )
