from django.urls import path

from .views import (
    BranchSupplierDetailView,
    BranchSupplierLedgerView,
    BranchSupplierListView,
)

app_name = "suppliers"

urlpatterns = [
    path(
        "branches/<int:branch_id>/",
        BranchSupplierListView.as_view(),
        name="branch-supplier-list",
    ),
    path(
        "branches/<int:branch_id>/<int:supplier_id>/",
        BranchSupplierDetailView.as_view(),
        name="branch-supplier-detail",
    ),
    path(
        "branches/<int:branch_id>/<int:supplier_id>/ledger/",
        BranchSupplierLedgerView.as_view(),
        name="branch-supplier-ledger",
    ),
]
