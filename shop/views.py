# shop/views.py
from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.paginator import Paginator
from django.contrib.auth import login, logout
from .forms import SignupForm, EmailAuthenticationForm
from django.contrib.auth.decorators import login_required
from .models import Product, Commande
import json


def index(request):
    product_object = Product.objects.all()
    item_name = request.GET.get('item-name')
    if item_name:
        product_object = Product.objects.filter(title__icontains=item_name)
    paginator = Paginator(product_object, 4)
    page = request.GET.get('page')
    product_object = paginator.get_page(page)
    return render(request, 'shop/index.html', {'product_object': product_object})


def detail(request, myid):
    product_object = Product.objects.get(id=myid)
    return render(request, 'shop/detail.html', {'product': product_object})

@login_required(login_url='/connexion/')
def checkout(request):
    if request.method == "POST":
        # 1. Récupérer les infos client
        nom     = request.POST.get("nom", "").strip()
        email   = request.POST.get("email", "").strip()
        address = request.POST.get("address", "").strip()
        address2 = request.POST.get("address2", "").strip()
        ville   = request.POST.get("ville", "").strip()
        pays    = request.POST.get("pays", "").strip()
        zipcode = request.POST.get("zipcode", "").strip()

        # 2. Vérifier les champs obligatoires
        if not nom or not email or not address:
            return render(request, 'shop/checkout.html', {
                'error': 'Veuillez remplir tous les champs obligatoires.'
            })

        # 3. Récupérer les articles envoyés par le navigateur
        items_json = request.POST.get("items", "[]")

        try:
            items_data = json.loads(items_json)
            # items_data ressemble à :
            # [{"id": 1, "quantity": 2}, {"id": 3, "quantity": 1}]
        except (json.JSONDecodeError, TypeError):
            return render(request, 'shop/checkout.html', {
                'error': 'Panier invalide, veuillez réessayer.'
            })

        if not items_data:
            return render(request, 'shop/checkout.html', {
                'error': 'Votre panier est vide.'
            })

        # 4. LE POINT CLÉ : recalculer le total côté serveur
        #    On ignore complètement le prix envoyé par le navigateur
        total_calcule = 0
        items_verifies = []

        for item in items_data:
            try:
                product_id = int(item.get("id"))
                quantity   = int(item.get("quantity", 1))

                if quantity < 1:
                    continue

                product = Product.objects.get(id=product_id)

                # Vérifier qu'il y a assez de stock
                if product.stock < quantity:
                    return render(request, 'shop/checkout.html', {
                     'error': f'Stock insuffisant pour "{product.title}" (disponible : {product.stock})'
                 })

                prix_reel  = product.price
                sous_total = prix_reel * quantity
                total_calcule += sous_total

                items_verifies.append({
                    "id":       product.id,
                    "title":    product.title,
                    "price":    str(prix_reel),
                    "quantity": quantity,
                    "subtotal": str(sous_total),
                })

                # Décrémenter le stock
                product.stock -= quantity
                if product.stock == 0:
                    product.available = False  # plus disponible si stock = 0
                product.save()

            except (Product.DoesNotExist, ValueError, TypeError):
                # Produit introuvable ou données corrompues → on l'ignore
                continue

        if not items_verifies:
            return render(request, 'shop/checkout.html', {
                'error': 'Aucun produit valide dans le panier.'
            })

        # 5. Sauvegarder la commande avec le vrai total calculé par Django
        commande = Commande(
            items    = json.dumps(items_verifies),  # on sauvegarde la version vérifiée
            total    = total_calcule,               # ← notre total, pas celui du client
            nom      = nom,
            email    = email,
            address  = address,
            address2 = address2,
            ville    = ville,
            pays     = pays,
            zipcode  = zipcode,
            user     = request.user if request.user.is_authenticated else None,
        )
        commande.save()

        # 6. Message de succès et redirection
        messages.success(request, f"Merci {nom}, votre commande a bien été enregistrée !")
        return redirect('confirmation')

    return render(request, 'shop/checkout.html')


def confirmation(request):
    # On prend la dernière commande — plus robuste que [:1]
    commande = Commande.objects.order_by('-id').first()
    nom = commande.nom if commande else "Client"
    return render(request, 'shop/confirmation.html', {'nom': nom})


def inscription(request):
    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f"Bienvenue {user.username}, votre compte a été créé !")
            return redirect('home')
    else:
        form = SignupForm()
    return render(request, 'shop/inscription.html', {'form': form})


def connexion(request):
    if request.method == 'POST':
        form = EmailAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f"Bienvenue {user.username} !")
            return redirect('home')
    else:
        form = EmailAuthenticationForm(request)
    return render(request, 'shop/connexion.html', {'form': form})


def deconnexion(request):
    logout(request)
    messages.success(request, "Vous avez été déconnecté.")
    return redirect('home')


@login_required(login_url='/connexion/')
def profil(request):
    commandes = Commande.objects.filter(user=request.user).order_by('-date_commande')
    return render(request, 'shop/mes_commandes.html', {'commandes': commandes})