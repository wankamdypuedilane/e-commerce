from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shop', '0014_commande_tax_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='commande',
            name='stock_deducted',
            field=models.BooleanField(default=False),
        ),
    ]
