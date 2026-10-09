"""Règles de la commande : calcul de la TVA (ADR-003, #49).

Contrat de l'app orders : les autres apps (shop, payments) n'appellent que
les fonctions de ce module.
"""
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings


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
