"""Déplacement de Commande et OrderItem de `shop` vers `orders` (#49, ADR-003).

Même méthode que catalog/migrations/0001_initial.py. Aucune opération sur la
base : les tables shop_commande et shop_orderitem restent en place
(Meta.db_table), avec leurs données, leurs contraintes (dont l'unicité de
stripe_checkout_session_id, dont dépend l'idempotence du webhook) et leurs
clés étrangères. Seul l'état des migrations change : les modèles sont créés
ici dans `orders`, puis retirés de `shop` par shop/migrations/0018.

Les types de contenu sont renommés plutôt que recréés, pour conserver les
permissions attribuées et l'historique d'administration.

Les fonctions ci-dessous reprennent celles de catalog/0001 au lieu de les
importer : une migration est un instantané figé, qui ne doit pas dépendre
d'un code susceptible de changer ensuite.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


MODELES = ("commande", "orderitem")


def est_utilise(apps, db, type_de_contenu):
    """Vrai si une permission de ce type est attribuée, ou s'il figure dans l'historique."""
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    User = apps.get_model("auth", "User")
    LogEntry = apps.get_model("admin", "LogEntry")
    permissions = Permission.objects.using(db).filter(content_type=type_de_contenu)
    return (
        Group.permissions.through.objects.using(db).filter(permission__in=permissions).exists()
        or User.user_permissions.through.objects.using(db).filter(permission__in=permissions).exists()
        or LogEntry.objects.using(db).filter(content_type=type_de_contenu).exists()
    )


def renommer_types_de_contenu(apps, schema_editor, depuis, vers):
    ContentType = apps.get_model("contenttypes", "ContentType")
    db = schema_editor.connection.alias
    for modele in MODELES:
        source = ContentType.objects.using(db).filter(app_label=depuis, model=modele).first()
        if source is None:
            # Base neuve : post_migrate créera directement le bon type.
            continue
        cible = ContentType.objects.using(db).filter(app_label=vers, model=modele).first()
        if cible is not None:
            # post_migrate a pu créer un type vide sous le nouveau nom, par
            # exemple lors d'un retour arrière. Vide, il est remplacé par
            # l'original ; utilisé, on ne détruit rien et on laisse les deux.
            if est_utilise(apps, db, cible):
                continue
            cible.delete()  # emporte ses permissions, jamais attribuées
        source.app_label = vers
        source.save(update_fields=["app_label"])


def vers_orders(apps, schema_editor):
    renommer_types_de_contenu(apps, schema_editor, "shop", "orders")


def vers_shop(apps, schema_editor):
    renommer_types_de_contenu(apps, schema_editor, "orders", "shop")


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        # Les tables existent déjà, créées par les migrations de `shop`.
        ("shop", "0017_deplacer_catalogue_vers_catalog"),
        ("catalog", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("contenttypes", "0002_remove_content_type_name"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("admin", "0003_logentry_add_action_flag_choices"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="Commande",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        (
                            "subtotal_ht",
                            models.DecimalField(decimal_places=2, default=0, max_digits=10),
                        ),
                        (
                            "tax_amount",
                            models.DecimalField(decimal_places=2, default=0, max_digits=10),
                        ),
                        ("total", models.DecimalField(decimal_places=2, max_digits=10)),
                        ("nom", models.CharField(max_length=150)),
                        ("email", models.EmailField(max_length=254)),
                        ("address", models.CharField(max_length=200)),
                        ("address2", models.CharField(blank=True, max_length=300, null=True)),
                        ("ville", models.CharField(max_length=200)),
                        ("pays", models.CharField(max_length=300)),
                        ("zipcode", models.CharField(max_length=10)),
                        (
                            "status",
                            models.CharField(
                                choices=[
                                    ("pending", "En attente"),
                                    ("confirmed", "Confirmée"),
                                    ("shipped", "Expédiée"),
                                    ("delivered", "Livrée"),
                                    ("cancelled", "Annulée"),
                                ],
                                default="pending",
                                max_length=20,
                            ),
                        ),
                        (
                            "payment_status",
                            models.CharField(
                                choices=[
                                    ("pending", "En attente"),
                                    ("processing", "En cours"),
                                    ("paid", "Payée"),
                                    ("failed", "Échouée"),
                                    ("cancelled", "Annulée"),
                                ],
                                default="pending",
                                max_length=20,
                            ),
                        ),
                        (
                            "stripe_checkout_session_id",
                            models.CharField(
                                blank=True, max_length=255, null=True, unique=True
                            ),
                        ),
                        (
                            "payment_reference",
                            models.CharField(blank=True, max_length=255, null=True),
                        ),
                        ("confirmation_email_sent", models.BooleanField(default=False)),
                        ("stock_deducted", models.BooleanField(default=False)),
                        ("date_commande", models.DateTimeField(auto_now_add=True)),
                        (
                            "user",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                    ],
                    options={
                        "db_table": "shop_commande",
                        "ordering": ["-date_commande"],
                    },
                ),
                migrations.CreateModel(
                    name="OrderItem",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        ("price", models.DecimalField(decimal_places=2, max_digits=10)),
                        ("quantity", models.PositiveIntegerField()),
                        (
                            "commande",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="order_items",
                                to="orders.commande",
                            ),
                        ),
                        (
                            "product",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                to="catalog.product",
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "Article de commande",
                        "verbose_name_plural": "Articles de commande",
                        "db_table": "shop_orderitem",
                    },
                ),
            ],
            database_operations=[],
        ),
        migrations.RunPython(vers_orders, vers_shop),
    ]
