from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shop', '0008_backfill_orderitem_from_commande_items'),
    ]

    operations = [
        migrations.AddField(
            model_name='commande',
            name='payment_reference',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='commande',
            name='payment_status',
            field=models.CharField(choices=[('pending', 'En attente'), ('processing', 'En cours'), ('paid', 'Payée'), ('failed', 'Échouée'), ('cancelled', 'Annulée')], default='pending', max_length=20),
        ),
        migrations.AddField(
            model_name='commande',
            name='stripe_checkout_session_id',
            field=models.CharField(blank=True, max_length=255, null=True, unique=True),
        ),
    ]
