"""Retire Category et Product de l'état de `shop` (#49, ADR-003).

Pendant de catalog/migrations/0001_initial.py. Aucune opération sur la base :
les tables shop_category et shop_product appartiennent désormais à l'app
`catalog`, sous le même nom. La clé étrangère OrderItem.product pointe vers
la même table qu'avant ; seule sa cible dans l'état de Django change.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0001_initial"),
        ("shop", "0016_alter_orderitem_options_alter_product_options"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="orderitem",
                    name="product",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="catalog.product",
                    ),
                ),
                migrations.DeleteModel(name="Product"),
                migrations.DeleteModel(name="Category"),
            ],
            database_operations=[],
        ),
    ]
