"""Emails transactionnels (ADR-003, #49).

Contrat de l'app : les autres apps n'appellent que les fonctions de ce
module. Aucun modèle propre ; la commande est reçue en argument.
"""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def build_order_items_payload(commande):
    order_items = list(commande.order_items.select_related('product').all())
    return [
        {
            'title': item.product.title if item.product else 'Produit supprimé',
            'quantity': item.quantity,
            'price': str(item.price),
            'subtotal': str(item.price * item.quantity),
        }
        for item in order_items
    ]


def send_order_confirmation_email(commande):
    if not commande.email or commande.confirmation_email_sent:
        return False

    items = build_order_items_payload(commande)
    context = {
        'commande': commande,
        'items': items,
        'site_name': 'Dilane-shop',
    }

    subject = f"Confirmation de commande #{commande.id}"
    text_body = render_to_string('notifications/emails/order_confirmation_email.txt', context)
    html_body = None
    try:
        html_body = render_to_string('notifications/emails/order_confirmation_email.html', context)
    except Exception as exc:
        logger.exception(
            "HTML confirmation email rendering failed for order %s: %s",
            commande.id,
            exc,
        )

    email = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[commande.email],
    )
    if html_body:
        email.attach_alternative(html_body, 'text/html')
    email.send(fail_silently=False)

    commande.confirmation_email_sent = True
    commande.save(update_fields=['confirmation_email_sent'])
    return True
