"""Catalogue : catégories et produits (ADR-003, #49).

Les deux modèles viennent de l'app `shop`. Leurs tables gardent leur nom
d'origine (`db_table`) : le déplacement ne change que le code, pas la base,
et ne copie aucune donnée en production. Voir catalog/migrations/0001_initial.py.
"""
from django.db import models


class Category(models.Model):
    name       = models.CharField(max_length=200)
    date_added = models.DateTimeField(auto_now_add=True)  # auto_now_add pas auto_now

    class Meta:
        db_table = 'shop_category'
        ordering     = ['name']
        verbose_name_plural = 'Catégories'

    def __str__(self):
        return self.name


class Product(models.Model):
    title       = models.CharField(max_length=200)
    price       = models.DecimalField(max_digits=10, decimal_places=2)  # plus FloatField
    description = models.TextField()
    category    = models.ForeignKey(Category, related_name='products', on_delete=models.CASCADE)
    image       = models.CharField(max_length=5000, blank=True, default='')  # URL legacy
    image_file  = models.ImageField(upload_to='products/', blank=True, null=True)
    stock       = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'shop_product'
        ordering = ['title']
        verbose_name = 'Produit'
        verbose_name_plural = 'Produits'

    def __str__(self):
        return self.title

    @property
    def display_image_url(self):
        if self.image_file:
            return self.image_file.url
        return self.image or ''
