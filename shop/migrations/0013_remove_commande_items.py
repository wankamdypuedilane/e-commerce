from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('shop', '0012_commande_confirmation_email_sent'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='commande',
            name='items',
        ),
    ]