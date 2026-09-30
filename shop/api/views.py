from rest_framework import viewsets

from shop.models import Category, Product

from .serializers import CategorySerializer, ProductSerializer


# Catalogue en lecture seule : ReadOnlyModelViewSet n'expose que GET
# (liste et détail). Aucune écriture possible, même authentifié : toute
# autre méthode répond 405. Le catalogue se gère dans l'administration.

class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Product.objects.select_related('category').all()
    serializer_class = ProductSerializer
