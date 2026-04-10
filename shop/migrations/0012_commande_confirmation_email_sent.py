from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shop', '0011_product_image_file'),
    ]

    operations = [
        migrations.AddField(
            model_name='commande',
            name='confirmation_email_sent',
            field=models.BooleanField(default=False),
        ),
    ]
