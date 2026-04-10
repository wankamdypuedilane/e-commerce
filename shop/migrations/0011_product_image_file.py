from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shop', '0010_remove_product_available'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='image_file',
            field=models.ImageField(blank=True, null=True, upload_to='products/'),
        ),
        migrations.AlterField(
            model_name='product',
            name='image',
            field=models.CharField(blank=True, default='', max_length=5000),
        ),
    ]
