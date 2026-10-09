"""Déplacement de Category et Product de `shop` vers `catalog` (#49, ADR-003).

Aucune opération sur la base : les tables shop_category et shop_product
restent en place (Meta.db_table), avec leurs données, leurs index et la clé
étrangère de shop_orderitem. Seul l'état des migrations de Django change :
les modèles sont créés ici dans `catalog`, puis retirés de `shop` par
shop/migrations/0017.

Les types de contenu sont renommés plutôt que recréés. Sans cela, Django
créerait catalog.product à côté de shop.product, et perdrait :
- les permissions déjà attribuées (add_product, change_category...) ;
- les liens de l'historique d'administration vers les produits.
"""

import django.db.models.deletion
from django.db import migrations, models


MODELES = ("category", "product")


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


def vers_catalog(apps, schema_editor):
    renommer_types_de_contenu(apps, schema_editor, "shop", "catalog")


def vers_shop(apps, schema_editor):
    renommer_types_de_contenu(apps, schema_editor, "catalog", "shop")


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        # Les tables existent déjà, créées par les migrations de `shop`.
        ("shop", "0016_alter_orderitem_options_alter_product_options"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("admin", "0003_logentry_add_action_flag_choices"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="Category",
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
                        ("name", models.CharField(max_length=200)),
                        ("date_added", models.DateTimeField(auto_now_add=True)),
                    ],
                    options={
                        "verbose_name_plural": "Catégories",
                        "db_table": "shop_category",
                        "ordering": ["name"],
                    },
                ),
                migrations.CreateModel(
                    name="Product",
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
                        ("title", models.CharField(max_length=200)),
                        ("price", models.DecimalField(decimal_places=2, max_digits=10)),
                        ("description", models.TextField()),
                        ("image", models.CharField(blank=True, default="", max_length=5000)),
                        (
                            "image_file",
                            models.ImageField(blank=True, null=True, upload_to="products/"),
                        ),
                        ("stock", models.PositiveIntegerField(default=0)),
                        (
                            "category",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="products",
                                to="catalog.category",
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "Produit",
                        "verbose_name_plural": "Produits",
                        "db_table": "shop_product",
                        "ordering": ["title"],
                    },
                ),
            ],
            database_operations=[],
        ),
        migrations.RunPython(vers_catalog, vers_shop),
    ]
