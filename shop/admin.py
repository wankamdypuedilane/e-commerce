from django.contrib import admin

# Réglages communs à tout le back-office. Les modèles sont enregistrés par
# leurs apps : catalog/admin.py et orders/admin.py.
admin.site.site_header = "E-commerce"
admin.site.site_title = "SBC-shop"
admin.site.index_title = "Manageur"
