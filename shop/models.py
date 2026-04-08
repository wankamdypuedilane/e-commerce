from django.db import models
from django.contrib.auth.models import User 


class Category(models.Model):
    name       = models.CharField(max_length=200)
    date_added = models.DateTimeField(auto_now_add=True)  # auto_now_add pas auto_now

    class Meta:
        ordering     = ['name']
        verbose_name_plural = 'Catégories'

    def __str__(self):
        return self.name


class Product(models.Model):
    title       = models.CharField(max_length=200)
    price       = models.DecimalField(max_digits=10, decimal_places=2)  # plus FloatField
    description = models.TextField()
    category    = models.ForeignKey(Category, related_name='products', on_delete=models.CASCADE)
    image       = models.CharField(max_length=5000)  # on garde CharField pour l'instant
    available   = models.BooleanField(default=True)
    stock       = models.PositiveIntegerField(default=0) 

    class Meta:
        ordering = ['title']

    def __str__(self):
        return self.title


class Commande(models.Model):

    STATUS_CHOICES = [
        ('pending',   'En attente'),
        ('confirmed', 'Confirmée'),
        ('shipped',   'Expédiée'),
        ('delivered', 'Livrée'),
        ('cancelled', 'Annulée'),
    ]

    items         = models.TextField()                                        # TextField, pas CharField
    total         = models.DecimalField(max_digits=10, decimal_places=2)     # plus CharField
    nom           = models.CharField(max_length=150)
    email         = models.EmailField()
    address       = models.CharField(max_length=200)
    address2      = models.CharField(max_length=300, blank=True, null=True)
    ville         = models.CharField(max_length=200)
    pays          = models.CharField(max_length=300)
    zipcode       = models.CharField(max_length=10)
    status        = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    date_commande = models.DateTimeField(auto_now_add=True)
    user          = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-date_commande']

    def __str__(self):
        return f"#{self.id} — {self.nom} — {self.total} €"