from django.urls import path

from .views import (
    BranchSaleCheckoutView,
    BranchSaleDetailView,
    BranchSaleListView,
    BranchSaleReturnsView,
    BranchSalesOptionsView,
)

app_name = "sales"

urlpatterns = [
    path("branches/", BranchSalesOptionsView.as_view(), name="branch-options"),
    path(
        "branches/<int:branch_id>/",
        BranchSaleListView.as_view(),
        name="branch-sale-list",
    ),
    path(
        "branches/<int:branch_id>/<int:sale_id>/",
        BranchSaleDetailView.as_view(),
        name="branch-sale-detail",
    ),
    path(
        "branches/<int:branch_id>/<int:sale_id>/checkout/",
        BranchSaleCheckoutView.as_view(),
        name="branch-sale-checkout",
    ),
    path(
        "branches/<int:branch_id>/<int:sale_id>/returns/",
        BranchSaleReturnsView.as_view(),
        name="branch-sale-returns",
    ),
]
