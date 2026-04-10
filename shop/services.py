import logging
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse

logger = logging.getLogger(__name__)

try:
    import stripe
except ImportError:
    stripe = None


def stripe_is_configured():
    return bool(
        stripe
        and settings.STRIPE_SECRET_KEY
        and settings.STRIPE_PUBLIC_KEY
    )


def get_tax_rate_percent():
    raw_rate = str(getattr(settings, 'TAX_RATE_PERCENT', '20'))
    try:
        return Decimal(raw_rate)
    except Exception:
        return Decimal('20')


def calculate_tax_totals(subtotal_ht):
    rate_percent = get_tax_rate_percent()
    tax_amount = (subtotal_ht * rate_percent / Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    total_ttc = (subtotal_ht + tax_amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return rate_percent, tax_amount, total_ttc


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
    text_body = render_to_string('shop/emails/order_confirmation_email.txt', context)
    html_body = render_to_string('shop/emails/order_confirmation_email.html', context)

    email = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[commande.email],
    )
    email.attach_alternative(html_body, 'text/html')
    email.send(fail_silently=False)

    commande.confirmation_email_sent = True
    commande.save(update_fields=['confirmation_email_sent'])
    return True


def build_stripe_line_items(items_verifies, tax_amount=None, rate_percent=None):
    line_items = []
    for item in items_verifies:
        unit_amount = int(Decimal(item['price']) * 100)
        line_items.append(
            {
                'price_data': {
                    'currency': 'eur',
                    'product_data': {'name': item['title']},
                    'unit_amount': unit_amount,
                },
                'quantity': item['quantity'],
            }
        )

    if tax_amount and tax_amount > 0:
        rate_label = rate_percent if rate_percent is not None else get_tax_rate_percent()
        line_items.append(
            {
                'price_data': {
                    'currency': 'eur',
                    'product_data': {'name': f"TVA ({rate_label}%)"},
                    'unit_amount': int(Decimal(tax_amount) * 100),
                },
                'quantity': 1,
            }
        )

    return line_items


def create_stripe_checkout_session(
    request,
    commande,
    items_verifies,
    customer_email,
    tax_amount=None,
    rate_percent=None,
):
    if not stripe_is_configured():
        return None

    stripe.api_key = settings.STRIPE_SECRET_KEY
    domain = request.build_absolute_uri('/').rstrip('/')
    success_url = (
        f"{domain}{reverse('payment_success')}?session_id={{CHECKOUT_SESSION_ID}}&order_id={commande.id}"
    )
    cancel_url = f"{domain}{reverse('payment_cancel')}?order_id={commande.id}"

    return stripe.checkout.Session.create(
        mode='payment',
        payment_method_types=['card'],
        customer_email=customer_email,
        line_items=build_stripe_line_items(items_verifies, tax_amount=tax_amount, rate_percent=rate_percent),
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={'commande_id': str(commande.id)},
    )


def sync_commande_payment_from_stripe(commande, session_id=None):
    if not stripe_is_configured():
        return commande.payment_status

    target_session_id = session_id or commande.stripe_checkout_session_id
    if not target_session_id:
        return commande.payment_status

    stripe.api_key = settings.STRIPE_SECRET_KEY
    session = stripe.checkout.Session.retrieve(target_session_id)

    if session.payment_status == 'paid':
        payment_intent = getattr(session, 'payment_intent', None)
        if hasattr(payment_intent, 'id'):
            payment_intent = payment_intent.id

        commande.payment_status = 'paid'
        commande.status = 'confirmed'
        if payment_intent:
            commande.payment_reference = str(payment_intent)
        commande.save(update_fields=['payment_status', 'status', 'payment_reference'])

        if not commande.confirmation_email_sent:
            try:
                send_order_confirmation_email(commande)
            except Exception as exc:
                logger.exception("Order confirmation email failed for order %s: %s", commande.id, exc)
    else:
        commande.payment_status = 'processing'
        commande.save(update_fields=['payment_status'])

    return commande.payment_status