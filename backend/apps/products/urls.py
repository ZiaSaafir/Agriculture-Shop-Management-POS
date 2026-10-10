from django.urls import path

from .views import (
    BranchProductDetailView,
    BranchProductListView,
    ProductBranchOptionsView,
    ProductCatalogOptionsView,
)

app_name = "products"

urlpatterns = [
    path("branches/", ProductBranchOptionsView.as_view(), name="branch-options"),
    path(
        "branches/<int:branch_id>/options/",
        ProductCatalogOptionsView.as_view(),
        name="catalog-options",
    ),
    path(
        "branches/<int:branch_id>/",
        BranchProductListView.as_view(),
        name="branch-product-list",
    ),
    path(
        "branches/<int:branch_id>/<int:product_id>/",
        BranchProductDetailView.as_view(),
        name="branch-product-detail",
    ),
]
