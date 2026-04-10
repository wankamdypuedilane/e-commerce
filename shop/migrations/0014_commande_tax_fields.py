from django.db import migrations, models


def backfill_existing_orders(apps, schema_editor):
    Commande = apps.get_model('shop', 'Commande')
    for commande in Commande.objects.all().iterator():
        # Historic orders had only total; map it to HT with zero VAT by default.
        if commande.subtotal_ht == 0 and commande.tax_amount == 0 and commande.total > 0:
            commande.subtotal_ht = commande.total
            commande.tax_amount = 0
            commande.save(update_fields=['subtotal_ht', 'tax_amount'])


class Migration(migrations.Migration):

    dependencies = [
        ('shop', '0013_remove_commande_items'),
    ]

    operations = [
        migrations.AddField(
            model_name='commande',
            name='subtotal_ht',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name='commande',
            name='tax_amount',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.RunPython(backfill_existing_orders, migrations.RunPython.noop),
    ]
