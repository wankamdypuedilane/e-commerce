from rest_framework import serializers

from shop.models import Category, Commande, OrderItem, Product


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name']


class ProductSerializer(serializers.ModelSerializer):
    # Même règle que le site : fichier hébergé en priorité, sinon URL héritée
    image = serializers.CharField(source='display_image_url', read_only=True)

    class Meta:
        model = Product
        fields = ['id', 'title', 'description', 'price', 'stock', 'category', 'image']


class OrderItemSerializer(serializers.ModelSerializer):
    # Le produit peut avoir été supprimé depuis la commande (SET_NULL)
    title = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = ['product', 'title', 'price', 'quantity']

    def get_title(self, item):
        return item.product.title if item.product else 'Produit supprimé'


class CommandeSerializer(serializers.ModelSerializer):
    """Commande vue par son propriétaire.

    Minimisation des données : ni coordonnées (nom, email, adresse), ni
    identifiants Stripe, ni indicateurs internes de traitement. Seul ce
    qui sert à suivre une commande est exposé.
    """
    date = serializers.DateTimeField(source='date_commande', read_only=True)
    items = OrderItemSerializer(source='order_items', many=True, read_only=True)

    class Meta:
        model = Commande
        fields = [
            'id', 'date', 'status', 'payment_status',
            'subtotal_ht', 'tax_amount', 'total', 'items',
        ]
