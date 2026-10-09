from django.urls import path

from .views import stripe_webhook

urlpatterns = [
    # Adresse enregistrée dans le tableau de bord Stripe : ne pas la changer.
    path('webhooks/stripe/', stripe_webhook, name='stripe_webhook'),
]
