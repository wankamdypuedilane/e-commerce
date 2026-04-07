from django.shortcuts import render, redirect
from .models import Product, Commande
from django.core.paginator import Paginator

def index (request):
    product_object = Product.objects.all()
    item_name = request.GET.get('item-name')
    if(item_name != '' and item_name is not None):
        product_object = Product.objects.filter(title__icontains=item_name)
    paginator = Paginator(product_object, 4)
    page = request.GET.get('page')
    product_object=paginator.get_page(page)
    return render(request, 'shop/index.html', {'product_object':product_object})

def detail(request,myid):
    product_object = Product.objects.get(id=myid)
    return render(request, 'shop/detail.html', {'product':product_object })

def checkout(request):
    if(request.method == "POST"):
        items=request.POST.get("items")
        total=request.POST.get("total")
        nom=request.POST.get("nom")
        email=request.POST.get("email")
        address=request.POST.get("address")
        address2=request.POST.get("address2")
        ville=request.POST.get("ville")
        pays=request.POST.get("pays")
        zipcode=request.POST.get("zipcode")

        if not nom or not email or not address:
            return render(request, 'shop/checkout.html', {'error': 'Veuillez remplir tous les champs'})

        com=Commande(items=items, total=total, nom=nom, email=email, address=address, address2=address2, ville=ville, pays=pays, zipcode=zipcode)
        com.save()
        return redirect('confirmation')

        
    return render(request, 'shop/checkout.html')

def confirmation (request):
    info=Commande.objects.all()[:1]
    for item in info :
        nom=item.nom
    return render(request, 'shop/confirmation.html', {'nom': nom})

# Create your views here.
