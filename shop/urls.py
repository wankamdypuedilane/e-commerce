from django.urls import path
from django.contrib.auth import views as auth_views
from shop.views import index, detail, checkout, confirmation, inscription, connexion, deconnexion, profil

urlpatterns = [
    path('', index, name='home'),
    path('<int:myid>', detail, name='detail'),
    path('checkout', checkout, name="checkout"),
    path('confirmation', confirmation, name="confirmation"),
    path('inscription/', inscription, name='inscription'),
    path('connexion/', connexion, name='connexion'),
    path(
        'mot-de-passe-oublie/',
        auth_views.PasswordResetView.as_view(
            template_name='shop/password_reset_form.html',
            email_template_name='registration/password_reset_email.html',
            subject_template_name='registration/password_reset_subject.txt',
        ),
        name='password_reset'
    ),
    path(
        'mot-de-passe-oublie/envoye/',
        auth_views.PasswordResetDoneView.as_view(template_name='shop/password_reset_done.html'),
        name='password_reset_done'
    ),
    path(
        'reinitialisation/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(template_name='shop/password_reset_confirm.html'),
        name='password_reset_confirm'
    ),
    path(
        'reinitialisation/terminee/',
        auth_views.PasswordResetCompleteView.as_view(template_name='shop/password_reset_complete.html'),
        name='password_reset_complete'
    ),
    path('deconnexion/', deconnexion, name='deconnexion'),
    path('profil/', profil, name='profil'),
]
