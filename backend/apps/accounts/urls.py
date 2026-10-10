from django.urls import path

from .api import (
    CurrentUserView,
    DashboardAccessView,
    InventoryAccessView,
    LoginView,
    LogoutView,
    SalesAccessView,
    csrf_token,
)

app_name = "accounts"

urlpatterns = [
    path("csrf/", csrf_token, name="csrf"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", CurrentUserView.as_view(), name="me"),
    path("protected/dashboard/", DashboardAccessView.as_view(), name="dashboard-access"),
    path("protected/sales/", SalesAccessView.as_view(), name="sales-access"),
    path(
        "protected/inventory/",
        InventoryAccessView.as_view(),
        name="inventory-access",
    ),
]
