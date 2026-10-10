from django.urls import path

from .views import (
    BranchCustomerDetailView,
    BranchCustomerLedgerView,
    BranchCustomerListView,
)

app_name = "customers"

urlpatterns = [
    path(
        "branches/<int:branch_id>/",
        BranchCustomerListView.as_view(),
        name="branch-customer-list",
    ),
    path(
        "branches/<int:branch_id>/<int:customer_id>/",
        BranchCustomerDetailView.as_view(),
        name="branch-customer-detail",
    ),
    path(
        "branches/<int:branch_id>/<int:customer_id>/ledger/",
        BranchCustomerLedgerView.as_view(),
        name="branch-customer-ledger",
    ),
]
