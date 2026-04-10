from decimal import Decimal
import json

from django.db import migrations


def forward_backfill_order_items(apps, schema_editor):
    Commande = apps.get_model('shop', 'Commande')
    Product = apps.get_model('shop', 'Product')
    OrderItem = apps.get_model('shop', 'OrderItem')

    for commande in Commande.objects.all().iterator():
        if OrderItem.objects.filter(commande=commande).exists():
            continue

        try:
            items = json.loads(commande.items or '[]')
        except (TypeError, json.JSONDecodeError):
            continue

        if not isinstance(items, list):
            continue

        order_items = []
        for raw_item in items:
            if not isinstance(raw_item, dict):
                continue

            try:
                product_id = int(raw_item.get('id')) if raw_item.get('id') is not None else None
                quantity = int(raw_item.get('quantity', 0))
                price = Decimal(str(raw_item.get('price', '0')))
            except (ValueError, TypeError, ArithmeticError):
                continue

            if quantity < 1:
                continue

            product = None
            if product_id is not None:
                product = Product.objects.filter(id=product_id).first()

            order_items.append(
                OrderItem(
                    commande=commande,
                    product=product,
                    price=price,
                    quantity=quantity,
                )
            )

        if order_items:
            OrderItem.objects.bulk_create(order_items)


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('shop', '0007_orderitem'),
    ]

    operations = [
        migrations.RunPython(forward_backfill_order_items, reverse_noop),
    ]
