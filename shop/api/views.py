from rest_framework import viewsets
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import AnonRateThrottle

from shop.models import Category, Commande, Product

from .serializers import CategorySerializer, CommandeSerializer, ProductSerializer


# Catalogue en lecture seule : ReadOnlyModelViewSet n'expose que GET
# (liste et détail). Aucune écriture possible, même authentifié : toute
# autre méthode répond 405. Le catalogue se gère dans l'administration.

class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Product.objects.select_related('category').all()
    serializer_class = ProductSerializer


class CommandeViewSet(viewsets.ReadOnlyModelViewSet):
    """Commandes de l'utilisateur authentifié, même règle que le site (#70).

    - Authentification obligatoire : un visiteur anonyme reçoit 401.
    - Le queryset ne contient que les commandes de request.user : celle
      d'autrui, ou une commande sans utilisateur, répond 404 et non 403.
      Un 403 confirmerait qu'elle existe, et les identifiants étant
      séquentiels, permettrait de recenser les commandes du site.
    - Lecture seule : les commandes naissent dans le tunnel de paiement.
    """
    serializer_class = CommandeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Commande.objects
            .filter(user=self.request.user)
            .prefetch_related('order_items__product')
            .order_by('-date_commande', '-id')
        )


class ObtainAuthTokenView(ObtainAuthToken):
    """Obtention d'un jeton, soumise à la limitation de débit.

    La vue de DRF désactive toute limitation (throttle_classes vide) : elle
    permettrait d'essayer des mots de passe sans limite. Les demandes de
    jeton étant anonymes, la limite des visiteurs s'applique.
    """
    throttle_classes = [AnonRateThrottle]
