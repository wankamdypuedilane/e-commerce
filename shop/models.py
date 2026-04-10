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
    image       = models.CharField(max_length=5000, blank=True, default='')  # URL legacy
    image_file  = models.ImageField(upload_to='products/', blank=True, null=True)
    stock       = models.PositiveIntegerField(default=0) 

    class Meta:
        ordering = ['title']

    def __str__(self):
        return self.title

    @property
    def display_image_url(self):
        if self.image_file:
            return self.image_file.url
        return self.image or ''


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
    date_commande = models.DateTimeField(auto_now_add=True)
    user          = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-date_commande']

    def __str__(self):
        return f"#{self.id} — {self.nom} — {self.total} €"


class OrderItem(models.Model):
    commande = models.ForeignKey(Commande, related_name='order_items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()

    def __str__(self):
        product_name = self.product.title if self.product else 'Produit supprimé'
        return f"{product_name} x{self.quantity}"