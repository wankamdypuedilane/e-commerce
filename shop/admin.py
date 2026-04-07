import json 
from django.contrib import admin
from .models import Category, Product, Commande
from django.utils.safestring import mark_safe

# Register your models here.
admin.site.site_header = "E-commerce"
admin.site.site_title = "SBC-shop"
admin.site.index_title = "Manageur"


class AdminCategorie(admin.ModelAdmin):
    list_display = ('name', 'date_added')

class AdminProduct(admin.ModelAdmin):
    list_display = ('title','price','category','category__date_added')
    search_fields = ('title',)
    ist_editable = ('price',)

class AdminCommande(admin.ModelAdmin):
    list_display = ('panier_lisible','nom', 'email','address', 'ville', 'pays', 'total','date_commande')
    search_fields = ('nom', 'email')

    def panier_lisible(self, obj):
        try:
            # On transforme le texte JSON en dictionnaire Python
            panier = json.loads(obj.items)
            res = ""
            for key, value in panier.items():
                # value[0] = quantité, value[1] = nom du produit
                res += f"<b>{value[1]}</b> (x{value[0]})<br>"
            
            # mark_safe permet à Django d'afficher les balises <b> et <br>
            return mark_safe(res)
        except:
            return "Erreur de format"
    
    # On donne un nom propre à la colonne dans l'admin
    panier_lisible.short_description = "Articles commandés"

admin.site.register(Product, AdminProduct)
admin.site.register(Category, AdminCategorie)
admin.site.register(Commande, AdminCommande)