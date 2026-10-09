from django.urls import path
from shop.views import (
    index,
    detail,
    checkout,
    confirmation,
    payment_success,
    payment_cancel,
    profil,
    search_products,
    healthz,
    metrics,
)

urlpatterns = [
    path('healthz/', healthz, name='healthz'),
    # Metriques Prometheus, refusees si la requete vient de l'Ingress
    path('metrics', metrics, name='metrics'),
    path('api/produits/', search_products, name='search_products'),
    path('', index, name='home'),
    path('<int:myid>', detail, name='detail'),
    path('checkout', checkout, name="checkout"),
    path('confirmation/<int:order_id>/', confirmation, name="confirmation_order"),
    path('confirmation', confirmation, name="confirmation"),
    path('paiement/succes/', payment_success, name='payment_success'),
    path('paiement/annule/', payment_cancel, name='payment_cancel'),
    path('profil/', profil, name='profil'),
]
