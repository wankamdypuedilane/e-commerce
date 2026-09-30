from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerSplitView
from rest_framework.routers import DefaultRouter

from .views import CategoryViewSet, CommandeViewSet, ObtainAuthTokenView, ProductViewSet

app_name = 'api'

router = DefaultRouter()
router.register('products', ProductViewSet, basename='product')
router.register('categories', CategoryViewSet, basename='category')
router.register('orders', CommandeViewSet, basename='order')

urlpatterns = [
    # POST identifiant et mot de passe -> {"token": "..."}
    path('auth/token/', ObtainAuthTokenView.as_view(), name='token'),
    # Schéma OpenAPI (YAML, ou JSON avec ?format=json) et Swagger UI
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerSplitView.as_view(url_name='api:schema'), name='docs'),
    path('', include(router.urls)),
]
