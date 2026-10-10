from django.urls import path

from .views import BranchInventoryView, BranchStockMovementsView

app_name = "inventory"

urlpatterns = [
    path(
        "branches/<int:branch_id>/stock/",
        BranchInventoryView.as_view(),
        name="branch-stock",
    ),
    path(
        "branches/<int:branch_id>/movements/",
        BranchStockMovementsView.as_view(),
        name="branch-stock-movements",
    ),
]
