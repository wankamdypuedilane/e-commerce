from rest_framework import serializers

from shop.models import Category, Product


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
