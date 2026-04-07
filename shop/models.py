from django.db import models

class Category(models.Model):

    name = models.CharField(max_length=200)
    date_added = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date_added']

    def __str__(self):
        return self.name

class Product (models.Model):
    title = models.CharField(max_length=200)
    price = models.FloatField()
    description = models.TextField()
    category = models.ForeignKey(Category, related_name = 'categorie', on_delete = models.CASCADE)
    image = models.CharField(max_length=5000)
    class Meta:
        ordering = ['-category__date_added']

    def __str__(self):
        return self.title

class Commande (models.Model):
    items=models.CharField(max_length=300)
    total=models.CharField(max_length=200)
    nom=models.CharField(max_length=150)
    email=models.EmailField()
    address=models.CharField(max_length=200)
    address2=models.CharField(max_length=300, blank=True, null=True)
    ville=models.CharField(max_length=200)
    pays=models.CharField(max_length=300)
    zipcode=models.CharField(max_length=10)
    date_commande=models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering=['-date_commande']
    
    def __str__(self):
        return self.nom


# Create your models here.
