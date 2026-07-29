from django.urls import path

from . import views


app_name = "tunnels"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("login/", views.TunnelLoginView.as_view(), name="login"),
    path("register/", views.register, name="register"),
    path("logout/", views.sign_out, name="logout"),
]
