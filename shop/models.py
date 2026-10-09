from django.db import models
from django.contrib.auth.models import User 


class Commande(models.Model):

    STATUS_CHOICES = [
        ('pending',   'En attente'),
        ('confirmed', 'Confirmée'),
        ('shipped',   'Expédiée'),
        ('delivered', 'Livrée'),
        ('cancelled', 'Annulée'),
    ]

    PAYMENT_STATUS_CHOICES = [
        ('pending', 'En attente'),
        ('processing', 'En cours'),
        ('paid', 'Payée'),
        ('failed', 'Échouée'),
        ('cancelled', 'Annulée'),
    ]

    subtotal_ht   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_amount    = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total         = models.DecimalField(max_digits=10, decimal_places=2)     # plus CharField
    nom           = models.CharField(max_length=150)
    email         = models.EmailField()
    address       = models.CharField(max_length=200)
    address2      = models.CharField(max_length=300, blank=True, null=True)
    ville         = models.CharField(max_length=200)
    pays          = models.CharField(max_length=300)
    zipcode       = models.CharField(max_length=10)
    status        = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    stripe_checkout_session_id = models.CharField(max_length=255, blank=True, null=True, unique=True)
    payment_reference = models.CharField(max_length=255, blank=True, null=True)
    confirmation_email_sent = models.BooleanField(default=False)
    stock_deducted = models.BooleanField(default=False)
    date_commande = models.DateTimeField(auto_now_add=True)
    user          = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-date_commande']

    def __str__(self):
        return f"#{self.id} — {self.nom} — {self.total} €"


class OrderItem(models.Model):
    commande = models.ForeignKey(Commande, related_name='order_items', on_delete=models.CASCADE)
    product = models.ForeignKey('catalog.Product', on_delete=models.SET_NULL, null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()

    class Meta:
        verbose_name = 'Article de commande'
        verbose_name_plural = 'Articles de commande'

    def __str__(self):
        product_name = self.product.title if self.product else 'Produit supprimé'
        return f"{product_name} x{self.quantity}"
