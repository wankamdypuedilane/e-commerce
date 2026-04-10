from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('shop', '0009_commande_payment_fields'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='product',
            name='available',
        ),
    ]
