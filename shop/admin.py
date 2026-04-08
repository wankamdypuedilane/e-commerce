import json 
from django.contrib import admin
from .models import Category, Product, Commande
from django.utils.safestring import mark_safe

admin.site.site_header = "E-commerce"
admin.site.site_title = "SBC-shop"
admin.site.index_title = "Manageur"


class AdminCategorie(admin.ModelAdmin):
    list_display = ('name', 'date_added')


class AdminProduct(admin.ModelAdmin):
    list_display  = ('title', 'price', 'category', 'available', 'stock')
    search_fields = ('title',)
    list_editable = ('price', 'stock')  

class AdminCommande(admin.ModelAdmin):
    list_display  = ('panier_lisible', 'nom', 'email', 'address', 'ville', 'pays', 'total', 'status', 'date_commande')
    search_fields = ('nom', 'email')
    list_editable = ('status',)

    def panier_lisible(self, obj):
        try:
            # items est maintenant une LISTE de dicts, pas un dictionnaire
            items = json.loads(obj.items)
            res = ""
            for item in items:
                res += f"<b>{item['title']}</b> x{item['quantity']} — {item['subtotal']} €<br>"
            return mark_safe(res)
        except Exception as e:
            return f"Erreur : {e}"

    panier_lisible.short_description = "Articles commandés"


admin.site.register(Product, AdminProduct)
admin.site.register(Category, AdminCategorie)
admin.site.register(Commande, AdminCommande)