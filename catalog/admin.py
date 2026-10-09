from django.contrib import admin

from .models import Category, Product


@admin.register(Category)
class AdminCategorie(admin.ModelAdmin):
    list_display = ('name', 'date_added')


@admin.register(Product)
class AdminProduct(admin.ModelAdmin):
    list_display  = ('title', 'price', 'category', 'stock')
    search_fields = ('title',)
    list_editable = ('price', 'stock')
