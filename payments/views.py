"""Webhook Stripe (ADR-003, #49).

Seul code qui décrémente le stock en production. Déplacé de shop/views.py
sans changement de logique. L'adresse (/webhooks/stripe/) est enregistrée
dans le tableau de bord Stripe : elle ne doit pas changer.
"""
import logging

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from catalog.models import Product
from orders.models import Commande, OrderItem

from .services import stripe, stripe_is_configured, sync_commande_payment_from_stripe

logger = logging.getLogger(__name__)


@csrf_exempt
def stripe_webhook(request):
    if not stripe_is_configured() or not settings.STRIPE_WEBHOOK_SECRET:
        logger.error("Stripe webhook rejected: missing Stripe configuration or webhook secret.")
        return HttpResponse(status=400)

    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=settings.STRIPE_WEBHOOK_SECRET,
        )
    except Exception as exc:
        logger.exception("Stripe webhook signature verification failed: %s", exc)
        return HttpResponse(status=400)

    if event['type'] == 'checkout.session.completed':
        try:
            session = event['data']['object']
            session_id = getattr(session, 'id', None)

            commande = Commande.objects.filter(stripe_checkout_session_id=session_id).first()
            if not commande:
                metadata = getattr(session, 'metadata', {}) or {}
                commande_id = metadata.get('commande_id') if hasattr(metadata, 'get') else None
                if commande_id and str(commande_id).isdigit():
                    commande = Commande.objects.filter(id=int(commande_id)).first()

            if commande:
                sync_commande_payment_from_stripe(commande, session_id=session_id)

                # Décrémenter le stock une seule fois, seulement après paiement confirmé.
                with transaction.atomic():
                    commande_locked = Commande.objects.select_for_update().filter(id=commande.id).first()
                    if commande_locked and commande_locked.payment_status == 'paid' and not commande_locked.stock_deducted:
                        order_items = list(OrderItem.objects.filter(commande=commande_locked).select_related('product'))
                        for item in order_items:
                            if not item.product:
                                continue
                            product = Product.objects.select_for_update().filter(id=item.product_id).first()
                            if not product:
                                continue
                            product.stock = max(0, product.stock - item.quantity)
                            product.save(update_fields=['stock'])

                        commande_locked.stock_deducted = True
                        commande_locked.save(update_fields=['stock_deducted'])
        except Exception as exc:
            logger.exception("Stripe checkout.session.completed processing failed: %s", exc)
            # 500 et non 200 : Stripe réessaiera l'envoi. Sans danger, le
            # traitement étant idempotent (drapeau stock_deducted sous verrou).
            return HttpResponse(status=500)

    elif event['type'] == 'checkout.session.expired':
        session = event['data']['object']
        session_id = getattr(session, 'id', None)
        commande = Commande.objects.filter(stripe_checkout_session_id=session_id).first()
        if commande and commande.payment_status in ['pending', 'processing']:
            update_fields = ['payment_status']
            commande.payment_status = 'cancelled'
            if commande.stock_deducted:
                order_items = OrderItem.objects.filter(commande=commande).select_related('product')
                for item in order_items:
                    if item.product:
                        item.product.stock += item.quantity
                        item.product.save(update_fields=['stock'])
                commande.stock_deducted = False
                update_fields.append('stock_deducted')
            commande.save(update_fields=update_fields)

    return HttpResponse(status=200)
