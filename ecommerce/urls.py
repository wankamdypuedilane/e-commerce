"""
URL configuration for ecommerce project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views

urlpatterns = [
    path(
        'admin/password_reset/',
        auth_views.PasswordResetView.as_view(
            template_name='admin/password_reset_form.html',
            email_template_name='admin/password_reset_email.html',
            subject_template_name='registration/password_reset_subject.txt',
            success_url='/admin/password_reset/done/',
        ),
        name='admin_password_reset',
    ),
    path(
        'admin/password_reset/done/',
        auth_views.PasswordResetDoneView.as_view(
            template_name='admin/password_reset_done.html',
        ),
        name='admin_password_reset_done',
    ),
    path(
        'admin/reset/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(
            template_name='admin/password_reset_confirm.html',
            success_url='/admin/reset/done/',
        ),
        name='admin_password_reset_confirm',
    ),
    path(
        'admin/reset/done/',
        auth_views.PasswordResetCompleteView.as_view(
            template_name='admin/password_reset_complete.html',
        ),
        name='admin_password_reset_complete',
    ),
    path('admin/', admin.site.urls),
    path('',include('shop.urls'))
]
