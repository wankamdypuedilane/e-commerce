from django.contrib import admin
from .models import Category, Product, Commande, OrderItem
from django.utils.safestring import mark_safe

admin.site.site_header = "E-commerce"
admin.site.site_title = "SBC-shop"
admin.site.index_title = "Manageur"


class AdminCategorie(admin.ModelAdmin):
    list_display = ('name', 'date_added')


class AdminProduct(admin.ModelAdmin):
    list_display  = ('title', 'price', 'category', 'stock')
    search_fields = ('title',)
    list_editable = ('price', 'stock')  

class AdminCommande(admin.ModelAdmin):
    list_display  = ('panier_lisible', 'nom', 'email', 'subtotal_ht', 'tax_amount', 'total', 'status', 'payment_status', 'date_commande')
    search_fields = ('nom', 'email', 'payment_reference', 'stripe_checkout_session_id')
    list_editable = ('status', 'payment_status')
    inlines = []

    def panier_lisible(self, obj):
        order_items = obj.order_items.select_related('product').all()
        if order_items.exists():
            res = ""
            for item in order_items:
                title = item.product.title if item.product else "Produit supprimé"
                subtotal = item.price * item.quantity
                res += f"<b>{title}</b> x{item.quantity} — {subtotal} €<br>"
            return mark_safe(res)

        return "Détails indisponibles"

    panier_lisible.short_description = "Articles commandés"


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'price', 'quantity')
    can_delete = False


AdminCommande.inlines = [OrderItemInline]


admin.site.register(Product, AdminProduct)
admin.site.register(Category, AdminCategorie)
admin.site.register(Commande, AdminCommande)


@admin.register(OrderItem)
class AdminOrderItem(admin.ModelAdmin):
    list_display = ('commande', 'product', 'price', 'quantity')
    list_select_related = ('commande', 'product')