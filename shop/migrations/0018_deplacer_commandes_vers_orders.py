"""Retire Commande et OrderItem de l'état de `shop` (#49, ADR-003).

Pendant de orders/migrations/0001_initial.py. Aucune opération sur la base :
les tables shop_commande et shop_orderitem appartiennent désormais à l'app
`orders`, sous le même nom. Après cette migration, `shop` n'a plus de modèle.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0001_initial"),
        ("shop", "0017_deplacer_catalogue_vers_catalog"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name="OrderItem"),
                migrations.DeleteModel(name="Commande"),
            ],
            database_operations=[],
        ),
    ]
