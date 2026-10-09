"""Tests du déplacement de Category et Product vers l'app catalog (#49).

Le déplacement ne doit rien changer en base : mêmes tables, mêmes lignes,
mêmes permissions attribuées. Ces tests le vérifient en rejouant la
migration sur une base où le catalogue appartient encore à `shop`.
"""
from django.apps import apps
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TransactionTestCase

AVANT = [("shop", "0016_alter_orderitem_options_alter_product_options"), ("catalog", None)]
APRES = [("shop", "0017_deplacer_catalogue_vers_catalog"), ("catalog", "0001_initial")]


class EmplacementDesModelesTest(SimpleTestCase):

    def test_les_modeles_appartiennent_a_catalog(self):
        for nom in ("Category", "Product"):
            with self.subTest(modele=nom):
                self.assertEqual(apps.get_model("catalog", nom)._meta.app_label, "catalog")
                with self.assertRaises(LookupError):
                    apps.get_model("shop", nom)

    def test_les_tables_gardent_leur_nom(self):
        """Renommer les tables imposerait une vraie migration en production."""
        self.assertEqual(apps.get_model("catalog", "Category")._meta.db_table, "shop_category")
        self.assertEqual(apps.get_model("catalog", "Product")._meta.db_table, "shop_product")

    def test_la_ligne_de_commande_pointe_vers_catalog(self):
        champ = apps.get_model("shop", "OrderItem")._meta.get_field("product")
        self.assertIs(champ.related_model, apps.get_model("catalog", "Product"))


class MigrationDuCatalogueTest(TransactionTestCase):
    """Rejoue catalog.0001 et shop.0017 sur une base peuplée à l'ancienne."""

    def migrer(self, cible):
        executeur = MigrationExecutor(connection)
        executeur.loader.build_graph()
        executeur.migrate(cible)
        executeur.loader.build_graph()
        # État complet : dernières migrations des autres apps, et pour shop et
        # catalog celles de la cible (project_state n'accepte pas « zéro »).
        noeuds = [n for n in executeur.loader.graph.leaf_nodes() if n[0] not in ("shop", "catalog")]
        noeuds += [n for n in cible if n[1]]
        return executeur.loader.project_state(noeuds).apps

    def tearDown(self):
        self.migrer(APRES)  # laisser la base dans l'état attendu par les autres tests

    def test_donnees_et_permissions_conservees(self):
        anciennes = self.migrer(AVANT)
        ContentType = anciennes.get_model("contenttypes", "ContentType")
        Permission = anciennes.get_model("auth", "Permission")
        Group = anciennes.get_model("auth", "Group")

        type_produit = ContentType.objects.get_or_create(app_label="shop", model="product")[0]
        permission = Permission.objects.get_or_create(
            content_type=type_produit, codename="change_product",
            defaults={"name": "Can change produit"},
        )[0]
        groupe = Group.objects.create(name="Gestion catalogue")
        groupe.permissions.add(permission)
        categorie = anciennes.get_model("shop", "Category").objects.create(name="Audio")
        produit = anciennes.get_model("shop", "Product").objects.create(
            title="Casque", price="99.90", description="", category=categorie, stock=3,
        )

        nouvelles = self.migrer(APRES)

        Produit = nouvelles.get_model("catalog", "Product")
        self.assertEqual(Produit.objects.get(pk=produit.pk).category.name, "Audio")

        type_apres = nouvelles.get_model("contenttypes", "ContentType").objects.get(pk=type_produit.pk)
        self.assertEqual((type_apres.app_label, type_apres.model), ("catalog", "product"))
        self.assertFalse(
            nouvelles.get_model("contenttypes", "ContentType").objects
            .filter(app_label="shop", model="product").exists()
        )
        groupe_apres = nouvelles.get_model("auth", "Group").objects.get(pk=groupe.pk)
        self.assertEqual(
            list(groupe_apres.permissions.values_list("content_type__app_label", "codename")),
            [("catalog", "change_product")],
        )
