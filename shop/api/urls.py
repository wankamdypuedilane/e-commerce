from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

from .views import CategoryViewSet, ProductViewSet

app_name = 'api'

router = DefaultRouter()
router.register('products', ProductViewSet, basename='product')
router.register('categories', CategoryViewSet, basename='category')

urlpatterns = [
    # POST identifiant et mot de passe -> {"token": "..."}
    path('auth/token/', obtain_auth_token, name='token'),
    path('', include(router.urls)),
]
