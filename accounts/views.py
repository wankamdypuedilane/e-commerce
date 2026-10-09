"""Inscription, connexion et déconnexion (ADR-003, #49).

Déplacées de shop/views.py sans changement de comportement.
"""
from django.contrib import messages
from django.contrib.auth import login, logout
from django.shortcuts import redirect, render

from .forms import EmailAuthenticationForm, SignupForm

BACKEND = 'accounts.backends.EmailOrUsernameModelBackend'


def inscription(request):
    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Chemin explicite : deux chemins du même moteur sont déclarés
            # pendant la transition (voir settings.AUTHENTICATION_BACKENDS).
            login(request, user, backend=BACKEND)
            messages.success(request, f"Bienvenue {user.username}, votre compte a été créé !")
            return redirect('home')
    else:
        form = SignupForm()
    return render(request, 'accounts/inscription.html', {'form': form})


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
    return render(request, 'accounts/connexion.html', {'form': form})


def deconnexion(request):
    logout(request)
    messages.success(request, "Vous avez été déconnecté.")
    return redirect('home')
